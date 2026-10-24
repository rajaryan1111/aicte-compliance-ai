"""Transactional outbox dispatcher for reliable background task publication."""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from backend.app.db.models import OutboxMessage
from backend.app.repositories.outbox_repository import OutboxRepository
from backend.app.worker.tasks import process_document_job_task, validate_application_task

logger = logging.getLogger(__name__)


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
    """Find and dispatch pending or un-published outbox messages (for recovery/retry)."""
    pending = OutboxRepository.get_pending_messages(db, limit=limit)
    dispatched_count = 0
    for msg in pending:
        if dispatch_outbox_message(db, msg):
            dispatched_count += 1
    return dispatched_count
