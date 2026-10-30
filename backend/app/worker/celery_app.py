"""Celery application configuration for AICTE Compliance AI background processing."""

from __future__ import annotations

import os
import sys

from celery import Celery

REDIS_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
is_pytest = "pytest" in sys.modules or any("pytest" in arg for arg in sys.argv)
default_eager = "true" if is_pytest else "false"
CELERY_TASK_ALWAYS_EAGER = (
    os.getenv("CELERY_TASK_ALWAYS_EAGER", default_eager).lower() in ("true", "1", "yes")
)

celery_app = Celery(
    "aicte_compliance_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

retention_interval = float(os.getenv("RETENTION_SCHEDULE_INTERVAL_SECONDS", "86400"))

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_always_eager=CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=False,
    broker_connection_timeout=1.0,
    broker_transport_options={"max_retries": 1},
    beat_schedule={
        "periodic-retention-pass": {
            "task": "backend.app.worker.tasks.periodic_retention_pass_task",
            "schedule": retention_interval,
        },
    },
)

celery_app.autodiscover_tasks(["backend.app.worker"])
