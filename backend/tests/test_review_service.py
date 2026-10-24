"""Unit and domain tests for ReviewService lifecycle, state machine, and persistence."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.rbac import (
    PERMISSION_FINDING_WAIVE,
    PERMISSION_REVIEW_ACTION,
    ROLE_AUDITOR,
    ROLE_INSTITUTION_ADMIN,
    ROLE_SCRUTINY_OFFICER,
)
from backend.app.db.base import Base
from backend.app.db.models import (
    Application,
    AuditEvent,
    Finding,
    Institution,
    InstitutionMembership,
    ReviewAction,
    User,
    ValidationCheckResult,
    ValidationRun,
)
from backend.app.schemas.review import ReviewActionCreateRequest
from backend.app.services.review_service import (
    InvalidReviewTransitionError,
    ReviewPermissionDeniedError,
    ReviewService,
    ReviewValidationError,
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
def setup_data(db_session: Session) -> dict[str, object]:
    institution = Institution(institution_id="INST-001", display_name="Test Engineering College")
    db_session.add(institution)
    db_session.flush()

    user_officer = User(username="officer_1", hashed_password="dummy_hash_for_test")
    user_admin = User(username="admin_1", hashed_password="dummy_hash_for_test")
    user_auditor = User(username="auditor_1", hashed_password="dummy_hash_for_test")
    db_session.add_all([user_officer, user_admin, user_auditor])
    db_session.flush()

    mem_officer = InstitutionMembership(
        user_id=user_officer.id,
        institution_id=institution.id,
        role=ROLE_SCRUTINY_OFFICER,
        is_active=True,
    )
    mem_admin = InstitutionMembership(
        user_id=user_admin.id,
        institution_id=institution.id,
        role=ROLE_INSTITUTION_ADMIN,
        is_active=True,
    )
    mem_auditor = InstitutionMembership(
        user_id=user_auditor.id,
        institution_id=institution.id,
        role=ROLE_AUDITOR,
        is_active=True,
    )
    db_session.add_all([mem_officer, mem_admin, mem_auditor])

    app = Application(
        institution_id=institution.id,
        application_type="eoa",
        academic_year="2026-2027",
        status="under_review",
    )
    db_session.add(app)
    db_session.flush()

    run = ValidationRun(
        application_id=app.id,
        status="completed",
        evaluation_date=date(2026, 4, 1),
        outcome="failed",
    )
    db_session.add(run)
    db_session.flush()

    check_res = ValidationCheckResult(
        validation_run_id=run.id,
        check_id="CHK_FIRE_NOC",
        check_name="Fire Safety NOC Verification",
        category="safety",
        status="failed",
        message="Fire Safety Certificate has expired.",
    )
    db_session.add(check_res)
    db_session.flush()

    finding = Finding(
        validation_run_id=run.id,
        code="CHK_FIRE_NOC",
        status="open",
        severity="high",
        summary="Expired Fire Safety NOC",
        evidence='{"source": "ocr_extraction", "expiry": "2025-12-31"}',
        version=1,
    )
    db_session.add(finding)
    db_session.commit()

    return {
        "institution": institution,
        "officer": user_officer,
        "admin": user_admin,
        "auditor": user_auditor,
        "application": app,
        "run": run,
        "check_result": check_res,
        "finding": finding,
    }


def test_acknowledge_finding_success(db_session: Session, setup_data: dict[str, object]):
    app: Application = setup_data["application"]  # type: ignore
    run: ValidationRun = setup_data["run"]  # type: ignore
    finding: Finding = setup_data["finding"]  # type: ignore
    officer: User = setup_data["officer"]  # type: ignore

    payload = ReviewActionCreateRequest(
        action="acknowledge",
        comment="Examined initial fire NOC finding.",
    )

    resp = ReviewService.record_review_action(
        db_session,
        application_id=app.id,
        run_id=run.id,
        finding_id=finding.id,
        user=officer,
        user_role=ROLE_SCRUTINY_OFFICER,
        payload=payload,
    )

    assert resp.finding.status == "acknowledged"
    assert resp.action.action == "acknowledge"
    assert resp.action.previous_status == "open"
    assert resp.action.new_status == "acknowledged"
    assert resp.action.reviewer_id == officer.username
    assert resp.action.actor_role == ROLE_SCRUTINY_OFFICER

    # Database state verification
    db_session.refresh(finding)
    assert finding.status == "acknowledged"
    assert finding.version == 2

    # Audit event created
    audit = db_session.query(AuditEvent).filter_by(target_id=str(finding.id)).first()
    assert audit is not None
    assert audit.action == "REVIEW_ACTION_RECORDED"
    assert audit.actor_id == officer.username


def test_comment_does_not_alter_status_or_automated_result(
    db_session: Session, setup_data: dict[str, object]
):
    app: Application = setup_data["application"]  # type: ignore
    run: ValidationRun = setup_data["run"]  # type: ignore
    finding: Finding = setup_data["finding"]  # type: ignore
    officer: User = setup_data["officer"]  # type: ignore
    check_result: ValidationCheckResult = setup_data["check_result"]  # type: ignore

    initial_version = finding.version

    payload = ReviewActionCreateRequest(
        action="comment",
        comment="Reviewing NOC validity with regional fire department.",
    )

    resp = ReviewService.record_review_action(
        db_session,
        application_id=app.id,
        run_id=run.id,
        finding_id=finding.id,
        user=officer,
        user_role=ROLE_SCRUTINY_OFFICER,
        payload=payload,
    )

    assert resp.finding.status == "open"
    assert resp.action.previous_status == "open"
    assert resp.action.new_status == "open"

    db_session.refresh(finding)
    assert finding.status == "open"
    assert finding.version == initial_version  # comment does not mutate state version

    # Automated check result must remain failed
    db_session.refresh(check_result)
    assert check_result.status == "failed"


def test_resolve_finding_requires_rationale(db_session: Session, setup_data: dict[str, object]):
    app: Application = setup_data["application"]  # type: ignore
    run: ValidationRun = setup_data["run"]  # type: ignore
    finding: Finding = setup_data["finding"]  # type: ignore
    officer: User = setup_data["officer"]  # type: ignore

    # Missing rationale must fail
    invalid_payload = ReviewActionCreateRequest(
        action="resolve",
        comment="Resolving finding without rationale",
    )
    with pytest.raises(ReviewValidationError, match="rationale"):
        ReviewService.record_review_action(
            db_session,
            application_id=app.id,
            run_id=run.id,
            finding_id=finding.id,
            user=officer,
            user_role=ROLE_SCRUTINY_OFFICER,
            payload=invalid_payload,
        )

    # Valid resolution with rationale
    valid_payload = ReviewActionCreateRequest(
        action="resolve",
        rationale="Institution submitted renewed Fire Safety NOC valid through 2027.",
        resolution_outcome="issue_addressed",
        evidence_ref="doc_ver_12",
    )
    resp = ReviewService.record_review_action(
        db_session,
        application_id=app.id,
        run_id=run.id,
        finding_id=finding.id,
        user=officer,
        user_role=ROLE_SCRUTINY_OFFICER,
        payload=valid_payload,
    )

    assert resp.finding.status == "resolved"
    db_session.refresh(finding)
    assert finding.status == "resolved"
    assert finding.resolved_by == officer.username
    assert finding.resolution_rationale == valid_payload.rationale
    assert finding.resolved_at is not None


def test_reopen_resolved_finding(db_session: Session, setup_data: dict[str, object]):
    app: Application = setup_data["application"]  # type: ignore
    run: ValidationRun = setup_data["run"]  # type: ignore
    finding: Finding = setup_data["finding"]  # type: ignore
    officer: User = setup_data["officer"]  # type: ignore

    # First resolve
    resolve_payload = ReviewActionCreateRequest(
        action="resolve",
        rationale="Preliminary resolution.",
    )
    ReviewService.record_review_action(
        db_session,
        application_id=app.id,
        run_id=run.id,
        finding_id=finding.id,
        user=officer,
        user_role=ROLE_SCRUTINY_OFFICER,
        payload=resolve_payload,
    )

    # Now reopen without rationale should fail
    with pytest.raises(ReviewValidationError, match="rationale"):
        ReviewService.record_review_action(
            db_session,
            application_id=app.id,
            run_id=run.id,
            finding_id=finding.id,
            user=officer,
            user_role=ROLE_SCRUTINY_OFFICER,
            payload=ReviewActionCreateRequest(action="reopen"),
        )

    # Reopen with rationale succeeds
    reopen_payload = ReviewActionCreateRequest(
        action="reopen",
        rationale="Fire NOC verification failed upon secondary verification.",
    )
    resp = ReviewService.record_review_action(
        db_session,
        application_id=app.id,
        run_id=run.id,
        finding_id=finding.id,
        user=officer,
        user_role=ROLE_SCRUTINY_OFFICER,
        payload=reopen_payload,
    )

    assert resp.finding.status == "open"
    db_session.refresh(finding)
    assert finding.status == "open"
    assert finding.resolved_by is None
    assert finding.resolution_rationale is None


def test_escalate_and_request_info(db_session: Session, setup_data: dict[str, object]):
    app: Application = setup_data["application"]  # type: ignore
    run: ValidationRun = setup_data["run"]  # type: ignore
    finding: Finding = setup_data["finding"]  # type: ignore
    officer: User = setup_data["officer"]  # type: ignore

    # Request information requires comment
    with pytest.raises(ReviewValidationError, match="comment"):
        ReviewService.record_review_action(
            db_session,
            application_id=app.id,
            run_id=run.id,
            finding_id=finding.id,
            user=officer,
            user_role=ROLE_SCRUTINY_OFFICER,
            payload=ReviewActionCreateRequest(action="request_information"),
        )

    req_info_payload = ReviewActionCreateRequest(
        action="request_information",
        comment="Please upload page 2 of the Fire Safety certificate containing the seal.",
    )
    resp = ReviewService.record_review_action(
        db_session,
        application_id=app.id,
        run_id=run.id,
        finding_id=finding.id,
        user=officer,
        user_role=ROLE_SCRUTINY_OFFICER,
        payload=req_info_payload,
    )
    assert resp.finding.status == "under_review"

    # Escalate requires rationale
    with pytest.raises(ReviewValidationError, match="rationale"):
        ReviewService.record_review_action(
            db_session,
            application_id=app.id,
            run_id=run.id,
            finding_id=finding.id,
            user=officer,
            user_role=ROLE_SCRUTINY_OFFICER,
            payload=ReviewActionCreateRequest(action="escalate"),
        )

    esc_payload = ReviewActionCreateRequest(
        action="escalate",
        rationale="Complex discrepancy in multi-building fire clearance requires committee review.",
    )
    resp_esc = ReviewService.record_review_action(
        db_session,
        application_id=app.id,
        run_id=run.id,
        finding_id=finding.id,
        user=officer,
        user_role=ROLE_SCRUTINY_OFFICER,
        payload=esc_payload,
    )
    assert resp_esc.finding.status == "escalated"


def test_waiver_policy_and_authorization(db_session: Session, setup_data: dict[str, object]):
    app: Application = setup_data["application"]  # type: ignore
    run: ValidationRun = setup_data["run"]  # type: ignore
    finding: Finding = setup_data["finding"]  # type: ignore
    officer: User = setup_data["officer"]  # type: ignore

    # Officer without finding:waive permission cannot waive
    waive_payload = ReviewActionCreateRequest(
        action="waive",
        rationale="Demonstration waiver for advisory finding.",
    )
    with pytest.raises(ReviewPermissionDeniedError, match="finding:waive"):
        ReviewService.record_review_action(
            db_session,
            application_id=app.id,
            run_id=run.id,
            finding_id=finding.id,
            user=officer,
            user_role=ROLE_SCRUTINY_OFFICER,
            payload=waive_payload,
            user_permissions={PERMISSION_REVIEW_ACTION},  # lacks PERMISSION_FINDING_WAIVE
        )

    # Statutory non-waivable check fails policy gate even with permission
    finding.code = "LAND_AREA_REQUIREMENT"
    db_session.commit()

    with pytest.raises(ReviewPermissionDeniedError, match="Statutory regulatory requirement"):
        ReviewService.record_review_action(
            db_session,
            application_id=app.id,
            run_id=run.id,
            finding_id=finding.id,
            user=officer,
            user_role=ROLE_SCRUTINY_OFFICER,
            payload=waive_payload,
            user_permissions={PERMISSION_REVIEW_ACTION, PERMISSION_FINDING_WAIVE},
        )

    # Synthetic demo finding with permission succeeds
    finding.code = "DEMO_FACULTY_CADRE_RATIO"
    db_session.commit()

    resp = ReviewService.record_review_action(
        db_session,
        application_id=app.id,
        run_id=run.id,
        finding_id=finding.id,
        user=officer,
        user_role=ROLE_SCRUTINY_OFFICER,
        payload=waive_payload,
        user_permissions={PERMISSION_REVIEW_ACTION, PERMISSION_FINDING_WAIVE},
    )
    assert resp.finding.status == "waived"


def test_invalid_state_transitions_rejected(db_session: Session, setup_data: dict[str, object]):
    app: Application = setup_data["application"]  # type: ignore
    run: ValidationRun = setup_data["run"]  # type: ignore
    finding: Finding = setup_data["finding"]  # type: ignore
    officer: User = setup_data["officer"]  # type: ignore

    # open -> reopen is invalid
    with pytest.raises(InvalidReviewTransitionError):
        ReviewService.record_review_action(
            db_session,
            application_id=app.id,
            run_id=run.id,
            finding_id=finding.id,
            user=officer,
            user_role=ROLE_SCRUTINY_OFFICER,
            payload=ReviewActionCreateRequest(action="reopen", rationale="reopen open finding"),
        )


def test_immutable_review_history_preserved(db_session: Session, setup_data: dict[str, object]):
    app: Application = setup_data["application"]  # type: ignore
    run: ValidationRun = setup_data["run"]  # type: ignore
    finding: Finding = setup_data["finding"]  # type: ignore
    officer: User = setup_data["officer"]  # type: ignore

    # 1. Acknowledge
    ReviewService.record_review_action(
        db_session,
        application_id=app.id,
        run_id=run.id,
        finding_id=finding.id,
        user=officer,
        user_role=ROLE_SCRUTINY_OFFICER,
        payload=ReviewActionCreateRequest(action="acknowledge"),
    )

    # 2. Add comment
    ReviewService.record_review_action(
        db_session,
        application_id=app.id,
        run_id=run.id,
        finding_id=finding.id,
        user=officer,
        user_role=ROLE_SCRUTINY_OFFICER,
        payload=ReviewActionCreateRequest(action="comment", comment="First comment"),
    )

    # 3. Resolve
    ReviewService.record_review_action(
        db_session,
        application_id=app.id,
        run_id=run.id,
        finding_id=finding.id,
        user=officer,
        user_role=ROLE_SCRUTINY_OFFICER,
        payload=ReviewActionCreateRequest(action="resolve", rationale="Resolution rationale"),
    )

    history = ReviewService.get_finding_with_history(
        db_session,
        application_id=app.id,
        run_id=run.id,
        finding_id=finding.id,
    )

    assert len(history.review_actions) == 3
    assert history.review_actions[0].action == "acknowledge"
    assert history.review_actions[1].action == "comment"
    assert history.review_actions[2].action == "resolve"

    # All actions persisted and distinct
    actions = db_session.query(ReviewAction).filter_by(finding_id=finding.id).all()
    assert len(actions) == 3


def test_review_summary_accurate_counts(db_session: Session, setup_data: dict[str, object]):
    app: Application = setup_data["application"]  # type: ignore
    run: ValidationRun = setup_data["run"]  # type: ignore
    finding: Finding = setup_data["finding"]  # type: ignore
    officer: User = setup_data["officer"]  # type: ignore

    # Initial summary: 1 open finding
    summary = ReviewService.get_application_review_summary(db_session, app.id)
    assert summary.total_findings == 1
    assert summary.open_count == 1
    assert summary.resolved_count == 0
    assert summary.pending_action_count == 1

    # Resolve the finding
    ReviewService.record_review_action(
        db_session,
        application_id=app.id,
        run_id=run.id,
        finding_id=finding.id,
        user=officer,
        user_role=ROLE_SCRUTINY_OFFICER,
        payload=ReviewActionCreateRequest(
            action="resolve",
            rationale="Resolved with verified certificate.",
            resolution_outcome="issue_addressed",
        ),
    )

    summary_after = ReviewService.get_application_review_summary(db_session, app.id)
    assert summary_after.total_findings == 1
    assert summary_after.open_count == 0
    assert summary_after.resolved_count == 1
    assert summary_after.pending_action_count == 0
    assert len(summary_after.recent_actions) == 1


def test_reviewer_queue_filtering(db_session: Session, setup_data: dict[str, object]):
    app: Application = setup_data["application"]  # type: ignore
    officer: User = setup_data["officer"]  # type: ignore
    inst: Institution = setup_data["institution"]  # type: ignore

    queue = ReviewService.get_reviewer_queue(
        db_session,
        user=officer,
        authorized_institution_ids=[inst.id],
        status_filter="open",
        severity_filter="high",
    )
    assert queue.total == 1
    assert len(queue.items) == 1
    assert queue.items[0].finding.code == "CHK_FIRE_NOC"
    assert queue.items[0].application_id == app.id


def test_transaction_rollback_preserves_state(
    db_session: Session, setup_data: dict[str, object]
):
    app: Application = setup_data["application"]  # type: ignore
    run: ValidationRun = setup_data["run"]  # type: ignore
    finding: Finding = setup_data["finding"]  # type: ignore
    officer: User = setup_data["officer"]  # type: ignore

    initial_version = finding.version
    initial_status = finding.status

    # Submitting an invalid action that raises an error should not change database state
    with pytest.raises(InvalidReviewTransitionError):
        ReviewService.record_review_action(
            db_session,
            application_id=app.id,
            run_id=run.id,
            finding_id=finding.id,
            user=officer,
            user_role=ROLE_SCRUTINY_OFFICER,
            payload=ReviewActionCreateRequest(action="reopen", rationale="invalid reopen"),
        )

    db_session.rollback()
    db_session.refresh(finding)
    assert finding.status == initial_status
    assert finding.version == initial_version
    actions = db_session.query(ReviewAction).filter_by(finding_id=finding.id).all()
    assert len(actions) == 0

