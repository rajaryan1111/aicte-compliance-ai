"""Shared fixtures and infrastructure readiness checks for Milestone B11 integration tests."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Generator
from typing import Any

import pytest
import redis
from pathlib import Path
import tempfile

# The live suite must exercise the real broker.  backend/app/worker/celery_app.py
# defaults task_always_eager to true whenever pytest is importable, so without
# this the *producer* (the pytest process) would run .delay() inline, no message
# would ever reach Redis, and the worker spawned below would idle forever.  This
# has to happen before the application modules below are imported, because
# celery_app decides its default at import time.  A caller that sets the
# variable explicitly still wins.
_RUN_LIVE_INTEGRATION_TESTS = os.getenv("RUN_LIVE_INTEGRATION_TESTS", "").lower() in (
    "true",
    "1",
    "yes",
)
if _RUN_LIVE_INTEGRATION_TESTS:
    os.environ["CELERY_TASK_ALWAYS_EAGER"] = "false"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from backend.app.db.session import get_db, normalize_database_url  # noqa: E402
from backend.app.main import app  # noqa: E402

# Integration test environment flags
RUN_LIVE_INTEGRATION_TESTS = _RUN_LIVE_INTEGRATION_TESTS
DEFAULT_PG_URL = "postgresql://aicte_test:aicte_test_pass@localhost:5432/aicte_test_db"
DEFAULT_REDIS_URL = "redis://localhost:6379/1"

# Normalised like the application does, so this harness uses the pinned
# psycopg2 driver instead of inheriting SQLAlchemy's bare-scheme default (psycopg v3).
POSTGRES_URL = normalize_database_url(
    os.getenv("INTEGRATION_DATABASE_URL", os.getenv("DATABASE_URL", DEFAULT_PG_URL))
)
REDIS_URL = os.getenv("INTEGRATION_REDIS_URL", os.getenv("REDIS_URL", DEFAULT_REDIS_URL))
CLAMAV_HOST = os.getenv("AICTE_CLAMAV_HOST", "localhost")
CLAMAV_PORT = int(os.getenv("AICTE_CLAMAV_PORT", "3310"))
# Bounded wait for the worker to answer a control ping (was a fixed 2s sleep).
WORKER_READY_TIMEOUT = float(os.getenv("INTEGRATION_WORKER_READY_TIMEOUT", "30"))

TEST_JWT_SECRET = "integration-test-secret-key-at-least-32-chars-long!"
os.environ.setdefault("JWT_SECRET_KEY", TEST_JWT_SECRET)

INTEGRATION_STORAGE_DIR = os.getenv(
    "STORAGE_LOCAL_DIR",
    str(Path(tempfile.gettempdir()) / "aicte_integration_storage"),
)
os.environ["STORAGE_LOCAL_DIR"] = INTEGRATION_STORAGE_DIR
Path(INTEGRATION_STORAGE_DIR).mkdir(parents=True, exist_ok=True)



def is_postgres_available(url: str, timeout: float = 2.0) -> tuple[bool, str]:
    """Verify live PostgreSQL connectivity by issuing a SELECT 1 ping."""
    try:
        eng = create_engine(url, connect_args={"connect_timeout": int(timeout)})
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "OK"
    except Exception as exc:
        return False, str(exc)


def is_redis_available(url: str, timeout: float = 2.0) -> tuple[bool, str]:
    """Verify live Redis connectivity by sending a PING command."""
    try:
        r = redis.Redis.from_url(url, socket_timeout=timeout, socket_connect_timeout=timeout)
        r.ping()
        return True, "OK"
    except Exception as exc:
        return False, str(exc)


def is_clamav_available(host: str = CLAMAV_HOST, port: int = CLAMAV_PORT, timeout: float = 2.0) -> tuple[bool, str]:
    """Verify live ClamAV daemon connectivity via TCP socket."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.sendall(b"zPING\0")
            response = s.recv(1024)
            if b"PONG" in response:
                return True, "OK"
            return False, f"Unexpected response: {response!r}"
    except Exception as exc:
        return False, str(exc)


@pytest.fixture(scope="session")
def require_live_postgres() -> str:
    """Enforce PostgreSQL availability for integration tests.

    If RUN_LIVE_INTEGRATION_TESTS is not enabled, skips the test cleanly.
    If RUN_LIVE_INTEGRATION_TESTS is enabled and PostgreSQL cannot be reached,
    FAILS the test with a clear, actionable diagnostic.
    """
    if not RUN_LIVE_INTEGRATION_TESTS:
        pytest.skip(
            "Live infrastructure integration tests are disabled. "
            "Set RUN_LIVE_INTEGRATION_TESTS=true to execute against real services."
        )

    ok, reason = is_postgres_available(POSTGRES_URL)
    if not ok:
        pytest.fail(
            f"Required PostgreSQL integration database at {POSTGRES_URL} is unreachable: {reason}. "
            "Ensure the integration container is running (docker compose -f docker-compose.integration.yml up -d) "
            "or that the CI PostgreSQL service container is healthy."
        )
    return POSTGRES_URL


@pytest.fixture(scope="session")
def require_live_redis() -> str:
    """Enforce Redis availability for integration tests.

    If RUN_LIVE_INTEGRATION_TESTS is enabled and Redis cannot be reached,
    FAILS the test clearly without falling back to mocks.
    """
    if not RUN_LIVE_INTEGRATION_TESTS:
        pytest.skip(
            "Live infrastructure integration tests are disabled. "
            "Set RUN_LIVE_INTEGRATION_TESTS=true to execute against real services."
        )

    ok, reason = is_redis_available(REDIS_URL)
    if not ok:
        pytest.fail(
            f"Required Redis broker at {REDIS_URL} is unreachable: {reason}. "
            "Ensure the Redis container is running (docker compose -f docker-compose.integration.yml up -d)."
        )
    return REDIS_URL


@pytest.fixture(scope="session")
def live_postgres_engine(require_live_postgres: str) -> Generator[Engine, None, None]:
    """Provide a SQLAlchemy Engine connected to the real PostgreSQL database."""
    engine = create_engine(
        require_live_postgres,
        pool_pre_ping=True,
        echo=False,
    )
    yield engine
    engine.dispose()


@pytest.fixture
def live_postgres_session(live_postgres_engine: Engine) -> Generator[Session, None, None]:
    """Provide an isolated database session on real PostgreSQL, cleaning up on teardown."""
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=live_postgres_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def live_redis_client(require_live_redis: str) -> Generator[redis.Redis[Any], None, None]:
    """Provide a Redis client connected to the test Redis database."""
    client = redis.Redis.from_url(require_live_redis)
    client.flushdb()
    try:
        yield client
    finally:
        try:
            client.flushdb()
            client.close()
        except Exception:
            pass


@pytest.fixture(scope="module")
def live_celery_worker(require_live_postgres: str, require_live_redis: str) -> Generator[subprocess.Popen[Any], None, None]:
    """Start a real Celery worker subprocess connected to real Redis and PostgreSQL."""
    env = os.environ.copy()
    env["DATABASE_URL"] = require_live_postgres
    env["REDIS_URL"] = require_live_redis
    env["CELERY_BROKER_URL"] = require_live_redis
    env["CELERY_TASK_ALWAYS_EAGER"] = "false"
    env["PYTHONUTF8"] = "1"
    env["JWT_SECRET_KEY"] = TEST_JWT_SECRET
    env["STORAGE_LOCAL_DIR"] = INTEGRATION_STORAGE_DIR

    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "backend.app.worker.celery_app",
        "worker",
        "-l",
        "warning",
        "-c",
        "1",
        "--pool=solo",
        "-Q",
        "celery",
    ]

    # Worker output goes to a file rather than a pipe: nothing reads an unread
    # PIPE, so a chatty worker would block on a full buffer, and on timeout we
    # want its actual output for the failure message instead of a hang.
    log_file = tempfile.NamedTemporaryFile(  # noqa: SIM115 - closed in teardown
        mode="w+", prefix="celery_worker_", suffix=".log", delete=False
    )

    def _read_log() -> str:
        log_file.flush()
        with open(log_file.name, encoding="utf-8", errors="replace") as handle:
            return handle.read()

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Bounded readiness polling on an observable condition -- the worker
    # answering a control ping -- instead of a fixed sleep, which raced a real
    # worker start (~2s here) and produced non-deterministic results.
    from backend.app.worker.celery_app import celery_app

    celery_app.conf.broker_url = require_live_redis
    readiness_deadline = time.time() + WORKER_READY_TIMEOUT
    worker_ready = False
    while time.time() < readiness_deadline:
        if proc.poll() is not None:
            pytest.fail(
                f"Celery worker exited during startup (exit code {proc.returncode}):\n{_read_log()}"
            )
        try:
            # A worker that has not finished booting either does not reply or
            # raises a transport error; both mean "not ready yet".
            if celery_app.control.ping(timeout=0.5):
                worker_ready = True
                break
        except Exception:
            pass
        time.sleep(0.25)

    if not worker_ready:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except Exception:
            proc.kill()
        pytest.fail(
            f"Celery worker did not answer a control ping within {WORKER_READY_TIMEOUT}s.\n"
            f"Broker: {require_live_redis}\nWorker output:\n{_read_log()}"
        )

    yield proc

    # Teardown: terminate gracefully, then read the log before closing it.
    try:
        proc.terminate()
        proc.wait(timeout=5.0)
    except Exception:
        proc.kill()
        proc.wait(timeout=5.0)
    finally:
        log_file.close()
        try:
            os.unlink(log_file.name)
        except OSError:
            pass


@pytest.fixture
def live_api_client(live_postgres_engine: Engine) -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient wired to the real PostgreSQL database."""
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=live_postgres_engine)

    def _override_get_db() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)

