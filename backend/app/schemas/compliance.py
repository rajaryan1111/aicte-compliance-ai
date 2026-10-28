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
