"""SQLAlchemy 2.x ORM models for AICTE Compliance AI persistence foundation.

Implements the 9 canonical entities:
1. Institution — stable institutional identifier and basic metadata.
2. Application — institution relationship, application type, academic year, lifecycle status and timestamps.
3. Document — logical document slot associated with an application.
4. DocumentVersion — immutable version metadata, storage key, SHA-256 hash, media type, byte size, upload timestamp and processing status.
5. ExtractedField — field name, raw text, normalized value, optional confidence and evidence/page metadata.
6. ValidationRun — application reference, execution timestamps, status, evaluation date and version/provenance information.
7. Finding — validation-run reference, finding code, status, severity, summary and evidence references.
8. ReviewAction — application reference, action, reviewer identifier, comment and timestamp.
9. AuditEvent — attributable event metadata, action, target, timestamp and request identifier.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Institution(Base):
    """Stable institutional identifier and tenant boundary."""

    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    institution_id: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    # Relationships
    applications: Mapped[list[Application]] = relationship(
        back_populates="institution", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="institution"
    )
    memberships: Mapped[list[InstitutionMembership]] = relationship(
        back_populates="institution", cascade="all, delete-orphan"
    )
    record_snapshots: Mapped[list[InstitutionalRecordSnapshot]] = relationship(
        back_populates="institution", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Institution(id={self.id}, institution_id={self.institution_id!r})>"


class Application(Base):
    """Reviewable submission linked to an institution."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_type: Mapped[str] = mapped_column(String(50), nullable=False)
    academic_year: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="draft", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    # Relationships
    institution: Mapped[Institution] = relationship(back_populates="applications")
    documents: Mapped[list[Document]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    validation_runs: Mapped[list[ValidationRun]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    review_actions: Mapped[list[ReviewAction]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    audit_packages: Mapped[list[AuditPackage]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    verification_attempts: Mapped[list[VerificationAttempt]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    infrastructure_evidence: Mapped[list[InfrastructureEvidence]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    consistency_checks: Mapped[list[ConsistencyCheck]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Application(id={self.id}, institution_id={self.institution_id}, "
            f"type={self.application_type!r}, status={self.status!r})>"
        )


class Document(Base):
    """Logical document slot associated with an application."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "document_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_documents_current_version_id",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "application_id", "document_type", name="uq_application_document_type"
        ),
    )

    # Relationships
    application: Mapped[Application] = relationship(back_populates="documents")
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        foreign_keys="[DocumentVersion.document_id]",
        cascade="all, delete-orphan",
    )
    current_version: Mapped[DocumentVersion | None] = relationship(
        foreign_keys=[current_version_id], post_update=True
    )

    def __repr__(self) -> str:
        return (
            f"<Document(id={self.id}, application_id={self.application_id}, "
            f"type={self.document_type!r}, current_version_id={self.current_version_id})>"
        )


class DocumentVersion(Base):
    """Immutable uploaded document version and metadata."""

    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    storage_key: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scan_status: Mapped[str | None] = mapped_column(
        String(50), default="pending_scan", nullable=True
    )
    processing_status: Mapped[str] = mapped_column(
        String(50), default="queued", nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_number", name="uq_document_version_number"
        ),
    )

    # Relationships
    document: Mapped[Document] = relationship(
        back_populates="versions", foreign_keys=[document_id]
    )
    extracted_fields: Mapped[list[ExtractedField]] = relationship(
        back_populates="document_version", cascade="all, delete-orphan"
    )
    processing_jobs: Mapped[list[ProcessingJob]] = relationship(
        back_populates="document_version", cascade="all, delete-orphan"
    )
    verification_attempts: Mapped[list[VerificationAttempt]] = relationship(
        back_populates="document_version", cascade="all, delete-orphan"
    )
    infrastructure_evidence: Mapped[list[InfrastructureEvidence]] = relationship(
        back_populates="document_version", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentVersion(id={self.id}, document_id={self.document_id}, "
            f"version={self.version_number}, storage_key={self.storage_key!r})>"
        )


class ExtractedField(Base):
    """Field observation extracted from a document version."""

    __tablename__ = "extracted_fields"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bounding_box: Mapped[str | None] = mapped_column(Text, nullable=True)
    engine_name: Mapped[str] = mapped_column(String(100), nullable=False)
    engine_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extraction_status: Mapped[str] = mapped_column(
        String(50), default="extracted", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    # Relationships
    document_version: Mapped[DocumentVersion] = relationship(
        back_populates="extracted_fields"
    )

    def __repr__(self) -> str:
        return (
            f"<ExtractedField(id={self.id}, version_id={self.document_version_id}, "
            f"field_name={self.field_name!r})>"
        )


class ValidationRun(Base):
    """Reproducible evaluation run linked to an application."""

    __tablename__ = "validation_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(50), default="queued", nullable=False, index=True
    )
    evaluation_date: Mapped[date] = mapped_column(Date, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(
        String(100), default="0.1.0-draft", nullable=False
    )
    triggered_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    consumed_version_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_counts: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    application: Mapped[Application] = relationship(back_populates="validation_runs")
    findings: Mapped[list[Finding]] = relationship(
        back_populates="validation_run", cascade="all, delete-orphan"
    )
    check_results: Mapped[list[ValidationCheckResult]] = relationship(
        back_populates="validation_run", cascade="all, delete-orphan"
    )
    audit_packages: Mapped[list[AuditPackage]] = relationship(
        back_populates="validation_run"
    )

    def __repr__(self) -> str:
        return (
            f"<ValidationRun(id={self.id}, application_id={self.application_id}, "
            f"status={self.status!r}, outcome={self.outcome!r}, date={self.evaluation_date})>"
        )


class ValidationCheckResult(Base):
    """Deterministic result for an individual validation check within a run."""

    __tablename__ = "validation_check_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    validation_run_id: Mapped[int] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    check_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    check_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    document_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    # Relationships
    validation_run: Mapped[ValidationRun] = relationship(back_populates="check_results")
    document_version: Mapped[DocumentVersion | None] = relationship()

    def __repr__(self) -> str:
        return (
            f"<ValidationCheckResult(id={self.id}, run_id={self.validation_run_id}, "
            f"check_id={self.check_id!r}, status={self.status!r})>"
        )


class Finding(Base):
    """Validation finding linked to a validation run and optional document version."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    validation_run_id: Mapped[int] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="open", nullable=False)
    severity: Mapped[str] = mapped_column(String(50), default="warning", nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    # Relationships
    validation_run: Mapped[ValidationRun] = relationship(back_populates="findings")
    document_version: Mapped[DocumentVersion | None] = relationship()
    review_actions: Mapped[list[ReviewAction]] = relationship(
        back_populates="finding", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Finding(id={self.id}, run_id={self.validation_run_id}, "
            f"code={self.code!r}, status={self.status!r}, severity={self.severity!r})>"
        )


class ReviewAction(Base):
    """Attributable reviewer action and decision recorded on an application."""

    __tablename__ = "review_actions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    finding_id: Mapped[int | None] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), nullable=True, index=True
    )
    validation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewer_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    evidence_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    # Relationships
    application: Mapped[Application] = relationship(back_populates="review_actions")
    finding: Mapped[Finding | None] = relationship(back_populates="review_actions")
    validation_run: Mapped[ValidationRun | None] = relationship()

    def __repr__(self) -> str:
        return (
            f"<ReviewAction(id={self.id}, application_id={self.application_id}, "
            f"finding_id={self.finding_id}, reviewer={self.reviewer_id!r}, action={self.action!r})>"
        )


class AuditPackage(Base):
    """Immutable, tamper-evident audit package bundle exported for scrutiny hand-off."""

    __tablename__ = "audit_packages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    package_reference: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    validation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    package_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="completed", nullable=False, index=True
    )
    sha256_root_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    application: Mapped[Application] = relationship(back_populates="audit_packages")
    validation_run: Mapped[ValidationRun | None] = relationship(back_populates="audit_packages")

    def __repr__(self) -> str:
        return (
            f"<AuditPackage(id={self.id}, ref={self.package_reference!r}, "
            f"app_id={self.application_id}, sha256={self.sha256_root_hash[:8]}...)>"
        )


class AuditEvent(Base):
    """Attributable system and actor history log."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    # Relationships
    institution: Mapped[Institution | None] = relationship(back_populates="audit_events")

    def __repr__(self) -> str:
        return (
            f"<AuditEvent(id={self.id}, action={self.action!r}, "
            f"target={self.target_type}:{self.target_id})>"
        )


class ConsistencyCheck(Base):
    """Institution-scoped consistency review attached to an application."""

    __tablename__ = "consistency_checks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    check_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_field: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(40), default="pending", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    application: Mapped[Application] = relationship(back_populates="consistency_checks")
    findings: Mapped[list[ConsistencyFinding]] = relationship(
        back_populates="consistency_check", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ConsistencyCheck(id={self.id}, application_id={self.application_id}, status={self.status!r})>"


class ConsistencyFinding(Base):
    """Persisted discrepancy observation for a consistency check."""

    __tablename__ = "consistency_findings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    consistency_check_id: Mapped[int] = mapped_column(
        ForeignKey("consistency_checks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value_1: Mapped[str] = mapped_column(Text, nullable=False)
    value_2: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    consistency_check: Mapped[ConsistencyCheck] = relationship(back_populates="findings")

    def __repr__(self) -> str:
        return f"<ConsistencyFinding(id={self.id}, check_id={self.consistency_check_id}, field={self.field_name!r})>"


class User(Base):
    """User account identity and credentials."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    # Relationships
    memberships: Mapped[list[InstitutionMembership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username!r}, is_active={self.is_active})>"


class InstitutionMembership(Base):
    """User assignment to an institution with a specific RBAC role."""

    __tablename__ = "institution_memberships"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "institution_id", name="uq_user_institution_membership"),
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="memberships")
    institution: Mapped[Institution] = relationship(back_populates="memberships")

    def __repr__(self) -> str:
        return (
            f"<InstitutionMembership(id={self.id}, user_id={self.user_id}, "
            f"institution_id={self.institution_id}, role={self.role!r}, is_active={self.is_active})>"
        )


class ProcessingJob(Base):
    """Durable processing-job tracking for asynchronous document pipeline."""

    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_type: Mapped[str] = mapped_column(
        String(64), default="document_intake_pipeline", nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(32), default="queued", nullable=False, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pipeline_version: Mapped[str | None] = mapped_column(
        String(32), default="v1.0", nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "document_version_id", "job_type", name="uq_processing_job_version_type"
        ),
    )

    # Relationships
    document_version: Mapped[DocumentVersion] = relationship(
        back_populates="processing_jobs"
    )

    def __repr__(self) -> str:
        return (
            f"<ProcessingJob(id={self.id!r}, version_id={self.document_version_id}, "
            f"state={self.state!r}, attempts={self.attempt_count}/{self.max_attempts})>"
        )


class OutboxMessage(Base):
    """Transactional outbox for reliable background job dispatch."""

    __tablename__ = "outbox_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<OutboxMessage(id={self.id!r}, topic={self.topic!r}, "
            f"status={self.status!r}, retries={self.retry_count})>"
        )



class VerificationAttempt(Base):
    """Traceable issuing-authority verification attempt and comparison record."""

    __tablename__ = "verification_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_reference: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    adapter_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_title: Mapped[str] = mapped_column(String(255), nullable=False)
    is_official_source: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="not_attempted", nullable=False, index=True
    )
    submitted_attributes: Mapped[str | None] = mapped_column(Text, nullable=True)
    returned_attributes: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    # Relationships
    application: Mapped[Application] = relationship(back_populates="verification_attempts")
    document_version: Mapped[DocumentVersion] = relationship(
        back_populates="verification_attempts"
    )

    def __repr__(self) -> str:
        return (
            f"<VerificationAttempt(id={self.id}, adapter={self.adapter_name!r}, "
            f"status={self.status!r}, ref={self.attempt_reference!r})>"
        )


class InstitutionalRecordSnapshot(Base):
    """Versioned snapshot of authorized institutional records (past EoA, intake, NBA, TER)."""

    __tablename__ = "institutional_record_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    record_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_category: Mapped[str] = mapped_column(
        String(50), default="unavailable", nullable=False
    )
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    record_data: Mapped[str] = mapped_column(Text, nullable=False)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    # Relationships
    institution: Mapped[Institution] = relationship(back_populates="record_snapshots")

    def __repr__(self) -> str:
        return (
            f"<InstitutionalRecordSnapshot(id={self.id}, inst={self.institution_id}, "
            f"type={self.record_type!r}, source={self.source_category!r})>"
        )


class InfrastructureEvidence(Base):
    """Infrastructure documentary & visual evidence tracking and inspection flags."""

    __tablename__ = "infrastructure_evidence"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    declared_area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    inspection_recommended: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    inspection_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    # Relationships
    application: Mapped[Application] = relationship(back_populates="infrastructure_evidence")
    document_version: Mapped[DocumentVersion] = relationship(
        back_populates="infrastructure_evidence"
    )

    def __repr__(self) -> str:
        return (
            f"<InfrastructureEvidence(id={self.id}, type={self.evidence_type!r}, "
            f"inspection={self.inspection_recommended})>"
        )


class RuleApprovalRecord(Base):
    """Durable statutory approval record for a regulatory rule version."""

    __tablename__ = "rule_approvals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(100), nullable=False)
    reviewer_username: Mapped[str] = mapped_column(String(100), nullable=False)
    reviewer_role: Mapped[str] = mapped_column(String(50), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_clause: Mapped[str] = mapped_column(String(120), nullable=False)
    source_page: Mapped[str] = mapped_column(String(40), nullable=False)
    source_document_version: Mapped[str] = mapped_column(String(120), nullable=False)
    source_document_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_retrieved_at: Mapped[date] = mapped_column(Date, nullable=False)
    source_verified_by: Mapped[str] = mapped_column(String(120), nullable=False)
    source_verified_at: Mapped[date] = mapped_column(Date, nullable=False)
    source_verification_status: Mapped[str] = mapped_column(String(50), default="verified", nullable=False)
    statutory_interpretation_approved: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    rule_definition_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("rule_id", "rule_version", "decision", name="uq_rule_approval_version_decision"),
    )

    def __repr__(self) -> str:
        return (
            f"<RuleApprovalRecord(id={self.id}, rule={self.rule_id!r}, v={self.rule_version}, "
            f"decision={self.decision!r}, reviewer={self.reviewer_username!r})>"
        )


class RetentionRunRecord(Base):
    """Auditable execution record for automated and manual data retention runs."""

    __tablename__ = "retention_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_reference: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    execution_type: Mapped[str] = mapped_column(String(50), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="running", nullable=False, index=True)
    quarantined_purged_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_cleaned_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<RetentionRunRecord(id={self.id}, ref={self.run_reference!r}, "
            f"type={self.execution_type!r}, status={self.status!r})>"
        )
