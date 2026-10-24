"""Pydantic schemas for institutions and applications."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InstitutionCreate(BaseModel):
    institution_id: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=255)
    status: str = "active"


class InstitutionRead(BaseModel):
    id: int
    institution_id: str
    display_name: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationCreate(BaseModel):
    institution_id: int
    application_type: Literal["eoa", "new_program", "intake_change"]
    academic_year: str = Field(description="Academic year in YYYY-YYYY format, e.g. 2026-2027")
    status: str = "draft"


class ApplicationUpdate(BaseModel):
    status: str | None = None
    academic_year: str | None = None


class ApplicationCreateRequest(BaseModel):
    institution_id: int | None = Field(
        default=None,
        description="Target institution ID. If omitted, derived from user's active institutional scope.",
    )
    application_type: Literal["eoa", "new_program", "intake_change"]
    academic_year: str = Field(description="Academic year in YYYY-YYYY format, e.g. 2026-2027")
    status: str = "draft"


class ApplicationRead(BaseModel):
    id: int
    institution_id: int
    application_type: str
    academic_year: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationListResponse(BaseModel):
    items: list[ApplicationRead]
    total: int
    skip: int
    limit: int

