"""Apply Alembic migrations from application startup, but only when deployed.

Why this exists
---------------
The deployed backend had *no* migration step anywhere: nothing in the repository
ran ``alembic upgrade head``, and the deploy log shows the service starting
against an empty database. Render's own mechanism for this is a Pre-Deploy
Command configured in the dashboard; this module makes the repository work even
if nobody has configured it, which is the difference between "green deploy, no
tables" and a service that can authenticate someone.

Design constraints
------------------
* **Deployed only.** Local runs and the test suite keep using the documented
  manual ``alembic upgrade head`` and must not touch Alembic on import.
* **Fail closed.** A migration error aborts startup. Serving traffic against a
  half-migrated schema is what produced ``no such table: users``.
* **Opt-out.** ``MIGRATE_ON_START=false`` disables it, so an operator who runs
  migrations in a release phase (or runs several instances) can turn it off.
* **Absolute paths.** ``script_location`` is resolved from the repository root so
  the working directory of the process does not matter.
* **No secrets in logs.** Only the revision id is logged.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from backend.app.db.session import get_database_url, is_deployed_environment

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "backend" / "alembic.ini"
ALEMBIC_SCRIPTS = REPO_ROOT / "backend" / "alembic"


def migration_enabled() -> bool:
    """True when startup should apply migrations."""
    if not is_deployed_environment():
        return False
    return os.getenv("MIGRATE_ON_START", "true").strip().lower() not in {"0", "false", "no"}


def run_migrations() -> str:
    """Upgrade the configured database to ``head``. Returns the resulting revision.

    Raises on any failure: the caller (startup) must not continue.
    """
    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    from backend.app.db.session import normalize_database_url

    if not ALEMBIC_INI.exists():  # pragma: no cover - packaging error
        raise RuntimeError(f"alembic.ini not found at {ALEMBIC_INI}")

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPTS))
    # env.py reads DATABASE_URL itself; setting it here keeps a single source of
    # truth and guarantees the normalised (driver-explicit) URL is used.
    config.set_main_option("sqlalchemy.url", normalize_database_url(get_database_url()))

    logger.info("Applying database migrations to head (MIGRATE_ON_START enabled)")
    command.upgrade(config, "head")

    engine = create_engine(normalize_database_url(get_database_url()))
    try:
        with engine.connect() as connection:
            revision = MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()
    logger.info("Database is at Alembic revision %s", revision)
    return revision or ""


def migrate_if_deployed() -> str | None:
    """Run migrations when configured to; otherwise do nothing.

    Returns the revision when migrations ran, else ``None``.
    """
    if not migration_enabled():
        return None
    return run_migrations()
