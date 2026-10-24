"""Integration tests verifying real Redis queue dispatch and Celery worker processing (Phase 4).

Proves asynchronous document processing with real Redis broker and Celery worker process.
Guarantees non-eager execution, job state transitions, outbox recovery, retry backoff,
idempotency, and safe terminal states.
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid
import time
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.dispatcher import dispatch_outbox_message, dispatch_pending_outbox
from backend.app.core.scanner import ScanResult, ScanStatus
from backend.app.core.storage import LocalStorageBackend, generate_storage_key
from backend.app.db.models import (
    OutboxMessage,
    Application,
    AuditEvent,
    Document,
    DocumentVersion,
    ExtractedField,
    Institution,
)
from backend.app.repositories.outbox_repository import OutboxRepository
from backend.app.repositories.processing_job_repository import ProcessingJobRepository
from backend.app.services.processing_job_service import ProcessingJobService
from backend.app.worker.celery_app import celery_app
from backend.app.worker.tasks import set_worker_session_factory
from backend.app.worker.tasks import process_document_job_task


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _unique_key_suffix() -> str:
    """Collision-free storage-key segment.

    ``document_versions.storage_key`` carries a UNIQUE index, so a fixed key
    makes the suite pass only on a pristine database and fail on every rerun.
    """
    return uuid.uuid4().hex




def _create_synthetic_pdf(text_lines: list[str]) -> bytes:
    """Build a minimal compliant PDF byte stream with text lines."""
    parts = ["BT /F1 12 Tf 50 700 Td"]
    for i, line in enumerate(text_lines):
        if i == 0:
            parts.append(f"({line}) Tj")
        else:
            parts.append(f"0 -20 Td ({line}) Tj")
    parts.append("ET")
    stream_data = " ".join(parts).encode("utf-8")
    stream_len = len(stream_data)

    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(stream_len).encode("utf-8") + b" >>\nstream\n"
        + stream_data + b"\nendstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000240 00000 n \n0000000350 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n450\n%%EOF"
    )


@pytest.fixture(autouse=True)
def setup_integration_env(require_live_postgres: str, require_live_redis: str, live_postgres_engine: Engine) -> None:
    """Configure in-process Celery to use real Redis and configure worker session factory."""
    celery_app.conf.broker_url = require_live_redis
    celery_app.conf.result_backend = require_live_redis
    # The producer must publish, not execute inline.  celery_app.py defaults this
    # to true under pytest; the worker subprocess is already non-eager, so the
    # two would otherwise disagree and no message would ever reach the broker.
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False
    set_worker_session_factory(sessionmaker(bind=live_postgres_engine))


def test_document_job_dispatched_and_processed_by_real_worker(
    live_celery_worker: Any,
    live_postgres_session: Session,
    require_live_redis: str,
) -> None:
    """Verify document job is dispatched through Redis queue and processed by a real Celery worker (Phase 4.1-4.3)."""
    # Enforce non-eager Celery mode for test dispatch
    celery_app.conf.task_always_eager = False

    code = f"INST-WORKER-{int(_utc_now().timestamp())}"
    inst = Institution(institution_id=code, display_name="Celery Worker Test Institute")
    live_postgres_session.add(inst)
    live_postgres_session.commit()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027", status="draft")
    live_postgres_session.add(app)
    live_postgres_session.commit()

    doc = Document(application_id=app.id, document_type="aicte_approval")
    live_postgres_session.add(doc)
    live_postgres_session.commit()

    # Create synthetic PDF and write to storage
    pdf_bytes = _create_synthetic_pdf([
        f"Institution ID: {code}",
        "Valid Until: 2029-06-30",
        "Academic Year: 2026-2027",
    ])
    storage = LocalStorageBackend()
    storage_key = generate_storage_key(extension=".pdf")
    storage.put(storage_key, pdf_bytes)

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=storage_key,
        sha256="0" * 64,
        media_type="application/pdf",
        byte_size=len(pdf_bytes),
        file_name="approval.pdf",
        scan_status="clean",
        processing_status="queued",
    )
    live_postgres_session.add(version)
    live_postgres_session.commit()
    doc.current_version_id = version.id
    live_postgres_session.commit()

    # Create durable ProcessingJob and OutboxMessage
    job = ProcessingJobRepository.create_job(
        live_postgres_session,
        document_version_id=version.id,
        max_attempts=3,
    )
    outbox_msg = OutboxRepository.create_message(
        live_postgres_session,
        topic="document_processing",
        payload={"job_id": job.id},
    )
    live_postgres_session.commit()

    # Dispatch via Outbox to real Redis broker
    dispatched = dispatch_outbox_message(live_postgres_session, outbox_msg)
    assert dispatched is True
    live_postgres_session.refresh(outbox_msg)
    assert outbox_msg.status == "published"

    # Poll PostgreSQL for real Celery worker execution (bounded timeout: 15s)
    deadline = time.time() + 15.0
    terminal_reached = False
    while time.time() < deadline:
        live_postgres_session.expire_all()
        refreshed_job = ProcessingJobRepository.get_by_id(live_postgres_session, job.id)
        if refreshed_job and refreshed_job.state in ("completed", "partial", "failed"):
            terminal_reached = True
            break
        time.sleep(0.3)

    assert terminal_reached is True, f"Celery worker did not process job {job.id} within 15 seconds"
    live_postgres_session.refresh(refreshed_job)
    assert refreshed_job.state in ("completed", "partial")

    live_postgres_session.refresh(version)
    assert version.scan_status == "clean"
    assert version.processing_status in ("completed", "succeeded", "partial")

    # Verify extracted fields were persisted to PostgreSQL
    fields = list(live_postgres_session.scalars(
        select(ExtractedField).where(ExtractedField.document_version_id == version.id)
    ).all())
    assert len(fields) > 0, "No extracted fields were persisted by the Celery worker"

    # Clean up
    live_postgres_session.delete(inst)
    live_postgres_session.commit()


def test_outbox_broker_failure_and_redispatch_recovery(
    live_postgres_session: Session,
    require_live_redis: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify outbox records failure when broker is unreachable and recovers on retry (Phase 4.4)."""
    code = f"INST-OUTBOX-{int(_utc_now().timestamp())}"
    inst = Institution(institution_id=code, display_name="Outbox Recovery Institute")
    live_postgres_session.add(inst)
    live_postgres_session.commit()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    live_postgres_session.add(app)
    live_postgres_session.commit()

    doc = Document(application_id=app.id, document_type="land_noc")
    live_postgres_session.add(doc)
    live_postgres_session.commit()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"docs/test/{_unique_key_suffix()}/outbox.pdf",
        sha256="1" * 64,
        media_type="application/pdf",
        byte_size=512,
        scan_status="clean",
        processing_status="queued",
    )
    live_postgres_session.add(ver)
    live_postgres_session.commit()

    job = ProcessingJobRepository.create_job(live_postgres_session, document_version_id=ver.id)
    outbox_msg = OutboxRepository.create_message(
        live_postgres_session,
        topic="document_processing",
        payload={"job_id": job.id},
    )
    live_postgres_session.commit()

    # Simulate broker failure by pointing to an unreachable broker port
    # Simulate the publish failing, at the publish boundary.
    #
    # Pointing broker_url at a dead port does NOT do this: Celery caches both a
    # connection pool and a producer pool per app, and neither app.close() nor
    # setting app._pool = None invalidates a warm producer -- verified, the
    # publish still succeeded and the old assertions passed without exercising
    # the failure path at all.  Patching the task's publish is therefore the
    # honest way to test the dispatcher's contract here; the recovery half below
    # still uses the real broker.
    def _broker_unreachable(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("broker unreachable (simulated publish failure)")

    monkeypatch.setattr(process_document_job_task, "delay", _broker_unreachable)
    success = dispatch_outbox_message(live_postgres_session, outbox_msg)
    assert success is False

    live_postgres_session.refresh(outbox_msg)
    assert outbox_msg.status == "failed"
    assert outbox_msg.last_error is not None
    assert "unreachable" in outbox_msg.last_error.lower()

    # The message must be preserved for redispatch, not dropped: the repository
    # has no get_by_id, so reload it through the session.
    live_postgres_session.expire_all()
    retained = live_postgres_session.get(OutboxMessage, outbox_msg.id)
    assert retained is not None, "failed outbox message must be retained for recovery"

    # Recovery: real broker again, and the retained message is republished.
    monkeypatch.undo()

    # Recovery: restore broker connectivity and run dispatch_pending_outbox
    outbox_msg.status = "pending"
    live_postgres_session.commit()

    recovered_count = dispatch_pending_outbox(live_postgres_session)
    assert recovered_count >= 1

    live_postgres_session.refresh(outbox_msg)
    assert outbox_msg.status == "published"

    # Clean up
    live_postgres_session.delete(inst)
    live_postgres_session.commit()


def test_retry_and_backoff_on_transient_error(
    live_postgres_session: Session,
) -> None:
    """Verify transient error initiates retry_wait with exponential backoff (Phase 4.5)."""
    code = f"INST-RETRY-{int(_utc_now().timestamp())}"
    inst = Institution(institution_id=code, display_name="Retry Test Institute")
    live_postgres_session.add(inst)
    live_postgres_session.commit()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    live_postgres_session.add(app)
    live_postgres_session.commit()

    doc = Document(application_id=app.id, document_type="land_noc")
    live_postgres_session.add(doc)
    live_postgres_session.commit()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"docs/test/{_unique_key_suffix()}/retry.pdf",
        sha256="2" * 64,
        media_type="application/pdf",
        byte_size=512,
        scan_status="clean",
        processing_status="queued",
    )
    live_postgres_session.add(ver)
    live_postgres_session.commit()

    job = ProcessingJobRepository.create_job(
        live_postgres_session,
        document_version_id=ver.id,
        max_attempts=3,
    )
    live_postgres_session.commit()

    # Mock scanner with transient failure
    class TransientFailingScanner:
        def scan(self, file_bytes: bytes, filename: str) -> ScanResult:
            raise ConnectionError("Transient network timeout to scanner socket")

    # Mock storage returning bytes
    class SimpleStorage:
        def read(self, key: str) -> bytes:
            return b"%PDF-1.4 mock content"

    updated_job = ProcessingJobService.run_job(
        live_postgres_session,
        job_id=job.id,
        scanner=TransientFailingScanner(),  # type: ignore[arg-type]
        storage=SimpleStorage(),  # type: ignore[arg-type]
    )

    assert updated_job is not None
    assert updated_job.attempt_count == 1
    assert updated_job.state == "retry_wait"
    assert updated_job.scheduled_for is not None
    assert updated_job.scheduled_for > _utc_now()
    assert updated_job.last_error_code == "ConnectionError"

    # Clean up
    live_postgres_session.delete(inst)
    live_postgres_session.commit()


def test_duplicate_task_delivery_idempotency(
    live_postgres_session: Session,
) -> None:
    """Verify duplicate task delivery does not duplicate versions, findings, or fields (Phase 4.6)."""
    code = f"INST-IDEMP-{int(_utc_now().timestamp())}"
    inst = Institution(institution_id=code, display_name="Idempotency Institute")
    live_postgres_session.add(inst)
    live_postgres_session.commit()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    live_postgres_session.add(app)
    live_postgres_session.commit()

    doc = Document(application_id=app.id, document_type="land_noc")
    live_postgres_session.add(doc)
    live_postgres_session.commit()

    storage = LocalStorageBackend()
    pdf_bytes = _create_synthetic_pdf([
        f"Institution ID: {code}",
        "Valid Until: 2030-01-01",
    ])
    key = generate_storage_key(extension=".pdf")
    storage.put(key, pdf_bytes)

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=key,
        sha256="3" * 64,
        media_type="application/pdf",
        byte_size=len(pdf_bytes),
        scan_status="clean",
        processing_status="queued",
    )
    live_postgres_session.add(ver)
    live_postgres_session.commit()

    job = ProcessingJobRepository.create_job(live_postgres_session, document_version_id=ver.id)
    live_postgres_session.commit()

    # Pass 1: initial execution
    res1 = ProcessingJobService.run_job(live_postgres_session, job.id)
    assert res1 is not None
    assert res1.state in ("completed", "partial")

    fields_count_1 = len(list(live_postgres_session.scalars(
        select(ExtractedField).where(ExtractedField.document_version_id == ver.id)
    ).all()))
    audit_count_1 = len(list(live_postgres_session.scalars(
        select(AuditEvent).where(AuditEvent.institution_id == inst.id)
    ).all()))

    # Pass 2: duplicate task delivery for terminal job
    res2 = ProcessingJobService.run_job(live_postgres_session, job.id)
    assert res2 is not None
    assert res2.state in ("completed", "partial")

    fields_count_2 = len(list(live_postgres_session.scalars(
        select(ExtractedField).where(ExtractedField.document_version_id == ver.id)
    ).all()))
    audit_count_2 = len(list(live_postgres_session.scalars(
        select(AuditEvent).where(AuditEvent.institution_id == inst.id)
    ).all()))

    # Assert no duplicate fields or duplicate audit events were created
    assert fields_count_2 == fields_count_1
    assert audit_count_2 == audit_count_1

    # Clean up
    live_postgres_session.delete(inst)
    live_postgres_session.commit()


def test_permanent_malware_detection_reaches_terminal_failure(
    live_postgres_session: Session,
) -> None:
    """Verify malware detection marks job permanently failed and creates audit event (Phase 4.8)."""
    code = f"INST-MALWARE-{int(_utc_now().timestamp())}"
    inst = Institution(institution_id=code, display_name="Malware Test Institute")
    live_postgres_session.add(inst)
    live_postgres_session.commit()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    live_postgres_session.add(app)
    live_postgres_session.commit()

    doc = Document(application_id=app.id, document_type="land_noc")
    live_postgres_session.add(doc)
    live_postgres_session.commit()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"docs/test/{_unique_key_suffix()}/malware.bin",
        sha256="4" * 64,
        media_type="application/pdf",
        byte_size=100,
        scan_status="pending_scan",
        processing_status="queued",
    )
    live_postgres_session.add(ver)
    live_postgres_session.commit()

    job = ProcessingJobRepository.create_job(live_postgres_session, document_version_id=ver.id)
    live_postgres_session.commit()

    class MaliciousScanner:
        def scan(self, file_bytes: bytes, filename: str) -> ScanResult:
            # ScanResult(status, scanner_name, details) -- scanner_name is
            # required and there is no engine_version field.
            return ScanResult(
                status=ScanStatus.REJECTED,
                scanner_name="clamav-test-double",
                details="Win.Test.EICAR_HDB-1 FOUND",
            )

    class SimpleStorage:
        def read(self, key: str) -> bytes:
            return b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"

    res = ProcessingJobService.run_job(
        live_postgres_session,
        job.id,
        scanner=MaliciousScanner(),  # type: ignore[arg-type]
        storage=SimpleStorage(),  # type: ignore[arg-type]
    )

    assert res is not None
    assert res.state == "failed"
    assert res.last_error_code == "MALWARE_DETECTED"

    live_postgres_session.refresh(ver)
    assert ver.scan_status == "rejected"
    assert ver.processing_status == "rejected"

    # Verify audit event recorded
    audit = live_postgres_session.scalar(
        select(AuditEvent).where(
            AuditEvent.institution_id == inst.id,
            AuditEvent.action == "DOCUMENT_SCAN_REJECTED",
        )
    )
    assert audit is not None
    assert "malware_scan_rejected" in audit.details

    # Clean up
    live_postgres_session.delete(inst)
    live_postgres_session.commit()


def test_authoritative_status_polling_returns_persisted_state(
    live_postgres_session: Session,
) -> None:
    """Verify status query returns the authoritative persisted state from PostgreSQL (Phase 4.9)."""
    code = f"INST-STATUS-{int(_utc_now().timestamp())}"
    inst = Institution(institution_id=code, display_name="Status Check Institute")
    live_postgres_session.add(inst)
    live_postgres_session.commit()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    live_postgres_session.add(app)
    live_postgres_session.commit()

    doc = Document(application_id=app.id, document_type="land_noc")
    live_postgres_session.add(doc)
    live_postgres_session.commit()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"docs/test/{_unique_key_suffix()}/status.pdf",
        sha256="5" * 64,
        media_type="application/pdf",
        byte_size=200,
        scan_status="clean",
        processing_status="completed",
    )
    live_postgres_session.add(ver)
    live_postgres_session.commit()

    job = ProcessingJobRepository.create_job(live_postgres_session, document_version_id=ver.id)
    ProcessingJobRepository.update_state(live_postgres_session, job, state="completed")
    live_postgres_session.commit()

    fetched_job = ProcessingJobRepository.get_latest_for_version(live_postgres_session, ver.id)
    assert fetched_job is not None
    assert fetched_job.id == job.id
    assert fetched_job.state == "completed"

    # Clean up
    live_postgres_session.delete(inst)
    live_postgres_session.commit()


def test_repeated_transient_failures_reach_terminal_failure(
    live_postgres_session: Session,
) -> None:
    """A job that keeps failing transiently must fail closed at max_attempts.

    Regression guard for a rollback bug: claim_job() increments attempt_count
    inside the unit of work, and the failure path rolled that back, so the
    counter read zero on every retry.  The backoff then stayed at 2**0 * 5s and
    the job could never satisfy ``attempt_count >= max_attempts`` -- it retried
    forever instead of failing closed, leaving the document permanently
    unscanned rather than terminally rejected.
    """
    code = f"INST-BOUNDED-{int(_utc_now().timestamp())}"
    inst = Institution(institution_id=code, display_name="Bounded Retry Institute")
    live_postgres_session.add(inst)
    live_postgres_session.commit()

    app_rec = Application(
        institution_id=inst.id, application_type="eoa", academic_year="2026-2027"
    )
    live_postgres_session.add(app_rec)
    live_postgres_session.commit()

    doc = Document(application_id=app_rec.id, document_type="land_noc")
    live_postgres_session.add(doc)
    live_postgres_session.commit()

    storage = LocalStorageBackend()
    key = generate_storage_key(extension=".pdf")
    storage.put(key, b"%PDF-1.4 bounded retry")
    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=key,
        sha256="6" * 64,
        media_type="application/pdf",
        byte_size=20,
        scan_status="pending_scan",
        processing_status="queued",
    )
    live_postgres_session.add(ver)
    live_postgres_session.commit()

    job = ProcessingJobRepository.create_job(
        live_postgres_session, document_version_id=ver.id, max_attempts=3
    )
    live_postgres_session.commit()

    class AlwaysTransientScanner:
        def scan(self, data: bytes, filename: str | None = None) -> ScanResult:
            raise ConnectionError("scanner socket unreachable")

    attempts_seen: list[int] = []
    for _ in range(job.max_attempts):
        updated = ProcessingJobService.run_job(
            live_postgres_session,
            job_id=job.id,
            scanner=AlwaysTransientScanner(),  # type: ignore[arg-type]
            storage=storage,
        )
        assert updated is not None
        attempts_seen.append(updated.attempt_count)

    # Every attempt is counted, so the counter advances 1..max_attempts.
    assert attempts_seen == list(range(1, job.max_attempts + 1))

    final = ProcessingJobRepository.get_by_id(live_postgres_session, job.id)
    assert final is not None
    assert final.state == "failed", "a repeatedly failing job must fail closed"
    assert final.last_error_code == "ConnectionError"

    live_postgres_session.refresh(ver)
    assert ver.processing_status == "failed"

    live_postgres_session.delete(inst)
    live_postgres_session.commit()
