"""Unit tests for AuditPackageService generation, packaging, and tamper-evidence."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
import io
import zipfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.storage import get_storage_backend
from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
    AuditEvent,
    Document,
    DocumentVersion,
    Finding,
    Institution,
    InstitutionMembership,
    ReviewAction,
    User,
    ValidationCheckResult,
    ValidationRun,
)
from backend.app.schemas.audit_package import AuditPackageCreateRequest
from backend.app.services.audit_package_service import (
    AuditPackageNotFoundError,
    AuditPackageService,
)


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
def service_data(db_session: Session) -> dict[str, object]:
    institution = Institution(institution_id="INST-PKG-01", display_name="Packaging Tech Institute")
    db_session.add(institution)
    db_session.flush()

    user = User(username="officer_pkg", hashed_password="dummy_hash_for_test")
    db_session.add(user)
    db_session.flush()

    mem = InstitutionMembership(
        user_id=user.id,
        institution_id=institution.id,
        role="scrutiny_officer",
        is_active=True,
    )
    db_session.add(mem)

    app = Application(
        institution_id=institution.id,
        application_type="eoa",
        academic_year="2026-2027",
        status="under_review",
    )
    db_session.add(app)
    db_session.flush()

    # Document & Version in storage
    doc = Document(application_id=app.id, document_type="fire_noc")
    db_session.add(doc)
    db_session.flush()

    storage = get_storage_backend()
    doc_content = b"%PDF-1.4 Mock Fire Safety NOC Document Content"
    storage_key = "documents/test_fire_noc_pkg.pdf"
    storage.put(storage_key, doc_content)

    doc_ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=storage_key,
        sha256="mock_sha256_hash",
        media_type="application/pdf",
        byte_size=len(doc_content),
        file_name="fire_safety_noc.pdf",
    )
    db_session.add(doc_ver)
    db_session.flush()
    doc.current_version_id = doc_ver.id

    # Validation Run
    run = ValidationRun(
        application_id=app.id,
        status="completed",
        evaluation_date=date(2026, 4, 1),
        outcome="failed",
        ruleset_version="0.1.0-draft",
    )
    db_session.add(run)
    db_session.flush()

    check = ValidationCheckResult(
        validation_run_id=run.id,
        check_id="CHK_FIRE_01",
        check_name="Fire NOC Validity",
        category="safety",
        status="failed",
        message="Fire certificate validity check failed.",
    )
    db_session.add(check)

    finding = Finding(
        validation_run_id=run.id,
        code="CHK_FIRE_01",
        status="resolved",
        severity="high",
        summary="Expired Fire NOC",
        resolution_rationale="Institution provided valid state fire clearance letter.",
        resolved_by="officer_pkg",
        version=2,
    )
    db_session.add(finding)
    db_session.flush()

    action = ReviewAction(
        application_id=app.id,
        finding_id=finding.id,
        validation_run_id=run.id,
        reviewer_id=user.username,
        action="resolve",
        previous_status="open",
        new_status="resolved",
        rationale="Institution provided valid state fire clearance letter.",
    )
    db_session.add(action)

    audit_ev = AuditEvent(
        actor_id=user.username,
        institution_id=institution.id,
        action="REVIEW_ACTION_RECORDED",
        target_type="Finding",
        target_id=str(finding.id),
    )
    db_session.add(audit_ev)
    db_session.commit()

    return {
        "institution": institution,
        "application": app,
        "run": run,
        "user": user,
    }


def test_create_audit_package_bundle_success(db_session: Session, service_data: dict[str, object]):
    app: Application = service_data["application"]  # type: ignore
    user: User = service_data["user"]  # type: ignore

    payload = AuditPackageCreateRequest(
        package_name="Annual_Scrutiny_Audit_Bundle",
        include_documents=True,
    )

    pkg_detail = AuditPackageService.create_package(
        db_session,
        application_id=app.id,
        user=user,
        payload=payload,
    )

    assert pkg_detail.id is not None
    assert pkg_detail.status == "completed"
    assert pkg_detail.package_name == "Annual_Scrutiny_Audit_Bundle"
    assert len(pkg_detail.sha256_root_hash) == 64
    assert pkg_detail.file_size_bytes > 0
    assert pkg_detail.storage_key is not None

    # Verify manifest structure
    manifest = pkg_detail.manifest
    assert manifest.application_id == app.id
    assert manifest.institution_id == "INST-PKG-01"
    assert manifest.sha256_root_hash == pkg_detail.sha256_root_hash
    assert len(manifest.items) >= 4  # report, findings, reviews, audit_trail, document

    paths = [item.path for item in manifest.items]
    assert "scrutiny_report.json" in paths
    assert "findings_resolution.json" in paths
    assert "review_history.json" in paths
    assert "audit_trail.json" in paths
    assert "documents/fire_noc/fire_safety_noc.pdf" in paths

    # Verify storage contents
    storage = get_storage_backend()
    assert storage.exists(pkg_detail.storage_key)
    zip_bytes = storage.read(pkg_detail.storage_key)
    assert len(zip_bytes) == pkg_detail.file_size_bytes

    # Unzip in memory and inspect files
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        namelist = zf.namelist()
        assert "manifest.json" in namelist
        assert "CHECKSUMS.txt" in namelist
        assert "scrutiny_report.json" in namelist
        assert "documents/fire_noc/fire_safety_noc.pdf" in namelist


def test_get_and_list_audit_packages(db_session: Session, service_data: dict[str, object]):
    app: Application = service_data["application"]  # type: ignore
    user: User = service_data["user"]  # type: ignore

    # Create two packages
    pkg1 = AuditPackageService.create_package(
        db_session,
        application_id=app.id,
        user=user,
        payload=AuditPackageCreateRequest(package_name="Bundle_1"),
    )
    pkg2 = AuditPackageService.create_package(
        db_session,
        application_id=app.id,
        user=user,
        payload=AuditPackageCreateRequest(package_name="Bundle_2"),
    )

    # List packages
    list_resp = AuditPackageService.list_packages(db_session, application_id=app.id)
    assert list_resp.total == 2
    assert len(list_resp.items) == 2
    assert list_resp.items[0].id == pkg2.id  # newest first

    # Get single package
    retrieved = AuditPackageService.get_package(db_session, application_id=app.id, package_id=pkg1.id)
    assert retrieved.id == pkg1.id
    assert retrieved.package_name == "Bundle_1"
    assert retrieved.manifest.sha256_root_hash == pkg1.sha256_root_hash

    # Non-existent package raises 404
    with pytest.raises(AuditPackageNotFoundError):
        AuditPackageService.get_package(db_session, application_id=app.id, package_id=99999)


def test_get_package_download_bytes(db_session: Session, service_data: dict[str, object]):
    app: Application = service_data["application"]  # type: ignore
    user: User = service_data["user"]  # type: ignore

    pkg = AuditPackageService.create_package(
        db_session,
        application_id=app.id,
        user=user,
        payload=AuditPackageCreateRequest(package_name="Download_Test_Bundle"),
    )

    zip_bytes, filename = AuditPackageService.get_package_download_bytes(
        db_session, application_id=app.id, package_id=pkg.id
    )
    assert len(zip_bytes) == pkg.file_size_bytes
    assert filename == "Download_Test_Bundle.zip"
    assert zip_bytes.startswith(b"PK")  # ZIP magic bytes
