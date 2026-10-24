"""Security, RBAC, tenant isolation, and authenticated applications API tests.

Covers all 20 required authentication, authorization, and tenant isolation scenarios.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import jwt
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
from backend.app.db.models import Application, AuditEvent, Institution, InstitutionMembership, User
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.repositories.user_repository import UserRepository

TEST_JWT_SECRET = "test-secret-key-minimum-32-characters-for-hs256-compliance!!"


@pytest.fixture(autouse=True)
def setup_test_jwt_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure secure test JWT signing key is available for all tests."""
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)



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
    session = session_factory()
    try:
        yield session
    finally:
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


def create_test_user(
    db: Session,
    username: str,
    password: str = "CorrectPassword123!",
    is_active: bool = True,
) -> User:
    """Helper to provision a synthetic test user with hashed password."""
    user = UserRepository.create(
        db,
        username=username,
        hashed_password=get_password_hash(password),
        is_active=is_active,
    )
    db.commit()
    db.refresh(user)
    return user


def create_test_institution(
    db: Session,
    institution_id: str,
    display_name: str,
) -> Institution:
    """Helper to provision a synthetic test institution."""
    inst = Institution(institution_id=institution_id, display_name=display_name)
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


def assign_test_membership(
    db: Session,
    user_id: int,
    institution_id: int,
    role: str,
    is_active: bool = True,
) -> InstitutionMembership:
    """Helper to assign a role to a user in an institution."""
    membership = UserRepository.create_membership(
        db,
        user_id=user_id,
        institution_id=institution_id,
        role=role,
        is_active=is_active,
    )
    db.commit()
    db.refresh(membership)
    return membership


def auth_header_for_user(user: User) -> dict[str, str]:
    """Generate Authorization header with valid JWT for the user."""
    token = create_access_token(subject=user.id, extra_claims={"username": user.username})
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# SECTION A: Authentication Tests (Scenarios 1 - 6)
# ==============================================================================


def test_scenario_01_unauthenticated_cannot_access_applications(client: TestClient):
    """Scenario 1: An unauthenticated user cannot list, create, retrieve or update applications."""
    # List
    r_list = client.get("/api/v1/applications")
    assert r_list.status_code == 401

    # Create
    r_create = client.post("/api/v1/applications", json={
        "application_type": "eoa",
        "academic_year": "2026-2027",
    })
    assert r_create.status_code == 401

    # Retrieve
    r_get = client.get("/api/v1/applications/1")
    assert r_get.status_code == 401

    # Update
    r_patch = client.patch("/api/v1/applications/1", json={"status": "submitted"})
    assert r_patch.status_code == 401


def test_scenario_02_invalid_token_is_rejected(client: TestClient):
    """Scenario 2: An invalid token is rejected."""
    headers = {"Authorization": "Bearer invalid.garbage.token"}
    r = client.get("/api/v1/applications", headers=headers)
    assert r.status_code == 401
    assert "credentials" in r.json()["detail"].lower()


def test_scenario_03_expired_token_is_rejected(client: TestClient, db_session: Session):
    """Scenario 3: An expired token is rejected."""
    user = create_test_user(db_session, "expired_user")
    # Token expired 10 minutes ago
    expired_token = create_access_token(
        subject=user.id,
        expires_delta=timedelta(minutes=-10),
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    r = client.get("/api/v1/applications", headers=headers)
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_scenario_04_disallowed_algorithm_or_signature_rejected(client: TestClient, db_session: Session):
    """Scenario 4: A token with disallowed algorithm or forged signature is rejected."""
    user = create_test_user(db_session, "forged_user")

    # 1. Unsigned / algorithm none token
    now = datetime.now(timezone.utc)
    token_none = jwt.encode(
        {"sub": str(user.id), "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=1)).timestamp())},
        key="",
        algorithm="none",
    )
    r1 = client.get("/api/v1/applications", headers={"Authorization": f"Bearer {token_none}"})
    assert r1.status_code == 401

    # 2. Token signed with wrong secret key
    token_wrong_key = jwt.encode(
        {"sub": str(user.id), "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=1)).timestamp())},
        key="completely-different-signing-key-that-is-at-least-32-chars!",
        algorithm="HS256",
    )
    r2 = client.get("/api/v1/applications", headers={"Authorization": f"Bearer {token_wrong_key}"})
    assert r2.status_code == 401


def test_scenario_05_inactive_account_cannot_access_data(client: TestClient, db_session: Session):
    """Scenario 5: An inactive account cannot access protected data."""
    # User is marked is_active = False
    inactive_user = create_test_user(db_session, "disabled_user", is_active=False)
    headers = auth_header_for_user(inactive_user)

    r = client.get("/api/v1/applications", headers=headers)
    assert r.status_code == 401
    assert "inactive" in r.json()["detail"].lower()


def test_scenario_06_revoked_or_inactive_membership_denied(client: TestClient, db_session: Session):
    """Scenario 6: A user with a revoked/inactive institutional membership cannot retain access."""
    user = create_test_user(db_session, "revoked_member")
    inst = create_test_institution(db_session, "INST-REV-01", "Revoked Inst")
    # Inactive membership
    assign_test_membership(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN, is_active=False)

    headers = auth_header_for_user(user)

    # Attempt to create application for this institution
    r_create = client.post(
        "/api/v1/applications",
        json={"institution_id": inst.id, "application_type": "eoa", "academic_year": "2026-2027"},
        headers=headers,
    )
    # 404 concealed or 403 denied
    assert r_create.status_code in (403, 404)


# ==============================================================================
# SECTION B: Authorization and Tenant Isolation (Scenarios 7 - 14)
# ==============================================================================


def test_scenario_07_institution_admin_can_manage_authorized_applications(client: TestClient, db_session: Session):
    """Scenario 7: An institution administrator can access authorized institutional applications."""
    user = create_test_user(db_session, "inst_admin_1")
    inst = create_test_institution(db_session, "INST-A-01", "Institute Alpha")
    assign_test_membership(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN)

    headers = auth_header_for_user(user)

    # 1. Create application
    r_create = client.post(
        "/api/v1/applications",
        json={"institution_id": inst.id, "application_type": "eoa", "academic_year": "2026-2027"},
        headers=headers,
    )
    assert r_create.status_code == 201
    app_data = r_create.json()
    app_id = app_data["id"]
    assert app_data["institution_id"] == inst.id
    assert app_data["status"] == "draft"

    # 2. Retrieve application
    r_get = client.get(f"/api/v1/applications/{app_id}", headers=headers)
    assert r_get.status_code == 200
    assert r_get.json()["id"] == app_id

    # 3. List applications
    r_list = client.get("/api/v1/applications", headers=headers)
    assert r_list.status_code == 200
    assert r_list.json()["total"] == 1
    assert r_list.json()["items"][0]["id"] == app_id

    # 4. Update application
    r_update = client.patch(
        f"/api/v1/applications/{app_id}",
        json={"status": "submitted"},
        headers=headers,
    )
    assert r_update.status_code == 200
    assert r_update.json()["status"] == "submitted"


def test_scenario_08_admin_cannot_read_other_institutions_application(client: TestClient, db_session: Session):
    """Scenario 8: An institution administrator cannot read another institution's application."""
    user_a = create_test_user(db_session, "admin_a")
    inst_a = create_test_institution(db_session, "INST-A-02", "Inst A")
    assign_test_membership(db_session, user_a.id, inst_a.id, ROLE_INSTITUTION_ADMIN)

    user_b = create_test_user(db_session, "admin_b")
    inst_b = create_test_institution(db_session, "INST-B-02", "Inst B")
    assign_test_membership(db_session, user_b.id, inst_b.id, ROLE_INSTITUTION_ADMIN)

    # Create application in Inst B
    headers_b = auth_header_for_user(user_b)
    r_create = client.post(
        "/api/v1/applications",
        json={"institution_id": inst_b.id, "application_type": "eoa", "academic_year": "2026-2027"},
        headers=headers_b,
    )
    assert r_create.status_code == 201
    app_b_id = r_create.json()["id"]

    # User A attempts to read User B's application -> 404 (concealed)
    headers_a = auth_header_for_user(user_a)
    r_read = client.get(f"/api/v1/applications/{app_b_id}", headers=headers_a)
    assert r_read.status_code == 404


def test_scenario_09_admin_cannot_modify_other_institutions_application(client: TestClient, db_session: Session):
    """Scenario 9: An institution administrator cannot modify another institution's application."""
    user_a = create_test_user(db_session, "admin_a_mut")
    inst_a = create_test_institution(db_session, "INST-A-03", "Inst A")
    assign_test_membership(db_session, user_a.id, inst_a.id, ROLE_INSTITUTION_ADMIN)

    user_b = create_test_user(db_session, "admin_b_mut")
    inst_b = create_test_institution(db_session, "INST-B-03", "Inst B")
    assign_test_membership(db_session, user_b.id, inst_b.id, ROLE_INSTITUTION_ADMIN)

    # Create application in Inst B
    headers_b = auth_header_for_user(user_b)
    r_create = client.post(
        "/api/v1/applications",
        json={"institution_id": inst_b.id, "application_type": "eoa", "academic_year": "2026-2027"},
        headers=headers_b,
    )
    app_b_id = r_create.json()["id"]

    # User A attempts to modify Inst B's application
    headers_a = auth_header_for_user(user_a)
    r_patch = client.patch(
        f"/api/v1/applications/{app_b_id}",
        json={"status": "submitted"},
        headers=headers_a,
    )
    assert r_patch.status_code == 404

    # Assert database state remains unmodified!
    db_session.expire_all()
    db_app = db_session.get(Application, app_b_id)
    assert db_app is not None
    assert db_app.status == "draft"


def test_scenario_10_user_cannot_gain_scope_by_tampering_institution_id(client: TestClient, db_session: Session):
    """Scenario 10: A user cannot gain scope by tampering with an institution ID in body or query."""
    user = create_test_user(db_session, "tamper_user")
    inst_own = create_test_institution(db_session, "INST-OWN", "Own Inst")
    inst_victim = create_test_institution(db_session, "INST-VICTIM", "Victim Inst")
    assign_test_membership(db_session, user.id, inst_own.id, ROLE_INSTITUTION_ADMIN)

    headers = auth_header_for_user(user)

    # 1. Tampering body institution_id to victim institution
    r_body = client.post(
        "/api/v1/applications",
        json={"institution_id": inst_victim.id, "application_type": "eoa", "academic_year": "2026-2027"},
        headers=headers,
    )
    assert r_body.status_code == 404

    # 2. Tampering query parameter institution_id to victim institution
    r_query = client.get(f"/api/v1/applications?institution_id={inst_victim.id}", headers=headers)
    assert r_query.status_code == 404


def test_scenario_11_auditor_cannot_perform_write_operations(client: TestClient, db_session: Session):
    """Scenario 11: An auditor cannot perform write operations (create or update)."""
    admin = create_test_user(db_session, "admin_for_auditor")
    auditor = create_test_user(db_session, "auditor_user")
    inst = create_test_institution(db_session, "INST-AUD", "Audited Inst")

    assign_test_membership(db_session, admin.id, inst.id, ROLE_INSTITUTION_ADMIN)
    assign_test_membership(db_session, auditor.id, inst.id, ROLE_AUDITOR)

    # Admin creates application
    r_create = client.post(
        "/api/v1/applications",
        json={"institution_id": inst.id, "application_type": "eoa", "academic_year": "2026-2027"},
        headers=auth_header_for_user(admin),
    )
    app_id = r_create.json()["id"]

    headers_auditor = auth_header_for_user(auditor)

    # 1. Auditor cannot create applications -> 403
    r_auditor_create = client.post(
        "/api/v1/applications",
        json={"institution_id": inst.id, "application_type": "new_program", "academic_year": "2026-2027"},
        headers=headers_auditor,
    )
    assert r_auditor_create.status_code == 403

    # 2. Auditor can read applications -> 200
    r_auditor_read = client.get(f"/api/v1/applications/{app_id}", headers=headers_auditor)
    assert r_auditor_read.status_code == 200

    # 3. Auditor cannot update applications -> 403
    r_auditor_patch = client.patch(
        f"/api/v1/applications/{app_id}",
        json={"status": "submitted"},
        headers=headers_auditor,
    )
    assert r_auditor_patch.status_code == 403


def test_scenario_12_scrutiny_officer_cannot_access_unauthorized_institution(client: TestClient, db_session: Session):
    """Scenario 12: A scrutiny officer cannot access an institution outside their explicit assignment."""
    officer = create_test_user(db_session, "scrutiny_off")
    inst_assigned = create_test_institution(db_session, "INST-ASSIGNED", "Assigned Inst")
    inst_foreign = create_test_institution(db_session, "INST-FOREIGN", "Foreign Inst")

    assign_test_membership(db_session, officer.id, inst_assigned.id, ROLE_SCRUTINY_OFFICER)

    headers = auth_header_for_user(officer)

    # Officer cannot read foreign institution's application list
    r_foreign = client.get(f"/api/v1/applications?institution_id={inst_foreign.id}", headers=headers)
    assert r_foreign.status_code == 404

    # Officer cannot create applications even in assigned institution
    r_create = client.post(
        "/api/v1/applications",
        json={"institution_id": inst_assigned.id, "application_type": "eoa", "academic_year": "2026-2027"},
        headers=headers,
    )
    assert r_create.status_code == 403


def test_scenario_13_unrecognized_role_denied_by_default(client: TestClient, db_session: Session):
    """Scenario 13: An unrecognized role is denied by default."""
    user = create_test_user(db_session, "unknown_role_user")
    inst = create_test_institution(db_session, "INST-UNK", "Unknown Role Inst")
    assign_test_membership(db_session, user.id, inst.id, role="super_admin_bypass_attempt")

    headers = auth_header_for_user(user)

    r_create = client.post(
        "/api/v1/applications",
        json={"institution_id": inst.id, "application_type": "eoa", "academic_year": "2026-2027"},
        headers=headers,
    )
    assert r_create.status_code == 403

    r_list = client.get(f"/api/v1/applications?institution_id={inst.id}", headers=headers)
    assert r_list.status_code == 403


def test_scenario_14_resource_ids_cannot_bypass_tenant_isolation(client: TestClient, db_session: Session):
    """Scenario 14: Resource IDs cannot be used to bypass tenant isolation."""
    user1 = create_test_user(db_session, "tenant_1_user")
    user2 = create_test_user(db_session, "tenant_2_user")
    inst1 = create_test_institution(db_session, "INST-1", "Tenant 1")
    inst2 = create_test_institution(db_session, "INST-2", "Tenant 2")

    assign_test_membership(db_session, user1.id, inst1.id, ROLE_INSTITUTION_ADMIN)
    assign_test_membership(db_session, user2.id, inst2.id, ROLE_INSTITUTION_ADMIN)

    # User 2 creates application
    r2 = client.post(
        "/api/v1/applications",
        json={"institution_id": inst2.id, "application_type": "eoa", "academic_year": "2026-2027"},
        headers=auth_header_for_user(user2),
    )
    tenant2_app_id = r2.json()["id"]

    # User 1 attempts direct ID access
    r1 = client.get(f"/api/v1/applications/{tenant2_app_id}", headers=auth_header_for_user(user1))
    assert r1.status_code == 404


# ==============================================================================
# SECTION C: Application Workflow & Audit (Scenarios 15 - 20)
# ==============================================================================


def test_scenario_15_authorized_request_creates_application_via_service(client: TestClient, db_session: Session):
    """Scenario 15: An authorized request creates an application through ApplicationService."""
    user = create_test_user(db_session, "creator_user")
    inst = create_test_institution(db_session, "INST-CREATE", "Creator Inst")
    assign_test_membership(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN)

    headers = auth_header_for_user(user)

    # Derives institution automatically if not specified when user has single membership
    r = client.post(
        "/api/v1/applications",
        json={"application_type": "intake_change", "academic_year": "2026-2027"},
        headers=headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["institution_id"] == inst.id
    assert data["application_type"] == "intake_change"
    assert data["status"] == "draft"


def test_scenario_16_pagination_and_status_filtering_institution_scoped(client: TestClient, db_session: Session):
    """Scenario 16: Pagination and status filtering remain institution-scoped."""
    user = create_test_user(db_session, "paging_user")
    inst = create_test_institution(db_session, "INST-PAGE", "Paging Inst")
    other_inst = create_test_institution(db_session, "INST-OTHER", "Other Inst")
    assign_test_membership(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN)

    # Add 3 apps to own institution
    app1 = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027", status="draft")
    app2 = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027", status="submitted")
    app3 = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027", status="draft")
    # Add 1 app to foreign institution
    foreign_app = Application(institution_id=other_inst.id, application_type="eoa", academic_year="2026-2027", status="draft")
    db_session.add_all([app1, app2, app3, foreign_app])
    db_session.commit()

    headers = auth_header_for_user(user)

    # 1. Total count only includes own institution
    r = client.get("/api/v1/applications?skip=0&limit=10", headers=headers)
    assert r.status_code == 200
    assert r.json()["total"] == 3
    assert len(r.json()["items"]) == 3

    # 2. Status filter
    r_filtered = client.get("/api/v1/applications?status=submitted", headers=headers)
    assert r_filtered.status_code == 200
    assert r_filtered.json()["total"] == 1
    assert r_filtered.json()["items"][0]["status"] == "submitted"


def test_scenario_17_invalid_lifecycle_transition_rejected(client: TestClient, db_session: Session):
    """Scenario 17: Invalid lifecycle transitions are rejected."""
    user = create_test_user(db_session, "transition_user")
    inst = create_test_institution(db_session, "INST-TRANS", "Transition Inst")
    assign_test_membership(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN)

    headers = auth_header_for_user(user)
    r_create = client.post(
        "/api/v1/applications",
        json={"institution_id": inst.id, "application_type": "eoa", "academic_year": "2026-2027"},
        headers=headers,
    )
    app_id = r_create.json()["id"]

    # Invalid jump from draft directly to reviewed
    r_bad = client.patch(
        f"/api/v1/applications/{app_id}",
        json={"status": "reviewed"},
        headers=headers,
    )
    assert r_bad.status_code == 400
    assert "Illegal lifecycle transition" in r_bad.json()["detail"]


def test_scenario_18_unauthorized_update_does_not_mutate_db(client: TestClient, db_session: Session):
    """Scenario 18: Unauthorized update attempts do not mutate stored data."""
    admin = create_test_user(db_session, "admin_owner")
    auditor = create_test_user(db_session, "auditor_att")
    inst = create_test_institution(db_session, "INST-IMMUT", "Immut Inst")
    assign_test_membership(db_session, admin.id, inst.id, ROLE_INSTITUTION_ADMIN)
    assign_test_membership(db_session, auditor.id, inst.id, ROLE_AUDITOR)

    r_create = client.post(
        "/api/v1/applications",
        json={"institution_id": inst.id, "application_type": "eoa", "academic_year": "2026-2027"},
        headers=auth_header_for_user(admin),
    )
    app_id = r_create.json()["id"]

    # Auditor attempts to patch status
    r_patch = client.patch(
        f"/api/v1/applications/{app_id}",
        json={"status": "submitted"},
        headers=auth_header_for_user(auditor),
    )
    assert r_patch.status_code == 403

    # Check database row directly
    db_session.expire_all()
    app = db_session.get(Application, app_id)
    assert app is not None
    assert app.status == "draft"


def test_scenario_19_successful_changes_create_audit_events(client: TestClient, db_session: Session):
    """Scenario 19: Successful changes create the expected audit events."""
    user = create_test_user(db_session, "audit_actor")
    inst = create_test_institution(db_session, "INST-AUD-EV", "Audit Event Inst")
    assign_test_membership(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN)

    headers = auth_header_for_user(user)

    # 1. Create application
    r_create = client.post(
        "/api/v1/applications",
        json={"institution_id": inst.id, "application_type": "eoa", "academic_year": "2026-2027"},
        headers=headers,
    )
    app_id = r_create.json()["id"]

    # 2. Update application
    client.patch(
        f"/api/v1/applications/{app_id}",
        json={"status": "submitted"},
        headers=headers,
    )

    # Verify audit events in database
    db_session.expire_all()
    events = list(db_session.scalars(
        select(AuditEvent).where(AuditEvent.target_id == str(app_id)).order_by(AuditEvent.id.asc())
    ).all())

    assert len(events) == 2
    assert events[0].action == "APPLICATION_CREATED"
    assert events[0].actor_id == "audit_actor"
    assert events[1].action == "APPLICATION_UPDATED"
    assert events[1].actor_id == "audit_actor"


def test_scenario_20_failures_do_not_leave_partial_writes(client: TestClient, db_session: Session):
    """Scenario 20: Failures do not leave partial database writes."""
    user = create_test_user(db_session, "rollback_user")
    inst = create_test_institution(db_session, "INST-ROLL", "Rollback Inst")
    assign_test_membership(db_session, user.id, inst.id, ROLE_INSTITUTION_ADMIN)

    headers = auth_header_for_user(user)

    # Invalid academic year should fail validation cleanly without DB writes
    r = client.post(
        "/api/v1/applications",
        json={"institution_id": inst.id, "application_type": "eoa", "academic_year": "invalid-year"},
        headers=headers,
    )
    assert r.status_code == 422

    # Assert no applications created
    apps = list(db_session.scalars(select(Application).where(Application.institution_id == inst.id)).all())
    assert len(apps) == 0


def test_auth_login_and_profile_flow(client: TestClient, db_session: Session):
    """Test login with credentials and fetching user profile."""
    user = create_test_user(db_session, "login_test_user", password="SecurePassword123!")

    # 1. Invalid password
    r_bad_pwd = client.post("/api/v1/auth/token", json={
        "username": user.username,
        "password": "WrongPassword!",
    })
    assert r_bad_pwd.status_code == 401

    # 2. Correct password
    r_login = client.post("/api/v1/auth/token", json={
        "username": user.username,
        "password": "SecurePassword123!",
    })
    assert r_login.status_code == 200
    token_data = r_login.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["expires_in"] == 3600

    # 3. Use token on /me
    token = token_data["access_token"]
    r_me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r_me.status_code == 200
    profile = r_me.json()
    assert profile["username"] == user.username
    assert profile["is_active"] is True


def test_missing_or_short_jwt_secret_fails_safely(monkeypatch: pytest.MonkeyPatch):
    """Verify that startup or token generation fails safely if JWT_SECRET_KEY is missing or < 32 chars."""
    from backend.app.core.security import get_jwt_secret_key

    # Empty
    monkeypatch.setenv("JWT_SECRET_KEY", "")
    with pytest.raises(RuntimeError) as exc_info:
        get_jwt_secret_key()
    assert "JWT_SECRET_KEY environment variable is not configured" in str(exc_info.value)

    # Insecure short key
    monkeypatch.setenv("JWT_SECRET_KEY", "short-key")
    with pytest.raises(RuntimeError) as exc_info2:
        get_jwt_secret_key()
    assert "shorter than 32 characters" in str(exc_info2.value)

