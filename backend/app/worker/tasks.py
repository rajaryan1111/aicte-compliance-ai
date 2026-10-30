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


@celery_app.task(name="backend.app.worker.tasks.periodic_retention_pass_task", bind=True, max_retries=2)
def periodic_retention_pass_task(self: Any, dry_run: bool = False) -> dict[str, Any]:
    """Execute scheduled data retention pass in the Celery background worker."""
    logger.info("Starting periodic retention pass task")
    db = get_worker_session()
    try:
        from backend.app.services.retention_service import RetentionService
        rec = RetentionService.run_retention_pass(
            db,
            execution_type="scheduled",
            dry_run=dry_run,
            actor_id="celery_retention_worker",
        )
        return {
            "run_reference": rec.run_reference,
            "status": rec.status,
            "quarantined_purged": rec.quarantined_purged_count,
            "jobs_cleaned": rec.jobs_cleaned_count,
            "storage_errors": rec.storage_errors_count,
        }
    except Exception as exc:
        logger.exception("Task exception for periodic retention pass: %s", exc)
        raise exc
    finally:
        db.close()
