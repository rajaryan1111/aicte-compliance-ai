"""Tests for Task B7: Background Processing, Durable Jobs, Outbox Dispatch, and Status Polling."""

from __future__ import annotations

from collections.abc import Generator
import io
from pathlib import Path
import tempfile
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.dispatcher import dispatch_outbox_message, dispatch_pending_outbox
from backend.app.core.rbac import ROLE_INSTITUTION_ADMIN
from backend.app.core.scanner import MalwareScanner, ScanResult, ScanStatus, set_malware_scanner
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.core.storage import LocalStorageBackend, set_storage_backend
from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
    AuditEvent,
    Document,
    DocumentVersion,
    ExtractedField,
    Institution,
    OutboxMessage,
    User,
)
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.repositories.outbox_repository import OutboxRepository
from backend.app.repositories.processing_job_repository import ProcessingJobRepository
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.processing_job_service import ProcessingJobService
from backend.app.worker.celery_app import celery_app
from backend.app.worker.tasks import set_worker_session_factory
from backend.tests.test_document_processing import create_synthetic_pdf_bytes

VALID_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\n\x00\x00\x00\n\x08\x02\x00\x00\x00"
    b"\x02PX\xea\x00\x00\x00\x16IDATx\x9cc\xfc\xff\xff?\x03n\xc0\x84G\x8ea\xe4J\x03\x00"
    b"\xa5\xe3\x03\x11\xc7z\x1cU\x00\x00\x00\x00IEND\xaeB`\x82"
)


TEST_JWT_SECRET = "test-secret-key-minimum-32-characters-for-hs256-compliance!!"


class MockScanner(MalwareScanner):
    """Deterministic mock scanner for test doubles."""

    def __init__(self, status: ScanStatus = ScanStatus.CLEAN, details: str = "Test scan") -> None:
        self.status = status
        self.details = details

    def scan(self, data: bytes, filename: str | None = None) -> ScanResult:
        return ScanResult(
            status=self.status,
            scanner_name="MockScanner",
            details=self.details,
        )


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Configure in-memory storage, mock clean scanner, and Celery eager execution for tests."""
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    temp_dir = tempfile.mkdtemp(prefix="test_jobs_storage_")
    storage = LocalStorageBackend(base_dir=Path(temp_dir))
    set_storage_backend(storage)
    set_malware_scanner(MockScanner(ScanStatus.CLEAN))

    # Configure Celery to run tasks eagerly within the test process
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    yield

    set_storage_backend(None)  # type: ignore[arg-type]
    set_malware_scanner(None)  # type: ignore[arg-type]



@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Isolated in-memory database session."""
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


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient with overridden database session."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_user(db: Session, username: str) -> User:
    user = UserRepository.create(
        db,
        username=username,
        hashed_password=get_password_hash("Secret123!"),
    )
    db.commit()
    db.refresh(user)
    return user


def create_institution(db: Session, inst_id: str) -> Institution:
    inst = Institution(institution_id=inst_id, display_name=f"Inst {inst_id}")
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


def create_application(db: Session, institution_id: int) -> Application:
    app_record = Application(
        institution_id=institution_id,
        application_type="eoa",
        academic_year="2026-2027",
        status="draft",
    )
    db.add(app_record)
    db.commit()
    db.refresh(app_record)
    return app_record


def assign_role(db: Session, user_id: int, inst_id: int, role: str) -> None:
    UserRepository.create_membership(db, user_id=user_id, institution_id=inst_id, role=role)
    db.commit()


def auth_header(user: User) -> dict[str, str]:
    token = create_access_token(subject=user.id, extra_claims={"username": user.username})
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# SECTION A: Durable Job & Outbox Creation on Upload
# ==============================================================================


def test_durable_job_and_outbox_created_on_upload(client: TestClient, db_session: Session):
    """Uploading a document creates a durable ProcessingJob and OutboxMessage."""
    user = create_user(db_session, "job_uploader_1")
    inst = create_institution(db_session, "INST-JOB-01")
    app_rec = create_application(db_session, inst.id)
    assign_role(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN)

    with patch("backend.app.api.v1.documents.dispatch_outbox_message") as mock_dispatch:
        files = {"file": ("test.png", io.BytesIO(VALID_PNG_BYTES), "image/png")}
        headers = auth_header(user)
        headers["Prefer"] = "respond-async"

        r = client.post(
            f"/api/v1/applications/{app_rec.id}/documents",
            files=files,
            data={"document_type": "land_document"},
            headers=headers,
        )
        assert r.status_code == 202
        body = r.json()
        assert body["job"] is not None
        job_id = body["job"]["id"]
        assert body["job"]["state"] == "queued"
        assert body["polling_url"] == f"/api/v1/applications/{app_rec.id}/documents/{body['document']['id']}/versions/{body['version']['id']}/processing"

        # Verify job persisted in DB
        job = ProcessingJobRepository.get_by_id(db_session, job_id)
        assert job is not None
        assert job.document_version_id == body["version"]["id"]
        assert job.attempt_count == 0

        # Verify outbox message created
        outbox_msgs = list(db_session.scalars(select(OutboxMessage)).all())
        assert len(outbox_msgs) == 1
        assert outbox_msgs[0].topic == "document_processing"
        mock_dispatch.assert_called_once()


# ==============================================================================
# SECTION B: Outbox Dispatch, Failure Recovery, and Redispatch
# ==============================================================================


def test_outbox_broker_failure_and_recovery(db_session: Session):
    """Simulate message broker failure: outbox marks failed, recovery redispatches."""
    inst = create_institution(db_session, "INST-OUTBOX-01")
    app_rec = create_application(db_session, inst.id)
    doc = Document(application_id=app_rec.id, document_type="test_doc")
    db_session.add(doc)
    db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key="docs/test.bin",
        sha256="0" * 64,
        media_type="image/png",
        byte_size=100,
        scan_status="pending_scan",
        processing_status="queued",
    )
    db_session.add(ver)
    db_session.flush()

    job = ProcessingJobRepository.create_job(db_session, ver.id)
    outbox_msg = OutboxRepository.create_message(
        db_session,
        topic="document_processing",
        payload={"job_id": job.id, "document_version_id": ver.id},
    )
    db_session.commit()

    # 1. Simulate Celery broker connection error on dispatch
    with patch("backend.app.core.dispatcher.process_document_job_task.delay", side_effect=ConnectionError("Redis connection refused")):
        success = dispatch_outbox_message(db_session, outbox_msg)
        assert success is False
        db_session.refresh(outbox_msg)
        assert outbox_msg.status == "failed"
        assert "Redis connection refused" in (outbox_msg.last_error or "")

    # 2. Re-dispatch / recovery with working broker
    with patch("backend.app.core.dispatcher.process_document_job_task.delay") as mock_delay:
        # Mark status back to pending or test dispatch_pending_outbox
        outbox_msg.status = "pending"
        db_session.commit()

        recovered_count = dispatch_pending_outbox(db_session)
        assert recovered_count == 1
        db_session.refresh(outbox_msg)
        assert outbox_msg.status == "published"
        mock_delay.assert_called_once_with(job.id)


# ==============================================================================
# SECTION C: Worker Stages, Malware Gate, and Advisory Extraction
# ==============================================================================


def test_worker_clean_scan_runs_ocr_and_completes(db_session: Session):
    """A clean scan allows the worker to proceed to OCR and finalize the job."""
    inst = create_institution(db_session, "INST-WORKER-01")
    app_rec = create_application(db_session, inst.id)
    doc = Document(application_id=app_rec.id, document_type="land_docs")
    db_session.add(doc)
    db_session.flush()

    pdf_bytes = create_synthetic_pdf_bytes([
        "Institution Name: Test Engineering College",
        "Valid Until: 2029-06-30",
        "Issue Date: 2024-01-15",
    ])
    from backend.app.core.storage import get_storage_backend
    storage = get_storage_backend()
    storage_key = "docs/worker_clean.pdf"
    storage.put(storage_key, pdf_bytes)

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=storage_key,
        sha256="1" * 64,
        media_type="application/pdf",
        byte_size=len(pdf_bytes),
        file_name="clean.pdf",
        scan_status="pending_scan",
        processing_status="queued",
    )
    db_session.add(ver)
    db_session.flush()

    job = ProcessingJobRepository.create_job(db_session, ver.id)
    db_session.commit()

    # Run the worker job with clean scanner
    updated_job = ProcessingJobService.run_job(
        db_session,
        job_id=job.id,
        scanner=MockScanner(ScanStatus.CLEAN),
    )
    assert updated_job is not None
    assert updated_job.state == "completed"
    assert updated_job.attempt_count == 1

    db_session.refresh(ver)
    assert ver.scan_status == "clean"
    assert ver.processing_status == "succeeded"

    # Verify extracted fields were persisted
    fields = list(db_session.scalars(select(ExtractedField).where(ExtractedField.document_version_id == ver.id)).all())
    assert len(fields) >= 2


def test_worker_malware_gate_rejects_and_prevents_ocr(db_session: Session):
    """A malicious file is rejected by the worker: OCR is blocked, job marked failed, download blocked."""
    inst = create_institution(db_session, "INST-WORKER-MAL")
    app_rec = create_application(db_session, inst.id)
    doc = Document(application_id=app_rec.id, document_type="eoa_doc")
    db_session.add(doc)
    db_session.flush()

    storage = LocalStorageBackend(base_dir=Path(tempfile.mkdtemp()))
    storage_key = "docs/malware.bin"
    storage.put(storage_key, b"VIRUS_PAYLOAD")

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=storage_key,
        sha256="2" * 64,
        media_type="application/pdf",
        byte_size=13,
        file_name="infected.pdf",
        scan_status="pending_scan",
        processing_status="queued",
    )
    db_session.add(ver)
    db_session.flush()

    job = ProcessingJobRepository.create_job(db_session, ver.id)
    db_session.commit()

    # Run worker with REJECTED mock scanner
    updated_job = ProcessingJobService.run_job(
        db_session,
        job_id=job.id,
        scanner=MockScanner(ScanStatus.REJECTED, details="Signature EICAR found"),
        storage=storage,
    )
    assert updated_job is not None
    assert updated_job.state == "failed"
    assert updated_job.last_error_code == "MALWARE_DETECTED"

    db_session.refresh(ver)
    assert ver.scan_status == "rejected"
    assert ver.processing_status == "rejected"

    # Verify NO extracted fields exist
    fields = list(db_session.scalars(select(ExtractedField).where(ExtractedField.document_version_id == ver.id)).all())
    assert len(fields) == 0

    # Verify audit event recorded
    events = list(db_session.scalars(select(AuditEvent).where(AuditEvent.action == "DOCUMENT_SCAN_REJECTED")).all())
    assert len(events) == 1
    assert "malware_scan_rejected" in (events[0].details or "")


def test_worker_unavailable_scanner_quarantines_and_schedules_retry(db_session: Session):
    """An unavailable scanner does not fail open: status stays scan_unavailable, job waits for retry."""
    inst = create_institution(db_session, "INST-WORKER-UNAVAIL")
    app_rec = create_application(db_session, inst.id)
    doc = Document(application_id=app_rec.id, document_type="eoa_doc")
    db_session.add(doc)
    db_session.flush()

    storage = LocalStorageBackend(base_dir=Path(tempfile.mkdtemp()))
    storage_key = "docs/unavail.bin"
    storage.put(storage_key, VALID_PNG_BYTES)

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=storage_key,
        sha256="3" * 64,
        media_type="image/png",
        byte_size=len(VALID_PNG_BYTES),
        file_name="unavail.png",
        scan_status="pending_scan",
        processing_status="queued",
    )
    db_session.add(ver)
    db_session.flush()

    job = ProcessingJobRepository.create_job(db_session, ver.id, max_attempts=3)
    db_session.commit()

    updated_job = ProcessingJobService.run_job(
        db_session,
        job_id=job.id,
        scanner=MockScanner(ScanStatus.SCAN_UNAVAILABLE, details="ClamAV daemon offline"),
        storage=storage,
    )
    assert updated_job is not None
    assert updated_job.state == "retry_wait"
    assert updated_job.last_error_code == "SCANNER_UNAVAILABLE"
    assert updated_job.scheduled_for is not None

    db_session.refresh(ver)
    assert ver.scan_status == "scan_unavailable"


def test_worker_max_retries_exhaustion(db_session: Session):
    """When a job exceeds max_attempts, it transitions to failed/blocked rather than retrying indefinitely."""
    inst = create_institution(db_session, "INST-RETRY-EXH")
    app_rec = create_application(db_session, inst.id)
    doc = Document(application_id=app_rec.id, document_type="eoa_doc")
    db_session.add(doc)
    db_session.flush()

    storage = LocalStorageBackend(base_dir=Path(tempfile.mkdtemp()))
    storage_key = "docs/exhaust.bin"
    storage.put(storage_key, VALID_PNG_BYTES)

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=storage_key,
        sha256="4" * 64,
        media_type="image/png",
        byte_size=len(VALID_PNG_BYTES),
        file_name="exhaust.png",
        scan_status="pending_scan",
        processing_status="queued",
    )
    db_session.add(ver)
    db_session.flush()

    job = ProcessingJobRepository.create_job(db_session, ver.id, max_attempts=1)
    job.attempt_count = 1
    db_session.commit()

    updated_job = ProcessingJobService.run_job(
        db_session,
        job_id=job.id,
        scanner=MockScanner(ScanStatus.SCAN_UNAVAILABLE),
        storage=storage,
    )
    assert updated_job is not None
    assert updated_job.state in ("failed", "blocked")
    assert updated_job.last_error_code in ("SCANNER_UNAVAILABLE", "MAX_RETRIES_EXCEEDED")


def test_worker_idempotent_reprocessing(db_session: Session):
    """Re-running processing on a version clears old fields/findings and avoids duplicate records."""
    inst = create_institution(db_session, "INST-IDEMP-01")
    app_rec = create_application(db_session, inst.id)
    doc = Document(application_id=app_rec.id, document_type="aicte_approval")
    db_session.add(doc)
    db_session.flush()

    pdf_bytes = create_synthetic_pdf_bytes([
        "Institution Name: Idempotent Institute",
        "Valid Until: 2028-12-31",
    ])
    from backend.app.core.storage import get_storage_backend
    storage = get_storage_backend()
    storage_key = "docs/idempotent.pdf"
    storage.put(storage_key, pdf_bytes)

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=storage_key,
        sha256="5" * 64,
        media_type="application/pdf",
        byte_size=len(pdf_bytes),
        file_name="idemp.pdf",
        scan_status="pending_scan",
        processing_status="queued",
    )
    db_session.add(ver)
    db_session.flush()

    job = ProcessingJobRepository.create_job(db_session, ver.id)
    db_session.commit()

    # First run
    ProcessingJobService.run_job(db_session, job_id=job.id, scanner=MockScanner(ScanStatus.CLEAN))
    fields_run1 = list(db_session.scalars(select(ExtractedField).where(ExtractedField.document_version_id == ver.id)).all())
    count1 = len(fields_run1)
    assert count1 >= 1

    # Second run (simulating retry / redelivery)
    job.state = "queued"
    db_session.commit()

    ProcessingJobService.run_job(db_session, job_id=job.id, scanner=MockScanner(ScanStatus.CLEAN))
    fields_run2 = list(db_session.scalars(select(ExtractedField).where(ExtractedField.document_version_id == ver.id)).all())
    assert len(fields_run2) == count1, "Reprocessing must not duplicate extracted fields"


# ==============================================================================
# SECTION D: Status Polling & Tenant Security
# ==============================================================================


def test_status_polling_authenticated_flow(client: TestClient, db_session: Session):
    """Authorized user can poll document processing status and receive accurate metadata."""
    user = create_user(db_session, "poll_user")
    inst = create_institution(db_session, "INST-POLL-01")
    app_rec = create_application(db_session, inst.id)
    assign_role(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN)

    doc = Document(application_id=app_rec.id, document_type="land_docs")
    db_session.add(doc)
    db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key="docs/poll.bin",
        sha256="6" * 64,
        media_type="image/png",
        byte_size=100,
        scan_status="clean",
        processing_status="succeeded",
    )
    db_session.add(ver)
    db_session.flush()

    job = ProcessingJobRepository.create_job(db_session, ver.id)
    job.state = "completed"
    db_session.commit()

    headers = auth_header(user)
    r = client.get(
        f"/api/v1/applications/{app_rec.id}/documents/{doc.id}/versions/{ver.id}/processing",
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["job_id"] == job.id
    assert data["state"] == "completed"
    assert data["scan_status"] == "clean"
    assert data["processing_status"] == "succeeded"
    assert data["is_terminal"] is True


def test_status_polling_cross_tenant_concealment(client: TestClient, db_session: Session):
    """User from another institution receives 404 concealment when polling processing status."""
    user_a = create_user(db_session, "user_inst_a")
    inst_a = create_institution(db_session, "INST-A")
    app_a = create_application(db_session, inst_a.id)
    assign_role(db_session, user_a.id, inst_a.id, ROLE_INSTITUTION_ADMIN)

    user_b = create_user(db_session, "user_inst_b")
    inst_b = create_institution(db_session, "INST-B")
    assign_role(db_session, user_b.id, inst_b.id, ROLE_INSTITUTION_ADMIN)

    doc_a = Document(application_id=app_a.id, document_type="eoa_doc")
    db_session.add(doc_a)
    db_session.flush()
    ver_a = DocumentVersion(
        document_id=doc_a.id,
        version_number=1,
        storage_key="docs/secret.bin",
        sha256="7" * 64,
        media_type="image/png",
        byte_size=100,
        scan_status="clean",
        processing_status="succeeded",
    )
    db_session.add(ver_a)
    db_session.flush()
    ProcessingJobRepository.create_job(db_session, ver_a.id)
    db_session.commit()

    # User B attempts to poll Institution A's document processing status
    r = client.get(
        f"/api/v1/applications/{app_a.id}/documents/{doc_a.id}/versions/{ver_a.id}/processing",
        headers=auth_header(user_b),
    )
    assert r.status_code == 404
    assert r.json()["detail"] in ("Application not found", "Resource not found or access denied.")


def test_status_polling_unauthenticated_rejected(client: TestClient):
    """Unauthenticated request to status polling is rejected with 401."""
    r = client.get("/api/v1/applications/1/documents/1/versions/1/processing")
    assert r.status_code == 401
