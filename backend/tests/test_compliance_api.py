"""Integration tests for compliance endpoints: issuing-authority, infrastructure, records, and field corrections."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.rbac import (
    ROLE_INSTITUTION_ADMIN,
    ROLE_SCRUTINY_OFFICER,
)
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
def seed_data(db_session: Session) -> dict[str, object]:
    hashed_pwd = get_password_hash("ValidPass123!")
    inst = Institution(institution_id="INST-COMP-01", display_name="Compliance Tech Institute")
    db_session.add(inst)
    db_session.flush()

    user_officer = User(username="officer_comp", hashed_password=hashed_pwd)
    db_session.add(user_officer)
    db_session.flush()

    mem = InstitutionMembership(
        user_id=user_officer.id,
        institution_id=inst.id,
        role=ROLE_SCRUTINY_OFFICER,
        is_active=True,
    )
    db_session.add(mem)

    app_obj = Application(
        institution_id=inst.id,
        application_type="eoa",
        academic_year="2026-2027",
        status="under_review",
    )
    db_session.add(app_obj)
    db_session.flush()

    doc = Document(application_id=app_obj.id, document_type="fire_safety_certificate")
    db_session.add(doc)
    db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key="test_fire_cert.pdf",
        sha256="abc999" + "0" * 58,
        media_type="application/pdf",
        byte_size=1024,
    )
    db_session.add(ver)
    db_session.flush()
    doc.current_version_id = ver.id

    field = ExtractedField(
        document_version_id=ver.id,
        field_name="certificate_number",
        raw_text="FIRE-2024-REG-101",
        normalized_value="FIRE-2024-REG-101",
        engine_name="test_ocr",
    )
    db_session.add(field)
    db_session.commit()

    token = create_access_token(
        subject=str(user_officer.id),
        extra_claims={
            "institution_id": inst.id,
            "role": ROLE_SCRUTINY_OFFICER,
        },
    )

    return {
        "institution": inst,
        "user": user_officer,
        "application": app_obj,
        "document": doc,
        "version": ver,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def test_list_verification_adapters(client: TestClient, seed_data: dict[str, object]):
    headers = seed_data["headers"]
    resp = client.get("/api/v1/compliance/verification-adapters", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 4
    names = {item["adapter_name"] for item in data}
    assert "digilocker_national_gateway" in names
    assert "simulated_demo_adapter" in names


def test_verify_document_version_simulated(client: TestClient, seed_data: dict[str, object]):
    headers = seed_data["headers"]
    app_id = seed_data["application"].id
    doc_id = seed_data["document"].id
    ver_id = seed_data["version"].id

    resp = client.post(
        f"/api/v1/compliance/applications/{app_id}/documents/{doc_id}/versions/{ver_id}/verify",
        headers=headers,
        json={
            "adapter_name": "simulated_demo_adapter",
            "force_simulated": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "simulated_demo"
    assert data["is_official_source"] is False
    assert data["application_id"] == app_id
    assert data["document_version_id"] == ver_id


def test_list_application_verifications(client: TestClient, seed_data: dict[str, object]):
    headers = seed_data["headers"]
    app_id = seed_data["application"].id
    doc_id = seed_data["document"].id
    ver_id = seed_data["version"].id

    # Create one attempt first
    client.post(
        f"/api/v1/compliance/applications/{app_id}/documents/{doc_id}/versions/{ver_id}/verify",
        headers=headers,
        json={"force_simulated": True},
    )

    resp = client.get(
        f"/api/v1/compliance/applications/{app_id}/verifications",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["application_id"] == app_id


def test_execute_infrastructure_review(client: TestClient, seed_data: dict[str, object]):
    headers = seed_data["headers"]
    app_id = seed_data["application"].id

    resp = client.post(
        f"/api/v1/compliance/applications/{app_id}/infrastructure/review",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["application_id"] == app_id
    assert "overall_status" in data
    assert "physical_inspection_recommended" in data
    assert isinstance(data["items"], list)


def test_get_institutional_records_comparison(client: TestClient, seed_data: dict[str, object]):
    headers = seed_data["headers"]
    app_id = seed_data["application"].id

    resp = client.get(
        f"/api/v1/compliance/applications/{app_id}/institutional-records",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["application_id"] == app_id
    assert data["overall_consistency"] in ("consistent", "discrepancies_detected")
    assert len(data["comparisons"]) == 4


def test_correct_extracted_field(client: TestClient, seed_data: dict[str, object]):
    headers = seed_data["headers"]
    app_id = seed_data["application"].id
    doc_id = seed_data["document"].id
    ver_id = seed_data["version"].id

    resp = client.patch(
        f"/api/v1/compliance/applications/{app_id}/documents/{doc_id}/versions/{ver_id}/fields/certificate_number",
        headers=headers,
        json={
            "corrected_value": "FIRE-2024-CORRECTED-999",
            "rationale": "Corrected OCR trailing digit from image stamp.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["field_name"] == "certificate_number"
    assert data["corrected_value"] == "FIRE-2024-CORRECTED-999"
    assert data["previous_value"] == "FIRE-2024-REG-101"
    assert "user_comp" in data["corrected_by"] or "officer_comp" in data["corrected_by"]


def test_list_regulatory_rules_api(client: TestClient, seed_data: dict[str, object]):
    headers = seed_data["headers"]
    resp = client.get("/api/v1/compliance/rules", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 6
    ids = {r["rule_id"] for r in data}
    assert "APH_2024_FIRE_SAFETY" in ids
    assert "APH_2024_STRUCTURAL_STABILITY" in ids


def test_approve_regulatory_rule_unauthorized(client: TestClient, seed_data: dict[str, object]):
    # Scrutiny officer lacks PERMISSION_RULE_APPROVE
    headers = seed_data["headers"]
    resp = client.post(
        "/api/v1/compliance/rules/APH_2024_FIRE_SAFETY/approve",
        headers=headers,
        json={
            "rationale": "Unauthorized attempt to approve statutory rule.",
            "statutory_interpretation_approved": True,
        },
    )
    assert resp.status_code == 403
    assert "lacks permission" in resp.json()["detail"].lower() or "permission_rule_approve" in resp.json()["detail"].lower()


def test_approve_regulatory_rule_director(client: TestClient, db_session: Session, seed_data: dict[str, object]):
    from backend.app.core.rbac import ROLE_REGULATORY_DIRECTOR

    hashed_pwd = get_password_hash("DirectorSecret123!")
    director_user = User(username="director_legal", hashed_password=hashed_pwd)
    db_session.add(director_user)
    db_session.flush()

    mem = InstitutionMembership(
        user_id=director_user.id,
        institution_id=seed_data["institution"].id,
        role=ROLE_REGULATORY_DIRECTOR,
        is_active=True,
    )
    db_session.add(mem)
    db_session.commit()

    token = create_access_token(
        subject=str(director_user.id),
        extra_claims={"institution_id": seed_data["institution"].id, "role": ROLE_REGULATORY_DIRECTOR},
    )
    dir_headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/api/v1/compliance/rules/APH_2024_FIRE_SAFETY/approve",
        headers=dir_headers,
        json={
            "rationale": "Director scrutiny confirming compliance with AICTE APH 2024-2027 Clause 2.4.",
            "statutory_interpretation_approved": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["rule_id"] == "APH_2024_FIRE_SAFETY"
    assert data["status"] == "active"
    assert data["decision"] == "approved"
    assert data["reviewer_username"] == "director_legal"
    assert data["statutory_interpretation_approved"] is True

    # Check history endpoint
    resp_hist = client.get("/api/v1/compliance/rules/history", headers=dir_headers)
    assert resp_hist.status_code == 200
    hist = resp_hist.json()
    assert len(hist) >= 1
    assert any(h["rule_id"] == "APH_2024_FIRE_SAFETY" for h in hist)


def test_retention_api_endpoints(client: TestClient, seed_data: dict[str, object]):
    headers = seed_data["headers"]

    # Status
    resp_status = client.get("/api/v1/compliance/retention/status", headers=headers)
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert "quarantine_retention_days" in status_data
    assert "job_retention_days" in status_data
    assert "audit_log_retention_years" in status_data

    # Dry-run purge trigger
    resp_purge = client.post(
        "/api/v1/compliance/retention/purge",
        headers=headers,
        json={"dry_run": True, "quarantine_days": 30, "job_days": 14},
    )
    assert resp_purge.status_code == 200
    purge_data = resp_purge.json()
    assert purge_data["dry_run"] is True
    assert purge_data["status"] == "completed"
    assert "run_reference" in purge_data

    # List runs
    resp_runs = client.get("/api/v1/compliance/retention/runs", headers=headers)
    assert resp_runs.status_code == 200
    runs = resp_runs.json()
    assert len(runs) >= 1
