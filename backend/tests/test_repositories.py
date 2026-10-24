"""Tests for repository layer operations."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import Base
from backend.app.repositories.application_repository import ApplicationRepository
from backend.app.repositories.document_repository import DocumentRepository
from backend.app.repositories.institution_repository import InstitutionRepository
from backend.app.repositories.review_audit_repository import ReviewAuditRepository
from backend.app.repositories.validation_repository import ValidationRepository


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Isolated database session fixture for repository tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
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


def test_institution_repository_crud(db: Session):
    """Test InstitutionRepository get, create and list."""
    inst = InstitutionRepository.create(
        db,
        institution_id="INST-REPO-01",
        display_name="Repo College of Engineering",
        status="active",
    )
    db.commit()

    by_id = InstitutionRepository.get_by_id(db, inst.id)
    assert by_id is not None
    assert by_id.institution_id == "INST-REPO-01"

    by_ident = InstitutionRepository.get_by_identifier(db, "INST-REPO-01")
    assert by_ident is not None
    assert by_ident.id == inst.id

    assert InstitutionRepository.get_by_identifier(db, "NONEXISTENT") is None

    inst_list = InstitutionRepository.list(db)
    assert len(inst_list) == 1


def test_application_repository_pagination_and_ordering(db: Session):
    """Test ApplicationRepository list_by_institution with pagination and count."""
    inst1 = InstitutionRepository.create(db, institution_id="INST-PAG-01", display_name="Inst 1")
    inst2 = InstitutionRepository.create(db, institution_id="INST-PAG-02", display_name="Inst 2")
    db.commit()

    for i in range(5):
        ApplicationRepository.create(
            db,
            institution_id=inst1.id,
            application_type="eoa",
            academic_year=f"202{i}-202{i+1}",
        )
    # Different institution
    ApplicationRepository.create(
        db,
        institution_id=inst2.id,
        application_type="new_program",
        academic_year="2026-2027",
    )
    db.commit()

    records, total = ApplicationRepository.list_by_institution(db, inst1.id, skip=0, limit=3)
    assert total == 5
    assert len(records) == 3

    page2, total2 = ApplicationRepository.list_by_institution(db, inst1.id, skip=3, limit=3)
    assert total2 == 5
    assert len(page2) == 2

    other_records, other_total = ApplicationRepository.list_by_institution(db, inst2.id)
    assert other_total == 1
    assert len(other_records) == 1


def test_document_repository_multi_version_lifecycle(db: Session):
    """Test DocumentRepository versions and current_version pointer."""
    inst = InstitutionRepository.create(db, institution_id="INST-DOC-01", display_name="Inst")
    db.commit()

    app = ApplicationRepository.create(
        db, institution_id=inst.id, application_type="eoa", academic_year="2026-2027"
    )
    db.commit()

    doc = DocumentRepository.create_document(
        db, application_id=app.id, document_type="undertaking"
    )
    db.commit()

    v1 = DocumentRepository.add_version(
        db,
        document_id=doc.id,
        version_number=1,
        storage_key="s3://bucket/app/undertaking_v1.pdf",
        sha256="1" * 64,
        media_type="application/pdf",
        byte_size=1000,
    )
    db.commit()

    DocumentRepository.set_current_version(db, doc, v1)
    db.commit()

    v2 = DocumentRepository.add_version(
        db,
        document_id=doc.id,
        version_number=2,
        storage_key="s3://bucket/app/undertaking_v2.pdf",
        sha256="2" * 64,
        media_type="application/pdf",
        byte_size=1200,
    )
    db.commit()

    DocumentRepository.set_current_version(db, doc, v2)
    db.commit()

    versions = DocumentRepository.list_versions(db, doc.id)
    assert len(versions) == 2
    assert versions[0].sha256 == "1" * 64
    assert versions[1].sha256 == "2" * 64

    refreshed_doc = DocumentRepository.get_document(db, doc.id)
    assert refreshed_doc is not None
    assert refreshed_doc.current_version_id == v2.id


def test_validation_repository_runs_and_findings(db: Session):
    """Test ValidationRepository runs, findings and query scoping."""
    inst = InstitutionRepository.create(db, institution_id="INST-VAL-01", display_name="Inst")
    db.commit()

    app = ApplicationRepository.create(
        db, institution_id=inst.id, application_type="eoa", academic_year="2026-2027"
    )
    db.commit()

    run = ValidationRepository.create_run(
        db,
        application_id=app.id,
        evaluation_date=date(2026, 4, 30),
        status="succeeded",
        triggered_by="manual_review",
    )
    db.commit()

    f1 = ValidationRepository.create_finding(
        db,
        validation_run_id=run.id,
        code="MISSING_DOCUMENT",
        summary="Document missing.",
        severity="error",
    )
    f2 = ValidationRepository.create_finding(
        db,
        validation_run_id=run.id,
        code="DOCUMENT_EXPIRED",
        summary="Document expired.",
        severity="warning",
    )
    db.commit()
    assert f1.id is not None
    assert f2.id is not None

    runs = ValidationRepository.list_runs_for_application(db, app.id)
    assert len(runs) == 1
    assert runs[0].id == run.id

    findings = ValidationRepository.list_findings_for_run(db, run.id)
    assert len(findings) == 2
    assert {f.code for f in findings} == {"MISSING_DOCUMENT", "DOCUMENT_EXPIRED"}


def test_review_and_audit_repository(db: Session):
    """Test ReviewAuditRepository actions and audit events."""
    inst = InstitutionRepository.create(db, institution_id="INST-AUD-01", display_name="Inst")
    db.commit()

    app = ApplicationRepository.create(
        db, institution_id=inst.id, application_type="eoa", academic_year="2026-2027"
    )
    db.commit()

    action = ReviewAuditRepository.create_review_action(
        db,
        application_id=app.id,
        reviewer_id="REV-01",
        action="request_information",
        comment="Need clearer scan.",
    )
    event = ReviewAuditRepository.create_audit_event(
        db,
        action="REVIEW_REQUEST_INFO",
        target_type="Application",
        target_id=str(app.id),
        actor_id="REV-01",
        institution_id=inst.id,
    )
    db.commit()
    assert action.id is not None
    assert event.id is not None

    actions = ReviewAuditRepository.list_review_actions(db, app.id)
    assert len(actions) == 1
    assert actions[0].reviewer_id == "REV-01"

    events = ReviewAuditRepository.list_audit_events(db, target_type="Application", target_id=str(app.id))
    assert len(events) == 1
    assert events[0].action == "REVIEW_REQUEST_INFO"
