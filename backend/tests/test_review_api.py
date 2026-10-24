"""Integration tests for Human Review API endpoints, filtering, and queue retrieval."""

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
    hashed_pwd = get_password_hash("TestPass123!")

    institution = Institution(institution_id="INST-ENG-01", display_name="National Institute of Tech")
    db_session.add(institution)
    db_session.flush()

    user_officer = User(username="officer_api", hashed_password=hashed_pwd)
    user_admin = User(username="admin_api", hashed_password=hashed_pwd)
    user_auditor = User(username="auditor_api", hashed_password=hashed_pwd)
    db_session.add_all([user_officer, user_admin, user_auditor])
    db_session.flush()

    mem_officer = InstitutionMembership(
        user_id=user_officer.id,
        institution_id=institution.id,
        role=ROLE_SCRUTINY_OFFICER,
        is_active=True,
    )
    mem_admin = InstitutionMembership(
        user_id=user_admin.id,
        institution_id=institution.id,
        role=ROLE_INSTITUTION_ADMIN,
        is_active=True,
    )
    mem_auditor = InstitutionMembership(
        user_id=user_auditor.id,
        institution_id=institution.id,
        role=ROLE_AUDITOR,
        is_active=True,
    )
    db_session.add_all([mem_officer, mem_admin, mem_auditor])

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
        evaluation_date=date(2026, 3, 15),
        outcome="failed",
    )
    db_session.add(run)
    db_session.flush()

    check_res = ValidationCheckResult(
        validation_run_id=run.id,
        check_id="CHK_FIRE_01",
        check_name="Fire NOC Check",
        category="safety",
        status="failed",
        message="Fire Safety Certificate is expired.",
    )
    db_session.add(check_res)

    finding1 = Finding(
        validation_run_id=run.id,
        code="CHK_FIRE_01",
        status="open",
        severity="high",
        summary="Expired Fire Safety NOC",
        evidence='{"source": "ocr_extraction", "expiry": "2025-10-10"}',
        version=1,
    )
    finding2 = Finding(
        validation_run_id=run.id,
        code="CHK_BUILDING_02",
        status="open",
        severity="medium",
        summary="Building Completion Certificate pending renewal",
        evidence='{"source": "ocr_extraction"}',
        version=1,
    )
    db_session.add_all([finding1, finding2])
    db_session.commit()

    token_officer = create_access_token(subject=user_officer.id, extra_claims={"username": user_officer.username})
    token_admin = create_access_token(subject=user_admin.id, extra_claims={"username": user_admin.username})
    token_auditor = create_access_token(subject=user_auditor.id, extra_claims={"username": user_auditor.username})

    return {
        "institution": institution,
        "application": application,
        "run": run,
        "finding1": finding1,
        "finding2": finding2,
        "token_officer": token_officer,
        "token_admin": token_admin,
        "token_auditor": token_auditor,
    }


def test_get_application_review_summary(client: TestClient, api_data: dict[str, object]):
    app: Application = api_data["application"]  # type: ignore
    token: str = api_data["token_officer"]  # type: ignore

    res = client.get(
        f"/api/v1/applications/{app.id}/review-summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["application_id"] == app.id
    assert data["total_findings"] == 2
    assert data["open_count"] == 2
    assert data["resolved_count"] == 0
    assert data["pending_action_count"] == 2
    assert "advisory" in data["notice"].lower()


def test_list_application_findings_with_filters_and_pagination(
    client: TestClient, api_data: dict[str, object]
):
    app: Application = api_data["application"]  # type: ignore
    token: str = api_data["token_officer"]  # type: ignore

    # List all
    res = client.get(
        f"/api/v1/applications/{app.id}/findings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Filter by severity
    res_high = client.get(
        f"/api/v1/applications/{app.id}/findings?severity=high",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_high.status_code == 200
    data_high = res_high.json()
    assert data_high["total"] == 1
    assert data_high["items"][0]["code"] == "CHK_FIRE_01"

    # Filter by code
    res_code = client.get(
        f"/api/v1/applications/{app.id}/findings?code=CHK_BUILDING_02",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_code.status_code == 200
    data_code = res_code.json()
    assert data_code["total"] == 1
    assert data_code["items"][0]["code"] == "CHK_BUILDING_02"


def test_get_finding_detail_and_history(client: TestClient, api_data: dict[str, object]):
    app: Application = api_data["application"]  # type: ignore
    run: ValidationRun = api_data["run"]  # type: ignore
    finding: Finding = api_data["finding1"]  # type: ignore
    token: str = api_data["token_officer"]  # type: ignore

    res = client.get(
        f"/api/v1/applications/{app.id}/validation-runs/{run.id}/findings/{finding.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == finding.id
    assert data["code"] == "CHK_FIRE_01"
    assert data["status"] == "open"
    assert data["review_actions"] == []


def test_record_review_actions_lifecycle(client: TestClient, api_data: dict[str, object]):
    app: Application = api_data["application"]  # type: ignore
    run: ValidationRun = api_data["run"]  # type: ignore
    finding: Finding = api_data["finding1"]  # type: ignore
    token: str = api_data["token_officer"]  # type: ignore

    # 1. Acknowledge
    ack_res = client.post(
        f"/api/v1/applications/{app.id}/validation-runs/{run.id}/findings/{finding.id}/actions",
        json={"action": "acknowledge", "comment": "Officer reviewing fire safety NOC."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ack_res.status_code == 201
    ack_data = ack_res.json()
    assert ack_data["finding"]["status"] == "acknowledged"
    assert ack_data["action"]["action"] == "acknowledge"
    assert ack_data["action"]["previous_status"] == "open"
    assert ack_data["action"]["new_status"] == "acknowledged"

    # 2. Add comment
    cmt_res = client.post(
        f"/api/v1/applications/{app.id}/validation-runs/{run.id}/findings/{finding.id}/actions",
        json={"action": "comment", "comment": "Contacted state fire department for certificate copy."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cmt_res.status_code == 201
    cmt_data = cmt_res.json()
    assert cmt_data["finding"]["status"] == "acknowledged"
    assert cmt_data["action"]["action"] == "comment"

    # 3. Resolve with rationale
    resolve_res = client.post(
        f"/api/v1/applications/{app.id}/validation-runs/{run.id}/findings/{finding.id}/actions",
        json={
            "action": "resolve",
            "rationale": "Verified renewed NOC issued on 2026-02-01 valid until 2029-01-31.",
            "resolution_outcome": "issue_addressed",
            "evidence_ref": "storage://docs/fire_noc_renewed.pdf",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resolve_res.status_code == 201
    res_data = resolve_res.json()
    assert res_data["finding"]["status"] == "resolved"
    assert res_data["finding"]["resolved_by"] == "officer_api"
    assert res_data["action"]["action"] == "resolve"

    # 4. Reopen with rationale
    reopen_res = client.post(
        f"/api/v1/applications/{app.id}/validation-runs/{run.id}/findings/{finding.id}/actions",
        json={
            "action": "reopen",
            "rationale": "Audit check found discrepancies in seal of submitted renewed NOC.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reopen_res.status_code == 201
    reopen_data = reopen_res.json()
    assert reopen_data["finding"]["status"] == "open"
    assert reopen_data["finding"]["resolved_by"] is None

    # 5. Escalate with rationale
    esc_res = client.post(
        f"/api/v1/applications/{app.id}/validation-runs/{run.id}/findings/{finding.id}/actions",
        json={
            "action": "escalate",
            "rationale": "Escalating suspicious NOC seal to legal verification committee.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert esc_res.status_code == 201
    esc_data = esc_res.json()
    assert esc_data["finding"]["status"] == "escalated"

    # Verify history has 5 actions in chronological order
    history_res = client.get(
        f"/api/v1/applications/{app.id}/validation-runs/{run.id}/findings/{finding.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history_res.status_code == 200
    hist_data = history_res.json()
    assert len(hist_data["review_actions"]) == 5
    assert [a["action"] for a in hist_data["review_actions"]] == [
        "acknowledge",
        "comment",
        "resolve",
        "reopen",
        "escalate",
    ]


def test_record_review_action_validation_errors(client: TestClient, api_data: dict[str, object]):
    app: Application = api_data["application"]  # type: ignore
    run: ValidationRun = api_data["run"]  # type: ignore
    finding: Finding = api_data["finding1"]  # type: ignore
    token: str = api_data["token_officer"]  # type: ignore

    # Missing rationale on resolve returns 422
    res = client.post(
        f"/api/v1/applications/{app.id}/validation-runs/{run.id}/findings/{finding.id}/actions",
        json={"action": "resolve"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422
    assert "rationale" in res.json()["detail"].lower()

    # Invalid state transition (open -> reopen) returns 400
    res_invalid = client.post(
        f"/api/v1/applications/{app.id}/validation-runs/{run.id}/findings/{finding.id}/actions",
        json={"action": "reopen", "rationale": "trying to reopen an open finding"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_invalid.status_code == 400
    assert "not permitted" in res_invalid.json()["detail"].lower()


def test_get_reviewer_queue(client: TestClient, api_data: dict[str, object]):
    token: str = api_data["token_officer"]  # type: ignore

    res = client.get(
        "/api/v1/reviews/queue",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["institution_id"] == "INST-ENG-01"
    assert data["items"][0]["application_type"] == "eoa"
