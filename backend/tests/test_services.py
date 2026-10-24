"""Tests for application service layer and business logic rules."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import Base
from backend.app.db.models import Application, DocumentVersion, Institution
from backend.app.schemas.application import (
    ApplicationCreate,
    ApplicationUpdate,
    InstitutionCreate,
)
from backend.app.services.application_service import ApplicationService
from backend.app.services.exceptions import (
    ApplicationNotFoundError,
    DuplicateInstitutionError,
    InstitutionNotFoundError,
    InvalidAcademicYearError,
    InvalidApplicationTypeError,
    InvalidStatusTransitionError,
)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Isolated in-memory database session for service tests."""
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


@pytest.fixture
def service() -> ApplicationService:
    return ApplicationService()


def test_create_and_retrieve_application_linked_to_institution(
    db: Session, service: ApplicationService
):
    """Scenario 1: Creating and retrieving an application linked to an existing institution."""
    inst = service.create_institution(
        db,
        InstitutionCreate(
            institution_id="INST-SRV-01",
            display_name="Service Institute of Tech",
        ),
    )

    app_data = ApplicationCreate(
        institution_id=inst.id,
        application_type="eoa",
        academic_year="2026-2027",
    )
    app = service.create_application(db, app_data, actor_id="ACTOR-1", request_id="REQ-1")

    assert app.id is not None
    assert app.institution_id == inst.id
    assert app.status == "draft"

    retrieved = service.get_application(db, app.id)
    assert retrieved.id == app.id
    assert retrieved.academic_year == "2026-2027"

    with pytest.raises(ApplicationNotFoundError):
        service.get_application(db, 999999)


def test_reject_nonexistent_institution_reference(
    db: Session, service: ApplicationService
):
    """Scenario 2: Rejecting a nonexistent institution reference."""
    app_data = ApplicationCreate(
        institution_id=999999,
        application_type="eoa",
        academic_year="2026-2027",
    )
    with pytest.raises(InstitutionNotFoundError) as exc_info:
        service.create_application(db, app_data)
    assert "does not exist" in str(exc_info.value)


def test_reject_unsupported_application_type(
    db: Session, service: ApplicationService
):
    """Scenario 3: Rejecting an unsupported application type."""
    inst = service.create_institution(
        db, InstitutionCreate(institution_id="INST-SRV-02", display_name="Inst")
    )
    # Using model_construct to bypass pydantic's schema validator and verify service-layer enforcement
    app_data = ApplicationCreate.model_construct(
        institution_id=inst.id,
        application_type="unsupported_type",
        academic_year="2026-2027",
    )
    with pytest.raises(InvalidApplicationTypeError) as exc_info:
        service.create_application(db, app_data)
    assert "Unsupported application type" in str(exc_info.value)


@pytest.mark.parametrize(
    "invalid_year",
    [
        "2026/2027",
        "2026",
        "2027-2026",  # Reversed
        "2024-2026",  # Two year span
        "not-a-year",
        "1999-2000",
    ],
)
def test_reject_invalid_academic_year_formats(
    db: Session, service: ApplicationService, invalid_year: str
):
    """Scenario 4: Handling invalid academic-year formats."""
    inst = service.create_institution(
        db, InstitutionCreate(institution_id=f"INST-{invalid_year}", display_name="Inst")
    )
    app_data = ApplicationCreate(
        institution_id=inst.id,
        application_type="eoa",
        academic_year=invalid_year,
    )
    with pytest.raises(InvalidAcademicYearError):
        service.create_application(db, app_data)


def test_list_applications_filtering_and_pagination(
    db: Session, service: ApplicationService
):
    """Scenario 5: Listing applications with correct institution filters, pagination and ordering."""
    inst1 = service.create_institution(
        db, InstitutionCreate(institution_id="INST-LIST-1", display_name="Inst 1")
    )
    inst2 = service.create_institution(
        db, InstitutionCreate(institution_id="INST-LIST-2", display_name="Inst 2")
    )

    for i in range(5):
        service.create_application(
            db,
            ApplicationCreate(
                institution_id=inst1.id,
                application_type="eoa",
                academic_year=f"202{i}-202{i+1}",
            ),
        )

    service.create_application(
        db,
        ApplicationCreate(
            institution_id=inst2.id,
            application_type="new_program",
            academic_year="2026-2027",
        ),
    )

    apps, total = service.list_applications_for_institution(db, inst1.id, skip=0, limit=3)
    assert total == 5
    assert len(apps) == 3

    page2, total2 = service.list_applications_for_institution(db, inst1.id, skip=3, limit=3)
    assert total2 == 5
    assert len(page2) == 2

    other_apps, other_total = service.list_applications_for_institution(db, inst2.id)
    assert other_total == 1
    assert len(other_apps) == 1


def test_update_allowed_application_fields(
    db: Session, service: ApplicationService
):
    """Scenario 6: Updating allowed application fields."""
    inst = service.create_institution(
        db, InstitutionCreate(institution_id="INST-UPD-01", display_name="Inst")
    )
    app = service.create_application(
        db,
        ApplicationCreate(
            institution_id=inst.id,
            application_type="eoa",
            academic_year="2026-2027",
        ),
    )

    updated = service.update_application(
        db,
        app.id,
        ApplicationUpdate(academic_year="2027-2028"),
    )
    assert updated.academic_year == "2027-2028"


def test_reject_invalid_lifecycle_transitions(
    db: Session, service: ApplicationService
):
    """Scenario 7: Rejecting invalid lifecycle transitions where transition rules are defined."""
    inst = service.create_institution(
        db, InstitutionCreate(institution_id="INST-TRANS-01", display_name="Inst")
    )
    app = service.create_application(
        db,
        ApplicationCreate(
            institution_id=inst.id,
            application_type="eoa",
            academic_year="2026-2027",
        ),
    )
    assert app.status == "draft"

    # Valid: draft -> submitted
    service.transition_status(db, app.id, "submitted")
    assert app.status == "submitted"

    # Invalid: submitted -> draft (cannot go backward)
    with pytest.raises(InvalidStatusTransitionError) as exc_info:
        service.transition_status(db, app.id, "draft")
    assert "Cannot transition" in str(exc_info.value)

    # Valid: submitted -> processing -> review_required -> reviewed -> closed
    service.transition_status(db, app.id, "processing")
    service.transition_status(db, app.id, "review_required")
    service.transition_status(
        db, app.id, "reviewed", reviewer_id="REV-1", comment="All criteria satisfied."
    )
    service.transition_status(db, app.id, "closed")
    assert app.status == "closed"

    # Terminal: closed cannot transition to anything
    with pytest.raises(InvalidStatusTransitionError):
        service.transition_status(db, app.id, "draft")


def test_duplicate_institutional_identifier_rejected(
    db: Session, service: ApplicationService
):
    """Scenario 8: Handling duplicate institutional identifiers and database constraint violations."""
    service.create_institution(
        db, InstitutionCreate(institution_id="DUP-IDENT-01", display_name="First")
    )
    with pytest.raises(DuplicateInstitutionError):
        service.create_institution(
            db, InstitutionCreate(institution_id="DUP-IDENT-01", display_name="Second")
        )


def test_create_document_and_multiple_historical_versions(
    db: Session, service: ApplicationService
):
    """Scenarios 9 & 10: Creating document record, adding versions and preserving history."""
    inst = service.create_institution(
        db, InstitutionCreate(institution_id="INST-DOC-HIST", display_name="Inst")
    )
    app = service.create_application(
        db,
        ApplicationCreate(
            institution_id=inst.id,
            application_type="eoa",
            academic_year="2026-2027",
        ),
    )

    doc, v1 = service.add_document_version(
        db,
        app.id,
        "aicte_approval",
        storage_key="s3://store/v1.pdf",
        sha256="1" * 64,
        media_type="application/pdf",
        byte_size=1000,
    )
    assert doc.current_version_id == v1.id
    assert v1.version_number == 1

    doc_refreshed, v2 = service.add_document_version(
        db,
        app.id,
        "aicte_approval",
        storage_key="s3://store/v2.pdf",
        sha256="2" * 64,
        media_type="application/pdf",
        byte_size=1500,
    )
    assert doc_refreshed.current_version_id == v2.id
    assert v2.version_number == 2

    # Verify historical records remain intact
    versions = db.scalars(
        select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
    ).all()
    assert len(versions) == 2
    assert {v.sha256 for v in versions} == {"1" * 64, "2" * 64}


def test_transaction_rollback_on_failure(
    db: Session, service: ApplicationService, monkeypatch: pytest.MonkeyPatch
):
    """Scenario 13: Transaction rollback when one step of a multi-step operation fails."""
    inst = service.create_institution(
        db, InstitutionCreate(institution_id="INST-ROLLBACK", display_name="Inst")
    )

    # Force review_audit_repo to fail after application creation flush
    def broken_audit(*args, **kwargs):
        raise RuntimeError("Simulated audit subsystem crash")

    monkeypatch.setattr(service.review_audit_repo, "create_audit_event", broken_audit)

    with pytest.raises(RuntimeError):
        service.create_application(
            db,
            ApplicationCreate(
                institution_id=inst.id,
                application_type="eoa",
                academic_year="2026-2027",
            ),
        )

    # Verify that the application was rolled back and never committed
    apps = db.scalars(select(Application).where(Application.institution_id == inst.id)).all()
    assert len(apps) == 0, "Application must be rolled back on failure"


def test_test_isolation_leaves_clean_database(
    db: Session, service: ApplicationService
):
    """Scenario 14: Ensuring test cases remain isolated and leave no unexpected database state."""
    institutions = db.scalars(select(Institution)).all()
    assert len(institutions) == 0, "Test database must start completely clean"
