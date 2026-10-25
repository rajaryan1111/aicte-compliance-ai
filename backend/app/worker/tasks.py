"""Celery task entry points for asynchronous document processing and validation."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.session import SessionLocal
from backend.app.services.processing_job_service import ProcessingJobService
from backend.app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

_session_factory: sessionmaker[Session] | None = None


def set_worker_session_factory(factory: sessionmaker[Session] | None) -> None:
    """Configure custom session factory for worker tasks (e.g. isolated test databases)."""
    global _session_factory
    _session_factory = factory


def get_worker_session() -> Session:
    """Return a database session using the configured factory or default SessionLocal."""
    if _session_factory is not None:
        return _session_factory()
    return SessionLocal()


@celery_app.task(name="backend.app.worker.tasks.process_document_job_task", bind=True, max_retries=3)
def process_document_job_task(self: Any, job_id: str) -> dict[str, Any]:
    """Execute background malware scan, OCR extraction, and advisory validation for a document version."""
    logger.info("Starting processing task for job %s", job_id)
    db = get_worker_session()
    try:
        job = ProcessingJobService.run_job(db, job_id=job_id)
        state = job.state if job else "not_found"
        logger.info("Completed processing task for job %s with state %s", job_id, state)
        return {"job_id": job_id, "state": state}
    except Exception as exc:
        logger.exception("Task exception for job %s: %s", job_id, exc)
        raise exc
    finally:
        db.close()


@celery_app.task(name="backend.app.worker.tasks.recovery_sweep_task")
def recovery_sweep_task() -> dict[str, int]:
    """Beat-scheduled recovery sweep: re-dispatch stranded outbox messages and due jobs.

    This task is the *only* scheduler for
    :func:`backend.app.core.dispatcher.run_recovery_sweep`; without it,
    ``retry_wait`` jobs and undelivered outbox messages would wait forever.
    Run exactly one worker with ``--beat`` (or one standalone ``celery beat``)
    so the sweep is scheduled exactly once.

    The dispatcher import is deferred: ``backend.app.core.dispatcher`` imports
    this module at import time, so a module-level import here would cycle.
    """
    from backend.app.core.dispatcher import run_recovery_sweep

    db = get_worker_session()
    try:
        return run_recovery_sweep(db)
    finally:
        db.close()


@celery_app.task(name="backend.app.worker.tasks.validate_application_task", bind=True, max_retries=3)
def validate_application_task(
    self: Any,
    run_id: int,
    checklist_type: str = "default",
    required_documents: list[str] | None = None,
) -> dict[str, Any]:
    """Execute application-level validation orchestration in the background worker."""
    logger.info("Starting validation task for run_id %s", run_id)
    db = get_worker_session()
    try:
        from backend.app.repositories.validation_repository import ValidationRepository
        from backend.app.services.validation_orchestration_service import ValidationOrchestrationService

        run = ValidationRepository.get_run(db, run_id)
        if run is None:
            logger.warning("ValidationRun %s not found; skipping task.", run_id)
            return {"run_id": run_id, "status": "not_found"}

        if run.status in ("succeeded", "failed"):
            logger.info("ValidationRun %s already in terminal state %s; skipping duplicate.", run_id, run.status)
            return {"run_id": run_id, "status": run.status}

        run.status = "running"
        db.commit()

        service = ValidationOrchestrationService()
        run = service.execute_validation_for_run(
            db,
            run=run,
            checklist_type=checklist_type,
            required_documents=required_documents,
            actor_id="system_worker",
        )
        logger.info(
            "Completed validation task for run_id %s with status %s and outcome %s",
            run_id,
            run.status,
            run.outcome,
        )
        return {"run_id": run_id, "status": run.status, "outcome": run.outcome}
    except Exception as exc:
        logger.exception("Task exception for validation run %s: %s", run_id, exc)
        raise exc
    finally:
        db.close()
