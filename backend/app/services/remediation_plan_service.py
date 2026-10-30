"""Institution-scoped remediation plan persistence.

The plan content is derived by the client from a preliminary validation result. This service
stores it, attributes progress to an authenticated actor, records status changes in the audit log,
and guarantees that re-posting the same deficiency signature is a no-op rather than a duplicate.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import (
    Institution,
    RemediationDeadlineChange,
    RemediationPlan,
    RemediationTask,
)
from backend.app.repositories.review_audit_repository import ReviewAuditRepository
from backend.app.schemas.remediation_plan import (
    DeadlinePolicy,
    RemediationDeadlineChangeRead,
    DeadlinePolicyUpdateRequest,
    RemediationPlanCreateRequest,
    RemediationPlanRead,
    RemediationTaskRead,
    RemediationTaskUpdateRequest,
)
from backend.app.services.exceptions import (
    RemediationPlanNotFoundError,
    RemediationTaskNotFoundError,
    StaleRemediationTaskVersionError,
)

AUDIT_PLAN_CREATED = "remediation_plan_created"
AUDIT_TASK_UPDATED = "remediation_task_updated"
AUDIT_DEADLINE_POLICY_CHANGED = "remediation_deadline_policy_changed"

TARGET_PLAN = "remediation_plan"
TARGET_TASK = "remediation_task"


def decode_deadline_policy(raw: str | None) -> DeadlinePolicy:
    """Tolerant decode: a plan stored before a policy field existed still renders with defaults."""
    if not raw:
        return DeadlinePolicy()
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return DeadlinePolicy()
    if not isinstance(parsed, dict):
        return DeadlinePolicy()
    allowed = set(DeadlinePolicy.model_fields)
    return DeadlinePolicy(**{key: value for key, value in parsed.items() if key in allowed})


def serialize_task(task: RemediationTask) -> RemediationTaskRead:
    return RemediationTaskRead.model_validate(task)


def serialize_deadline_change(change: RemediationDeadlineChange) -> RemediationDeadlineChangeRead:
    return RemediationDeadlineChangeRead(
        id=change.id,
        changed_by=change.changed_by,
        previous_policy=decode_deadline_policy(change.previous_policy),
        new_policy=decode_deadline_policy(change.new_policy),
        rescheduled_tasks=change.rescheduled_tasks,
        created_at=change.created_at,
    )


def serialize_plan(plan: RemediationPlan, institution_ref: str) -> RemediationPlanRead:
    return RemediationPlanRead(
        id=plan.id,
        institution_id=plan.institution_id,
        institution_ref=institution_ref,
        plan_key=plan.plan_key,
        application_type=plan.application_type,
        deadline_policy=decode_deadline_policy(plan.deadline_policy),
        created_by=plan.created_by,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        tasks=[serialize_task(task) for task in plan.tasks],
        deadline_history=[serialize_deadline_change(entry) for entry in plan.deadline_changes[:10]],
    )


def find_plan(db: Session, institution_id: int, plan_key: str) -> RemediationPlan | None:
    return db.scalar(
        select(RemediationPlan).where(
            RemediationPlan.institution_id == institution_id,
            RemediationPlan.plan_key == plan_key,
        )
    )


def get_plan(db: Session, institution_id: int, plan_id: int) -> RemediationPlan:
    plan = db.scalar(
        select(RemediationPlan).where(
            RemediationPlan.id == plan_id,
            RemediationPlan.institution_id == institution_id,
        )
    )
    if plan is None:
        raise RemediationPlanNotFoundError("Remediation plan not found in this institution scope.")
    return plan


def list_plans(
    db: Session, institution_id: int, limit: int = 50
) -> list[RemediationPlan]:
    stmt = (
        select(RemediationPlan)
        .where(RemediationPlan.institution_id == institution_id)
        .order_by(RemediationPlan.updated_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def create_or_get_plan(
    db: Session,
    *,
    institution: Institution,
    payload: RemediationPlanCreateRequest,
    actor_id: str,
) -> tuple[RemediationPlan, bool]:
    """Idempotent create. Returns (plan, created).

    Re-posting an existing (institution, plan_key) returns the stored plan **without** touching
    task status, notes or versions, so a re-validation can never silently reset progress.
    """
    existing = find_plan(db, institution.id, payload.plan_key)
    if existing is not None:
        return existing, False

    plan = RemediationPlan(
        institution_id=institution.id,
        plan_key=payload.plan_key,
        application_type=payload.application_type,
        deadline_policy=json.dumps(payload.deadline_policy.model_dump(), sort_keys=True),
        created_by=actor_id,
    )
    plan.tasks = [
        RemediationTask(
            task_key=item.task_key,
            document_id=item.document_id,
            document_label=item.document_label,
            finding_code=item.finding_code,
            priority=item.priority,
            owner_role=item.owner_role,
            due_date=item.due_date,
            evidence_required=item.evidence_required,
            clause=item.clause,
            status="open",
            note="",
            version=1,
        )
        for item in payload.items
    ]

    db.add(plan)
    try:
        db.flush()
        ReviewAuditRepository.create_audit_event(
            db,
            action=AUDIT_PLAN_CREATED,
            target_type=TARGET_PLAN,
            target_id=payload.plan_key,
            actor_id=actor_id,
            institution_id=institution.id,
            details=json.dumps(
                {
                    "plan_key": payload.plan_key,
                    "application_type": payload.application_type,
                    "task_count": len(payload.items),
                    "deadline_policy": payload.deadline_policy.model_dump(),
                    "source": "client_derived_preliminary_validation",
                },
                sort_keys=True,
            ),
        )
        db.commit()
    except IntegrityError:
        # Another request created the same plan concurrently: treat it as the idempotent outcome.
        db.rollback()
        concurrent = find_plan(db, institution.id, payload.plan_key)
        if concurrent is None:
            raise
        return concurrent, False

    db.refresh(plan)
    return plan, True


def update_task(
    db: Session,
    *,
    plan: RemediationPlan,
    task_key: str,
    payload: RemediationTaskUpdateRequest,
    actor_id: str,
) -> RemediationTask:
    """Apply a status/note change with optimistic concurrency and an audit trail.

    A request that changes nothing is a successful no-op and does not bump the version, so retries
    are idempotent. A version mismatch raises a 409 rather than overwriting another user's edit.
    """
    task = next((item for item in plan.tasks if item.task_key == task_key), None)
    if task is None:
        raise RemediationTaskNotFoundError(
            f"Task {task_key!r} does not exist in this remediation plan."
        )

    if payload.version != task.version:
        raise StaleRemediationTaskVersionError(expected=task.version, received=payload.version)

    changes: list[dict[str, object]] = []

    if payload.status is not None and payload.status != task.status:
        changes.append({"field": "status", "from": task.status, "to": payload.status})
        task.status = payload.status
        task.status_changed_by = actor_id
        task.status_changed_at = datetime.now(timezone.utc)

    if payload.note is not None and payload.note != task.note:
        # The note text itself is not copied into the audit log; only its presence and size.
        changes.append({"field": "note", "changed": True, "length": len(payload.note)})
        task.note = payload.note

    if not changes:
        return task

    task.version = task.version + 1
    ReviewAuditRepository.create_audit_event(
        db,
        action=AUDIT_TASK_UPDATED,
        target_type=TARGET_TASK,
        target_id=f"{plan.plan_key}:{task.task_key}",
        actor_id=actor_id,
        institution_id=plan.institution_id,
        details=json.dumps(
            {"plan_id": plan.id, "plan_key": plan.plan_key, "changes": changes},
            sort_keys=True,
        ),
    )
    db.commit()
    db.refresh(task)
    return task


def _policy_dump(policy: DeadlinePolicy) -> str:
    return json.dumps(policy.model_dump(), sort_keys=True)


def update_deadline_policy(
    db: Session,
    *,
    plan: RemediationPlan,
    payload: DeadlinePolicyUpdateRequest,
    actor_id: str,
) -> RemediationPlan:
    """Reschedule a shared plan and keep an append-only record of the change.

    Rules, chosen so the schedule stays explainable:

    * Only tasks that are still open work are rescheduled. A completed task keeps the date it was
      completed against, so history is not rewritten by a later policy change.
    * ``EXPIRING_SOON`` tasks keep their stored date: those dates are driven by the certificate's own
      expiry, and the policy only bounds them when they are first computed.
    * Every moved task gets a version bump, so a stale tab's task update is rejected with 409 rather
      than silently overwriting the new schedule.

    The policy is an internal planning instrument. It is never presented as an AICTE deadline.
    """
    previous = decode_deadline_policy(plan.deadline_policy)
    requested = payload.policy
    # UTC, not the server's local date: otherwise the same request reschedules differently on a
    # laptop in IST and a container in UTC, which makes due dates untrustworthy.
    today = datetime.now(timezone.utc).date()

    moved = 0
    for task in plan.tasks:
        if task.status == "done" or task.finding_code == "EXPIRING_SOON":
            continue
        if task.priority == "P1":
            target = today + timedelta(days=requested.p1_days)
        elif task.priority == "P2":
            target = today + timedelta(days=requested.p2_days)
        else:
            target = today + timedelta(days=requested.p3_max_days)
        if task.due_date != target:
            task.due_date = target
            task.version = task.version + 1
            moved += 1

    if moved == 0 and previous == requested:
        # Idempotent no-op: re-sending the same policy neither writes history nor bumps versions.
        return plan

    plan.deadline_policy = _policy_dump(requested)
    change = RemediationDeadlineChange(
        plan_id=plan.id,
        changed_by=actor_id,
        previous_policy=_policy_dump(previous),
        new_policy=_policy_dump(requested),
        rescheduled_tasks=moved,
    )
    db.add(change)
    ReviewAuditRepository.create_audit_event(
        db,
        action=AUDIT_DEADLINE_POLICY_CHANGED,
        target_type=TARGET_PLAN,
        target_id=plan.plan_key,
        actor_id=actor_id,
        institution_id=plan.institution_id,
        details=json.dumps(
            {
                "plan_id": plan.id,
                "plan_key": plan.plan_key,
                "previous_policy": previous.model_dump(),
                "new_policy": requested.model_dump(),
                "rescheduled_tasks": moved,
                "policy_scope": "internal_recommendation_not_aicte_deadline",
            },
            sort_keys=True,
        ),
    )
    db.commit()
    db.refresh(plan)
    return plan
