"""Authenticated, tenant-scoped human review, finding resolution, and queue endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, verify_institution_membership
from backend.app.core.rbac import (
    PERMISSION_REVIEW_READ,
    has_permission,
)
from backend.app.db.models import Application, User
from backend.app.db.session import get_db
from backend.app.repositories.user_repository import UserRepository
from backend.app.schemas.review import (
    FindingListResponse,
    FindingWithReviewRead,
    ReviewActionCreateRequest,
    ReviewActionResponse,
    ReviewQueueResponse,
    ReviewSummaryResponse,
)
from backend.app.services.review_service import (
    FindingNotFoundError,
    InvalidReviewTransitionError,
    ReviewConcurrencyConflictError,
    ReviewPermissionDeniedError,
    ReviewService,
    ReviewValidationError,
)

router = APIRouter()


@router.get(
    "/applications/{application_id}/review-summary",
    response_model=ReviewSummaryResponse,
    summary="Get application review summary and status counts",
    description="Retrieve consolidated summary of review statuses, pending action counts, and recent actions.",
)
def get_application_review_summary(
    application_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReviewSummaryResponse:
    """Retrieve review summary enforcing institutional tenant boundary."""
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_REVIEW_READ,
    )

    try:
        return ReviewService.get_application_review_summary(db, application_id)
    except FindingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/applications/{application_id}/findings",
    response_model=FindingListResponse,
    summary="List findings for an application with review status",
    description="Paginated retrieval of findings with filtering by review status, severity, code, or run ID.",
)
def list_application_findings_endpoint(
    application_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    review_status: Annotated[str | None, Query(alias="status", description="Filter by review status")] = None,
    severity: Annotated[str | None, Query(description="Filter by finding severity")] = None,
    code: Annotated[str | None, Query(description="Filter by finding code")] = None,
    run_id: Annotated[int | None, Query(description="Filter by specific validation run ID")] = None,
    skip: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Pagination limit")] = 20,
) -> FindingListResponse:
    """List findings for an application enforcing institutional boundary."""
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_REVIEW_READ,
    )

    items, total = ReviewService.list_application_findings(
        db,
        application_id,
        status_filter=review_status,
        severity_filter=severity,
        code_filter=code,
        run_id=run_id,
        skip=skip,
        limit=limit,
    )
    return FindingListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get(
    "/applications/{application_id}/validation-runs/{run_id}/findings/{finding_id}",
    response_model=FindingWithReviewRead,
    summary="Get finding details and chronological review history",
    description="Inspect finding, original automated observations, current review state, and reviewer comments.",
)
def get_finding_detail_endpoint(
    application_id: int,
    run_id: int,
    finding_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FindingWithReviewRead:
    """Retrieve single finding with full review history."""
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_REVIEW_READ,
    )

    try:
        return ReviewService.get_finding_with_history(
            db, application_id=application_id, run_id=run_id, finding_id=finding_id
        )
    except FindingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/applications/{application_id}/validation-runs/{run_id}/findings/{finding_id}/actions",
    response_model=ReviewActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an attributable human review action on a finding",
    description="Execute lifecycle transitions (acknowledge, comment, request_info, resolve, reopen, escalate, waive).",
)
def record_review_action_endpoint(
    application_id: int,
    run_id: int,
    finding_id: int,
    payload: ReviewActionCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReviewActionResponse:
    """Record a review action enforcing role permissions, state transitions, and concurrency."""
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    # Verify membership and obtain user's active role in this institution
    membership = verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_REVIEW_READ,
    )

    try:
        return ReviewService.record_review_action(
            db,
            application_id=application_id,
            run_id=run_id,
            finding_id=finding_id,
            user=current_user,
            user_role=membership.role,
            payload=payload,
        )
    except FindingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ReviewPermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except InvalidReviewTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ReviewValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ReviewConcurrencyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/reviews/queue",
    response_model=ReviewQueueResponse,
    summary="Get reviewer queue across authorized institutions",
    description="Retrieve review items requiring reviewer attention scoped strictly to institutions the user administers.",
)
def get_reviewer_queue_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    review_status: Annotated[str | None, Query(alias="status", description="Filter by review status")] = None,
    severity: Annotated[str | None, Query(description="Filter by finding severity")] = None,
    institution_id: Annotated[int | None, Query(description="Filter by specific institution ID")] = None,
    skip: Annotated[int, Query(ge=0, description="Offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Limit")] = 20,
) -> ReviewQueueResponse:
    """Retrieve reviewer queue for all institutions the user is authorized to review."""
    # Find active institutions where user has review permission
    memberships = [
        m for m in UserRepository.get_active_memberships(db, current_user.id)
        if has_permission(m.role, PERMISSION_REVIEW_READ)
    ]
    if not memberships:
        return ReviewQueueResponse(items=[], total=0, skip=skip, limit=limit)

    allowed_inst_ids = [m.institution_id for m in memberships]

    return ReviewService.get_reviewer_queue(
        db,
        current_user,
        authorized_institution_ids=allowed_inst_ids,
        status_filter=review_status,
        severity_filter=severity,
        institution_id_filter=institution_id,
        skip=skip,
        limit=limit,
    )
