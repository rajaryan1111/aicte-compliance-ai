"""Schemas for human review actions, finding resolution, and auditor workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReviewActionType = Literal[
    "acknowledge",
    "comment",
    "request_information",
    "resolve",
    "reopen",
    "escalate",
    "waive",
]

ResolutionOutcome = Literal[
    "issue_addressed",
    "false_positive_confirmed",
    "evidence_provided",
    "superseded_by_new_evidence",
]


class ReviewActionCreateRequest(BaseModel):
    """Payload to record an attributable human review action on a finding."""

    model_config = ConfigDict(extra="forbid")

    action: ReviewActionType = Field(
        description="Review action: acknowledge, comment, request_information, resolve, reopen, escalate, or waive."
    )
    comment: str | None = Field(
        default=None,
        max_length=2000,
        description="Attributable reviewer comment or observation note.",
    )
    resolution_outcome: ResolutionOutcome | None = Field(
        default=None,
        description="Explicit classification when resolving a finding.",
    )
    rationale: str | None = Field(
        default=None,
        max_length=2000,
        description="Mandatory justification/rationale for resolve, waive, reopen, or escalate.",
    )
    evidence_ref: str | None = Field(
        default=None,
        max_length=500,
        description="Optional evidence reference (e.g. storage key, uploaded affidavit ID, verification doc).",
    )
    expected_version: int | None = Field(
        default=None,
        description="Optimistic concurrency control: expected current version of the finding.",
    )
    request_id: str | None = Field(
        default=None,
        max_length=100,
        description="Unique client request ID for safe, idempotent action submission.",
    )


class ReviewActionRead(BaseModel):
    """Historical attributable review action recorded on an application or finding."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    finding_id: int | None = None
    validation_run_id: int | None = None
    reviewer_id: str
    actor_role: str | None = None
    action: str
    previous_status: str | None = None
    new_status: str | None = None
    comment: str | None = None
    rationale: str | None = None
    request_id: str | None = None
    evidence_ref: str | None = None
    created_at: datetime


class FindingWithReviewRead(BaseModel):
    """Finding details including current review status and historical reviewer actions."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    validation_run_id: int
    document_version_id: int | None = None
    code: str
    status: str
    severity: str
    summary: str
    evidence: str | None = None
    resolution_rationale: str | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    version: int
    created_at: datetime
    review_actions: list[ReviewActionRead] = Field(default_factory=list)


class FindingListResponse(BaseModel):
    """Paginated list of findings for an application."""

    items: list[FindingWithReviewRead]
    total: int
    skip: int = 0
    limit: int = 20


class ReviewSummaryResponse(BaseModel):
    """Summary of all review statuses and pending action items for an application."""

    model_config = ConfigDict(from_attributes=True)

    application_id: int
    application_type: str
    academic_year: str
    institution_id: str
    total_findings: int
    open_count: int
    acknowledged_count: int
    under_review_count: int
    resolved_count: int
    escalated_count: int
    waived_count: int
    pending_action_count: int
    recent_actions: list[ReviewActionRead] = Field(default_factory=list)
    generated_at: datetime
    notice: str = Field(
        default=(
            "Advisory summary only. Human review findings and waivers assist compliance scrutiny "
            "and do not constitute official statutory AICTE approval."
        )
    )


class ReviewQueueItemRead(BaseModel):
    """Single item in the reviewer queue across authorized institutions."""

    finding: FindingWithReviewRead
    application_id: int
    institution_id: str
    institution_name: str
    application_type: str
    academic_year: str


class ReviewQueueResponse(BaseModel):
    """Paginated response of active review items in the reviewer queue."""

    items: list[ReviewQueueItemRead]
    total: int
    skip: int = 0
    limit: int = 20


class ReviewActionResponse(BaseModel):
    """Response returned upon recording a human review action."""

    finding: FindingWithReviewRead
    action: ReviewActionRead
    message: str
