"""Authenticated, institution-scoped consistency API endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, get_db
from backend.app.db.models import User
from backend.app.schemas.consistency import (
    ConsistencyCheckCreate,
    ConsistencyCheckRead,
    ConsistencyFindingCreate,
    ConsistencyFindingRead,
    ConsistencyFindingUpdate,
    ConsistencyStatus,
)
from backend.app.services.consistency_service import ConsistencyCheckService

router = APIRouter(prefix="/consistency", tags=["consistency"])


@router.post(
    "/",
    response_model=ConsistencyCheckRead,
    status_code=status.HTTP_201_CREATED,
)
def create_consistency_check_endpoint(
    payload: ConsistencyCheckCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ConsistencyCheckRead:
    check = ConsistencyCheckService.create_check(db, payload=payload, user=current_user)
    return ConsistencyCheckRead.model_validate(check)


@router.get("/", response_model=list[ConsistencyCheckRead])
def list_consistency_checks_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    application_id: Annotated[int | None, Query(gt=0)] = None,
    status_filter: Annotated[ConsistencyStatus | None, Query()] = None,
) -> list[ConsistencyCheckRead]:
    checks = ConsistencyCheckService.list_checks(
        db,
        user=current_user,
        application_id=application_id,
        status_filter=status_filter,
    )
    return [ConsistencyCheckRead.model_validate(check) for check in checks]


@router.get("/{check_id}", response_model=ConsistencyCheckRead)
def get_consistency_check_endpoint(
    check_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ConsistencyCheckRead:
    check = ConsistencyCheckService.get_check(db, check_id=check_id, user=current_user)
    return ConsistencyCheckRead.model_validate(check)


@router.post(
    "/findings",
    response_model=ConsistencyFindingRead,
    status_code=status.HTTP_201_CREATED,
)
def create_consistency_finding_endpoint(
    payload: ConsistencyFindingCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ConsistencyFindingRead:
    finding = ConsistencyCheckService.create_finding(
        db, payload=payload, user=current_user
    )
    return ConsistencyFindingRead.model_validate(finding)


@router.get("/findings/{finding_id}", response_model=ConsistencyFindingRead)
def get_consistency_finding_endpoint(
    finding_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ConsistencyFindingRead:
    finding = ConsistencyCheckService.get_finding(
        db, finding_id=finding_id, user=current_user
    )
    return ConsistencyFindingRead.model_validate(finding)


@router.get(
    "/checks/{check_id}/findings",
    response_model=list[ConsistencyFindingRead],
)
def list_consistency_findings_endpoint(
    check_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    severity_filter: Annotated[str | None, Query(min_length=1, max_length=30)] = None,
    resolved: bool | None = Query(default=None),
) -> list[ConsistencyFindingRead]:
    findings = ConsistencyCheckService.list_findings(
        db,
        check_id=check_id,
        user=current_user,
        severity_filter=severity_filter,
        resolved=resolved,
    )
    return [ConsistencyFindingRead.model_validate(finding) for finding in findings]


@router.patch("/findings/{finding_id}", response_model=ConsistencyFindingRead)
def update_consistency_finding_endpoint(
    finding_id: int,
    payload: ConsistencyFindingUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ConsistencyFindingRead:
    finding = ConsistencyCheckService.update_finding(
        db,
        finding_id=finding_id,
        payload=payload,
        user=current_user,
    )
    return ConsistencyFindingRead.model_validate(finding)
