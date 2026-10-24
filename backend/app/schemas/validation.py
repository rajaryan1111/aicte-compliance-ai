"""Validation run, check results, findings, and scrutiny report schemas."""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ValidationRunRequest(BaseModel):
    """Payload to trigger an application pre-scrutiny validation run."""

    model_config = ConfigDict(extra="forbid")

    evaluation_date: date | None = Field(
        default=None,
        description="Authoritative date against which document expiries are evaluated. Defaults to current UTC date.",
    )
    ruleset_version: str | None = Field(
        default="0.1.0-draft",
        description="Requested ruleset version identifier or tag.",
    )
    checklist_type: Literal["default", "synthetic_demo", "caller_specified"] | None = Field(
        default="default",
        description="Checklist mode: 'default' (official catalogue check), 'synthetic_demo' (versioned demo rules), or 'caller_specified'.",
    )
    required_documents: list[str] | None = Field(
        default=None,
        description="Explicit required document slot list when checklist_type is 'caller_specified'.",
    )
    async_mode: bool | None = Field(
        default=False,
        description="Whether to enqueue the validation run for asynchronous background processing.",
    )


class ValidationCheckResultRead(BaseModel):
    """Deterministic result for an individual evaluation check."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    validation_run_id: int
    check_id: str
    check_name: str
    category: str
    status: Literal["passed", "failed", "inconclusive", "not_applicable", "not_run"]
    document_version_id: int | None = None
    message: str
    evidence: str | None = None
    limitations: str | None = None
    created_at: datetime


class FindingRead(BaseModel):
    """Individual advisory finding linked to a validation run and document version."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    validation_run_id: int
    document_version_id: int | None = None
    code: str
    status: str
    severity: str
    summary: str
    evidence: str | None = None
    created_at: datetime


class ValidationRunSummaryCounts(BaseModel):
    """Aggregated count of individual check outcomes for a validation run."""

    passed: int = 0
    failed: int = 0
    inconclusive: int = 0
    not_applicable: int = 0
    not_run: int = 0


class ValidationRunRead(BaseModel):
    """Summary of a persisted ValidationRun execution and preliminary outcome."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    status: Literal["queued", "running", "succeeded", "partial", "failed"]
    outcome: Literal["preliminary_checks_passed", "attention_required", "inconclusive", "processing_incomplete"] | None = None
    evaluation_date: date
    ruleset_version: str
    started_at: datetime
    completed_at: datetime | None = None
    triggered_by: str | None = None
    consumed_version_ids: list[int] = Field(default_factory=list)
    summary_counts: ValidationRunSummaryCounts = Field(default_factory=ValidationRunSummaryCounts)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("consumed_version_ids", mode="before")
    @classmethod
    def parse_consumed_version_ids(cls, v: Any) -> list[int]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return [int(x) for x in parsed] if isinstance(parsed, list) else []
            except Exception:
                return []
        if isinstance(v, list):
            return [int(x) for x in v]
        return []

    @field_validator("summary_counts", mode="before")
    @classmethod
    def parse_summary_counts(cls, v: Any) -> ValidationRunSummaryCounts:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return ValidationRunSummaryCounts(**parsed) if isinstance(parsed, dict) else ValidationRunSummaryCounts()
            except Exception:
                return ValidationRunSummaryCounts()
        if isinstance(v, dict):
            return ValidationRunSummaryCounts(**v)
        if isinstance(v, ValidationRunSummaryCounts):
            return v
        return ValidationRunSummaryCounts()

    @field_validator("limitations", mode="before")
    @classmethod
    def parse_limitations(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return [str(x) for x in parsed] if isinstance(parsed, list) else []
            except Exception:
                return []
        if isinstance(v, list):
            return [str(x) for x in v]
        return []


class ScrutinyReportResponse(BaseModel):
    """Consolidated preliminary scrutiny report for an authorized application validation run."""

    model_config = ConfigDict(from_attributes=True)

    application_id: int
    application_type: str
    academic_year: str
    institution_id: str
    institution_name: str
    validation_run: ValidationRunRead
    check_results: list[ValidationCheckResultRead] = Field(default_factory=list)
    findings: list[FindingRead] = Field(default_factory=list)
    disclaimer: str
    polling_url: str | None = None


class ValidationRunListResponse(BaseModel):
    """Paginated list of historical validation runs for an application."""

    items: list[ValidationRunRead]
    total: int
    skip: int = 0
    limit: int = 20
