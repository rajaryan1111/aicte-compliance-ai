"""Regression tests: PostgreSQL URLs keep using the pinned psycopg2 driver.

SQLAlchemy 2.1 changed the default DBAPI for the bare ``postgresql://`` scheme
from ``psycopg2`` to ``psycopg`` (v3). ``backend/requirements.txt`` pins
``psycopg2-binary`` and the documented ``DATABASE_URL`` form is a bare
``postgresql://…`` (see ``.github/workflows/backend-tests.yml`` and
``docs/development/INTEGRATION_TESTING.md``), so a fresh install raised
``ModuleNotFoundError: No module named 'psycopg'`` before any connection was
attempted -- in the CI migration job and in any PostgreSQL deployment.

These tests pin the fix: the DBAPI is made explicit by the application, so it
no longer depends on a SQLAlchemy default.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.db.session import (
    create_db_engine,
    get_database_url,
    normalize_database_url,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BARE_URL = "postgresql://aicte_test:aicte_test_pass@localhost:5432/aicte_test_db"
NORMALISED_URL = "postgresql+psycopg2://aicte_test:aicte_test_pass@localhost:5432/aicte_test_db"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        # The documented CI / integration-testing form.
        (BARE_URL, NORMALISED_URL),
        # Legacy Heroku-style alias for the same scheme.
        ("postgres://u:p@db:5432/x", "postgresql+psycopg2://u:p@db:5432/x"),
        # SQLAlchemy's own postgresql:// form with query options preserved.
        (
            "postgresql://u:p@db:5432/x?sslmode=require",
            "postgresql+psycopg2://u:p@db:5432/x?sslmode=require",
        ),
        # Already explicit: left alone, so an operator can opt into psycopg v3.
        ("postgresql+psycopg2://u:p@db:5432/x", "postgresql+psycopg2://u:p@db:5432/x"),
        ("postgresql+psycopg://u:p@db:5432/x", "postgresql+psycopg://u:p@db:5432/x"),
        # Non-PostgreSQL URLs are untouched.
        ("sqlite:///./demo.db", "sqlite:///./demo.db"),
        ("sqlite+pysqlite:///:memory:", "sqlite+pysqlite:///:memory:"),
    ],
)
def test_normalize_database_url(given: str, expected: str) -> None:
    assert normalize_database_url(given) == expected


def test_normalize_is_idempotent() -> None:
    once = normalize_database_url(BARE_URL)
    assert normalize_database_url(once) == once


def test_normalize_leaves_non_url_strings_alone() -> None:
    assert normalize_database_url("") == ""
    assert normalize_database_url("not-a-url") == "not-a-url"


def test_create_db_engine_uses_psycopg2_for_bare_postgresql_url() -> None:
    """Engine construction must resolve the pinned driver without connecting.

    ``create_engine`` imports the DBAPI eagerly, which is exactly what failed
    with ``ModuleNotFoundError`` before the fix; no server is needed.
    """
    engine = create_db_engine(BARE_URL)
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg2"
    finally:
        engine.dispose()


def test_create_db_engine_normalizes_database_url_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The DATABASE_URL path is normalised too, not just an explicit argument."""
    monkeypatch.setenv("DATABASE_URL", BARE_URL)
    assert get_database_url() == BARE_URL  # the getter still reports what was configured
    engine = create_db_engine()
    try:
        assert engine.dialect.driver == "psycopg2"
    finally:
        engine.dispose()


def test_alembic_offline_migration_accepts_bare_postgresql_url() -> None:
    """End-to-end check of the CI migration path, without needing a server.

    ``alembic upgrade head --sql`` runs offline: Alembic still builds the
    PostgreSQL dialect, which imports the DBAPI -- the exact step that raised
    ``ModuleNotFoundError: No module named 'psycopg'`` on a fresh install.
    Generating SQL proves driver initialisation succeeded; it does not prove a
    live migration, which requires a real PostgreSQL service.
    """
    env = {**os.environ, "DATABASE_URL": BARE_URL}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "backend/alembic.ini",
            "upgrade",
            "head",
            "--sql",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert "No module named 'psycopg'" not in proc.stderr, proc.stderr[-2000:]
    assert proc.returncode == 0, (proc.stdout[-2000:], proc.stderr[-2000:])
    assert "Context impl PostgresqlImpl." in proc.stdout + proc.stderr
    assert "CREATE TABLE" in proc.stdout
