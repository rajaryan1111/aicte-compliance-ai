"""Tests for hardened issuing-authority endpoint security, anti-SSRF protections, and schema validation."""

from __future__ import annotations

import httpx
import pytest

from backend.app.services.verification_adapter import (
    AuthorityEndpointSecurity,
    DigiLockerIssuerAdapter,
    StateFireSafetyIssuerAdapter,
    UniversityAffiliationIssuerAdapter,
    VerificationRequestPayload,
)


def test_endpoint_security_embedded_credentials_rejected():
    is_valid, err = AuthorityEndpointSecurity.validate_endpoint_url(
        "https://admin:secret@api.digitallocker.gov.in/pull",
        allow_insecure_for_test=False,
    )
    assert is_valid is False
    assert "Embedded credentials" in err


def test_endpoint_security_private_ip_literal_rejected():
    # Direct access to private/link-local IPv4 addresses
    for private_ip in ["127.0.0.1", "169.254.169.254", "10.0.0.1", "192.168.1.1"]:
        is_valid, err = AuthorityEndpointSecurity.validate_endpoint_url(
            f"https://{private_ip}/pull",
            allow_insecure_for_test=False,
        )
        assert is_valid is False
        assert "private or loopback IP address" in err or "anti-SSRF" in err or "allowlist" in err


def test_endpoint_security_non_standard_port_rejected():
    is_valid, err = AuthorityEndpointSecurity.validate_endpoint_url(
        "https://api.digitallocker.gov.in:8080/pull",
        allow_insecure_for_test=False,
    )
    assert is_valid is False
    assert "Non-standard port" in err


def test_endpoint_security_unauthorized_domain_rejected():
    is_valid, err = AuthorityEndpointSecurity.validate_endpoint_url(
        "https://attacker-controlled-site.com/pull",
        allow_insecure_for_test=False,
    )
    assert is_valid is False
    assert "not in the administrator-verified authority allowlist" in err


def test_endpoint_security_authorized_hosts_accepted():
    for host in [
        "https://api.digitallocker.gov.in/pull",
        "https://fire.delhigovt.nic.in/verify",
        "https://nad.gov.in/records",
    ]:
        is_valid, err = AuthorityEndpointSecurity.validate_endpoint_url(
            host,
            allow_insecure_for_test=False,
            skip_dns_check=True,
        )
        assert is_valid is True, f"Failed for {host}: {err}"


def test_adapter_redirect_blocked_as_source_unavailable(monkeypatch):
    adapter = DigiLockerIssuerAdapter(
        api_key="valid_key",
        sandbox_mode=False,
        base_url="https://api.digitallocker.gov.in",
    )

    class RedirectResponse:
        status_code = 302
        headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        def json(self):
            return {}

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: RedirectResponse())

    req = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="NOC-2024-TEST",
        claimed_issuing_authority="State Fire",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(req)
    assert res.status == "source_unavailable"
    assert res.is_official_source is False
    assert "unauthorized HTTP redirect" in res.failure_reason


def test_state_fire_redirect_blocked(monkeypatch):
    adapter = StateFireSafetyIssuerAdapter(portal_url="https://fire.delhigovt.nic.in/verify")

    class RedirectResponse:
        status_code = 301
        headers = {"Location": "http://internal-service.local/"}
        def json(self):
            return {}

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: RedirectResponse())

    req = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="fire_safety_certificate",
        certificate_number="NOC-2024-7788",
        claimed_issuing_authority="Delhi Fire",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(req)
    assert res.status == "source_unavailable"
    assert "redirect" in res.failure_reason.lower()


def test_university_redirect_blocked(monkeypatch):
    adapter = UniversityAffiliationIssuerAdapter(api_url="https://delhi.gov.in/affiliation")

    class RedirectResponse:
        status_code = 307
        def json(self):
            return {}

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: RedirectResponse())

    req = VerificationRequestPayload(
        application_id=1,
        document_version_id=10,
        document_category="university_noc",
        certificate_number="UNIV-2024-11",
        claimed_issuing_authority="State Univ",
        issue_date="2024-01-01",
        expiry_date="2027-01-01",
        institution_id="INST-001",
        actor_id="officer_1",
    )
    res = adapter.verify(req)
    assert res.status == "source_unavailable"
    assert "redirect" in res.failure_reason.lower()

