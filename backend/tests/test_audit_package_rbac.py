"""RBAC, tenant isolation, and auditor access control tests for Audit Package APIs."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.rbac import (
    ROLE_AUDITOR,
    ROLE_INSTITUTION_ADMIN,
    ROLE_SCRUTINY_OFFICER,
)
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
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
def rbac_data(db_session: Session) -> dict[str, object]:
    hashed_pwd = get_password_hash("ValidPass123!")

    # Tenant A
    inst_a = Institution(institution_id="INST-TENANT-A", display_name="Tenant A College")
    # Tenant B
    inst_b = Institution(institution_id="INST-TENANT-B", display_name="Tenant B College")
    db_session.add_all([inst_a, inst_b])
    db_session.flush()

    user_admin_a = User(username="admin_a", hashed_password=hashed_pwd)
    user_officer_a = User(username="officer_a", hashed_password=hashed_pwd)
    user_auditor_a = User(username="auditor_a", hashed_password=hashed_pwd)
    user_tenant_b = User(username="admin_b", hashed_password=hashed_pwd)
    db_session.add_all([user_admin_a, user_officer_a, user_auditor_a, user_tenant_b])
    db_session.flush()

    mem_admin_a = InstitutionMembership(
        user_id=user_admin_a.id, institution_id=inst_a.id, role=ROLE_INSTITUTION_ADMIN, is_active=True
    )
    mem_officer_a = InstitutionMembership(
        user_id=user_officer_a.id, institution_id=inst_a.id, role=ROLE_SCRUTINY_OFFICER, is_active=True
    )
    mem_auditor_a = InstitutionMembership(
        user_id=user_auditor_a.id, institution_id=inst_a.id, role=ROLE_AUDITOR, is_active=True
    )
    mem_tenant_b = InstitutionMembership(
        user_id=user_tenant_b.id, institution_id=inst_b.id, role=ROLE_INSTITUTION_ADMIN, is_active=True
    )
    db_session.add_all([mem_admin_a, mem_officer_a, mem_auditor_a, mem_tenant_b])

    app_a = Application(
        institution_id=inst_a.id, application_type="eoa", academic_year="2026-2027", status="under_review"
    )
    app_b = Application(
        institution_id=inst_b.id, application_type="eoa", academic_year="2026-2027", status="under_review"
    )
    db_session.add_all([app_a, app_b])
    db_session.flush()

    run_a = ValidationRun(
        application_id=app_a.id, status="completed", evaluation_date=date(2026, 4, 1), outcome="passed"
    )
    db_session.add(run_a)
    db_session.commit()

    pkg_a = AuditPackageService.create_package(
        db_session,
        application_id=app_a.id,
        user=user_officer_a,
        payload=AuditPackageCreateRequest(package_name="Tenant_A_Package"),
    )

    token_admin_a = create_access_token(subject=user_admin_a.id, extra_claims={"username": user_admin_a.username})
    token_officer_a = create_access_token(subject=user_officer_a.id, extra_claims={"username": user_officer_a.username})
    token_auditor_a = create_access_token(subject=user_auditor_a.id, extra_claims={"username": user_auditor_a.username})
    token_tenant_b = create_access_token(subject=user_tenant_b.id, extra_claims={"username": user_tenant_b.username})

    return {
        "app_a": app_a,
        "app_b": app_b,
        "pkg_a": pkg_a,
        "token_admin_a": token_admin_a,
        "token_officer_a": token_officer_a,
        "token_auditor_a": token_auditor_a,
        "token_tenant_b": token_tenant_b,
    }


def test_anonymous_requests_rejected(client: TestClient, rbac_data: dict[str, object]):
    app_a: Application = rbac_data["app_a"]  # type: ignore
    pkg_a = rbac_data["pkg_a"]  # type: ignore

    res1 = client.get(f"/api/v1/applications/{app_a.id}/audit-packages")
    assert res1.status_code == 401

    res2 = client.post(
        f"/api/v1/applications/{app_a.id}/audit-packages",
        json={"package_name": "Anon_Bundle"},
    )
    assert res2.status_code == 401

    res3 = client.get(f"/api/v1/applications/{app_a.id}/audit-packages/{pkg_a.id}/download")
    assert res3.status_code == 401


def test_cross_tenant_access_concealed_with_404(client: TestClient, rbac_data: dict[str, object]):
    app_a: Application = rbac_data["app_a"]  # type: ignore
    pkg_a = rbac_data["pkg_a"]  # type: ignore
    token_tenant_b: str = rbac_data["token_tenant_b"]  # type: ignore

    # List packages across tenant returns 404
    res_list = client.get(
        f"/api/v1/applications/{app_a.id}/audit-packages",
        headers={"Authorization": f"Bearer {token_tenant_b}"},
    )
    assert res_list.status_code == 404

    # Create package across tenant returns 404
    res_create = client.post(
        f"/api/v1/applications/{app_a.id}/audit-packages",
        json={"package_name": "Illegal_Cross_Tenant_Package"},
        headers={"Authorization": f"Bearer {token_tenant_b}"},
    )
    assert res_create.status_code == 404

    # Download package across tenant returns 404
    res_dl = client.get(
        f"/api/v1/applications/{app_a.id}/audit-packages/{pkg_a.id}/download",
        headers={"Authorization": f"Bearer {token_tenant_b}"},
    )
    assert res_dl.status_code == 404


def test_auditor_read_only_access(client: TestClient, rbac_data: dict[str, object]):
    app_a: Application = rbac_data["app_a"]  # type: ignore
    pkg_a = rbac_data["pkg_a"]  # type: ignore
    token_auditor: str = rbac_data["token_auditor_a"]  # type: ignore

    # Auditor CAN list packages
    res_list = client.get(
        f"/api/v1/applications/{app_a.id}/audit-packages",
        headers={"Authorization": f"Bearer {token_auditor}"},
    )
    assert res_list.status_code == 200

    # Auditor CAN get package details and manifest
    res_detail = client.get(
        f"/api/v1/applications/{app_a.id}/audit-packages/{pkg_a.id}",
        headers={"Authorization": f"Bearer {token_auditor}"},
    )
    assert res_detail.status_code == 200

    # Auditor CAN download package ZIP archive
    res_dl = client.get(
        f"/api/v1/applications/{app_a.id}/audit-packages/{pkg_a.id}/download",
        headers={"Authorization": f"Bearer {token_auditor}"},
    )
    assert res_dl.status_code == 200
    assert res_dl.content.startswith(b"PK")

    # Auditor CANNOT create new package (403 Forbidden - audit_package:create denied)
    res_create = client.post(
        f"/api/v1/applications/{app_a.id}/audit-packages",
        json={"package_name": "Auditor_Created_Package"},
        headers={"Authorization": f"Bearer {token_auditor}"},
    )
    assert res_create.status_code == 403


def test_scrutiny_officer_and_admin_can_create_and_read(client: TestClient, rbac_data: dict[str, object]):
    app_a: Application = rbac_data["app_a"]  # type: ignore
    token_officer: str = rbac_data["token_officer_a"]  # type: ignore
    token_admin: str = rbac_data["token_admin_a"]  # type: ignore

    # Scrutiny officer creates package
    res_officer = client.post(
        f"/api/v1/applications/{app_a.id}/audit-packages",
        json={"package_name": "Officer_Export"},
        headers={"Authorization": f"Bearer {token_officer}"},
    )
    assert res_officer.status_code == 201

    # Institution admin creates package
    res_admin = client.post(
        f"/api/v1/applications/{app_a.id}/audit-packages",
        json={"package_name": "Admin_Export"},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res_admin.status_code == 201
