"""Institution-scoped remediation plan API: auth, RBAC, tenancy, idempotency and audit.

These tests exercise the persisted plan workflow with synthetic institutions and users. They cover
multi-user and multi-institution behaviour explicitly: the same deficiency signature must never
leak across tenants, and two members of the same institution must share progress.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
import json

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.rbac import (
    ROLE_AUDITOR,
    ROLE_INSTITUTION_ADMIN,
    ROLE_SCRUTINY_OFFICER,
)
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.db.base import Base
from backend.app.db.models import AuditEvent, Institution, User
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.repositories.user_repository import UserRepository

TEST_JWT_SECRET = "test-secret-key-minimum-32-characters-for-hs256-compliance!!"


@pytest.fixture(autouse=True)
def _jwt_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── Synthetic fixtures ───────────────────────────────────────────────────────


def make_user(db: Session, username: str) -> User:
    user = UserRepository.create(
        db,
        username=username,
        hashed_password=get_password_hash("CorrectPassword123!"),
    )
    db.commit()
    db.refresh(user)
    return user


def make_institution(db: Session, ref: str) -> Institution:
    institution = Institution(institution_id=ref, display_name=f"{ref} Institute")
    db.add(institution)
    db.commit()
    db.refresh(institution)
    return institution


def join(db: Session, user: User, institution: Institution, role: str) -> None:
    UserRepository.create_membership(
        db, user_id=user.id, institution_id=institution.id, role=role
    )
    db.commit()


def headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=user.id, extra_claims={"username": user.username})
    return {"Authorization": f"Bearer {token}"}


def plan_body(institution_ref: str, plan_key: str = "plan-0123abcd", **overrides) -> dict:
    body = {
        "institution_ref": institution_ref,
        "plan_key": plan_key,
        "application_type": "eoa",
        "deadline_policy": {
            "p1_days": 3,
            "p2_days": 7,
            "p3_buffer_days": 14,
            "p3_max_days": 21,
            "expiring_window_days": 60,
        },
        "items": [
            {
                "task_key": "fire_safety_certificate::MISSING_DOCUMENT",
                "document_id": "fire_safety_certificate",
                "document_label": "Fire Safety Certificate / NOC",
                "finding_code": "MISSING_DOCUMENT",
                "priority": "P1",
                "owner_role": "Estate & Fire Safety Officer",
                "due_date": "2026-11-03",
                "evidence_required": "Valid fire NOC covering all blocks.",
                "clause": "Clause 2.4",
            },
            {
                "task_key": "aicte_approval::DOCUMENT_EXPIRED",
                "document_id": "aicte_approval",
                "document_label": "AICTE Approval Letter",
                "finding_code": "DOCUMENT_EXPIRED",
                "priority": "P1",
                "owner_role": "Registrar / Principal",
                "due_date": "2026-11-03",
                "evidence_required": "Current LoA/LoE with validity dates.",
                "clause": None,
            },
        ],
    }
    body.update(overrides)
    return body


def create_plan(client: TestClient, user: User, ref: str, **overrides) -> dict:
    response = client.post(
        f"/api/v1/institutions/{ref}/remediation-plans",
        json=plan_body(ref, **overrides),
        headers=headers(user),
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


# ── Authentication and tenancy ───────────────────────────────────────────────


def test_plan_routes_require_authentication(client: TestClient, db_session: Session):
    make_institution(db_session, "SYNTH-A-001")
    ref = "SYNTH-A-001"

    assert client.post(f"/api/v1/institutions/{ref}/remediation-plans", json=plan_body(ref)).status_code == 401
    assert client.get(f"/api/v1/institutions/{ref}/remediation-plans").status_code == 401
    assert client.get(f"/api/v1/institutions/{ref}/remediation-plans/1").status_code == 401
    update = {"status": "done", "version": 1}
    assert client.patch(
        f"/api/v1/institutions/{ref}/remediation-plans/1/tasks/x", json=update
    ).status_code == 401


def test_unknown_institution_is_not_disclosed(client: TestClient, db_session: Session):
    user = make_user(db_session, "admin_unknown")
    response = client.post(
        "/api/v1/institutions/NOT-REGISTERED/remediation-plans",
        json=plan_body("NOT-REGISTERED"),
        headers=headers(user),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Institution not found or access denied."


def test_foreign_institution_is_concealed_as_not_found(client: TestClient, db_session: Session):
    """User A belongs to A only; A must not be able to read or write B's plan even with its id."""
    institution_a = make_institution(db_session, "SYNTH-A-002")
    institution_b = make_institution(db_session, "SYNTH-B-002")
    user_a = make_user(db_session, "user_a2")
    join(db_session, user_a, institution_a, ROLE_INSTITUTION_ADMIN)

    user_b = make_user(db_session, "user_b2")
    join(db_session, user_b, institution_b, ROLE_INSTITUTION_ADMIN)
    plan_b = create_plan(client, user_b, "SYNTH-B-002")

    read = client.get(
        f"/api/v1/institutions/SYNTH-B-002/remediation-plans/{plan_b['id']}",
        headers=headers(user_a),
    )
    assert read.status_code == 404

    write = client.patch(
        f"/api/v1/institutions/SYNTH-B-002/remediation-plans/{plan_b['id']}/tasks/"
        "fire_safety_certificate::MISSING_DOCUMENT",
        json={"status": "done", "version": 1},
        headers=headers(user_a),
    )
    assert write.status_code == 404

    listing = client.get(
        "/api/v1/institutions/SYNTH-B-002/remediation-plans", headers=headers(user_a)
    )
    assert listing.status_code == 404


def test_read_only_role_can_read_but_not_write(client: TestClient, db_session: Session):
    institution = make_institution(db_session, "SYNTH-A-003")
    admin = make_user(db_session, "admin3")
    join(db_session, admin, institution, ROLE_INSTITUTION_ADMIN)
    auditor = make_user(db_session, "auditor3")
    join(db_session, auditor, institution, ROLE_AUDITOR)

    plan = create_plan(client, admin, "SYNTH-A-003")

    assert client.get(
        "/api/v1/institutions/SYNTH-A-003/remediation-plans", headers=headers(auditor)
    ).status_code == 200

    denied = client.patch(
        f"/api/v1/institutions/SYNTH-A-003/remediation-plans/{plan['id']}/tasks/"
        "fire_safety_certificate::MISSING_DOCUMENT",
        json={"status": "done", "version": 1},
        headers=headers(auditor),
    )
    assert denied.status_code == 403
    assert "plan:write" in denied.json()["detail"]

    create_denied = client.post(
        "/api/v1/institutions/SYNTH-A-003/remediation-plans",
        json=plan_body("SYNTH-A-003", plan_key="plan-other"),
        headers=headers(auditor),
    )
    assert create_denied.status_code == 403


# ── Creation and idempotency ─────────────────────────────────────────────────


def test_create_returns_201_then_reopens_same_plan_with_200(client: TestClient, db_session: Session):
    institution = make_institution(db_session, "SYNTH-A-004")
    user = make_user(db_session, "admin4")
    join(db_session, user, institution, ROLE_INSTITUTION_ADMIN)

    first = create_plan(client, user, "SYNTH-A-004")
    assert first["plan_key"] == "plan-0123abcd"
    assert len(first["tasks"]) == 2
    assert {task["status"] for task in first["tasks"]} == {"open"}
    assert {task["version"] for task in first["tasks"]} == {1}
    assert first["deadline_policy"]["p1_days"] == 3
    assert "not AICTE deadlines" in first["notice"]

    # Record progress, then re-post the same signature.
    key = "fire_safety_certificate::MISSING_DOCUMENT"
    update = client.patch(
        f"/api/v1/institutions/SYNTH-A-004/remediation-plans/{first['id']}/tasks/{key}",
        json={"status": "done", "note": "NOC received", "version": 1},
        headers=headers(user),
    )
    assert update.status_code == 200
    assert update.json()["version"] == 2

    reopened = client.post(
        "/api/v1/institutions/SYNTH-A-004/remediation-plans",
        json=plan_body("SYNTH-A-004"),
        headers=headers(user),
    )
    assert reopened.status_code == 200
    assert reopened.json()["id"] == first["id"]
    reopened_task = next(t for t in reopened.json()["tasks"] if t["task_key"] == key)
    assert reopened_task["status"] == "done", "re-validating must not reset recorded progress"
    assert reopened_task["note"] == "NOC received"
    assert reopened_task["version"] == 2

    listing = client.get(
        "/api/v1/institutions/SYNTH-A-004/remediation-plans", headers=headers(user)
    )
    assert listing.json()["total"] == 1


def test_same_plan_key_in_two_institutions_stays_separate(client: TestClient, db_session: Session):
    institution_a = make_institution(db_session, "SYNTH-A-005")
    institution_b = make_institution(db_session, "SYNTH-B-005")
    admin = make_user(db_session, "admin5")
    join(db_session, admin, institution_a, ROLE_INSTITUTION_ADMIN)
    join(db_session, admin, institution_b, ROLE_INSTITUTION_ADMIN)

    plan_a = create_plan(client, admin, "SYNTH-A-005", plan_key="plan-shared")
    plan_b = create_plan(client, admin, "SYNTH-B-005", plan_key="plan-shared")

    assert plan_a["id"] != plan_b["id"]

    updated = client.patch(
        f"/api/v1/institutions/SYNTH-A-005/remediation-plans/{plan_a['id']}/tasks/"
        "fire_safety_certificate::MISSING_DOCUMENT",
        json={"status": "done", "version": 1},
        headers=headers(admin),
    )
    assert updated.status_code == 200

    other = client.get(
        f"/api/v1/institutions/SYNTH-B-005/remediation-plans/{plan_b['id']}", headers=headers(admin)
    )
    statuses = {task["status"] for task in other.json()["tasks"]}
    assert statuses == {"open"}, "progress in one institution must not affect another"


def test_path_and_body_institution_must_match(client: TestClient, db_session: Session):
    institution = make_institution(db_session, "SYNTH-A-006")
    user = make_user(db_session, "admin6")
    join(db_session, user, institution, ROLE_INSTITUTION_ADMIN)

    mismatch = client.post(
        "/api/v1/institutions/SYNTH-A-006/remediation-plans",
        json=plan_body("SYNTH-B-006"),
        headers=headers(user),
    )
    assert mismatch.status_code == 422


# ── Concurrency, audit and validation ────────────────────────────────────────


def test_status_change_is_attributed_and_audited(client: TestClient, db_session: Session):
    institution = make_institution(db_session, "SYNTH-A-007")
    user = make_user(db_session, "officer7")
    join(db_session, user, institution, ROLE_SCRUTINY_OFFICER)
    plan = create_plan(client, user, "SYNTH-A-007")

    key = "aicte_approval::DOCUMENT_EXPIRED"
    response = client.patch(
        f"/api/v1/institutions/SYNTH-A-007/remediation-plans/{plan['id']}/tasks/{key}",
        json={"status": "in_progress", "version": 1},
        headers=headers(user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["status_changed_by"] == "officer7"
    assert body["status_changed_at"] is not None
    assert body["version"] == 2

    db_session.expire_all()
    events = list(
        db_session.scalars(
            select(AuditEvent).where(AuditEvent.action == "remediation_task_updated")
        ).all()
    )
    assert len(events) == 1
    assert events[0].actor_id == "officer7"
    assert events[0].institution_id == institution.id
    details = json.loads(events[0].details or "{}")
    assert details["changes"] == [{"field": "status", "from": "open", "to": "in_progress"}]
    assert key in events[0].target_id

    created = list(
        db_session.scalars(
            select(AuditEvent).where(AuditEvent.action == "remediation_plan_created")
        ).all()
    )
    assert len(created) == 1
    assert json.loads(created[0].details or "{}")["task_count"] == 2


def test_stale_version_is_rejected_with_conflict(client: TestClient, db_session: Session):
    institution = make_institution(db_session, "SYNTH-A-008")
    first_user = make_user(db_session, "user8a")
    second_user = make_user(db_session, "user8b")
    join(db_session, first_user, institution, ROLE_SCRUTINY_OFFICER)
    join(db_session, second_user, institution, ROLE_SCRUTINY_OFFICER)
    plan = create_plan(client, first_user, "SYNTH-A-008")
    key = "fire_safety_certificate::MISSING_DOCUMENT"
    url = f"/api/v1/institutions/SYNTH-A-008/remediation-plans/{plan['id']}/tasks/{key}"

    accepted = client.patch(url, json={"status": "done", "version": 1}, headers=headers(first_user))
    assert accepted.status_code == 200

    # Second officer still holds version 1: the edit must not overwrite the first one.
    rejected = client.patch(
        url, json={"status": "blocked", "version": 1}, headers=headers(second_user)
    )
    assert rejected.status_code == 409
    assert rejected.headers["X-Current-Version"] == "2"
    assert "version" in rejected.json()["detail"].lower()

    current = client.get(
        f"/api/v1/institutions/SYNTH-A-008/remediation-plans/{plan['id']}",
        headers=headers(second_user),
    )
    task = next(t for t in current.json()["tasks"] if t["task_key"] == key)
    assert task["status"] == "done"


def test_identical_update_is_an_idempotent_no_op(client: TestClient, db_session: Session):
    institution = make_institution(db_session, "SYNTH-A-009")
    user = make_user(db_session, "user9")
    join(db_session, user, institution, ROLE_SCRUTINY_OFFICER)
    plan = create_plan(client, user, "SYNTH-A-009")
    key = "fire_safety_certificate::MISSING_DOCUMENT"
    url = f"/api/v1/institutions/SYNTH-A-009/remediation-plans/{plan['id']}/tasks/{key}"

    first = client.patch(url, json={"status": "done", "version": 1}, headers=headers(user))
    assert first.status_code == 200
    repeat = client.patch(url, json={"status": "done", "version": 2}, headers=headers(user))
    assert repeat.status_code == 200
    assert repeat.json()["version"] == 2, "a retry must not bump the version again"


def test_invalid_payloads_are_rejected(client: TestClient, db_session: Session):
    institution = make_institution(db_session, "SYNTH-A-010")
    user = make_user(db_session, "user10")
    join(db_session, user, institution, ROLE_INSTITUTION_ADMIN)
    plan = create_plan(client, user, "SYNTH-A-010")
    key = "fire_safety_certificate::MISSING_DOCUMENT"
    url = f"/api/v1/institutions/SYNTH-A-010/remediation-plans/{plan['id']}/tasks/{key}"

    assert client.patch(
        url, json={"status": "approved", "version": 1}, headers=headers(user)
    ).status_code == 422
    assert client.patch(
        url, json={"note": "x" * 281, "version": 1}, headers=headers(user)
    ).status_code == 422
    assert client.patch(url, json={"version": 0}, headers=headers(user)).status_code == 422

    bad_policy = plan_body(
        "SYNTH-A-010",
        plan_key="plan-badpolicy",
        deadline_policy={"p1_days": 10, "p2_days": 5},
    )
    assert client.post(
        "/api/v1/institutions/SYNTH-A-010/remediation-plans",
        json=bad_policy,
        headers=headers(user),
    ).status_code == 422

    duplicate_keys = plan_body("SYNTH-A-010", plan_key="plan-dupes")
    duplicate_keys["items"][1]["task_key"] = duplicate_keys["items"][0]["task_key"]
    assert client.post(
        "/api/v1/institutions/SYNTH-A-010/remediation-plans",
        json=duplicate_keys,
        headers=headers(user),
    ).status_code == 422

    unknown_task = client.patch(
        url.replace(key, "does_not_exist::MISSING_DOCUMENT"),
        json={"status": "done", "version": 1},
        headers=headers(user),
    )
    assert unknown_task.status_code == 404


def test_note_text_is_not_copied_into_the_audit_log(client: TestClient, db_session: Session):
    institution = make_institution(db_session, "SYNTH-A-011")
    user = make_user(db_session, "user11")
    join(db_session, user, institution, ROLE_INSTITUTION_ADMIN)
    plan = create_plan(client, user, "SYNTH-A-011")
    key = "aicte_approval::DOCUMENT_EXPIRED"
    secret_note = "Contact 9876543210 about the renewal"

    response = client.patch(
        f"/api/v1/institutions/SYNTH-A-011/remediation-plans/{plan['id']}/tasks/{key}",
        json={"note": secret_note, "version": 1},
        headers=headers(user),
    )
    assert response.status_code == 200
    assert response.json()["note"] == secret_note

    db_session.expire_all()
    event = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "remediation_task_updated")
    ).one()
    assert secret_note not in (event.details or "")
    assert json.loads(event.details or "{}")["changes"][0]["length"] == len(secret_note)


def test_plan_listing_scopes_to_the_calling_institution(client: TestClient, db_session: Session):
    institution_a = make_institution(db_session, "SYNTH-A-012")
    institution_b = make_institution(db_session, "SYNTH-B-012")
    user_a = make_user(db_session, "user12a")
    user_b = make_user(db_session, "user12b")
    join(db_session, user_a, institution_a, ROLE_INSTITUTION_ADMIN)
    join(db_session, user_b, institution_b, ROLE_INSTITUTION_ADMIN)

    create_plan(client, user_a, "SYNTH-A-012", plan_key="plan-a-one")
    create_plan(client, user_a, "SYNTH-A-012", plan_key="plan-a-two")
    create_plan(client, user_b, "SYNTH-B-012", plan_key="plan-b-one")

    listing_a = client.get(
        "/api/v1/institutions/SYNTH-A-012/remediation-plans", headers=headers(user_a)
    ).json()
    assert listing_a["total"] == 2
    assert {item["plan_key"] for item in listing_a["items"]} == {"plan-a-one", "plan-a-two"}

    filtered = client.get(
        "/api/v1/institutions/SYNTH-A-012/remediation-plans?plan_key=plan-a-two",
        headers=headers(user_a),
    ).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["plan_key"] == "plan-a-two"

    assert client.get(
        "/api/v1/institutions/SYNTH-B-012/remediation-plans", headers=headers(user_a)
    ).status_code == 404


def test_deadline_policy_is_stored_as_the_basis_for_due_dates(
    client: TestClient, db_session: Session
):
    institution = make_institution(db_session, "SYNTH-A-013")
    user = make_user(db_session, "user13")
    join(db_session, user, institution, ROLE_INSTITUTION_ADMIN)

    plan = create_plan(
        client,
        user,
        "SYNTH-A-013",
        deadline_policy={
            "p1_days": 2,
            "p2_days": 9,
            "p3_buffer_days": 10,
            "p3_max_days": 30,
            "expiring_window_days": 45,
        },
    )
    assert plan["deadline_policy"] == {
        "p1_days": 2,
        "p2_days": 9,
        "p3_buffer_days": 10,
        "p3_max_days": 30,
        "expiring_window_days": 45,
    }

    db_session.expire_all()
    event = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "remediation_plan_created")
    ).one()
    details = json.loads(event.details or "{}")
    assert details["deadline_policy"]["p1_days"] == 2
    assert details["source"] == "client_derived_preliminary_validation"


# ── Administrator rescheduling and deadline history ───────────────────────────


def _reschedule(client: TestClient, user: User, ref: str, plan_id: int, **policy):
    body = {
        "policy": {
            "p1_days": policy.get("p1_days", 3),
            "p2_days": policy.get("p2_days", 7),
            "p3_buffer_days": policy.get("p3_buffer_days", 14),
            "p3_max_days": policy.get("p3_max_days", 21),
            "expiring_window_days": policy.get("expiring_window_days", 60),
        }
    }
    return client.patch(
        f"/api/v1/institutions/{ref}/remediation-plans/{plan_id}/deadline-policy",
        json=body,
        headers=headers(user),
    )


def test_only_administrators_can_reschedule(client: TestClient, db_session: Session):
    institution = make_institution(db_session, "SYNTH-A-020")
    other = make_institution(db_session, "SYNTH-B-020")
    admin = make_user(db_session, "admin20")
    officer = make_user(db_session, "officer20")
    auditor = make_user(db_session, "auditor20")
    foreign = make_user(db_session, "foreign20")
    join(db_session, admin, institution, ROLE_INSTITUTION_ADMIN)
    join(db_session, officer, institution, ROLE_SCRUTINY_OFFICER)
    join(db_session, auditor, institution, ROLE_AUDITOR)
    join(db_session, foreign, other, ROLE_INSTITUTION_ADMIN)

    plan = create_plan(client, admin, "SYNTH-A-020")
    url = f"/api/v1/institutions/SYNTH-A-020/remediation-plans/{plan['id']}/deadline-policy"
    body = {"policy": {"p1_days": 4, "p2_days": 8, "p3_buffer_days": 14, "p3_max_days": 21, "expiring_window_days": 60}}

    assert client.patch(url, json=body).status_code == 401
    assert client.patch(url, json=body, headers=headers(auditor)).status_code == 403
    # A scrutiny officer may edit tasks but must not move institutional commitments.
    assert client.patch(url, json=body, headers=headers(officer)).status_code == 403
    assert (
        client.patch(
            f"/api/v1/institutions/SYNTH-B-020/remediation-plans/{plan['id']}/deadline-policy",
            json=body,
            headers=headers(foreign),
        ).status_code
        == 404
    )
    assert client.patch(url, json=body, headers=headers(admin)).status_code == 200


def test_reschedule_moves_open_tasks_only(client: TestClient, db_session: Session):
    institution = make_institution(db_session, "SYNTH-A-021")
    admin = make_user(db_session, "admin21")
    join(db_session, admin, institution, ROLE_INSTITUTION_ADMIN)

    items = [
        {
            "task_key": "fire_safety_certificate::MISSING_DOCUMENT",
            "document_id": "fire_safety_certificate",
            "document_label": "Fire Safety Certificate / NOC",
            "finding_code": "MISSING_DOCUMENT",
            "priority": "P1",
            "owner_role": "Estate & Fire Safety Officer",
            "due_date": (datetime.now(timezone.utc).date() + timedelta(days=3)).isoformat(),
            "evidence_required": "Valid fire NOC covering all blocks.",
            "clause": "Clause 2.4",
        },
        {
            "task_key": "aicte_approval::DOCUMENT_EXPIRED",
            "document_id": "aicte_approval",
            "document_label": "AICTE Approval Letter",
            "finding_code": "DOCUMENT_EXPIRED",
            "priority": "P2",
            "owner_role": "Registrar / Principal",
            "due_date": (datetime.now(timezone.utc).date() + timedelta(days=7)).isoformat(),
            "evidence_required": "Current LoA/LoE with validity dates.",
            "clause": None,
        },
        {
            "task_key": "nba_accreditation::EXPIRING_SOON",
            "document_id": "nba_accreditation",
            "document_label": "NBA Accreditation Certificate",
            "finding_code": "EXPIRING_SOON",
            "priority": "P3",
            "owner_role": "IQAC Coordinator",
            "due_date": (datetime.now(timezone.utc).date() + timedelta(days=5)).isoformat(),
            "evidence_required": "Renewal acknowledgement.",
            "clause": None,
        },
    ]
    plan = create_plan(client, admin, "SYNTH-A-021", items=items)
    # Complete the P1 task first: a completed task must keep the date it was completed against.
    done = client.patch(
        f"/api/v1/institutions/SYNTH-A-021/remediation-plans/{plan['id']}/tasks/"
        "fire_safety_certificate::MISSING_DOCUMENT",
        json={"status": "done", "version": 1},
        headers=headers(admin),
    )
    assert done.status_code == 200, done.text

    response = _reschedule(client, admin, "SYNTH-A-021", plan["id"], p1_days=9, p2_days=12, p3_max_days=40)
    assert response.status_code == 200, response.text
    updated = {task["task_key"]: task for task in response.json()["tasks"]}
    today = datetime.now(timezone.utc).date()

    assert updated["fire_safety_certificate::MISSING_DOCUMENT"]["due_date"] == (
        today + timedelta(days=3)
    ).isoformat()
    assert updated["aicte_approval::DOCUMENT_EXPIRED"]["due_date"] == (
        today + timedelta(days=12)
    ).isoformat()
    assert updated["nba_accreditation::EXPIRING_SOON"]["due_date"] == (
        today + timedelta(days=5)
    ).isoformat()
    # Moved tasks must invalidate stale tabs; the untouched ones keep their version.
    assert updated["aicte_approval::DOCUMENT_EXPIRED"]["version"] == 2
    assert updated["nba_accreditation::EXPIRING_SOON"]["version"] == 1
    assert response.json()["deadline_history"][0]["rescheduled_tasks"] == 1
    assert response.json()["deadline_history"][0]["changed_by"] == "admin21"


def test_reschedule_history_is_append_only_and_idempotent(
    client: TestClient, db_session: Session
):
    institution = make_institution(db_session, "SYNTH-A-022")
    admin = make_user(db_session, "admin22")
    join(db_session, admin, institution, ROLE_INSTITUTION_ADMIN)
    plan = create_plan(client, admin, "SYNTH-A-022")

    first = _reschedule(client, admin, "SYNTH-A-022", plan["id"], p1_days=5, p2_days=10)
    assert first.status_code == 200, first.text
    assert len(first.json()["deadline_history"]) == 1

    # An identical request must not append history or bump task versions.
    second = _reschedule(client, admin, "SYNTH-A-022", plan["id"], p1_days=5, p2_days=10)
    assert second.status_code == 200, second.text
    assert len(second.json()["deadline_history"]) == 1
    assert [task["version"] for task in second.json()["tasks"]] == [
        task["version"] for task in first.json()["tasks"]
    ]

    third = _reschedule(client, admin, "SYNTH-A-022", plan["id"], p1_days=1, p2_days=2)
    history = third.json()["deadline_history"]
    assert len(history) == 2
    # Newest first, each entry carrying the exact before/after policy.
    assert history[0]["new_policy"]["p1_days"] == 1
    assert history[0]["previous_policy"]["p1_days"] == 5
    assert history[1]["new_policy"]["p1_days"] == 5
    assert history[1]["previous_policy"]["p1_days"] == 3

    db_session.expire_all()
    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "remediation_deadline_policy_changed")
    ).all()
    assert len(events) == 2
    details = json.loads(events[0].details or "{}")
    assert details["policy_scope"] == "internal_recommendation_not_aicte_deadline"
    assert details["new_policy"]["p1_days"] in (1, 5)


def test_reschedule_rejects_invalid_policy(client: TestClient, db_session: Session):
    institution = make_institution(db_session, "SYNTH-A-023")
    admin = make_user(db_session, "admin23")
    join(db_session, admin, institution, ROLE_INSTITUTION_ADMIN)
    plan = create_plan(client, admin, "SYNTH-A-023")

    response = _reschedule(client, admin, "SYNTH-A-023", plan["id"], p1_days=10, p2_days=5)
    assert response.status_code == 422
    response = _reschedule(client, admin, "SYNTH-A-023", plan["id"], p1_days=0)
    assert response.status_code == 422
    response = _reschedule(client, admin, "SYNTH-A-023", plan["id"], p1_days=400)
    assert response.status_code == 422
