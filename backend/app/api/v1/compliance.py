"""API routes for issuing-authority verification, infrastructure review, institutional records, and field corrections."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import (
    get_current_user,
    verify_institution_membership,
)
from backend.app.core.rbac import (
    PERMISSION_APPLICATION_READ,
    PERMISSION_APPLICATION_UPDATE,
)
from backend.app.db.models import Application, Document, DocumentVersion, ExtractedField, User
from backend.app.db.session import get_db
from backend.app.repositories.review_audit_repository import ReviewAuditRepository
from backend.app.schemas.compliance import (
    FieldCorrectionInput,
    FieldCorrectionResponse,
    InfrastructureItemRead,
    InfrastructureReviewResponse,
    InstitutionalComparisonResponse,
    RecordComparisonItemRead,
    VerificationAttemptRead,
    VerificationRequestInput,
)
from backend.app.services.infrastructure_review_service import InfrastructureReviewService
from backend.app.services.institutional_record_service import InstitutionalRecordService
from backend.app.services.issuing_authority_service import IssuingAuthorityService

router = APIRouter()


# ---------------------------------------------------------------------------
# 1. Issuing-Authority Verification Endpoints
# ---------------------------------------------------------------------------
@router.post(
    "/applications/{application_id}/documents/{document_id}/versions/{version_id}/verify",
    response_model=VerificationAttemptRead,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger issuing-authority verification attempt",
    tags=["issuing-authority"],
)
def verify_document_version(
    application_id: int,
    document_id: int,
    version_id: int,
    req_body: VerificationRequestInput,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> VerificationAttemptRead:
    """Request an external issuing-authority verification or simulated demo verification."""
    app = db.get(Application, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    verify_institution_membership(
        db, current_user, app.institution_id, required_permission=PERMISSION_APPLICATION_UPDATE
    )

    doc = db.get(Document, document_id)
    if not doc or doc.application_id != app.id:
        raise HTTPException(status_code=404, detail="Document not found for this application.")

    version = db.get(DocumentVersion, version_id)
    if not version or version.document_id != doc.id:
        raise HTTPException(status_code=404, detail="DocumentVersion not found for this document.")

    try:
        attempt = IssuingAuthorityService.request_verification(
            db,
            application_id=app.id,
            document_version_id=version.id,
            adapter_name=req_body.adapter_name,
            actor_id=current_user.username,
            force_simulated=req_body.force_simulated,
        )
        return VerificationAttemptRead.model_validate(attempt)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Verification request failed: {exc}") from exc


@router.get(
    "/applications/{application_id}/verifications",
    response_model=list[VerificationAttemptRead],
    summary="List verification attempts for application",
    tags=["issuing-authority"],
)
def list_application_verifications(
    application_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[VerificationAttemptRead]:
    """Retrieve all recorded issuing-authority verification attempts for the application."""
    app = db.get(Application, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    verify_institution_membership(
        db, current_user, app.institution_id, required_permission=PERMISSION_APPLICATION_READ
    )

    attempts = IssuingAuthorityService.list_attempts(db, app.id)
    return [VerificationAttemptRead.model_validate(a) for a in attempts]


@router.get(
    "/verification-adapters",
    summary="List available issuing authority adapters",
    tags=["issuing-authority"],
)
def list_adapters() -> list[dict[str, Any]]:
    """List supported issuing authority adapters with official/simulated labels."""
    return IssuingAuthorityService.get_available_adapters()


# ---------------------------------------------------------------------------
# 2. Infrastructure Compliance Review Endpoints
# ---------------------------------------------------------------------------
@router.post(
    "/applications/{application_id}/infrastructure/review",
    response_model=InfrastructureReviewResponse,
    summary="Execute infrastructure compliance review",
    tags=["infrastructure"],
)
def execute_infrastructure_review(
    application_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> InfrastructureReviewResponse:
    """Analyze infrastructure evidence and check whether physical inspection by an EVC is required."""
    app = db.get(Application, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    verify_institution_membership(
        db, current_user, app.institution_id, required_permission=PERMISSION_APPLICATION_READ
    )

    summary = InfrastructureReviewService.review_application_infrastructure(
        db, app.id, actor_id=current_user.username
    )

    items = [
        InfrastructureItemRead(
            evidence_type=it.evidence_type,
            document_version_id=it.document_version_id,
            declared_area_sqm=it.declared_area_sqm,
            observed_area_sqm=it.observed_area_sqm,
            inspection_recommended=it.inspection_recommended,
            inspection_rationale=it.inspection_rationale,
            analysis_metadata=it.analysis_metadata,
        )
        for it in summary.items
    ]

    return InfrastructureReviewResponse(
        application_id=app.id,
        overall_status=summary.overall_status,
        physical_inspection_recommended=summary.physical_inspection_recommended,
        inspection_reasons=summary.inspection_reasons,
        items=items,
        evaluated_at=summary.evaluated_at,
    )


# ---------------------------------------------------------------------------
# 3. Institutional Record Comparison Endpoints
# ---------------------------------------------------------------------------
@router.get(
    "/applications/{application_id}/institutional-records",
    response_model=InstitutionalComparisonResponse,
    summary="Compare application with authorized institutional records",
    tags=["institutional-records"],
)
def get_institutional_record_comparison(
    application_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> InstitutionalComparisonResponse:
    """Compare application against previous EoA status, intake roster, NBA accreditation, and TER payment."""
    app = db.get(Application, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    verify_institution_membership(
        db, current_user, app.institution_id, required_permission=PERMISSION_APPLICATION_READ
    )

    report = InstitutionalRecordService.compare_application_against_records(
        db, app.id, actor_id=current_user.username
    )

    comparisons = [
        RecordComparisonItemRead(
            record_type=c.record_type,
            source_category=c.source_category,
            source_reference=c.source_reference,
            claim_value=c.claim_value,
            authorized_value=c.authorized_value,
            matched=c.matched,
            discrepancy_explanation=c.discrepancy_explanation,
            limitations=c.limitations,
        )
        for c in report.comparisons
    ]

    return InstitutionalComparisonResponse(
        application_id=app.id,
        institution_id=report.institution_id,
        overall_consistency=report.overall_consistency,
        comparisons=comparisons,
        evaluated_at=report.evaluated_at,
    )


# ---------------------------------------------------------------------------
# 4. Human-In-The-Loop Candidate Field Correction
# ---------------------------------------------------------------------------
@router.patch(
    "/applications/{application_id}/documents/{document_id}/versions/{version_id}/fields/{field_name}",
    response_model=FieldCorrectionResponse,
    summary="Submit human-in-the-loop field correction",
    tags=["documents"],
)
def correct_extracted_field(
    application_id: int,
    document_id: int,
    version_id: int,
    field_name: str,
    correction: FieldCorrectionInput,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FieldCorrectionResponse:
    """Submit human reviewer/applicant correction of an extracted candidate field with full audit trail."""
    app = db.get(Application, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    verify_institution_membership(
        db, current_user, app.institution_id, required_permission=PERMISSION_APPLICATION_UPDATE
    )

    doc = db.get(Document, document_id)
    if not doc or doc.application_id != app.id:
        raise HTTPException(status_code=404, detail="Document not found.")

    version = db.get(DocumentVersion, version_id)
    if not version or version.document_id != doc.id:
        raise HTTPException(status_code=404, detail="DocumentVersion not found.")

    stmt = select(ExtractedField).where(
        ExtractedField.document_version_id == version.id,
        ExtractedField.field_name == field_name,
    )
    field_obj = db.scalars(stmt).first()

    now = datetime.now(timezone.utc)
    prev_val = field_obj.normalized_value if field_obj else None

    if field_obj is None:
        # Create field if it was missing from machine extraction
        field_obj = ExtractedField(
            document_version_id=version.id,
            field_name=field_name,
            raw_text=correction.corrected_value,
            normalized_value=correction.corrected_value,
            confidence=1.0,
            engine_name="human_verified_correction",
            extraction_status="user_corrected",
            created_at=now,
        )
        db.add(field_obj)
    else:
        field_obj.normalized_value = correction.corrected_value
        field_obj.extraction_status = "user_corrected"
        field_obj.confidence = 1.0

    # Attributable audit event
    ReviewAuditRepository.create_audit_event(
        db,
        action="EXTRACTED_FIELD_USER_CORRECTED",
        target_type="ExtractedField",
        target_id=f"{version.id}:{field_name}",
        actor_id=current_user.username,
        institution_id=app.institution_id,
        details=json.dumps({
            "previous_value": prev_val,
            "corrected_value": correction.corrected_value,
            "rationale": correction.rationale,
        }),
    )
    db.commit()

    return FieldCorrectionResponse(
        field_name=field_name,
        previous_value=prev_val,
        corrected_value=correction.corrected_value,
        corrected_by=current_user.username,
        corrected_at=now,
        message="Field correction saved with attributable audit record.",
    )


# ---------------------------------------------------------------------------
# 5. Data Retention & Privacy Enforcement Endpoint
# ---------------------------------------------------------------------------
@router.post(
    "/retention/purge",
    summary="Trigger retention policy enforcement pass",
    tags=["retention"],
)
def trigger_retention_purge(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Execute scheduled retention pass: purge stale quarantined files and temporary processing jobs."""
    from backend.app.services.retention_service import RetentionService
    return RetentionService.run_scheduled_retention_pass(db, actor_id=current_user.username)
