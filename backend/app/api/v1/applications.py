"""Authenticated and tenant-scoped application API endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import (
    get_application_service,
    get_current_user,
    verify_institution_membership,
)
from backend.app.core.rbac import (
    PERMISSION_APPLICATION_CREATE,
    PERMISSION_APPLICATION_READ,
    PERMISSION_APPLICATION_UPDATE,
    has_permission,
)
from backend.app.db.models import Application, User
from backend.app.db.session import get_db
from backend.app.repositories.user_repository import UserRepository
from backend.app.schemas.application import (
    ApplicationCreate,
    ApplicationCreateRequest,
    ApplicationListResponse,
    ApplicationRead,
    ApplicationUpdate,
)
from backend.app.services.application_service import ApplicationService
from backend.app.services.exceptions import (
    ApplicationNotFoundError,
    InstitutionNotFoundError,
    InvalidAcademicYearError,
    InvalidApplicationTypeError,
    InvalidStatusTransitionError,
)

router = APIRouter()


@router.post(
    "",
    response_model=ApplicationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create application in authorized scope",
    description="Create a new application for an institution the authenticated user is authorized to administer.",
)
def create_application(
    payload: ApplicationCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[ApplicationService, Depends(get_application_service)],
) -> ApplicationRead:
    """Create an application enforcing tenant boundary and application:create permission."""
    target_institution_id = payload.institution_id

    # If institution_id is not explicitly specified, derive from user's active memberships
    if target_institution_id is None:
        memberships = [
            m for m in UserRepository.get_active_memberships(db, current_user.id)
            if has_permission(m.role, PERMISSION_APPLICATION_CREATE)
        ]
        if not memberships:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: User has no authorized institutions for application creation.",
            )
        if len(memberships) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Multiple authorized institutions available; please specify target institution_id.",
            )
        target_institution_id = memberships[0].institution_id

    # Verify user has active membership with application:create permission in target institution
    verify_institution_membership(
        db,
        current_user,
        target_institution_id,
        required_permission=PERMISSION_APPLICATION_CREATE,
    )

    create_data = ApplicationCreate(
        institution_id=target_institution_id,
        application_type=payload.application_type,
        academic_year=payload.academic_year,
        status=payload.status or "draft",
    )

    try:
        application = service.create_application(
            db,
            create_data,
            actor_id=current_user.username,
        )
        return ApplicationRead.model_validate(application)
    except InvalidApplicationTypeError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e
    except InvalidAcademicYearError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e
    except InstitutionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.get(
    "",
    response_model=ApplicationListResponse,
    summary="List applications in authorized tenant scope",
    description="Retrieve paginated list of applications scoped strictly to the authenticated user's institution memberships.",
)
def list_applications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    institution_id: Annotated[int | None, Query(description="Filter by specific authorized institution ID")] = None,
    status_filter: Annotated[str | None, Query(alias="status", description="Filter by lifecycle status")] = None,
    skip: Annotated[int, Query(ge=0, description="Offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Limit")] = 20,
) -> ApplicationListResponse:
    """List applications with database-side pagination within user's verified tenant scope."""
    # If institution_id is provided, verify access
    if institution_id is not None:
        verify_institution_membership(
            db,
            current_user,
            institution_id,
            required_permission=PERMISSION_APPLICATION_READ,
        )
        allowed_institution_ids = [institution_id]
    else:
        # Determine all active institutions the user has permission to read
        memberships = [
            m for m in UserRepository.get_active_memberships(db, current_user.id)
            if has_permission(m.role, PERMISSION_APPLICATION_READ)
        ]
        if not memberships:
            return ApplicationListResponse(items=[], total=0, skip=skip, limit=limit)
        allowed_institution_ids = [m.institution_id for m in memberships]

    count_stmt = (
        select(func.count())
        .select_from(Application)
        .where(Application.institution_id.in_(allowed_institution_ids))
    )
    if status_filter:
        count_stmt = count_stmt.where(Application.status == status_filter)
    total = db.scalar(count_stmt) or 0

    query = (
        select(Application)
        .where(Application.institution_id.in_(allowed_institution_ids))
    )
    if status_filter:
        query = query.where(Application.status == status_filter)

    query = (
        query.order_by(Application.created_at.desc(), Application.id.desc())
        .offset(skip)
        .limit(limit)
    )
    records = list(db.scalars(query).all())

    return ApplicationListResponse(
        items=[ApplicationRead.model_validate(app) for app in records],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{application_id}",
    response_model=ApplicationRead,
    summary="Retrieve single authorized application",
)
def get_application_by_id(
    application_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApplicationRead:
    """Retrieve an application by ID after verifying institutional access."""
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    # Conceals foreign tenant applications with 404 to prevent resource discovery
    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_APPLICATION_READ,
    )

    return ApplicationRead.model_validate(app)


@router.patch(
    "/{application_id}",
    response_model=ApplicationRead,
    summary="Update application fields in authorized scope",
)
def update_application_by_id(
    application_id: int,
    payload: ApplicationUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    service: Annotated[ApplicationService, Depends(get_application_service)],
) -> ApplicationRead:
    """Update permitted application fields enforcing write permissions and lifecycle transitions."""
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    # Verify user has membership and application:update permission in the application's institution
    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_APPLICATION_UPDATE,
    )

    try:
        updated = service.update_application(
            db,
            application_id,
            payload,
            actor_id=current_user.username,
        )
        return ApplicationRead.model_validate(updated)
    except InvalidStatusTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except InvalidAcademicYearError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e
    except ApplicationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
