"""Review action and audit event repository for database access."""

from __future__ import annotations


from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models import Application, AuditEvent, Finding, ReviewAction, ValidationRun


class ReviewAuditRepository:
    """Encapsulates persistence operations for human review decisions and audit logs."""

    @staticmethod
    def create_review_action(
        db: Session,
        *,
        application_id: int,
        reviewer_id: str,
        action: str,
        finding_id: int | None = None,
        validation_run_id: int | None = None,
        actor_role: str | None = None,
        previous_status: str | None = None,
        new_status: str | None = None,
        comment: str | None = None,
        rationale: str | None = None,
        request_id: str | None = None,
        evidence_ref: str | None = None,
        metadata_payload: str | None = None,
    ) -> ReviewAction:
        """Record an attributable review action for an application or specific finding."""
        review_action = ReviewAction(
            application_id=application_id,
            reviewer_id=reviewer_id,
            action=action,
            finding_id=finding_id,
            validation_run_id=validation_run_id,
            actor_role=actor_role,
            previous_status=previous_status,
            new_status=new_status,
            comment=comment,
            rationale=rationale,
            request_id=request_id,
            evidence_ref=evidence_ref,
            metadata_payload=metadata_payload,
        )
        db.add(review_action)
        return review_action

    @staticmethod
    def get_review_action_by_request_id(
        db: Session,
        finding_id: int,
        request_id: str,
    ) -> ReviewAction | None:
        """Find an existing review action by finding ID and idempotency request ID."""
        stmt = select(ReviewAction).where(
            ReviewAction.finding_id == finding_id,
            ReviewAction.request_id == request_id,
        )
        return db.scalar(stmt)

    @staticmethod
    def list_review_actions(
        db: Session,
        application_id: int,
        limit: int = 50,
    ) -> list[ReviewAction]:
        """List review actions for an application ordered by creation time."""
        stmt = (
            select(ReviewAction)
            .where(ReviewAction.application_id == application_id)
            .order_by(ReviewAction.created_at.desc(), ReviewAction.id.desc())
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def list_review_actions_for_finding(
        db: Session,
        finding_id: int,
    ) -> list[ReviewAction]:
        """List chronological review actions and comments for a specific finding."""
        stmt = (
            select(ReviewAction)
            .where(ReviewAction.finding_id == finding_id)
            .order_by(ReviewAction.created_at.asc(), ReviewAction.id.asc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_review_summary_counts(
        db: Session,
        application_id: int,
    ) -> dict[str, int]:
        """Aggregate review status counts across findings for an application."""
        stmt = (
            select(Finding.status, func.count(Finding.id))
            .join(ValidationRun, Finding.validation_run_id == ValidationRun.id)
            .where(ValidationRun.application_id == application_id)
            .group_by(Finding.status)
        )
        rows = db.execute(stmt).all()
        counts: dict[str, int] = {
            "open": 0,
            "acknowledged": 0,
            "under_review": 0,
            "resolved": 0,
            "escalated": 0,
            "waived": 0,
        }
        for status_val, count in rows:
            if status_val in counts:
                counts[status_val] = count
            else:
                counts[status_val] = count
        return counts

    @staticmethod
    def list_application_findings(
        db: Session,
        application_id: int,
        *,
        status_filter: str | None = None,
        severity_filter: str | None = None,
        code_filter: str | None = None,
        run_id: int | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[Finding], int]:
        """Paginated search of findings belonging to an application."""
        base_query = (
            select(Finding)
            .join(ValidationRun, Finding.validation_run_id == ValidationRun.id)
            .where(ValidationRun.application_id == application_id)
        )
        count_query = (
            select(func.count(Finding.id))
            .join(ValidationRun, Finding.validation_run_id == ValidationRun.id)
            .where(ValidationRun.application_id == application_id)
        )

        if status_filter:
            base_query = base_query.where(Finding.status == status_filter)
            count_query = count_query.where(Finding.status == status_filter)
        if severity_filter:
            base_query = base_query.where(Finding.severity == severity_filter)
            count_query = count_query.where(Finding.severity == severity_filter)
        if code_filter:
            base_query = base_query.where(Finding.code == code_filter)
            count_query = count_query.where(Finding.code == code_filter)
        if run_id:
            base_query = base_query.where(Finding.validation_run_id == run_id)
            count_query = count_query.where(Finding.validation_run_id == run_id)

        total = db.scalar(count_query) or 0
        records = list(
            db.scalars(
                base_query.order_by(Finding.created_at.desc(), Finding.id.desc())
                .offset(skip)
                .limit(limit)
            ).all()
        )
        return records, total

    @staticmethod
    def list_queue_findings(
        db: Session,
        institution_ids: list[int],
        *,
        status_filter: str | None = None,
        severity_filter: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[Finding], int]:
        """List findings across authorized institutions for a reviewer queue."""
        if not institution_ids:
            return [], 0

        base_query = (
            select(Finding)
            .join(ValidationRun, Finding.validation_run_id == ValidationRun.id)
            .join(Application, ValidationRun.application_id == Application.id)
            .where(Application.institution_id.in_(institution_ids))
        )
        count_query = (
            select(func.count(Finding.id))
            .join(ValidationRun, Finding.validation_run_id == ValidationRun.id)
            .join(Application, ValidationRun.application_id == Application.id)
            .where(Application.institution_id.in_(institution_ids))
        )

        if status_filter:
            base_query = base_query.where(Finding.status == status_filter)
            count_query = count_query.where(Finding.status == status_filter)
        else:
            # Default queue focuses on items needing action
            base_query = base_query.where(
                Finding.status.in_(["open", "acknowledged", "under_review", "escalated"])
            )
            count_query = count_query.where(
                Finding.status.in_(["open", "acknowledged", "under_review", "escalated"])
            )

        if severity_filter:
            base_query = base_query.where(Finding.severity == severity_filter)
            count_query = count_query.where(Finding.severity == severity_filter)

        total = db.scalar(count_query) or 0
        records = list(
            db.scalars(
                base_query.order_by(Finding.created_at.desc(), Finding.id.desc())
                .offset(skip)
                .limit(limit)
            ).all()
        )
        return records, total

    @staticmethod
    def create_audit_event(
        db: Session,
        *,
        action: str,
        target_type: str,
        target_id: str,
        actor_id: str | None = None,
        institution_id: int | None = None,
        request_id: str | None = None,
        details: str | None = None,
    ) -> AuditEvent:
        """Create an attributable audit event record."""
        event = AuditEvent(
            action=action,
            target_type=target_type,
            target_id=target_id,
            actor_id=actor_id,
            institution_id=institution_id,
            request_id=request_id,
            details=details,
        )
        db.add(event)
        return event

    @staticmethod
    def list_audit_events(
        db: Session,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = 50,
    ) -> list[AuditEvent]:
        """List audit events with optional filtering by target."""
        stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
        if target_type is not None:
            stmt = stmt.where(AuditEvent.target_type == target_type)
        if target_id is not None:
            stmt = stmt.where(AuditEvent.target_id == target_id)
        return list(db.scalars(stmt).all())
