"""Human review, finding resolution, and auditor workflow service.

Coordinates:
- Verification of review permissions and institutional tenant scope.
- State machine enforcement for finding review lifecycles.
- Recording immutable, attributable review actions and comments.
- Optimistic concurrency control via finding versioning.
- Safe idempotency handling via client request identifiers.
- Attributable audit event logging.
- Review queue aggregation and summary count derivation.

Automated findings and validation runs are strictly preserved and never overwritten
by human decisions. All outcomes are advisory and do not constitute official AICTE
statutory approval.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging

from sqlalchemy.orm import Session

from backend.app.core.rbac import (
    PERMISSION_FINDING_WAIVE,
    PERMISSION_REVIEW_ACTION,
    ROLE_AUDITOR,
    ROLE_INSTITUTION_ADMIN,
    ROLE_PERMISSIONS,
)
from backend.app.db.models import Application, Finding, User, ValidationRun
from backend.app.repositories.review_audit_repository import ReviewAuditRepository
from backend.app.schemas.review import (
    FindingWithReviewRead,
    ReviewActionCreateRequest,
    ReviewActionRead,
    ReviewActionResponse,
    ReviewQueueItemRead,
    ReviewQueueResponse,
    ReviewSummaryResponse,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReviewError(Exception):
    """Base exception for review domain errors."""


class FindingNotFoundError(ReviewError):
    """Finding not found in the given application and validation run scope."""


class InvalidReviewTransitionError(ReviewError):
    """Requested transition violates the allowed review lifecycle."""


class ReviewValidationError(ReviewError):
    """Required rationale, comment, or payload fields are missing or invalid."""


class ReviewConcurrencyConflictError(ReviewError):
    """Optimistic concurrency conflict on finding version."""


class ReviewPermissionDeniedError(ReviewError):
    """User role lacks required permission for this review operation."""


# Allowed transition matrix: action -> set of valid previous statuses
VALID_TRANSITIONS: dict[str, set[str]] = {
    "acknowledge": {"open"},
    "comment": {"open", "acknowledged", "under_review", "escalated", "resolved", "waived"},
    "request_information": {"open", "acknowledged", "under_review", "escalated"},
    "resolve": {"open", "acknowledged", "under_review", "escalated"},
    "escalate": {"open", "acknowledged", "under_review"},
    "waive": {"open", "acknowledged", "under_review", "escalated"},
    "reopen": {"resolved", "waived", "escalated"},
}

# Resulting status for each state-changing action
ACTION_RESULT_STATUS: dict[str, str | None] = {
    "acknowledge": "acknowledged",
    "comment": None,  # preserves current status
    "request_information": "under_review",
    "resolve": "resolved",
    "escalate": "escalated",
    "waive": "waived",
    "reopen": "open",
}


class ReviewService:
    """Service orchestrating human review actions, finding resolution, and queues."""

    @classmethod
    def get_application_review_summary(
        cls,
        db: Session,
        application_id: int,
    ) -> ReviewSummaryResponse:
        """Derive consolidated review summary and action counts for an application."""
        app = db.get(Application, application_id)
        if app is None:
            raise FindingNotFoundError(f"Application {application_id} not found.")

        counts = ReviewAuditRepository.get_review_summary_counts(db, application_id)
        recent_records = ReviewAuditRepository.list_review_actions(db, application_id, limit=10)

        total_findings = sum(counts.values())
        pending_action = counts.get("open", 0) + counts.get("under_review", 0) + counts.get("escalated", 0)

        return ReviewSummaryResponse(
            application_id=app.id,
            application_type=app.application_type,
            academic_year=app.academic_year,
            institution_id=app.institution.institution_id if app.institution else str(app.institution_id),
            total_findings=total_findings,
            open_count=counts.get("open", 0),
            acknowledged_count=counts.get("acknowledged", 0),
            under_review_count=counts.get("under_review", 0),
            resolved_count=counts.get("resolved", 0),
            escalated_count=counts.get("escalated", 0),
            waived_count=counts.get("waived", 0),
            pending_action_count=pending_action,
            recent_actions=[ReviewActionRead.model_validate(r) for r in recent_records],
            generated_at=_utc_now(),
        )

    @classmethod
    def get_finding_with_history(
        cls,
        db: Session,
        application_id: int,
        run_id: int,
        finding_id: int,
    ) -> FindingWithReviewRead:
        """Retrieve finding details, current review state, and chronological action history."""
        finding = db.get(Finding, finding_id)
        if finding is None:
            raise FindingNotFoundError(f"Finding {finding_id} not found.")

        run = db.get(ValidationRun, run_id)
        if run is None or run.application_id != application_id or finding.validation_run_id != run.id:
            raise FindingNotFoundError(f"Finding {finding_id} does not belong to run {run_id} and application {application_id}.")

        actions = ReviewAuditRepository.list_review_actions_for_finding(db, finding_id)
        finding_read = FindingWithReviewRead.model_validate(finding)
        finding_read.review_actions = [ReviewActionRead.model_validate(a) for a in actions]
        return finding_read

    @classmethod
    def record_review_action(
        cls,
        db: Session,
        *,
        application_id: int,
        run_id: int,
        finding_id: int,
        user: User,
        user_role: str,
        payload: ReviewActionCreateRequest,
        user_permissions: set[str] | frozenset[str] | None = None,
    ) -> ReviewActionResponse:
        """Validate, authorize, and record an attributable review action on a finding."""
        app = db.get(Application, application_id)
        if app is None:
            raise FindingNotFoundError(f"Application {application_id} not found.")

        run = db.get(ValidationRun, run_id)
        if run is None or run.application_id != application_id:
            raise FindingNotFoundError(f"Validation run {run_id} not found on application {application_id}.")

        finding = db.get(Finding, finding_id)
        if finding is None or finding.validation_run_id != run.id:
            raise FindingNotFoundError(f"Finding {finding_id} not found on run {run_id}.")

        action = payload.action

        # ----------------------------------------------------------------------
        # 1. RBAC and Permission Enforcement
        # ----------------------------------------------------------------------
        effective_permissions = set(ROLE_PERMISSIONS.get(user_role, set()))
        if user_permissions:
            effective_permissions.update(user_permissions)

        if user_role == ROLE_AUDITOR:
            raise ReviewPermissionDeniedError("Auditor role has read-only access and cannot submit review actions.")

        if user_role == ROLE_INSTITUTION_ADMIN:
            # Institution admin may only comment; cannot resolve, waive, escalate, or reopen
            if action != "comment":
                raise ReviewPermissionDeniedError(
                    f"Institution administrator is restricted to submitting comments; action '{action}' is reserved for scrutiny officers."
                )

        if PERMISSION_REVIEW_ACTION not in effective_permissions and action != "comment":
            raise ReviewPermissionDeniedError(f"Role '{user_role}' lacks review:action permission.")

        if action == "waive":
            # Waiver requires dedicated finding:waive permission
            if PERMISSION_FINDING_WAIVE not in effective_permissions:
                raise ReviewPermissionDeniedError(
                    "Action 'waive' requires dedicated 'finding:waive' permission. Scrutiny officer must obtain waiver authorization."
                )
            # Safeguard: prevent waiving non-synthetic statutory rules if unverified
            if (
                finding.code.startswith("STATUTORY_")
                or "LAND" in finding.code
                or "STATUTORY" in finding.code
            ):
                raise ReviewPermissionDeniedError(
                    "Statutory regulatory requirements cannot be waived; permitted only on advisory or demonstration findings."
                )

        # ----------------------------------------------------------------------
        # 2. Idempotency Check
        # ----------------------------------------------------------------------
        if payload.request_id:
            existing_action = ReviewAuditRepository.get_review_action_by_request_id(
                db, finding.id, payload.request_id
            )
            if existing_action is not None:
                logger.info("Idempotent retry detected for request_id %s; returning existing action.", payload.request_id)
                actions = ReviewAuditRepository.list_review_actions_for_finding(db, finding.id)
                finding_read = FindingWithReviewRead.model_validate(finding)
                finding_read.review_actions = [ReviewActionRead.model_validate(a) for a in actions]
                return ReviewActionResponse(
                    finding=finding_read,
                    action=ReviewActionRead.model_validate(existing_action),
                    message="Action was previously recorded (idempotent request).",
                )

        # ----------------------------------------------------------------------
        # 3. Optimistic Concurrency Control
        # ----------------------------------------------------------------------
        if payload.expected_version is not None and finding.version != payload.expected_version:
            raise ReviewConcurrencyConflictError(
                f"Finding review state was updated by another reviewer (expected version {payload.expected_version}, current {finding.version}). Please refresh and review latest actions."
            )

        # ----------------------------------------------------------------------
        # 4. State Machine Transition Validation
        # ----------------------------------------------------------------------
        allowed_prior = VALID_TRANSITIONS.get(action, set())
        if finding.status not in allowed_prior:
            raise InvalidReviewTransitionError(
                f"Action '{action}' is not permitted from current status '{finding.status}'. Allowed from: {sorted(allowed_prior)}."
            )

        # ----------------------------------------------------------------------
        # 5. Required Rationale / Comment Validation
        # ----------------------------------------------------------------------
        effective_comment = payload.comment.strip() if payload.comment else None
        effective_rationale = payload.rationale.strip() if payload.rationale else None

        if action in ("resolve", "waive", "reopen", "escalate"):
            if not effective_rationale:
                raise ReviewValidationError(f"Action '{action}' requires a non-empty rationale.")

        if action in ("comment", "request_information"):
            if not effective_comment:
                raise ReviewValidationError(f"Action '{action}' requires a non-empty comment.")

        # ----------------------------------------------------------------------
        # 6. Apply State Transition and Record Historical ReviewAction
        # ----------------------------------------------------------------------
        previous_status = finding.status
        target_status = ACTION_RESULT_STATUS.get(action)
        new_status = target_status if target_status is not None else previous_status

        # Update finding review state
        if action != "comment":
            finding.status = new_status
            finding.version += 1

        if action in ("resolve", "waive"):
            finding.resolution_rationale = effective_rationale
            finding.resolved_by = user.username
            finding.resolved_at = _utc_now()
        elif action == "reopen":
            finding.resolution_rationale = None
            finding.resolved_by = None
            finding.resolved_at = None

        metadata_dict = {}
        if payload.resolution_outcome:
            metadata_dict["resolution_outcome"] = payload.resolution_outcome
        if payload.evidence_ref:
            metadata_dict["evidence_ref"] = payload.evidence_ref

        review_action = ReviewAuditRepository.create_review_action(
            db,
            application_id=app.id,
            reviewer_id=user.username,
            action=action,
            finding_id=finding.id,
            validation_run_id=run.id,
            actor_role=user_role,
            previous_status=previous_status,
            new_status=new_status,
            comment=effective_comment,
            rationale=effective_rationale,
            request_id=payload.request_id,
            evidence_ref=payload.evidence_ref,
            metadata_payload=json.dumps(metadata_dict) if metadata_dict else None,
        )

        ReviewAuditRepository.create_audit_event(
            db,
            action="REVIEW_ACTION_RECORDED",
            target_type="Finding",
            target_id=str(finding.id),
            actor_id=user.username,
            institution_id=app.institution_id,
            request_id=payload.request_id,
            details=json.dumps({
                "action": action,
                "previous_status": previous_status,
                "new_status": new_status,
                "finding_code": finding.code,
                "finding_version": finding.version,
            }),
        )

        db.commit()
        db.refresh(finding)
        db.refresh(review_action)

        actions = ReviewAuditRepository.list_review_actions_for_finding(db, finding.id)
        finding_read = FindingWithReviewRead.model_validate(finding)
        finding_read.review_actions = [ReviewActionRead.model_validate(a) for a in actions]

        return ReviewActionResponse(
            finding=finding_read,
            action=ReviewActionRead.model_validate(review_action),
            message=f"Review action '{action}' successfully recorded. Status transitioned from '{previous_status}' to '{new_status}'.",
        )

    @classmethod
    def list_application_findings(
        cls,
        db: Session,
        application_id: int,
        *,
        status_filter: str | None = None,
        severity_filter: str | None = None,
        code_filter: str | None = None,
        run_id: int | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[FindingWithReviewRead], int]:
        """List findings for an application with review actions."""
        records, total = ReviewAuditRepository.list_application_findings(
            db,
            application_id,
            status_filter=status_filter,
            severity_filter=severity_filter,
            code_filter=code_filter,
            run_id=run_id,
            skip=skip,
            limit=limit,
        )
        reads = []
        for f in records:
            actions = ReviewAuditRepository.list_review_actions_for_finding(db, f.id)
            f_read = FindingWithReviewRead.model_validate(f)
            f_read.review_actions = [ReviewActionRead.model_validate(a) for a in actions]
            reads.append(f_read)
        return reads, total

    @classmethod
    def get_reviewer_queue(
        cls,
        db: Session,
        user: User,
        authorized_institution_ids: list[int],
        *,
        status_filter: str | None = None,
        severity_filter: str | None = None,
        institution_id_filter: int | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> ReviewQueueResponse:
        """Retrieve items in the reviewer queue across authorized institutions."""
        effective_inst_ids = authorized_institution_ids
        if institution_id_filter is not None:
            if institution_id_filter not in authorized_institution_ids:
                return ReviewQueueResponse(items=[], total=0, skip=skip, limit=limit)
            effective_inst_ids = [institution_id_filter]

        records, total = ReviewAuditRepository.list_queue_findings(
            db,
            effective_inst_ids,
            status_filter=status_filter,
            severity_filter=severity_filter,
            skip=skip,
            limit=limit,
        )

        queue_items = []
        for f in records:
            actions = ReviewAuditRepository.list_review_actions_for_finding(db, f.id)
            f_read = FindingWithReviewRead.model_validate(f)
            f_read.review_actions = [ReviewActionRead.model_validate(a) for a in actions]

            run = f.validation_run
            app = run.application if run else None
            inst = app.institution if app else None

            queue_items.append(
                ReviewQueueItemRead(
                    finding=f_read,
                    application_id=app.id if app else 0,
                    institution_id=inst.institution_id if inst else "Unknown",
                    institution_name=inst.display_name if inst else "Unknown",
                    application_type=app.application_type if app else "unknown",
                    academic_year=app.academic_year if app else "unknown",
                )
            )

        return ReviewQueueResponse(items=queue_items, total=total, skip=skip, limit=limit)
