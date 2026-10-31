"""Tenant-scoped requirement gap analysis endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, verify_institution_membership
from backend.app.core.rbac import PERMISSION_APPLICATION_READ, PERMISSION_APPLICATION_UPDATE, PERMISSION_REVIEW_ACTION
from backend.app.db.models import Application, DocumentVersion, ExtractedField, RequirementAssessment, RequirementEvidenceMapping, RuleApprovalRecord, User, ValidationRun
from backend.app.db.session import get_db
from backend.app.schemas.gap_analyzer import EvidenceMappingCreate, EvidenceMappingRead, EvidenceMappingReview, GapAnalysisRead, GapMetrics, RequirementAssessmentRead, RequirementAssessmentReview, RequirementRead
from backend.app.services import gap_analyzer_service as svc

router = APIRouter()


def _application(db: Session, app_id: int, user: User, permission: str = PERMISSION_APPLICATION_READ) -> Application:
    app = db.get(Application, app_id)
    if app is None:
        raise HTTPException(404, "Application not found")
    verify_institution_membership(db, user, app.institution_id, required_permission=permission)
    return app


@router.get("/{application_id}/gap-requirements", response_model=list[RequirementRead])
def list_gap_requirements(application_id: int, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return svc.get_requirements_for_application(db, _application(db, application_id, user))


@router.get("/{application_id}/requirement-evidence-mappings", response_model=list[EvidenceMappingRead])
def list_mappings(application_id: int, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    _application(db, application_id, user)
    return [svc.serialize_mapping(db, m) for m in svc.get_mappings_for_application(db, application_id)]


@router.post("/{application_id}/requirement-evidence-mappings", response_model=EvidenceMappingRead, status_code=201)
def create_mapping(application_id: int, payload: EvidenceMappingCreate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    app = _application(db, application_id, user, PERMISSION_APPLICATION_UPDATE)
    approval = db.get(RuleApprovalRecord, payload.rule_approval_id)
    version = db.get(DocumentVersion, payload.document_version_id)
    field = db.get(ExtractedField, payload.extracted_field_id) if payload.extracted_field_id else None
    if approval is None or version is None or (payload.extracted_field_id and field is None):
        raise HTTPException(404, "Requirement or evidence record not found")
    try:
        mapping = svc.create_mapping(db, application=app, rule_approval=approval, version=version, extracted_field=field, page_number=payload.page_number, excerpt=payload.evidence_excerpt, rationale=payload.rationale, actor=user.username)
        db.commit()
        db.refresh(mapping)
        return svc.serialize_mapping(db, mapping)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.patch("/{application_id}/requirement-evidence-mappings/{mapping_id}", response_model=EvidenceMappingRead)
def review_mapping(application_id: int, mapping_id: int, payload: EvidenceMappingReview, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    app = _application(db, application_id, user, PERMISSION_REVIEW_ACTION)
    mapping = db.get(RequirementEvidenceMapping, mapping_id)
    if mapping is None or mapping.application_id != app.id:
        raise HTTPException(404, "Evidence mapping not found")
    try:
        result = svc.review_mapping(db, mapping=mapping, status=payload.status, sufficiency_status=payload.sufficiency_status, rationale=payload.rationale, actor=user.username, institution_id=app.institution_id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    return svc.serialize_mapping(db, result)


@router.get("/{application_id}/validation-runs/{run_id}/requirement-assessments", response_model=list[RequirementAssessmentRead])
def assessments(application_id: int, run_id: int, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    _application(db, application_id, user)
    run = db.get(ValidationRun, run_id)
    if run is None or run.application_id != application_id:
        raise HTTPException(404, "Validation run not found")
    return [svc.assessment_to_read(db, item) for item in svc.list_assessments_for_run(db, application_id, run_id)]


@router.get("/{application_id}/gap-analysis", response_model=GapAnalysisRead)
def gap_analysis(application_id: int, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)], run_id: int | None = None):
    _application(db, application_id, user)
    if run_id is None:
        run_id = db.scalar(select(ValidationRun.id).where(ValidationRun.application_id == application_id).order_by(ValidationRun.created_at.desc()).limit(1))
    if run_id is None:
        raise HTTPException(404, "No assessment run is available")
    run = db.get(ValidationRun, run_id)
    if run is None or run.application_id != application_id:
        raise HTTPException(404, "Validation run not found")
    items = [svc.assessment_to_read(db, row) for row in svc.list_assessments_for_run(db, application_id, run_id)]
    applicable = [x for x in items if x.applicability_status == "applicable"]
    counts = {key: sum(x.outcome_status == key for x in items) for key in ("compliant", "partially_compliant", "potential_gap", "missing_evidence", "manual_verification_required", "not_applicable")}
    coverage = round(100 * counts["compliant"] / len(applicable), 1) if applicable else None
    metrics = GapMetrics(application_id=application_id, validation_run_id=run_id, total_requirements=len(items), applicable_requirements=len(applicable), compliant=counts["compliant"], partially_compliant=counts["partially_compliant"], potential_gaps=counts["potential_gap"], missing_evidence=counts["missing_evidence"], manual_verification_required=counts["manual_verification_required"], not_applicable=counts["not_applicable"], pending_review=sum(x.review_status == "pending" for x in items), coverage_percent=coverage, overall_status="requires_review" if any(x.outcome_status in {"potential_gap", "missing_evidence", "manual_verification_required"} for x in items) else "complete")
    return GapAnalysisRead(metrics=metrics, requirements=items)


@router.patch("/{application_id}/validation-runs/{run_id}/requirement-assessments/{assessment_id}", response_model=RequirementAssessmentRead)
def review_assessment(application_id: int, run_id: int, assessment_id: int, payload: RequirementAssessmentReview, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    app = _application(db, application_id, user, PERMISSION_REVIEW_ACTION)
    item = db.get(RequirementAssessment, assessment_id)
    if item is None or item.application_id != app.id or item.validation_run_id != run_id:
        raise HTTPException(404, "Requirement assessment not found")
    previous = item.review_status
    item.review_status = payload.status
    item.reviewed_by = user.username
    from datetime import datetime, timezone
    item.reviewed_at = datetime.now(timezone.utc)
    item.review_rationale = payload.rationale
    from backend.app.db.models import AuditEvent
    import json
    db.add(AuditEvent(institution_id=app.institution_id, actor_id=user.username, action="REQUIREMENT_ASSESSMENT_REVIEWED", target_type="RequirementAssessment", target_id=str(item.id), details=json.dumps({"previous_status": previous, "new_status": payload.status, "rationale": payload.rationale, "application_id": app.id, "run_id": run_id})))
    db.commit()
    db.refresh(item)
    return svc.assessment_to_read(db, item)
