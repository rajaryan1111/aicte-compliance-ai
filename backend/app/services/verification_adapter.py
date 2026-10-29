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
                    source_reference=f"DL-MOCK-{abs(hash(clean_num)) % 100000}",
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
                source_reference=f"DL-SANDBOX-TX-{abs(hash(clean_num)) % 1000000}",
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

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    f"{self.base_url.rstrip('/')}/pull/certificate",
                    json=submitted,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Accept": "application/json",
                        "User-Agent": "AICTE-Compliance-Verification/1.0",
                    },
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
                data = resp.json()
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
                record_status = str(data.get("record_status", data.get("status", ""))).lower()
                if record_status in ("verified", "valid", "active", "matched"):
                    ref = str(data.get("source_reference") or data.get("txn_id") or f"DL-TX-{abs(hash(clean_num)) % 1000000}")
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
                source_reference=f"FIRE-SIM-{abs(hash(req.certificate_number or 'DEMO')) % 100000}",
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

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    self.portal_url,
                    json=submitted,
                    headers={"Accept": "application/json", "User-Agent": "AICTE-Compliance-Verification/1.0"},
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
                record_status = str(data.get("record_status", data.get("status", ""))).lower()
                if record_status in ("verified", "valid", "active", "matched", "approved"):
                    ref = str(data.get("source_reference") or data.get("reference_number") or f"FIRE-STAT-{abs(hash(req.certificate_number)) % 100000}")
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
                source_reference=f"UNIV-SIM-{abs(hash(req.certificate_number or 'DEMO')) % 100000}",
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

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    self.api_url,
                    json=submitted,
                    headers={"Accept": "application/json", "User-Agent": "AICTE-Compliance-Verification/1.0"},
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
                record_status = str(data.get("affiliation_status", data.get("record_status", data.get("status", "")))).lower()
                if record_status in ("affiliated_active", "verified", "valid", "approved", "active"):
                    ref = str(data.get("source_reference") or data.get("reference_number") or "UNIV-REC-2026")
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
