"""Repository for storing and querying exported audit packages."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models import AuditEvent, AuditPackage


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditPackageRepository:
    """SQLAlchemy persistence and querying for exported audit packages."""

    @classmethod
    def create_package(
        cls,
        db: Session,
        *,
        package_reference: str,
        application_id: int,
        validation_run_id: int | None,
        package_name: str,
        status: str,
        sha256_root_hash: str,
        file_size_bytes: int,
        storage_key: str | None,
        manifest_json: str,
        generated_by: str,
        expires_at: datetime | None = None,
    ) -> AuditPackage:
        """Create and persist a new immutable audit package record."""
        package = AuditPackage(
            package_reference=package_reference,
            application_id=application_id,
            validation_run_id=validation_run_id,
            package_name=package_name,
            status=status,
            sha256_root_hash=sha256_root_hash,
            file_size_bytes=file_size_bytes,
            storage_key=storage_key,
            manifest_json=manifest_json,
            generated_by=generated_by,
            generated_at=_utc_now(),
            expires_at=expires_at,
        )
        db.add(package)
        db.commit()
        db.refresh(package)
        return package

    @classmethod
    def get_by_id(
        cls,
        db: Session,
        *,
        application_id: int,
        package_id: int,
    ) -> AuditPackage | None:
        """Fetch audit package by primary key scoped to application."""
        stmt = select(AuditPackage).where(
            AuditPackage.id == package_id,
            AuditPackage.application_id == application_id,
        )
        return db.scalars(stmt).first()

    @classmethod
    def get_by_reference(
        cls,
        db: Session,
        package_reference: str,
    ) -> AuditPackage | None:
        """Fetch audit package by unique package reference."""
        stmt = select(AuditPackage).where(AuditPackage.package_reference == package_reference)
        return db.scalars(stmt).first()

    @classmethod
    def list_packages(
        cls,
        db: Session,
        application_id: int,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[AuditPackage], int]:
        """Paginated retrieval of audit packages for an application, sorted newest first."""
        count_stmt = (
            select(func.count(AuditPackage.id))
            .where(AuditPackage.application_id == application_id)
        )
        total = db.scalar(count_stmt) or 0

        stmt = (
            select(AuditPackage)
            .where(AuditPackage.application_id == application_id)
            .order_by(AuditPackage.generated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        packages = list(db.scalars(stmt).all())
        return packages, total

    @classmethod
    def record_audit_event(
        cls,
        db: Session,
        *,
        actor_id: str | None,
        institution_id: int | None,
        action: str,
        target_type: str,
        target_id: str,
        request_id: str | None = None,
        details: str | None = None,
    ) -> AuditEvent:
        """Create attributable audit log entry."""
        event = AuditEvent(
            actor_id=actor_id,
            institution_id=institution_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            request_id=request_id,
            details=details,
            created_at=_utc_now(),
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event
