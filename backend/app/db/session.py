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


def get_database_url() -> str:
    """Return the database URL from DATABASE_URL or the local SQLite default.

    Returned verbatim: normalisation happens where the URL is consumed (engine
    construction and Alembic), so this helper keeps reporting what was configured.
    """
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


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
