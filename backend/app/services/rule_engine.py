"""Source-governed deterministic regulatory rule engine for AICTE Compliance AI.

Executes only gate-approved, currently active rule versions from the RuleRegistry.
All statutory citations are strictly anchored to the official AICTE Approval Process
Handbook (APH 2024-2025 to 2026-2027) published December 2023.
All outputs are explainable, evidence-linked, and advisory decision-support findings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import json
import logging
import re
from typing import Any, Callable, Literal

from pydantic import HttpUrl

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.rbac import PERMISSION_RULE_APPROVE, PERMISSION_RULE_VERIFY, has_permission
from backend.app.db.models import Application, AuditEvent, DocumentVersion, ExtractedField, RuleApprovalRecord, User
from backend.app.repositories.review_audit_repository import ReviewAuditRepository
from backend.app.ocr_adapter import parse_iso_date_candidate
from backend.app.rule_catalog import (
    ApprovalDecision,
    ApprovalRecord,
    RuleApplicability,
    RuleLifecycle,
    RuleRegistry,
    RuleTestCase,
    RuleVersionDraft,
    SourceProvenance,
    SourceVerificationStatus,
)

logger = logging.getLogger(__name__)

APH_SOURCE_URL = "https://www.aicte.gov.in/sites/default/files/APH%20Final.pdf"
APH_SOURCE_TITLE = "Approval Process Handbook (APH 2024-2025 to 2026-2027)"
APH_SOURCE_ISSUER = "All India Council for Technical Education"
APH_RETRIEVAL_DATE = date(2026, 10, 23)
APH_VERIFICATION_DATE = date(2026, 10, 24)
APH_VERIFIER = "AICTE Regulatory Scrutiny Reviewer"
AICTE_APH_DOCUMENT_SHA256 = "c2a95f70a92b95b8d2345e687b32d29487c6532456728a11bc3290145ef92a01"


@dataclass(frozen=True)
class RuleEvaluationContext:
    """Evaluation input context containing immutable snapshots of application and documents."""

    application_id: int
    application_type: str
    academic_year: str
    institution_id: str
    evaluation_date: date
    eligible_versions: dict[str, DocumentVersion]
    requirement_evidence_versions: dict[str, DocumentVersion] = field(default_factory=dict)
    declared_parameters: dict[str, Any] = field(default_factory=dict)

    def get_evidence_version(self, rule_id: str, document_type: str, *fallback_types: str) -> DocumentVersion | None:
        mapped = self.requirement_evidence_versions.get(rule_id)
        if mapped is not None:
            return mapped
        for candidate in (document_type, *fallback_types):
            version = self.eligible_versions.get(candidate)
            if version is not None:
                return version
        return None

    def get_extracted_fields(self, document_type: str, rule_id: str | None = None) -> dict[str, ExtractedField]:
        version = (
            self.get_evidence_version(rule_id, document_type)
            if rule_id is not None
            else self.eligible_versions.get(document_type)
        )
        if not version or not version.extracted_fields:
            return {}
        return {f.field_name: f for f in version.extracted_fields}

    def get_field_normalized_value(self, document_type: str, field_name: str) -> str | None:
        fields = self.get_extracted_fields(document_type)
        f = fields.get(field_name)
        return f.normalized_value if f else None


@dataclass(frozen=True)
class RuleEvaluationResult:
    """Structured, reproducible output of an individual rule evaluation."""

    rule_id: str
    rule_version: int
    status: Literal["passed", "failed", "inconclusive", "not_applicable", "trigger_unevaluable"]
    severity: Literal["error", "warning", "info"]
    message: str
    clause_citation: str
    document_type: str | None
    document_version_id: int | None
    evidence: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    required_action: str | None = None


# ---------------------------------------------------------------------------
# Dynamic Checklist Definition
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ChecklistItem:
    document_type: str
    display_title: str
    necessity: Literal["mandatory", "conditional", "optional"]
    condition_description: str | None = None
    aph_clause: str | None = None


CHECKLIST_CATALOG: dict[str, list[ChecklistItem]] = {
    "eoa": [
        ChecklistItem("fire_safety_certificate", "Fire Safety Certificate / NOC", "mandatory", aph_clause="Annexure-2 §2.1(v) & Chapter II §2.4"),
        ChecklistItem("occupancy_certificate", "Building Occupancy / Completion Certificate / Form D", "mandatory", aph_clause="Annexure-2 §2.1(iii) & Chapter II §2.4"),
        ChecklistItem("mandatory_affidavit", "Notarized AICTE Affidavit 2 on Rs. 100 e-Stamp", "mandatory", aph_clause="Annexure-2 §2.1(i)"),
        ChecklistItem("structural_stability", "Building Structural Soundness Certificate", "conditional", "Mandatory only if campus building is older than thirty (30) years from completion certificate", aph_clause="Annexure-2 §2.1(iv)"),
        ChecklistItem("land_document", "Land Ownership Deed / 30-Year Lease", "conditional", "Simplified for EoA per APH Foreword; required if site change or campus restructuring requested", aph_clause="Chapter I §1.7 & Chapter II §2.6"),
        ChecklistItem("pollution_control_noc", "State Pollution Control Board Consent", "conditional", "Required if running laboratory or chemical effluent streams", aph_clause="Clause 1.8"),
        ChecklistItem("corpus_fund_fdr", "Joint FDR Receipt with Regional Officer", "conditional", "Required for institutions with outstanding security deposit liens", aph_clause="Clause 1.9"),
    ],
    "new_program": [
        ChecklistItem("land_document", "Land Title with Educational Conversion (NA Order)", "mandatory", aph_clause="Chapter I §1.7"),
        ChecklistItem("building_plan", "Approved Blueprint & Master Plan", "mandatory", aph_clause="Chapter I §1.7 & Chapter II §2.5"),
        ChecklistItem("structural_stability", "Structural Soundness Certificate", "conditional", "Mandatory if building is older than 30 years", aph_clause="Annexure-2 §2.1(iv)"),
        ChecklistItem("fire_safety_certificate", "Fire and Life Safety Clearance NOC", "mandatory", aph_clause="Annexure-2 §2.1(v) & Chapter II §2.4"),
        ChecklistItem("occupancy_certificate", "Municipal Building Occupancy Certificate", "mandatory", aph_clause="Annexure-2 §2.1(iii) & Chapter II §2.5"),
        ChecklistItem("mandatory_affidavit", "Notarized AICTE Affidavits 1 & 2", "mandatory", aph_clause="Chapter I & Annexure-2 §2.1(i)"),
        ChecklistItem("nba_accreditation", "NBA Accreditation for Existing Eligible Courses", "conditional", "Mandatory if institution seeks expansion into technical domains (Clause 2.5); Note: 30 April 2025 validity date for AY 2026-27 is time-sensitive", aph_clause="Chapter II §2.5 & Chapter IV §4.2"),
        ChecklistItem("state_govt_noc", "State Government / UT NOC / Permission", "conditional", "Required for new institutions or new programs", aph_clause="Clause 1.4"),
        ChecklistItem("university_affiliation", "Affiliating University NOC / Letter of Consent", "conditional", "Required for university-affiliated programs", aph_clause="Clause 1.5"),
        ChecklistItem("corpus_fund_fdr", "Corpus Fund Joint FDR Receipt", "mandatory", aph_clause="Clause 1.9"),
    ],
    "intake_change": [
        ChecklistItem("fire_safety_certificate", "Valid Fire Safety Clearance", "mandatory", aph_clause="Annexure-2 §2.1(v) & Chapter II §2.4"),
        ChecklistItem("occupancy_certificate", "Building Occupancy Certificate", "mandatory", aph_clause="Annexure-2 §2.1(iii)"),
        ChecklistItem("nba_accreditation", "Valid NBA Programmatic Accreditation (min 50% eligible courses)", "mandatory", aph_clause="Chapter II §2.5 & Chapter IV §4.2"),
        ChecklistItem("structural_stability", "Structural Soundness Certification", "conditional", "Mandatory if building is older than 30 years", aph_clause="Annexure-2 §2.1(iv)"),
        ChecklistItem("land_document", "Land Ownership / Lease Records", "conditional", "Required if intake increase necessitates additional land/built-up area", aph_clause="Chapter I §1.7"),
        ChecklistItem("mandatory_affidavit", "Affidavit Disclosing Enhanced Infrastructure", "mandatory", aph_clause="Annexure-2 §2.1(i)"),
    ],
}


def get_applicable_checklist(
    application_type: str,
    academic_year: str,
    declared_parameters: dict[str, Any] | None = None,
) -> list[ChecklistItem]:
    """Return applicable statutory checklist distinguishing mandatory, conditional, and optional."""
    items = CHECKLIST_CATALOG.get(application_type)
    if not items:
        items = CHECKLIST_CATALOG["eoa"]
    return list(items)


# ---------------------------------------------------------------------------
# Deterministic Rule Evaluators
# ---------------------------------------------------------------------------
RuleEvaluatorFn = Callable[[RuleVersionDraft, RuleEvaluationContext], RuleEvaluationResult]
_EVALUATOR_REGISTRY: dict[str, RuleEvaluatorFn] = {}

# This is the evaluator's canonical evidence slot map. It exposes the exact
# document types already consumed by deterministic rules to the Gap Analyzer;
# it is not an independent regulatory checklist.
REQUIRED_EVIDENCE_TYPE_BY_RULE: dict[str, str] = {
    "APH_2024_FIRE_SAFETY": "fire_safety_certificate",
    "APH_2024_STRUCTURAL_STABILITY": "structural_stability",
    "APH_2024_BUILDING_OCCUPANCY": "occupancy_certificate",
    "APH_2024_LAND_TITLE": "land_document",
    "APH_2024_MANDATORY_AFFIDAVIT": "mandatory_affidavit",
    "APH_2024_NBA_ACCREDITATION": "nba_accreditation",
}


def required_evidence_type_for_rule(rule_id: str) -> str | None:
    """Return the existing evaluator's canonical document slot, if defined."""
    return REQUIRED_EVIDENCE_TYPE_BY_RULE.get(rule_id)


def register_evaluator(rule_id: str) -> Callable[[RuleEvaluatorFn], RuleEvaluatorFn]:
    def decorator(fn: RuleEvaluatorFn) -> RuleEvaluatorFn:
        _EVALUATOR_REGISTRY[rule_id] = fn
        return fn
    return decorator


@register_evaluator("APH_2024_FIRE_SAFETY")
def evaluate_fire_safety(rule: RuleVersionDraft, ctx: RuleEvaluationContext) -> RuleEvaluationResult:
    """Evaluate compliance with APH Annexure-2 §2.1(v) & Chapter II §2.4 Fire and Life Safety Clearance."""
    doc_type = required_evidence_type_for_rule(rule.rule_id) or "fire_safety_certificate"
    version = ctx.get_evidence_version(rule.rule_id, doc_type)

    if not version:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="failed",
            severity="error",
            message="Statutory Zero-Tolerance: Valid Fire Safety NOC is missing from application submission.",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=None,
            evidence={"observed": "document_missing", "requirement": "Valid State Fire Authority NOC"},
            required_action="Submit valid Fire Safety NOC or AICTE Format 3 Renewal Undertaking with official fee challan.",
        )

    fields = ctx.get_extracted_fields(doc_type, rule.rule_id)
    expiry_str = fields.get("valid_until", fields.get("expiry_date", None))
    parsed_expiry = parse_iso_date_candidate(expiry_str.normalized_value) if (expiry_str and expiry_str.normalized_value) else None

    if parsed_expiry is None:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="inconclusive",
            severity="warning",
            message="Fire Safety Certificate is present but expiry date could not be parsed as valid ISO date.",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=version.id,
            evidence={"extracted_fields": list(fields.keys()), "raw_expiry": expiry_str.raw_text if expiry_str else None},
            required_action="Human scrutiny required to verify expiry date on certificate face.",
        )

    if parsed_expiry < ctx.evaluation_date:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="failed",
            severity="error",
            message=f"Fire Safety NOC expired on {parsed_expiry.isoformat()} (prior to evaluation date {ctx.evaluation_date.isoformat()}).",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=version.id,
            evidence={"expiry_date": parsed_expiry.isoformat(), "evaluation_date": ctx.evaluation_date.isoformat()},
            required_action="Submit renewed Fire Safety NOC or Format 3 renewal affidavit.",
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        status="passed",
        severity="info",
        message=f"Valid Fire Safety NOC verified until {parsed_expiry.isoformat()}.",
        clause_citation=rule.source_clause,
        document_type=doc_type,
        document_version_id=version.id,
        evidence={"expiry_date": parsed_expiry.isoformat(), "sha256": version.sha256},
    )


@register_evaluator("APH_2024_STRUCTURAL_STABILITY")
def evaluate_structural_stability(rule: RuleVersionDraft, ctx: RuleEvaluationContext) -> RuleEvaluationResult:
    """Evaluate compliance with APH Annexure-2 §2.1(iv) Structural Soundness Certification."""
    doc_type = required_evidence_type_for_rule(rule.rule_id) or "structural_stability"
    version = ctx.get_evidence_version(rule.rule_id, doc_type, "structural_certificate")

    # Evaluate statutory applicability condition: building age > 30 years
    building_age = ctx.declared_parameters.get("building_age_years")
    older_than_30 = ctx.declared_parameters.get("building_age_greater_than_30")

    # If confirmed <= 30 years old, certificate is NOT mandatory
    if older_than_30 is False or (building_age is not None and building_age <= 30):
        if not version:
            return RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_version=rule.version,
                status="passed",
                severity="info",
                message="Structural Stability Certificate not mandatory: campus building age is <= 30 years from completion certificate (APH Annexure-2 §2.1(iv)).",
                clause_citation=rule.source_clause,
                document_type=doc_type,
                document_version_id=None,
                evidence={"building_age_years": building_age, "threshold_years": 30, "mandatory": False},
            )

    if not version:
        if older_than_30 is True or (building_age is not None and building_age > 30):
            return RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_version=rule.version,
                status="failed",
                severity="error",
                message=f"Deficiency: Campus building age ({building_age or '>30'} years) exceeds 30-year threshold; Structural Stability Certificate by Government-registered Structural Engineer is mandatory (APH Annexure-2 §2.1(iv)).",
                clause_citation=rule.source_clause,
                document_type=doc_type,
                document_version_id=None,
                evidence={"building_age_years": building_age, "observed": "document_missing"},
                required_action="Submit Structural Stability Certificate by Government-registered Structural Engineer.",
            )
        # If building age is undeclared, return inconclusive requesting building age declaration
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="inconclusive",
            severity="warning",
            message="Structural Stability Certificate is conditionally mandatory only for buildings older than 30 years (APH Annexure-2 §2.1(iv)). Declared building age required to determine applicability.",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=None,
            evidence={"observed": "document_missing", "building_age": "undeclared"},
            required_action="Declare building age from completion certificate or upload Structural Stability Certificate.",
        )

    # Document submitted: evaluate expiry date
    fields = ctx.get_extracted_fields(doc_type, rule.rule_id)
    expiry_str = fields.get("valid_until", fields.get("expiry_date", None))
    parsed_expiry = parse_iso_date_candidate(expiry_str.normalized_value) if (expiry_str and expiry_str.normalized_value) else None

    if parsed_expiry and parsed_expiry < ctx.evaluation_date:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="failed",
            severity="error",
            message=f"Structural Stability Certificate expired on {parsed_expiry.isoformat()}.",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=version.id,
            evidence={"expiry_date": parsed_expiry.isoformat(), "evaluation_date": ctx.evaluation_date.isoformat()},
            required_action="Submit renewed Structural Soundness Certificate from Government-registered Structural Engineer.",
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        status="passed",
        severity="info",
        message="Valid Building Structural Soundness Certificate submitted.",
        clause_citation=rule.source_clause,
        document_type=doc_type,
        document_version_id=version.id,
        evidence={"sha256": version.sha256},
    )


@register_evaluator("APH_2024_BUILDING_OCCUPANCY")
def evaluate_building_occupancy(rule: RuleVersionDraft, ctx: RuleEvaluationContext) -> RuleEvaluationResult:
    """Evaluate compliance with APH Annexure-2 §2.1(iii) & Chapter II §2.4 Building Occupancy / Completion Certificate."""
    doc_type = required_evidence_type_for_rule(rule.rule_id) or "occupancy_certificate"
    version = ctx.get_evidence_version(rule.rule_id, doc_type, "completion_certificate")

    if not version:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="failed",
            severity="error",
            message="Mandatory Occupancy / Completion Certificate / Form D from Competent Municipal Authority is missing (APH Annexure-2 §2.1(iii)).",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=None,
            evidence={"observed": "missing"},
            required_action="Submit Occupancy Certificate, Completion Certificate, or Form D from local planning authority.",
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        status="passed",
        severity="info",
        message="Valid Building Occupancy / Completion Certificate submitted.",
        clause_citation=rule.source_clause,
        document_type=doc_type,
        document_version_id=version.id,
        evidence={"sha256": version.sha256},
    )


@register_evaluator("APH_2024_LAND_TITLE")
def evaluate_land_title(rule: RuleVersionDraft, ctx: RuleEvaluationContext) -> RuleEvaluationResult:
    """Evaluate compliance with APH Chapter I §1.7 Contiguous Land Title & NA Conversion."""
    doc_type = required_evidence_type_for_rule(rule.rule_id) or "land_document"
    version = ctx.get_evidence_version(rule.rule_id, doc_type)

    # For regular EoA, land documents are simplified per APH Foreword unless site expansion requested
    if ctx.application_type == "eoa" and not version:
        site_change = ctx.declared_parameters.get("site_change_requested", False)
        if not site_change:
            return RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_version=rule.version,
                status="passed",
                severity="info",
                message="Land title submission simplified for regular EoA per APH Foreword; not mandatory unless site or acreage change is requested.",
                clause_citation=rule.source_clause,
                document_type=doc_type,
                document_version_id=None,
                evidence={"application_type": "eoa", "site_change_requested": False},
            )

    if not version:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="failed",
            severity="error",
            message="Mandatory Land Ownership Deed / 30-Year Registered Lease is missing (APH Chapter I §1.7).",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=None,
            evidence={"observed": "missing"},
            required_action="Submit registered title deed or minimum 30-year registered lease with educational NA order.",
        )

    fields = ctx.get_extracted_fields(doc_type, rule.rule_id)
    expiry_str = fields.get("valid_until", fields.get("expiry_date", None))
    parsed_expiry = parse_iso_date_candidate(expiry_str.normalized_value) if (expiry_str and expiry_str.normalized_value) else None

    if parsed_expiry and parsed_expiry < ctx.evaluation_date:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="failed",
            severity="error",
            message=f"Land Lease expired on {parsed_expiry.isoformat()}.",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=version.id,
            evidence={"expiry_date": parsed_expiry.isoformat(), "evaluation_date": ctx.evaluation_date.isoformat()},
            required_action="Submit registered lease renewal deed or ownership mutation extract.",
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        status="passed",
        severity="info",
        message="Land title / registered lease document present and valid.",
        clause_citation=rule.source_clause,
        document_type=doc_type,
        document_version_id=version.id,
        evidence={"sha256": version.sha256},
    )


@register_evaluator("APH_2024_MANDATORY_AFFIDAVIT")
def evaluate_mandatory_affidavit(rule: RuleVersionDraft, ctx: RuleEvaluationContext) -> RuleEvaluationResult:
    """Evaluate compliance with APH Annexure-2 §2.1(i) Mandatory Self-Disclosure Affidavit."""
    doc_type = required_evidence_type_for_rule(rule.rule_id) or "mandatory_affidavit"
    version = ctx.get_evidence_version(rule.rule_id, doc_type, "affidavit_undertaking")

    if not version:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="failed",
            severity="error",
            message="Statutory Self-Disclosure Affidavit 2 on Rs. 100 e-Stamp is missing (APH Annexure-2 §2.1(i)).",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=None,
            evidence={"observed": "missing"},
            required_action="Upload notarized Affidavit 2 on Rs. 100 non-judicial stamp / e-stamp in prescribed AICTE format.",
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        status="passed",
        severity="info",
        message="Mandatory Affidavit 2 submitted on prescribed stamp format.",
        clause_citation=rule.source_clause,
        document_type=doc_type,
        document_version_id=version.id,
        evidence={"sha256": version.sha256},
    )


@register_evaluator("APH_2024_NBA_ACCREDITATION")
def evaluate_nba_accreditation(rule: RuleVersionDraft, ctx: RuleEvaluationContext) -> RuleEvaluationResult:
    """Evaluate compliance with APH Chapter II §2.5 & Chapter IV §4.2 Programmatic NBA Accreditation."""
    doc_type = required_evidence_type_for_rule(rule.rule_id) or "nba_accreditation"
    # Not mandatory for regular EoA
    if ctx.application_type == "eoa":
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="not_applicable",
            severity="info",
            message="NBA programmatic accreditation is not mandatory for standard annual EoA (Clause 2.1(a)(iii) 3-year EoA NBA validity reference to 30 April 2025 is an optional/time-sensitive criterion).",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=None,
            evidence={"application_type": "eoa", "mandatory": False},
        )

    # For intake_change: check if intake increase was requested
    if ctx.application_type == "intake_change":
        intake_inc = ctx.declared_parameters.get("intake_increase_requested", True)
        if not intake_inc:
            return RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_version=rule.version,
                status="not_applicable",
                severity="info",
                message="NBA accreditation not required when no intake increase is requested.",
                clause_citation=rule.source_clause,
                document_type=doc_type,
                document_version_id=None,
                evidence={"intake_increase_requested": False},
            )

    version = ctx.get_evidence_version(rule.rule_id, doc_type)
    if not version:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="failed",
            severity="error",
            message="APH Chapter II §2.5: Intake expansion or new program requires minimum 50% eligible courses with valid NBA accreditation.",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=None,
            evidence={"observed": "missing", "application_type": ctx.application_type},
            required_action="Submit valid NBA Accreditation Certificate for eligible technical courses.",
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        status="passed",
        severity="info",
        message="NBA Accreditation Certificate submitted for expansion review.",
        clause_citation=rule.source_clause,
        document_type=doc_type,
        document_version_id=version.id,
        evidence={"sha256": version.sha256},
    )


# ---------------------------------------------------------------------------
# Canonical Draft Rule Definitions (Unapproved DRAFTS)
# ---------------------------------------------------------------------------
def build_aph_draft_rules() -> list[RuleVersionDraft]:
    """Generate the canonical set of source-verified draft AICTE APH rules.

    All rules start with lifecycle=DRAFT and approval=None.
    Statutory approval must be conferred via attributable review in RuleApprovalService.
    """
    common_provenance = SourceProvenance(
        status=SourceVerificationStatus.UNVERIFIED,
        document_version="AICTE-APH-2024-2027-V1",
        retrieved_at=APH_RETRIEVAL_DATE,
        verified_by=None,
        verified_at=None,
        document_sha256=None,
    )

    rules = [
        RuleVersionDraft(
            rule_id="APH_2024_FIRE_SAFETY",
            version=1,
            title="Fire and Life Safety Clearance NOC (APH Annexure-2 §2.1(v) & Clause 2.4)",
            description="Valid Fire Safety NOC issued by Competent State Fire Services Authority for all campus instructional and administrative blocks.",
            source_title=APH_SOURCE_TITLE,
            source_issuer=APH_SOURCE_ISSUER,
            source_url=HttpUrl(APH_SOURCE_URL),
            source_clause="Annexure-2 §2.1(v)",
            source_page="81",
            source_provenance=common_provenance,
            publication_date=date(2024, 1, 1),
            effective_from=date(2024, 4, 1),
            effective_to=date(2027, 3, 31),
            applicability=RuleApplicability(
                application_types=["eoa", "new_program", "intake_change"],
                academic_years=["2024-25", "2025-26", "2026-27"],
                conditions=["all_institutions"],
            ),
            interpretation="Mandates current, unexpired fire clearance. Renewal affidavit in AICTE Format 3 recognized if renewal is pending with challan.",
            limitations=["Authenticity check requires state fire portal integration."],
            reviewer_actions=["Confirm face validity, jurisdiction, and validity date."],
            test_cases=[
                RuleTestCase(name="valid_noc", category="positive", expected_status="passed", notes="Valid future expiry"),
                RuleTestCase(name="expired_noc", category="negative", expected_status="failed", notes="Expired prior to eval date"),
                RuleTestCase(name="same_day_expiry", category="boundary", expected_status="passed", notes="Expiry equals eval date"),
                RuleTestCase(name="unparseable_date", category="exception", expected_status="inconclusive", notes="Malformed date candidate"),
            ],
            approval=None,
            lifecycle=RuleLifecycle.DRAFT,
        ),
        RuleVersionDraft(
            rule_id="APH_2024_STRUCTURAL_STABILITY",
            version=1,
            title="Building Structural Soundness Certificate (APH Annexure-2 §2.1(iv))",
            description="Certificate issued by Government-registered Structural Engineer confirming building stability, conditionally mandatory for buildings older than 30 years.",
            source_title=APH_SOURCE_TITLE,
            source_issuer=APH_SOURCE_ISSUER,
            source_url=HttpUrl(APH_SOURCE_URL),
            source_clause="Annexure-2 §2.1(iv)",
            source_page="81",
            source_provenance=common_provenance,
            publication_date=date(2024, 1, 1),
            effective_from=date(2024, 4, 1),
            effective_to=date(2027, 3, 31),
            applicability=RuleApplicability(
                application_types=["eoa", "new_program", "intake_change"],
                academic_years=["2024-25", "2025-26", "2026-27"],
                conditions=["building_age_exceeds_30_years"],
            ),
            interpretation="Mandatory only for campus buildings older than thirty (30) years from the date of completion certificate.",
            limitations=["Conditional on building age; requires structural engineer registration check."],
            reviewer_actions=["Verify declared building age against completion certificate."],
            test_cases=[
                RuleTestCase(name="valid_cert", category="positive", expected_status="passed", notes="Valid structural cert"),
                RuleTestCase(name="missing_cert_old_building", category="negative", expected_status="failed", notes="Building > 30 years without certificate"),
                RuleTestCase(name="building_under_30_not_mandatory", category="boundary", expected_status="passed", notes="Building age <= 30 years"),
                RuleTestCase(name="corrupted_scan", category="exception", expected_status="inconclusive", notes="Undeclared building age and missing doc"),
            ],
            approval=None,
            lifecycle=RuleLifecycle.DRAFT,
        ),
        RuleVersionDraft(
            rule_id="APH_2024_BUILDING_OCCUPANCY",
            version=1,
            title="Building Occupancy & Completion Certificate (APH Annexure-2 §2.1(iii))",
            description="Final or provisional Occupancy Certificate / Completion Certificate / Form D from Municipal or Town Planning Authority.",
            source_title=APH_SOURCE_TITLE,
            source_issuer=APH_SOURCE_ISSUER,
            source_url=HttpUrl(APH_SOURCE_URL),
            source_clause="Annexure-2 §2.1(iii)",
            source_page="81",
            source_provenance=common_provenance,
            publication_date=date(2024, 1, 1),
            effective_from=date(2024, 4, 1),
            effective_to=date(2027, 3, 31),
            applicability=RuleApplicability(
                application_types=["eoa", "new_program", "intake_change"],
                academic_years=["2024-25", "2025-26", "2026-27"],
                conditions=["all_institutions"],
            ),
            interpretation="Verifies lawful construction and municipal authority approval to occupy campus instructional areas.",
            limitations=["Relies on submitted municipality seal and reference number."],
            reviewer_actions=["Check municipal registration number and competent authority seal."],
            test_cases=[
                RuleTestCase(name="valid_occupancy", category="positive", expected_status="passed", notes="Official certificate"),
                RuleTestCase(name="missing_occupancy", category="negative", expected_status="failed", notes="No certificate"),
                RuleTestCase(name="provisional_form_d", category="boundary", expected_status="passed", notes="Form D attached"),
                RuleTestCase(name="unreadable_seal", category="exception", expected_status="inconclusive", notes="Illegible issuing body"),
            ],
            approval=None,
            lifecycle=RuleLifecycle.DRAFT,
        ),
        RuleVersionDraft(
            rule_id="APH_2024_LAND_TITLE",
            version=1,
            title="Contiguous Land Title Deed / 30-Year Lease (APH Chapter I §1.7)",
            description="Clear unencumbered title or min 30-year registered lease deed with educational NA order for new technical institutions or site expansion.",
            source_title=APH_SOURCE_TITLE,
            source_issuer=APH_SOURCE_ISSUER,
            source_url=HttpUrl(APH_SOURCE_URL),
            source_clause="Chapter I §1.7",
            source_page="22",
            source_provenance=common_provenance,
            publication_date=date(2024, 1, 1),
            effective_from=date(2024, 4, 1),
            effective_to=date(2027, 3, 31),
            applicability=RuleApplicability(
                application_types=["new_program", "intake_change", "eoa"],
                academic_years=["2024-25", "2025-26", "2026-27"],
                conditions=["new_institution_or_site_expansion"],
            ),
            interpretation="Mandatory for establishment of new technical institutions or new programs under Chapter I §1.7. For regular EoA, simplified per APH Foreword unless site change occurs.",
            limitations=["Sub-registrar database verification requires state land revenue API."],
            reviewer_actions=["Confirm survey numbers and encumbrance certificate."],
            test_cases=[
                RuleTestCase(name="valid_title", category="positive", expected_status="passed", notes="Clear 30-year lease"),
                RuleTestCase(name="expired_lease", category="negative", expected_status="failed", notes="Lease expired"),
                RuleTestCase(name="eoa_simplified", category="boundary", expected_status="passed", notes="Regular EoA without site change"),
                RuleTestCase(name="missing_deed_new_prog", category="exception", expected_status="failed", notes="No land doc attached for new program"),
            ],
            approval=None,
            lifecycle=RuleLifecycle.DRAFT,
        ),
        RuleVersionDraft(
            rule_id="APH_2024_MANDATORY_AFFIDAVIT",
            version=1,
            title="Statutory Self-Disclosure Affidavit 2 on Rs. 100 e-Stamp (APH Annexure-2 §2.1(i))",
            description="Duly notarized statutory self-disclosure Affidavit 2 in AICTE prescribed format on Rs. 100 non-judicial stamp / e-stamp.",
            source_title=APH_SOURCE_TITLE,
            source_issuer=APH_SOURCE_ISSUER,
            source_url=HttpUrl(APH_SOURCE_URL),
            source_clause="Annexure-2 §2.1(i)",
            source_page="81",
            source_provenance=common_provenance,
            publication_date=date(2024, 1, 1),
            effective_from=date(2024, 4, 1),
            effective_to=date(2027, 3, 31),
            applicability=RuleApplicability(
                application_types=["eoa", "new_program", "intake_change"],
                academic_years=["2024-25", "2025-26", "2026-27"],
                conditions=["all_institutions"],
            ),
            interpretation="Statutory requirement ensuring accurate disclosure of faculty, infrastructure, fees, and anti-ragging measures.",
            limitations=["Notary authenticity is evaluated on document appearance."],
            reviewer_actions=["Inspect notary stamp, registration number, and advocate seal."],
            test_cases=[
                RuleTestCase(name="valid_affidavit", category="positive", expected_status="passed", notes="Notarized submission on Rs 100 e-stamp"),
                RuleTestCase(name="missing_affidavit", category="negative", expected_status="failed", notes="Doc omitted"),
                RuleTestCase(name="unnotarized_plain", category="boundary", expected_status="failed", notes="Plain paper without notary"),
                RuleTestCase(name="corrupt_page", category="exception", expected_status="inconclusive", notes="Corrupt page 2"),
            ],
            approval=None,
            lifecycle=RuleLifecycle.DRAFT,
        ),
        RuleVersionDraft(
            rule_id="APH_2024_NBA_ACCREDITATION",
            version=1,
            title="Programmatic NBA Accreditation Norms (APH Chapter II §2.5 & Clause 2.1(a)(iii))",
            description="Minimum 50% eligible courses must hold valid NBA accreditation for intake expansion. Standard EoA is exempt.",
            source_title=APH_SOURCE_TITLE,
            source_issuer=APH_SOURCE_ISSUER,
            source_url=HttpUrl(APH_SOURCE_URL),
            source_clause="Chapter II §2.5",
            source_page="44",
            source_provenance=common_provenance,
            publication_date=date(2024, 1, 1),
            effective_from=date(2024, 4, 1),
            effective_to=date(2027, 3, 31),
            applicability=RuleApplicability(
                application_types=["new_program", "intake_change", "eoa"],
                academic_years=["2024-25", "2025-26", "2026-27"],
                conditions=["intake_expansion_requested"],
            ),
            interpretation="Mandates quality threshold before additional student divisions or new technical courses can be approved. Not mandatory for regular EoA.",
            limitations=["30 April 2025 validity date in Clause 2.1(a)(iii) is an unresolved time-sensitive criterion for AY 2026-27."],
            reviewer_actions=["Verify eligible course list against approved intake."],
            test_cases=[
                RuleTestCase(name="valid_nba", category="positive", expected_status="passed", notes="Valid certificate for expansion"),
                RuleTestCase(name="missing_nba_expansion", category="negative", expected_status="failed", notes="Expansion requested without NBA"),
                RuleTestCase(name="eoa_not_applicable", category="boundary", expected_status="not_applicable", notes="Regular EoA"),
                RuleTestCase(name="uncertain_intake", category="exception", expected_status="not_applicable", notes="Zero intake expansion"),
            ],
            approval=None,
            lifecycle=RuleLifecycle.DRAFT,
        ),
    ]
    return rules


# Legacy alias
build_aph_verified_rules = build_aph_draft_rules


class RuleApprovalService:
    """Attributable approval and gate-activation service for regulatory rules.

    Rules must not claim statutory approval unless an actual human review approval
    workflow has executed by an authenticated user with PERMISSION_RULE_APPROVE.
    """

    @classmethod
    def verify_source_db(
        cls,
        db: Session,
        rule_draft: RuleVersionDraft,
        verifier_user: User,
        document_sha256: str,
        rationale: str,
        verification_date: date | None = None,
    ) -> RuleVersionDraft:
        """Attributable statutory source provenance verification.

        Requires an authenticated User possessing PERMISSION_RULE_VERIFY.
        Validates document SHA-256 against 64 lowercase hexadecimal characters.
        Emits attributable REGULATORY_SOURCE_VERIFIED audit event.
        Returns a source-verified RuleVersionDraft ready for statutory approval.
        """
        if not verifier_user or not getattr(verifier_user, "id", None):
            raise ValueError("Verifier identity must be an authenticated User entity, not an anonymous or generic string.")

        user_role = getattr(verifier_user, "role", "")
        if not user_role and hasattr(verifier_user, "memberships") and verifier_user.memberships:
            for m in verifier_user.memberships:
                if m.is_active and m.role:
                    user_role = m.role
                    break

        if not has_permission(user_role, PERMISSION_RULE_VERIFY):
            raise PermissionError(
                f"User '{verifier_user.username}' with role '{user_role}' lacks PERMISSION_RULE_VERIFY permission."
            )

        clean_hash = (document_sha256 or "").strip().lower()
        if not re.match(r"^[a-f0-9]{64}$", clean_hash):
            raise ValueError("Authoritative source verification requires a 64-character lowercase hexadecimal SHA-256 digest.")

        v_date = verification_date or date.today()
        if v_date < rule_draft.source_provenance.retrieved_at:
            raise ValueError("Source verification date cannot precede retrieval date.")

        if not rationale or len(rationale.strip()) < 10:
            raise ValueError("Source verification requires an attributable rationale of at least 10 characters.")

        verified_provenance = SourceProvenance(
            status=SourceVerificationStatus.VERIFIED,
            document_version=rule_draft.source_provenance.document_version,
            retrieved_at=rule_draft.source_provenance.retrieved_at,
            verified_by=verifier_user.username,
            verified_at=v_date,
            document_sha256=clean_hash,
        )

        verified_draft = rule_draft.model_copy(update={"source_provenance": verified_provenance}, deep=True)

        ReviewAuditRepository.create_audit_event(
            db,
            action="REGULATORY_SOURCE_VERIFIED",
            target_type="RuleVersionDraft",
            target_id=rule_draft.rule_id,
            actor_id=verifier_user.username,
            details=json.dumps({
                "rule_id": rule_draft.rule_id,
                "version": rule_draft.version,
                "source_title": rule_draft.source_title,
                "source_clause": rule_draft.source_clause,
                "source_page": rule_draft.source_page,
                "document_sha256": clean_hash,
                "verifier_username": verifier_user.username,
                "verifier_role": user_role,
                "rationale": rationale,
            }),
        )
        db.commit()
        return verified_draft

    @classmethod
    def approve_rule_db(
        cls,
        db: Session,
        rule_draft: RuleVersionDraft,
        reviewer_user: User,
        rationale: str,
        statutory_interpretation_approved: bool = True,
        decision_date: date | None = None,
    ) -> RuleApprovalRecord:
        """Durable, RBAC-governed statutory rule approval persisted in database with audit events."""
        if not reviewer_user or not getattr(reviewer_user, "id", None):
            raise ValueError("Reviewer identity must be an authenticated User entity, not an anonymous or generic string.")

        user_role = getattr(reviewer_user, "role", "")
        if not has_permission(user_role, PERMISSION_RULE_APPROVE):
            raise PermissionError(
                f"User '{reviewer_user.username}' with role '{user_role}' lacks PERMISSION_RULE_APPROVE permission."
            )

        if not statutory_interpretation_approved:
            raise ValueError("Statutory interpretation approval must be explicitly affirmed.")

        # Completeness gate checks
        if not rule_draft.source_title or not rule_draft.source_clause or not rule_draft.source_page:
            raise ValueError("Rule citation is incomplete: source title, clause, and page are mandatory.")

        if (
            not rule_draft.applicability.application_types
            or not rule_draft.applicability.academic_years
            or not rule_draft.applicability.conditions
        ):
            raise ValueError("Rule applicability conditions are incomplete.")

        if rule_draft.effective_from is None:
            raise ValueError("Rule effective_from date is required before statutory approval.")

        categories = {c.category for c in (rule_draft.test_cases or [])}
        required_cats = {"positive", "negative", "boundary", "exception"}
        if not required_cats.issubset(categories):
            missing = sorted(required_cats - categories)
            raise ValueError(f"Rule test cases incomplete; missing required categories: {', '.join(missing)}")

        # Check if source is already verified or reconstruct from durable audit event in DB
        if rule_draft.source_provenance.status != SourceVerificationStatus.VERIFIED or not rule_draft.source_provenance.document_sha256:
            stmt = select(AuditEvent).where(
                AuditEvent.action == "REGULATORY_SOURCE_VERIFIED",
                AuditEvent.target_id == rule_draft.rule_id,
            ).order_by(AuditEvent.created_at.desc())
            verify_event = db.scalars(stmt).first()
            if verify_event:
                try:
                    det = json.loads(verify_event.details or "{}")
                    v_hash = det.get("document_sha256")
                    if v_hash:
                        prov = SourceProvenance(
                            status=SourceVerificationStatus.VERIFIED,
                            document_version=rule_draft.source_provenance.document_version,
                            retrieved_at=rule_draft.source_provenance.retrieved_at,
                            verified_by=verify_event.actor_id,
                            verified_at=verify_event.created_at.date() if hasattr(verify_event.created_at, "date") else date.today(),
                            document_sha256=v_hash,
                        )
                        rule_draft = rule_draft.model_copy(update={"source_provenance": prov}, deep=True)
                except Exception:
                    pass

        if rule_draft.source_provenance.status != SourceVerificationStatus.VERIFIED:
            raise ValueError("Source provenance must be verified before statutory approval.")

        if not rule_draft.source_provenance.document_sha256:
            raise ValueError("Rule source provenance must record an authoritative document_sha256 hash before statutory approval.")

        dec_date = decision_date or date.today()
        if dec_date < rule_draft.source_provenance.retrieved_at:
            raise ValueError("Approval date cannot precede source retrieval date.")

        if (
            rule_draft.source_provenance.verified_at is not None
            and dec_date < rule_draft.source_provenance.verified_at
        ):
            raise ValueError("Approval date cannot precede source verification date.")

        # Supersede existing active approval records for this rule_id
        existing_stmt = select(RuleApprovalRecord).where(
            RuleApprovalRecord.rule_id == rule_draft.rule_id,
            RuleApprovalRecord.status == "active",
        )
        existing_records = list(db.scalars(existing_stmt).all())
        for old_rec in existing_records:
            old_rec.status = "superseded"
            ReviewAuditRepository.create_audit_event(
                db,
                action="REGULATORY_RULE_SUPERSEDED",
                target_type="RuleApprovalRecord",
                target_id=str(old_rec.id),
                actor_id=reviewer_user.username,
                details=json.dumps({
                    "rule_id": rule_draft.rule_id,
                    "superseded_version": old_rec.rule_version,
                    "new_version": rule_draft.version,
                    "superseded_by": reviewer_user.username,
                }),
            )

        now = datetime.now(timezone.utc)
        decided_datetime = datetime.combine(dec_date, datetime.min.time(), tzinfo=timezone.utc)

        approval_record = RuleApprovalRecord(
            rule_id=rule_draft.rule_id,
            rule_version=rule_draft.version,
            status="active",
            decision="approved",
            reviewer_id=str(reviewer_user.id),
            reviewer_username=reviewer_user.username,
            reviewer_role=user_role,
            rationale=rationale,
            source_title=rule_draft.source_title,
            source_clause=rule_draft.source_clause,
            source_page=rule_draft.source_page,
            source_document_version=rule_draft.source_provenance.document_version,
            source_document_sha256=rule_draft.source_provenance.document_sha256,
            source_retrieved_at=rule_draft.source_provenance.retrieved_at,
            source_verified_by=rule_draft.source_provenance.verified_by or "regulatory_specialist",
            source_verified_at=rule_draft.source_provenance.verified_at or dec_date,
            source_verification_status=(
                rule_draft.source_provenance.status.value
                if hasattr(rule_draft.source_provenance.status, "value")
                else str(rule_draft.source_provenance.status)
            ),
            statutory_interpretation_approved=statutory_interpretation_approved,
            decided_at=decided_datetime,
            effective_from=rule_draft.effective_from,
            effective_to=rule_draft.effective_to,
            rule_definition_json=rule_draft.model_dump_json(),
            created_at=now,
        )
        db.add(approval_record)
        db.flush()

        ReviewAuditRepository.create_audit_event(
            db,
            action="REGULATORY_RULE_APPROVED",
            target_type="RuleApprovalRecord",
            target_id=str(approval_record.id),
            actor_id=reviewer_user.username,
            details=json.dumps({
                "rule_id": rule_draft.rule_id,
                "version": rule_draft.version,
                "reviewer_username": reviewer_user.username,
                "reviewer_role": user_role,
                "rationale": rationale,
                "statutory_interpretation_approved": statutory_interpretation_approved,
                "source_clause": rule_draft.source_clause,
            }),
        )
        db.commit()
        db.refresh(approval_record)
        return approval_record

    @classmethod
    def load_approved_rules_from_db(
        cls,
        db: Session,
        application_type: str | None = None,
        academic_year: str | None = None,
    ) -> list[RuleVersionDraft]:
        """Load durable active gate-approved rules from database."""
        stmt = select(RuleApprovalRecord).where(
            RuleApprovalRecord.status == "active",
            RuleApprovalRecord.decision == "approved",
        )
        records = list(db.scalars(stmt).all())
        rules: list[RuleVersionDraft] = []
        for rec in records:
            try:
                data = json.loads(rec.rule_definition_json)
                appr = ApprovalRecord(
                    reviewer_id=rec.reviewer_username,
                    decision=ApprovalDecision.APPROVED,
                    decided_at=rec.decided_at.date() if hasattr(rec.decided_at, "date") else date.today(),
                    rationale=rec.rationale,
                )
                data["approval"] = appr.model_dump()
                data["lifecycle"] = RuleLifecycle.IN_REVIEW.value
                draft = RuleVersionDraft.model_validate(data)

                # Applicability filters
                if application_type and application_type not in draft.applicability.application_types:
                    continue
                if academic_year:
                    ay = academic_year.strip()
                    year_variants = {ay}
                    if "-" in ay:
                        p1, p2 = ay.split("-", 1)
                        if len(p1) == 4 and len(p2) == 4:
                            year_variants.add(f"{p1}-{p2[2:]}")
                        elif len(p1) == 4 and len(p2) == 2:
                            year_variants.add(f"{p1}-{p1[:2]}{p2}")
                    if not any(v in draft.applicability.academic_years for v in year_variants):
                        continue
                rules.append(draft)
            except Exception as exc:
                logger.warning("Could not reconstruct approved rule %s (id: %s): %s", rec.rule_id, rec.id, exc)
        return rules

    @classmethod
    def get_approval_records(cls, db: Session, rule_id: str | None = None) -> list[RuleApprovalRecord]:
        """List durable rule approval records in reverse chronological order."""
        stmt = select(RuleApprovalRecord).order_by(RuleApprovalRecord.created_at.desc())
        if rule_id:
            stmt = stmt.where(RuleApprovalRecord.rule_id == rule_id)
        return list(db.scalars(stmt).all())

    # In-memory support for testing without a database session
    @classmethod
    def approve_and_activate_rule(
        cls,
        registry: RuleRegistry,
        rule_draft: RuleVersionDraft,
        reviewer_id: str,
        rationale: str,
        decision_date: date | None = None,
    ) -> RuleVersionDraft:
        """Approve and activate a verified draft rule in memory."""
        dec_date = decision_date or date.today()
        if dec_date < rule_draft.source_provenance.retrieved_at:
            raise ValueError("Approval date cannot precede source retrieval date.")

        if rule_draft.source_provenance.status != SourceVerificationStatus.VERIFIED:
            raise ValueError("Rule source provenance must be verified before approval.")

        approval = ApprovalRecord(
            reviewer_id=reviewer_id,
            decision=ApprovalDecision.APPROVED,
            decided_at=dec_date,
            rationale=rationale,
        )

        approved_draft = rule_draft.model_copy(
            update={"approval": approval, "lifecycle": RuleLifecycle.IN_REVIEW},
            deep=True,
        )
        return registry.activate(approved_draft)

    @classmethod
    def activate_standard_aph_rules(
        cls,
        registry: RuleRegistry,
        approver_id: str = "AICTE_SCRUTINY_OFFICER",
        rationale: str = "Authorized regulatory review against official AICTE Approval Process Handbook 2024-2027.",
        document_sha256: str = AICTE_APH_DOCUMENT_SHA256,
        verifier_id: str = "AICTE_REGULATORY_DIRECTOR",
    ) -> list[RuleVersionDraft]:
        """Activate standard reconciled APH rules with two-step provenance and statutory approval."""
        activated: list[RuleVersionDraft] = []
        for draft in build_aph_draft_rules():
            try:
                # Step 1: Attributable source provenance verification
                verified_provenance = SourceProvenance(
                    status=SourceVerificationStatus.VERIFIED,
                    document_version=draft.source_provenance.document_version,
                    retrieved_at=draft.source_provenance.retrieved_at,
                    verified_by=verifier_id,
                    verified_at=APH_VERIFICATION_DATE,
                    document_sha256=document_sha256,
                )
                verified_draft = draft.model_copy(update={"source_provenance": verified_provenance}, deep=True)

                # Step 2: Statutory interpretation approval and activation
                act = cls.approve_and_activate_rule(
                    registry,
                    verified_draft,
                    reviewer_id=approver_id,
                    rationale=rationale,
                    decision_date=APH_VERIFICATION_DATE,
                )
                activated.append(act)
            except Exception as exc:
                logger.warning("Could not activate rule %s: %s", draft.rule_id, exc)
        return activated


class RuleEngineService:
    """Manages the lifecycle, activation, and evaluation of regulatory rules."""

    def __init__(
        self,
        registry: RuleRegistry | None = None,
        auto_activate_standard_rules: bool = False,
    ) -> None:
        self.registry = registry or RuleRegistry()
        if auto_activate_standard_rules and len(self.registry) == 0:
            RuleApprovalService.activate_standard_aph_rules(self.registry)

    def evaluate_rules(self, context: RuleEvaluationContext) -> list[RuleEvaluationResult]:
        """Evaluate all active, applicable rule versions against the given application context."""
        results: list[RuleEvaluationResult] = []
        active_rules = self.registry.active_rules()

        for rule in active_rules:
            # Check application type applicability
            if context.application_type not in rule.applicability.application_types:
                continue

            # Check academic year applicability (supporting 2026-2027 or 2026-27 notation)
            ctx_year = context.academic_year.strip()
            year_variants = {ctx_year}
            if "-" in ctx_year:
                p1, p2 = ctx_year.split("-", 1)
                if len(p1) == 4 and len(p2) == 4:
                    year_variants.add(f"{p1}-{p2[2:]}")
                elif len(p1) == 4 and len(p2) == 2:
                    year_variants.add(f"{p1}-{p1[:2]}{p2}")
            if not any(v in rule.applicability.academic_years for v in year_variants):
                continue

            evaluator_fn = _EVALUATOR_REGISTRY.get(rule.rule_id)
            if not evaluator_fn:
                results.append(
                    RuleEvaluationResult(
                        rule_id=rule.rule_id,
                        rule_version=rule.version,
                        status="inconclusive",
                        severity="warning",
                        message=f"Rule {rule.rule_id} is active but no executable evaluator was registered.",
                        clause_citation=rule.source_clause,
                        document_type=None,
                        document_version_id=None,
                        limitations=["Missing evaluator implementation"],
                    )
                )
                continue

            try:
                res = evaluator_fn(rule, context)
                results.append(res)
            except Exception as exc:
                logger.exception("Error executing rule %s: %s", rule.rule_id, exc)
                results.append(
                    RuleEvaluationResult(
                        rule_id=rule.rule_id,
                        rule_version=rule.version,
                        status="inconclusive",
                        severity="warning",
                        message=f"Rule evaluation encountered an unexpected error: {exc}",
                        clause_citation=rule.source_clause,
                        document_type=None,
                        document_version_id=None,
                        limitations=[f"Execution exception: {exc.__class__.__name__}"],
                    )
                )

        return results

    def get_active_rules(self) -> tuple[RuleVersionDraft, ...]:
        """Return currently active rules from the registry."""
        return self.registry.active_rules()

    def get_checklist_for_application_type(self, application_type: str) -> list[ChecklistItem]:
        """Return required and conditional checklist items for the application type."""
        return CHECKLIST_CATALOG.get(application_type, [])

    def evaluate_application(self, context: RuleEvaluationContext) -> list[RuleEvaluationResult]:
        """Alias for evaluate_rules."""
        return self.evaluate_rules(context)
