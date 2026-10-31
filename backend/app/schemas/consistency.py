"""Request and response schemas for the institution-scoped consistency API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ConsistencyStatus = Literal["pending", "discrepancy_detected", "resolved"]


class ConsistencyCheckCreate(BaseModel):
    """Create a recorded consistency review for an existing application."""

    model_config = ConfigDict(extra="forbid")

    application_id: int = Field(gt=0)
    check_name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    related_field: str | None = Field(default=None, max_length=100)

    @field_validator("check_name")
    @classmethod
    def clean_check_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("check_name must not be blank.")
        return value

    @field_validator("description", "related_field")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ConsistencyCheckRead(BaseModel):
    """Persisted consistency check response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    check_name: str
    description: str | None
    related_field: str | None
    status: ConsistencyStatus
    created_at: datetime
    updated_at: datetime


class ConsistencyFindingCreate(BaseModel):
    """Record two compared values and the associated discrepancy finding."""

    model_config = ConfigDict(extra="forbid")

    consistency_check_id: int = Field(gt=0)
    field_name: str = Field(min_length=1, max_length=100)
    value_1: str = Field(max_length=4000)
    value_2: str = Field(max_length=4000)
    severity: str = Field(min_length=1, max_length=30)
    confidence: float | None = Field(default=None, ge=0, le=1)
    description: str = Field(min_length=1, max_length=4000)
    evidence: dict[str, Any] | None = None

    @field_validator("field_name")
    @classmethod
    def clean_field_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field_name must not be blank.")
        return value

    @field_validator("severity")
    @classmethod
    def clean_severity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("severity must not be blank.")
        return value


class ConsistencyFindingUpdate(BaseModel):
    """Update only the reviewable attributes of a finding."""

    model_config = ConfigDict(extra="forbid")

    severity: str | None = Field(default=None, min_length=1, max_length=30)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    evidence: dict[str, Any] | None = None
    resolved: bool | None = None

    @model_validator(mode="after")
    def require_update(self) -> ConsistencyFindingUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one finding field must be supplied.")
        for field in ("severity", "description", "resolved"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null.")
        if self.description is not None:
            self.description = self.description.strip()
            if not self.description:
                raise ValueError("description must not be blank.")
        if self.severity is not None:
            self.severity = self.severity.strip()
            if not self.severity:
                raise ValueError("severity must not be blank.")
        return self


class ConsistencyFindingRead(BaseModel):
    """Persisted consistency finding response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    consistency_check_id: int
    field_name: str
    value_1: str
    value_2: str
    severity: str
    confidence: float | None
    description: str
    evidence: dict[str, Any] | None
    resolved: bool
    created_at: datetime
    updated_at: datetime
