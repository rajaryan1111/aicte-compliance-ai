"""Concurrency, optimistic locking, idempotency, and automated check separation tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
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
    AuditEvent,
    Finding,
    Institution,
    InstitutionMembership,
    ReviewAction,
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
def concurrency_data(db_session: Session) -> dict[str, object]:
    hashed_pwd = get_password_hash("ValidPass123!")

    institution = Institution(institution_id="INST-CONCURRENCY", display_name="Concurrency Institute")
    db_session.add(institution)
    db_session.flush()

    reviewer_1 = User(username="reviewer_alice", hashed_password=hashed_pwd)
    reviewer_2 = User(username="reviewer_bob", hashed_password=hashed_pwd)
    db_session.add_all([reviewer_1, reviewer_2])
    db_session.flush()

    mem_1 = InstitutionMembership(
        user_id=reviewer_1.id, institution_id=institution.id, role=ROLE_SCRUTINY_OFFICER, is_active=True
    )
    mem_2 = InstitutionMembership(
        user_id=reviewer_2.id, institution_id=institution.id, role=ROLE_SCRUTINY_OFFICER, is_active=True
    )
    db_session.add_all([mem_1, mem_2])

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

    check_res = ValidationCheckResult(
        validation_run_id=run.id,
        check_id="CHK_FIRE_SAFETY",
        check_name="Fire Safety NOC",
        category="safety",
        status="failed",
        message="Fire Safety NOC missing valid clearance stamp.",
    )
    db_session.add(check_res)

    finding = Finding(
        validation_run_id=run.id,
        code="CHK_FIRE_SAFETY",
        status="open",
        severity="high",
        summary="Missing Fire Clearance Stamp",
        version=1,
    )
    db_session.add(finding)
    db_session.commit()

    token_1 = create_access_token(subject=reviewer_1.id, extra_claims={"username": reviewer_1.username})
    token_2 = create_access_token(subject=reviewer_2.id, extra_claims={"username": reviewer_2.username})

    return {
        "institution": institution,
        "application": application,
        "run": run,
        "check_result": check_res,
        "finding": finding,
        "token_1": token_1,
        "token_2": token_2,
    }


def test_optimistic_concurrency_conflict_409(client: TestClient, concurrency_data: dict[str, object]):
    app: Application = concurrency_data["application"]  # type: ignore
    run: ValidationRun = concurrency_data["run"]  # type: ignore
    finding: Finding = concurrency_data["finding"]  # type: ignore
    token_1: str = concurrency_data["token_1"]  # type: ignore
    token_2: str = concurrency_data["token_2"]  # type: ignore

    # Both reviewers inspect the finding at version 1
    # Reviewer 1 acknowledges the finding specifying expected_version=1
    res1 = client.post(
        f"/api/v1/applications/{app.id}/validation-runs/{run.id}/findings/{finding.id}/actions",
        json={"action": "acknowledge", "expected_version": 1},
        headers={"Authorization": f"Bearer {token_1}"},
    )
    assert res1.status_code == 201
    assert res1.json()["finding"]["version"] == 2

    # Reviewer 2 concurrently submits a resolve action with stale expected_version=1
    res2 = client.post(
        f"/api/v1/applications/{app.id}/validation-runs/{run.id}/findings/{finding.id}/actions",
        json={
            "action": "resolve",
            "rationale": "Verified valid stamp on hard copy.",
            "expected_version": 1,
        },
        headers={"Authorization": f"Bearer {token_2}"},
    )
    assert res2.status_code == 409
    assert "updated by another reviewer" in res2.json()["detail"].lower()

    # Reviewer 2 fetches updated state, sees version=2, and retries with expected_version=2
    res3 = client.post(
        f"/api/v1/applications/{app.id}/validation-runs/{run.id}/findings/{finding.id}/actions",
        json={
            "action": "resolve",
            "rationale": "Verified valid stamp on hard copy.",
            "expected_version": 2,
        },
        headers={"Authorization": f"Bearer {token_2}"},
    )
    assert res3.status_code == 201
    assert res3.json()["finding"]["version"] == 3
    assert res3.json()["finding"]["status"] == "resolved"


def test_idempotent_retry_handling(
    client: TestClient, concurrency_data: dict[str, object], db_session: Session
):
    app: Application = concurrency_data["application"]  # type: ignore
    run: ValidationRun = concurrency_data["run"]  # type: ignore
    finding: Finding = concurrency_data["finding"]  # type: ignore
    token_1: str = concurrency_data["token_1"]  # type: ignore

    request_id = "req-idempotent-unique-uuid-999"

    # Initial submission
    res1 = client.post(
        f"/api/v1/applications/{app.id}/validation-runs/{run.id}/findings/{finding.id}/actions",
        json={
            "action": "acknowledge",
            "comment": "Initial review acknowledgment.",
            "request_id": request_id,
        },
        headers={"Authorization": f"Bearer {token_1}"},
    )
    assert res1.status_code == 201
    action_id_1 = res1.json()["action"]["id"]

    # Retried submission with identical request_id (simulating client retry after network blip)
    res2 = client.post(
        f"/api/v1/applications/{app.id}/validation-runs/{run.id}/findings/{finding.id}/actions",
        json={
            "action": "acknowledge",
            "comment": "Initial review acknowledgment.",
            "request_id": request_id,
        },
        headers={"Authorization": f"Bearer {token_1}"},
    )
    assert res2.status_code == 201
    action_id_2 = res2.json()["action"]["id"]
    assert action_id_1 == action_id_2
    assert "previously recorded" in res2.json()["message"].lower()

    # Verify database has exactly 1 ReviewAction record, not 2
    actions = db_session.query(ReviewAction).filter_by(finding_id=finding.id).all()
    assert len(actions) == 1

    # Verify audit event was logged only once
    audits = db_session.query(AuditEvent).filter_by(target_id=str(finding.id)).all()
    assert len(audits) == 1


def test_automated_check_results_preserved_after_human_resolution(
    client: TestClient, concurrency_data: dict[str, object], db_session: Session
):
    app: Application = concurrency_data["application"]  # type: ignore
    run: ValidationRun = concurrency_data["run"]  # type: ignore
    finding: Finding = concurrency_data["finding"]  # type: ignore
    check_result: ValidationCheckResult = concurrency_data["check_result"]  # type: ignore
    token_1: str = concurrency_data["token_1"]  # type: ignore

    # Initial state: check_result failed
    assert check_result.status == "failed"

    # Reviewer resolves finding
    res = client.post(
        f"/api/v1/applications/{app.id}/validation-runs/{run.id}/findings/{finding.id}/actions",
        json={
            "action": "resolve",
            "rationale": "Clarified that fire department issued addendum letter.",
            "resolution_outcome": "issue_addressed",
        },
        headers={"Authorization": f"Bearer {token_1}"},
    )
    assert res.status_code == 201
    assert res.json()["finding"]["status"] == "resolved"

    # CRITICAL: Automated check result MUST strictly remain failed
    db_session.refresh(check_result)
    assert check_result.status == "failed"
    assert "Fire Safety NOC missing valid clearance stamp" in check_result.message

    # ValidationRun status and outcome must also remain unchanged
    db_session.refresh(run)
    assert run.outcome == "failed"
    assert run.status == "completed"
