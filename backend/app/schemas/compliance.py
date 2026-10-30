"""Pydantic schemas for issuing-authority verification, infrastructure, and institutional comparisons."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class VerificationRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_name: str | None = Field(default=None, description="Optional adapter to use, defaults to best matching")
    force_simulated: bool = Field(default=False, description="Explicitly request simulated demonstration verification")


class VerificationAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    document_version_id: int
    attempt_reference: str
    adapter_name: str
    source_title: str
    is_official_source: bool
    status: str
    submitted_attributes: str | None = None
    returned_attributes: str | None = None
    failure_reason: str | None = None
    source_reference: str | None = None
    actor_id: str
    created_at: datetime


class InfrastructureItemRead(BaseModel):
    evidence_type: str
    document_version_id: int
    declared_area_sqm: float | None = None
    observed_area_sqm: float | None = None
    inspection_recommended: bool
    inspection_rationale: str | None = None
    analysis_metadata: dict[str, Any] = Field(default_factory=dict)


class InfrastructureReviewResponse(BaseModel):
    application_id: int
    overall_status: str
    physical_inspection_recommended: bool
    inspection_reasons: list[str]
    items: list[InfrastructureItemRead]
    evaluated_at: datetime


class RecordComparisonItemRead(BaseModel):
    record_type: str
    source_category: str
    source_reference: str | None = None
    claim_value: Any
    authorized_value: Any
    matched: bool
    discrepancy_explanation: str | None = None
    limitations: list[str] = Field(default_factory=list)


class InstitutionalComparisonResponse(BaseModel):
    application_id: int
    institution_id: str
    overall_consistency: str
    comparisons: list[RecordComparisonItemRead]
    evaluated_at: datetime


class FieldCorrectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corrected_value: str = Field(min_length=1, max_length=2000, description="User-verified corrected value")
    rationale: str = Field(min_length=5, max_length=500, description="Justification for human-in-the-loop correction")


class FieldCorrectionResponse(BaseModel):
    field_name: str
    previous_value: str | None
    corrected_value: str
    corrected_by: str
    corrected_at: datetime
    message: str


# ---------------------------------------------------------------------------
# 6. Regulatory Rule Governance Schemas
# ---------------------------------------------------------------------------
class RuleApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rationale: str = Field(min_length=10, max_length=1000, description="Attributable statutory review justification")
    statutory_interpretation_approved: bool = Field(default=True, description="Statutory interpretation approval affirmation")


class RuleApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: str
    rule_version: int
    status: str
    decision: str
    reviewer_username: str
    reviewer_role: str
    rationale: str
    source_title: str
    source_clause: str
    source_page: str
    source_document_version: str
    statutory_interpretation_approved: bool
    decided_at: datetime
    effective_from: Any
    effective_to: Any | None = None
    created_at: datetime


class RuleSummaryRead(BaseModel):
    rule_id: str
    version: int
    title: str
    status: str
    source_clause: str
    source_page: str
    effective_from: str | None = None
    effective_to: str | None = None
    has_active_approval: bool = False
    reviewer_username: str | None = None


# ---------------------------------------------------------------------------
# 7. Retention Policy & Execution Schemas
# ---------------------------------------------------------------------------
class RetentionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_reference: str
    execution_type: str
    dry_run: bool
    status: str
    quarantined_purged_count: int
    jobs_cleaned_count: int
    storage_errors_count: int
    triggered_by: str
    started_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None
    details: str | None = None


class RetentionTriggerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = Field(default=False, description="Simulate deletion pass without modifying disk or DB")
    quarantine_days: int = Field(default=30, ge=1, le=3650, description="Age threshold in days for quarantined files")
    job_days: int = Field(default=14, ge=1, le=365, description="Age threshold in days for completed/failed jobs")


class RetentionStatusResponse(BaseModel):
    scheduler_running: bool
    schedule_interval_seconds: int
    quarantine_retention_days: int
    job_retention_days: int
    audit_log_retention_years: int
    last_run: RetentionRunRead | None = None
