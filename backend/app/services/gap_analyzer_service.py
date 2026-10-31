"""Requirement-level gap analysis built on approved rule versions and existing evidence."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import (
    Application,
    AuditEvent,
    Document,
    DocumentVersion,
    ExtractedField,
    RequirementAssessment,
    RequirementAssessmentEvidence,
    RequirementEvidenceMapping,
    RuleApprovalRecord,
)
from backend.app.schemas.gap_analyzer import (
    EvidenceMappingRead,
    RequirementAssessmentRead,
    RequirementRead,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _year_variants(value: str) -> set[str]:
    year = value.strip()
    variants = {year}
    if "-" in year:
        first, second = year.split("-", 1)
        if len(first) == 4 and len(second) == 4:
            variants.add(f"{first}-{second[2:]}")
        elif len(first) == 4 and len(second) == 2:
            variants.add(f"{first}-{first[:2]}{second}")
    return variants


def active_requirement_records(db: Session) -> list[tuple[RuleApprovalRecord, object]]:
    """Return only durable approved, verified rule versions and validated definitions."""
    from backend.app.rule_catalog import RuleVersionDraft

    stmt = select(RuleApprovalRecord).where(
        RuleApprovalRecord.status == "active",
        RuleApprovalRecord.decision == "approved",
        RuleApprovalRecord.source_verification_status == "verified",
        RuleApprovalRecord.statutory_interpretation_approved.is_(True),
    ).order_by(RuleApprovalRecord.rule_id, RuleApprovalRecord.rule_version)
    result: list[tuple[RuleApprovalRecord, object]] = []
    for record in db.scalars(stmt).all():
        if not record.source_document_sha256:
            continue
        try:
            data = json.loads(record.rule_definition_json)
            draft = RuleVersionDraft.model_validate(data)
        except Exception:
            continue
        if draft.rule_id != record.rule_id or draft.version != record.rule_version:
            continue
        result.append((record, draft))
    return result


def get_requirements_for_application(db: Session, application: Application) -> list[RequirementRead]:
    from backend.app.services.rule_engine import required_evidence_type_for_rule

    year_variants = _year_variants(application.academic_year)
    requirements: list[RequirementRead] = []
    for record, draft_obj in active_requirement_records(db):
        draft = draft_obj
        type_match = application.application_type in draft.applicability.application_types
        year_match = bool(year_variants.intersection(draft.applicability.academic_years))
        today = date.today()
        date_match = (record.effective_from <= today) and (record.effective_to is None or today <= record.effective_to)
        applicable = type_match and year_match and date_match
        reason_parts = [
            f"Application type '{application.application_type}' {'matches' if type_match else 'does not match'} the approved rule scope.",
            f"Academic year '{application.academic_year}' {'matches' if year_match else 'does not match'} the approved rule scope.",
            f"Evaluation date {today.isoformat()} {'is' if date_match else 'is outside'} the approved effective interval.",
        ]
        requirements.append(RequirementRead(
            id=record.id,
            rule_id=record.rule_id,
            version=record.rule_version,
            title=draft.title,
            description=draft.description,
            category="Regulatory requirement",
            source_title=record.source_title,
            source_issuer=draft.source_issuer,
            source_url=str(draft.source_url),
            source_clause=record.source_clause,
            source_page=record.source_page,
            source_document_version=record.source_document_version,
            source_sha256=record.source_document_sha256,
            source_verified_by=record.source_verified_by,
            source_verified_at=record.source_verified_at,
            effective_from=record.effective_from,
            effective_to=record.effective_to,
            applicable=applicable,
            applicability_reason=" ".join(reason_parts),
            applicability_conditions=draft.applicability.conditions,
            required_evidence_type=required_evidence_type_for_rule(record.rule_id),
        ))
    return requirements


def create_mapping(
    db: Session,
    *,
    application: Application,
    rule_approval: RuleApprovalRecord,
    version: DocumentVersion,
    extracted_field: ExtractedField | None,
    page_number: int | None,
    excerpt: str | None,
    rationale: str,
    actor: str,
) -> RequirementEvidenceMapping:
    document = db.get(Document, version.document_id)
    if document is None or document.application_id != application.id:
        raise ValueError("Document version does not belong to this application.")
    if extracted_field is not None and extracted_field.document_version_id != version.id:
        raise ValueError("Extracted field does not belong to the selected document version.")
    if rule_approval not in [record for record, _ in active_requirement_records(db)]:
        raise ValueError("Only active, verified, approved requirement versions can be mapped.")

    mapping = RequirementEvidenceMapping(
        application_id=application.id,
        rule_approval_id=rule_approval.id,
        document_version_id=version.id,
        extracted_field_id=extracted_field.id if extracted_field else None,
        status="suggested",
        source="user",
        page_number=page_number or (extracted_field.page_number if extracted_field else None),
        evidence_excerpt=excerpt or (extracted_field.raw_text if extracted_field else None),
        rationale=rationale,
        created_by=actor,
    )
    db.add(mapping)
    db.flush()
    return mapping


def review_mapping(
    db: Session,
    *,
    mapping: RequirementEvidenceMapping,
    status: str,
    rationale: str,
    actor: str,
    institution_id: int,
) -> RequirementEvidenceMapping:
    previous_status = mapping.status
    mapping.status = status
    mapping.reviewed_by = actor
    mapping.reviewed_at = _utc_now()
    mapping.review_rationale = rationale
    db.add(AuditEvent(
        institution_id=institution_id,
        actor_id=actor,
        action=f"REQUIREMENT_EVIDENCE_MAPPING_{status.upper()}",
        target_type="RequirementEvidenceMapping",
        target_id=str(mapping.id),
        details=json.dumps({
            "application_id": mapping.application_id,
            "rule_approval_id": mapping.rule_approval_id,
            "document_version_id": mapping.document_version_id,
            "previous_status": previous_status,
            "new_status": status,
            "rationale": rationale,
        }),
    ))
    db.commit()
    db.refresh(mapping)
    return mapping


def serialize_mapping(db: Session, mapping: RequirementEvidenceMapping) -> EvidenceMappingRead:
    version = db.get(DocumentVersion, mapping.document_version_id)
    document = db.get(Document, version.document_id) if version else None
    approval = db.get(RuleApprovalRecord, mapping.rule_approval_id)
    field = db.get(ExtractedField, mapping.extracted_field_id) if mapping.extracted_field_id else None
    return EvidenceMappingRead(
        id=mapping.id,
        application_id=mapping.application_id,
        rule_approval_id=mapping.rule_approval_id,
        rule_id=approval.rule_id if approval else "unknown",
        rule_version=approval.rule_version if approval else 0,
        document_id=document.id if document else 0,
        document_type=document.document_type if document else "unknown",
        document_version_id=version.id if version else mapping.document_version_id,
        version_number=version.version_number if version else 0,
        file_name=version.file_name if version else None,
        scan_status=version.scan_status if version else None,
        processing_status=version.processing_status if version else "unknown",
        sha256=version.sha256 if version else "",
        extracted_field_id=field.id if field else None,
        field_name=field.field_name if field else None,
        page_number=mapping.page_number,
        evidence_excerpt=mapping.evidence_excerpt,
        extraction_confidence=field.confidence if field else None,
        status=mapping.status,
        source=mapping.source,
        rationale=mapping.rationale,
        created_by=mapping.created_by,
        reviewed_by=mapping.reviewed_by,
        reviewed_at=mapping.reviewed_at,
        review_rationale=mapping.review_rationale,
        created_at=mapping.created_at,
    )


def get_mappings_for_application(db: Session, application_id: int) -> list[RequirementEvidenceMapping]:
    stmt = select(RequirementEvidenceMapping).where(
        RequirementEvidenceMapping.application_id == application_id
    ).order_by(RequirementEvidenceMapping.created_at.desc(), RequirementEvidenceMapping.id.desc())
    return list(db.scalars(stmt).all())


def assessment_to_read(db: Session, item: RequirementAssessment) -> RequirementAssessmentRead:
    record = db.get(RuleApprovalRecord, item.rule_approval_id)
    if record is None:
        raise ValueError("Approved requirement version is unavailable.")
    draft_data = json.loads(record.rule_definition_json)
    evidence_snapshot = json.loads(item.evidence_snapshot or "[]")
    return RequirementAssessmentRead(
        id=item.id,
        application_id=item.application_id,
        validation_run_id=item.validation_run_id,
        rule_approval_id=item.rule_approval_id,
        rule_id=record.rule_id,
        rule_version=record.rule_version,
        title=draft_data.get("title", record.rule_id),
        description=draft_data.get("description", ""),
        category="Regulatory requirement",
        source_title=record.source_title,
        source_url=draft_data.get("source_url", ""),
        source_clause=record.source_clause,
        source_page=record.source_page,
        applicability_status=item.applicability_status,
        applicability_reason=item.applicability_reason,
        evaluation_status=item.evaluation_status,
        outcome_status=item.outcome_status,
        evidence_sufficiency=item.evidence_sufficiency,
        result_message=item.result_message,
        evidence=evidence_snapshot,
        confidence=item.confidence,
        review_status=item.review_status,
        reviewed_by=item.reviewed_by,
        reviewed_at=item.reviewed_at,
        review_rationale=item.review_rationale,
        created_at=item.created_at,
    )


def list_assessments_for_run(db: Session, application_id: int, run_id: int) -> list[RequirementAssessment]:
    stmt = select(RequirementAssessment).where(
        RequirementAssessment.application_id == application_id,
        RequirementAssessment.validation_run_id == run_id,
    ).order_by(RequirementAssessment.id.asc())
    return list(db.scalars(stmt).all())
