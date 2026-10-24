"""RBAC, tenant isolation, and auditor access control tests for Review APIs."""

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
    Finding,
    Institution,
    InstitutionMembership,
    ReviewAction,
    User,
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
def rbac_data(db_session: Session) -> dict[str, object]:
    hashed_pwd = get_password_hash("ValidPass123!")

    # Tenant 1: Inst A
    inst_a = Institution(institution_id="INST-TENANT-A", display_name="Tenant A College")
    # Tenant 2: Inst B
    inst_b = Institution(institution_id="INST-TENANT-B", display_name="Tenant B University")
    db_session.add_all([inst_a, inst_b])
    db_session.flush()

    # Users
    user_officer_a = User(username="officer_a", hashed_password=hashed_pwd)
    user_admin_a = User(username="admin_a", hashed_password=hashed_pwd)
    user_auditor_a = User(username="auditor_a", hashed_password=hashed_pwd)
    user_tenant_b = User(username="admin_b", hashed_password=hashed_pwd)
    user_no_role = User(username="no_role_user", hashed_password=hashed_pwd)

    db_session.add_all([user_officer_a, user_admin_a, user_auditor_a, user_tenant_b, user_no_role])
    db_session.flush()

    # Memberships
    mem_officer_a = InstitutionMembership(
        user_id=user_officer_a.id, institution_id=inst_a.id, role=ROLE_SCRUTINY_OFFICER, is_active=True
    )
    mem_admin_a = InstitutionMembership(
        user_id=user_admin_a.id, institution_id=inst_a.id, role=ROLE_INSTITUTION_ADMIN, is_active=True
    )
    mem_auditor_a = InstitutionMembership(
        user_id=user_auditor_a.id, institution_id=inst_a.id, role=ROLE_AUDITOR, is_active=True
    )
    mem_tenant_b = InstitutionMembership(
        user_id=user_tenant_b.id, institution_id=inst_b.id, role=ROLE_INSTITUTION_ADMIN, is_active=True
    )
    db_session.add_all([mem_officer_a, mem_admin_a, mem_auditor_a, mem_tenant_b])

    # Applications
    app_a = Application(
        institution_id=inst_a.id, application_type="eoa", academic_year="2026-2027", status="under_review"
    )
    app_b = Application(
        institution_id=inst_b.id, application_type="eoa", academic_year="2026-2027", status="under_review"
    )
    db_session.add_all([app_a, app_b])
    db_session.flush()

    # Runs
    run_a = ValidationRun(application_id=app_a.id, status="completed", evaluation_date=date(2026, 4, 1), outcome="failed")
    run_b = ValidationRun(application_id=app_b.id, status="completed", evaluation_date=date(2026, 4, 1), outcome="failed")
    db_session.add_all([run_a, run_b])
    db_session.flush()

    # Findings
    finding_a = Finding(
        validation_run_id=run_a.id,
        code="CHK_LAND_AREA",
        status="open",
        severity="high",
        summary="Insufficient contiguous land area",
        version=1,
    )
    finding_b = Finding(
        validation_run_id=run_b.id,
        code="CHK_FIRE_NOC",
        status="open",
        severity="high",
        summary="Expired Fire NOC in Tenant B",
        version=1,
    )
    db_session.add_all([finding_a, finding_b])
    db_session.commit()

    token_officer_a = create_access_token(subject=user_officer_a.id, extra_claims={"username": user_officer_a.username})
    token_admin_a = create_access_token(subject=user_admin_a.id, extra_claims={"username": user_admin_a.username})
    token_auditor_a = create_access_token(subject=user_auditor_a.id, extra_claims={"username": user_auditor_a.username})
    token_tenant_b = create_access_token(subject=user_tenant_b.id, extra_claims={"username": user_tenant_b.username})
    token_no_role = create_access_token(subject=user_no_role.id, extra_claims={"username": user_no_role.username})

    return {
        "inst_a": inst_a,
        "inst_b": inst_b,
        "app_a": app_a,
        "app_b": app_b,
        "run_a": run_a,
        "run_b": run_b,
        "finding_a": finding_a,
        "finding_b": finding_b,
        "token_officer_a": token_officer_a,
        "token_admin_a": token_admin_a,
        "token_auditor_a": token_auditor_a,
        "token_tenant_b": token_tenant_b,
        "token_no_role": token_no_role,
    }


def test_anonymous_requests_rejected(client: TestClient, rbac_data: dict[str, object]):
    app_a: Application = rbac_data["app_a"]  # type: ignore
    run_a: ValidationRun = rbac_data["run_a"]  # type: ignore
    finding_a: Finding = rbac_data["finding_a"]  # type: ignore

    res1 = client.get(f"/api/v1/applications/{app_a.id}/review-summary")
    assert res1.status_code == 401

    res2 = client.get(f"/api/v1/applications/{app_a.id}/findings")
    assert res2.status_code == 401

    res3 = client.get(f"/api/v1/applications/{app_a.id}/validation-runs/{run_a.id}/findings/{finding_a.id}")
    assert res3.status_code == 401

    res4 = client.post(
        f"/api/v1/applications/{app_a.id}/validation-runs/{run_a.id}/findings/{finding_a.id}/actions",
        json={"action": "acknowledge"},
    )
    assert res4.status_code == 401

    res5 = client.get("/api/v1/reviews/queue")
    assert res5.status_code == 401


def test_cross_tenant_information_concealment_404(client: TestClient, rbac_data: dict[str, object]):
    """Tenant B user accessing Tenant A resources must receive 404 (not 403) to prevent enumeration."""
    app_a: Application = rbac_data["app_a"]  # type: ignore
    run_a: ValidationRun = rbac_data["run_a"]  # type: ignore
    finding_a: Finding = rbac_data["finding_a"]  # type: ignore
    token_tenant_b: str = rbac_data["token_tenant_b"]  # type: ignore

    # Review summary across tenant
    res_summary = client.get(
        f"/api/v1/applications/{app_a.id}/review-summary",
        headers={"Authorization": f"Bearer {token_tenant_b}"},
    )
    assert res_summary.status_code == 404

    # Findings across tenant
    res_findings = client.get(
        f"/api/v1/applications/{app_a.id}/findings",
        headers={"Authorization": f"Bearer {token_tenant_b}"},
    )
    assert res_findings.status_code == 404

    # Finding detail across tenant
    res_detail = client.get(
        f"/api/v1/applications/{app_a.id}/validation-runs/{run_a.id}/findings/{finding_a.id}",
        headers={"Authorization": f"Bearer {token_tenant_b}"},
    )
    assert res_detail.status_code == 404

    # Record action across tenant
    res_action = client.post(
        f"/api/v1/applications/{app_a.id}/validation-runs/{run_a.id}/findings/{finding_a.id}/actions",
        json={"action": "acknowledge"},
        headers={"Authorization": f"Bearer {token_tenant_b}"},
    )
    assert res_action.status_code == 404


def test_auditor_is_strictly_read_only(client: TestClient, rbac_data: dict[str, object], db_session: Session):
    app_a: Application = rbac_data["app_a"]  # type: ignore
    run_a: ValidationRun = rbac_data["run_a"]  # type: ignore
    finding_a: Finding = rbac_data["finding_a"]  # type: ignore
    token_auditor: str = rbac_data["token_auditor_a"]  # type: ignore

    # Auditor CAN read review summary
    res_summary = client.get(
        f"/api/v1/applications/{app_a.id}/review-summary",
        headers={"Authorization": f"Bearer {token_auditor}"},
    )
    assert res_summary.status_code == 200

    # Auditor CAN read finding detail
    res_detail = client.get(
        f"/api/v1/applications/{app_a.id}/validation-runs/{run_a.id}/findings/{finding_a.id}",
        headers={"Authorization": f"Bearer {token_auditor}"},
    )
    assert res_detail.status_code == 200

    # Auditor CANNOT acknowledge (403 Forbidden)
    res_ack = client.post(
        f"/api/v1/applications/{app_a.id}/validation-runs/{run_a.id}/findings/{finding_a.id}/actions",
        json={"action": "acknowledge"},
        headers={"Authorization": f"Bearer {token_auditor}"},
    )
    assert res_ack.status_code == 403

    # Auditor CANNOT resolve (403 Forbidden)
    res_resolve = client.post(
        f"/api/v1/applications/{app_a.id}/validation-runs/{run_a.id}/findings/{finding_a.id}/actions",
        json={"action": "resolve", "rationale": "Auditor attempting resolution"},
        headers={"Authorization": f"Bearer {token_auditor}"},
    )
    assert res_resolve.status_code == 403

    # State must be unmodified
    db_session.refresh(finding_a)
    assert finding_a.status == "open"
    assert finding_a.version == 1
    actions = db_session.query(ReviewAction).filter_by(finding_id=finding_a.id).all()
    assert len(actions) == 0


def test_institution_admin_permissions_boundary(
    client: TestClient, rbac_data: dict[str, object], db_session: Session
):
    app_a: Application = rbac_data["app_a"]  # type: ignore
    run_a: ValidationRun = rbac_data["run_a"]  # type: ignore
    finding_a: Finding = rbac_data["finding_a"]  # type: ignore
    token_admin: str = rbac_data["token_admin_a"]  # type: ignore

    # Admin CAN read summary and findings
    res_summary = client.get(
        f"/api/v1/applications/{app_a.id}/review-summary",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res_summary.status_code == 200

    # Admin CAN submit a comment
    res_comment = client.post(
        f"/api/v1/applications/{app_a.id}/validation-runs/{run_a.id}/findings/{finding_a.id}/actions",
        json={"action": "comment", "comment": "Admin clarifying that new land survey is underway."},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res_comment.status_code == 201

    # Admin CANNOT resolve finding (403 Forbidden - reserved for scrutiny officers)
    res_resolve = client.post(
        f"/api/v1/applications/{app_a.id}/validation-runs/{run_a.id}/findings/{finding_a.id}/actions",
        json={"action": "resolve", "rationale": "Admin attempting to resolve land deficit"},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res_resolve.status_code == 403
    assert "reserved for scrutiny officers" in res_resolve.json()["detail"].lower()

    # Admin CANNOT waive finding (403 Forbidden)
    res_waive = client.post(
        f"/api/v1/applications/{app_a.id}/validation-runs/{run_a.id}/findings/{finding_a.id}/actions",
        json={"action": "waive", "rationale": "Admin attempting waiver"},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res_waive.status_code == 403


def test_foreign_finding_or_run_substitution_returns_404(
    client: TestClient, rbac_data: dict[str, object]
):
    app_a: Application = rbac_data["app_a"]  # type: ignore
    run_a: ValidationRun = rbac_data["run_a"]  # type: ignore
    finding_b: Finding = rbac_data["finding_b"]  # finding belonging to Run B / Tenant B
    token_officer: str = rbac_data["token_officer_a"]  # type: ignore

    # Attempting to access finding_b via app_a / run_a
    res = client.get(
        f"/api/v1/applications/{app_a.id}/validation-runs/{run_a.id}/findings/{finding_b.id}",
        headers={"Authorization": f"Bearer {token_officer}"},
    )
    assert res.status_code == 404

    # Attempting to post action to finding_b via app_a / run_a
    res_post = client.post(
        f"/api/v1/applications/{app_a.id}/validation-runs/{run_a.id}/findings/{finding_b.id}/actions",
        json={"action": "acknowledge"},
        headers={"Authorization": f"Bearer {token_officer}"},
    )
    assert res_post.status_code == 404
