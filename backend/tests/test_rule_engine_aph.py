"""Tests for APH 2024-2027 Regulatory Rule Engine, dynamic checklists, and evaluation."""

from __future__ import annotations

from datetime import date
import pytest

from backend.app.db.models import DocumentVersion, ExtractedField
from backend.app.services.rule_engine import (
    CHECKLIST_CATALOG,
    RuleEngineService,
    RuleEvaluationContext,
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


def test_rule_engine_service_initialization():
    service = RuleEngineService()
    active_rules = service.get_active_rules()
    assert len(active_rules) >= 6
    rule_ids = {r.rule_id for r in active_rules}
    assert "APH_2024_FIRE_SAFETY" in rule_ids
    assert "APH_2024_STRUCTURAL_STABILITY" in rule_ids
    assert "APH_2024_BUILDING_OCCUPANCY" in rule_ids
    assert "APH_2024_LAND_TITLE" in rule_ids
    assert "APH_2024_MANDATORY_AFFIDAVIT" in rule_ids
    assert "APH_2024_NBA_ACCREDITATION" in rule_ids


def test_dynamic_checklist_catalog():
    service = RuleEngineService()

    eoa_checklist = service.get_checklist_for_application_type("eoa")
    assert len(eoa_checklist) >= 4
    doc_types = {item.document_type for item in eoa_checklist}
    assert "fire_safety_certificate" in doc_types
    assert "structural_stability" in doc_types
    assert "occupancy_certificate" in doc_types
    assert "mandatory_affidavit" in doc_types

    new_prog_checklist = service.get_checklist_for_application_type("new_program")
    np_types = {item.document_type for item in new_prog_checklist}
    assert "state_govt_noc" in np_types
    assert "university_affiliation" in np_types

    intake_checklist = service.get_checklist_for_application_type("intake_change")
    ic_types = {item.document_type for item in intake_checklist}
    assert "nba_accreditation" in ic_types


def test_rule_fire_safety_evaluation_compliant():
    service = RuleEngineService()
    ver = _make_version(1, {
        "valid_until": "2027-12-31",
        "issuing_authority": "State Fire and Emergency Services",
    })
    context = RuleEvaluationContext(
        application_id="1",
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
    service = RuleEngineService()
    ver = _make_version(2, {
        "valid_until": "2025-01-01",
        "issuing_authority": "State Fire and Emergency Services",
    })
    context = RuleEvaluationContext(
        application_id="1",
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
    service = RuleEngineService()
    context = RuleEvaluationContext(
        application_id="1",
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


def test_rule_nba_accreditation_not_applicable_for_zero_intake_increase():
    service = RuleEngineService()
    context = RuleEvaluationContext(
        application_id="2",
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
    service = RuleEngineService()
    context = RuleEvaluationContext(
        application_id="3",
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
