"""Repository for durable ProcessingJob tracking and state transitions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import ProcessingJob


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProcessingJobRepository:
    """Repository operations for background processing jobs."""

    @staticmethod
    def create_job(
        db: Session,
        document_version_id: int,
        job_type: str = "document_intake_pipeline",
        max_attempts: int = 3,
        pipeline_version: str = "v1.0",
    ) -> ProcessingJob:
        """Create a new durable processing job in queued state."""
        job_id = str(uuid.uuid4())
        job = ProcessingJob(
            id=job_id,
            document_version_id=document_version_id,
            job_type=job_type,
            state="queued",
            attempt_count=0,
            max_attempts=max_attempts,
            created_at=_utc_now(),
            updated_at=_utc_now(),
            pipeline_version=pipeline_version,
        )
        db.add(job)
        db.flush()
        return job

    @staticmethod
    def get_by_id(db: Session, job_id: str) -> ProcessingJob | None:
        """Retrieve a processing job by unique job ID."""
        return db.get(ProcessingJob, job_id)

    @staticmethod
    def get_latest_for_version(
        db: Session,
        document_version_id: int,
    ) -> ProcessingJob | None:
        """Retrieve the latest processing job for a given document version."""
        stmt = (
            select(ProcessingJob)
            .where(ProcessingJob.document_version_id == document_version_id)
            .order_by(ProcessingJob.created_at.desc())
            .limit(1)
        )
        return db.scalars(stmt).first()

    @staticmethod
    def claim_job(
        db: Session,
        job_id: str,
    ) -> ProcessingJob | None:
        """Atomically claim a job for processing if in queued or retry_wait state.

        Returns the claimed job with incremented attempt_count and state 'scanning',
        or None if the job was already claimed, completed, or not found.
        """
        job = db.get(ProcessingJob, job_id)
        if job is None:
            return None

        # Idempotency / concurrent claim guard
        if job.state not in ("queued", "retry_wait"):
            return None

        now = _utc_now()
        job.state = "scanning"
        job.attempt_count += 1
        job.started_at = now
        job.updated_at = now
        db.flush()
        return job

    @staticmethod
    def update_state(
        db: Session,
        job: ProcessingJob,
        state: str,
        last_error_code: str | None = None,
        scheduled_for: datetime | None = None,
    ) -> ProcessingJob:
        """Update job state, timestamps and optional error/schedule metadata."""
        now = _utc_now()
        job.state = state
        job.updated_at = now
        if last_error_code is not None:
            job.last_error_code = last_error_code
        if scheduled_for is not None:
            job.scheduled_for = scheduled_for
        if state in ("completed", "partial", "failed", "blocked"):
            job.completed_at = now
        db.flush()
        return job

    @staticmethod
    def get_retryable_jobs(
        db: Session,
        now: datetime | None = None,
    ) -> list[ProcessingJob]:
        """Fetch jobs in retry_wait state whose scheduled_for time has arrived."""
        current_time = now or _utc_now()
        stmt = (
            select(ProcessingJob)
            .where(
                ProcessingJob.state == "retry_wait",
                ProcessingJob.scheduled_for <= current_time,
            )
            .order_by(ProcessingJob.scheduled_for.asc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_stale_queued_jobs(
        db: Session,
        older_than_seconds: int = 600,
        now: datetime | None = None,
    ) -> list[ProcessingJob]:
        """Fetch queued jobs whose broker delivery appears to have been lost.

        A job stays ``queued`` only until a worker claims it (``claim_job`` is
        atomic and flips the state immediately), so a job still ``queued`` long
        after creation means its task message never reached a worker — for
        example a broker restart without persistence. Re-publishing is safe
        because the claim is a no-op for anything already claimed or terminal:
        at-least-once delivery, exactly-once claim.
        """
        current_time = now or _utc_now()
        cutoff = current_time - timedelta(seconds=older_than_seconds)
        stmt = (
            select(ProcessingJob)
            .where(
                ProcessingJob.state == "queued",
                ProcessingJob.updated_at <= cutoff,
            )
            .order_by(ProcessingJob.updated_at.asc())
        )
        return list(db.scalars(stmt).all())
