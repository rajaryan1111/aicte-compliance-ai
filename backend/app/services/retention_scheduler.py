"""In-process background scheduler for automated recurring data retention passes."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.services.retention_service import (
    AUDIT_LOG_MINIMUM_RETENTION_YEARS,
    DEFAULT_JOB_RETENTION_DAYS,
    DEFAULT_QUARANTINE_RETENTION_DAYS,
    DEFAULT_SCHEDULE_INTERVAL_SECONDS,
    RetentionService,
)

logger = logging.getLogger(__name__)


class RetentionBackgroundScheduler:
    """Thread-safe recurring background scheduler enforcing data retention policies."""

    _instance: RetentionBackgroundScheduler | None = None
    _lock = threading.Lock()

    def __init__(self, interval_seconds: int = DEFAULT_SCHEDULE_INTERVAL_SECONDS) -> None:
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @classmethod
    def get_instance(cls) -> RetentionBackgroundScheduler:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start the background recurring retention worker thread."""
        with self._lock:
            if self.is_running():
                logger.info("RetentionBackgroundScheduler is already running.")
                return

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="RetentionSchedulerThread",
                daemon=True,
            )
            self._thread.start()
            logger.info("Started RetentionBackgroundScheduler with interval=%ds", self.interval_seconds)

    def stop(self) -> None:
        """Stop the background retention worker thread gracefully."""
        with self._lock:
            if not self.is_running():
                return

            self._stop_event.set()
            if self._thread:
                self._thread.join(timeout=5.0)
            self._thread = None
            logger.info("Stopped RetentionBackgroundScheduler.")

    def run_once(self, dry_run: bool = False, actor_id: str = "manual_scheduler_trigger") -> dict[str, Any]:
        """Trigger an immediate retention execution pass."""
        db = SessionLocal()
        try:
            rec = RetentionService.run_retention_pass(
                db,
                execution_type="manual" if not dry_run else "dry_run",
                dry_run=dry_run,
                actor_id=actor_id,
            )
            return {
                "run_reference": rec.run_reference,
                "status": rec.status,
                "quarantined_purged": rec.quarantined_purged_count,
                "jobs_cleaned": rec.jobs_cleaned_count,
                "storage_errors": rec.storage_errors_count,
                "started_at": rec.started_at.isoformat(),
            }
        finally:
            db.close()

    def _run_loop(self) -> None:
        """Periodic execution loop executing at configured intervals."""
        while not self._stop_event.is_set():
            # Wait for interval or stop signal
            if self._stop_event.wait(timeout=self.interval_seconds):
                break

            logger.info("Executing scheduled recurring retention pass...")
            db = SessionLocal()
            try:
                RetentionService.run_retention_pass(
                    db,
                    execution_type="scheduled",
                    dry_run=False,
                    actor_id="retention_scheduler",
                )
            except Exception as exc:
                logger.exception("Scheduled retention pass failed: %s", exc)
            finally:
                db.close()

    def get_status(self, db: Session | None = None) -> dict[str, Any]:
        """Return diagnostic status information for administrative inspection."""
        close_on_exit = False
        if db is None:
            db = SessionLocal()
            close_on_exit = True
        try:
            latest = RetentionService.get_latest_run(db)
            return {
                "scheduler_running": self.is_running(),
                "schedule_interval_seconds": self.interval_seconds,
                "quarantine_retention_days": DEFAULT_QUARANTINE_RETENTION_DAYS,
                "job_retention_days": DEFAULT_JOB_RETENTION_DAYS,
                "audit_log_retention_years": AUDIT_LOG_MINIMUM_RETENTION_YEARS,
                "last_run": latest,
            }
        finally:
            if close_on_exit:
                db.close()
