"""Database engine and session management."""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///./aicte_dev.db"


def get_database_url() -> str:
    """Return the database URL from DATABASE_URL or the local SQLite default."""
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def normalize_database_url(url: str) -> str:
    """Resolve driver-less PostgreSQL URLs to the driver this project ships.

    SQLAlchemy >= 2.1 maps a bare ``postgresql://`` (or legacy ``postgres://``)
    URL to its unified psycopg (v3) dialect, but this repository declares and
    installs the psycopg2 driver (``psycopg2-binary``) only.  Without this
    normalization, every PostgreSQL engine — runtime sessions and Alembic
    migrations alike — fails with ``ModuleNotFoundError: No module named
    'psycopg'`` before any connection is attempted.  Explicitly suffixed URLs
    (``postgresql+psycopg2://``, ``postgresql+psycopg://``, ...) are returned
    untouched so an operator can still choose a driver deliberately.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


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
