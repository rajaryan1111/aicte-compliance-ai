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

    # In sandbox mode, successful matches must be reported as simulated_demo, NOT verified
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
    assert res.status == "simulated_demo"
    assert res.is_official_source is False
    assert res.returned_attributes["verified_identifier"] == "DL-NOC-2024-7711"

    # In sandbox mode, invalid patterns return mismatch_detected with is_official_source=False
    payload_inv = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="INVALID-REF-999",
        claimed_issuing_authority="State Fire",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res_inv = adapter.verify(payload_inv)
    assert res_inv.status == "mismatch_detected"
    assert res_inv.is_official_source is False

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


def test_digilocker_live_http_verified(monkeypatch):
    import httpx
    adapter = DigiLockerIssuerAdapter(api_key="live_key", sandbox_mode=False, base_url="https://api.digitallocker.gov.in/public")

    class MockResponse:
        status_code = 200
        def json(self):
            return {"record_status": "verified", "issuer": "State Govt", "txn_id": "DL-123456"}

    def mock_post(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="NOC-2024-8899",
        claimed_issuing_authority="State Fire",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "verified"
    assert res.is_official_source is True
    assert res.source_reference == "DL-123456"


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
    assert res.is_official_source is True


def test_state_fire_safety_live_http_verified(monkeypatch):
    import httpx
    adapter = StateFireSafetyIssuerAdapter(portal_url="https://fire.state.gov.in/api/verify")

    class MockResponse:
        status_code = 200
        def json(self):
            return {"record_status": "valid", "fire_zone": "Division-1", "reference_number": "FS-NOC-7788"}

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: MockResponse())

    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="FS-NOC-7788",
        claimed_issuing_authority="Fire Dept",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "verified"
    assert res.is_official_source is True
    assert res.source_reference == "FS-NOC-7788"


def test_state_fire_safety_live_http_not_found(monkeypatch):
    import httpx
    adapter = StateFireSafetyIssuerAdapter(portal_url="https://fire.state.gov.in/api/verify")

    class MockResponse:
        status_code = 404
        def json(self):
            return {"record_status": "record_not_found"}

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: MockResponse())

    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="FS-NOC-UNKNOWN",
        claimed_issuing_authority="Fire Dept",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "mismatch_detected"
    assert "not found" in res.failure_reason.lower()


def test_state_fire_safety_live_http_timeout(monkeypatch):
    import httpx
    adapter = StateFireSafetyIssuerAdapter(portal_url="https://fire.state.gov.in/api/verify")

    def mock_timeout(*a, **kw):
        raise httpx.TimeoutException("Connection timed out")

    monkeypatch.setattr(httpx.Client, "post", mock_timeout)

    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="FS-NOC-TIMEOUT",
        claimed_issuing_authority="Fire Dept",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "source_unavailable"
    assert "timed out" in res.failure_reason.lower()


def test_state_fire_safety_live_http_invalid_schema(monkeypatch):
    import httpx
    adapter = StateFireSafetyIssuerAdapter(portal_url="https://fire.state.gov.in/api/verify")

    class MockResponse:
        status_code = 200
        def json(self):
            return "not-a-dict"

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: MockResponse())

    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="FS-NOC-99",
        claimed_issuing_authority="Fire Dept",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "verification_inconclusive"
    assert "invalid non-json" in res.failure_reason.lower() or "schema invalid" in res.failure_reason.lower()


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


def test_university_affiliation_live_http_verified(monkeypatch):
    import httpx
    adapter = UniversityAffiliationIssuerAdapter(api_url="https://univ.state.gov.in/api/affiliations")

    class MockResponse:
        status_code = 200
        def json(self):
            return {"affiliation_status": "affiliated_active", "reference_number": "UNIV-REC-900"}

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: MockResponse())

    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="university_affiliation",
        certificate_number="UNIV-REC-900",
        claimed_issuing_authority="State Tech Univ",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "verified"
    assert res.is_official_source is True
    assert res.source_reference == "UNIV-REC-900"


def test_university_affiliation_live_http_mismatch(monkeypatch):
    import httpx
    adapter = UniversityAffiliationIssuerAdapter(api_url="https://univ.state.gov.in/api/affiliations")

    class MockResponse:
        status_code = 200
        def json(self):
            return {"affiliation_status": "disaffiliated", "failure_reason": "Affiliation revoked"}

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: MockResponse())

    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="university_affiliation",
        certificate_number="UNIV-REVOKED-1",
        claimed_issuing_authority="State Tech Univ",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "mismatch_detected"
    assert "revoked" in res.failure_reason.lower()


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


def test_state_fire_safety_live_http_expired(monkeypatch):
    import httpx
    adapter = StateFireSafetyIssuerAdapter(portal_url="https://fire.state.gov.in/api/verify")

    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "record_status": "expired",
                "reference_number": "FS-NOC-EXPIRED",
                "valid_until": "2020-01-01",
            }

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: MockResponse())

    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="FS-NOC-EXPIRED",
        claimed_issuing_authority="Fire Dept",
        issue_date="2018-01-01",
        expiry_date="2020-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "expired"
    assert res.is_official_source is True
    assert "expired" in res.failure_reason.lower()


def test_state_fire_safety_live_http_identifier_mismatch(monkeypatch):
    import httpx
    adapter = StateFireSafetyIssuerAdapter(portal_url="https://fire.state.gov.in/api/verify")

    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "record_status": "valid",
                "reference_number": "FS-NOC-9999",  # Different from FS-NOC-1111
                "valid_until": "2028-01-01",
            }

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: MockResponse())

    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="FS-NOC-1111",
        claimed_issuing_authority="Fire Dept",
        issue_date="2024-01-01",
        expiry_date="2028-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "mismatch_detected"
    assert "does not match" in res.failure_reason.lower()


def test_state_fire_safety_live_http_institution_mismatch(monkeypatch):
    import httpx
    adapter = StateFireSafetyIssuerAdapter(portal_url="https://fire.state.gov.in/api/verify")

    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "record_status": "valid",
                "reference_number": "FS-NOC-1111",
                "institution_id": "INST-DIFFERENT-COLLEGE",
                "valid_until": "2028-01-01",
            }

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: MockResponse())

    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="FS-NOC-1111",
        claimed_issuing_authority="Fire Dept",
        issue_date="2024-01-01",
        expiry_date="2028-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "mismatch_detected"
    assert "does not match" in res.failure_reason.lower()


def test_state_fire_safety_live_http_non_json_response(monkeypatch):
    import httpx
    adapter = StateFireSafetyIssuerAdapter(portal_url="https://fire.state.gov.in/api/verify")

    class MockResponse:
        status_code = 200
        text = "<html><body>502 Bad Gateway - HTML error page</body></html>"
        def json(self):
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: MockResponse())

    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="FS-NOC-HTML",
        claimed_issuing_authority="Fire Dept",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "verification_inconclusive"
    assert "invalid non-json" in res.failure_reason.lower() or "schema invalid" in res.failure_reason.lower()


def test_state_fire_safety_live_http_unauthorized_401(monkeypatch):
    import httpx
    adapter = StateFireSafetyIssuerAdapter(portal_url="https://fire.state.gov.in/api/verify")

    class MockResponse:
        status_code = 401
        def json(self):
            return {"error": "Unauthorized API credentials"}

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: MockResponse())

    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="FS-NOC-401",
        claimed_issuing_authority="Fire Dept",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "source_unavailable"
    assert "unauthorized" in res.failure_reason.lower() or "authentication failed" in res.failure_reason.lower()


def test_state_fire_safety_live_http_server_error_500(monkeypatch):
    import httpx
    adapter = StateFireSafetyIssuerAdapter(portal_url="https://fire.state.gov.in/api/verify")

    class MockResponse:
        status_code = 500
        def json(self):
            return {"error": "Internal database connection failure"}

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: MockResponse())

    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="FS-NOC-500",
        claimed_issuing_authority="Fire Dept",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(payload)
    assert res.status == "source_unavailable"
    assert "server error" in res.failure_reason.lower()


def test_state_fire_safety_disallowed_domain_and_non_tls():
    # Insecure HTTP
    adapter_http = StateFireSafetyIssuerAdapter(portal_url="http://fire.state.gov.in/api/verify")
    payload = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="FS-NOC-HTTP",
        claimed_issuing_authority="Fire Dept",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res_http = adapter_http.verify(payload)
    assert res_http.status == "source_unavailable"
    assert "security check failed" in res_http.failure_reason.lower()

    # Disallowed external domain
    adapter_disallowed = StateFireSafetyIssuerAdapter(portal_url="https://phishing-fire-records.com/api/verify")
    res_disallowed = adapter_disallowed.verify(payload)
    assert res_disallowed.status == "source_unavailable"
    assert "security check failed" in res_disallowed.failure_reason.lower()
