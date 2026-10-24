"""Pydantic schemas for Exportable Audit Packages, Evidence Manifests, and Integrity Verification."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AuditPackageItemManifest(BaseModel):
    """Manifest entry for a single item inside the audit package."""

    model_config = ConfigDict(from_attributes=True)

    path: str = Field(description="Relative path inside the ZIP archive.")
    sha256: str = Field(description="SHA-256 digest of the uncompressed file.")
    byte_size: int = Field(description="Uncompressed file size in bytes.")
    content_type: str = Field(description="MIME media type.")


class AuditPackageManifest(BaseModel):
    """Cryptographic tamper-evident manifest embedded in the audit package."""

    model_config = ConfigDict(from_attributes=True)

    package_reference: str
    application_id: int
    institution_id: str
    academic_year: str
    application_type: str
    validation_run_id: int | None = None
    sha256_root_hash: str
    generated_at: datetime
    generated_by: str
    advisory_notice: str = (
        "Advisory audit package only. Pre-scrutiny observations, evidence manifests, "
        "and human review actions do not constitute official statutory AICTE approval or rejection."
    )
    items: list[AuditPackageItemManifest] = Field(default_factory=list)


class AuditPackageCreateRequest(BaseModel):
    """Request payload to generate an exportable audit package."""

    model_config = ConfigDict(extra="forbid")

    validation_run_id: int | None = Field(
        default=None,
        description="Optional validation run to package. Defaults to the latest completed run.",
    )
    package_name: str | None = Field(
        default=None,
        max_length=255,
        description="Optional custom name for the package archive.",
    )
    include_documents: bool = Field(
        default=True,
        description="Whether to package private document files into the archive alongside reports.",
    )
    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional auditor notes to attach to the package manifest.",
    )


class AuditPackageRead(BaseModel):
    """Metadata response for an exportable audit package."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    package_reference: str
    application_id: int
    validation_run_id: int | None
    package_name: str
    status: Literal["pending", "completed", "failed"]
    sha256_root_hash: str
    file_size_bytes: int
    storage_key: str | None
    generated_by: str
    generated_at: datetime
    expires_at: datetime | None = None
    advisory_notice: str = (
        "Advisory audit package only. Pre-scrutiny observations, evidence manifests, "
        "and human review actions do not constitute official statutory AICTE approval or rejection."
    )


class AuditPackageDetailRead(AuditPackageRead):
    """Comprehensive package response including embedded manifest and item checksums."""

    manifest: AuditPackageManifest


class AuditPackageListResponse(BaseModel):
    """Paginated list of generated audit packages."""

    items: list[AuditPackageRead]
    total: int
    skip: int
    limit: int


class AuditPackageVerificationResponse(BaseModel):
    """Cryptographic tamper-evidence verification response."""

    verified: bool = Field(description="True if all item checksums and the root hash match perfectly.")
    package_reference: str | None = Field(default=None, description="Package reference extracted from manifest.")
    computed_root_hash: str = Field(description="Root SHA-256 digest recomputed from archive contents.")
    expected_root_hash: str | None = Field(default=None, description="Root hash claimed in the package manifest.")
    tampered_files: list[str] = Field(default_factory=list, description="Files whose SHA-256 differed from manifest.")
    missing_files: list[str] = Field(default_factory=list, description="Files declared in manifest but missing from ZIP.")
    extra_files: list[str] = Field(default_factory=list, description="Files present in ZIP but undeclared in manifest.")
    message: str = Field(description="Human-readable verification conclusion.")
    advisory_notice: str = (
        "Cryptographic verification certifies file integrity and tamper-evidence of the package bundle only; "
        "it does not certify AICTE regulatory compliance or statutory approval."
    )
