#!/usr/bin/env python3
"""Verify a deployment's environment in one command, without printing secrets.

Why this exists
---------------
Every failure in this deployment so far was invisible from the outside: a green
``/health`` on a database with no tables, a login screen that could only say
"cannot reach the API", a scanner that made uploads park in ``retry_wait``. Each
one is checkable in a second -- if you know exactly what to check.

Run this in the Render Shell of the backend service (or any host with the same
environment variables) immediately after a deploy:

    python tools/deploy/preflight.py

It checks, in order: database configuration, connectivity, migration revision
against the code's head, required tables, provisioned accounts, Redis, the
malware scanner, and document storage. Each line is PASS/FAIL/WARN with an
actionable reason, and the exit code is 1 if any required check fails.

Secrets: connection strings are never printed, only redacted
(``postgresql://user:***@host/db``). Nothing here writes to the database.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:  # allow `python tools/deploy/preflight.py`
    sys.path.insert(0, str(REPO_ROOT))

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

# Tables the application cannot work without. Kept as a list (not a count) so a
# half-applied migration names the missing table.
REQUIRED_TABLES = (
    "alembic_version",
    "users",
    "institutions",
    "institution_memberships",
    "applications",
    "documents",
    "document_versions",
    "processing_jobs",
    "outbox_messages",
    "validation_runs",
    "findings",
    "review_actions",
    "audit_packages",
)

_URL_CREDENTIALS = re.compile(r"(//[^:/@]+):[^@]*@")


def redact_url(value: str) -> str:
    """Mask the password in a connection string; keep the rest diagnosable."""
    if "://" not in value:
        return value
    return _URL_CREDENTIALS.sub(r"\1:***@", value)


@dataclass
class Result:
    name: str
    status: str
    detail: str


class Checks:
    def __init__(self) -> None:
        self.results: list[Result] = []

    def add(self, name: str, status: str, detail: str) -> None:
        self.results.append(Result(name, status, detail))

    @property
    def failed(self) -> list[Result]:
        return [r for r in self.results if r.status == FAIL]

    def render(self) -> str:
        width = max(len(r.name) for r in self.results) if self.results else 10
        lines = [f"{r.status:<4} {r.name:<{width}}  {r.detail}" for r in self.results]
        return "\n".join(lines)


def _deployment_marks_present() -> bool:
    """Read the deployment markers without importing the app (which may abort)."""
    if os.getenv("RENDER", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return any(
        os.getenv(name, "").strip().lower() in {"production", "prod"}
        for name in ("APP_ENV", "ENVIRONMENT", "ENV")
    )


def check_database_configuration(checks: Checks) -> str | None:
    """Validate DATABASE_URL, reporting failures instead of aborting.

    Importing the application's session module is what proves the guard works --
    it raises under exactly the conditions that break the deployed service. The
    preflight turns that exception into a FAIL line, because a traceback in a
    Render shell is harder to read than a checklist.
    """
    raw = os.getenv("DATABASE_URL", "").strip()
    try:
        from backend.app.db.session import is_deployed_environment, normalize_database_url
    except RuntimeError:
        checks.add("deployed environment", PASS, "detected (the database guard refused to start)")
        if not raw:
            checks.add(
                "DATABASE_URL",
                FAIL,
                "not set: the service cannot start here. Set it to the PostgreSQL "
                "connection string (Render: Postgres -> Connect -> Internal URL)",
            )
        else:
            checks.add(
                "DATABASE_URL",
                FAIL,
                "points at SQLite: not durable and not shareable with a worker",
            )
        return None

    checks.add(
        "deployed environment",
        PASS if is_deployed_environment() else WARN,
        "detected (RENDER/APP_ENV set)" if is_deployed_environment() else "not detected: local-style run",
    )

    if not raw:
        checks.add("DATABASE_URL", FAIL, "not set: the service cannot start on a deployed host")
        return None
    if raw.startswith("sqlite"):
        checks.add(
            "DATABASE_URL",
            FAIL,
            "points at SQLite: not durable and not shareable with a worker",
        )
        return None

    checks.add("DATABASE_URL", PASS, redact_url(raw))
    return normalize_database_url(raw)


def _query(engine, sql: str):
    """Run one read-only query on its own connection, returning None on error.

    PostgreSQL aborts the whole transaction after a failed statement, so an
    expected miss (no ``alembic_version`` yet) would poison every later check on
    the same connection and report a bogus "database unreachable".
    """
    from sqlalchemy import text

    try:
        with engine.connect() as connection:
            return connection.execute(text(sql)).scalars().all()
    except Exception:
        return None


def check_database(url: str | None, checks: Checks) -> None:
    if url is None:
        for name in ("database", "migrations", "tables", "accounts"):
            checks.add(name, WARN, "skipped: no usable DATABASE_URL")
        return

    from sqlalchemy import create_engine

    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect():
            pass
    except Exception as exc:
        checks.add("database", FAIL, f"unreachable ({type(exc).__name__})")
        for name in ("migrations", "tables", "accounts"):
            checks.add(name, WARN, "skipped: database unreachable")
        return

    checks.add("database", PASS, "connection established")

    revisions = _query(engine, "SELECT version_num FROM alembic_version")
    expected = alembic_head()
    if revisions is None:
        checks.add("migrations", FAIL, "no alembic_version table: migrations never ran")
    elif expected and revisions and revisions[0] != expected:
        checks.add("migrations", FAIL, f"database at {revisions[0]}, code expects {expected}")
    elif revisions:
        checks.add("migrations", PASS, f"at head ({revisions[0]})")
    else:
        checks.add("migrations", FAIL, "alembic_version is empty: no migration recorded")

    tables = _query(
        engine,
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'",
    )
    if tables is None:
        checks.add("tables", FAIL, "could not list tables")
    else:
        missing = [table for table in REQUIRED_TABLES if table not in tables]
        if missing:
            checks.add("tables", FAIL, "missing: " + ", ".join(missing))
        else:
            checks.add("tables", PASS, f"all {len(REQUIRED_TABLES)} required tables present")

        if "users" in tables:
            counts = _query(engine, "SELECT count(*) FROM users")
            count = counts[0] if counts else 0
            if count:
                checks.add("accounts", PASS, f"{count} user account(s) provisioned")
            else:
                checks.add(
                    "accounts",
                    FAIL,
                    "no users: run tools/demo/seed_demo.py against this database",
                )
        else:
            checks.add("accounts", WARN, "skipped: users table absent")

    engine.dispose()


def alembic_head() -> str | None:
    """Return the code's head revision, read from the Alembic scripts."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
        config.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))
        return ScriptDirectory.from_config(config).get_current_head()
    except Exception:
        return None


def check_redis(checks: Checks, url: str | None) -> None:
    from backend.app.worker.celery_app import REDIS_URL as default_url

    target = url or os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL") or default_url
    try:
        import redis  # type: ignore[import-untyped]

        client = redis.Redis.from_url(target, socket_connect_timeout=5, socket_timeout=5)
        client.ping()
        checks.add("redis", PASS, redact_url(target))
    except Exception as exc:
        checks.add(
            "redis",
            WARN,
            f"unreachable ({type(exc).__name__}): background jobs stay queued. "
            "Not required to log in, required for upload processing",
        )


def check_scanner(checks: Checks, host: str | None, port: int | None) -> None:
    """Scan a harmless payload through the same code path uploads use.

    A TCP connect proves nothing: the intake pipeline asks clamd to scan bytes
    and refuses to continue without a CLEAN/REJECTED verdict. This drives the
    real ClamAVScanner, so a scanner that answers but cannot scan is caught here
    rather than by every upload parking in retry_wait.
    """
    from backend.app.core.scanner import ClamAVScanner, ScanStatus

    target_host = host or os.getenv("CLAMAV_HOST")
    target_port = port or (int(os.getenv("CLAMAV_PORT", "3310")))
    if not target_host:
        checks.add(
            "scanner",
            WARN,
            "CLAMAV_HOST unset: uploads will park in retry_wait with SCAN_UNAVAILABLE "
            "(fail-closed, never clean). Fine for a login-only demo",
        )
        return

    target = f"{target_host}:{target_port}"
    try:
        result = ClamAVScanner(host=target_host, port=target_port).scan(
            b"aicte preflight - harmless text, not malware", filename="preflight.txt"
        )
    except Exception as exc:
        checks.add("scanner", FAIL, f"{target} raised {type(exc).__name__}: no verdict available")
        return

    if result.status is ScanStatus.CLEAN:
        checks.add("scanner", PASS, f"{target} returned CLEAN for a harmless payload")
    elif result.status is ScanStatus.REJECTED:
        checks.add(
            "scanner",
            FAIL,
            f"{target} rejected a harmless payload: signature database may be "
            "misconfigured or this is not a clean scanner",
        )
    else:
        checks.add(
            "scanner",
            FAIL,
            f"{target} returned {result.status.value}: uploads cannot be cleared, "
            "they park in retry_wait (fail-closed)",
        )


def check_storage(checks: Checks, directory: str | None) -> None:
    from backend.app.core.storage import LocalStorageBackend

    backend = LocalStorageBackend(directory) if directory else LocalStorageBackend()
    root = Path(getattr(backend, "base_dir", getattr(backend, "root", ".")))
    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=root, prefix=".preflight-", delete=True) as handle:
            handle.write(b"ok")
            handle.flush()
        checks.add("storage", PASS, f"writable: {root}")
    except Exception as exc:
        checks.add("storage", FAIL, f"not writable ({type(exc).__name__}): {root}")
    if "tmp" in str(root).lower() or str(root) in (".", ""):
        checks.add(
            "storage durability",
            WARN,
            "local directory on an ephemeral instance: uploads disappear on redeploy "
            "unless a persistent disk is mounted",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redis-url", default=None, help="override the Redis target")
    parser.add_argument("--scanner-host", default=None)
    parser.add_argument("--scanner-port", type=int, default=None)
    parser.add_argument("--storage-dir", default=None)
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        choices=["redis", "scanner", "storage"],
        help="skip optional infrastructure checks",
    )
    args = parser.parse_args(argv)

    checks = Checks()
    url = check_database_configuration(checks)
    check_database(url, checks)
    if "redis" not in args.skip:
        check_redis(checks, args.redis_url)
    if "scanner" not in args.skip:
        check_scanner(checks, args.scanner_host, args.scanner_port)
    if "storage" not in args.skip:
        check_storage(checks, args.storage_dir)

    print(checks.render())
    print()
    if checks.failed:
        print(f"RESULT: NOT READY ({len(checks.failed)} required check(s) failed)")
        return 1
    print("RESULT: READY (required checks passed; WARN items are documented limitations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
