"""Tests for hardened regulatory rule approval governance, RBAC, supersession, and validation integration."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.rbac import (
    PERMISSION_RULE_APPROVE,
    PERMISSION_RULE_VERIFY,
    ROLE_INSTITUTION_ADMIN,
    ROLE_SCRUTINY_OFFICER,
    ROLE_REGULATORY_DIRECTOR,
)
from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
    AuditEvent,
    Document,
    DocumentVersion,
    ExtractedField,
    Institution,
    RuleApprovalRecord,
    User,
)
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
from backend.app.services.rule_engine import (
    AICTE_APH_DOCUMENT_SHA256,
    RuleApprovalService,
    RuleEngineService,
    RuleEvaluationContext,
    build_aph_draft_rules,
)
from backend.app.services.validation_orchestration_service import ValidationOrchestrationService


@pytest.fixture
def db_session():
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


def test_rule_approval_permission_enforcement(db_session: Session):
    officer_user = User(
        id=101,
        username="case_officer_bob",
        hashed_password="hash",
    )
    officer_user.role = ROLE_SCRUTINY_OFFICER
    db_session.add(officer_user)
    db_session.commit()

    draft = build_aph_draft_rules()[0]

    with pytest.raises(PermissionError, match="lacks PERMISSION_RULE_APPROVE"):
        RuleApprovalService.approve_rule_db(
            db_session,
            rule_draft=draft,
            reviewer_user=officer_user,
            rationale="Attempting unauthorized rule approval.",
        )


def test_rule_approval_generic_string_rejected(db_session: Session):
    draft = build_aph_draft_rules()[0]
    with pytest.raises(ValueError, match="Reviewer identity must be an authenticated User entity"):
        RuleApprovalService.approve_rule_db(
            db_session,
            rule_draft=draft,
            reviewer_user=None,  # type: ignore
            rationale="Attempt with no authenticated user.",
        )


def test_rule_approval_blocked_without_source_verification(db_session: Session):
    director = User(
        id=102,
        username="director_sharma",
        hashed_password="hash",
    )
    director.role = ROLE_REGULATORY_DIRECTOR
    db_session.add(director)
    db_session.commit()

    # Unverified draft must be blocked from approval
    draft = build_aph_draft_rules()[0]
    assert draft.source_provenance.status == SourceVerificationStatus.UNVERIFIED

    with pytest.raises(ValueError, match="Source provenance must be verified before statutory approval"):
        RuleApprovalService.approve_rule_db(
            db_session,
            rule_draft=draft,
            reviewer_user=director,
            rationale="Attempting approval without source verification.",
            statutory_interpretation_approved=True,
        )


def test_source_verification_permission_and_hash_enforcement(db_session: Session):
    officer = User(id=110, username="officer_alice", hashed_password="hash")
    officer.role = ROLE_SCRUTINY_OFFICER
    director = User(id=111, username="director_raman", hashed_password="hash")
    director.role = ROLE_REGULATORY_DIRECTOR
    db_session.add_all([officer, director])
    db_session.commit()

    draft = build_aph_draft_rules()[0]

    # 1. Scrutiny officer lacks PERMISSION_RULE_VERIFY
    with pytest.raises(PermissionError, match="lacks PERMISSION_RULE_VERIFY"):
        RuleApprovalService.verify_source_db(
            db_session,
            rule_draft=draft,
            verifier_user=officer,
            document_sha256=AICTE_APH_DOCUMENT_SHA256,
            rationale="Unauthorized source verification attempt.",
        )

    # 2. Invalid SHA-256 format rejected
    with pytest.raises(ValueError, match="64-character lowercase hexadecimal"):
        RuleApprovalService.verify_source_db(
            db_session,
            rule_draft=draft,
            verifier_user=director,
            document_sha256="not_a_valid_hash",
            rationale="Verification with bad hash.",
        )

    # 3. Successful source verification
    verified_draft = RuleApprovalService.verify_source_db(
        db_session,
        rule_draft=draft,
        verifier_user=director,
        document_sha256=AICTE_APH_DOCUMENT_SHA256,
        rationale="Authoritative APH 2024-27 PDF retrieved from AICTE portal and cryptographically verified.",
    )
    assert verified_draft.source_provenance.status == SourceVerificationStatus.VERIFIED
    assert verified_draft.source_provenance.verified_by == "director_raman"
    assert verified_draft.source_provenance.document_sha256 == AICTE_APH_DOCUMENT_SHA256

    # Verify AuditEvent
    audit_events = list(
        db_session.scalars(
            select(AuditEvent).where(AuditEvent.action == "REGULATORY_SOURCE_VERIFIED")
        ).all()
    )
    assert len(audit_events) == 1
    assert audit_events[0].actor_id == "director_raman"


def test_rule_approval_durable_persistence_and_audit(db_session: Session):
    director = User(
        id=103,
        username="director_verma",
        hashed_password="hash",
    )
    director.role = ROLE_REGULATORY_DIRECTOR
    db_session.add(director)
    db_session.commit()

    draft = build_aph_draft_rules()[0]

    # Step 1: Source verification
    verified_draft = RuleApprovalService.verify_source_db(
        db_session,
        rule_draft=draft,
        verifier_user=director,
        document_sha256=AICTE_APH_DOCUMENT_SHA256,
        rationale="Cryptographically verified against official AICTE APH PDF.",
    )

    # Step 2: Statutory interpretation approval
    approval_rec = RuleApprovalService.approve_rule_db(
        db_session,
        rule_draft=verified_draft,
        reviewer_user=director,
        rationale="Approved after scrutiny of AICTE APH 2024-27 Clause 2.4 and Annexure-2.",
        statutory_interpretation_approved=True,
    )

    assert approval_rec.id is not None
    assert approval_rec.rule_id == draft.rule_id
    assert approval_rec.rule_version == draft.version
    assert approval_rec.status == "active"
    assert approval_rec.decision == "approved"
    assert approval_rec.reviewer_username == "director_verma"
    assert approval_rec.reviewer_role == ROLE_REGULATORY_DIRECTOR
    assert approval_rec.source_clause == draft.source_clause
    assert approval_rec.source_document_sha256 == AICTE_APH_DOCUMENT_SHA256
    assert approval_rec.statutory_interpretation_approved is True

    # Verify AuditEvent for approval
    audit_events = list(
        db_session.scalars(
            select(AuditEvent).where(AuditEvent.action == "REGULATORY_RULE_APPROVED")
        ).all()
    )
    assert len(audit_events) == 1
    assert audit_events[0].actor_id == "director_verma"
    details = json.loads(audit_events[0].details or "{}")
    assert details["rule_id"] == draft.rule_id
    assert details["statutory_interpretation_approved"] is True


def test_rule_supersession_governance(db_session: Session):
    director = User(
        id=104,
        username="director_patel",
        hashed_password="hash",
    )
    director.role = ROLE_REGULATORY_DIRECTOR
    db_session.add(director)
    db_session.commit()

    draft_v1 = build_aph_draft_rules()[0]
    verified_v1 = RuleApprovalService.verify_source_db(
        db_session,
        rule_draft=draft_v1,
        verifier_user=director,
        document_sha256=AICTE_APH_DOCUMENT_SHA256,
        rationale="Attributable verification of version 1.",
    )
    rec_v1 = RuleApprovalService.approve_rule_db(
        db_session,
        rule_draft=verified_v1,
        reviewer_user=director,
        rationale="Approval of version 1.",
    )
    assert rec_v1.status == "active"

    # Create version 2 draft and verify
    draft_v2 = verified_v1.model_copy(update={"version": 2, "title": "Updated Fire Safety Rule V2"}, deep=True)

    rec_v2 = RuleApprovalService.approve_rule_db(
        db_session,
        rule_draft=draft_v2,
        reviewer_user=director,
        rationale="Approval of version 2 superseding version 1.",
    )

    db_session.refresh(rec_v1)
    assert rec_v1.status == "superseded"
    assert rec_v2.status == "active"
    assert rec_v2.rule_version == 2

    # Verify supersession audit event
    super_events = list(
        db_session.scalars(
            select(AuditEvent).where(AuditEvent.action == "REGULATORY_RULE_SUPERSEDED")
        ).all()
    )
    assert len(super_events) == 1
    details = json.loads(super_events[0].details or "{}")
    assert details["superseded_version"] == 1
    assert details["new_version"] == 2


def test_unapproved_rules_kept_inactive_in_validation(db_session: Session):
    inst = Institution(institution_id="INST-GOV-01", display_name="Engineering College")
    db_session.add(inst)
    db_session.flush()

    app = Application(
        institution_id=inst.id,
        application_type="eoa",
        academic_year="2026-2027",
        status="under_review",
    )
    db_session.add(app)
    db_session.flush()

    doc = Document(application_id=app.id, document_type="fire_safety_certificate")
    db_session.add(doc)
    db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key="fire_cert.pdf",
        sha256="1234567890123456789012345678901234567890123456789012345678901234",
        media_type="application/pdf",
        byte_size=2048,
        scan_status="clean",
        processing_status="succeeded",
    )
    db_session.add(ver)
    db_session.commit()

    service = ValidationOrchestrationService(rule_registry=RuleRegistry())
    run = service.run_validation(db_session, application_id=app.id)

    # Check results: CHECK_OFFICIAL_REGULATORY_RULES must be not_run because no approved rules exist
    statutory_checks = [c for c in run.check_results if c.check_id == "CHECK_OFFICIAL_REGULATORY_RULES"]
    assert len(statutory_checks) == 1
    assert statutory_checks[0].status == "not_run"
    assert "no active, approved statutory rules" in statutory_checks[0].message.lower()


def test_validation_evaluates_db_approved_rules(db_session: Session):
    director = User(
        id=105,
        username="director_rao",
        hashed_password="hash",
    )
    director.role = ROLE_REGULATORY_DIRECTOR
    db_session.add(director)
    db_session.commit()

    # Step 1 & 2: Verify and Approve all 6 canonical rules
    for draft in build_aph_draft_rules():
        verified = RuleApprovalService.verify_source_db(
            db_session,
            rule_draft=draft,
            verifier_user=director,
            document_sha256=AICTE_APH_DOCUMENT_SHA256,
            rationale="Authoritative source verification against APH 2024-2027.",
        )
        RuleApprovalService.approve_rule_db(
            db_session,
            rule_draft=verified,
            reviewer_user=director,
            rationale="Statutory approval under APH 2024-2027 norms.",
        )

    # Setup application with valid fire certificate
    inst = Institution(institution_id="INST-GOV-02", display_name="Tech Institute")
    db_session.add(inst)
    db_session.flush()

    app = Application(
        institution_id=inst.id,
        application_type="eoa",
        academic_year="2026-2027",
        status="under_review",
    )
    db_session.add(app)
    db_session.flush()

    doc = Document(application_id=app.id, document_type="fire_safety_certificate")
    db_session.add(doc)
    db_session.flush()

    future_exp = (date.today() + timedelta(days=365)).isoformat()
    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key="valid_fire.pdf",
        sha256="abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdef",
        media_type="application/pdf",
        byte_size=2048,
        scan_status="clean",
        processing_status="succeeded",
    )
    db_session.add(ver)
    db_session.flush()
    doc.current_version_id = ver.id

    f_exp = ExtractedField(
        document_version_id=ver.id,
        field_name="valid_until",
        raw_text=future_exp,
        normalized_value=future_exp,
        confidence=0.99,
        engine_name="test_ocr",
    )
    db_session.add(f_exp)
    db_session.commit()

    service = ValidationOrchestrationService(rule_registry=RuleRegistry())
    run = service.run_validation(db_session, application_id=app.id)

    # Approved rules must have run
    rule_checks = [c for c in run.check_results if c.check_id.startswith("RULE_")]
    assert len(rule_checks) >= 1
    fire_check = next((c for c in rule_checks if "FIRE_SAFETY" in c.check_id), None)
    assert fire_check is not None
    assert fire_check.status == "passed"
