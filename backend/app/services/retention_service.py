"""Data retention and deletion policy enforcement service for AICTE Compliance AI.

Enforces statutory document retention horizons, privacy safeguards, and automated
purging of stale quarantined files and temporary processing jobs.
Storage deletion occurs prior to DB record deletion, preventing orphaned storage.
Audit logs and audit packages are strictly preserved and never purged.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import os
import uuid
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
    RetentionRunRecord,
    ValidationRun,
)
from backend.app.repositories.review_audit_repository import ReviewAuditRepository

logger = logging.getLogger(__name__)

DEFAULT_QUARANTINE_RETENTION_DAYS = int(os.getenv("RETENTION_QUARANTINE_DAYS", "30"))
DEFAULT_JOB_RETENTION_DAYS = int(os.getenv("RETENTION_JOB_DAYS", "14"))
DEFAULT_SCHEDULE_INTERVAL_SECONDS = int(os.getenv("RETENTION_SCHEDULE_INTERVAL_SECONDS", "86400"))
AUDIT_LOG_MINIMUM_RETENTION_YEARS = 7


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
        dry_run: bool = False,
        actor_id: str = "retention_worker",
        return_summary: bool = False,
    ) -> int | tuple[int, int]:
        """Purge quarantined/rejected document versions older than the retention threshold.

        Returns (purged_count, storage_errors_count).
        Storage deletion occurs first. If storage deletion fails, the DB record is NOT deleted.
        """
        storage = storage or get_storage_backend()
        cutoff = _utc_now() - timedelta(days=max_age_days)

        stmt = select(DocumentVersion).where(
            DocumentVersion.scan_status == "rejected",
            DocumentVersion.uploaded_at < cutoff,
        )
        stale_versions = list(db.scalars(stmt).all())

        if dry_run:
            logger.info("Dry-run: found %d stale quarantined files older than %d days", len(stale_versions), max_age_days)
            return (len(stale_versions), 0) if return_summary else len(stale_versions)

        purged_count = 0
        storage_errors = 0

        for ver in stale_versions:
            storage_key = ver.storage_key
            # Step 1: Physical storage deletion
            storage_deleted = False
            try:
                storage.delete(storage_key)
                storage_deleted = True
            except Exception as exc:
                storage_errors += 1
                logger.error("Could not delete quarantined storage key %s: %s; preserving DB record", storage_key, exc)
                # Failure handling: record failure event, do NOT delete DB record
                ReviewAuditRepository.create_audit_event(
                    db,
                    action="QUARANTINED_PURGE_STORAGE_FAILED",
                    target_type="DocumentVersion",
                    target_id=str(ver.id),
                    actor_id=actor_id,
                    institution_id=ver.document.application.institution_id if (ver.document and ver.document.application) else None,
                    details=json.dumps({"storage_key": storage_key, "error": str(exc)}),
                )
                continue

            if storage_deleted:
                try:
                    # Step 2: Attributable audit event
                    ReviewAuditRepository.create_audit_event(
                        db,
                        action="QUARANTINED_FILE_PURGED",
                        target_type="DocumentVersion",
                        target_id=str(ver.id),
                        actor_id=actor_id,
                        institution_id=ver.document.application.institution_id if (ver.document and ver.document.application) else None,
                        details=json.dumps({"storage_key": storage_key, "age_days": max_age_days}),
                    )
                    # Step 3: DB record deletion
                    db.delete(ver)
                    purged_count += 1
                except Exception as db_exc:
                    logger.error("DB error deleting DocumentVersion %d after storage delete: %s", ver.id, db_exc)
                    ReviewAuditRepository.create_audit_event(
                        db,
                        action="QUARANTINED_PURGE_DB_FAILED_TOMBSTONE",
                        target_type="DocumentVersion",
                        target_id=str(ver.id),
                        actor_id=actor_id,
                        institution_id=ver.document.application.institution_id if (ver.document and ver.document.application) else None,
                        details=json.dumps({"storage_key": storage_key, "error": str(db_exc), "status": "storage_deleted_pending_db"}),
                    )

        db.commit()
        return (purged_count, storage_errors) if return_summary else purged_count

    @classmethod
    def cleanup_old_processing_jobs(
        cls,
        db: Session,
        completed_retention_days: int = DEFAULT_JOB_RETENTION_DAYS,
        dry_run: bool = False,
    ) -> int:
        """Clean up completed or failed processing jobs older than the retention horizon.

        In-flight jobs ('queued', 'running', 'processing') are strictly preserved.
        """
        cutoff = _utc_now() - timedelta(days=completed_retention_days)
        stmt = select(ProcessingJob.id).where(
            ProcessingJob.state.in_(["completed", "failed"]),
            ProcessingJob.updated_at < cutoff,
        )
        stale_ids = list(db.scalars(stmt).all())

        if dry_run:
            logger.info("Dry-run: found %d terminal processing jobs older than %d days", len(stale_ids), completed_retention_days)
            return len(stale_ids)

        if not stale_ids:
            return 0

        del_stmt = (
            delete(ProcessingJob)
            .where(ProcessingJob.id.in_(stale_ids))
            .execution_options(synchronize_session=False)
        )
        db.execute(del_stmt)
        db.commit()
        return len(stale_ids)

    @classmethod
    def run_retention_pass(
        cls,
        db: Session,
        storage: StorageBackend | None = None,
        execution_type: str = "scheduled",
        dry_run: bool = False,
        actor_id: str = "retention_worker",
        quarantine_retention_days: int = DEFAULT_QUARANTINE_RETENTION_DAYS,
        job_retention_days: int = DEFAULT_JOB_RETENTION_DAYS,
    ) -> RetentionRunRecord:
        """Execute scheduled or manual retention pass with concurrency protection and durable audit record."""
        # Check concurrency: ensure no active running pass started within last 15 minutes
        recent_running_stmt = select(RetentionRunRecord).where(
            RetentionRunRecord.status == "running",
            RetentionRunRecord.started_at > _utc_now() - timedelta(minutes=15),
        )
        active_pass = db.scalars(recent_running_stmt).first()
        if active_pass is not None:
            logger.warning("Another retention pass is currently running: %s; skipping concurrent pass", active_pass.run_reference)
            return active_pass

        # Check Postgres advisory lock if running on PostgreSQL engine
        bind = db.get_bind()
        is_postgres = bind is not None and "postgresql" in getattr(bind.dialect, "name", "").lower()
        if is_postgres:
            try:
                from sqlalchemy import text
                lock_res = db.execute(text("SELECT pg_try_advisory_lock(83928172)")).scalar()
                if lock_res is False:
                    logger.warning("Postgres advisory lock 83928172 held by another worker; skipping concurrent pass.")
                    if active_pass:
                        return active_pass
            except Exception as lock_err:
                logger.warning("Advisory lock check skipped: %s", lock_err)

        now = _utc_now()
        run_ref = f"RET-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        run_rec = RetentionRunRecord(
            run_reference=run_ref,
            execution_type=execution_type,
            dry_run=dry_run,
            status="running",
            triggered_by=actor_id,
            started_at=now,
        )
        db.add(run_rec)
        db.commit()
        db.refresh(run_rec)

        try:
            purged, storage_errs = cls.purge_stale_quarantined_files(
                db,
                storage=storage,
                max_age_days=quarantine_retention_days,
                dry_run=dry_run,
                actor_id=actor_id,
                return_summary=True,
            )
            cleaned = cls.cleanup_old_processing_jobs(
                db,
                completed_retention_days=job_retention_days,
                dry_run=dry_run,
            )

            completed_now = _utc_now()
            run_rec.status = "completed"
            run_rec.quarantined_purged_count = purged
            run_rec.jobs_cleaned_count = cleaned
            run_rec.storage_errors_count = storage_errs
            run_rec.completed_at = completed_now
            run_rec.details = json.dumps({
                "dry_run": dry_run,
                "quarantine_retention_days": quarantine_retention_days,
                "job_retention_days": job_retention_days,
                "purged_count": purged,
                "cleaned_jobs": cleaned,
                "storage_errors": storage_errs,
            })

            ReviewAuditRepository.create_audit_event(
                db,
                action="RETENTION_PASS_COMPLETED",
                target_type="RetentionRunRecord",
                target_id=run_ref,
                actor_id=actor_id,
                details=run_rec.details,
            )
            db.commit()
            db.refresh(run_rec)
            return run_rec

        except Exception as exc:
            db.rollback()
            logger.exception("Retention pass %s encountered an error: %s", run_ref, exc)
            run_rec_cur = db.get(RetentionRunRecord, run_rec.id)
            if run_rec_cur:
                run_rec_cur.status = "failed"
                run_rec_cur.error_message = str(exc)
                run_rec_cur.completed_at = _utc_now()
                db.commit()
                db.refresh(run_rec_cur)
                return run_rec_cur
            raise exc
        finally:
            bind = db.get_bind()
            if bind is not None and "postgresql" in getattr(bind.dialect, "name", "").lower():
                try:
                    from sqlalchemy import text
                    db.execute(text("SELECT pg_advisory_unlock(83928172)"))
                except Exception:
                    pass

    # Legacy alias for backward compatibility
    @classmethod
    def run_scheduled_retention_pass(
        cls,
        db: Session,
        storage: StorageBackend | None = None,
        quarantine_retention_days: int = DEFAULT_QUARANTINE_RETENTION_DAYS,
        job_retention_days: int = DEFAULT_JOB_RETENTION_DAYS,
        actor_id: str = "retention_scheduler",
    ) -> dict[str, Any]:
        """Legacy entry point returning dictionary summary."""
        rec = cls.run_retention_pass(
            db,
            storage=storage,
            execution_type="scheduled",
            dry_run=False,
            actor_id=actor_id,
            quarantine_retention_days=quarantine_retention_days,
            job_retention_days=job_retention_days,
        )
        return {
            "run_reference": rec.run_reference,
            "quarantined_purged": rec.quarantined_purged_count,
            "jobs_cleaned": rec.jobs_cleaned_count,
            "storage_errors": rec.storage_errors_count,
            "status": rec.status,
            "executed_at": rec.started_at.isoformat(),
        }

    @classmethod
    def list_retention_runs(cls, db: Session, limit: int = 50) -> list[RetentionRunRecord]:
        """List historical retention execution runs."""
        stmt = (
            select(RetentionRunRecord)
            .order_by(RetentionRunRecord.started_at.desc())
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    @classmethod
    def get_latest_run(cls, db: Session) -> RetentionRunRecord | None:
        """Return the most recently executed retention run."""
        stmt = select(RetentionRunRecord).order_by(RetentionRunRecord.started_at.desc()).limit(1)
        return db.scalars(stmt).first()
