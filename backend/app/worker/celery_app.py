"""Celery application configuration for AICTE Compliance AI background processing."""

from __future__ import annotations

from datetime import timedelta
import os

from celery import Celery

import sys

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
    # Recovery sweep: the only scheduler that re-enqueues retry_wait jobs,
    # lost queued jobs, and undelivered outbox messages. Schedule it exactly
    # once — run a single worker with `--beat`, or one standalone
    # `celery beat` process alongside beat-less workers. The sweep itself is
    # idempotent, so a duplicate beat would be noisy but not incorrect.
    beat_schedule={
        "recovery-sweep": {
            "task": "backend.app.worker.tasks.recovery_sweep_task",
            "schedule": timedelta(seconds=30),
        },
    },
)

celery_app.autodiscover_tasks(["backend.app.worker"])
