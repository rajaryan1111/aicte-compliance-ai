"""Tests for Task B8: Application-Level Validation API Endpoints, RBAC, Tenant Isolation, and Outbox Integration.

Verifies:
- Unauthenticated validation requests return 401 Unauthorized.
- Authorized institutional admin triggers validation returning 201 Created.
- Auditor user (read-only) triggering validation returns 403 Forbidden.
- Cross-tenant user attempting validation returns 404 Not Found (information concealment).
- Listing validation runs via GET /api/v1/applications/{id}/validation-runs.
- Fetching full scrutiny report via GET /api/v1/applications/{id}/validation-runs/{run_id}.
- Cross-tenant access to report or findings returns 404 Not Found.
- Fetching findings via GET /api/v1/applications/{id}/validation-runs/{run_id}/findings.
- Asynchronous validation via Prefer: respond-async returns 202 Accepted with polling URL.
- Celery worker task execution and duplicate delivery idempotency.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.rbac import ROLE_AUDITOR, ROLE_INSTITUTION_ADMIN
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
    Document,
    DocumentVersion,
    ExtractedField,
    Institution,
    InstitutionMembership,
    User,
)
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.worker.celery_app import celery_app
from backend.app.worker.tasks import set_worker_session_factory, validate_application_task

TEST_JWT_SECRET = "test-secret-key-minimum-32-characters-for-hs256-compliance!!"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "True")
    celery_app.conf.task_always_eager = True


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
    set_worker_session_factory(session_factory)
    try:
        yield session
    finally:
        session.close()
        set_worker_session_factory(None)
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
def institutions(db_session: Session) -> tuple[Institution, Institution]:
    inst_a = Institution(institution_id="INST-TENANT-A", display_name="Tenant A College")
    inst_b = Institution(institution_id="INST-TENANT-B", display_name="Tenant B University")
    db_session.add_all([inst_a, inst_b])
    db_session.commit()
    db_session.refresh(inst_a)
    db_session.refresh(inst_b)
    return inst_a, inst_b


@pytest.fixture
def users_and_tokens(
    db_session: Session, institutions: tuple[Institution, Institution]
) -> dict[str, tuple[User, str]]:
    inst_a, inst_b = institutions
    hashed_pwd = get_password_hash("ValidPass123!")

    # 1. Admin in Tenant A
    user_a_admin = User(username="admin_a", hashed_password=hashed_pwd)
    db_session.add(user_a_admin)
    db_session.flush()
    mem_a_admin = InstitutionMembership(
        user_id=user_a_admin.id, institution_id=inst_a.id, role=ROLE_INSTITUTION_ADMIN
    )
    db_session.add(mem_a_admin)

    # 2. Auditor in Tenant A
    user_a_auditor = User(username="auditor_a", hashed_password=hashed_pwd)
    db_session.add(user_a_auditor)
    db_session.flush()
    mem_a_auditor = InstitutionMembership(
        user_id=user_a_auditor.id, institution_id=inst_a.id, role=ROLE_AUDITOR
    )
    db_session.add(mem_a_auditor)

    # 3. Admin in Tenant B
    user_b_admin = User(username="admin_b", hashed_password=hashed_pwd)
    db_session.add(user_b_admin)
    db_session.flush()
    mem_b_admin = InstitutionMembership(
        user_id=user_b_admin.id, institution_id=inst_b.id, role=ROLE_INSTITUTION_ADMIN
    )
    db_session.add(mem_b_admin)

    db_session.commit()

    token_a_admin = create_access_token(subject=user_a_admin.id, extra_claims={"username": user_a_admin.username})
    token_a_auditor = create_access_token(subject=user_a_auditor.id, extra_claims={"username": user_a_auditor.username})
    token_b_admin = create_access_token(subject=user_b_admin.id, extra_claims={"username": user_b_admin.username})

    return {
        "admin_a": (user_a_admin, token_a_admin),
        "auditor_a": (user_a_auditor, token_a_auditor),
        "admin_b": (user_b_admin, token_b_admin),
    }


@pytest.fixture
def sample_application_a(db_session: Session, institutions: tuple[Institution, Institution]) -> Application:
    inst_a, _ = institutions
    app_a = Application(
        institution_id=inst_a.id,
        application_type="eoa",
        academic_year="2025-2026",
        status="submitted",
    )
    db_session.add(app_a)
    db_session.commit()
    db_session.refresh(app_a)

    # Attach a clean document
    doc = Document(application_id=app_a.id, document_type="land_document")
    db_session.add(doc)
    db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key="storage_land_a",
        sha256="sha_land_a",
        media_type="application/pdf",
        byte_size=1024,
        scan_status="clean",
        processing_status="succeeded",
    )
    db_session.add(ver)
    db_session.flush()
    doc.current_version_id = ver.id

    ef = ExtractedField(
        document_version_id=ver.id,
        field_name="institution_id",
        raw_text=inst_a.institution_id,
        normalized_value=inst_a.institution_id,
        confidence=0.95,
        engine_name="test_engine",
    )
    db_session.add(ef)
    db_session.commit()
    db_session.refresh(app_a)
    return app_a


# ==============================================================================
# 1. Authentication and RBAC Tests
# ==============================================================================


def test_anonymous_validation_request_rejected(client: TestClient, sample_application_a: Application):
    """Anonymous call to POST /validate returns 401 Unauthorized."""
    resp = client.post(
        f"/api/v1/applications/{sample_application_a.id}/validate",
        json={"checklist_type": "default"},
    )
    assert resp.status_code == 401


def test_authorized_admin_can_validate_application(
    client: TestClient,
    sample_application_a: Application,
    users_and_tokens: dict[str, tuple[User, str]],
):
    """Tenant admin triggers validation successfully and receives 201 Created and ScrutinyReportResponse."""
    _, token = users_and_tokens["admin_a"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        f"/api/v1/applications/{sample_application_a.id}/validate",
        json={"checklist_type": "default"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()

    assert data["application_id"] == sample_application_a.id
    assert data["institution_id"] == "INST-TENANT-A"
    assert "validation_run" in data
    assert data["validation_run"]["status"] == "succeeded"
    assert "check_results" in data
    assert "findings" in data
    assert "disclaimer" in data
    assert "Preliminary pre-scrutiny result only" in data["disclaimer"]


def test_auditor_cannot_trigger_validation(
    client: TestClient,
    sample_application_a: Application,
    users_and_tokens: dict[str, tuple[User, str]],
):
    """Auditor user with read-only permission receives 403 Forbidden on POST /validate."""
    _, token = users_and_tokens["auditor_a"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        f"/api/v1/applications/{sample_application_a.id}/validate",
        json={"checklist_type": "default"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert "Forbidden" in resp.json()["detail"]


def test_cross_tenant_validation_concealed_with_404(
    client: TestClient,
    sample_application_a: Application,
    users_and_tokens: dict[str, tuple[User, str]],
):
    """Admin from Tenant B calling POST /validate on Tenant A's application receives 404 Not Found."""
    _, token = users_and_tokens["admin_b"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        f"/api/v1/applications/{sample_application_a.id}/validate",
        json={"checklist_type": "default"},
        headers=headers,
    )
    assert resp.status_code == 404


# ==============================================================================
# 2. Scrutiny Report Retrieval and Tenant Concealment
# ==============================================================================


def test_list_and_get_validation_runs(
    client: TestClient,
    sample_application_a: Application,
    users_and_tokens: dict[str, tuple[User, str]],
):
    """Verify listing runs and retrieving single scrutiny report."""
    _, admin_token = users_and_tokens["admin_a"]
    _, auditor_token = users_and_tokens["auditor_a"]

    # Trigger a validation run
    create_resp = client.post(
        f"/api/v1/applications/{sample_application_a.id}/validate",
        json={"checklist_type": "default"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    run_id = create_resp.json()["validation_run"]["id"]

    # Auditor can list runs (read permission)
    list_resp = client.get(
        f"/api/v1/applications/{sample_application_a.id}/validation-runs",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert any(r["id"] == run_id for r in list_data["items"])

    # Auditor can retrieve the scrutiny report
    report_resp = client.get(
        f"/api/v1/applications/{sample_application_a.id}/validation-runs/{run_id}",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    assert report_data["validation_run"]["id"] == run_id
    assert report_data["application_id"] == sample_application_a.id

    # Auditor can retrieve findings list
    findings_resp = client.get(
        f"/api/v1/applications/{sample_application_a.id}/validation-runs/{run_id}/findings",
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert findings_resp.status_code == 200
    assert isinstance(findings_resp.json(), list)


def test_cross_tenant_report_access_denied(
    client: TestClient,
    sample_application_a: Application,
    users_and_tokens: dict[str, tuple[User, str]],
):
    """Cross-tenant user cannot retrieve report or findings (returns 404 Not Found)."""
    _, admin_a_token = users_and_tokens["admin_a"]
    _, admin_b_token = users_and_tokens["admin_b"]

    create_resp = client.post(
        f"/api/v1/applications/{sample_application_a.id}/validate",
        json={"checklist_type": "default"},
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    run_id = create_resp.json()["validation_run"]["id"]

    # Tenant B tries to read Tenant A's report
    resp1 = client.get(
        f"/api/v1/applications/{sample_application_a.id}/validation-runs/{run_id}",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert resp1.status_code == 404

    # Tenant B tries to read Tenant A's findings
    resp2 = client.get(
        f"/api/v1/applications/{sample_application_a.id}/validation-runs/{run_id}/findings",
        headers={"Authorization": f"Bearer {admin_b_token}"},
    )
    assert resp2.status_code == 404


# ==============================================================================
# 3. Asynchronous Execution and Background Worker Tests
# ==============================================================================


def test_asynchronous_validation_returns_202_with_polling_url(
    client: TestClient,
    sample_application_a: Application,
    users_and_tokens: dict[str, tuple[User, str]],
):
    """POST /validate with Prefer: respond-async creates a queued run and returns 202 Accepted with polling URL."""
    _, token = users_and_tokens["admin_a"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Prefer": "respond-async",
    }

    resp = client.post(
        f"/api/v1/applications/{sample_application_a.id}/validate",
        json={"checklist_type": "default"},
        headers=headers,
    )
    assert resp.status_code == 202
    data = resp.json()

    assert data["validation_run"]["status"] in ("queued", "running", "succeeded")
    assert data["polling_url"] is not None
    assert f"/api/v1/applications/{sample_application_a.id}/validation-runs/" in data["polling_url"]


def test_worker_validate_application_task_execution_and_idempotency(
    db_session: Session,
    sample_application_a: Application,
):
    """Direct execution of validate_application_task completes run; duplicate delivery is idempotent."""
    from backend.app.repositories.validation_repository import ValidationRepository

    # Create queued run in database
    run = ValidationRepository.create_run(
        db_session,
        application_id=sample_application_a.id,
        evaluation_date=date(2026, 10, 24),
        status="queued",
        triggered_by="test_user",
    )
    db_session.commit()
    run_id = run.id

    # 1. First execution
    res1 = validate_application_task(run_id)
    assert res1["status"] == "succeeded"

    db_session.refresh(run)
    assert run.status == "succeeded"
    assert run.completed_at is not None

    findings1 = ValidationRepository.list_findings_for_run(db_session, run_id)
    check_results1 = ValidationRepository.list_check_results_for_run(db_session, run_id)

    # 2. Duplicate task delivery
    res2 = validate_application_task(run_id)
    assert res2["status"] == "succeeded"

    # Verify no duplicate findings or check results were created
    findings2 = ValidationRepository.list_findings_for_run(db_session, run_id)
    check_results2 = ValidationRepository.list_check_results_for_run(db_session, run_id)

    assert len(findings1) == len(findings2)
    assert len(check_results1) == len(check_results2)
