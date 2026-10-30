"""Pydantic schemas for institution-scoped remediation plans.

The plan is derived by the client from a preliminary validation result; this API persists it,
attributes progress to users, and records status changes. It does not evaluate compliance and
must not be read as an AICTE determination.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PlanStatus = Literal["open", "in_progress", "blocked", "done"]
FindingCode = Literal["MISSING_DOCUMENT", "DOCUMENT_EXPIRED", "EXPIRING_SOON"]
Priority = Literal["P1", "P2", "P3"]

#: Upper bound for any configurable offset. Deliberately generous but bounded, so a client cannot
#: schedule a task years out and call it a deadline.
MAX_DEADLINE_DAYS = 365


class DeadlinePolicy(BaseModel):
    """Recommended internal deadlines. These are NOT AICTE deadlines and carry no official status."""

    p1_days: int = Field(default=3, ge=1, le=MAX_DEADLINE_DAYS)
    p2_days: int = Field(default=7, ge=1, le=MAX_DEADLINE_DAYS)
    p3_buffer_days: int = Field(default=14, ge=0, le=MAX_DEADLINE_DAYS)
    p3_max_days: int = Field(default=21, ge=1, le=MAX_DEADLINE_DAYS)
    expiring_window_days: int = Field(default=60, ge=1, le=MAX_DEADLINE_DAYS)

    @field_validator("p2_days")
    @classmethod
    def _p2_not_earlier_than_p1(cls, value: int, info) -> int:
        p1 = info.data.get("p1_days")
        if p1 is not None and value < p1:
            raise ValueError("p2_days must be greater than or equal to p1_days")
        return value


class RemediationTaskInput(BaseModel):
    task_key: str = Field(min_length=1, max_length=160)
    document_id: str = Field(min_length=1, max_length=100)
    document_label: str = Field(min_length=1, max_length=255)
    finding_code: FindingCode
    priority: Priority
    owner_role: str = Field(min_length=1, max_length=120)
    due_date: date
    evidence_required: str = Field(min_length=1, max_length=2000)
    clause: str | None = Field(default=None, max_length=80)


class RemediationPlanCreateRequest(BaseModel):
    """Create-or-get. Re-posting the same (institution, plan_key) returns the stored plan."""

    institution_ref: str = Field(
        min_length=1,
        max_length=100,
        description="The institution identifier used by the validation request, e.g. 1-1097261821.",
    )
    plan_key: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_.:-]+$",
        description="Client-computed deficiency signature; stable across re-runs of the same checklist.",
    )
    application_type: str = Field(min_length=1, max_length=50)
    deadline_policy: DeadlinePolicy = Field(default_factory=DeadlinePolicy)
    items: list[RemediationTaskInput] = Field(min_length=1, max_length=100)

    @field_validator("items")
    @classmethod
    def _unique_task_keys(cls, value: list[RemediationTaskInput]) -> list[RemediationTaskInput]:
        keys = [item.task_key for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("task_key values must be unique within a plan")
        return value


class RemediationTaskUpdateRequest(BaseModel):
    """Status and/or note update. `version` is mandatory so concurrent edits cannot overwrite."""

    status: PlanStatus | None = None
    note: str | None = Field(default=None, max_length=280)
    version: int = Field(ge=1)


class DeadlinePolicyUpdateRequest(BaseModel):
    """Administrator reschedule request. Internal planning policy only, never an AICTE deadline."""

    policy: DeadlinePolicy


class RemediationDeadlineChangeRead(BaseModel):
    id: int
    changed_by: str
    previous_policy: DeadlinePolicy
    new_policy: DeadlinePolicy
    rescheduled_tasks: int
    created_at: datetime


class RemediationTaskRead(BaseModel):
    id: int
    task_key: str
    document_id: str
    document_label: str
    finding_code: str
    priority: str
    owner_role: str
    due_date: date
    evidence_required: str
    clause: str | None
    status: str
    note: str
    version: int
    status_changed_by: str | None
    status_changed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RemediationPlanRead(BaseModel):
    id: int
    institution_id: int
    institution_ref: str
    plan_key: str
    application_type: str
    deadline_policy: DeadlinePolicy
    created_by: str
    created_at: datetime
    updated_at: datetime
    tasks: list[RemediationTaskRead]
    deadline_history: list[RemediationDeadlineChangeRead] = Field(default_factory=list)
    notice: str = (
        "Stored institutional work plan derived from a preliminary validation result. It is not an "
        "AICTE determination, and its due dates are internal recommendations, not AICTE deadlines."
    )


class RemediationPlanListResponse(BaseModel):
    items: list[RemediationPlanRead]
    total: int
