"""Pydantic schemas for documents, versions, jobs, and extraction observations."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentVersionRead(BaseModel):
    id: int
    document_id: int
    version_number: int
    storage_key: str
    sha256: str
    media_type: str
    byte_size: int
    page_count: int | None = None
    file_name: str | None = None
    scan_status: str | None = None
    processing_status: str
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentRead(BaseModel):
    id: int
    application_id: int
    document_type: str
    current_version_id: int | None = None
    created_at: datetime
    current_version: DocumentVersionRead | None = None

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    items: list[DocumentRead]
    total: int


class ExtractedFieldRead(BaseModel):
    id: int
    document_version_id: int
    field_name: str
    raw_text: str
    normalized_value: str | None = None
    confidence: float | None = None
    page_number: int | None = None
    engine_name: str
    extraction_status: str

    model_config = ConfigDict(from_attributes=True)


class ProcessingJobRead(BaseModel):
    id: str
    document_version_id: int
    job_type: str
    state: str
    attempt_count: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_error_code: str | None = None
    polling_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProcessingJobStatusResponse(BaseModel):
    job_id: str
    document_id: int
    version_id: int
    application_id: int
    state: str
    scan_status: str | None = None
    processing_status: str
    attempt_count: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_error_code: str | None = None
    extracted_fields_count: int = 0
    findings_count: int = 0
    is_terminal: bool = False
    notice: str = (
        "Advisory status only. A queued or completed job is not proof of regulatory compliance or document authenticity."
    )


class DocumentUploadResponse(BaseModel):
    document: DocumentRead
    version: DocumentVersionRead
    job: ProcessingJobRead | None = None
    polling_url: str | None = None
    extracted_fields_count: int = Field(default=0)
    notice: str = (
        "Document accepted for asynchronous processing. "
        "OCR output is evidence for human review, never proof of authenticity or regulatory compliance."
    )
