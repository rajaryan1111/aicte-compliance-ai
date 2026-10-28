"""Negative security tests verifying tenant isolation across institutional boundaries."""

from __future__ import annotations

from collections.abc import Generator
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
def multi_tenant_data(db_session: Session) -> dict[str, object]:
    hashed_pwd = get_password_hash("Password123!")

    # Institution A
    inst_a = Institution(institution_id="INST-TENANT-A", display_name="Alpha Engineering College")
    db_session.add(inst_a)
    db_session.flush()

    user_a = User(username="user_tenant_a", hashed_password=hashed_pwd)
    db_session.add(user_a)
    db_session.flush()

    mem_a = InstitutionMembership(
        user_id=user_a.id,
        institution_id=inst_a.id,
        role=ROLE_INSTITUTION_ADMIN,
        is_active=True,
    )
    db_session.add(mem_a)

    app_a = Application(institution_id=inst_a.id, application_type="eoa", academic_year="2026-2027")
    db_session.add(app_a)
    db_session.flush()

    doc_a = Document(application_id=app_a.id, document_type="fire_safety_certificate")
    db_session.add(doc_a)
    db_session.flush()

    ver_a = DocumentVersion(
        document_id=doc_a.id,
        version_number=1,
        storage_key="tenant_a_fire.pdf",
        sha256="111" + "0" * 61,
        media_type="application/pdf",
        byte_size=1024,
    )
    db_session.add(ver_a)

    # Institution B
    inst_b = Institution(institution_id="INST-TENANT-B", display_name="Beta Technical Institute")
    db_session.add(inst_b)
    db_session.flush()

    user_b = User(username="user_tenant_b", hashed_password=hashed_pwd)
    db_session.add(user_b)
    db_session.flush()

    mem_b = InstitutionMembership(
        user_id=user_b.id,
        institution_id=inst_b.id,
        role=ROLE_INSTITUTION_ADMIN,
        is_active=True,
    )
    db_session.add(mem_b)

    app_b = Application(institution_id=inst_b.id, application_type="eoa", academic_year="2026-2027")
    db_session.add(app_b)
    db_session.flush()

    doc_b = Document(application_id=app_b.id, document_type="fire_safety_certificate")
    db_session.add(doc_b)
    db_session.flush()

    ver_b = DocumentVersion(
        document_id=doc_b.id,
        version_number=1,
        storage_key="tenant_b_fire.pdf",
        sha256="222" + "0" * 61,
        media_type="application/pdf",
        byte_size=2048,
    )
    db_session.add(ver_b)
    db_session.flush()

    field_b = ExtractedField(
        document_version_id=ver_b.id,
        field_name="certificate_number",
        raw_text="BETA-NOC-100",
        normalized_value="BETA-NOC-100",
        engine_name="test",
    )
    db_session.add(field_b)
    db_session.commit()

    token_a = create_access_token(
        subject=str(user_a.id),
        extra_claims={"institution_id": inst_a.id, "role": ROLE_INSTITUTION_ADMIN},
    )

    return {
        "headers_a": {"Authorization": f"Bearer {token_a}"},
        "inst_a": inst_a,
        "inst_b": inst_b,
        "app_b": app_b,
        "doc_b": doc_b,
        "ver_b": ver_b,
        "doc_a": doc_a,
    }


def test_user_a_cannot_trigger_verification_on_inst_b(client: TestClient, multi_tenant_data: dict[str, object]):
    headers_a = multi_tenant_data["headers_a"]
    app_b = multi_tenant_data["app_b"]
    doc_b = multi_tenant_data["doc_b"]
    ver_b = multi_tenant_data["ver_b"]

    resp = client.post(
        f"/api/v1/compliance/applications/{app_b.id}/documents/{doc_b.id}/versions/{ver_b.id}/verify",
        headers=headers_a,
        json={"force_simulated": True},
    )
    # Conceals foreign tenant resources with 404 to prevent enumeration probing
    assert resp.status_code in (403, 404)


def test_user_a_cannot_list_verifications_of_inst_b(client: TestClient, multi_tenant_data: dict[str, object]):
    headers_a = multi_tenant_data["headers_a"]
    app_b = multi_tenant_data["app_b"]

    resp = client.get(
        f"/api/v1/compliance/applications/{app_b.id}/verifications",
        headers=headers_a,
    )
    assert resp.status_code in (403, 404)


def test_user_a_cannot_trigger_infrastructure_review_of_inst_b(client: TestClient, multi_tenant_data: dict[str, object]):
    headers_a = multi_tenant_data["headers_a"]
    app_b = multi_tenant_data["app_b"]

    resp = client.post(
        f"/api/v1/compliance/applications/{app_b.id}/infrastructure/review",
        headers=headers_a,
    )
    assert resp.status_code in (403, 404)


def test_user_a_cannot_view_institutional_records_of_inst_b(client: TestClient, multi_tenant_data: dict[str, object]):
    headers_a = multi_tenant_data["headers_a"]
    app_b = multi_tenant_data["app_b"]

    resp = client.get(
        f"/api/v1/compliance/applications/{app_b.id}/institutional-records",
        headers=headers_a,
    )
    assert resp.status_code in (403, 404)


def test_user_a_cannot_correct_fields_of_inst_b(client: TestClient, multi_tenant_data: dict[str, object]):
    headers_a = multi_tenant_data["headers_a"]
    app_b = multi_tenant_data["app_b"]
    doc_b = multi_tenant_data["doc_b"]
    ver_b = multi_tenant_data["ver_b"]

    resp = client.patch(
        f"/api/v1/compliance/applications/{app_b.id}/documents/{doc_b.id}/versions/{ver_b.id}/fields/certificate_number",
        headers=headers_a,
        json={"corrected_value": "ATTACK_VALUE", "rationale": "Unauthorized overwrite"},
    )
    assert resp.status_code in (403, 404)
