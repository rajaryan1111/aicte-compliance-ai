"""Authorization and persistence tests for the consistency API."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.rbac import ROLE_AUDITOR, ROLE_INSTITUTION_ADMIN
from backend.app.core.security import create_access_token
from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
    AuditEvent,
    ConsistencyCheck,
    ConsistencyFinding,
    Institution,
    InstitutionMembership,
    User,
)
from backend.app.db.session import get_db
from backend.app.main import app

TEST_JWT_SECRET = "test-secret-key-minimum-32-characters-for-hs256-compliance!!"
CHECK_PAYLOAD = {
    "application_id": 1,
    "check_name": "Institution identifier comparison",
    "description": "Compare the institution IDs across submitted records.",
    "related_field": "institution_id",
}
FINDING_PAYLOAD = {
    "consistency_check_id": 1,
    "field_name": "institution_id",
    "value_1": "INST-A",
    "value_2": "INST-B",
    "severity": "high",
    "confidence": 0.95,
    "description": "The identifiers differ across the two records.",
    "evidence": {"document_types": ["application", "approval_letter"]},
}


@pytest.fixture(autouse=True)
def configure_test_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
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
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def data(db_session: Session) -> dict[str, object]:
    institution_a = Institution(institution_id="INST-A", display_name="Institution A")
    institution_b = Institution(institution_id="INST-B", display_name="Institution B")
    db_session.add_all([institution_a, institution_b])
    db_session.flush()

    user_a = User(username="consistency_admin_a", hashed_password="unused")
    auditor_a = User(username="consistency_auditor_a", hashed_password="unused")
    user_b = User(username="consistency_admin_b", hashed_password="unused")
    db_session.add_all([user_a, auditor_a, user_b])
    db_session.flush()
    db_session.add_all(
        [
            InstitutionMembership(
                user_id=user_a.id,
                institution_id=institution_a.id,
                role=ROLE_INSTITUTION_ADMIN,
            ),
            InstitutionMembership(
                user_id=auditor_a.id,
                institution_id=institution_a.id,
                role=ROLE_AUDITOR,
            ),
            InstitutionMembership(
                user_id=user_b.id,
                institution_id=institution_b.id,
                role=ROLE_INSTITUTION_ADMIN,
            ),
        ]
    )
    application_a = Application(
        institution_id=institution_a.id,
        application_type="eoa",
        academic_year="2026-2027",
        status="submitted",
    )
    application_b = Application(
        institution_id=institution_b.id,
        application_type="eoa",
        academic_year="2026-2027",
        status="submitted",
    )
    db_session.add_all([application_a, application_b])
    db_session.flush()
    check_a = ConsistencyCheck(
        application_id=application_a.id,
        check_name="Institution identifier comparison",
        description="Compare institution IDs.",
        related_field="institution_id",
        status="discrepancy_detected",
    )
    db_session.add(check_a)
    db_session.flush()
    finding_a = ConsistencyFinding(
        consistency_check_id=check_a.id,
        field_name="institution_id",
        value_1="INST-A",
        value_2="OTHER",
        severity="high",
        confidence=0.95,
        description="Identifiers do not match.",
        evidence={"source": "fixture"},
        resolved=False,
    )
    db_session.add(finding_a)
    db_session.commit()

    return {
        "application_a": application_a,
        "application_b": application_b,
        "check_a": check_a,
        "finding_a": finding_a,
        "admin_a": (
            user_a,
            create_access_token(subject=user_a.id, extra_claims={"username": user_a.username}),
        ),
        "auditor_a": (
            auditor_a,
            create_access_token(
                subject=auditor_a.id, extra_claims={"username": auditor_a.username}
            ),
        ),
        "admin_b": (
            user_b,
            create_access_token(subject=user_b.id, extra_claims={"username": user_b.username}),
        ),
    }


def _headers(data: dict[str, object], actor: str) -> dict[str, str]:
    token = data[actor][1]  # type: ignore[index]
    return {"Authorization": f"Bearer {token}"}


def test_application_starts_and_registers_all_consistency_routes() -> None:
    paths = app.openapi()["paths"]
    assert "/health" in paths
    assert "post" in paths["/consistency/"]
    assert "get" in paths["/consistency/"]
    assert "get" in paths["/consistency/{check_id}"]
    assert "post" in paths["/consistency/findings"]
    assert "get" in paths["/consistency/findings/{finding_id}"]
    assert "get" in paths["/consistency/checks/{check_id}/findings"]
    assert "patch" in paths["/consistency/findings/{finding_id}"]


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/consistency/1", None),
        ("get", "/consistency/?application_id=1", None),
        ("post", "/consistency/", CHECK_PAYLOAD),
        ("post", "/consistency/findings", FINDING_PAYLOAD),
        ("get", "/consistency/findings/1", None),
        ("get", "/consistency/checks/1/findings", None),
        ("patch", "/consistency/findings/1", {"resolved": True}),
    ],
)
def test_all_consistency_routes_reject_anonymous_requests(
    client: TestClient,
    data: dict[str, object],
    method: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    response = getattr(client, method)(path, json=payload) if payload is not None else getattr(client, method)(path)
    assert response.status_code == 401


def test_authorized_member_can_use_all_consistency_endpoints(
    client: TestClient,
    data: dict[str, object],
    db_session: Session,
) -> None:
    headers = _headers(data, "admin_a")
    application_a = data["application_a"]

    created_check_response = client.post(
        "/consistency/",
        json={**CHECK_PAYLOAD, "application_id": application_a.id},
        headers=headers,
    )
    assert created_check_response.status_code == 201
    created_check = created_check_response.json()
    assert created_check["status"] == "pending"
    check_id = created_check["id"]

    assert client.get(f"/consistency/{check_id}", headers=headers).status_code == 200
    listed_checks = client.get(
        f"/consistency/?application_id={application_a.id}", headers=headers
    )
    assert listed_checks.status_code == 200
    assert check_id in [check["id"] for check in listed_checks.json()]
    assert all(check["application_id"] == application_a.id for check in listed_checks.json())

    created_finding_response = client.post(
        "/consistency/findings",
        json={**FINDING_PAYLOAD, "consistency_check_id": check_id},
        headers=headers,
    )
    assert created_finding_response.status_code == 201
    created_finding = created_finding_response.json()
    assert created_finding["evidence"] == FINDING_PAYLOAD["evidence"]
    finding_id = created_finding["id"]

    assert client.get(
        f"/consistency/findings/{finding_id}", headers=headers
    ).status_code == 200
    listed_findings = client.get(
        f"/consistency/checks/{check_id}/findings?severity_filter=high&resolved=false",
        headers=headers,
    )
    assert listed_findings.status_code == 200
    assert [finding["id"] for finding in listed_findings.json()] == [finding_id]

    updated = client.patch(
        f"/consistency/findings/{finding_id}",
        json={"resolved": True, "description": "Reviewed and resolved."},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["resolved"] is True
    db_session.refresh(db_session.get(ConsistencyCheck, check_id))
    assert db_session.get(ConsistencyCheck, check_id).status == "resolved"


def test_cross_institution_reads_and_mutations_are_concealed_and_noop(
    client: TestClient,
    data: dict[str, object],
    db_session: Session,
) -> None:
    check = data["check_a"]
    finding = data["finding_a"]
    headers = _headers(data, "admin_b")
    checks_before = db_session.scalar(select(func.count()).select_from(ConsistencyCheck))
    findings_before = db_session.scalar(select(func.count()).select_from(ConsistencyFinding))
    audit_events_before = db_session.scalar(select(func.count()).select_from(AuditEvent))
    severity_before = finding.severity

    assert client.get(f"/consistency/{check.id}", headers=headers).status_code == 404
    assert client.get(
        f"/consistency/?application_id={data['application_a'].id}", headers=headers
    ).status_code == 404
    assert client.get(f"/consistency/findings/{finding.id}", headers=headers).status_code == 404
    assert client.get(
        f"/consistency/checks/{check.id}/findings", headers=headers
    ).status_code == 404
    assert client.post(
        "/consistency/",
        json={**CHECK_PAYLOAD, "application_id": data["application_a"].id},
        headers=headers,
    ).status_code == 404
    assert client.post(
        "/consistency/findings",
        json={**FINDING_PAYLOAD, "consistency_check_id": check.id},
        headers=headers,
    ).status_code == 404
    assert client.patch(
        f"/consistency/findings/{finding.id}",
        json={"severity": "critical", "resolved": True},
        headers=headers,
    ).status_code == 404

    assert db_session.scalar(select(func.count()).select_from(ConsistencyCheck)) == checks_before
    assert db_session.scalar(select(func.count()).select_from(ConsistencyFinding)) == findings_before
    assert db_session.scalar(select(func.count()).select_from(AuditEvent)) == audit_events_before
    db_session.refresh(finding)
    assert finding.severity == severity_before
    assert finding.resolved is False


def test_auditor_can_read_but_cannot_mutate_consistency_records(
    client: TestClient,
    data: dict[str, object],
    db_session: Session,
) -> None:
    headers = _headers(data, "auditor_a")
    check = data["check_a"]
    finding = data["finding_a"]
    count_before = db_session.scalar(select(func.count()).select_from(ConsistencyFinding))
    audit_events_before = db_session.scalar(select(func.count()).select_from(AuditEvent))

    assert client.get(f"/consistency/{check.id}", headers=headers).status_code == 200
    response = client.post(
        "/consistency/findings",
        json={**FINDING_PAYLOAD, "consistency_check_id": check.id},
        headers=headers,
    )
    assert response.status_code == 403
    response = client.patch(
        f"/consistency/findings/{finding.id}",
        json={"resolved": True},
        headers=headers,
    )
    assert response.status_code == 403

    assert db_session.scalar(select(func.count()).select_from(ConsistencyFinding)) == count_before
    assert db_session.scalar(select(func.count()).select_from(AuditEvent)) == audit_events_before
    db_session.refresh(finding)
    assert finding.resolved is False


def test_invalid_parent_ids_fail_closed_without_database_changes(
    client: TestClient,
    data: dict[str, object],
    db_session: Session,
) -> None:
    headers = _headers(data, "admin_a")
    checks_before = db_session.scalar(select(func.count()).select_from(ConsistencyCheck))
    findings_before = db_session.scalar(select(func.count()).select_from(ConsistencyFinding))

    assert client.post(
        "/consistency/", json={**CHECK_PAYLOAD, "application_id": 99999}, headers=headers
    ).status_code == 404
    assert client.post(
        "/consistency/findings",
        json={**FINDING_PAYLOAD, "consistency_check_id": 99999},
        headers=headers,
    ).status_code == 404
    assert client.get("/consistency/99999", headers=headers).status_code == 404
    assert client.patch(
        "/consistency/findings/99999", json={"resolved": True}, headers=headers
    ).status_code == 404

    assert db_session.scalar(select(func.count()).select_from(ConsistencyCheck)) == checks_before
    assert db_session.scalar(select(func.count()).select_from(ConsistencyFinding)) == findings_before


def test_list_without_filter_returns_only_accessible_institution_records(
    client: TestClient,
    data: dict[str, object],
) -> None:
    response = client.get("/consistency/", headers=_headers(data, "admin_a"))
    assert response.status_code == 200
    assert all(check["application_id"] == data["application_a"].id for check in response.json())
