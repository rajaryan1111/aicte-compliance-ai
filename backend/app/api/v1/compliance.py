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
    PERMISSION_RETENTION_MANAGE,
    PERMISSION_RULE_APPROVE,
    PERMISSION_RULE_READ,
    PERMISSION_RULE_VERIFY,
    has_permission,
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
    RetentionRunRead,
    RetentionStatusResponse,
    RetentionTriggerInput,
    RuleApprovalInput,
    RuleApprovalRead,
    RuleSourceVerificationInput,
    RuleSourceVerificationRead,
    RuleSummaryRead,
    VerificationAttemptRead,
    VerificationRequestInput,
)
from backend.app.services.infrastructure_review_service import InfrastructureReviewService
from backend.app.services.institutional_record_service import InstitutionalRecordService
from backend.app.services.issuing_authority_service import IssuingAuthorityService

router = APIRouter()

def _get_effective_user_role(user: User) -> str:
    if hasattr(user, "role") and user.role:
        return user.role
    if hasattr(user, "memberships") and user.memberships:
        for m in user.memberships:
            if m.is_active and m.role:
                return m.role
    return ""



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
# 5. Data Retention & Privacy Enforcement Endpoints
# ---------------------------------------------------------------------------
@router.get(
    "/retention/status",
    response_model=RetentionStatusResponse,
    summary="View retention policy enforcement and scheduler status",
    tags=["retention"],
)
def get_retention_status(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RetentionStatusResponse:
    """Return retention policy configuration, status of scheduler, and latest execution record."""
    from backend.app.services.retention_scheduler import RetentionBackgroundScheduler
    from backend.app.services.retention_service import (
        AUDIT_LOG_MINIMUM_RETENTION_YEARS,
        DEFAULT_JOB_RETENTION_DAYS,
        DEFAULT_QUARANTINE_RETENTION_DAYS,
        DEFAULT_SCHEDULE_INTERVAL_SECONDS,
        RetentionService,
    )

    scheduler = RetentionBackgroundScheduler.get_instance()
    latest_run = RetentionService.get_latest_run(db)

    import os
    inprocess_enabled = os.getenv("ENABLE_INPROCESS_RETENTION_SCHEDULER", "false").lower() in ("true", "1")
    return RetentionStatusResponse(
        primary_scheduler="celery_beat",
        celery_beat_configured=True,
        inprocess_scheduler_enabled=inprocess_enabled,
        scheduler_running=scheduler.is_running(),
        schedule_interval_seconds=scheduler.interval_seconds,
        quarantine_retention_days=DEFAULT_QUARANTINE_RETENTION_DAYS,
        job_retention_days=DEFAULT_JOB_RETENTION_DAYS,
        audit_log_retention_years=AUDIT_LOG_MINIMUM_RETENTION_YEARS,
        last_run=latest_run,
    )


@router.post(
    "/retention/purge",
    response_model=RetentionRunRead,
    summary="Trigger retention policy enforcement pass (dry-run or live)",
    tags=["retention"],
)
def trigger_retention_purge(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    payload: RetentionTriggerInput | None = None,
) -> RetentionRunRead:
    """Execute scheduled or manual retention pass with RBAC permission check."""
    user_role = _get_effective_user_role(current_user)
    current_user.role = user_role
    if not has_permission(user_role, PERMISSION_RETENTION_MANAGE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User lacks required permission '{PERMISSION_RETENTION_MANAGE}' to execute retention purge.",
        )

    from backend.app.services.retention_service import RetentionService

    dry_run = payload.dry_run if payload else False
    quarantine_days = payload.quarantine_days if payload else 30
    job_days = payload.job_days if payload else 14

    rec = RetentionService.run_retention_pass(
        db,
        execution_type="manual" if not dry_run else "dry_run",
        dry_run=dry_run,
        actor_id=current_user.username,
        quarantine_retention_days=quarantine_days,
        job_retention_days=job_days,
    )
    return rec


@router.get(
    "/retention/runs",
    response_model=list[RetentionRunRead],
    summary="List past retention runs",
    tags=["retention"],
)
def list_retention_runs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 20,
) -> list[RetentionRunRead]:
    """List historical retention execution runs."""
    from backend.app.services.retention_service import RetentionService
    return RetentionService.list_retention_runs(db, limit=limit)


# ---------------------------------------------------------------------------
# 6. Regulatory Rule Governance Endpoints
# ---------------------------------------------------------------------------
@router.get(
    "/rules",
    response_model=list[RuleSummaryRead],
    summary="List canonical regulatory rule drafts and active approval states",
    tags=["rule-governance"],
)
def list_regulatory_rules(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[RuleSummaryRead]:
    """List draft and active statutory rule versions."""
    from backend.app.services.rule_engine import RuleApprovalService, build_aph_draft_rules

    drafts = build_aph_draft_rules()
    approvals = {a.rule_id: a for a in RuleApprovalService.get_approval_records(db) if a.status == "active"}

    summaries: list[RuleSummaryRead] = []
    for d in drafts:
        active_appr = approvals.get(d.rule_id)
        summaries.append(
            RuleSummaryRead(
                rule_id=d.rule_id,
                version=d.version,
                title=d.title,
                status="active" if active_appr else "draft",
                source_clause=d.source_clause,
                source_page=d.source_page,
                effective_from=d.effective_from.isoformat() if d.effective_from else None,
                effective_to=d.effective_to.isoformat() if d.effective_to else None,
                has_active_approval=active_appr is not None,
                reviewer_username=active_appr.reviewer_username if active_appr else None,
            )
        )
    return summaries


@router.post(
    "/rules/{rule_id}/verify-source",
    response_model=RuleSourceVerificationRead,
    status_code=status.HTTP_200_OK,
    summary="Record attributable source provenance verification for a regulatory rule",
    tags=["rule-governance"],
)
def verify_rule_source(
    rule_id: str,
    payload: RuleSourceVerificationInput,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RuleSourceVerificationRead:
    """Verify and attest the authoritative document source provenance with document SHA-256."""
    user_role = _get_effective_user_role(current_user)
    current_user.role = user_role
    if not has_permission(user_role, PERMISSION_RULE_VERIFY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User '{current_user.username}' lacks required permission '{PERMISSION_RULE_VERIFY}'.",
        )

    from backend.app.services.rule_engine import RuleApprovalService, build_aph_draft_rules

    drafts = {d.rule_id: d for d in build_aph_draft_rules()}
    draft = drafts.get(rule_id)
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft rule '{rule_id}' not found in canonical catalogue.",
        )

    try:
        verified_draft = RuleApprovalService.verify_source_db(
            db,
            rule_draft=draft,
            verifier_user=current_user,
            document_sha256=payload.document_sha256,
            rationale=payload.rationale,
        )
        return RuleSourceVerificationRead(
            rule_id=verified_draft.rule_id,
            version=verified_draft.version,
            status=verified_draft.source_provenance.status.value,
            verified_by=current_user.username,
            verified_at=(verified_draft.source_provenance.verified_at or datetime.now(timezone.utc).date()).isoformat(),
            document_sha256=payload.document_sha256,
            message="Source provenance verified and attributed successfully.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.post(
    "/rules/{rule_id}/approve",
    response_model=RuleApprovalRead,
    status_code=status.HTTP_201_CREATED,
    summary="Confer durable statutory approval on a verified rule draft",
    tags=["rule-governance"],
)
def approve_regulatory_rule(
    rule_id: str,
    payload: RuleApprovalInput,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RuleApprovalRead:
    """Record attributable statutory approval with user identity, RBAC checks, and audit logging."""
    user_role = _get_effective_user_role(current_user)
    current_user.role = user_role
    if not has_permission(user_role, PERMISSION_RULE_APPROVE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User '{current_user.username}' lacks PERMISSION_RULE_APPROVE permission.",
        )

    from backend.app.services.rule_engine import RuleApprovalService, build_aph_draft_rules

    drafts = {d.rule_id: d for d in build_aph_draft_rules()}
    draft = drafts.get(rule_id)
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft rule '{rule_id}' not found in canonical catalogue.",
        )

    try:
        record = RuleApprovalService.approve_rule_db(
            db,
            rule_draft=draft,
            reviewer_user=current_user,
            rationale=payload.rationale,
            statutory_interpretation_approved=payload.statutory_interpretation_approved,
        )
        return record
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.get(
    "/rules/history",
    response_model=list[RuleApprovalRead],
    summary="List all durable regulatory rule approval records",
    tags=["rule-governance"],
)
def list_rule_approvals(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    rule_id: str | None = None,
) -> list[RuleApprovalRead]:
    """List historical rule approvals with reviewer identities and rationales."""
    from backend.app.services.rule_engine import RuleApprovalService
    return RuleApprovalService.get_approval_records(db, rule_id=rule_id)

