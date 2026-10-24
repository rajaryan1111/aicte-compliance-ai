"""Regression tests: a deployed service must not fall back to SQLite.

Why this exists
---------------
The Render backend answered ``GET /health`` with ``{"status": "ok"}`` while the
container was running against an empty SQLite file, so every authentication
attempt died on ``sqlite3.OperationalError: no such table: users``. The service
looked healthy and the login screen only said it could not reach the API.

``get_database_url()`` therefore refuses both a missing ``DATABASE_URL`` and a
SQLite ``DATABASE_URL`` when the process is clearly deployed (``RENDER`` is set,
or ``APP_ENV``/``ENVIRONMENT``/``ENV`` is ``production``), and keeps the SQLite
default for local runs and this test suite.

The guard raises at import time, so a misconfigured deploy fails loudly instead
of serving a service that can never authenticate anyone.
"""

from __future__ import annotations

import pytest

from backend.app.db.session import (
    DEFAULT_DATABASE_URL,
    get_database_url,
    is_deployed_environment,
)

POSTGRES_URL = "postgresql://demo:not-a-real-password@db.example.invalid:5432/appdb"

DEPLOYMENT_MARKERS = ("RENDER", "APP_ENV", "ENVIRONMENT", "ENV")


@pytest.fixture(autouse=True)
def clear_deployment_markers(monkeypatch: pytest.MonkeyPatch):
    """Start each test from an unambiguous "local machine" environment."""
    for marker in DEPLOYMENT_MARKERS:
        monkeypatch.delenv(marker, raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    yield
    for marker in DEPLOYMENT_MARKERS:
        monkeypatch.delenv(marker, raising=False)


@pytest.mark.parametrize("marker", DEPLOYMENT_MARKERS)
def test_each_deployment_marker_is_recognised(monkeypatch: pytest.MonkeyPatch, marker: str) -> None:
    monkeypatch.setenv(marker, "production" if marker != "RENDER" else "true")

    assert is_deployed_environment() is True


def test_local_run_keeps_the_sqlite_default() -> None:
    """Local development and the test suite still get the throwaway SQLite file."""
    assert is_deployed_environment() is False
    assert get_database_url() == DEFAULT_DATABASE_URL


def test_local_run_honours_an_explicit_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)

    assert get_database_url() == POSTGRES_URL


def test_deployed_without_database_url_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENDER", "true")

    with pytest.raises(RuntimeError) as excinfo:
        get_database_url()

    message = str(excinfo.value)
    assert "DATABASE_URL is not set" in message
    # The message must tell the operator how to fix it, not just that it failed.
    assert "alembic" in message.lower()


def test_deployed_with_sqlite_url_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./aicte_dev.db")

    with pytest.raises(RuntimeError) as excinfo:
        get_database_url()

    message = str(excinfo.value)
    assert "SQLite" in message
    assert "postgresql" in message.lower()


def test_deployed_with_postgres_url_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)

    assert get_database_url() == POSTGRES_URL


def test_guard_does_not_echo_the_connection_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """Error text must not leak credentials to a log aggregator."""
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./leaked-name.db")

    with pytest.raises(RuntimeError) as excinfo:
        get_database_url()

    assert "not-a-real-password" not in str(excinfo.value)
