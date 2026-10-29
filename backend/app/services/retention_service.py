"""Data retention and deletion policy enforcement service for AICTE Compliance AI.

Enforces statutory document retention horizons, privacy safeguards, and automated
purging of stale quarantined files and temporary processing jobs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.core.storage import StorageBackend, get_storage_backend
from backend.app.db.models import (
    Application,
    AuditEvent,
    Document,
    DocumentVersion,
    ProcessingJob,
    ValidationRun,
)
from backend.app.repositories.review_audit_repository import ReviewAuditRepository

logger = logging.getLogger(__name__)

DEFAULT_QUARANTINE_RETENTION_DAYS = 30
DEFAULT_AUDIT_LOG_MINIMUM_RETENTION_YEARS = 7


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RetentionService:
    """Coordinates lifecycle retention and deletion policies across storage and database."""

    @classmethod
    def purge_stale_quarantined_files(
        cls,
        db: Session,
        storage: StorageBackend | None = None,
        max_age_days: int = DEFAULT_QUARANTINE_RETENTION_DAYS,
        actor_id: str = "retention_worker",
    ) -> int:
        """Purge quarantined or rejected document versions older than the retention threshold."""
        storage = storage or get_storage_backend()
        cutoff = _utc_now() - timedelta(days=max_age_days)

        stmt = select(DocumentVersion).where(
            DocumentVersion.scan_status == "rejected",
            DocumentVersion.uploaded_at < cutoff,
        )
        stale_versions = list(db.scalars(stmt).all())
        purged_count = 0

        for ver in stale_versions:
            # Delete private storage file
            try:
                storage.delete(ver.storage_key)
            except Exception as exc:
                logger.warning("Could not delete quarantined storage key %s: %s", ver.storage_key, exc)

            # Record audit event before deleting version
            ReviewAuditRepository.create_audit_event(
                db,
                action="QUARANTINED_FILE_PURGED",
                target_type="DocumentVersion",
                target_id=str(ver.id),
                actor_id=actor_id,
                institution_id=ver.document.application.institution_id if (ver.document and ver.document.application) else None,
                details=json.dumps({"storage_key": ver.storage_key, "age_days": max_age_days}),
            )
            db.delete(ver)
            purged_count += 1

        db.commit()
        return purged_count

    @classmethod
    def cleanup_old_processing_jobs(
        cls,
        db: Session,
        completed_retention_days: int = 14,
    ) -> int:
        """Clean up completed or failed processing jobs older than the retention horizon."""
        cutoff = _utc_now() - timedelta(days=completed_retention_days)
        stmt = delete(ProcessingJob).where(
            ProcessingJob.state.in_(["completed", "failed"]),
            ProcessingJob.updated_at < cutoff,
        )
        result = db.execute(stmt)
        db.commit()
        return int(result.rowcount or 0)

    @classmethod
    def run_scheduled_retention_pass(
        cls,
        db: Session,
        storage: StorageBackend | None = None,
        quarantine_retention_days: int = DEFAULT_QUARANTINE_RETENTION_DAYS,
        job_retention_days: int = 14,
        actor_id: str = "retention_scheduler",
    ) -> dict[str, Any]:
        """Execute scheduled retention pass purging stale quarantined files and completed jobs."""
        purged = cls.purge_stale_quarantined_files(
            db, storage=storage, max_age_days=quarantine_retention_days, actor_id=actor_id
        )
        cleaned = cls.cleanup_old_processing_jobs(
            db, completed_retention_days=job_retention_days
        )
        return {
            "quarantined_purged": purged,
            "jobs_cleaned": cleaned,
            "executed_at": _utc_now().isoformat(),
        }
