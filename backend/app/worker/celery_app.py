"""Celery application configuration for AICTE Compliance AI background processing."""

from __future__ import annotations

import os
import ssl

from celery import Celery

import sys

REDIS_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
is_pytest = "pytest" in sys.modules or any("pytest" in arg for arg in sys.argv)
default_eager = "true" if is_pytest else "false"
CELERY_TASK_ALWAYS_EAGER = (
    os.getenv("CELERY_TASK_ALWAYS_EAGER", default_eager).lower() in ("true", "1", "yes")
)


def _redis_tls_options() -> dict[str, object]:
    """Verified-TLS context for a ``rediss://`` broker or result URL.

    Celery applies TLS purely from app config; URL query parameters do not
    reach the kombu broker connection, so an API process dispatching to a
    ``rediss://`` URL without this config either publishes unverified or is
    refused outright by redis-py ("a rediss:// URL must have parameter
    ssl_cert_reqs"). Both are unacceptable, so the configured TLS always
    requires certificate verification: the system CA store by default, or the
    CA bundle named by ``REDIS_SSL_CA_CERTS`` (platform-appropriate, e.g.
    certifi on hosts whose Python ships no default store).

    The value is a dict of redis-py SSL kwargs, not an ``ssl.SSLContext``: kombu
    unpacks these options verbatim into ``SSLConnection(...)`` constructors, and
    an ``SSLContext`` there fails with "'SSLContext' object is not iterable"
    (observed live: an upload's Outbox publish died with exactly that error).
    Verification stays required: redis-py defaults would otherwise leave
    ``ssl_cert_reqs`` unset, which redis-py rejects for ``rediss://`` URLs.

    Deliberately no bypass switch: a rediss:// scheme is always verified.
    """
    options: dict[str, object] = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
    ca_certs = os.getenv("REDIS_SSL_CA_CERTS", "").strip()
    if ca_certs:
        options["ssl_ca_certs"] = ca_certs
    certfile = os.getenv("REDIS_SSL_CERTFILE", "").strip()
    keyfile = os.getenv("REDIS_SSL_KEYFILE", "").strip()
    if certfile:
        options["ssl_certfile"] = certfile
    if keyfile:
        options["ssl_keyfile"] = keyfile
    return options


_REDIS_TLS_APPLIED = REDIS_URL.startswith("rediss://")
_tls_options = _redis_tls_options() if _REDIS_TLS_APPLIED else None

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
    # Periodic re-dispatch of jobs whose retry backoff has elapsed. The schedule
    # is only active when a beat is running (`celery worker -B`, or a separate
    # `celery beat` service); without it, retry_wait jobs are never retried.
    beat_schedule={
        "sweep-due-retries": {
            "task": "backend.app.worker.tasks.sweep_due_retries_task",
            "schedule": float(os.getenv("RETRY_SWEEP_INTERVAL_SECONDS", "30")),
        }
    },
)

if _tls_options is not None:
    # Verified TLS for both the broker and the result backend (see
    # _redis_tls_options). Local bootstrap modules may override these values,
    # but the defaults are always certificate-verification-required.
    celery_app.conf.update(
        broker_use_ssl=_tls_options,
        redis_backend_use_ssl=_tls_options,
    )

celery_app.autodiscover_tasks(["backend.app.worker"])
