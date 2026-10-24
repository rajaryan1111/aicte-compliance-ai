"""Tests for Task B8: Consolidated Scrutiny Report, Provenance, Summary Counts, and Audit Trails.

Verifies:
- ScrutinyReportResponse schema and completeness.
- Summary counts match persisted check results.
- Evidence references and document version linkages.
- Advisory disclaimer explicitly informs user that outputs are preliminary and non-binding.
- Audit event VALIDATION_RUN_COMPLETED is persisted with attributable metadata.
- Reproducibility and provenance across multiple runs on the same application.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
    AuditEvent,
    Document,
    DocumentVersion,
    ExtractedField,
    Institution,
)
from backend.app.repositories.validation_repository import ValidationRepository
from backend.app.schemas.validation import ScrutinyReportResponse, ValidationRunRead
from backend.app.services.validation_orchestration_service import (
    PRELIMINARY_ADVISORY_DISCLAIMER,
    ValidationOrchestrationService,
)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
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
def sample_setup(db_session: Session) -> tuple[Institution, Application]:
    inst = Institution(institution_id="INST-REPORT-100", display_name="Government Engineering College")
    db_session.add(inst)
    db_session.commit()
    db_session.refresh(inst)

    app = Application(
        institution_id=inst.id,
        application_type="eoa",
        academic_year="2025-2026",
        status="submitted",
    )
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)

    # Document 1: Land document
    doc1 = Document(application_id=app.id, document_type="land_document")
    db_session.add(doc1)
    db_session.flush()

    v1 = DocumentVersion(
        document_id=doc1.id,
        version_number=1,
        storage_key="key_land_v1",
        sha256="sha_land_111",
        media_type="application/pdf",
        byte_size=2048,
        scan_status="clean",
        processing_status="succeeded",
    )
    db_session.add(v1)
    db_session.flush()
    doc1.current_version_id = v1.id

    f1 = ExtractedField(
        document_version_id=v1.id,
        field_name="institution_name",
        raw_text=inst.display_name,
        normalized_value=inst.display_name,
        confidence=0.97,
        engine_name="test_ocr",
    )
    db_session.add(f1)

    # Document 2: Fire safety with expired date
    doc2 = Document(application_id=app.id, document_type="fire_safety_certificate")
    db_session.add(doc2)
    db_session.flush()

    v2 = DocumentVersion(
        document_id=doc2.id,
        version_number=1,
        storage_key="key_fire_v1",
        sha256="sha_fire_222",
        media_type="application/pdf",
        byte_size=1536,
        scan_status="clean",
        processing_status="succeeded",
    )
    db_session.add(v2)
    db_session.flush()
    doc2.current_version_id = v2.id

    f2 = ExtractedField(
        document_version_id=v2.id,
        field_name="valid_until",
        raw_text="2022-05-15",
        normalized_value="2022-05-15",
        confidence=0.91,
        engine_name="test_ocr",
    )
    db_session.add(f2)

    db_session.commit()
    db_session.refresh(app)
    return inst, app


def test_scrutiny_report_structure_and_disclaimer(db_session: Session, sample_setup: tuple[Institution, Application]):
    """Verify ScrutinyReportResponse serializes cleanly with full provenance and advisory disclaimer."""
    inst, app = sample_setup
    service = ValidationOrchestrationService()

    run = service.run_validation(
        db_session,
        app.id,
        actor_id="officer_sharma",
        evaluation_date=date(2026, 10, 24),
        checklist_type="synthetic_demo",
    )

    check_results = ValidationRepository.list_check_results_for_run(db_session, run.id)
    findings = ValidationRepository.list_findings_for_run(db_session, run.id)

    report = ScrutinyReportResponse(
        application_id=app.id,
        application_type=app.application_type,
        academic_year=app.academic_year,
        institution_id=inst.institution_id,
        institution_name=inst.display_name,
        validation_run=ValidationRunRead.model_validate(run),
        check_results=check_results,
        findings=findings,
        disclaimer=PRELIMINARY_ADVISORY_DISCLAIMER,
    )

    dumped = report.model_dump()

    assert dumped["application_id"] == app.id
    assert dumped["institution_id"] == "INST-REPORT-100"
    assert dumped["institution_name"] == "Government Engineering College"

    # Run checks
    run_dump = dumped["validation_run"]
    assert run_dump["status"] == "succeeded"
    assert run_dump["outcome"] == "attention_required"
    assert run_dump["evaluation_date"] == date(2026, 10, 24)
    assert run_dump["triggered_by"] == "officer_sharma"
    assert len(run_dump["consumed_version_ids"]) == 2

    # Verify counts match individual check results
    summary = run_dump["summary_counts"]
    actual_passed = sum(1 for c in check_results if c.status == "passed")
    actual_failed = sum(1 for c in check_results if c.status == "failed")
    actual_inconclusive = sum(1 for c in check_results if c.status == "inconclusive")
    actual_not_applicable = sum(1 for c in check_results if c.status == "not_applicable")
    actual_not_run = sum(1 for c in check_results if c.status == "not_run")

    assert summary["passed"] == actual_passed
    assert summary["failed"] == actual_failed
    assert summary["inconclusive"] == actual_inconclusive
    assert summary["not_applicable"] == actual_not_applicable
    assert summary["not_run"] == actual_not_run

    # Disclaimer verification
    assert "Preliminary pre-scrutiny result only" in dumped["disclaimer"]
    assert "not constitute official AICTE regulatory approval" in dumped["disclaimer"]


def test_audit_event_recorded_on_validation_completion(
    db_session: Session, sample_setup: tuple[Institution, Application]
):
    """Execution of validation creates an attributable AuditEvent in the database."""
    inst, app = sample_setup
    service = ValidationOrchestrationService()

    run = service.run_validation(
        db_session,
        app.id,
        actor_id="evaluator_patel",
        evaluation_date=date(2026, 10, 24),
    )

    stmt = (
        select(AuditEvent)
        .where(
            AuditEvent.action == "VALIDATION_RUN_COMPLETED",
            AuditEvent.target_type == "ValidationRun",
            AuditEvent.target_id == str(run.id),
        )
    )
    event = db_session.scalar(stmt)
    assert event is not None
    assert event.actor_id == "evaluator_patel"
    assert event.institution_id == inst.id

    details = json.loads(event.details or "{}")
    assert "outcome" in details
    assert "counts" in details
    assert "consumed_versions" in details


def test_reproducible_provenance_and_version_stability(
    db_session: Session, sample_setup: tuple[Institution, Application]
):
    """Verifies that historical run details do not change when new documents are subsequently added."""
    inst, app = sample_setup
    service = ValidationOrchestrationService()

    # Initial Run 1
    run1 = service.run_validation(db_session, app.id, evaluation_date=date(2026, 10, 24))
    snap1 = json.loads(run1.consumed_version_ids or "[]")

    # Add a third document slot to application
    doc3 = Document(application_id=app.id, document_type="building_plan")
    db_session.add(doc3)
    db_session.flush()

    v3 = DocumentVersion(
        document_id=doc3.id,
        version_number=1,
        storage_key="key_build_v1",
        sha256="sha_build_333",
        media_type="application/pdf",
        byte_size=3000,
        scan_status="clean",
        processing_status="succeeded",
    )
    db_session.add(v3)
    db_session.flush()
    doc3.current_version_id = v3.id
    db_session.commit()

    # Run 2
    run2 = service.run_validation(db_session, app.id, evaluation_date=date(2026, 10, 24))
    snap2 = json.loads(run2.consumed_version_ids or "[]")

    # Run 1 retains original 2 versions; Run 2 consumed 3 versions
    assert len(snap1) == 2
    assert len(snap2) == 3
    assert v3.id not in snap1
    assert v3.id in snap2
