"""Cryptographic integrity and tamper-evidence tests for Audit Packages."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
import io
import zipfile

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.rbac import ROLE_SCRUTINY_OFFICER
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
    Finding,
    Institution,
    InstitutionMembership,
    User,
    ValidationRun,
)
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.schemas.audit_package import AuditPackageCreateRequest
from backend.app.services.audit_package_service import AuditPackageService

TEST_JWT_SECRET = "test-secret-key-minimum-32-characters-for-hs256-compliance!!"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
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


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def package_zip(db_session: Session) -> tuple[bytes, User, str]:
    institution = Institution(institution_id="INST-INTEGRITY", display_name="Integrity Verification College")
    db_session.add(institution)
    db_session.flush()

    user = User(username="auditor_verifier", hashed_password=get_password_hash("ValidPass123!"))
    db_session.add(user)
    db_session.flush()

    mem = InstitutionMembership(
        user_id=user.id, institution_id=institution.id, role=ROLE_SCRUTINY_OFFICER, is_active=True
    )
    db_session.add(mem)

    app_row = Application(
        institution_id=institution.id, application_type="eoa", academic_year="2026-2027", status="under_review"
    )
    db_session.add(app_row)
    db_session.flush()

    run = ValidationRun(
        application_id=app_row.id, status="completed", evaluation_date=date(2026, 4, 1), outcome="failed"
    )
    db_session.add(run)
    db_session.flush()

    finding = Finding(
        validation_run_id=run.id,
        code="CHK_SAFETY_01",
        status="open",
        severity="high",
        summary="Building safety certificate issue",
        version=1,
    )
    db_session.add(finding)
    db_session.commit()

    pkg = AuditPackageService.create_package(
        db_session,
        application_id=app_row.id,
        user=user,
        payload=AuditPackageCreateRequest(package_name="Authentic_Package", include_documents=False),
    )

    zip_bytes, _ = AuditPackageService.get_package_download_bytes(
        db_session, application_id=app_row.id, package_id=pkg.id
    )

    token = create_access_token(subject=user.id, extra_claims={"username": user.username})
    return zip_bytes, user, token


def test_authentic_audit_package_passes_verification(package_zip: tuple[bytes, User, str]):
    zip_bytes, _, _ = package_zip

    verification = AuditPackageService.verify_package_archive(zip_bytes)
    assert verification.verified is True
    assert len(verification.tampered_files) == 0
    assert len(verification.missing_files) == 0
    assert len(verification.extra_files) == 0
    assert verification.computed_root_hash == verification.expected_root_hash
    assert "passed cryptographic verification" in verification.message.lower()


def test_tampered_file_content_detected(package_zip: tuple[bytes, User, str]):
    original_zip_bytes, _, _ = package_zip

    # Read original files from ZIP
    tampered_buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original_zip_bytes), mode="r") as zf_in:
        with zipfile.ZipFile(tampered_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf_out:
            for item in zf_in.infolist():
                content = zf_in.read(item.filename)
                if item.filename == "scrutiny_report.json":
                    # Maliciously modify scrutiny report content
                    content = content.replace(b"failed", b"passed")
                zf_out.writestr(item.filename, content)

    tampered_zip_bytes = tampered_buffer.getvalue()

    verification = AuditPackageService.verify_package_archive(tampered_zip_bytes)
    assert verification.verified is False
    assert "scrutiny_report.json" in verification.tampered_files
    assert "failed" in verification.message.lower()


def test_missing_declared_file_detected(package_zip: tuple[bytes, User, str]):
    original_zip_bytes, _, _ = package_zip

    tampered_buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original_zip_bytes), mode="r") as zf_in:
        with zipfile.ZipFile(tampered_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf_out:
            for item in zf_in.infolist():
                # Omit findings_resolution.json
                if item.filename != "findings_resolution.json":
                    zf_out.writestr(item.filename, zf_in.read(item.filename))

    tampered_zip_bytes = tampered_buffer.getvalue()

    verification = AuditPackageService.verify_package_archive(tampered_zip_bytes)
    assert verification.verified is False
    assert "findings_resolution.json" in verification.missing_files


def test_injected_extra_file_detected(package_zip: tuple[bytes, User, str]):
    original_zip_bytes, _, _ = package_zip

    tampered_buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original_zip_bytes), mode="r") as zf_in:
        with zipfile.ZipFile(tampered_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf_out:
            for item in zf_in.infolist():
                zf_out.writestr(item.filename, zf_in.read(item.filename))
            # Inject unmanifested file
            zf_out.writestr("unauthorized_override.txt", b"Bypassing check results unauthorized")

    tampered_zip_bytes = tampered_buffer.getvalue()

    verification = AuditPackageService.verify_package_archive(tampered_zip_bytes)
    assert verification.verified is False
    assert "unauthorized_override.txt" in verification.extra_files


def test_verify_audit_package_api_endpoint(client: TestClient, package_zip: tuple[bytes, User, str]):
    zip_bytes, _, token = package_zip

    # 1. Verify authentic archive via API
    res_valid = client.post(
        "/api/v1/audit-packages/verify",
        files={"file": ("package.zip", zip_bytes, "application/zip")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_valid.status_code == 200
    valid_data = res_valid.json()
    assert valid_data["verified"] is True
    assert len(valid_data["tampered_files"]) == 0

    # 2. Verify tampered archive via API
    tampered_buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r") as zf_in:
        with zipfile.ZipFile(tampered_buf, mode="w") as zf_out:
            for item in zf_in.infolist():
                c = zf_in.read(item.filename)
                if item.filename == "findings_resolution.json":
                    c = b'{"tampered": true}'
                zf_out.writestr(item.filename, c)

    res_tampered = client.post(
        "/api/v1/audit-packages/verify",
        files={"file": ("tampered.zip", tampered_buf.getvalue(), "application/zip")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_tampered.status_code == 200
    tampered_data = res_tampered.json()
    assert tampered_data["verified"] is False
    assert "findings_resolution.json" in tampered_data["tampered_files"]
