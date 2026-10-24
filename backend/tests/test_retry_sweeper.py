"""Regression tests: retry_wait jobs must actually be re-dispatched.

Before this fix ``ProcessingJobRepository.get_retryable_jobs`` had no caller
anywhere in the application. A transient failure therefore parked a job in
``retry_wait`` with a ``scheduled_for`` timestamp that nothing ever acted on, so
the document was never scanned: the bounded-retry policy was dead code in a real
deployment even though the unit that computed the backoff was correct.

``sweep_due_retries_task`` is the caller. These tests pin the three properties
that matter: only due jobs are dispatched, a broker error for one job does not
abort the sweep, and re-dispatch does not bypass the atomic claim (so duplicate
delivery still processes a job once).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
    Document,
    DocumentVersion,
    Institution,
    OutboxMessage,
    ProcessingJob,
)
from backend.app.repositories.outbox_repository import OutboxRepository
from backend.app.repositories.processing_job_repository import ProcessingJobRepository
from backend.app.worker import tasks as worker_tasks
from backend.app.worker.celery_app import celery_app
from backend.app.worker.tasks import set_worker_session_factory, sweep_due_retries_task


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    set_worker_session_factory(factory)
    yield factory
    set_worker_session_factory(None)
    engine.dispose()


@pytest.fixture()
def dispatched(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record dispatch calls instead of publishing to a broker."""
    calls: list[str] = []

    def fake_delay(job_id: str, *args: Any, **kwargs: Any) -> None:
        calls.append(job_id)

    monkeypatch.setattr(worker_tasks.process_document_job_task, "delay", fake_delay)
    return calls


def _build_job(factory, *, state: str, scheduled_for=None, suffix: str = "1") -> ProcessingJob:
    """Persist a minimal application/document/version/job chain."""
    from datetime import datetime, timezone

    db = factory()
    try:
        institution = Institution(
            institution_id=f"INST-{suffix}", display_name=f"Institution {suffix}"
        )
        db.add(institution)
        db.flush()
        application = Application(
            institution_id=institution.id,
            application_type="eoa",
            academic_year="2026-2027",
            status="draft",
        )
        db.add(application)
        db.flush()
        document = Document(application_id=application.id, document_type="affiliation_application")
        db.add(document)
        db.flush()
        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            storage_key=f"documents/{suffix}.pdf",
            file_name=f"{suffix}.pdf",
            media_type="application/pdf",
            byte_size=10,
            sha256="0" * 64,
        )
        db.add(version)
        db.flush()
        job = ProcessingJob(
            id=str(uuid.uuid4()),
            document_version_id=version.id,
            job_type="document_processing",
            state=state,
            attempt_count=1,
            max_attempts=3,
            scheduled_for=scheduled_for,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job
    finally:
        db.close()


def test_only_due_retry_jobs_are_dispatched(session_factory, dispatched) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    due = _build_job(session_factory, state="retry_wait", scheduled_for=now - timedelta(seconds=5), suffix="a")
    _build_job(session_factory, state="retry_wait", scheduled_for=now + timedelta(hours=1), suffix="b")
    _build_job(session_factory, state="queued", suffix="c")
    _build_job(session_factory, state="completed", suffix="d")

    result = sweep_due_retries_task()

    assert result == {"due": 1, "dispatched": 1, "outbox_redispatched": 0}
    assert dispatched == [due.id]


def test_a_broker_error_does_not_abort_the_sweep(session_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    first = _build_job(session_factory, state="retry_wait", scheduled_for=now - timedelta(seconds=5), suffix="e")
    second = _build_job(session_factory, state="retry_wait", scheduled_for=now - timedelta(seconds=4), suffix="f")

    attempted: list[str] = []

    def flaky_delay(job_id: str, *args: Any, **kwargs: Any) -> None:
        attempted.append(job_id)
        if job_id == first.id:
            raise ConnectionError("broker down")

    monkeypatch.setattr(worker_tasks.process_document_job_task, "delay", flaky_delay)

    result = sweep_due_retries_task()

    # Both were attempted; only the successful one counts as dispatched, and the
    # failure did not stop the second job from being handed to the broker.
    assert attempted == [first.id, second.id]
    assert result == {"due": 2, "dispatched": 1, "outbox_redispatched": 0}


def test_sweep_does_not_bypass_the_atomic_claim(session_factory, dispatched) -> None:
    """Duplicate delivery stays safe: the second consumer loses the claim."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    job = _build_job(session_factory, state="retry_wait", scheduled_for=now - timedelta(seconds=5), suffix="g")

    sweep_due_retries_task()
    assert dispatched == [job.id]

    db = session_factory()
    try:
        first_claim = ProcessingJobRepository.claim_job(db, job.id)
        assert first_claim is not None and first_claim.state == "scanning"
        db.commit()
    finally:
        db.close()

    db = session_factory()
    try:
        second_claim = ProcessingJobRepository.claim_job(db, job.id)
        db.commit()
    finally:
        db.close()

    assert second_claim is None, "a duplicate delivery must not process an already-claimed job"


# ---------------------------------------------------------------------------
# Outbox recovery: failed publish messages must not strand their job forever.

# ``mark_failed`` documents that a failed message is "preserved for the
# recovery worker", but until now the sweep only looked at ``pending``
# messages, so a broker outage during publish left the message failed forever
# and its document queued with zero attempts. The sweep may now republish
# retryable failed messages; these tests pin the properties.


def _build_failed_outbox(factory) -> tuple[Any, str]:
    """Persist job + outbox message, marking the message failed (as real broker outage would)."""
    job = _build_job(factory, state="queued", suffix="outbox")
    db = factory()
    try:
        msg = OutboxRepository.create_message(
            db,
            topic="document_processing",
            payload={"job_id": job.id, "document_version_id": 1},
        )
        OutboxRepository.mark_failed(db, msg.id, "Retry limit exceeded while trying to reconnect to the Celery result store")
        db.commit()
        return job, msg.id
    finally:
        db.close()


def test_failed_outbox_message_is_republished_by_the_sweep(session_factory, dispatched) -> None:
    job, msg_id = _build_failed_outbox(session_factory)

    result = sweep_due_retries_task()

    assert result["outbox_redispatched"] == 1
    assert job.id in dispatched  # the stranded job was handed to the broker again
    db = session_factory()
    try:
        saved = db.get(OutboxMessage, msg_id)
        assert saved is not None and saved.status == "published"
    finally:
        db.close()


def test_outbox_republish_failure_records_the_error_and_retries_later(
    session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    job, msg_id = _build_failed_outbox(session_factory)

    def broken_delay(job_id: str, *args: Any, **kwargs: Any) -> None:
        raise ConnectionError("broker down again")

    monkeypatch.setattr(worker_tasks.process_document_job_task, "delay", broken_delay)

    result = sweep_due_retries_task()

    assert result["outbox_redispatched"] == 0
    db = session_factory()
    try:
        saved = db.get(OutboxMessage, msg_id)
        assert saved is not None
        assert saved.status == "failed"
        assert saved.retry_count == 2  # original failure + this sweep's failure
        assert "broker down again" in (saved.last_error or "")
        # Still below the cap, so the next sweep gets another chance.
        assert saved in OutboxRepository.get_retryable_failed_messages(db)
    finally:
        db.close()


def test_outbox_republish_stops_at_the_retry_cap(session_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    job, msg_id = _build_failed_outbox(session_factory)

    def publish_only(job_id: str, *args: Any, **kwargs: Any) -> None:
        raise ConnectionError("broker permanently down for this test")

    monkeypatch.setattr(worker_tasks.process_document_job_task, "delay", publish_only)

    # Exhaust the retry budget with repeated failed sweeps.
    for _ in range(5):
        sweep_due_retries_task()

    db = session_factory()
    try:
        saved = db.get(OutboxMessage, msg_id)
        assert saved is not None
        assert saved.status == "failed"
        assert saved.retry_count >= 5
        # At the cap the message is no longer offered for redispatch.
        assert OutboxRepository.get_retryable_failed_messages(db) == []
    finally:
        db.close()


def test_beat_schedule_includes_the_retry_sweep() -> None:
    """Without a scheduled entry the task would never run in a deployment."""
    schedule = celery_app.conf.beat_schedule

    assert "sweep-due-retries" in schedule
    assert schedule["sweep-due-retries"]["task"] == "backend.app.worker.tasks.sweep_due_retries_task"
    assert float(schedule["sweep-due-retries"]["schedule"]) > 0
