"""Consistency check API routes for AICTE Compliance AI."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from backend.app.api.deps import get_db, get_current_user
from backend.app.schemas.consistency import (
    ConsistencyCheckCreate,
    ConsistencyCheckUpdate,
    ConsistencyCheckRead,
    ConsistencyFindingCreate,
    ConsistencyFindingUpdate,
    ConsistencyFindingRead,
)
from backend.app.services.consistency_service import (
    ConsistencyCheckService,
    ConsistencyPermissionDeniedError,
)
from backend.app.repositories.consistency_check_repository import (
    create_consistency_check,
    get_consistency_check,
    list_consistency_checks,
    create_consistency_finding,
    get_consistency_finding,
    list_consistency_findings,
    update_consistency_finding,
)

router = APIRouter(prefix="/consistency", tags=["consistency"])


# ---- Consistency Check endpoints ----

@router.post("/", response_model=ConsistencyCheckRead, status_code=status.HTTP_201_CREATED)
def create_consistency_check_endpoint(
    *,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    payload: ConsistencyCheckCreate,
) -> ConsistencyCheckRead:
    """Create a new consistency check."""
    user = User(**current_user)
    check = ConsistencyCheckService.run_check(
        db,
        application_id=payload.application_id,
        user=user,
        user_role=user_role,
        check_name=payload.check_name,
        description=payload.description,
        related_field=payload.related_field,
    )
    return check


@router.get("/{check_id}", response_model=ConsistencyCheckRead)
def get_consistency_check_endpoint(
    *,
    db: Session = Depends(get_db),
    check_id: int,
    current_user: dict = Depends(get_current_user),
) -> ConsistencyCheckRead:
    """Retrieve a consistency check by ID with institution isolation."""
    user = User(**current_user)
    check = ConsistencyCheckService.get_check(db, check_id=check_id, user=user)
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consistency check {check_id} not found.",
        )
    return check


@router.get("/", response_model=list[ConsistencyCheckRead])
def list_consistency_checks_endpoint(
    *,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    application_id: Optional[int] = None,
    status_filter: Optional[str] = None,
) -> list[ConsistencyCheckRead]:
    """List consistency checks, optionally filtered by application and status with institution isolation."""
    user = User(**current_user)
    checks = ConsistencyCheckService.list_checks(
        db,
        application_id=application_id,
        status_filter=status_filter,
        user=user,
    )
    return checks


# ---- Consistency Finding endpoints ----

@router.post("/findings", response_model=ConsistencyFindingRead, status_code=status.HTTP_201_CREATED)
def create_consistency_finding_endpoint(
    *,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    payload: ConsistencyFindingCreate,
) -> ConsistencyFindingRead:
    """Create a new consistency finding."""
    from backend.app.db.models import User as DBUser
    user = DBUser(**current_user)
    # Get the consistency check to verify institution ownership
    check = db.get(ConsistencyCheck, payload.consistency_check_id)
    if check is not None:
        try:
            verify_institution_membership(
                db, user, check.application.institution_id, required_permission="consistency:check"
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You cannot create findings for checks outside your institution.",
            )
    finding = create_consistency_finding(
        db,
        consistency_check_id=payload.consistency_check_id,
        field_name=payload.field_name,
        value_1=payload.value_1,
        value_2=payload.value_2,
        severity=payload.severity,
        confidence=payload.confidence,
        description=payload.description,
        evidence=payload.evidence,
    )
    return ConsistencyFindingRead.model_validate(finding)


@router.get("/findings/{finding_id}", response_model=ConsistencyFindingRead)
def get_consistency_finding_endpoint(
    *,
    db: Session = Depends(get_db),
    finding_id: int,
    current_user: dict = Depends(get_current_user),
) -> ConsistencyFindingRead:
    """Retrieve a consistency finding by ID with institution isolation."""
    from backend.app.db.models import User as DBUser
    user = DBUser(**current_user)
    finding = get_consistency_finding(db, finding_id=finding_id)
    if finding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consistency finding {finding_id} not found.",
        )
    # Verify institution ownership via the linked consistency check
    check = db.get(ConsistencyCheck, finding.consistency_check_id)
    if check is not None:
        try:
            verify_institution_membership(
                db, user, check.application.institution_id, required_permission="consistency:read"
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You cannot access findings outside your institution.",
            )
    return ConsistencyFindingRead.model_validate(finding)


@router.get("/checks/{check_id}/findings", response_model=list[ConsistencyFindingRead])
def list_consistency_findings_endpoint(
    *,
    db: Session = Depends(get_db),
    check_id: int,
    current_user: dict = Depends(get_current_user),
    severity_filter: Optional[str] = None,
    resolved: Optional[bool] = None,
) -> list[ConsistencyFindingRead]:
    """List findings for a specific consistency check with institution isolation."""
    from backend.app.db.models import User as DBUser
    user = DBUser(**current_user)
    # First verify the check itself is accessible
    check = db.get(ConsistencyCheck, check_id)
    if check is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consistency check {check_id} not found.",
        )
    try:
        verify_institution_membership(
            db, user, check.application.institution_id, required_permission="consistency:read"
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot access findings outside your institution.",
        )
    findings = list_consistency_findings(
        db,
        consistency_check_id=check_id,
        severity_filter=severity_filter,
        resolved=resolved,
    )
    return [ConsistencyFindingRead.model_validate(f) for f in findings]


@router.patch("/findings/{finding_id}", response_model=ConsistencyFindingRead)
def update_consistency_finding_endpoint(
    *,
    db: Session = Depends(get_db),
    finding_id: int,
    payload: ConsistencyFindingUpdate,
    current_user: dict = Depends(get_current_user),
) -> ConsistencyFindingRead:
    """Update a consistency finding with institution isolation."""
    from backend.app.db.models import User as DBUser
    user = DBUser(**current_user)
    finding = get_consistency_finding(db, finding_id=finding_id)
    if finding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consistency finding {finding_id} not found.",
        )
    # Verify institution ownership via the linked consistency check
    check = db.get(ConsistencyCheck, finding.consistency_check_id)
    if check is not None:
        try:
            verify_institution_membership(
                db, user, check.application.institution_id, required_permission="consistency:update"
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You cannot modify findings outside your institution.",
            )
    updated = update_consistency_finding(
        db,
        finding=finding,
        severity=payload.severity,
        description=payload.description,
        evidence=payload.evidence,
        resolved=payload.resolved,
    )
    return ConsistencyFindingRead.model_validate(updated)