"""Schemas for requirement registry, evidence links and requirement assessments."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RequirementRead(BaseModel):
    id: int
    rule_id: str
    version: int
    title: str
    description: str
    category: str
    source_title: str
    source_issuer: str
    source_url: str
    source_clause: str
    source_page: str
    source_document_version: str
    source_sha256: str | None = None
    source_verified_by: str
    source_verified_at: date
    effective_from: date
    effective_to: date | None = None
    applicable: bool
    applicability_reason: str
    applicability_conditions: list[str]
    required_evidence_type: str | None = None
    evaluation_method: Literal["deterministic_rule"] = "deterministic_rule"


class EvidenceMappingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_approval_id: int = Field(gt=0)
    document_version_id: int = Field(gt=0)
    extracted_field_id: int | None = Field(default=None, gt=0)
    page_number: int | None = Field(default=None, ge=1)
    evidence_excerpt: str | None = Field(default=None, max_length=4000)
    rationale: str = Field(min_length=5, max_length=1000)


class EvidenceMappingReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["confirmed", "rejected", "request_information"]
    sufficiency_status: Literal["sufficient", "insufficient"] | None = None
    rationale: str = Field(min_length=5, max_length=1000)


class EvidenceReviewHistory(BaseModel):
    actor: str | None = None
    status: str | None = None
    sufficiency_status: str | None = None
    rationale: str
    reviewed_at: datetime


class EvidenceMappingRead(BaseModel):
    id: int
    application_id: int
    rule_approval_id: int
    rule_id: str
    rule_version: int
    document_id: int
    document_type: str
    document_version_id: int
    version_number: int
    file_name: str | None = None
    scan_status: str | None = None
    uploaded_at: datetime | None = None
    processing_status: str
    sha256: str
    extracted_field_id: int | None = None
    field_name: str | None = None
    page_number: int | None = None
    evidence_excerpt: str | None = None
    extraction_confidence: float | None = None
    status: str
    sufficiency_status: str | None = None
    source: str
    rationale: str
    created_by: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_rationale: str | None = None
    created_at: datetime
    review_history: list[EvidenceReviewHistory] = Field(default_factory=list)


class FindingEvidenceRead(BaseModel):
    id: int
    document_id: int | None = None
    document_type: str | None = None
    file_name: str | None = None
    sha256: str | None = None
    uploaded_at: datetime | None = None
    document_version_id: int
    extracted_field_id: int | None = None
    page_number: int | None = None
    evidence_excerpt: str | None = None
    evidence_role: str
    confidence: float | None = None


class GapFindingRead(BaseModel):
    id: int
    code: str
    summary: str
    severity: str
    status: str
    document_version_id: int | None = None
    evidence: list[FindingEvidenceRead] = Field(default_factory=list)


class RequirementAssessmentRead(BaseModel):
    id: int
    application_id: int
    validation_run_id: int
    rule_approval_id: int
    rule_id: str
    rule_version: int
    title: str
    description: str
    category: str
    source_title: str
    source_url: str
    source_clause: str
    source_page: str
    applicability_status: str
    applicability_reason: str
    evaluation_status: str
    outcome_status: str
    evidence_sufficiency: str
    result_message: str
    evidence: list[dict[str, object]]
    confidence: float | None = None
    review_status: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_rationale: str | None = None
    created_at: datetime
    findings: list[GapFindingRead] = Field(default_factory=list)


class RequirementAssessmentReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "rejected", "request_information"]
    rationale: str = Field(min_length=5, max_length=1000)


class GapMetrics(BaseModel):
    application_id: int
    validation_run_id: int
    total_requirements: int
    applicable_requirements: int
    compliant: int
    partially_compliant: int
    potential_gaps: int
    missing_evidence: int
    manual_verification_required: int
    not_applicable: int
    pending_review: int
    coverage_percent: float | None
    overall_status: str


class GapAnalysisRead(BaseModel):
    metrics: GapMetrics
    requirements: list[RequirementAssessmentRead]
