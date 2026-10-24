"""Authenticated, tenant-scoped application validation and scrutiny report endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, verify_institution_membership
from backend.app.core.dispatcher import dispatch_outbox_message
from backend.app.core.rbac import (
    PERMISSION_APPLICATION_READ,
    PERMISSION_APPLICATION_UPDATE,
)
from backend.app.db.models import Application, User
from backend.app.db.session import get_db
from backend.app.repositories.outbox_repository import OutboxRepository
from backend.app.repositories.validation_repository import ValidationRepository
from backend.app.schemas.validation import (
    FindingRead,
    ScrutinyReportResponse,
    ValidationCheckResultRead,
    ValidationRunListResponse,
    ValidationRunRead,
    ValidationRunRequest,
)
from backend.app.services.validation_orchestration_service import (
    PRELIMINARY_ADVISORY_DISCLAIMER,
    ValidationOrchestrationService,
    _utc_now,
)

router = APIRouter()


@router.post(
    "/{application_id}/validate",
    response_model=ScrutinyReportResponse,
    summary="Validate application and generate preliminary scrutiny report",
    description="Run multi-document pre-scrutiny checks, evaluate eligibility and consistency, and persist reproducible findings.",
)
def validate_application_endpoint(
    application_id: int,
    payload: ValidationRunRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
    prefer: Annotated[str | None, Header(description="Async preference header")] = None,
) -> ScrutinyReportResponse:
    """Trigger application validation enforcing institutional boundaries and write permission."""
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    # Enforce tenant isolation & update permission (Auditor read-only cannot trigger validation)
    verify_institution_membership(
        db,
        current_user,
        app.institution_id,
        required_permission=PERMISSION_APPLICATION_UPDATE,
    )

    eval_date = payload.evaluation_date or _utc_now().date()
    ruleset_ver = payload.ruleset_version or "0.1.0-draft"
    checklist_mode = payload.checklist_type or "default"

    # Support asynchronous execution via Prefer: respond-async or async_mode
    is_async = payload.async_mode or (prefer and "respond-async" in prefer.lower())
    if is_async:
        run = ValidationRepository.create_run(
            db,
            application_id=app.id,
            evaluation_date=eval_date,
            ruleset_version=ruleset_ver,
            status="queued",
            outcome="processing_incomplete",
            triggered_by=current_user.username,
        )
        db.flush()

        outbox_payload = {
            "run_id": run.id,
            "application_id": app.id,
            "checklist_type": checklist_mode,
            "required_documents": payload.required_documents,
        }
        outbox_msg = OutboxRepository.create_message(
            db,
            topic="application.validation.requested",
            payload=outbox_payload,
        )
        db.commit()

        # Attempt immediate dispatch
        dispatch_outbox_message(db, outbox_msg)

        response.status_code = status.HTTP_202_ACCEPTED
        polling_url = f"/api/v1/applications/{app.id}/validation-runs/{run.id}"
        return ScrutinyReportResponse(
            application_id=app.id,
            application_type=app.application_type,
            academic_year=app.academic_year,
            institution_id=app.institution.institution_id if app.institution else str(app.institution_id),
            institution_name=app.institution.display_name if app.institution else "Unknown",
            validation_run=ValidationRunRead.model_validate(run),
            check_results=[],
            findings=[],
            disclaimer=PRELIMINARY_ADVISORY_DISCLAIMER,
            polling_url=polling_url,
        )

    # Synchronous evaluation
    service = ValidationOrchestrationService()
    run = service.run_validation(
        db,
        application_id=app.id,
        actor_id=current_user.username,
        evaluation_date=eval_date,
        checklist_type=checklist_mode,
        required_documents=payload.required_documents,
        ruleset_version=ruleset_ver,
    )

    check_results = ValidationRepository.list_check_results_for_run(db, run.id)
    findings = ValidationRepository.list_findings_for_run(db, run.id)

    response.status_code = status.HTTP_201_CREATED
    return ScrutinyReportResponse(
        application_id=app.id,
        application_type=app.application_type,
        academic_year=app.academic_year,
        institution_id=app.institution.institution_id if app.institution else str(app.institution_id),
        institution_name=app.institution.display_name if app.institution else "Unknown",
        validation_run=ValidationRunRead.model_validate(run),
        check_results=[ValidationCheckResultRead.model_validate(cr) for cr in check_results],
        findings=[FindingRead.model_validate(f) for f in findings],
        disclaimer=PRELIMINARY_ADVISORY_DISCLAIMER,
        polling_url=None,
    )


@router.get(
    "/{application_id}/validation-runs",
    response_model=ValidationRunListResponse,
    summary="List all validation runs for an application",
)
def list_application_validation_runs(
    application_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: Annotated[int, Query(ge=0, description="Offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Limit")] = 20,
) -> ValidationRunListResponse:
    """List validation runs scoped strictly to the authorized application."""
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
        required_permission=PERMISSION_APPLICATION_READ,
    )

    runs = ValidationRepository.list_runs_for_application(
        db, application_id, skip=skip, limit=limit
    )
    total_runs = len(runs)
    return ValidationRunListResponse(
        items=[ValidationRunRead.model_validate(r) for r in runs],
        total=total_runs,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{application_id}/validation-runs/{run_id}",
    response_model=ScrutinyReportResponse,
    summary="Get consolidated preliminary scrutiny report for a validation run",
)
def get_validation_run_report(
    application_id: int,
    run_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ScrutinyReportResponse:
    """Retrieve full scrutiny report enforcing institutional tenant boundary."""
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
        required_permission=PERMISSION_APPLICATION_READ,
    )

    run = ValidationRepository.get_run(db, run_id)
    if run is None or run.application_id != app.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Validation run not found",
        )

    check_results = ValidationRepository.list_check_results_for_run(db, run.id)
    findings = ValidationRepository.list_findings_for_run(db, run.id)

    return ScrutinyReportResponse(
        application_id=app.id,
        application_type=app.application_type,
        academic_year=app.academic_year,
        institution_id=app.institution.institution_id if app.institution else str(app.institution_id),
        institution_name=app.institution.display_name if app.institution else "Unknown",
        validation_run=ValidationRunRead.model_validate(run),
        check_results=[ValidationCheckResultRead.model_validate(cr) for cr in check_results],
        findings=[FindingRead.model_validate(f) for f in findings],
        disclaimer=PRELIMINARY_ADVISORY_DISCLAIMER,
        polling_url=f"/api/v1/applications/{app.id}/validation-runs/{run.id}" if run.status in ("queued", "running") else None,
    )


@router.get(
    "/{application_id}/validation-runs/{run_id}/findings",
    response_model=list[FindingRead],
    summary="Get findings for a validation run",
)
def get_validation_run_findings(
    application_id: int,
    run_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[FindingRead]:
    """Retrieve list of findings produced by a specific validation run."""
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
        required_permission=PERMISSION_APPLICATION_READ,
    )

    run = ValidationRepository.get_run(db, run_id)
    if run is None or run.application_id != app.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Validation run not found",
        )

    findings = ValidationRepository.list_findings_for_run(db, run.id)
    return [FindingRead.model_validate(f) for f in findings]
