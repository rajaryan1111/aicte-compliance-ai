"""Tests for Task B8: Validation Orchestration Service and Check Engine.

Verifies:
- Document readiness & intake security gates.
- Quarantined or rejected documents are blocked from evidence consumption.
- Pending document processing yields processing_incomplete outcome.
- Expiry checks against uniform evaluation dates.
- Invalid date-order consistency checks.
- Institution identifier conflict checks.
- Cross-document observation discrepancies.
- Duplicate SHA-256 content indicators across document slots.
- Low-confidence extraction alerts.
- Source-governed rule catalog gating (no official rules active -> not_run).
- Synthetic demo rules are clearly labelled.
- Historical runs and evidence snapshots are immutable across re-validation.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
    Document,
    DocumentVersion,
    ExtractedField,
    Institution,
)
from backend.app.repositories.validation_repository import ValidationRepository
from backend.app.services.validation_orchestration_service import (
    SYNTHETIC_DEMO_CHECKLISTS,
    ValidationOrchestrationService,
)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide isolated in-memory SQLite session with StaticPool."""
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
def sample_institution(db_session: Session) -> Institution:
    inst = Institution(institution_id="INST-AICTE-101", display_name="National Institute of Technology")
    db_session.add(inst)
    db_session.commit()
    db_session.refresh(inst)
    return inst


@pytest.fixture
def sample_application(db_session: Session, sample_institution: Institution) -> Application:
    app = Application(
        institution_id=sample_institution.id,
        application_type="eoa",
        academic_year="2025-2026",
        status="submitted",
    )
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)
    return app


def _create_doc_with_version(
    db: Session,
    app_id: int,
    doc_type: str,
    *,
    version_num: int = 1,
    sha256: str = "abc123sha",
    scan_status: str = "clean",
    processing_status: str = "succeeded",
    fields: list[dict] | None = None,
) -> tuple[Document, DocumentVersion]:
    doc = Document(application_id=app_id, document_type=doc_type)
    db.add(doc)
    db.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=version_num,
        storage_key=f"storage_{doc_type}_v{version_num}",
        sha256=sha256,
        media_type="application/pdf",
        byte_size=1024,
        scan_status=scan_status,
        processing_status=processing_status,
    )
    db.add(ver)
    db.flush()

    doc.current_version_id = ver.id
    db.flush()

    if fields:
        for f in fields:
            ef = ExtractedField(
                document_version_id=ver.id,
                field_name=f["name"],
                raw_text=f["val"],
                normalized_value=f.get("norm", f["val"]),
                confidence=f.get("conf", 0.95),
                engine_name="test_engine",
            )
            db.add(ef)
        db.flush()

    db.commit()
    db.refresh(doc)
    db.refresh(ver)
    return doc, ver


# ==============================================================================
# 1. Document Readiness and Completeness
# ==============================================================================


def test_missing_document_on_configured_checklist(db_session: Session, sample_application: Application):
    """When an application lacks required checklist documents, MISSING_DOCUMENT findings are created."""
    service = ValidationOrchestrationService()
    run = service.run_validation(
        db_session,
        sample_application.id,
        checklist_type="synthetic_demo",
    )

    assert run.status == "succeeded"
    assert run.outcome == "attention_required"

    check_results = ValidationRepository.list_check_results_for_run(db_session, run.id)
    findings = ValidationRepository.list_findings_for_run(db_session, run.id)

    readiness_checks = [c for c in check_results if c.check_id == "CHECK_DOCUMENT_READINESS"]
    expected_docs = SYNTHETIC_DEMO_CHECKLISTS["eoa"]
    assert len(readiness_checks) == len(expected_docs)
    assert all(c.status == "failed" for c in readiness_checks)

    missing_findings = [f for f in findings if f.code == "MISSING_DOCUMENT"]
    assert len(missing_findings) == len(expected_docs)


def test_quarantined_or_rejected_file_cannot_be_consumed(db_session: Session, sample_application: Application):
    """A file rejected by malware scanner produces MALWARE_SCAN_REJECTED and is blocked from evidence."""
    _create_doc_with_version(
        db_session,
        sample_application.id,
        "land_document",
        scan_status="rejected",
        processing_status="rejected",
    )

    service = ValidationOrchestrationService()
    run = service.run_validation(
        db_session,
        sample_application.id,
        checklist_type="caller_specified",
        required_documents=["land_document"],
    )

    assert run.status == "succeeded"
    assert run.outcome == "attention_required"

    # Consumed versions must not include rejected file
    consumed = json.loads(run.consumed_version_ids or "[]")
    assert len(consumed) == 0

    findings = ValidationRepository.list_findings_for_run(db_session, run.id)
    assert any(f.code == "MALWARE_SCAN_REJECTED" for f in findings)


def test_pending_document_processing_yields_processing_incomplete(db_session: Session, sample_application: Application):
    """When a required document is still in queue/processing, outcome must be processing_incomplete."""
    _create_doc_with_version(
        db_session,
        sample_application.id,
        "building_plan",
        scan_status="pending_scan",
        processing_status="queued",
    )

    service = ValidationOrchestrationService()
    run = service.run_validation(
        db_session,
        sample_application.id,
        checklist_type="caller_specified",
        required_documents=["building_plan"],
    )

    assert run.status == "succeeded"
    assert run.outcome == "processing_incomplete"

    findings = ValidationRepository.list_findings_for_run(db_session, run.id)
    assert any(f.code == "DOCUMENT_PROCESSING_PENDING" for f in findings)


def test_clean_document_without_extractable_text_yields_inconclusive(db_session: Session, sample_application: Application):
    """A clean document with 0 extracted fields produces NO_EXTRACTABLE_TEXT."""
    _create_doc_with_version(
        db_session,
        sample_application.id,
        "land_document",
        scan_status="clean",
        processing_status="succeeded",
        fields=[],
    )

    service = ValidationOrchestrationService()
    run = service.run_validation(
        db_session,
        sample_application.id,
        checklist_type="caller_specified",
        required_documents=["land_document"],
    )

    findings = ValidationRepository.list_findings_for_run(db_session, run.id)
    assert any(f.code == "NO_EXTRACTABLE_TEXT" for f in findings)


# ==============================================================================
# 2. Expiry and Validity Checks
# ==============================================================================


def test_document_expired_check(db_session: Session, sample_application: Application):
    """An extracted valid_until date earlier than evaluation_date fails with DOCUMENT_EXPIRED."""
    _create_doc_with_version(
        db_session,
        sample_application.id,
        "fire_safety_certificate",
        fields=[{"name": "valid_until", "val": "2020-01-01"}],
    )

    service = ValidationOrchestrationService()
    run = service.run_validation(
        db_session,
        sample_application.id,
        evaluation_date=date(2026, 10, 24),
    )

    assert run.outcome == "attention_required"
    findings = ValidationRepository.list_findings_for_run(db_session, run.id)
    expired_f = [f for f in findings if f.code == "DOCUMENT_EXPIRED"]
    assert len(expired_f) == 1
    assert "2020-01-01" in expired_f[0].summary
    assert "2026-10-24" in expired_f[0].summary


def test_document_future_expiry_passes(db_session: Session, sample_application: Application):
    """An extracted valid_until date on or after evaluation_date passes without findings."""
    _create_doc_with_version(
        db_session,
        sample_application.id,
        "fire_safety_certificate",
        fields=[{"name": "valid_until", "val": "2028-12-31"}],
    )

    service = ValidationOrchestrationService()
    run = service.run_validation(
        db_session,
        sample_application.id,
        evaluation_date=date(2026, 10, 24),
    )

    check_results = ValidationRepository.list_check_results_for_run(db_session, run.id)
    expiry_checks = [c for c in check_results if c.check_id == "CHECK_DOCUMENT_EXPIRY"]
    assert any(c.status == "passed" for c in expiry_checks)

    findings = ValidationRepository.list_findings_for_run(db_session, run.id)
    assert not any(f.code == "DOCUMENT_EXPIRED" for f in findings)


# ==============================================================================
# 3. Consistency Checks (Date Order, Institution, Cross-Document)
# ==============================================================================


def test_invalid_date_order_conflict(db_session: Session, sample_application: Application):
    """When issue_date is after valid_until date, produces INVALID_DATE_ORDER finding."""
    _create_doc_with_version(
        db_session,
        sample_application.id,
        "building_plan",
        fields=[
            {"name": "issue_date", "val": "2026-06-01"},
            {"name": "valid_until", "val": "2025-06-01"},
        ],
    )

    service = ValidationOrchestrationService()
    run = service.run_validation(db_session, sample_application.id)

    findings = ValidationRepository.list_findings_for_run(db_session, run.id)
    assert any(f.code == "INVALID_DATE_ORDER" for f in findings)


def test_institution_identifier_mismatch(db_session: Session, sample_application: Application):
    """Extracted institution identifier conflicting with application produces INSTITUTION_MISMATCH."""
    _create_doc_with_version(
        db_session,
        sample_application.id,
        "land_document",
        fields=[{"name": "institution_id", "val": "INST-OTHER-999"}],
    )

    service = ValidationOrchestrationService()
    run = service.run_validation(db_session, sample_application.id)

    findings = ValidationRepository.list_findings_for_run(db_session, run.id)
    assert any(f.code == "INSTITUTION_MISMATCH" for f in findings)


def test_cross_document_field_conflict(db_session: Session, sample_application: Application):
    """Conflicting institution names extracted across two documents produce INCONSISTENT_DOCUMENT_FIELDS."""
    _create_doc_with_version(
        db_session,
        sample_application.id,
        "land_document",
        sha256="sha_land_1",
        fields=[{"name": "institution_name", "val": "Delhi Technical Institute"}],
    )
    _create_doc_with_version(
        db_session,
        sample_application.id,
        "building_plan",
        sha256="sha_build_1",
        fields=[{"name": "institution_name", "val": "Mumbai Polytechnic College"}],
    )

    service = ValidationOrchestrationService()
    run = service.run_validation(db_session, sample_application.id)

    findings = ValidationRepository.list_findings_for_run(db_session, run.id)
    assert any(f.code == "INCONSISTENT_DOCUMENT_FIELDS" for f in findings)


def test_duplicate_file_sha256_indicator(db_session: Session, sample_application: Application):
    """Identical SHA-256 submitted across two distinct document slots produces DUPLICATE_FILE_INDICATOR."""
    identical_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    _create_doc_with_version(
        db_session,
        sample_application.id,
        "land_document",
        sha256=identical_hash,
        fields=[{"name": "institution_id", "val": sample_application.institution.institution_id}],
    )
    _create_doc_with_version(
        db_session,
        sample_application.id,
        "fire_safety_certificate",
        sha256=identical_hash,
        fields=[{"name": "institution_id", "val": sample_application.institution.institution_id}],
    )

    service = ValidationOrchestrationService()
    run = service.run_validation(db_session, sample_application.id)

    findings = ValidationRepository.list_findings_for_run(db_session, run.id)
    assert any(f.code == "DUPLICATE_FILE_INDICATOR" for f in findings)


def test_low_confidence_extraction_alerts_human_review(db_session: Session, sample_application: Application):
    """Extracted field with confidence < 0.60 creates LOW_CONFIDENCE_EXTRACTION advisory finding."""
    _create_doc_with_version(
        db_session,
        sample_application.id,
        "land_document",
        fields=[
            {"name": "institution_id", "val": sample_application.institution.institution_id, "conf": 0.42}
        ],
    )

    service = ValidationOrchestrationService()
    run = service.run_validation(db_session, sample_application.id)

    findings = ValidationRepository.list_findings_for_run(db_session, run.id)
    assert any(f.code == "LOW_CONFIDENCE_EXTRACTION" for f in findings)


# ==============================================================================
# 4. Regulatory Rule Governance and Provenance Immutability
# ==============================================================================


def test_official_regulatory_rules_gate_fails_safe(db_session: Session, sample_application: Application):
    """When no active approved official AICTE rules exist, statutory check is marked not_run."""
    service = ValidationOrchestrationService()
    run = service.run_validation(db_session, sample_application.id)

    check_results = ValidationRepository.list_check_results_for_run(db_session, run.id)
    reg_check = [c for c in check_results if c.check_id == "CHECK_OFFICIAL_REGULATORY_RULES"]
    assert len(reg_check) == 1
    assert reg_check[0].status == "not_run"

    limitations = json.loads(run.limitations or "[]")
    assert any("No verified, approved and active AICTE rules found" in item for item in limitations)


def test_synthetic_demo_rules_clearly_distinguished(db_session: Session, sample_application: Application):
    """Validation with synthetic_demo checklist records demo provenance and limitations."""
    service = ValidationOrchestrationService()
    run = service.run_validation(
        db_session,
        sample_application.id,
        checklist_type="synthetic_demo",
    )

    rule_snap = json.loads(run.rule_snapshot or "{}")
    assert rule_snap.get("source") == "synthetic_demo_ruleset"
    assert rule_snap.get("checklist_type") == "synthetic_demo"

    limitations = json.loads(run.limitations or "[]")
    assert any("synthetic demonstration checklist" in item for item in limitations)


def test_revalidation_preserves_immutable_historical_runs(db_session: Session, sample_application: Application):
    """Re-validating an application creates a new run without mutating or duplicating past runs."""
    doc, v1 = _create_doc_with_version(
        db_session,
        sample_application.id,
        "land_document",
        version_num=1,
        fields=[{"name": "valid_until", "val": "2020-01-01"}],
    )

    service = ValidationOrchestrationService()
    run1 = service.run_validation(db_session, sample_application.id, evaluation_date=date(2026, 10, 24))
    assert run1.outcome == "attention_required"

    # User uploads version 2 with updated, valid expiry
    v2 = DocumentVersion(
        document_id=doc.id,
        version_number=2,
        storage_key="storage_land_v2",
        sha256="sha_land_v2",
        media_type="application/pdf",
        byte_size=2048,
        scan_status="clean",
        processing_status="succeeded",
    )
    db_session.add(v2)
    db_session.flush()
    doc.current_version_id = v2.id

    ef2 = ExtractedField(
        document_version_id=v2.id,
        field_name="valid_until",
        raw_text="2028-12-31",
        normalized_value="2028-12-31",
        confidence=0.98,
        engine_name="test_engine",
    )
    db_session.add(ef2)
    db_session.commit()

    # Re-validate
    run2 = service.run_validation(db_session, sample_application.id, evaluation_date=date(2026, 10, 24))

    # Verify run1 and run2 are separate and distinct
    assert run1.id != run2.id
    assert json.loads(run1.consumed_version_ids or "[]") == [v1.id]
    assert json.loads(run2.consumed_version_ids or "[]") == [v2.id]

    run1_findings = ValidationRepository.list_findings_for_run(db_session, run1.id)
    run2_findings = ValidationRepository.list_findings_for_run(db_session, run2.id)

    assert any(f.code == "DOCUMENT_EXPIRED" for f in run1_findings)
    assert not any(f.code == "DOCUMENT_EXPIRED" for f in run2_findings)
