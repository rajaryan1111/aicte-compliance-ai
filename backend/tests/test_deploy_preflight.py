"""Tests for the deployment preflight tool (tools/deploy/preflight.py).

The tool exists because every deployment failure in this project was invisible
from outside. These tests drive the real CLI and pin its promises: it never
prints a credential, and it exits non-zero with an explicit FAIL line -- not a
traceback -- when the environment cannot work.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "deploy" / "preflight.py"

BASE_ENV = {
    "PATH": os.environ.get("PATH", ""),
    "PYTHONPATH": str(REPO_ROOT),
}
SKIP_OPTIONAL = ["--skip", "redis", "--skip", "scanner", "--skip", "storage"]


def run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={**BASE_ENV, **env},
        cwd=REPO_ROOT,
        check=False,
        timeout=120,
    )


def test_missing_database_url_fails_without_a_traceback() -> None:
    """This is the exact state that failed the Render deploy."""
    result = run({"RENDER": "true"}, *SKIP_OPTIONAL)

    assert result.returncode == 1
    assert "FAIL" in result.stdout and "DATABASE_URL" in result.stdout
    assert "NOT READY" in result.stdout
    assert "Traceback" not in result.stderr


def test_sqlite_in_a_deployed_environment_fails() -> None:
    result = run({"RENDER": "true", "DATABASE_URL": "sqlite:///./aicte_dev.db"}, *SKIP_OPTIONAL)

    assert result.returncode == 1
    assert "SQLite" in result.stdout


def test_connection_string_password_is_never_printed() -> None:
    """The host and database stay visible; the password must not."""
    result = run(
        {
            "RENDER": "true",
            # Nothing listens on port 1: the run fails, but the redacted URL is
            # printed before the connection attempt.
            "DATABASE_URL": "postgresql://demo_user:s3cret-pw@127.0.0.1:1/appdb",
        },
        *SKIP_OPTIONAL,
    )

    assert "s3cret-pw" not in result.stdout + result.stderr
    assert "postgresql://demo_user:***@127.0.0.1:1/appdb" in result.stdout
    assert result.returncode == 1
    assert "unreachable" in result.stdout


@pytest.mark.parametrize("marker", ["APP_ENV", "ENVIRONMENT", "ENV"])
def test_production_markers_are_recognised(marker: str) -> None:
    """Any of the documented markers must trigger the deployed-environment guard."""
    result = run({marker: "production"}, *SKIP_OPTIONAL)

    assert "detected" in result.stdout
    assert result.returncode == 1


def test_sqlite_is_refused_even_without_deployment_markers() -> None:
    """A developer's local SQLite is fine for the app, never for a deployment check."""
    result = run({"DATABASE_URL": "sqlite:///./aicte_dev.db"}, *SKIP_OPTIONAL)

    assert result.returncode == 1
    assert "not durable" in result.stdout
