"""Tests for the beat-scheduled recovery sweep.

The sweep (``backend.app.core.dispatcher.run_recovery_sweep``, published by the
Celery beat task ``recovery_sweep_task``) is the only mechanism that recovers
three stranded-work states:

1. outbox messages never published (pending, or failed under the retry cap),
2. ``retry_wait`` jobs whose backoff window has elapsed,
3. ``queued`` jobs whose broker delivery was lost.

Before these tests existed, none of that was scheduled anywhere: the recovery
functions were reachable only by calling them by hand, so a deployed instance
would strand every retried job and every failed outbox message forever.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Generator
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.dispatcher import (
    STALE_QUEUED_AGE_SECONDS,
    run_recovery_sweep,
)
from backend.app.db.models import (
    Application,
    Base,
    Document,
    DocumentVersion,
    Institution,
    ProcessingJob,
)
from backend.app.repositories.outbox_repository import (
    MAX_DELIVERY_ATTEMPTS,
    OutboxRepository,
)
from backend.app.repositories.processing_job_repository import ProcessingJobRepository
from backend.app.worker.celery_app import celery_app
from backend.app.worker.tasks import recovery_sweep_task, set_worker_session_factory

DELAY_TARGET = "backend.app.core.dispatcher.process_document_job_task.delay"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Isolated in-memory database session, wired as the worker session factory."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    set_worker_session_factory(session_factory)
    session = session_factory()
    try:
        yield session
    finally:
        set_worker_session_factory(None)
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _seed_version(db: Session, tag: str) -> DocumentVersion:
    inst = Institution(institution_id=f"INST-RECOV-{tag}", display_name=f"Recovery {tag}")
    db.add(inst)
    db.flush()
    app = Application(
        institution_id=inst.id,
        application_type="eoa",
        academic_year="2026-2027",
        status="draft",
    )
    db.add(app)
    db.flush()
    doc = Document(application_id=app.id, document_type="test_doc")
    db.add(doc)
    db.flush()
    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"docs/test/{tag}.bin",
        sha256="0" * 64,
        media_type="application/pdf",
        byte_size=128,
        scan_status="pending_scan",
        processing_status="queued",
    )
    db.add(ver)
    db.flush()
    return ver


def _seed_job(
    db: Session,
    tag: str,
    *,
    state: str,
    scheduled_for: datetime | None = None,
    updated_at: datetime | None = None,
) -> ProcessingJob:
    ver = _seed_version(db, tag)
    job = ProcessingJobRepository.create_job(db, ver.id, max_attempts=3)
    job.state = state
    if scheduled_for is not None:
        job.scheduled_for = scheduled_for
    if updated_at is not None:
        job.updated_at = updated_at
    db.commit()
    return job


def test_beat_schedule_registers_the_recovery_sweep_exactly_once() -> None:
    """The sweep must be on the beat schedule with the canonical task name.

    ``recovery_sweep_task`` is the production entry point; if the schedule
    entry drifts from its registered task name, beat silently schedules a task
    nothing handles and recovery stops again.
    """
    schedule = celery_app.conf.beat_schedule
    sweep_entries = [
        entry for entry in schedule.values() if entry["task"] == recovery_sweep_task.name
    ]
    assert len(sweep_entries) == 1, schedule
    assert schedule["recovery-sweep"] is sweep_entries[0]
    assert sweep_entries[0]["schedule"] == timedelta(seconds=30)
    assert recovery_sweep_task.name == "backend.app.worker.tasks.recovery_sweep_task"


def test_sweep_requeues_only_retry_wait_jobs_whose_backoff_elapsed(
    db_session: Session,
) -> None:
    now = _utc_now()
    due = _seed_job(
        db_session, "due", state="retry_wait", scheduled_for=now - timedelta(seconds=5)
    )
    not_yet_due = _seed_job(
        db_session, "later", state="retry_wait", scheduled_for=now + timedelta(seconds=600)
    )
    fresh = _seed_job(db_session, "fresh", state="queued", updated_at=now)
    done = _seed_job(db_session, "done", state="completed")

    with patch(DELAY_TARGET) as mock_delay:
        result = run_recovery_sweep(db_session, now=now)

    assert result["retry_jobs_requeued"] == 1
    mock_delay.assert_called_once_with(due.id)
    assert not_yet_due.state == "retry_wait"
    assert fresh.state == "queued"
    assert done.state == "completed"


def test_sweep_requeues_stale_queued_jobs_and_throttles_redelivery(
    db_session: Session,
) -> None:
    """A queued job past the staleness window is re-published once, then left alone.

    The requeue bumps ``updated_at`` so a job whose broker delivery is lost is
    re-published at most once per stale window instead of every sweep tick.
    """
    now = _utc_now()
    stale = _seed_job(
        db_session,
        "stale",
        state="queued",
        updated_at=now - timedelta(seconds=STALE_QUEUED_AGE_SECONDS + 60),
    )

    with patch(DELAY_TARGET) as mock_delay:
        first = run_recovery_sweep(db_session, now=now)
    assert first["stale_jobs_requeued"] == 1
    mock_delay.assert_called_once_with(stale.id)

    db_session.refresh(stale)
    assert stale.updated_at is not None

    with patch(DELAY_TARGET) as mock_delay:
        second = run_recovery_sweep(db_session, now=now + timedelta(seconds=1))
    assert second["stale_jobs_requeued"] == 0
    mock_delay.assert_not_called()


def test_sweep_recovers_failed_outbox_messages_without_manual_reset(
    db_session: Session,
) -> None:
    """Broker-failed outbox messages are re-dispatched as ``failed``, no manual flip.

    Older tests worked around this gap by setting ``status = "pending"`` by
    hand before calling the recovery function — the gap is now fixed at the
    query, so recovery must work from the recorded ``failed`` state itself.
    """
    job = _seed_job(db_session, "outbox", state="queued", updated_at=_utc_now())
    msg = OutboxRepository.create_message(
        db_session,
        topic="document_processing",
        payload={"job_id": job.id},
    )
    db_session.commit()

    with patch(DELAY_TARGET, side_effect=ConnectionError("broker refused")):
        assert run_recovery_sweep(db_session)["outbox_dispatched"] == 0
    db_session.refresh(msg)
    assert msg.status == "failed"
    assert msg.retry_count == 1

    with patch(DELAY_TARGET) as mock_delay:
        result = run_recovery_sweep(db_session)
    assert result["outbox_dispatched"] == 1
    db_session.refresh(msg)
    assert msg.status == "published"
    mock_delay.assert_called_once_with(job.id)


def test_outbox_messages_at_the_retry_cap_are_not_retried_forever(
    db_session: Session,
) -> None:
    """Permanently undeliverable messages stop at the cap instead of looping forever."""
    job = _seed_job(db_session, "cap", state="queued", updated_at=_utc_now())
    msg = OutboxRepository.create_message(
        db_session,
        topic="document_processing",
        payload={"job_id": job.id},
    )
    msg.status = "failed"
    msg.retry_count = MAX_DELIVERY_ATTEMPTS
    db_session.commit()

    with patch(DELAY_TARGET) as mock_delay:
        result = run_recovery_sweep(db_session)

    assert result["outbox_dispatched"] == 0
    mock_delay.assert_not_called()
    db_session.refresh(msg)
    assert msg.status == "failed"
    assert msg.retry_count == MAX_DELIVERY_ATTEMPTS


def test_recovery_sweep_task_entry_point_runs_the_sweep(db_session: Session) -> None:
    """The Celery task beat actually schedules must drive the sweep end to end."""
    now = _utc_now()
    due = _seed_job(
        db_session, "task", state="retry_wait", scheduled_for=now - timedelta(seconds=5)
    )

    with patch(DELAY_TARGET) as mock_delay:
        result: dict[str, Any] = recovery_sweep_task()

    assert result["retry_jobs_requeued"] == 1
    assert result["outbox_dispatched"] == 0
    assert result["stale_jobs_requeued"] == 0
    mock_delay.assert_called_once_with(due.id)
