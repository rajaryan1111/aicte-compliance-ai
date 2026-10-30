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

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.session import get_db, normalize_database_url
from backend.app.main import app

# Integration test environment flags
RUN_LIVE_INTEGRATION_TESTS = (
    os.getenv("RUN_LIVE_INTEGRATION_TESTS", "").lower() in ("true", "1", "yes")
)
DEFAULT_PG_URL = "postgresql+psycopg2://aicte_test:aicte_test_pass@localhost:5432/aicte_test_db"
DEFAULT_REDIS_URL = "redis://localhost:6379/1"

POSTGRES_URL = normalize_database_url(
    os.getenv("INTEGRATION_DATABASE_URL", os.getenv("DATABASE_URL", DEFAULT_PG_URL))
)
REDIS_URL = os.getenv("INTEGRATION_REDIS_URL", os.getenv("REDIS_URL", DEFAULT_REDIS_URL))
CLAMAV_HOST = os.getenv("AICTE_CLAMAV_HOST", "localhost")
CLAMAV_PORT = int(os.getenv("AICTE_CLAMAV_PORT", "3310"))

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
        norm_url = normalize_database_url(url)
        eng = create_engine(norm_url, connect_args={"connect_timeout": int(timeout)})
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

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for worker process to initialize and connect to broker
    time.sleep(2.0)
    if proc.poll() is not None:
        stdout, stderr = proc.communicate()
        pytest.fail(f"Celery worker process failed to start (exit code {proc.returncode}):\n{stderr}")

    yield proc

    # Teardown: terminate gracefully
    try:
        proc.terminate()
        proc.wait(timeout=5.0)
    except Exception:
        proc.kill()


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

