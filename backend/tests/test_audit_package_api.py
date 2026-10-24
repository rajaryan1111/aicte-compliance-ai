"""Integration tests for Audit Package endpoints (creation, retrieval, and download)."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.rbac import ROLE_INSTITUTION_ADMIN, ROLE_SCRUTINY_OFFICER
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
    Finding,
    Institution,
    InstitutionMembership,
    User,
    ValidationCheckResult,
    ValidationRun,
)
from backend.app.db.session import get_db
from backend.app.main import app

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
def api_data(db_session: Session) -> dict[str, object]:
    hashed_pwd = get_password_hash("ValidPass123!")

    institution = Institution(institution_id="INST-API-PKG", display_name="API Packaging Institute")
    db_session.add(institution)
    db_session.flush()

    user_officer = User(username="officer_api_pkg", hashed_password=hashed_pwd)
    user_admin = User(username="admin_api_pkg", hashed_password=hashed_pwd)
    db_session.add_all([user_officer, user_admin])
    db_session.flush()

    mem_officer = InstitutionMembership(
        user_id=user_officer.id, institution_id=institution.id, role=ROLE_SCRUTINY_OFFICER, is_active=True
    )
    mem_admin = InstitutionMembership(
        user_id=user_admin.id, institution_id=institution.id, role=ROLE_INSTITUTION_ADMIN, is_active=True
    )
    db_session.add_all([mem_officer, mem_admin])

    application = Application(
        institution_id=institution.id,
        application_type="eoa",
        academic_year="2026-2027",
        status="under_review",
    )
    db_session.add(application)
    db_session.flush()

    run = ValidationRun(
        application_id=application.id,
        status="completed",
        evaluation_date=date(2026, 4, 1),
        outcome="failed",
    )
    db_session.add(run)
    db_session.flush()

    check = ValidationCheckResult(
        validation_run_id=run.id,
        check_id="CHK_LAND_01",
        check_name="Contiguous Land Area",
        category="land",
        status="passed",
        message="Contiguous land area satisfies AICTE norms.",
    )
    db_session.add(check)

    finding = Finding(
        validation_run_id=run.id,
        code="CHK_SAFETY_01",
        status="open",
        severity="medium",
        summary="Building safety certificate advisory note.",
        version=1,
    )
    db_session.add(finding)
    db_session.commit()

    token_officer = create_access_token(subject=user_officer.id, extra_claims={"username": user_officer.username})
    token_admin = create_access_token(subject=user_admin.id, extra_claims={"username": user_admin.username})

    return {
        "institution": institution,
        "application": application,
        "run": run,
        "token_officer": token_officer,
        "token_admin": token_admin,
    }


def test_create_audit_package_api_endpoint(client: TestClient, api_data: dict[str, object]):
    app: Application = api_data["application"]  # type: ignore
    token: str = api_data["token_officer"]  # type: ignore

    res = client.post(
        f"/api/v1/applications/{app.id}/audit-packages",
        json={
            "package_name": "API_Scrutiny_Export",
            "include_documents": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["application_id"] == app.id
    assert data["status"] == "completed"
    assert data["package_name"] == "API_Scrutiny_Export"
    assert len(data["sha256_root_hash"]) == 64
    assert "advisory" in data["advisory_notice"].lower()
    assert "manifest" in data
    assert data["manifest"]["sha256_root_hash"] == data["sha256_root_hash"]


def test_list_and_get_audit_packages_api_endpoints(client: TestClient, api_data: dict[str, object]):
    app: Application = api_data["application"]  # type: ignore
    token: str = api_data["token_officer"]  # type: ignore

    # Create package first
    create_res = client.post(
        f"/api/v1/applications/{app.id}/audit-packages",
        json={"package_name": "List_Test_Package"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_res.status_code == 201
    pkg_id = create_res.json()["id"]

    # List packages
    list_res = client.get(
        f"/api/v1/applications/{app.id}/audit-packages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(p["id"] == pkg_id for p in list_data["items"])

    # Get single package
    get_res = client.get(
        f"/api/v1/applications/{app.id}/audit-packages/{pkg_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["id"] == pkg_id
    assert get_data["package_name"] == "List_Test_Package"
    assert "manifest" in get_data


def test_download_audit_package_archive(client: TestClient, api_data: dict[str, object]):
    app: Application = api_data["application"]  # type: ignore
    token: str = api_data["token_officer"]  # type: ignore

    # Create package
    create_res = client.post(
        f"/api/v1/applications/{app.id}/audit-packages",
        json={"package_name": "Downloadable_Bundle"},
        headers={"Authorization": f"Bearer {token}"},
    )
    pkg_id = create_res.json()["id"]

    # Download package
    dl_res = client.get(
        f"/api/v1/applications/{app.id}/audit-packages/{pkg_id}/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"] == "application/zip"
    assert "attachment" in dl_res.headers.get("content-disposition", "")
    assert dl_res.content.startswith(b"PK")  # ZIP signature
