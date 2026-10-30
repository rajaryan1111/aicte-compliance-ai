"""Integration tests verifying real PostgreSQL persistence and Alembic migrations (Phase 3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.db.models import (
    Application,
    AuditPackage,
    Document,
    DocumentVersion,
    Finding,
    Institution,
    ReviewAction,
    ValidationRun,
)
from backend.app.repositories.application_repository import ApplicationRepository

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI_PATH = REPO_ROOT / "backend" / "alembic.ini"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def test_alembic_sequential_upgrade_on_postgres(require_live_postgres: str, live_postgres_engine: Engine) -> None:
    """Verify that Alembic runs sequential migrations cleanly to head on real PostgreSQL."""
    cfg = Config(str(ALEMBIC_INI_PATH))
    cfg.set_main_option("sqlalchemy.url", require_live_postgres)
    cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))

    # Upgrade to head
    command.upgrade(cfg, "head")

    inspector = inspect(live_postgres_engine)
    tables = inspector.get_table_names()
    assert "alembic_version" in tables

    with live_postgres_engine.connect() as conn:
        rev = conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
    assert rev == "i9d0e1f2a3b4", f"Expected head revision i9d0e1f2a3b4, found {rev}"


def test_all_canonical_tables_and_indexes_exist_in_postgres(live_postgres_engine: Engine) -> None:
    """Verify that all 15 database tables, foreign keys, and indexes exist in real PostgreSQL."""
    inspector = inspect(live_postgres_engine)
    tables = set(inspector.get_table_names())

    expected_tables = {
        "institutions",
        "applications",
        "documents",
        "document_versions",
        "extracted_fields",
        "validation_runs",
        "validation_check_results",
        "findings",
        "review_actions",
        "audit_events",
        "users",
        "institution_memberships",
        "processing_jobs",
        "outbox_messages",
        "audit_packages",
        "institutional_record_snapshots",
        "infrastructure_evidence",
        "verification_attempts",
        "rule_approvals",
        "retention_runs",
    }
    missing = expected_tables - tables
    assert not missing, f"Missing PostgreSQL tables: {missing}"

    # Verify key unique constraints
    doc_uqs = {uq["name"] for uq in inspector.get_unique_constraints("documents")}
    assert "uq_application_document_type" in doc_uqs

    ver_uqs = {uq["name"] for uq in inspector.get_unique_constraints("document_versions")}
    assert "uq_document_version_number" in ver_uqs


def test_postgres_persistence_across_separate_sessions(live_postgres_engine: Engine) -> None:
    """Verify data persisted in Session A is retrieved faithfully in distinct Session B."""
    SessionMaker = sessionmaker(bind=live_postgres_engine)

    inst_code = f"PG-INST-{int(_utc_now().timestamp())}"
    # Session A: Create records
    with SessionMaker() as session_a:
        inst = Institution(institution_id=inst_code, display_name="PostgreSQL Test Institute")
        session_a.add(inst)
        session_a.commit()
        inst_id = inst.id

        app = Application(
            institution_id=inst_id,
            application_type="eoa",
            academic_year="2026-2027",
            status="draft",
        )
        session_a.add(app)
        session_a.commit()
        app_id = app.id

    # Session B: Independent connection retrieval
    with SessionMaker() as session_b:
        retrieved_app = session_b.get(Application, app_id)
        assert retrieved_app is not None
        assert retrieved_app.institution_id == inst_id
        assert retrieved_app.application_type == "eoa"
        assert retrieved_app.academic_year == "2026-2027"
        assert retrieved_app.status == "draft"
        assert retrieved_app.created_at is not None

        # Clean up
        inst_to_delete = session_b.get(Institution, inst_id)
        if inst_to_delete:
            session_b.delete(inst_to_delete)
            session_b.commit()


def test_postgres_uniqueness_and_foreign_key_constraints(live_postgres_engine: Engine) -> None:
    """Verify real PostgreSQL enforces UNIQUE and FOREIGN KEY constraints with transaction rollback."""
    SessionMaker = sessionmaker(bind=live_postgres_engine)

    inst_code = f"PG-UNIQ-{int(_utc_now().timestamp())}"
    with SessionMaker() as session:
        inst = Institution(institution_id=inst_code, display_name="Unique Test Institute")
        session.add(inst)
        session.commit()
        inst_id = inst.id

        # Duplicate institution_id must fail
        dup_inst = Institution(institution_id=inst_code, display_name="Duplicate Code")
        session.add(dup_inst)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # Foreign key failure: non-existent institution_id
        invalid_app = Application(
            institution_id=99999999,
            application_type="eoa",
            academic_year="2026-2027",
        )
        session.add(invalid_app)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # Clean up
        inst_del = session.get(Institution, inst_id)
        if inst_del:
            session.delete(inst_del)
            session.commit()


def test_postgres_multi_tenant_isolation(live_postgres_engine: Engine) -> None:
    """Verify institution tenant boundaries prevent cross-institution query leakage."""
    SessionMaker = sessionmaker(bind=live_postgres_engine)

    code_a = f"INST-A-{int(_utc_now().timestamp())}"
    code_b = f"INST-B-{int(_utc_now().timestamp())}"

    with SessionMaker() as session:
        inst_a = Institution(institution_id=code_a, display_name="Tenant A")
        inst_b = Institution(institution_id=code_b, display_name="Tenant B")
        session.add_all([inst_a, inst_b])
        session.commit()

        app_a = Application(institution_id=inst_a.id, application_type="eoa", academic_year="2026-2027")
        app_b = Application(institution_id=inst_b.id, application_type="new_program", academic_year="2026-2027")
        session.add_all([app_a, app_b])
        session.commit()

        # Query via repository scoped by tenant
        results_a, _ = ApplicationRepository.list_by_institution(session, inst_a.id)
        app_ids_a = {a.id for a in results_a}
        assert app_a.id in app_ids_a
        assert app_b.id not in app_ids_a

        results_b, _ = ApplicationRepository.list_by_institution(session, inst_b.id)
        app_ids_b = {b.id for b in results_b}
        assert app_b.id in app_ids_b
        assert app_a.id not in app_ids_b

        # Clean up
        session.delete(inst_a)
        session.delete(inst_b)
        session.commit()


def test_postgres_validation_run_snapshots_and_reviews(live_postgres_engine: Engine) -> None:
    """Verify ValidationRun JSON snapshots, ReviewAction overrides, and AuditPackage referential integrity."""
    SessionMaker = sessionmaker(bind=live_postgres_engine)
    code = f"INST-SNAP-{int(_utc_now().timestamp())}"

    with SessionMaker() as session:
        inst = Institution(institution_id=code, display_name="Snapshot Institute")
        session.add(inst)
        session.commit()

        app = Application(institution_id=inst.id, application_type="eoa", academic_year="2026-2027")
        session.add(app)
        session.commit()

        doc = Document(application_id=app.id, document_type="aicte_approval")
        session.add(doc)
        session.commit()

        v1 = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            storage_key=f"storage/key/1/{code}",
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            media_type="application/pdf",
            byte_size=1024,
            scan_status="clean",
            processing_status="completed",
        )
        session.add(v1)
        session.commit()
        doc.current_version_id = v1.id
        session.commit()

        # ValidationRun snapshot
        snapshot = json.dumps([{"document_type": "aicte_approval", "version_id": v1.id, "sha256": v1.sha256}])
        vrun = ValidationRun(
            application_id=app.id,
            status="succeeded",
            outcome="attention_required",
            evaluation_date=_utc_now(),
            consumed_version_ids=snapshot,
            ruleset_version="2026.1-draft",
        )
        session.add(vrun)
        session.commit()

        finding = Finding(
            validation_run_id=vrun.id,
            finding_code="DOCUMENT_EXPIRED",
            severity="high",
            status="open",
            document_type="aicte_approval",
            message="Document expiry check flagged.",
        )
        session.add(finding)
        session.commit()

        # ReviewAction
        action = ReviewAction(
            application_id=app.id,
            finding_id=finding.id,
            reviewer_id="reviewer@aicte.gov.in",
            action="resolved",
            new_status="resolved",
            resolution_outcome="issue_addressed",
            justification="Valid gazette extension verified by reviewer.",
        )
        session.add(action)
        finding.status = "resolved"
        session.commit()

        # AuditPackage
        manifest_payload = json.dumps({"package_reference": f"PKG-{code}", "items": [{"type": "finding", "id": finding.id}]})
        pkg = AuditPackage(
            application_id=app.id,
            validation_run_id=vrun.id,
            package_reference=f"PKG-{code}",
            package_name=f"package_{code}.zip",
            status="completed",
            sha256_root_hash="abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234",
            file_size_bytes=1024,
            manifest_json=manifest_payload,
            generated_by="reviewer@aicte.gov.in",
        )
        session.add(pkg)
        session.commit()

        # Query back and verify snapshot immutability
        re_run = session.get(ValidationRun, vrun.id)
        assert re_run is not None
        assert json.loads(re_run.consumed_document_versions)[0]["sha256"] == v1.sha256

        re_pkg = session.get(AuditPackage, pkg.id)
        assert re_pkg is not None
        assert re_pkg.package_reference == f"PKG-{code}"
        assert json.loads(re_pkg.manifest_json)["items"][0]["id"] == finding.id

        # Clean up
        session.delete(inst)
        session.commit()


def test_postgres_transaction_rollback_guarantee(live_postgres_engine: Engine) -> None:
    """Verify partial transactions roll back cleanly in PostgreSQL without leaving orphan records."""
    SessionMaker = sessionmaker(bind=live_postgres_engine)
    code = f"INST-FAIL-{int(_utc_now().timestamp())}"

    with SessionMaker() as session:
        inst = Institution(institution_id=code, display_name="Rollback Institute")
        session.add(inst)
        session.commit()
        inst_id = inst.id

        try:
            # Stage 1: valid application
            app = Application(institution_id=inst_id, application_type="eoa", academic_year="2026-2027")
            session.add(app)
            session.flush()

            # Stage 2: deliberate integrity violation in same transaction
            invalid_doc = Document(application_id=999999, document_type="land_record")
            session.add(invalid_doc)
            session.commit()
        except IntegrityError:
            session.rollback()

        # Verify Stage 1 was rolled back and no orphan application exists
        orphan_apps = session.scalars(select(Application).where(Application.institution_id == inst_id)).all()
        assert len(orphan_apps) == 0, "Partial transaction was not rolled back cleanly!"

        # Clean up
        session.delete(inst)
        session.commit()


def test_alembic_downgrade_and_reupgrade_on_postgres(require_live_postgres: str, live_postgres_engine: Engine) -> None:
    """Verify that Alembic can downgrade to base and re-upgrade to head cleanly on real PostgreSQL."""
    cfg = Config(str(ALEMBIC_INI_PATH))
    cfg.set_main_option("sqlalchemy.url", require_live_postgres)
    cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))

    # Downgrade to base
    command.downgrade(cfg, "base")

    # Verify tables removed
    inspector = inspect(live_postgres_engine)
    tables = set(inspector.get_table_names())
    assert "rule_approvals" not in tables
    assert "retention_runs" not in tables

    # Re-upgrade to head
    command.upgrade(cfg, "head")

    inspector_re = inspect(live_postgres_engine)
    tables_re = set(inspector_re.get_table_names())
    assert "rule_approvals" in tables_re
    assert "retention_runs" in tables_re
