"""Tests for authenticated document upload endpoints, upload validation, RBAC, and quarantine."""

from __future__ import annotations

from collections.abc import Generator
import io
import tempfile

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.rbac import (
    ROLE_AUDITOR,
    ROLE_INSTITUTION_ADMIN,
)
from backend.app.core.scanner import MalwareScanner, ScanResult, ScanStatus, set_malware_scanner
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.core.storage import LocalStorageBackend, set_storage_backend
from backend.app.db.base import Base
from backend.app.db.models import Application, AuditEvent, DocumentVersion, Institution, User
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.repositories.user_repository import UserRepository
from backend.app.worker.tasks import set_worker_session_factory

TEST_JWT_SECRET = "test-secret-key-minimum-32-characters-for-hs256-compliance!!"

# Valid 10x10 PNG bytes verified by Pillow
VALID_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\n\x00\x00\x00\n\x08\x02\x00\x00\x00"
    b"\x02PX\xea\x00\x00\x00\x16IDATx\x9cc\xfc\xff\xff?\x03n\xc0\x84G\x8ea\xe4J\x03\x00"
    b"\xa5\xe3\x03\x11\xc7z\x1cU\x00\x00\x00\x00IEND\xaeB`\x82"
)


# Valid minimal PDF bytes
VALID_PDF_BYTES = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer
<< /Size 4 /Root 1 0 R >>
startxref
192
%%EOF"""


class MockScanner(MalwareScanner):
    """Test double for malware scanner."""

    def __init__(self, status: ScanStatus = ScanStatus.CLEAN) -> None:
        self.status = status

    def scan(self, data: bytes, filename: str | None = None) -> ScanResult:
        return ScanResult(
            status=self.status,
            scanner_name="test_mock_scanner",
            details="Injected test scanner outcome",
        )


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch: pytest.MonkeyPatch):
    """Configure secure test JWT key, temp storage, and default clean mock scanner."""
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = LocalStorageBackend(base_dir=tmp_dir)
        set_storage_backend(storage)
        clean_scanner = MockScanner(ScanStatus.CLEAN)
        set_malware_scanner(clean_scanner)
        yield
        set_storage_backend(None)
        set_malware_scanner(None)



@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide isolated in-memory database session."""
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


def assign_role(db: Session, user_id: int, inst_id: int, role: str):
    UserRepository.create_membership(db, user_id=user_id, institution_id=inst_id, role=role)
    db.commit()


def auth_header(user: User) -> dict[str, str]:
    token = create_access_token(subject=user.id, extra_claims={"username": user.username})
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# SECTION A: Upload Intake and Format Validation Tests
# ==============================================================================


def test_upload_valid_png_and_pdf(client: TestClient, db_session: Session):
    """Verify successful upload of valid PNG and PDF documents."""
    user = create_user(db_session, "uploader_1")
    inst = create_institution(db_session, "INST-UP-01")
    app_rec = create_application(db_session, inst.id)
    assign_role(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN)

    headers = auth_header(user)

    # 1. Upload PNG
    files_png = {"file": ("scan.png", io.BytesIO(VALID_PNG_BYTES), "image/png")}
    data_png = {"document_type": "land_document"}
    r1 = client.post(f"/api/v1/applications/{app_rec.id}/documents", files=files_png, data=data_png, headers=headers)
    assert r1.status_code == 201
    resp_png = r1.json()
    assert resp_png["document"]["document_type"] == "land_document"
    assert resp_png["version"]["media_type"] == "image/png"
    assert resp_png["version"]["version_number"] == 1
    assert resp_png["version"]["storage_key"].startswith("docs/")

    # 2. Upload PDF
    files_pdf = {"file": ("approval.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
    data_pdf = {"document_type": "aicte_approval"}
    r2 = client.post(f"/api/v1/applications/{app_rec.id}/documents", files=files_pdf, data=data_pdf, headers=headers)
    assert r2.status_code == 201
    resp_pdf = r2.json()
    assert resp_pdf["document"]["document_type"] == "aicte_approval"
    assert resp_pdf["version"]["media_type"] == "application/pdf"
    assert resp_pdf["version"]["page_count"] == 1


def test_upload_empty_file_rejected(client: TestClient, db_session: Session):
    """Verify rejection of empty (0-byte) file upload."""
    user = create_user(db_session, "empty_uploader")
    inst = create_institution(db_session, "INST-UP-02")
    app_rec = create_application(db_session, inst.id)
    assign_role(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN)

    files = {"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}
    r = client.post(
        f"/api/v1/applications/{app_rec.id}/documents",
        files=files,
        data={"document_type": "land_doc"},
        headers=auth_header(user),
    )
    assert r.status_code == 422
    assert "empty" in r.json()["detail"].lower()


def test_upload_mismatched_mime_and_corrupted_format_rejected(client: TestClient, db_session: Session):
    """Verify rejection when declared MIME does not match magic bytes signature."""
    user = create_user(db_session, "spoof_uploader")
    inst = create_institution(db_session, "INST-UP-03")
    app_rec = create_application(db_session, inst.id)
    assign_role(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN)

    # Plain text spoofed as PDF
    files = {"file": ("fake.pdf", io.BytesIO(b"Plain text masquerading as PDF"), "application/pdf")}
    r = client.post(
        f"/api/v1/applications/{app_rec.id}/documents",
        files=files,
        data={"document_type": "land_doc"},
        headers=auth_header(user),
    )
    assert r.status_code == 422
    assert "signature" in r.json()["detail"].lower() or "unsupported" in r.json()["detail"].lower()


def test_upload_oversized_file_rejected(client: TestClient, db_session: Session):
    """Verify that files exceeding the 10 MiB limit are rejected with 413 or 422."""
    user = create_user(db_session, "big_uploader")
    inst = create_institution(db_session, "INST-UP-04")
    app_rec = create_application(db_session, inst.id)
    assign_role(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN)

    # 10 MiB + 1024 bytes
    oversized_data = b"%PDF-" + b"0" * (10 * 1024 * 1024 + 1024)
    files = {"file": ("oversized.pdf", io.BytesIO(oversized_data), "application/pdf")}
    r = client.post(
        f"/api/v1/applications/{app_rec.id}/documents",
        files=files,
        data={"document_type": "land_doc"},
        headers=auth_header(user),
    )
    assert r.status_code in (413, 422)


# ==============================================================================
# SECTION B: Malware Scanning Boundary & Quarantine
# ==============================================================================


def test_malware_scan_rejected_blocks_upload(client: TestClient, db_session: Session):
    """A positive malware detection marks version rejected, logs audit event, and prohibits download."""
    # Configure mock scanner to REJECT
    set_malware_scanner(MockScanner(ScanStatus.REJECTED))

    user = create_user(db_session, "infected_uploader")
    inst = create_institution(db_session, "INST-MAL-01")
    app_rec = create_application(db_session, inst.id)
    assign_role(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN)

    files = {"file": ("eicar.png", io.BytesIO(VALID_PNG_BYTES), "image/png")}
    r = client.post(
        f"/api/v1/applications/{app_rec.id}/documents",
        files=files,
        data={"document_type": "eoa_approval"},
        headers=auth_header(user),
    )
    assert r.status_code in (201, 202)
    doc_id = r.json()["document"]["id"]
    ver_id = r.json()["version"]["id"]

    # In eager worker execution, document was scanned and rejected
    ver = db_session.get(DocumentVersion, ver_id)
    assert ver.scan_status == "rejected"
    assert ver.processing_status == "rejected"

    # Attempting to download the infected file is prohibited (403)
    r_dl = client.get(
        f"/api/v1/applications/{app_rec.id}/documents/{doc_id}/versions/{ver_id}/download",
        headers=auth_header(user),
    )
    assert r_dl.status_code == 403

    # Check audit event
    events = list(db_session.scalars(select(AuditEvent).where(AuditEvent.action == "DOCUMENT_SCAN_REJECTED")).all())
    assert len(events) == 1
    assert "malware_scan_rejected" in (events[0].details or "")


def test_malware_scan_unavailable_places_file_in_quarantine(client: TestClient, db_session: Session):
    """When scanner is unavailable, file is stored in quarantine and download is blocked."""
    # Configure mock scanner as SCAN_UNAVAILABLE
    set_malware_scanner(MockScanner(ScanStatus.SCAN_UNAVAILABLE))

    user = create_user(db_session, "quarantine_uploader")
    inst = create_institution(db_session, "INST-QUAR-01")
    app_rec = create_application(db_session, inst.id)
    assign_role(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN)

    headers = auth_header(user)

    # 1. Upload accepted into quarantine
    files = {"file": ("doc.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
    r_up = client.post(
        f"/api/v1/applications/{app_rec.id}/documents",
        files=files,
        data={"document_type": "bank_statement"},
        headers=headers,
    )
    assert r_up.status_code == 201
    resp = r_up.json()
    assert resp["version"]["processing_status"] in ("quarantined", "queued")
    doc_id = resp["document"]["id"]
    version_id = resp["version"]["id"]

    ver = db_session.get(DocumentVersion, version_id)
    assert ver.scan_status == "scan_unavailable"

    # 2. Attempting to download quarantined document is forbidden (403)
    r_dl = client.get(
        f"/api/v1/applications/{app_rec.id}/documents/{doc_id}/versions/{version_id}/download",
        headers=headers,
    )
    assert r_dl.status_code == 403
    assert "quarantined" in r_dl.json()["detail"].lower()


# ==============================================================================
# SECTION C: Authorization and Tenant Isolation
# ==============================================================================


def test_anonymous_upload_denied(client: TestClient, db_session: Session):
    """Anonymous user cannot upload documents (401)."""
    inst = create_institution(db_session, "INST-ANON")
    app_rec = create_application(db_session, inst.id)

    files = {"file": ("test.png", io.BytesIO(VALID_PNG_BYTES), "image/png")}
    r = client.post(
        f"/api/v1/applications/{app_rec.id}/documents",
        files=files,
        data={"document_type": "land_doc"},
    )
    assert r.status_code == 401


def test_auditor_cannot_upload_documents(client: TestClient, db_session: Session):
    """An auditor cannot upload document versions (403)."""
    auditor = create_user(db_session, "auditor_upload_user")
    inst = create_institution(db_session, "INST-AUD-UP")
    app_rec = create_application(db_session, inst.id)
    assign_role(db_session, auditor.id, inst.id, ROLE_AUDITOR)

    files = {"file": ("test.png", io.BytesIO(VALID_PNG_BYTES), "image/png")}
    r = client.post(
        f"/api/v1/applications/{app_rec.id}/documents",
        files=files,
        data={"document_type": "land_doc"},
        headers=auth_header(auditor),
    )
    assert r.status_code == 403


def test_cross_tenant_access_denied_with_concealment(client: TestClient, db_session: Session):
    """User from institution A cannot access institution B documents (404 concealed)."""
    user_a = create_user(db_session, "tenant_a_user")
    user_b = create_user(db_session, "tenant_b_user")
    inst_a = create_institution(db_session, "INST-A")
    inst_b = create_institution(db_session, "INST-B")

    assign_role(db_session, user_a.id, inst_a.id, ROLE_INSTITUTION_ADMIN)
    assign_role(db_session, user_b.id, inst_b.id, ROLE_INSTITUTION_ADMIN)

    app_b = create_application(db_session, inst_b.id)

    # 1. User A attempts to upload to Inst B's application -> 404
    files = {"file": ("test.png", io.BytesIO(VALID_PNG_BYTES), "image/png")}
    r_up = client.post(
        f"/api/v1/applications/{app_b.id}/documents",
        files=files,
        data={"document_type": "land_doc"},
        headers=auth_header(user_a),
    )
    assert r_up.status_code == 404

    # 2. User B uploads valid document
    r_b_up = client.post(
        f"/api/v1/applications/{app_b.id}/documents",
        files={"file": ("test.png", io.BytesIO(VALID_PNG_BYTES), "image/png")},
        data={"document_type": "land_doc"},
        headers=auth_header(user_b),
    )
    assert r_b_up.status_code == 201
    doc_b_id = r_b_up.json()["document"]["id"]
    ver_b_id = r_b_up.json()["version"]["id"]

    # 3. User A attempts to read or download User B's document -> 404
    r_read = client.get(f"/api/v1/applications/{app_b.id}/documents/{doc_b_id}", headers=auth_header(user_a))
    assert r_read.status_code == 404

    r_dl = client.get(
        f"/api/v1/applications/{app_b.id}/documents/{doc_b_id}/versions/{ver_b_id}/download",
        headers=auth_header(user_a),
    )
    assert r_dl.status_code == 404


# ==============================================================================
# SECTION D: Immutable Versioning and Download Flow
# ==============================================================================


def test_immutable_versioning_and_download_flow(client: TestClient, db_session: Session):
    """Uploading replacement version increments version number, preserves history, and allows download."""
    user = create_user(db_session, "version_user")
    inst = create_institution(db_session, "INST-VERS-01")
    app_rec = create_application(db_session, inst.id)
    assign_role(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN)

    headers = auth_header(user)

    # 1. Upload Version 1
    files_v1 = {"file": ("v1.png", io.BytesIO(VALID_PNG_BYTES), "image/png")}
    r1 = client.post(
        f"/api/v1/applications/{app_rec.id}/documents",
        files=files_v1,
        data={"document_type": "approval_letter"},
        headers=headers,
    )
    assert r1.status_code == 201
    doc_id = r1.json()["document"]["id"]
    v1_id = r1.json()["version"]["id"]
    assert r1.json()["version"]["version_number"] == 1

    # 2. Upload Version 2 (replacement)
    files_v2 = {"file": ("v2.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
    r2 = client.post(
        f"/api/v1/applications/{app_rec.id}/documents",
        files=files_v2,
        data={"document_type": "approval_letter"},
        headers=headers,
    )
    assert r2.status_code == 201
    assert r2.json()["document"]["id"] == doc_id
    v2_id = r2.json()["version"]["id"]
    assert v2_id != v1_id
    assert r2.json()["version"]["version_number"] == 2

    # 3. Retrieve version history
    r_vers = client.get(
        f"/api/v1/applications/{app_rec.id}/documents/{doc_id}/versions",
        headers=headers,
    )
    assert r_vers.status_code == 200
    versions = r_vers.json()
    assert len(versions) == 2
    assert versions[0]["version_number"] == 1
    assert versions[1]["version_number"] == 2

    # 4. Download clean version
    r_dl = client.get(
        f"/api/v1/applications/{app_rec.id}/documents/{doc_id}/versions/{v1_id}/download",
        headers=headers,
    )
    assert r_dl.status_code == 200
    assert r_dl.content == VALID_PNG_BYTES
    assert "attachment" in r_dl.headers["content-disposition"]
