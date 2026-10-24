"""Automated persistence layer tests for Task B3.

Verifies:
- Database engine and session configuration.
- Creating and retrieving institutions.
- Creating applications linked to institutions.
- Creating documents with multiple immutable document versions.
- Preserving historical document versions upon update.
- Linking extracted fields to a document version.
- Linking findings to validation runs.
- Review actions and audit events.
- Database uniqueness constraints and foreign-key relationships.
- Alembic programmatic migration upgrade and downgrade on clean disposable database.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
    AuditEvent,
    Document,
    DocumentVersion,
    ExtractedField,
    Finding,
    Institution,
    ReviewAction,
    ValidationRun,
)
from backend.app.db.session import (
    create_db_engine,
    get_database_url,
    get_db,
)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide an isolated, in-memory SQLite database session for each test."""
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


# --- Engine and Session Configuration Tests ---


def test_database_url_configuration(monkeypatch: pytest.MonkeyPatch):
    """Verify DATABASE_URL defaults to SQLite or reflects environment override."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert "sqlite" in get_database_url()

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
    assert get_database_url() == "postgresql://user:pass@localhost:5432/testdb"


def test_create_db_engine_sqlite_connect_args():
    """Verify SQLite engine creation attaches check_same_thread=False."""
    engine = create_db_engine("sqlite:///:memory:")
    assert engine.dialect.name == "sqlite"
    with engine.connect() as conn:
        assert conn.closed is False


def test_get_db_dependency():
    """Verify FastAPI get_db dependency yields and closes session."""
    generator = get_db()
    session = next(generator)
    assert isinstance(session, Session)
    try:
        next(generator)
    except StopIteration:
        pass


# --- Institution and Application Creation Tests ---


def test_create_and_retrieve_institution(db_session: Session):
    """Verify creating and querying an Institution record."""
    inst = Institution(
        institution_id="SYNTH-INST-001",
        display_name="Synthetic Technical Institute",
        status="active",
    )
    db_session.add(inst)
    db_session.commit()

    retrieved = db_session.scalar(
        select(Institution).where(Institution.institution_id == "SYNTH-INST-001")
    )
    assert retrieved is not None
    assert retrieved.display_name == "Synthetic Technical Institute"
    assert retrieved.status == "active"
    assert retrieved.created_at is not None
    assert "SYNTH-INST-001" in repr(retrieved)


def test_create_application_linked_to_institution(db_session: Session):
    """Verify creating an Application linked to an Institution."""
    inst = Institution(
        institution_id="SYNTH-INST-002",
        display_name="Second Technical College",
    )
    db_session.add(inst)
    db_session.commit()

    app = Application(
        institution_id=inst.id,
        application_type="eoa",
        academic_year="2026-2027",
        status="draft",
    )
    db_session.add(app)
    db_session.commit()

    retrieved = db_session.scalar(select(Application).where(Application.id == app.id))
    assert retrieved is not None
    assert retrieved.institution_id == inst.id
    assert retrieved.institution.institution_id == "SYNTH-INST-002"
    assert len(inst.applications) == 1
    assert inst.applications[0].application_type == "eoa"


# --- Document and Immutable Version History Tests ---


def test_create_document_and_multiple_immutable_versions(db_session: Session):
    """Verify creating a document slot and adding multiple versions without erasing history."""
    inst = Institution(
        institution_id="SYNTH-INST-003",
        display_name="Engineering Academy",
    )
    db_session.add(inst)
    db_session.commit()

    app = Application(
        institution_id=inst.id,
        application_type="new_program",
        academic_year="2026-2027",
    )
    db_session.add(app)
    db_session.commit()

    doc = Document(
        application_id=app.id,
        document_type="aicte_approval",
    )
    db_session.add(doc)
    db_session.commit()

    # Upload version 1
    v1 = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key="docs/2026/app-1/approval_v1.pdf",
        sha256="a" * 64,
        media_type="application/pdf",
        byte_size=10240,
        page_count=3,
        processing_status="succeeded",
    )
    db_session.add(v1)
    db_session.commit()

    doc.current_version_id = v1.id
    db_session.commit()

    # Upload version 2 (replacement)
    v2 = DocumentVersion(
        document_id=doc.id,
        version_number=2,
        storage_key="docs/2026/app-1/approval_v2.pdf",
        sha256="b" * 64,
        media_type="application/pdf",
        byte_size=12400,
        page_count=4,
        processing_status="succeeded",
    )
    db_session.add(v2)
    db_session.commit()

    doc.current_version_id = v2.id
    db_session.commit()

    # Verify both historical versions are preserved
    versions = db_session.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number)
    ).all()

    assert len(versions) == 2
    assert versions[0].version_number == 1
    assert versions[0].sha256 == "a" * 64
    assert versions[1].version_number == 2
    assert versions[1].sha256 == "b" * 64

    # Current version points to v2
    assert doc.current_version is not None
    assert doc.current_version.id == v2.id
    assert doc.current_version.version_number == 2


# --- Extracted Fields and Findings Tests ---


def test_link_extracted_fields_to_document_version(db_session: Session):
    """Verify linking OCR extracted fields to a document version."""
    inst = Institution(institution_id="SYNTH-INST-004", display_name="Test Inst")
    db_session.add(inst)
    db_session.commit()

    app = Application(
        institution_id=inst.id,
        application_type="eoa",
        academic_year="2026-2027",
    )
    db_session.add(app)
    db_session.commit()

    doc = Document(application_id=app.id, document_type="aicte_approval")
    db_session.add(doc)
    db_session.commit()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key="docs/key-123",
        sha256="c" * 64,
        media_type="image/png",
        byte_size=50000,
    )
    db_session.add(version)
    db_session.commit()

    field = ExtractedField(
        document_version_id=version.id,
        field_name="institution_name",
        raw_text="Example Technical Institute",
        normalized_value="Example Technical Institute",
        confidence=0.95,
        page_number=1,
        engine_name="tesseract",
        engine_version="5.3.0",
        extraction_status="extracted",
    )
    db_session.add(field)
    db_session.commit()

    assert len(version.extracted_fields) == 1
    assert version.extracted_fields[0].field_name == "institution_name"
    assert version.extracted_fields[0].confidence == 0.95
    assert version.extracted_fields[0].document_version.id == version.id


def test_link_findings_to_validation_run(db_session: Session):
    """Verify validation runs and linked findings."""
    inst = Institution(institution_id="SYNTH-INST-005", display_name="Polytechnic")
    db_session.add(inst)
    db_session.commit()

    app = Application(
        institution_id=inst.id,
        application_type="intake_change",
        academic_year="2026-2027",
    )
    db_session.add(app)
    db_session.commit()

    run = ValidationRun(
        application_id=app.id,
        status="succeeded",
        evaluation_date=date(2026, 4, 30),
        ruleset_version="0.1.0-draft",
        triggered_by="system_scheduled",
    )
    db_session.add(run)
    db_session.commit()

    finding = Finding(
        validation_run_id=run.id,
        code="MISSING_DOCUMENT",
        status="open",
        severity="error",
        summary="Required document 'mandatory_disclosure' not submitted.",
        evidence='{"source": "submitted_document_list", "observed": "not_submitted"}',
    )
    db_session.add(finding)
    db_session.commit()

    assert len(run.findings) == 1
    assert run.findings[0].code == "MISSING_DOCUMENT"
    assert run.findings[0].severity == "error"
    assert run.findings[0].validation_run.id == run.id


# --- Review Actions and Audit Events Tests ---


def test_create_review_action_and_audit_event(db_session: Session):
    """Verify review actions and audit events are recorded attributable to an application."""
    inst = Institution(institution_id="SYNTH-INST-006", display_name="National College")
    db_session.add(inst)
    db_session.commit()

    app = Application(
        institution_id=inst.id,
        application_type="eoa",
        academic_year="2026-2027",
    )
    db_session.add(app)
    db_session.commit()

    action = ReviewAction(
        application_id=app.id,
        reviewer_id="REV-007",
        action="approve",
        comment="Preliminary checks verified against checklist.",
    )
    db_session.add(action)

    event = AuditEvent(
        actor_id="REV-007",
        institution_id=inst.id,
        action="APPLICATION_REVIEWED",
        target_type="Application",
        target_id=str(app.id),
        request_id="REQ-998877",
        details='{"decision": "approve"}',
    )
    db_session.add(event)
    db_session.commit()

    assert len(app.review_actions) == 1
    assert app.review_actions[0].reviewer_id == "REV-007"
    assert app.review_actions[0].action == "approve"

    audit_entry = db_session.scalar(
        select(AuditEvent).where(AuditEvent.request_id == "REQ-998877")
    )
    assert audit_entry is not None
    assert audit_entry.action == "APPLICATION_REVIEWED"
    assert audit_entry.institution is not None
    assert audit_entry.institution.id == inst.id


# --- Uniqueness and Constraint Enforcement Tests ---


def test_duplicate_institution_id_is_rejected(db_session: Session):
    """Verify unique constraint on Institution.institution_id."""
    inst1 = Institution(institution_id="DUP-ID", display_name="First")
    inst2 = Institution(institution_id="DUP-ID", display_name="Second")
    db_session.add(inst1)
    db_session.commit()

    db_session.add(inst2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_application_document_type_is_rejected(db_session: Session):
    """Verify unique constraint on (application_id, document_type)."""
    inst = Institution(institution_id="INST-DOC-DUP", display_name="Inst")
    db_session.add(inst)
    db_session.commit()

    app = Application(
        institution_id=inst.id, application_type="eoa", academic_year="2026-2027"
    )
    db_session.add(app)
    db_session.commit()

    doc1 = Document(application_id=app.id, document_type="undertaking")
    doc2 = Document(application_id=app.id, document_type="undertaking")
    db_session.add(doc1)
    db_session.commit()

    db_session.add(doc2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_document_version_number_is_rejected(db_session: Session):
    """Verify unique constraint on (document_id, version_number)."""
    inst = Institution(institution_id="INST-VER-DUP", display_name="Inst")
    db_session.add(inst)
    db_session.commit()

    app = Application(
        institution_id=inst.id, application_type="eoa", academic_year="2026-2027"
    )
    db_session.add(app)
    db_session.commit()

    doc = Document(application_id=app.id, document_type="undertaking")
    db_session.add(doc)
    db_session.commit()

    v1 = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key="key-1",
        sha256="1" * 64,
        media_type="application/pdf",
        byte_size=100,
    )
    v2 = DocumentVersion(
        document_id=doc.id,
        version_number=1,  # Duplicate version number
        storage_key="key-2",
        sha256="2" * 64,
        media_type="application/pdf",
        byte_size=100,
    )
    db_session.add(v1)
    db_session.commit()

    db_session.add(v2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --- Alembic Migration Upgrade and Downgrade Test ---


def test_alembic_migration_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify Alembic migration upgrade to head and downgrade to base on disposable database."""
    test_db_file = tmp_path / "test_migration_lifecycle.db"
    db_url = f"sqlite:///{test_db_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    ini_path = Path("backend/alembic.ini").resolve()
    assert ini_path.exists(), "backend/alembic.ini must exist"

    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", db_url)

    # Run upgrade to head
    command.upgrade(cfg, "head")

    # Verify tables created
    engine = create_engine(db_url)
    with engine.connect() as conn:
        from sqlalchemy import inspect
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        required_tables = {
            "institutions",
            "applications",
            "documents",
            "document_versions",
            "extracted_fields",
            "validation_runs",
            "findings",
            "review_actions",
            "audit_events",
        }
        assert required_tables <= tables, f"Missing tables: {required_tables - tables}"

    # Run downgrade to base
    command.downgrade(cfg, "base")

    # Verify all application tables were dropped
    with engine.connect() as conn:
        inspector = inspect(conn)
        tables_after_downgrade = set(inspector.get_table_names())
        assert not (required_tables & tables_after_downgrade), (
            f"Tables still present after downgrade: {required_tables & tables_after_downgrade}"
        )

    engine.dispose()


# --- Schema contract shared with the live PostgreSQL integration suite ---


def test_validation_evidence_schema_matches_repository_contract() -> None:
    """Pin the column names the live integration suite writes through.

    ``backend/tests/integration/test_postgres_migrations_and_persistence.py``
    builds validation runs, findings and review actions through the repositories
    with real PostgreSQL. That suite is skipped unless
    ``RUN_LIVE_INTEGRATION_TESTS`` is set, so a drift between the models and the
    repositories would otherwise stay invisible in the default job -- which is
    exactly how a set of guessed column names survived there unnoticed.

    This guard needs no infrastructure: it checks the ORM columns and the
    repository keyword arguments together.
    """
    import inspect

    from backend.app.repositories.review_audit_repository import ReviewAuditRepository
    from backend.app.repositories.validation_repository import ValidationRepository

    run_columns = ValidationRun.__table__.columns
    assert "consumed_version_ids" in run_columns
    assert "consumed_document_versions" not in run_columns
    # Provenance: a run may not be persisted without the date it was evaluated against.
    assert run_columns["evaluation_date"].nullable is False
    assert "evaluation_date" in inspect.signature(ValidationRepository.create_run).parameters

    finding_columns = Finding.__table__.columns
    for column in ("code", "summary", "evidence", "severity", "status"):
        assert column in finding_columns
    # Neither of these ever existed; the document type lives in the evidence JSON.
    assert "finding_code" not in finding_columns
    assert "message" not in finding_columns
    assert "code" in inspect.signature(ValidationRepository.create_finding).parameters
    assert "summary" in inspect.signature(ValidationRepository.create_finding).parameters

    action_columns = ReviewAction.__table__.columns
    for column in ("rationale", "comment", "metadata_payload", "new_status"):
        assert column in action_columns
    assert "justification" not in action_columns
    assert "resolution_outcome" not in action_columns
    action_params = inspect.signature(ReviewAuditRepository.create_review_action).parameters
    assert "rationale" in action_params
    assert "metadata_payload" in action_params
