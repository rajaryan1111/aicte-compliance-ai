"""Tests for Issuing Authority Verification Service and Adapters."""

from __future__ import annotations

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import Application, Document, DocumentVersion, ExtractedField, Institution
from backend.app.services.issuing_authority_service import IssuingAuthorityService
from backend.app.services.verification_adapter import (
    DigiLockerIssuerAdapter,
    SimulatedDemoIssuerAdapter,
    StateFireSafetyIssuerAdapter,
    UniversityAffiliationIssuerAdapter,
    VerificationRequestPayload,
    list_available_adapters,
)


@pytest.fixture
def db_session():
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


def test_list_available_adapters():
    adapters = list_available_adapters()
    assert len(adapters) >= 4
    names = {a["adapter_name"] for a in adapters}
    assert "digilocker_national_gateway" in names
    assert "state_fire_services_portal" in names
    assert "university_affiliation_portal" in names
    assert "simulated_demo_adapter" in names

    # Simulated demo adapter is explicitly not official
    sim_meta = next(a for a in adapters if a["adapter_name"] == "simulated_demo_adapter")
    assert sim_meta["is_official_source"] is False


def test_digilocker_unconfigured_returns_source_unavailable(monkeypatch):
    monkeypatch.delenv("DIGILOCKER_API_KEY", raising=False)
    monkeypatch.delenv("DIGILOCKER_SANDBOX", raising=False)
    adapter = DigiLockerIssuerAdapter(api_key=None, sandbox_mode=False)

    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="NOC-2024-9988",
        claimed_issuing_authority="State Fire",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "source_unavailable"
    assert res.is_official_source is True
    assert "not configured" in res.failure_reason.lower()


def test_digilocker_sandbox_mode():
    adapter = DigiLockerIssuerAdapter(api_key="mock_key", sandbox_mode=True)

    # With certificate number
    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="DL-NOC-2024-7711",
        claimed_issuing_authority="State Fire",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "verified"
    assert res.returned_attributes["verified_identifier"] == "DL-NOC-2024-7711"

    # Missing certificate number
    payload_no_cert = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number=None,
        claimed_issuing_authority=None,
        issue_date=None,
        expiry_date=None,
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res_no_cert = adapter.verify(payload_no_cert)
    assert res_no_cert.status == "verification_inconclusive"


def test_state_fire_safety_unconfigured(monkeypatch):
    monkeypatch.delenv("STATE_FIRE_PORTAL_URL", raising=False)
    adapter = StateFireSafetyIssuerAdapter(portal_url=None)
    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="NOC-1234",
        claimed_issuing_authority="Fire Dept",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "source_unavailable"


def test_university_affiliation_unconfigured(monkeypatch):
    monkeypatch.delenv("UNIVERSITY_PORTAL_URL", raising=False)
    adapter = UniversityAffiliationIssuerAdapter(api_url=None)
    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="university_affiliation",
        certificate_number="UNIV-AFF-2024-11",
        claimed_issuing_authority="State Tech Univ",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "source_unavailable"


def test_simulated_demo_adapter():
    adapter = SimulatedDemoIssuerAdapter()
    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="DEMO-FS-001",
        claimed_issuing_authority="Fire Dept",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
        simulated=True,
    )
    res = adapter.verify(payload)
    assert res.status == "simulated_demo"
    assert res.is_official_source is False
    assert res.evidence["is_demo"] is True


def test_issuing_authority_service_workflow(db_session: Session):
    # Setup test Institution, Application, Document, DocumentVersion
    inst = Institution(institution_id="INST-TEST-01", display_name="Test College")
    db_session.add(inst)
    db_session.flush()

    app = Application(
        institution_id=inst.id,
        application_type="eoa",
        academic_year="2026-2027",
        status="under_review",
    )
    db_session.add(app)
    db_session.flush()

    doc = Document(application_id=app.id, document_type="fire_safety_certificate")
    db_session.add(doc)
    db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key="test_storage_key.pdf",
        sha256="abc1234567890123456789012345678901234567890123456789012345678901",
        media_type="application/pdf",
        byte_size=1024,
    )
    db_session.add(ver)
    db_session.flush()

    field = ExtractedField(
        document_version_id=ver.id,
        field_name="certificate_number",
        raw_text="NOC-2024-TEST",
        normalized_value="NOC-2024-TEST",
        engine_name="test_engine",
    )
    db_session.add(field)
    db_session.commit()

    # Request verification using simulated demo adapter
    attempt = IssuingAuthorityService.request_verification(
        db_session,
        application_id=app.id,
        document_version_id=ver.id,
        adapter_name="simulated_demonstration_adapter",
        actor_id="test_scrutiny_officer",
        force_simulated=True,
    )

    assert attempt.id is not None
    assert attempt.application_id == app.id
    assert attempt.document_version_id == ver.id
    assert attempt.status == "simulated_demo"
    assert attempt.is_official_source is False

    # List attempts
    attempts = IssuingAuthorityService.list_attempts(db_session, app.id)
    assert len(attempts) == 1
    assert attempts[0].attempt_reference == attempt.attempt_reference


def test_issuing_authority_service_not_found(db_session: Session):
    with pytest.raises(ValueError, match="DocumentVersion 999 not found"):
        IssuingAuthorityService.request_verification(
            db_session,
            application_id=1,
            document_version_id=999,
        )
