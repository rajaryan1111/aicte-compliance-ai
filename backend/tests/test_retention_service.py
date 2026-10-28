"""Tests for Data Retention and Deletion Service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
    Document,
    DocumentVersion,
    Institution,
    ProcessingJob,
)
from backend.app.services.retention_service import RetentionService


class MockStorageBackend:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def put(self, storage_key: str, data: bytes) -> int:
        self.store[storage_key] = data
        return len(data)

    def delete(self, storage_key: str) -> bool:
        return self.store.pop(storage_key, None) is not None

    def exists(self, storage_key: str) -> bool:
        return storage_key in self.store


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


def test_purge_stale_quarantined_files(db_session: Session):
    storage = MockStorageBackend()

    inst = Institution(institution_id="INST-RET-01", display_name="Retention College")
    db_session.add(inst)
    db_session.flush()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    db_session.add(app)
    db_session.flush()

    doc = Document(application_id=app.id, document_type="fire_safety_certificate")
    db_session.add(doc)
    db_session.flush()

    # Stale rejected file (45 days old)
    stale_key = "quarantine/stale_malware.pdf"
    storage.put(stale_key, b"malicious-bytes")
    ver_stale = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=stale_key,
        sha256="abc111" + "0" * 58,
        media_type="application/pdf",
        byte_size=15,
        scan_status="rejected",
        uploaded_at=datetime.now(timezone.utc) - timedelta(days=45),
    )

    # Fresh rejected file (5 days old)
    fresh_key = "quarantine/fresh_rejected.pdf"
    storage.put(fresh_key, b"rejected-bytes")
    ver_fresh = DocumentVersion(
        document_id=doc.id,
        version_number=2,
        storage_key=fresh_key,
        sha256="abc222" + "0" * 58,
        media_type="application/pdf",
        byte_size=14,
        scan_status="rejected",
        uploaded_at=datetime.now(timezone.utc) - timedelta(days=5),
    )

    # Clean file (60 days old)
    clean_key = "clean/valid.pdf"
    storage.put(clean_key, b"clean-bytes")
    ver_clean = DocumentVersion(
        document_id=doc.id,
        version_number=3,
        storage_key=clean_key,
        sha256="abc333" + "0" * 58,
        media_type="application/pdf",
        byte_size=11,
        scan_status="clean",
        uploaded_at=datetime.now(timezone.utc) - timedelta(days=60),
    )

    db_session.add_all([ver_stale, ver_fresh, ver_clean])
    db_session.commit()

    # Execute purge
    purged = RetentionService.purge_stale_quarantined_files(
        db_session, storage=storage, max_age_days=30
    )

    assert purged == 1
    assert not storage.exists(stale_key)
    assert storage.exists(fresh_key)
    assert storage.exists(clean_key)


def test_cleanup_old_processing_jobs(db_session: Session):
    inst = Institution(institution_id="INST-RET-02", display_name="Jobs College")
    db_session.add(inst)
    db_session.flush()

    app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
    db_session.add(app)
    db_session.flush()

    doc = Document(application_id=app.id, document_type="fire_safety_certificate")
    db_session.add(doc)
    db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key="test.pdf",
        sha256="abc" + "0" * 61,
        media_type="application/pdf",
        byte_size=10,
    )
    db_session.add(ver)
    db_session.flush()

    stale_id = str(uuid.uuid4())
    job_stale = ProcessingJob(
        id=stale_id,
        document_version_id=ver.id,
        job_type="ocr",
        state="completed",
        updated_at=datetime.now(timezone.utc) - timedelta(days=20),
    )

    # Fresh completed job (2 days old)
    fresh_id = str(uuid.uuid4())
    job_fresh = ProcessingJob(
        id=fresh_id,
        document_version_id=ver.id,
        job_type="classification",
        state="completed",
        updated_at=datetime.now(timezone.utc) - timedelta(days=2),
    )

    # Active running job (30 days old) - must NOT be deleted
    running_id = str(uuid.uuid4())
    job_running = ProcessingJob(
        id=running_id,
        document_version_id=ver.id,
        job_type="metadata_extraction",
        state="running",
        updated_at=datetime.now(timezone.utc) - timedelta(days=30),
    )

    db_session.add_all([job_stale, job_fresh, job_running])
    db_session.commit()

    deleted = RetentionService.cleanup_old_processing_jobs(db_session, completed_retention_days=14)
    assert deleted == 1
    assert db_session.get(ProcessingJob, stale_id) is None
    assert db_session.get(ProcessingJob, fresh_id) is not None
    assert db_session.get(ProcessingJob, running_id) is not None
