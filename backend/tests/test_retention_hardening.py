"""Tests for data retention policy enforcement, safe deletion, worker concurrency, and scheduler."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.storage import StorageBackend
from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
    AuditEvent,
    Document,
    DocumentVersion,
    Institution,
    ProcessingJob,
    RetentionRunRecord,
)
from backend.app.services.retention_scheduler import RetentionBackgroundScheduler
from backend.app.services.retention_service import RetentionService
from backend.app.worker.tasks import periodic_retention_pass_task, set_worker_session_factory


class MockStorageBackend(StorageBackend):
    def __init__(self, should_fail: bool = False) -> None:
        self.files: dict[str, bytes] = {}
        self.deleted_keys: list[str] = []
        self.should_fail = should_fail

    def store(self, key: str, data: bytes) -> str:
        self.files[key] = data
        return key

    def retrieve(self, key: str) -> bytes:
        if key not in self.files:
            raise KeyError(key)
        return self.files[key]

    def delete(self, key: str) -> bool:
        if self.should_fail:
            raise IOError("Simulated S3/Disk I/O communication failure during deletion.")
        self.deleted_keys.append(key)
        self.files.pop(key, None)
        return True


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_dry_run_mode_does_not_delete(db_session: Session):
    """Dry-run mode inspects and counts candidates without deleting files or DB records."""
    inst = Institution(institution_id="INST-RET-01", display_name="College A")
    db_session.add(inst)
    db_session.flush()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    db_session.add(app)
    db_session.flush()

    doc = Document(application_id=app.id, document_type="land_document")
    db_session.add(doc)
    db_session.flush()

    old_date = datetime.now(timezone.utc) - timedelta(days=60)
    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key="quarantine/stale_malware.pdf",
        sha256="m"*64,
        media_type="application/pdf",
        byte_size=500,
        scan_status="rejected",
        uploaded_at=old_date,
    )
    db_session.add(ver)
    db_session.commit()

    storage = MockStorageBackend()
    storage.store("quarantine/stale_malware.pdf", b"fake malicious content")

    purged, errs = RetentionService.purge_stale_quarantined_files(
        db_session,
        storage=storage,
        max_age_days=30,
        dry_run=True,
        return_summary=True,
    )

    assert purged == 1
    assert errs == 0
    # Nothing was actually deleted
    assert "quarantine/stale_malware.pdf" in storage.files
    db_ver = db_session.get(DocumentVersion, ver.id)
    assert db_ver is not None


def test_storage_failure_preserves_database_record(db_session: Session):
    """If physical storage deletion fails, the DB record is NOT deleted, preventing orphaned storage."""
    inst = Institution(institution_id="INST-RET-02", display_name="College B")
    db_session.add(inst)
    db_session.flush()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    db_session.add(app)
    db_session.flush()

    doc = Document(application_id=app.id, document_type="fire_safety_certificate")
    db_session.add(doc)
    db_session.flush()

    old_date = datetime.now(timezone.utc) - timedelta(days=45)
    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key="quarantine/failed_delete.pdf",
        sha256="f"*64,
        media_type="application/pdf",
        byte_size=500,
        scan_status="rejected",
        uploaded_at=old_date,
    )
    db_session.add(ver)
    db_session.commit()

    failing_storage = MockStorageBackend(should_fail=True)

    purged, errs = RetentionService.purge_stale_quarantined_files(
        db_session,
        storage=failing_storage,
        max_age_days=30,
        dry_run=False,
        return_summary=True,
    )

    assert purged == 0
    assert errs == 1

    # Record MUST still exist in database
    db_ver = db_session.get(DocumentVersion, ver.id)
    assert db_ver is not None

    # Audit event must record storage failure
    fail_events = list(
        db_session.scalars(
            select(AuditEvent).where(AuditEvent.action == "QUARANTINED_PURGE_STORAGE_FAILED")
        ).all()
    )
    assert len(fail_events) == 1
    assert fail_events[0].target_id == str(ver.id)


def test_successful_purge_deletes_storage_and_db_with_audit(db_session: Session):
    """When storage deletion succeeds, the DB record is deleted and audit event logged."""
    inst = Institution(institution_id="INST-RET-03", display_name="College C")
    db_session.add(inst)
    db_session.flush()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    db_session.add(app)
    db_session.flush()

    doc = Document(application_id=app.id, document_type="fire_safety_certificate")
    db_session.add(doc)
    db_session.flush()

    old_date = datetime.now(timezone.utc) - timedelta(days=45)
    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key="quarantine/clean_purge.pdf",
        sha256="c"*64,
        media_type="application/pdf",
        byte_size=500,
        scan_status="rejected",
        uploaded_at=old_date,
    )
    db_session.add(ver)
    db_session.commit()

    storage = MockStorageBackend()
    storage.store("quarantine/clean_purge.pdf", b"infected content")

    purged, errs = RetentionService.purge_stale_quarantined_files(
        db_session,
        storage=storage,
        max_age_days=30,
        dry_run=False,
        return_summary=True,
    )

    assert purged == 1
    assert errs == 0
    assert "quarantine/clean_purge.pdf" not in storage.files

    # DB record was purged
    db_ver = db_session.get(DocumentVersion, ver.id)
    assert db_ver is None

    # Audit event logged
    audit_events = list(
        db_session.scalars(
            select(AuditEvent).where(AuditEvent.action == "QUARANTINED_FILE_PURGED")
        ).all()
    )
    assert len(audit_events) == 1
    assert audit_events[0].target_id == str(ver.id)


def test_in_flight_processing_jobs_preserved(db_session: Session):
    """In-flight jobs ('queued', 'running', 'processing') are NEVER deleted by retention passes."""
    old_date = datetime.now(timezone.utc) - timedelta(days=30)

    job_in_flight = ProcessingJob(
        id="job-active-1",
        document_version_id=1,
        job_type="document_intake_pipeline",
        state="running",
        updated_at=old_date,
    )
    job_completed_old = ProcessingJob(
        id="job-old-2",
        document_version_id=2,
        job_type="document_intake_pipeline",
        state="completed",
        updated_at=old_date,
    )
    job_failed_old = ProcessingJob(
        id="job-old-3",
        document_version_id=3,
        job_type="document_intake_pipeline",
        state="failed",
        updated_at=old_date,
    )

    db_session.add_all([job_in_flight, job_completed_old, job_failed_old])
    db_session.commit()

    cleaned = RetentionService.cleanup_old_processing_jobs(db_session, completed_retention_days=14)

    assert cleaned == 2
    # In-flight job must still exist
    assert db_session.get(ProcessingJob, "job-active-1") is not None
    assert db_session.get(ProcessingJob, "job-old-2") is None
    assert db_session.get(ProcessingJob, "job-old-3") is None


def test_audit_logs_and_packages_never_purged(db_session: Session):
    """System audit events are immutable and never deleted by retention passes."""
    old_date = datetime.now(timezone.utc) - timedelta(days=365 * 2)
    event = AuditEvent(
        action="APPLICATION_SUBMITTED",
        target_type="Application",
        target_id="1",
        actor_id="officer",
        created_at=old_date,
    )
    db_session.add(event)
    db_session.commit()

    storage = MockStorageBackend()
    run_rec = RetentionService.run_retention_pass(db_session, storage=storage, execution_type="manual")

    assert run_rec.status == "completed"
    # AuditEvent remains completely untouched
    preserved = db_session.get(AuditEvent, event.id)
    assert preserved is not None


def test_concurrency_protection(db_session: Session):
    """An active running pass blocks concurrent retention executions."""
    active_run = RetentionRunRecord(
        run_reference="RET-ACTIVE-001",
        execution_type="scheduled",
        status="running",
        triggered_by="worker_1",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    db_session.add(active_run)
    db_session.commit()

    # Second pass attempt
    second_run = RetentionService.run_retention_pass(db_session, execution_type="scheduled")
    assert second_run.run_reference == "RET-ACTIVE-001"
    assert second_run.status == "running"


def test_periodic_retention_pass_celery_task(db_session: Session):
    """The periodic Celery task executes successfully and returns summary statistics."""
    factory = sessionmaker(bind=db_session.get_bind())
    set_worker_session_factory(factory)

    try:
        res = periodic_retention_pass_task.apply(kwargs={"dry_run": True}).get()
        assert res["status"] == "completed"
        assert "run_reference" in res
    finally:
        set_worker_session_factory(None)


def test_background_scheduler_lifecycle(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    """RetentionBackgroundScheduler start, status, and graceful stop."""
    scheduler = RetentionBackgroundScheduler(interval_seconds=3600)
    assert not scheduler.is_running()

    # 1. By default without ENABLE_INPROCESS_RETENTION_SCHEDULER, start() remains disabled
    monkeypatch.delenv("ENABLE_INPROCESS_RETENTION_SCHEDULER", raising=False)
    scheduler.start()
    assert not scheduler.is_running()
    status_default = scheduler.get_status(db=db_session)
    assert status_default["primary_scheduler"] == "celery_beat"
    assert status_default["celery_beat_configured"] is True
    assert status_default["inprocess_scheduler_enabled"] is False

    # 2. When explicitly enabled for dev/test or forced, scheduler starts and stops gracefully
    scheduler.start(force=True)
    assert scheduler.is_running()

    status = scheduler.get_status(db=db_session)
    assert status["scheduler_running"] is True
    assert status["schedule_interval_seconds"] == 3600
    assert status["audit_log_retention_years"] == 7

    scheduler.stop()
    assert not scheduler.is_running()
