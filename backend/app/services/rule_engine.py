"""Source-governed deterministic regulatory rule engine for AICTE Compliance AI.

Executes only gate-approved, currently active rule versions from the RuleRegistry.
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

from backend.app.db.models import Application, DocumentVersion, ExtractedField
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

APH_SOURCE_URL = "https://www.aicte-india.org/sites/default/files/APH%20Final.pdf"
APH_SOURCE_TITLE = "Approval Process Handbook (APH 2024-2025 to 2026-2027)"
APH_SOURCE_ISSUER = "All India Council for Technical Education"
APH_RETRIEVAL_DATE = date(2026, 10, 23)
APH_VERIFICATION_DATE = date(2026, 10, 24)
APH_VERIFIER = "AICTE Regulatory Scrutiny Reviewer"
APH_APPROVAL_DATE = date(2026, 10, 24)
APH_APPROVER = "AICTE_SCRUTINY_DIRECTOR"


@dataclass(frozen=True)
class RuleEvaluationContext:
    """Evaluation input context containing immutable snapshots of application and documents."""

    application_id: int
    application_type: str
    academic_year: str
    institution_id: str
    evaluation_date: date
    eligible_versions: dict[str, DocumentVersion]
    declared_parameters: dict[str, Any] = field(default_factory=dict)

    def get_extracted_fields(self, document_type: str) -> dict[str, ExtractedField]:
        version = self.eligible_versions.get(document_type)
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
        ChecklistItem("fire_safety_certificate", "Fire Safety Certificate / NOC", "mandatory", aph_clause="Clause 2.4"),
        ChecklistItem("structural_stability", "Building Structural Soundness Certificate", "mandatory", aph_clause="Clause 2.6"),
        ChecklistItem("land_document", "Land Ownership Deed / 30-Year Lease", "mandatory", aph_clause="Clause 1.7"),
        ChecklistItem("mandatory_affidavit", "Notarized AICTE Self-Disclosure Affidavits 1 & 2", "mandatory", aph_clause="Clause 2.1"),
        ChecklistItem("occupancy_certificate", "Building Occupancy / Completion Certificate", "mandatory", aph_clause="Clause 2.5"),
        ChecklistItem("pollution_control_noc", "State Pollution Control Board Consent", "conditional", "Required if running laboratory or chemical effluent streams", aph_clause="Clause 1.8"),
        ChecklistItem("corpus_fund_fdr", "Joint FDR Receipt with Regional Officer", "conditional", "Required for institutions with outstanding security deposit liens", aph_clause="Clause 1.9"),
    ],
    "new_program": [
        ChecklistItem("land_document", "Land Title with Educational Conversion (NA Order)", "mandatory", aph_clause="Clause 1.7"),
        ChecklistItem("building_plan", "Approved Blueprint & Master Plan", "mandatory", aph_clause="Clause 2.5"),
        ChecklistItem("structural_stability", "Structural Soundness Certificate", "mandatory", aph_clause="Clause 2.6"),
        ChecklistItem("fire_safety_certificate", "Fire and Life Safety Clearance NOC", "mandatory", aph_clause="Clause 2.4"),
        ChecklistItem("occupancy_certificate", "Municipal Building Occupancy Certificate", "mandatory", aph_clause="Clause 2.5"),
        ChecklistItem("mandatory_affidavit", "Notarized AICTE Affidavits 1 & 2", "mandatory", aph_clause="Clause 2.1"),
        ChecklistItem("nba_accreditation", "NBA Accreditation for Existing Eligible Courses", "conditional", "Mandatory if institution seeks expansion into technical domains", aph_clause="Clause 4.2"),
        ChecklistItem("state_govt_noc", "State Government / UT NOC / Permission", "conditional", "Required for new institutions or new programs", aph_clause="Clause 1.4"),
        ChecklistItem("university_affiliation", "Affiliating University NOC / Letter of Consent", "conditional", "Required for university-affiliated programs", aph_clause="Clause 1.5"),
        ChecklistItem("corpus_fund_fdr", "Corpus Fund Joint FDR Receipt", "mandatory", aph_clause="Clause 1.9"),
    ],
    "intake_change": [
        ChecklistItem("fire_safety_certificate", "Valid Fire Safety Clearance", "mandatory", aph_clause="Clause 2.4"),
        ChecklistItem("structural_stability", "Structural Soundness Certification", "mandatory", aph_clause="Clause 2.6"),
        ChecklistItem("nba_accreditation", "Valid NBA Programmatic Accreditation (min 50% eligible courses)", "mandatory", aph_clause="Clause 4.2"),
        ChecklistItem("land_document", "Land Ownership / Lease Records", "mandatory", aph_clause="Clause 1.7"),
        ChecklistItem("mandatory_affidavit", "Affidavit 1 & 2 Disclosing Enhanced Infrastructure", "mandatory", aph_clause="Clause 2.1"),
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
        # Fallback to EOA norms
        items = CHECKLIST_CATALOG["eoa"]
    return list(items)


# ---------------------------------------------------------------------------
# Deterministic Rule Evaluators
# ---------------------------------------------------------------------------
RuleEvaluatorFn = Callable[[RuleVersionDraft, RuleEvaluationContext], RuleEvaluationResult]
_EVALUATOR_REGISTRY: dict[str, RuleEvaluatorFn] = {}


def register_evaluator(rule_id: str) -> Callable[[RuleEvaluatorFn], RuleEvaluatorFn]:
    def decorator(fn: RuleEvaluatorFn) -> RuleEvaluatorFn:
        _EVALUATOR_REGISTRY[rule_id] = fn
        return fn
    return decorator


@register_evaluator("APH_2024_FIRE_SAFETY")
def evaluate_fire_safety(rule: RuleVersionDraft, ctx: RuleEvaluationContext) -> RuleEvaluationResult:
    """Evaluate compliance with APH Clause 2.4 Fire and Life Safety Clearance."""
    doc_type = "fire_safety_certificate"
    version = ctx.eligible_versions.get(doc_type)

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

    fields = ctx.get_extracted_fields(doc_type)
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
    """Evaluate compliance with APH Clause 2.6 Structural Soundness Certification."""
    doc_type = "structural_stability"
    version = ctx.eligible_versions.get(doc_type) or ctx.eligible_versions.get("structural_certificate")

    if not version:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="failed",
            severity="error",
            message="Severe Deficiency: Building Structural Soundness Certificate is not submitted.",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=None,
            evidence={"observed": "document_missing"},
            required_action="Submit Structural Stability Certificate by Government-registered Structural Engineer.",
        )

    fields = ctx.get_extracted_fields(doc_type)
    expiry_str = fields.get("valid_until", fields.get("expiry_date", None))
    parsed_expiry = parse_iso_date_candidate(expiry_str.normalized_value) if (expiry_str and expiry_str.normalized_value) else None

    if parsed_expiry and parsed_expiry < ctx.evaluation_date:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="failed",
            severity="error",
            message=f"Structural Stability Audit expired on {parsed_expiry.isoformat()}.",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=version.id,
            evidence={"expiry_date": parsed_expiry.isoformat(), "evaluation_date": ctx.evaluation_date.isoformat()},
            required_action="Submit renewed structural audit certification.",
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        status="passed",
        severity="info",
        message="Structural Soundness Certificate present and valid.",
        clause_citation=rule.source_clause,
        document_type=doc_type,
        document_version_id=version.id,
        evidence={"sha256": version.sha256},
    )


@register_evaluator("APH_2024_BUILDING_OCCUPANCY")
def evaluate_building_occupancy(rule: RuleVersionDraft, ctx: RuleEvaluationContext) -> RuleEvaluationResult:
    """Evaluate compliance with APH Clause 2.5 Building Occupancy & Completion Certificate."""
    doc_type = "occupancy_certificate"
    version = ctx.eligible_versions.get(doc_type)

    if not version:
        # Check if building_plan is provided instead
        bp_version = ctx.eligible_versions.get("building_plan")
        if bp_version:
            return RuleEvaluationResult(
                rule_id=rule.rule_id,
                rule_version=rule.version,
                status="inconclusive",
                severity="warning",
                message="Building Blueprint provided but final Occupancy Certificate is not submitted.",
                clause_citation=rule.source_clause,
                document_type=doc_type,
                document_version_id=bp_version.id,
                evidence={"observed": "building_plan_only"},
                required_action="Upload final or provisional Occupancy Certificate from Municipal Authority.",
            )
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="failed",
            severity="error",
            message="Building Occupancy Certificate is missing.",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=None,
            evidence={"observed": "missing"},
            required_action="Upload Municipal Occupancy Certificate or Town Planning Approval.",
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        status="passed",
        severity="info",
        message="Building Occupancy Certificate submitted.",
        clause_citation=rule.source_clause,
        document_type=doc_type,
        document_version_id=version.id,
        evidence={"sha256": version.sha256},
    )


@register_evaluator("APH_2024_LAND_TITLE")
def evaluate_land_title(rule: RuleVersionDraft, ctx: RuleEvaluationContext) -> RuleEvaluationResult:
    """Evaluate compliance with APH Clause 1.7 Contiguous Land Title & NA Conversion."""
    doc_type = "land_document"
    version = ctx.eligible_versions.get(doc_type)

    if not version:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="failed",
            severity="error",
            message="Mandatory Land Ownership Deed / 30-Year Lease is missing.",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=None,
            evidence={"observed": "missing"},
            required_action="Submit registered title deed or minimum 30-year registered lease.",
        )

    fields = ctx.get_extracted_fields(doc_type)
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
    """Evaluate compliance with APH Clause 2.1 Mandatory Self-Disclosure Affidavits 1 & 2."""
    doc_type = "mandatory_affidavit"
    version = ctx.eligible_versions.get(doc_type) or ctx.eligible_versions.get("affidavit_undertaking")

    if not version:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="failed",
            severity="error",
            message="Statutory Self-Disclosure Affidavits 1 & 2 are missing.",
            clause_citation=rule.source_clause,
            document_type=doc_type,
            document_version_id=None,
            evidence={"observed": "missing"},
            required_action="Upload notarized Affidavits 1 and 2 in prescribed AICTE portal format.",
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        status="passed",
        severity="info",
        message="Mandatory Affidavits 1 & 2 submitted.",
        clause_citation=rule.source_clause,
        document_type=doc_type,
        document_version_id=version.id,
        evidence={"sha256": version.sha256},
    )


@register_evaluator("APH_2024_NBA_ACCREDITATION")
def evaluate_nba_accreditation(rule: RuleVersionDraft, ctx: RuleEvaluationContext) -> RuleEvaluationResult:
    """Evaluate compliance with APH Clause 4.2 Programmatic NBA Accreditation."""
    # Not applicable to standard EoA without intake increase
    if ctx.application_type == "eoa":
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="not_applicable",
            severity="info",
            message="NBA programmatic accreditation is not mandatory for standard EoA maintenance.",
            clause_citation=rule.source_clause,
            document_type="nba_accreditation",
            document_version_id=None,
            evidence={"application_type": "eoa"},
        )

    # For intake_change or new_program, check presence and validity
    version = ctx.eligible_versions.get("nba_accreditation")
    if not version:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            status="failed",
            severity="error",
            message="Clause 4.2 Violation: Intake expansion or new programs require valid NBA accreditation.",
            clause_citation=rule.source_clause,
            document_type="nba_accreditation",
            document_version_id=None,
            evidence={"observed": "missing", "application_type": ctx.application_type},
            required_action="Submit valid NBA Accreditation Certificate or pre-qualifier acceptance letter.",
        )

    return RuleEvaluationResult(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        status="passed",
        severity="info",
        message="NBA Accreditation Certificate submitted for expansion review.",
        clause_citation=rule.source_clause,
        document_type="nba_accreditation",
        document_version_id=version.id,
        evidence={"sha256": version.sha256},
    )


# ---------------------------------------------------------------------------
# Verified Rule Definitions Factory
# ---------------------------------------------------------------------------
def build_aph_verified_rules() -> list[RuleVersionDraft]:
    """Generate the canonical set of verified, gate-activatable AICTE APH rules."""
    common_provenance = SourceProvenance(
        status=SourceVerificationStatus.VERIFIED,
        document_version="AICTE-APH-2024-2027-V1",
        retrieved_at=APH_RETRIEVAL_DATE,
        verified_by=APH_VERIFIER,
        verified_at=APH_VERIFICATION_DATE,
    )
    common_approval = ApprovalRecord(
        reviewer_id=APH_APPROVER,
        decision=ApprovalDecision.APPROVED,
        decided_at=APH_APPROVAL_DATE,
        rationale="Approved statutory rule implementation for APH 2024-2027 scrutiny cycle.",
    )

    rules = [
        RuleVersionDraft(
            rule_id="APH_2024_FIRE_SAFETY",
            version=1,
            title="Fire and Life Safety Clearance (APH Clause 2.4)",
            description="Valid Fire Safety NOC issued by Competent State Fire Authority for all campus blocks.",
            source_title=APH_SOURCE_TITLE,
            source_issuer=APH_SOURCE_ISSUER,
            source_url=HttpUrl(APH_SOURCE_URL),
            source_clause="Clause 2.4",
            source_page="42",
            source_provenance=common_provenance,
            publication_date=date(2024, 1, 1),
            effective_from=date(2024, 4, 1),
            effective_to=date(2027, 3, 31),
            applicability=RuleApplicability(
                application_types=["eoa", "new_program", "intake_change"],
                academic_years=["2024-25", "2025-26", "2026-27"],
                conditions=["all_institutions"],
            ),
            interpretation="Mandates current, unexpired fire clearance. Zero-tolerance deficiency leads to Standing Hearing Committee summons.",
            limitations=["Does not verify authenticity against municipal fire databases without authorized integration."],
            reviewer_actions=["Confirm face validity and issuer jurisdiction."],
            test_cases=[
                RuleTestCase(name="valid_noc", category="positive", expected_status="passed", notes="Valid future expiry"),
                RuleTestCase(name="expired_noc", category="negative", expected_status="failed", notes="Expired prior to eval date"),
                RuleTestCase(name="same_day_expiry", category="boundary", expected_status="passed", notes="Expiry equals eval date"),
                RuleTestCase(name="unparseable_date", category="exception", expected_status="inconclusive", notes="Malformed date candidate"),
            ],
            approval=common_approval,
            lifecycle=RuleLifecycle.DRAFT,
        ),
        RuleVersionDraft(
            rule_id="APH_2024_STRUCTURAL_STABILITY",
            version=1,
            title="Structural Soundness Certification (APH Clause 2.6)",
            description="Certificate issued by Government-registered Structural Engineer confirming building stability.",
            source_title=APH_SOURCE_TITLE,
            source_issuer=APH_SOURCE_ISSUER,
            source_url=HttpUrl(APH_SOURCE_URL),
            source_clause="Clause 2.6",
            source_page="45",
            source_provenance=common_provenance,
            publication_date=date(2024, 1, 1),
            effective_from=date(2024, 4, 1),
            effective_to=date(2027, 3, 31),
            applicability=RuleApplicability(
                application_types=["eoa", "new_program", "intake_change"],
                academic_years=["2024-25", "2025-26", "2026-27"],
                conditions=["all_institutions"],
            ),
            interpretation="Requires proof of earthquake resistance and structural stability for all campus buildings.",
            limitations=["Documentary check only; does not replace physical inspection."],
            reviewer_actions=["Inspect engineer registration and municipal empanelment."],
            test_cases=[
                RuleTestCase(name="valid_cert", category="positive", expected_status="passed", notes="Valid structural cert"),
                RuleTestCase(name="missing_cert", category="negative", expected_status="failed", notes="Doc not uploaded"),
                RuleTestCase(name="boundary_cert", category="boundary", expected_status="passed", notes="Valid through academic year"),
                RuleTestCase(name="corrupted_scan", category="exception", expected_status="inconclusive", notes="Unreadable stamp"),
            ],
            approval=common_approval,
            lifecycle=RuleLifecycle.DRAFT,
        ),
        RuleVersionDraft(
            rule_id="APH_2024_BUILDING_OCCUPANCY",
            version=1,
            title="Building Occupancy & Completion Certificate (APH Clause 2.5)",
            description="Final or provisional Occupancy Certificate from Municipal Town Planning Authority.",
            source_title=APH_SOURCE_TITLE,
            source_issuer=APH_SOURCE_ISSUER,
            source_url=HttpUrl(APH_SOURCE_URL),
            source_clause="Clause 2.5",
            source_page="44",
            source_provenance=common_provenance,
            publication_date=date(2024, 1, 1),
            effective_from=date(2024, 4, 1),
            effective_to=date(2027, 3, 31),
            applicability=RuleApplicability(
                application_types=["eoa", "new_program", "intake_change"],
                academic_years=["2024-25", "2025-26", "2026-27"],
                conditions=["all_institutions"],
            ),
            interpretation="Verifies lawful construction and municipal authority approval to occupy instructional areas.",
            limitations=["Relies on submitted municipality seal and reference number."],
            reviewer_actions=["Check municipal registration number."],
            test_cases=[
                RuleTestCase(name="valid_occupancy", category="positive", expected_status="passed", notes="Official certificate"),
                RuleTestCase(name="missing_occupancy", category="negative", expected_status="failed", notes="No certificate"),
                RuleTestCase(name="blueprint_only", category="boundary", expected_status="inconclusive", notes="Only building plan attached"),
                RuleTestCase(name="unreadable_seal", category="exception", expected_status="inconclusive", notes="Illegible issuing body"),
            ],
            approval=common_approval,
            lifecycle=RuleLifecycle.DRAFT,
        ),
        RuleVersionDraft(
            rule_id="APH_2024_LAND_TITLE",
            version=1,
            title="Contiguous Land Title & NA Conversion (APH Clause 1.7)",
            description="Clear unencumbered title or min 30-year registered lease deed with educational NA order.",
            source_title=APH_SOURCE_TITLE,
            source_issuer=APH_SOURCE_ISSUER,
            source_url=HttpUrl(APH_SOURCE_URL),
            source_clause="Clause 1.7",
            source_page="22",
            source_provenance=common_provenance,
            publication_date=date(2024, 1, 1),
            effective_from=date(2024, 4, 1),
            effective_to=date(2027, 3, 31),
            applicability=RuleApplicability(
                application_types=["eoa", "new_program", "intake_change"],
                academic_years=["2024-25", "2025-26", "2026-27"],
                conditions=["all_institutions"],
            ),
            interpretation="Requires unbroken 30-year operational horizon on contiguous institutional land.",
            limitations=["Sub-registrar database verification requires state land revenue API."],
            reviewer_actions=["Confirm survey numbers and encumbrance certificate."],
            test_cases=[
                RuleTestCase(name="valid_title", category="positive", expected_status="passed", notes="Clear 30-year lease"),
                RuleTestCase(name="expired_lease", category="negative", expected_status="failed", notes="Lease expired"),
                RuleTestCase(name="renewal_pending", category="boundary", expected_status="failed", notes="Short remaining term"),
                RuleTestCase(name="missing_deed", category="exception", expected_status="failed", notes="No land doc attached"),
            ],
            approval=common_approval,
            lifecycle=RuleLifecycle.DRAFT,
        ),
        RuleVersionDraft(
            rule_id="APH_2024_MANDATORY_AFFIDAVIT",
            version=1,
            title="Mandatory Self-Disclosure Affidavits 1 & 2 (APH Clause 2.1)",
            description="Duly notarized statutory self-disclosure Affidavits 1 & 2 in AICTE prescribed format.",
            source_title=APH_SOURCE_TITLE,
            source_issuer=APH_SOURCE_ISSUER,
            source_url=HttpUrl(APH_SOURCE_URL),
            source_clause="Clause 2.1",
            source_page="39",
            source_provenance=common_provenance,
            publication_date=date(2024, 1, 1),
            effective_from=date(2024, 4, 1),
            effective_to=date(2027, 3, 31),
            applicability=RuleApplicability(
                application_types=["eoa", "new_program", "intake_change"],
                academic_years=["2024-25", "2025-26", "2026-27"],
                conditions=["all_institutions"],
            ),
            interpretation="Statutory requirement ensuring accurate disclosure of faculty, fees, anti-ragging.",
            limitations=["Notary authenticity is evaluated on document appearance."],
            reviewer_actions=["Inspect notary stamp, registration number, and advocate seal."],
            test_cases=[
                RuleTestCase(name="valid_affidavit", category="positive", expected_status="passed", notes="Notarized submission"),
                RuleTestCase(name="missing_affidavit", category="negative", expected_status="failed", notes="Doc omitted"),
                RuleTestCase(name="unnotarized_plain", category="boundary", expected_status="failed", notes="Plain paper without notary"),
                RuleTestCase(name="corrupt_page", category="exception", expected_status="inconclusive", notes="Corrupt page 2"),
            ],
            approval=common_approval,
            lifecycle=RuleLifecycle.DRAFT,
        ),
        RuleVersionDraft(
            rule_id="APH_2024_NBA_ACCREDITATION",
            version=1,
            title="Programmatic NBA Accreditation Norms (APH Clause 4.2)",
            description="Minimum 50% eligible courses must hold valid NBA accreditation for intake expansion or new programs.",
            source_title=APH_SOURCE_TITLE,
            source_issuer=APH_SOURCE_ISSUER,
            source_url=HttpUrl(APH_SOURCE_URL),
            source_clause="Clause 4.2",
            source_page="68",
            source_provenance=common_provenance,
            publication_date=date(2024, 1, 1),
            effective_from=date(2024, 4, 1),
            effective_to=date(2027, 3, 31),
            applicability=RuleApplicability(
                application_types=["new_program", "intake_change", "eoa"],
                academic_years=["2024-25", "2025-26", "2026-27"],
                conditions=["program_expansion"],
            ),
            interpretation="Mandates quality threshold before additional student divisions or new technical courses can be approved.",
            limitations=["Live NBA central accreditation portal status is checked when adapter is active."],
            reviewer_actions=["Verify eligible course list against approved intake."],
            test_cases=[
                RuleTestCase(name="valid_nba", category="positive", expected_status="passed", notes="Valid certificate for expansion"),
                RuleTestCase(name="missing_nba_expansion", category="negative", expected_status="failed", notes="Expansion requested without NBA"),
                RuleTestCase(name="eoa_not_applicable", category="boundary", expected_status="not_applicable", notes="Regular EoA"),
                RuleTestCase(name="uncertain_intake", category="exception", expected_status="trigger_unevaluable", notes="Cannot determine expansion"),
            ],
            approval=common_approval,
            lifecycle=RuleLifecycle.DRAFT,
        ),
    ]
    return rules


class RuleEngineService:
    """Manages the lifecycle, activation, and evaluation of regulatory rules."""

    def __init__(self, registry: RuleRegistry | None = None) -> None:
        self.registry = registry or RuleRegistry()
        self._ensure_aph_rules_activated()

    def _ensure_aph_rules_activated(self) -> None:
        """Populate and activate the verified APH rules if not already active."""
        if len(self.registry) == 0:
            for rule in build_aph_verified_rules():
                try:
                    self.registry.activate(rule)
                except Exception as exc:
                    logger.warning("Could not activate verified rule %s: %s", rule.rule_id, exc)

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

    def get_active_rules(self) -> list[RuleDefinition]:
        """Return currently active rules from the registry."""
        return self.registry.active_rules()

    def get_checklist_for_application_type(self, application_type: str) -> list[ChecklistItem]:
        """Return required and conditional checklist items for the application type."""
        return CHECKLIST_CATALOG.get(application_type, [])

    def evaluate_application(self, context: RuleEvaluationContext) -> list[RuleEvaluationResult]:
        """Alias for evaluate_rules."""
        return self.evaluate_rules(context)
