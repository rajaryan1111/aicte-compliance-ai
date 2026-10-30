"""Issuing-authority verification adapter interface and implementations.

Implements an honest, auditable external verification framework.
External verifications distinguish between live authorized checks, unconfigured endpoints,
inconclusive results, and simulated demonstrations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import json
import logging
import os
import re
from typing import Any, Literal
from urllib.parse import urlparse

import ipaddress
import socket
import httpx

from backend.app.ocr_adapter import parse_iso_date_candidate

logger = logging.getLogger(__name__)

VerificationStatus = Literal[
    "verified",
    "mismatch_detected",
    "expired",
    "verification_pending",
    "source_unavailable",
    "verification_inconclusive",
    "not_attempted",
    "manual_review_required",
    "simulated_demo",
]


class AuthorityEndpointSecurity:
    """Validates external authority endpoints against TLS, SSRF, and administrator allowlists."""

    DEFAULT_ALLOWED_DOMAINS: tuple[str, ...] = (
        ".gov.in",
        ".nic.in",
        ".ac.in",
        ".digitallocker.gov.in",
    )

    DEFAULT_APPROVED_HOSTS: tuple[str, ...] = (
        "api.digitallocker.gov.in",
        "digitallocker.gov.in",
        "nad.digitallocker.gov.in",
        "nad.gov.in",
        "services.india.gov.in",
        "delhigovt.nic.in",
        "fire.delhigovt.nic.in",
        "fireservice.up.gov.in",
        "delhi.gov.in",
        "aicte-india.org",
    )

    @classmethod
    def get_allowed_domains(cls) -> set[str]:
        domains = set(cls.DEFAULT_ALLOWED_DOMAINS)
        extra = os.getenv("ALLOWED_AUTHORITY_DOMAINS", "")
        for d in extra.split(","):
            clean = d.strip().lower()
            if clean:
                domains.add(clean if clean.startswith(".") else f".{clean}")
        return domains

    @classmethod
    def get_approved_hosts(cls) -> set[str]:
        hosts = set(cls.DEFAULT_APPROVED_HOSTS)
        extra = os.getenv("ALLOWED_AUTHORITY_HOSTS", "")
        for h in extra.split(","):
            clean = h.strip().lower()
            if clean:
                hosts.add(clean)
        return hosts

    @classmethod
    def validate_endpoint_url(
        cls,
        url: str | None,
        allow_insecure_for_test: bool = False,
        skip_dns_check: bool = False,
    ) -> tuple[bool, str | None]:
        """Validate endpoint URL with strict TLS, allowlist, credentials, and anti-SSRF protections."""
        if not url or not isinstance(url, str) or not url.strip():
            return False, "Endpoint URL is empty or not configured."

        clean_url = url.strip()
        try:
            parsed = urlparse(clean_url)
        except Exception as exc:
            return False, f"Malformed endpoint URL: {exc}"

        if not parsed.scheme or not parsed.netloc:
            return False, "Endpoint URL is missing scheme or hostname."

        # Anti-credential embedding check: user:pass@host forbidden
        if parsed.username or parsed.password or ("@" in clean_url.split("/")[2]):
            return False, "Embedded credentials (user:password@host) are strictly forbidden in authority endpoint URLs."

        is_test_env = (
            allow_insecure_for_test
            or os.getenv("ALLOW_INSECURE_AUTHORITY_ENDPOINTS", "false").lower() in ("true", "1")
        )

        if parsed.scheme.lower() != "https" and not is_test_env:
            return False, "Official authority endpoint requires HTTPS (TLS) encryption."

        if parsed.port and parsed.port not in (443, 8443) and not is_test_env:
            return False, f"Non-standard port '{parsed.port}' not permitted for official authority endpoints."

        hostname = parsed.hostname.lower() if parsed.hostname else ""

        # Direct IP literal check against private/reserved ranges
        try:
            ip_obj = ipaddress.ip_address(hostname)
            if (
                ip_obj.is_loopback
                or ip_obj.is_private
                or ip_obj.is_link_local
                or ip_obj.is_reserved
                or ip_obj.is_multicast
                or ip_obj.is_unspecified
            ):
                if not is_test_env:
                    return False, f"Direct access to private or loopback IP address '{hostname}' is blocked by anti-SSRF protections."
        except ValueError:
            pass

        if is_test_env:
            return True, None

        allowed_domains = cls.get_allowed_domains()
        approved_hosts = cls.get_approved_hosts()
        is_allowed = (
            hostname in approved_hosts
            or any(hostname.endswith(domain) or hostname == domain.lstrip(".") for domain in allowed_domains)
        )
        if not is_allowed:
            return False, (
                f"Hostname '{hostname}' is not in the administrator-verified authority allowlist. "
                "Arbitrary endpoints are rejected for safety."
            )

        # Anti-SSRF DNS resolution check against private/loopback/link-local ranges
        if not skip_dns_check:
            try:
                addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
                for entry in addr_info:
                    ip_str = entry[4][0]
                    resolved_ip = ipaddress.ip_address(ip_str)
                    if (
                        resolved_ip.is_loopback
                        or resolved_ip.is_private
                        or resolved_ip.is_link_local
                        or resolved_ip.is_reserved
                        or resolved_ip.is_multicast
                        or resolved_ip.is_unspecified
                    ):
                        return False, f"Endpoint hostname '{hostname}' resolves to restricted IP address '{ip_str}'; blocked by anti-SSRF protections."
            except socket.gaierror:
                pass

        return True, None


@dataclass(frozen=True)
class VerificationRequestPayload:
    application_id: int
    document_version_id: int
    document_category: str
    certificate_number: str | None
    claimed_issuing_authority: str | None
    issue_date: str | None
    expiry_date: str | None
    institution_id: str
    actor_id: str
    simulated: bool = False
    extra_attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VerificationResultPayload:
    adapter_name: str
    source_title: str
    is_official_source: bool
    status: VerificationStatus
    source_reference: str | None
    submitted_attributes: dict[str, Any]
    returned_attributes: dict[str, Any]
    failure_reason: str | None
    evidence: dict[str, Any]
    verified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class IssuingAuthorityAdapter(ABC):
    """Abstract base adapter for official issuing-authority integrations."""

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Stable adapter identifier."""

    @property
    @abstractmethod
    def source_title(self) -> str:
        """Human-readable name of the external authority."""

    @property
    @abstractmethod
    def is_official_source(self) -> bool:
        """True only if this adapter connects to an authorized, officially sanctioned endpoint."""

    @abstractmethod
    def supports_category(self, document_category: str) -> bool:
        """Return True if this adapter can verify the given document category."""

    @abstractmethod
    def verify(self, req: VerificationRequestPayload) -> VerificationResultPayload:
        """Execute verification query against the authority."""


class DigiLockerIssuerAdapter(IssuingAuthorityAdapter):
    """Adapter for DigiLocker National Document Exchange (NAD / State certificates)."""

    adapter_name = "digilocker_national_gateway"
    source_title = "DigiLocker National Document Repository (Ministry of Electronics & IT)"
    is_official_source = True

    def __init__(self, api_key: str | None = None, sandbox_mode: bool = False, base_url: str | None = None) -> None:
        self.api_key = api_key or os.getenv("DIGILOCKER_API_KEY")
        self.sandbox_mode = sandbox_mode or (os.getenv("DIGILOCKER_SANDBOX", "false").lower() == "true")
        self.base_url = base_url or os.getenv("DIGILOCKER_BASE_URL")

    def supports_category(self, document_category: str) -> bool:
        return document_category in (
            "fire_safety_certificate",
            "structural_stability",
            "occupancy_certificate",
            "land_document",
            "nba_accreditation",
        )

    def verify(self, req: VerificationRequestPayload) -> VerificationResultPayload:
        # Preserve privacy: send minimal essential attributes only
        submitted = {
            "certificate_number": req.certificate_number,
            "document_category": req.document_category,
            "institution_id": req.institution_id,
        }

        if not req.certificate_number:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=self.source_title,
                is_official_source=self.is_official_source,
                status="verification_inconclusive",
                source_reference=None,
                submitted_attributes=submitted,
                returned_attributes={},
                failure_reason="Missing certificate reference number in document extraction.",
                evidence={"reason": "missing_query_parameter"},
            )

        clean_num = req.certificate_number.strip().upper()

        # In sandbox or simulated mode: STRICTLY returns simulated_demo (or mismatch_detected) and is_official_source=False
        if self.sandbox_mode or req.simulated:
            if "INVALID" in clean_num or "REJECTED" in clean_num:
                return VerificationResultPayload(
                    adapter_name=self.adapter_name,
                    source_title=f"{self.source_title} (Sandbox Simulation)",
                    is_official_source=False,
                    status="mismatch_detected",
                    source_reference=None,
                    submitted_attributes=submitted,
                    returned_attributes={"record_status": "record_not_found"},
                    failure_reason="Certificate reference number not found in DigiLocker sandbox registry.",
                    evidence={"query_ref": clean_num, "is_demo": True},
                )

            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=f"{self.source_title} (Sandbox Simulation)",
                is_official_source=False,
                status="simulated_demo",
                source_reference="SIMULATED-DL-SANDBOX",
                submitted_attributes=submitted,
                returned_attributes={
                    "record_status": "matched_in_sandbox",
                    "issuer": "DigiLocker Sandbox Test Environment",
                    "verified_identifier": clean_num,
                    "notice": "Simulated sandbox demonstration check; does not constitute official production confirmation.",
                },
                failure_reason=None,
                evidence={"is_demo": True, "sandbox_mode": True, "source": "DigiLocker_Sandbox_Gateway"},
            )

        if not self.api_key or not self.base_url:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=self.source_title,
                is_official_source=self.is_official_source,
                status="source_unavailable",
                source_reference=None,
                submitted_attributes=submitted,
                returned_attributes={},
                failure_reason="DigiLocker National Gateway credentials or base URL not configured on host. Live API connection unavailable.",
                evidence={"integration_state": "unconfigured_endpoint", "authorized": True},
            )

        # Validate endpoint TLS and allowlist security
        is_valid_endpoint, endpoint_err = AuthorityEndpointSecurity.validate_endpoint_url(self.base_url)
        if not is_valid_endpoint:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=self.source_title,
                is_official_source=self.is_official_source,
                status="source_unavailable",
                source_reference=None,
                submitted_attributes=submitted,
                returned_attributes={},
                failure_reason=f"Security check failed: {endpoint_err}",
                evidence={"endpoint": self.base_url, "security_error": endpoint_err},
            )

        try:
            with httpx.Client(timeout=5.0, follow_redirects=False) as client:
                resp = client.post(
                    f"{self.base_url.rstrip('/')}/pull/certificate",
                    json=submitted,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Accept": "application/json",
                        "User-Agent": "AICTE-Compliance-Verification/1.0",
                    },
                )
                if resp.status_code in (301, 302, 303, 307, 308):
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=False,
                        status="source_unavailable",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason=f"DigiLocker gateway attempted unauthorized HTTP redirect ({resp.status_code}); blocked for security.",
                        evidence={"http_status": resp.status_code},
                    )
                if resp.status_code in (401, 403):
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="source_unavailable",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason=f"DigiLocker gateway authentication failed (HTTP {resp.status_code}); credentials rejected.",
                        evidence={"http_status": resp.status_code},
                    )
                if resp.status_code == 404:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="mismatch_detected",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={"record_status": "record_not_found"},
                        failure_reason="Certificate reference number not found in DigiLocker repository.",
                        evidence={"http_status": 404},
                    )
                if resp.status_code != 200:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="source_unavailable",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason=f"DigiLocker gateway returned HTTP {resp.status_code}.",
                        evidence={"http_status": resp.status_code},
                    )
                try:
                    data = resp.json()
                except Exception:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="verification_inconclusive",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason="Invalid non-JSON payload received from DigiLocker gateway.",
                        evidence={},
                    )
                if not isinstance(data, dict):
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="verification_inconclusive",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason="Invalid schema received from DigiLocker gateway.",
                        evidence={},
                    )

                # Validate returned identifier
                returned_id = data.get("certificate_number") or data.get("verified_identifier")
                if returned_id and str(returned_id).strip().upper() != clean_num:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="mismatch_detected",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes=data,
                        failure_reason=f"Returned certificate identifier '{returned_id}' does not match submitted '{clean_num}'.",
                        evidence={"submitted": clean_num, "returned": str(returned_id)},
                    )

                # Validate institution identifier if returned
                ret_inst = data.get("institution_id")
                if ret_inst and str(ret_inst).strip().upper() != req.institution_id.strip().upper():
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="mismatch_detected",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes=data,
                        failure_reason=f"Returned institution '{ret_inst}' conflicts with applicant '{req.institution_id}'.",
                        evidence={"submitted": req.institution_id, "returned": str(ret_inst)},
                    )

                # Validate validity date / expiry if returned
                exp_candidate_str = data.get("valid_until") or data.get("expiry_date")
                if exp_candidate_str:
                    parsed_exp = parse_iso_date_candidate(str(exp_candidate_str))
                    if parsed_exp and parsed_exp < datetime.now(timezone.utc).date():
                        return VerificationResultPayload(
                            adapter_name=self.adapter_name,
                            source_title=self.source_title,
                            is_official_source=self.is_official_source,
                            status="expired",
                            source_reference=None,
                            submitted_attributes=submitted,
                            returned_attributes=data,
                            failure_reason=f"Authority record indicates certificate expired on {parsed_exp.isoformat()}.",
                            evidence={"expiry_date": parsed_exp.isoformat()},
                        )

                record_status = str(data.get("record_status", data.get("status", ""))).lower()
                if record_status in ("verified", "valid", "active", "matched"):
                    raw_ref = data.get("source_reference") or data.get("txn_id") or data.get("reference_number")
                    ref = str(raw_ref).strip() if raw_ref else None
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="verified",
                        source_reference=ref,
                        submitted_attributes=submitted,
                        returned_attributes=data,
                        failure_reason=None,
                        evidence={"http_status": 200, "source": "DigiLocker_Production_Gateway"},
                    )
                else:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="mismatch_detected",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes=data,
                        failure_reason=str(data.get("failure_reason") or "DigiLocker record status indicates mismatch."),
                        evidence={"returned_status": record_status},
                    )
        except httpx.TimeoutException:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=self.source_title,
                is_official_source=self.is_official_source,
                status="source_unavailable",
                source_reference=None,
                submitted_attributes=submitted,
                returned_attributes={},
                failure_reason="Connection to DigiLocker gateway timed out.",
                evidence={"error": "timeout"},
            )
        except Exception as exc:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=self.source_title,
                is_official_source=self.is_official_source,
                status="source_unavailable",
                source_reference=None,
                submitted_attributes=submitted,
                returned_attributes={},
                failure_reason=f"Failed to query DigiLocker gateway: {exc}",
                evidence={"error": str(exc)},
            )


class StateFireSafetyIssuerAdapter(IssuingAuthorityAdapter):
    """Adapter for State Directorate of Fire and Emergency Services."""

    adapter_name = "state_fire_services_portal"
    source_title = "Directorate of Fire and Emergency Services (State Govt)"
    is_official_source = True

    def __init__(self, portal_url: str | None = None) -> None:
        self.portal_url = portal_url or os.getenv("STATE_FIRE_PORTAL_URL")

    def supports_category(self, document_category: str) -> bool:
        return document_category in ("fire_safety_certificate", "fire_noc")

    def verify(self, req: VerificationRequestPayload) -> VerificationResultPayload:
        submitted = {
            "certificate_number": req.certificate_number,
            "expiry_date": req.expiry_date,
        }

        if req.simulated:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=f"{self.source_title} (Simulated)",
                is_official_source=False,
                status="simulated_demo",
                source_reference="SIMULATED-FIRE-DEMO",
                submitted_attributes=submitted,
                returned_attributes={"fire_zone": "Division-1", "clearance": "active", "demo_notice": "Simulated query."},
                failure_reason=None,
                evidence={"is_demo": True},
            )

        if not self.portal_url:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=self.source_title,
                is_official_source=self.is_official_source,
                status="source_unavailable",
                source_reference=None,
                submitted_attributes=submitted,
                returned_attributes={},
                failure_reason="State Fire Safety portal API endpoint not configured.",
                evidence={"state": "unconfigured"},
            )

        if not req.certificate_number:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=self.source_title,
                is_official_source=self.is_official_source,
                status="verification_inconclusive",
                source_reference=None,
                submitted_attributes=submitted,
                returned_attributes={},
                failure_reason="No certificate number extracted to query fire portal.",
                evidence={},
            )

        clean_num = req.certificate_number.strip().upper()

        # Validate endpoint TLS and allowlist security
        is_valid_endpoint, endpoint_err = AuthorityEndpointSecurity.validate_endpoint_url(self.portal_url)
        if not is_valid_endpoint:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=self.source_title,
                is_official_source=self.is_official_source,
                status="source_unavailable",
                source_reference=None,
                submitted_attributes=submitted,
                returned_attributes={},
                failure_reason=f"Security check failed: {endpoint_err}",
                evidence={"endpoint": self.portal_url, "security_error": endpoint_err},
            )

        try:
            with httpx.Client(timeout=5.0, follow_redirects=False) as client:
                resp = client.post(
                    self.portal_url,
                    json=submitted,
                    headers={"Accept": "application/json", "User-Agent": "AICTE-Compliance-Verification/1.0"},
                )
                if resp.status_code in (301, 302, 303, 307, 308):
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=False,
                        status="source_unavailable",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason=f"State Fire Safety portal attempted unauthorized HTTP redirect ({resp.status_code}); blocked for security.",
                        evidence={"http_status": resp.status_code, "portal": self.portal_url},
                    )
                if resp.status_code in (401, 403):
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="source_unavailable",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason=f"State Fire Safety portal authentication failed (HTTP {resp.status_code}); credentials rejected.",
                        evidence={"http_status": resp.status_code, "portal": self.portal_url},
                    )
                if resp.status_code == 404:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="mismatch_detected",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={"record_status": "record_not_found"},
                        failure_reason=f"Fire Safety NOC '{req.certificate_number}' not found on State Fire Safety portal.",
                        evidence={"http_status": 404, "portal": self.portal_url},
                    )
                if resp.status_code >= 500:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="source_unavailable",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason=f"State Fire Safety portal internal server error (HTTP {resp.status_code}).",
                        evidence={"http_status": resp.status_code, "portal": self.portal_url},
                    )
                if resp.status_code != 200:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="source_unavailable",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason=f"State Fire Safety portal returned HTTP {resp.status_code}.",
                        evidence={"http_status": resp.status_code, "portal": self.portal_url},
                    )
                try:
                    data = resp.json()
                except Exception:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="verification_inconclusive",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason="State Fire Safety portal returned invalid non-JSON payload.",
                        evidence={"portal": self.portal_url},
                    )
                if not isinstance(data, dict):
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="verification_inconclusive",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason="State Fire Safety portal response schema invalid.",
                        evidence={"portal": self.portal_url},
                    )

                # Validate certificate identifier if returned
                returned_id = (
                    data.get("certificate_number")
                    or data.get("noc_number")
                    or data.get("reference_number")
                    or data.get("verified_identifier")
                )
                if returned_id and str(returned_id).strip().upper() != clean_num:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="mismatch_detected",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes=data,
                        failure_reason=f"Returned certificate identifier '{returned_id}' does not match submitted '{clean_num}'.",
                        evidence={"submitted": clean_num, "returned": str(returned_id)},
                    )

                # Validate institution identifier if returned
                returned_inst = data.get("institution_id") or data.get("institution_code")
                if req.institution_id and returned_inst and str(returned_inst).strip().upper() != str(req.institution_id).strip().upper():
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="mismatch_detected",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes=data,
                        failure_reason=f"Returned institution identifier '{returned_inst}' does not match submitted '{req.institution_id}'.",
                        evidence={"submitted_institution": str(req.institution_id), "returned_institution": str(returned_inst)},
                    )

                # Validate validity date / expiry if returned
                exp_candidate_str = data.get("valid_until") or data.get("expiry_date")
                if exp_candidate_str:
                    parsed_exp = parse_iso_date_candidate(str(exp_candidate_str))
                    if parsed_exp and parsed_exp < datetime.now(timezone.utc).date():
                        return VerificationResultPayload(
                            adapter_name=self.adapter_name,
                            source_title=self.source_title,
                            is_official_source=self.is_official_source,
                            status="expired",
                            source_reference=None,
                            submitted_attributes=submitted,
                            returned_attributes=data,
                            failure_reason=f"State Fire Safety record indicates certificate expired on {parsed_exp.isoformat()}.",
                            evidence={"expiry_date": parsed_exp.isoformat()},
                        )

                record_status = str(data.get("record_status", data.get("status", ""))).lower()
                if record_status in ("verified", "valid", "active", "matched", "approved"):
                    raw_ref = data.get("source_reference") or data.get("reference_number")
                    ref = str(raw_ref).strip() if raw_ref else None
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="verified",
                        source_reference=ref,
                        submitted_attributes=submitted,
                        returned_attributes=data,
                        failure_reason=None,
                        evidence={"portal": self.portal_url, "http_status": 200},
                    )
                else:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="mismatch_detected",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes=data,
                        failure_reason=str(data.get("failure_reason") or "Record status indicates unverified or expired fire clearance."),
                        evidence={"portal": self.portal_url, "record_status": record_status},
                    )
        except httpx.TimeoutException:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=self.source_title,
                is_official_source=self.is_official_source,
                status="source_unavailable",
                source_reference=None,
                submitted_attributes=submitted,
                returned_attributes={},
                failure_reason="Connection to State Fire Safety portal timed out.",
                evidence={"portal": self.portal_url, "error": "timeout"},
            )
        except Exception as exc:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=self.source_title,
                is_official_source=self.is_official_source,
                status="source_unavailable",
                source_reference=None,
                submitted_attributes=submitted,
                returned_attributes={},
                failure_reason=f"Failed to query State Fire Safety portal: {exc}",
                evidence={"portal": self.portal_url, "error": str(exc)},
            )


class UniversityAffiliationIssuerAdapter(IssuingAuthorityAdapter):
    """Adapter for Affiliating University NOC and Approval Verification."""

    adapter_name = "university_affiliation_portal"
    source_title = "Affiliating State Technical University Portal"
    is_official_source = True

    def __init__(self, api_url: str | None = None) -> None:
        self.api_url = api_url or os.getenv("UNIVERSITY_PORTAL_URL")

    def supports_category(self, document_category: str) -> bool:
        return document_category in ("university_noc", "affiliating_university_approval", "university_affiliation")

    def verify(self, req: VerificationRequestPayload) -> VerificationResultPayload:
        submitted = {"ref_number": req.certificate_number, "institution_id": req.institution_id}

        if req.simulated:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=f"{self.source_title} (Simulated)",
                is_official_source=False,
                status="simulated_demo",
                source_reference="SIMULATED-UNIV-DEMO",
                submitted_attributes=submitted,
                returned_attributes={"affiliation_status": "affiliated_active", "demo_notice": "Simulated query."},
                failure_reason=None,
                evidence={"is_demo": True},
            )

        if not self.api_url:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=self.source_title,
                is_official_source=self.is_official_source,
                status="source_unavailable",
                source_reference=None,
                submitted_attributes=submitted,
                returned_attributes={},
                failure_reason="University portal API not configured for this state jurisdiction.",
                evidence={},
            )

        if not req.certificate_number:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=self.source_title,
                is_official_source=self.is_official_source,
                status="verification_inconclusive",
                source_reference=None,
                submitted_attributes=submitted,
                returned_attributes={},
                failure_reason="No affiliation certificate or NOC number extracted.",
                evidence={},
            )

        clean_num = req.certificate_number.strip().upper()

        # Validate endpoint TLS and allowlist security
        is_valid_endpoint, endpoint_err = AuthorityEndpointSecurity.validate_endpoint_url(self.api_url)
        if not is_valid_endpoint:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=self.source_title,
                is_official_source=self.is_official_source,
                status="source_unavailable",
                source_reference=None,
                submitted_attributes=submitted,
                returned_attributes={},
                failure_reason=f"Security check failed: {endpoint_err}",
                evidence={"endpoint": self.api_url, "security_error": endpoint_err},
            )

        try:
            with httpx.Client(timeout=5.0, follow_redirects=False) as client:
                resp = client.post(
                    self.api_url,
                    json=submitted,
                    headers={"Accept": "application/json", "User-Agent": "AICTE-Compliance-Verification/1.0"},
                )
                if resp.status_code in (301, 302, 303, 307, 308):
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=False,
                        status="source_unavailable",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason=f"University portal attempted unauthorized HTTP redirect ({resp.status_code}); blocked for security.",
                        evidence={"http_status": resp.status_code, "portal": self.api_url},
                    )
                if resp.status_code in (401, 403):
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="source_unavailable",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason=f"University portal authentication failed (HTTP {resp.status_code}); credentials rejected.",
                        evidence={"http_status": resp.status_code, "portal": self.api_url},
                    )
                if resp.status_code == 404:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="mismatch_detected",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={"record_status": "record_not_found"},
                        failure_reason=f"Affiliation reference '{req.certificate_number}' not found on university portal.",
                        evidence={"http_status": 404, "portal": self.api_url},
                    )
                if resp.status_code >= 500:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="source_unavailable",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason=f"University portal internal server error (HTTP {resp.status_code}).",
                        evidence={"http_status": resp.status_code, "portal": self.api_url},
                    )
                if resp.status_code != 200:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="source_unavailable",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason=f"University portal returned HTTP {resp.status_code}.",
                        evidence={"http_status": resp.status_code, "portal": self.api_url},
                    )
                try:
                    data = resp.json()
                except Exception:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="verification_inconclusive",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason="University portal returned invalid non-JSON payload.",
                        evidence={"portal": self.api_url},
                    )
                if not isinstance(data, dict):
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="verification_inconclusive",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes={},
                        failure_reason="University portal response schema invalid.",
                        evidence={"portal": self.api_url},
                    )

                # Validate reference identifier if returned
                returned_id = data.get("reference_number") or data.get("certificate_number") or data.get("ref_number")
                if returned_id and str(returned_id).strip().upper() != clean_num:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="mismatch_detected",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes=data,
                        failure_reason=f"Returned reference identifier '{returned_id}' does not match submitted '{clean_num}'.",
                        evidence={"submitted": clean_num, "returned": str(returned_id)},
                    )

                # Validate institution identifier if returned
                ret_inst = data.get("institution_id")
                if ret_inst and str(ret_inst).strip().upper() != req.institution_id.strip().upper():
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="mismatch_detected",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes=data,
                        failure_reason=f"Returned institution identifier '{ret_inst}' does not match applicant '{req.institution_id}'.",
                        evidence={"submitted": req.institution_id, "returned": str(ret_inst)},
                    )

                record_status = str(data.get("affiliation_status", data.get("record_status", data.get("status", "")))).lower()
                if record_status in ("affiliated_active", "verified", "valid", "approved", "active"):
                    raw_ref = data.get("source_reference") or data.get("reference_number")
                    ref = str(raw_ref).strip() if raw_ref else None
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="verified",
                        source_reference=ref,
                        submitted_attributes=submitted,
                        returned_attributes=data,
                        failure_reason=None,
                        evidence={"portal": self.api_url, "http_status": 200},
                    )
                else:
                    return VerificationResultPayload(
                        adapter_name=self.adapter_name,
                        source_title=self.source_title,
                        is_official_source=self.is_official_source,
                        status="mismatch_detected",
                        source_reference=None,
                        submitted_attributes=submitted,
                        returned_attributes=data,
                        failure_reason=str(data.get("failure_reason") or "Affiliation status is not active or verified."),
                        evidence={"portal": self.api_url, "record_status": record_status},
                    )
        except httpx.TimeoutException:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=self.source_title,
                is_official_source=self.is_official_source,
                status="source_unavailable",
                source_reference=None,
                submitted_attributes=submitted,
                returned_attributes={},
                failure_reason="Connection to University portal timed out.",
                evidence={"portal": self.api_url, "error": "timeout"},
            )
        except Exception as exc:
            return VerificationResultPayload(
                adapter_name=self.adapter_name,
                source_title=self.source_title,
                is_official_source=self.is_official_source,
                status="source_unavailable",
                source_reference=None,
                submitted_attributes=submitted,
                returned_attributes={},
                failure_reason=f"Failed to query University portal: {exc}",
                evidence={"portal": self.api_url, "error": str(exc)},
            )


class SimulatedDemoIssuerAdapter(IssuingAuthorityAdapter):
    """Explicit demonstration adapter for offline hackathon jury review.

    Invariant: Status is always 'simulated_demo' and is_official_source is False.
    It never misleads reviewers into believing a live official query occurred.
    """

    adapter_name = "simulated_demo_adapter"
    source_title = "Synthetic Demonstration Scaffolding (Non-Official)"
    is_official_source = False

    def supports_category(self, document_category: str) -> bool:
        return True

    def verify(self, req: VerificationRequestPayload) -> VerificationResultPayload:
        submitted = {
            "certificate_number": req.certificate_number or "SYNTH-DEMO-CERT",
            "document_category": req.document_category,
            "institution_id": req.institution_id,
        }
        return VerificationResultPayload(
            adapter_name=self.adapter_name,
            source_title=self.source_title,
            is_official_source=False,
            status="simulated_demo",
            source_reference=f"DEMO-REF-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            submitted_attributes=submitted,
            returned_attributes={
                "demo_notice": "Synthesized observation for evaluation demonstration only.",
                "validity": "confirmed_in_synthetic_harness",
            },
            failure_reason=None,
            evidence={"is_demo": True, "notice": "Does not constitute official government confirmation."},
        )


# Global adapter registry
_ADAPTERS: dict[str, IssuingAuthorityAdapter] = {
    DigiLockerIssuerAdapter.adapter_name: DigiLockerIssuerAdapter(),
    StateFireSafetyIssuerAdapter.adapter_name: StateFireSafetyIssuerAdapter(),
    UniversityAffiliationIssuerAdapter.adapter_name: UniversityAffiliationIssuerAdapter(),
    SimulatedDemoIssuerAdapter.adapter_name: SimulatedDemoIssuerAdapter(),
}


def get_adapter(name: str) -> IssuingAuthorityAdapter | None:
    return _ADAPTERS.get(name)


def list_available_adapters() -> list[dict[str, Any]]:
    return [
        {
            "adapter_name": a.adapter_name,
            "source_title": a.source_title,
            "is_official_source": a.is_official_source,
        }
        for a in _ADAPTERS.values()
    ]
