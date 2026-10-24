"""Service coordinating background document processing stages:
Stage A: Claim job (atomicity & idempotency)
Stage B: Malware scanning gate
Stage C: Advisory OCR / native text extraction
Stage D: Persisting evidence, findings and updating job status
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy.orm import Session

from backend.app.core.scanner import MalwareScanner, ScanStatus, get_malware_scanner
from backend.app.core.storage import StorageBackend, get_storage_backend
from backend.app.db.models import DocumentVersion, Finding, ProcessingJob
from backend.app.repositories.processing_job_repository import ProcessingJobRepository
from backend.app.repositories.review_audit_repository import ReviewAuditRepository
from backend.app.services.document_processing_service import DocumentProcessingService

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProcessingJobService:
    """Orchestrates asynchronous processing of document versions through the security and OCR gates."""

    @classmethod
    def run_job(
        cls,
        db: Session,
        job_id: str,
        scanner: MalwareScanner | None = None,
        storage: StorageBackend | None = None,
        processing_service: DocumentProcessingService | None = None,
    ) -> ProcessingJob | None:
        """Execute the multi-stage document processing workflow for a claimed job."""
        scanner = scanner or get_malware_scanner()
        storage = storage or get_storage_backend()
        processing_service = processing_service or DocumentProcessingService()

        # ======================================================================
        # Stage A: Claim the job atomically
        # ======================================================================
        job = ProcessingJobRepository.claim_job(db, job_id)
        if job is None:
            # Check if job was already processed or doesn't exist
            existing = ProcessingJobRepository.get_by_id(db, job_id)
            if existing and existing.state in ("completed", "failed", "blocked"):
                logger.info("Job %s already in terminal state %s; skipping.", job_id, existing.state)
                return existing
            logger.warning("Job %s could not be claimed.", job_id)
            return existing

        version = db.get(DocumentVersion, job.document_version_id)
        if version is None:
            ProcessingJobRepository.update_state(
                db, job, state="failed", last_error_code="VERSION_NOT_FOUND"
            )
            db.commit()
            return job

        # Check maximum attempts
        if job.attempt_count > job.max_attempts:
            ProcessingJobRepository.update_state(
                db, job, state="failed", last_error_code="MAX_RETRIES_EXCEEDED"
            )
            version.processing_status = "failed"
            db.commit()
            return job

        app_rec = version.document.application if version.document else None
        inst_id = app_rec.institution_id if app_rec else None
        inst_code = (
            app_rec.institution.institution_id
            if (app_rec and app_rec.institution)
            else (str(inst_id) if inst_id else None)
        )

        try:
            # Load stored document bytes from private storage
            file_bytes = storage.read(version.storage_key)

            # ==================================================================
            # Stage B: Malware scanning gate
            # ==================================================================
            scan_result = scanner.scan(file_bytes, version.file_name or "document.bin")

            if scan_result.status == ScanStatus.REJECTED:
                # Malicious: fail-closed, quarantine permanently, never enter OCR
                version.scan_status = "rejected"
                version.processing_status = "rejected"
                job = ProcessingJobRepository.update_state(
                    db,
                    job,
                    state="failed",
                    last_error_code="MALWARE_DETECTED",
                )
                if inst_id:
                    ReviewAuditRepository.create_audit_event(
                        db,
                        action="DOCUMENT_SCAN_REJECTED",
                        target_type="DocumentVersion",
                        target_id=str(version.id),
                        actor_id="system_worker",
                        institution_id=inst_id,
                        details=f'{{"reason": "malware_scan_rejected", "details": "{scan_result.details}"}}',
                    )
                db.commit()
                return job

            if scan_result.status in (ScanStatus.SCAN_UNAVAILABLE, ScanStatus.PENDING_SCAN):
                # Inconclusive/scanner offline: fail-safe, keep quarantined
                version.scan_status = "scan_unavailable"
                if job.attempt_count < job.max_attempts:
                    backoff_sec = 2 ** job.attempt_count * 5
                    scheduled_for = _utc_now() + timedelta(seconds=backoff_sec)
                    job = ProcessingJobRepository.update_state(
                        db,
                        job,
                        state="retry_wait",
                        last_error_code="SCANNER_UNAVAILABLE",
                        scheduled_for=scheduled_for,
                    )
                else:
                    job = ProcessingJobRepository.update_state(
                        db,
                        job,
                        state="blocked",
                        last_error_code="SCANNER_UNAVAILABLE",
                    )
                    version.processing_status = "quarantined"
                db.commit()
                return job

            # Clean scan confirmed
            version.scan_status = "clean"
            job = ProcessingJobRepository.update_state(db, job, state="extracting")
            db.flush()

            # ==================================================================
            # Stage C: Advisory OCR / Native Text Extraction
            # ==================================================================
            # Idempotency: clean up any previously extracted fields or findings for this version
            for old_field in list(version.extracted_fields):
                db.delete(old_field)
            old_findings = list(
                db.query(Finding).filter(Finding.document_version_id == version.id).all()
            )
            for old_f in old_findings:
                db.delete(old_f)
            db.flush()

            processing_service.process_document_version(
                db,
                version=version,
                file_bytes=file_bytes,
                expected_institution_id=inst_code,
            )

            # ==================================================================
            # Stage D: Persist Evidence and Finalize Job
            # ==================================================================
            job_state = "partial" if version.processing_status == "partial" else "completed"
            job = ProcessingJobRepository.update_state(db, job, state=job_state)

            if inst_id:
                ReviewAuditRepository.create_audit_event(
                    db,
                    action="DOCUMENT_PROCESSING_COMPLETED",
                    target_type="DocumentVersion",
                    target_id=str(version.id),
                    actor_id="system_worker",
                    institution_id=inst_id,
                    details=f'{{"job_id": "{job.id}", "job_state": "{job_state}", "scan_status": "clean"}}',
                )

            db.commit()
            db.refresh(job)
            return job

        except Exception as exc:
            db.rollback()
            logger.exception("Error executing processing job %s: %s", job_id, exc)
            # Re-fetch records after rollback
            job_cur = ProcessingJobRepository.get_by_id(db, job_id)
            ver_cur = db.get(DocumentVersion, job.document_version_id) if job_cur else None

            if job_cur:
                is_transient = isinstance(exc, (IOError, TimeoutError, ConnectionError))
                if is_transient and job_cur.attempt_count < job_cur.max_attempts:
                    backoff_sec = 2 ** job_cur.attempt_count * 5
                    scheduled_for = _utc_now() + timedelta(seconds=backoff_sec)
                    ProcessingJobRepository.update_state(
                        db,
                        job_cur,
                        state="retry_wait",
                        last_error_code=exc.__class__.__name__[:64],
                        scheduled_for=scheduled_for,
                    )
                else:
                    ProcessingJobRepository.update_state(
                        db,
                        job_cur,
                        state="failed",
                        last_error_code=exc.__class__.__name__[:64],
                    )
                    if ver_cur:
                        ver_cur.processing_status = "failed"
                db.commit()
                return job_cur
            return None
