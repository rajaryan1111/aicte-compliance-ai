"""Database engine and session management."""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///./aicte_dev.db"

# Bare PostgreSQL schemes that carry no explicit DBAPI. SQLAlchemy 2.1 changed
# the default DBAPI for these from psycopg2 to psycopg (v3); this project pins
# psycopg2-binary, so the driver is always made explicit below.
_BARE_POSTGRES_SCHEMES = {"postgres", "postgresql"}
_POSTGRES_DRIVER = "psycopg2"


def normalize_database_url(url: str) -> str:
    """Make the DBAPI explicit in ``postgresql://`` URLs.

    ``DATABASE_URL`` is documented as a bare ``postgresql://…`` string (CI and
    ``docs/development/INTEGRATION_TESTING.md``), but the SQLAlchemy default
    DBAPI for that scheme is a library detail that has already changed once:
    SQLAlchemy 2.1 resolves it to ``psycopg`` (v3), which this project does not
    install, so every bare URL failed with
    ``ModuleNotFoundError: No module named 'psycopg'``.

    Pinning the driver in the URL keeps the documented input format working and
    keeps behaviour independent of the installed SQLAlchemy minor version.
    URLs that already name a driver (``postgresql+psycopg2://``,
    ``postgresql+psycopg://``), and non-PostgreSQL URLs such as ``sqlite:///``,
    are returned unchanged.
    """
    scheme, separator, remainder = url.partition("://")
    if not separator:
        return url
    if scheme.lower() in _BARE_POSTGRES_SCHEMES:
        return f"postgresql+{_POSTGRES_DRIVER}://{remainder}"
    return url


_PRODUCTION_ENV_VALUES = {"production", "prod"}


def is_deployed_environment() -> bool:
    """Report whether this process is running on a deployed platform.

    ``RENDER`` is set by Render for every service it runs, so the guard below
    works even if nobody remembered to set ``APP_ENV``. ``APP_ENV`` /
    ``ENVIRONMENT`` are honoured too, for other hosts.

    Deliberately false for tests and local runs: the SQLite default must keep
    working there, and 400+ tests depend on it.
    """
    if os.getenv("RENDER", "").strip().lower() in {"1", "true", "yes"}:
        return True
    for name in ("APP_ENV", "ENVIRONMENT", "ENV"):
        if os.getenv(name, "").strip().lower() in _PRODUCTION_ENV_VALUES:
            return True
    return False


def get_database_url() -> str:
    """Return the configured database URL, refusing a silent SQLite fallback.

    Local runs and tests fall back to the SQLite file, which is what makes the
    demo easy to start. A *deployed* service must not: the fallback previously
    produced a service that answered ``/health`` with ``{"status": "ok"}`` while
    every real query failed with ``sqlite3.OperationalError: no such table:
    users`` -- a healthy-looking API with an unusable database, and a login
    screen that could not tell the operator what was wrong.

    So on a deployed platform a missing ``DATABASE_URL``, or one pointing at
    SQLite, raises at import time. Failing the deploy with an actionable message
    is better than serving a service that can never authenticate anyone.
    """
    configured = os.getenv("DATABASE_URL", "").strip()

    if not is_deployed_environment():
        return configured or DEFAULT_DATABASE_URL

    if not configured:
        raise RuntimeError(
            "DATABASE_URL is not set. This looks like a deployed environment "
            "(RENDER/APP_ENV is set), where the local SQLite file is not a valid "
            "database: it is empty on every fresh container, so authentication "
            "fails with 'no such table: users'. Set DATABASE_URL to the "
            "PostgreSQL connection string (postgresql://user:password@host:5432/db) "
            "and run 'python -m alembic -c backend/alembic.ini upgrade head'. "
            "For an intentional single-container demo, unset RENDER/APP_ENV."
        )
    if configured.startswith("sqlite"):
        raise RuntimeError(
            "DATABASE_URL points at SQLite, but this looks like a deployed "
            "environment (RENDER/APP_ENV is set). A SQLite file is not durable "
            "across deploys and cannot be shared with a worker process. Set "
            "DATABASE_URL to the PostgreSQL connection string and run the Alembic "
            "migrations. For an intentional single-container demo, unset "
            "RENDER/APP_ENV."
        )
    return configured


def create_db_engine(url: str | None = None, echo: bool = False, **kwargs: Any) -> Engine:
    """Create a SQLAlchemy engine configured for PostgreSQL or SQLite."""
    db_url = normalize_database_url(url or get_database_url())
    connect_args = kwargs.pop("connect_args", {})

    if db_url.startswith("sqlite"):
        connect_args.setdefault("check_same_thread", False)
        return create_engine(db_url, echo=echo, connect_args=connect_args, **kwargs)

    # Production/PostgreSQL settings: connection pool health checks
    return create_engine(db_url, echo=echo, pool_pre_ping=True, connect_args=connect_args, **kwargs)


engine: Engine = create_db_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
