"""Tests for APH 2024-2027 Regulatory Rule Engine, dynamic checklists, and evaluation."""

from __future__ import annotations

from datetime import date
import pytest

from backend.app.db.models import DocumentVersion, ExtractedField
from backend.app.rule_catalog import (
    ApprovalDecision,
    ApprovalRecord,
    RuleLifecycle,
    RuleRegistry,
    SourceVerificationStatus,
)
from backend.app.services.rule_engine import (
    CHECKLIST_CATALOG,
    RuleApprovalService,
    RuleEngineService,
    RuleEvaluationContext,
    build_aph_draft_rules,
)


def _make_version(version_id: int, fields_dict: dict[str, str]) -> DocumentVersion:
    ver = DocumentVersion(
        id=version_id,
        document_id=version_id,
        version_number=1,
        storage_key=f"uploads/test_{version_id}.pdf",
        sha256=f"hash_{version_id:064d}",
        media_type="application/pdf",
        byte_size=1024,
    )
    extracted = []
    for idx, (k, v) in enumerate(fields_dict.items(), start=1):
        extracted.append(
            ExtractedField(
                id=version_id * 100 + idx,
                document_version_id=version_id,
                field_name=k,
                raw_text=v,
                normalized_value=v,
                confidence=0.98,
                engine_name="test_engine",
            )
        )
    ver.extracted_fields = extracted
    return ver


def _get_active_service() -> RuleEngineService:
    service = RuleEngineService()
    RuleApprovalService.activate_standard_aph_rules(service.registry)
    return service


def test_rule_engine_unapproved_starts_empty():
    """Rules must not claim statutory approval unless an actual human review approval workflow has executed."""
    service = RuleEngineService()
    active_rules = service.get_active_rules()
    assert len(active_rules) == 0


def test_rule_approval_and_activation_workflow():
    service = RuleEngineService()
    drafts = build_aph_draft_rules()
    assert len(drafts) >= 6
    for d in drafts:
        assert d.approval is None
        assert d.lifecycle == RuleLifecycle.DRAFT

    # Activate via attributable review
    activated = RuleApprovalService.activate_standard_aph_rules(
        service.registry,
        approver_id="AICTE_REGULATORY_DIRECTOR",
        rationale="Formally reviewed and reconciled against APH 2024-2027 statutory text.",
    )
    assert len(activated) >= 6
    rule_ids = {r.rule_id for r in service.get_active_rules()}
    assert "APH_2024_FIRE_SAFETY" in rule_ids
    assert "APH_2024_STRUCTURAL_STABILITY" in rule_ids
    assert "APH_2024_BUILDING_OCCUPANCY" in rule_ids
    assert "APH_2024_LAND_TITLE" in rule_ids
    assert "APH_2024_MANDATORY_AFFIDAVIT" in rule_ids
    assert "APH_2024_NBA_ACCREDITATION" in rule_ids


def test_dynamic_checklist_catalog():
    service = _get_active_service()

    eoa_checklist = service.get_checklist_for_application_type("eoa")
    assert len(eoa_checklist) >= 5
    items_by_type = {item.document_type: item for item in eoa_checklist}

    # Verify statutory citations
    assert items_by_type["fire_safety_certificate"].necessity == "mandatory"
    assert "Annexure-2" in items_by_type["fire_safety_certificate"].aph_clause
    assert "2.1(v)" in items_by_type["fire_safety_certificate"].aph_clause

    assert items_by_type["occupancy_certificate"].necessity == "mandatory"
    assert "Annexure-2" in items_by_type["occupancy_certificate"].aph_clause
    assert "2.1(iii)" in items_by_type["occupancy_certificate"].aph_clause

    assert items_by_type["mandatory_affidavit"].necessity == "mandatory"
    assert "Annexure-2" in items_by_type["mandatory_affidavit"].aph_clause
    assert "2.1(i)" in items_by_type["mandatory_affidavit"].aph_clause

    # Structural stability is CONDITIONAL per APH Annexure-2 Clause 2.1(iv)
    assert items_by_type["structural_stability"].necessity == "conditional"
    assert "30" in items_by_type["structural_stability"].condition_description

    # Land document is CONDITIONAL for EoA per APH Foreword
    assert items_by_type["land_document"].necessity == "conditional"

    new_prog_checklist = service.get_checklist_for_application_type("new_program")
    np_types = {item.document_type for item in new_prog_checklist}
    assert "state_govt_noc" in np_types
    assert "university_affiliation" in np_types

    intake_checklist = service.get_checklist_for_application_type("intake_change")
    ic_types = {item.document_type for item in intake_checklist}
    assert "nba_accreditation" in ic_types


def test_rule_fire_safety_evaluation_compliant():
    service = _get_active_service()
    ver = _make_version(1, {
        "valid_until": "2027-12-31",
        "issuing_authority": "State Fire and Emergency Services",
    })
    context = RuleEvaluationContext(
        application_id=1,
        application_type="eoa",
        academic_year="2026-2027",
        institution_id="INST-001",
        evaluation_date=date(2026, 10, 28),
        eligible_versions={"fire_safety_certificate": ver},
    )
    results = service.evaluate_application(context)
    fire_results = [r for r in results if r.rule_id == "APH_2024_FIRE_SAFETY"]
    assert len(fire_results) == 1
    assert fire_results[0].status == "passed"
    assert fire_results[0].severity == "info"


def test_rule_fire_safety_evaluation_expired():
    service = _get_active_service()
    ver = _make_version(2, {
        "valid_until": "2025-01-01",
        "issuing_authority": "State Fire and Emergency Services",
    })
    context = RuleEvaluationContext(
        application_id=1,
        application_type="eoa",
        academic_year="2026-2027",
        institution_id="INST-001",
        evaluation_date=date(2026, 10, 28),
        eligible_versions={"fire_safety_certificate": ver},
    )
    results = service.evaluate_application(context)
    fire_results = [r for r in results if r.rule_id == "APH_2024_FIRE_SAFETY"]
    assert len(fire_results) == 1
    assert fire_results[0].status == "failed"
    assert fire_results[0].severity == "error"
    assert "expired" in fire_results[0].message.lower()


def test_rule_fire_safety_missing_document():
    service = _get_active_service()
    context = RuleEvaluationContext(
        application_id=1,
        application_type="eoa",
        academic_year="2026-2027",
        institution_id="INST-001",
        evaluation_date=date(2026, 10, 28),
        eligible_versions={},
    )
    results = service.evaluate_application(context)
    fire_results = [r for r in results if r.rule_id == "APH_2024_FIRE_SAFETY"]
    assert len(fire_results) == 1
    assert fire_results[0].status == "failed"
    assert "missing" in fire_results[0].message.lower()


def test_rule_structural_stability_conditional_on_building_age():
    service = _get_active_service()

    # Case A: Building age <= 30 years -> NOT mandatory, passes even without document
    context_young = RuleEvaluationContext(
        application_id=10,
        application_type="eoa",
        academic_year="2026-2027",
        institution_id="INST-001",
        evaluation_date=date(2026, 10, 28),
        eligible_versions={},
        declared_parameters={"building_age_years": 15, "building_age_greater_than_30": False},
    )
    results_young = service.evaluate_application(context_young)
    ss_young = [r for r in results_young if r.rule_id == "APH_2024_STRUCTURAL_STABILITY"]
    assert len(ss_young) == 1
    assert ss_young[0].status == "passed"
    assert "not mandatory" in ss_young[0].message.lower()

    # Case B: Building age > 30 years -> Mandatory; missing document produces failure
    context_old = RuleEvaluationContext(
        application_id=11,
        application_type="eoa",
        academic_year="2026-2027",
        institution_id="INST-001",
        evaluation_date=date(2026, 10, 28),
        eligible_versions={},
        declared_parameters={"building_age_years": 35, "building_age_greater_than_30": True},
    )
    results_old = service.evaluate_application(context_old)
    ss_old = [r for r in results_old if r.rule_id == "APH_2024_STRUCTURAL_STABILITY"]
    assert len(ss_old) == 1
    assert ss_old[0].status == "failed"
    assert "30-year threshold" in ss_old[0].message

    # Case C: Valid certificate provided for old building -> passes
    ver = _make_version(20, {"valid_until": "2028-12-31"})
    context_old_with_cert = RuleEvaluationContext(
        application_id=12,
        application_type="eoa",
        academic_year="2026-2027",
        institution_id="INST-001",
        evaluation_date=date(2026, 10, 28),
        eligible_versions={"structural_stability": ver},
        declared_parameters={"building_age_years": 35},
    )
    results_cert = service.evaluate_application(context_old_with_cert)
    ss_cert = [r for r in results_cert if r.rule_id == "APH_2024_STRUCTURAL_STABILITY"]
    assert len(ss_cert) == 1
    assert ss_cert[0].status == "passed"


def test_rule_land_title_simplified_for_eoa():
    service = _get_active_service()

    # Regular EoA without site change: land title is simplified per APH Foreword
    context_eoa = RuleEvaluationContext(
        application_id=30,
        application_type="eoa",
        academic_year="2026-2027",
        institution_id="INST-001",
        evaluation_date=date(2026, 10, 28),
        eligible_versions={},
        declared_parameters={"site_change_requested": False},
    )
    res_eoa = service.evaluate_application(context_eoa)
    land_eoa = [r for r in res_eoa if r.rule_id == "APH_2024_LAND_TITLE"]
    assert len(land_eoa) == 1
    assert land_eoa[0].status == "passed"
    assert "simplified" in land_eoa[0].message.lower()

    # New program requires land document under Chapter I §1.7
    context_np = RuleEvaluationContext(
        application_id=31,
        application_type="new_program",
        academic_year="2026-2027",
        institution_id="INST-001",
        evaluation_date=date(2026, 10, 28),
        eligible_versions={},
    )
    res_np = service.evaluate_application(context_np)
    land_np = [r for r in res_np if r.rule_id == "APH_2024_LAND_TITLE"]
    assert len(land_np) == 1
    assert land_np[0].status == "failed"


def test_rule_nba_accreditation_not_applicable_for_zero_intake_increase():
    service = _get_active_service()
    context = RuleEvaluationContext(
        application_id=2,
        application_type="eoa",
        academic_year="2026-2027",
        institution_id="INST-001",
        evaluation_date=date(2026, 10, 28),
        eligible_versions={},
        declared_parameters={"intake_increase_requested": False},
    )
    results = service.evaluate_application(context)
    nba_results = [r for r in results if r.rule_id == "APH_2024_NBA_ACCREDITATION"]
    assert len(nba_results) == 1
    assert nba_results[0].status == "not_applicable"


def test_rule_nba_accreditation_required_for_intake_change():
    service = _get_active_service()
    context = RuleEvaluationContext(
        application_id=3,
        application_type="intake_change",
        academic_year="2026-2027",
        institution_id="INST-001",
        evaluation_date=date(2026, 10, 28),
        eligible_versions={},
        declared_parameters={"intake_increase_requested": True},
    )
    results = service.evaluate_application(context)
    nba_results = [r for r in results if r.rule_id == "APH_2024_NBA_ACCREDITATION"]
    assert len(nba_results) == 1
    assert nba_results[0].status == "failed"
    assert "nba accreditation" in nba_results[0].message.lower()
