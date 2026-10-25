"""Transactional outbox dispatcher for reliable background task publication."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging

from sqlalchemy.orm import Session

from backend.app.db.models import OutboxMessage
from backend.app.repositories.outbox_repository import OutboxRepository
from backend.app.repositories.processing_job_repository import ProcessingJobRepository
from backend.app.worker.tasks import process_document_job_task, validate_application_task

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

# Age past which a still-queued job is presumed lost in the broker and is
# re-published. Normal queue latency is seconds; this window only trips when a
# task delivery was actually lost.
STALE_QUEUED_AGE_SECONDS = 600


def dispatch_outbox_message(db: Session, msg: OutboxMessage) -> bool:
    """Publish an outbox message to the message broker.

    On success, marks the message published. If the broker is unreachable,
    marks it failed with the error so the recovery worker can re-dispatch it.
    """
    try:
        payload = json.loads(msg.payload)

        # Application validation task
        if msg.topic == "application.validation.requested" or "run_id" in payload:
            run_id = payload.get("run_id")
            if not run_id:
                OutboxRepository.mark_failed(db, msg.id, "Missing run_id in outbox payload")
                db.commit()
                return False

            validate_application_task.delay(
                run_id=int(run_id),
                checklist_type=payload.get("checklist_type", "default"),
                required_documents=payload.get("required_documents"),
            )
            OutboxRepository.mark_published(db, msg.id)
            db.commit()
            return True

        # Document intake processing task
        job_id = payload.get("job_id")
        if not job_id:
            OutboxRepository.mark_failed(db, msg.id, "Missing job_id in outbox payload")
            db.commit()
            return False

        # Publish to Celery queue (or run eager if task_always_eager=True)
        process_document_job_task.delay(job_id)

        OutboxRepository.mark_published(db, msg.id)
        db.commit()
        return True
    except Exception as exc:
        logger.warning(
            "Outbox dispatch failed for message %s: %s. Preserving message in outbox.",
            msg.id,
            exc,
        )
        OutboxRepository.mark_failed(db, msg.id, str(exc))
        db.commit()
        return False


def dispatch_pending_outbox(db: Session, limit: int = 50) -> int:
    """Find and dispatch undelivered outbox messages (pending, or failed under the retry cap)."""
    pending = OutboxRepository.get_pending_messages(db, limit=limit)
    dispatched_count = 0
    for msg in pending:
        if dispatch_outbox_message(db, msg):
            dispatched_count += 1
    return dispatched_count


def requeue_due_retry_jobs(db: Session, now: datetime | None = None) -> int:
    """Re-publish Celery tasks for retry_wait jobs whose backoff window has elapsed.

    Nothing else re-enqueues these jobs: ``ProcessingJobService.run_job`` parks
    transient failures in ``retry_wait`` with a ``scheduled_for`` backoff and
    returns, so without this sweep a job would wait forever. Safe to run
    concurrently and repeatedly — the worker-side claim is an atomic no-op for
    any job no longer in ``retry_wait``.
    """
    due_jobs = ProcessingJobRepository.get_retryable_jobs(db, now=now)
    requeued = 0
    for job in due_jobs:
        try:
            process_document_job_task.delay(job.id)
            requeued += 1
        except Exception as exc:
            logger.warning(
                "Retry requeue failed for job %s: %s. Left in retry_wait for the next sweep.",
                job.id,
                exc,
            )
    return requeued


def requeue_stale_queued_jobs(db: Session, now: datetime | None = None) -> int:
    """Re-publish Celery tasks for queued jobs whose broker delivery was lost.

    Each requeue bumps ``updated_at`` so the next stale window restarts: a
    stranded job is re-published at most once per ``STALE_QUEUED_AGE_SECONDS``
    even if the broker stays unreachable.
    """
    stale_jobs = ProcessingJobRepository.get_stale_queued_jobs(
        db, older_than_seconds=STALE_QUEUED_AGE_SECONDS, now=now
    )
    requeued = 0
    for job in stale_jobs:
        try:
            process_document_job_task.delay(job.id)
            job.updated_at = now or _utc_now()
            requeued += 1
        except Exception as exc:
            logger.warning(
                "Stale-queued requeue failed for job %s: %s. Left queued for the next sweep.",
                job.id,
                exc,
            )
    return requeued


def run_recovery_sweep(db: Session, now: datetime | None = None) -> dict[str, int]:
    """One scheduled pass that recovers every stranded-work state:

    1. outbox messages never published (pending, or failed under the retry cap),
    2. ``retry_wait`` jobs whose backoff has elapsed,
    3. ``queued`` jobs whose broker delivery was lost.

    Invoked by the Celery beat task ``recovery_sweep_task``. All three paths are
    idempotent (atomic job claims, guarded publish marks), so overlapping or
    repeated sweeps are safe.
    """
    result = {
        "outbox_dispatched": dispatch_pending_outbox(db),
        "retry_jobs_requeued": requeue_due_retry_jobs(db, now=now),
        "stale_jobs_requeued": requeue_stale_queued_jobs(db, now=now),
    }
    db.commit()
    logger.info("Recovery sweep completed: %s", result)
    return result
