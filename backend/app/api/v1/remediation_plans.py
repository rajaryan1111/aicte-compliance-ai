"""Authenticated, institution-scoped remediation plan API.

Every route resolves the institution from the URL, then enforces membership and a role permission
before touching a plan. Plans are additive to the validation flow: they record institutional work
against a preliminary result and never alter validation outcomes.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, verify_institution_membership
from backend.app.core.rbac import (
    PERMISSION_PLAN_POLICY,
    PERMISSION_PLAN_READ,
    PERMISSION_PLAN_WRITE,
)
from backend.app.db.models import Institution, User
from backend.app.db.session import get_db
from backend.app.schemas.remediation_plan import (
    DeadlinePolicyUpdateRequest,
    RemediationPlanCreateRequest,
    RemediationPlanListResponse,
    RemediationPlanRead,
    RemediationTaskRead,
    RemediationTaskUpdateRequest,
)
from backend.app.services import remediation_plan_service as plans
from backend.app.services.exceptions import (
    RemediationPlanNotFoundError,
    RemediationTaskNotFoundError,
    StaleRemediationTaskVersionError,
)

router = APIRouter()

INSTITUTION_REF_PATTERN = r"^[A-Za-z0-9_.:-]{1,100}$"


def _resolve_institution(db: Session, institution_ref: str) -> Institution:
    """Resolve the tenant, concealing whether a foreign institution exists."""
    institution = db.scalar(
        select(Institution).where(Institution.institution_id == institution_ref)
    )
    if institution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Institution not found or access denied.",
        )
    return institution


@router.post(
    "/{institution_ref}/remediation-plans",
    response_model=RemediationPlanRead,
    status_code=status.HTTP_200_OK,
    summary="Create or reopen an institution remediation plan",
    description=(
        "Idempotent by (institution, plan_key). Re-posting the same deficiency signature returns "
        "the stored plan with its current progress unchanged. Returns 201 when a plan is created "
        "and 200 when an existing plan is returned."
    ),
)
def create_or_reopen_plan(
    institution_ref: str,
    payload: RemediationPlanCreateRequest,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RemediationPlanRead:
    institution = _resolve_institution(db, institution_ref)
    verify_institution_membership(
        db, current_user, institution.id, required_permission=PERMISSION_PLAN_WRITE
    )

    if payload.institution_ref != institution_ref:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="institution_ref in the body must match the institution in the path.",
        )

    plan, created = plans.create_or_get_plan(
        db,
        institution=institution,
        payload=payload,
        actor_id=current_user.username,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return plans.serialize_plan(plan, institution.institution_id)


@router.get(
    "/{institution_ref}/remediation-plans",
    response_model=RemediationPlanListResponse,
    summary="List remediation plans for an institution",
)
def list_institution_plans(
    institution_ref: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    plan_key: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RemediationPlanListResponse:
    institution = _resolve_institution(db, institution_ref)
    verify_institution_membership(
        db, current_user, institution.id, required_permission=PERMISSION_PLAN_READ
    )

    if plan_key:
        plan = plans.find_plan(db, institution.id, plan_key)
        items = [plans.serialize_plan(plan, institution.institution_id)] if plan else []
        return RemediationPlanListResponse(items=items, total=len(items))

    stored = plans.list_plans(db, institution.id, limit=limit)
    return RemediationPlanListResponse(
        items=[plans.serialize_plan(plan, institution.institution_id) for plan in stored],
        total=len(stored),
    )


@router.get(
    "/{institution_ref}/remediation-plans/{plan_id}",
    response_model=RemediationPlanRead,
    summary="Read one remediation plan",
)
def read_institution_plan(
    institution_ref: str,
    plan_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RemediationPlanRead:
    institution = _resolve_institution(db, institution_ref)
    verify_institution_membership(
        db, current_user, institution.id, required_permission=PERMISSION_PLAN_READ
    )
    try:
        plan = plans.get_plan(db, institution.id, plan_id)
    except RemediationPlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return plans.serialize_plan(plan, institution.institution_id)


@router.patch(
    "/{institution_ref}/remediation-plans/{plan_id}/tasks/{task_key}",
    response_model=RemediationTaskRead,
    summary="Update a task status or note",
    description=(
        "Optimistic concurrency: the request must carry the version it read. A stale version is "
        "rejected with 409 so two officers working the same plan cannot overwrite each other. "
        "Status changes are written to the audit log with actor, before and after."
    ),
)
def update_plan_task(
    institution_ref: str,
    plan_id: int,
    task_key: str,
    payload: RemediationTaskUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RemediationTaskRead:
    institution = _resolve_institution(db, institution_ref)
    verify_institution_membership(
        db, current_user, institution.id, required_permission=PERMISSION_PLAN_WRITE
    )
    try:
        plan = plans.get_plan(db, institution.id, plan_id)
        task = plans.update_task(
            db,
            plan=plan,
            task_key=task_key,
            payload=payload,
            actor_id=current_user.username,
        )
    except RemediationPlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RemediationTaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StaleRemediationTaskVersionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
            headers={"X-Current-Version": str(exc.expected)},
        ) from exc

    return plans.serialize_task(task)


@router.patch(
    "/{institution_ref}/remediation-plans/{plan_id}/deadline-policy",
    response_model=RemediationPlanRead,
    summary="Reschedule an institution plan (administrators only)",
    description=(
        "Re-derives due dates for open tasks from a new internal planning policy and appends the "
        "change, its actor and the number of moved tasks to the plan's deadline history. Completed "
        "tasks and certificate-expiry tasks keep their dates. These dates are institutional "
        "recommendations, not AICTE deadlines."
    ),
)
def update_deadline_policy(
    institution_ref: str,
    plan_id: int,
    payload: DeadlinePolicyUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RemediationPlanRead:
    institution = _resolve_institution(db, institution_ref)
    verify_institution_membership(
        db, current_user, institution.id, required_permission=PERMISSION_PLAN_POLICY
    )
    try:
        plan = plans.get_plan(db, institution.id, plan_id)
    except RemediationPlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    updated = plans.update_deadline_policy(
        db, plan=plan, payload=payload, actor_id=current_user.username
    )
    return plans.serialize_plan(updated, institution.institution_id)

