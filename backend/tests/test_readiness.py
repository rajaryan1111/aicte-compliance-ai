"""Contract and behaviour tests for ``GET /health/ready``.

The liveness endpoint ``GET /health`` is pinned elsewhere to a fixed 200; this
suite pins the *strict* readiness surface: 200 only when the database answers,
the intake schema is migrated, a real malware engine can positively scan, and
private storage accepts writes — 503 with per-component detail otherwise.
"""

from __future__ import annotations

from typing import Any, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.scanner import (
    ClamAVScanner,
    QuarantineScanner,
    ScanResult,
    ScanStatus,
    set_malware_scanner,
)
from backend.app.core.storage import set_storage_backend
from backend.app.db.models import Base
from backend.app.db.session import get_db
from backend.app.main import app

# Field order is part of the contract, as for the other pinned endpoints.
READINESS_KEYS = ["status", "checks"]
CHECK_KEYS = ["name", "ok", "detail"]
CHECK_NAMES = ["database", "schema", "malware_scanner", "storage"]


class FakeScanner:
    """Scanner double with a controllable availability answer."""

    def __init__(self, available: bool) -> None:
        self._available = available

    def scan(self, data: bytes, filename: str | None = None) -> ScanResult:
        return ScanResult(status=ScanStatus.CLEAN, scanner_name="fake")

    def is_available(self) -> bool:
        return self._available


class BrokenStorage:
    """Storage double whose writes fail (read-only or full volume)."""

    def put(self, storage_key: str, data: bytes) -> int:
        raise OSError("read-only file system")

    def read(self, storage_key: str) -> bytes:
        raise OSError("read-only file system")

    def delete(self, storage_key: str) -> bool:
        return False

    def exists(self, storage_key: str) -> bool:
        return False


@pytest.fixture
def ready_env(tmp_path: Any) -> Generator[None, None, None]:
    """Default healthy dependencies: migrated in-memory DB, available scanner, real local storage."""
    from backend.app.core.storage import LocalStorageBackend

    set_malware_scanner(FakeScanner(available=True))
    set_storage_backend(LocalStorageBackend(base_dir=tmp_path))
    yield
    set_malware_scanner(None)
    set_storage_backend(None)  # type: ignore[arg-type]


def _client_for(session: Session) -> TestClient:
    def _override_get_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    return client


def _memory_session(create_tables: bool = True) -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    if create_tables:
        Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _by_name(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {check["name"]: check for check in body["checks"]}


def teardown_module() -> None:
    app.dependency_overrides.clear()


def test_ready_when_all_dependencies_work(ready_env: None) -> None:
    client = _client_for(_memory_session())
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert list(body) == READINESS_KEYS
    assert body["status"] == "ready"
    assert [check["name"] for check in body["checks"]] == CHECK_NAMES
    for check in body["checks"]:
        assert list(check) == CHECK_KEYS
        assert check["ok"] is True, check
        assert check["detail"]


def test_not_ready_when_scanner_cannot_positively_scan() -> None:
    """The fail-closed quarantine fallback is safe, never ready."""
    from backend.app.core.storage import LocalStorageBackend
    import tempfile

    set_storage_backend(LocalStorageBackend(base_dir=tempfile.mkdtemp()))
    set_malware_scanner(QuarantineScanner())
    client = _client_for(_memory_session())
    response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    checks = _by_name(body)
    assert checks["malware_scanner"]["ok"] is False
    assert "quarantine" in checks["malware_scanner"]["detail"]
    assert checks["database"]["ok"] is True
    assert checks["storage"]["ok"] is True


def test_not_ready_when_database_unreachable() -> None:
    from backend.app.core.storage import LocalStorageBackend
    import tempfile

    set_malware_scanner(FakeScanner(available=True))
    set_storage_backend(LocalStorageBackend(base_dir=tempfile.mkdtemp()))
    broken_engine = create_engine("sqlite:////nonexistent-readonly-dir/db.sqlite")
    session = sessionmaker(bind=broken_engine)()
    client = _client_for(session)
    response = client.get("/health/ready")
    assert response.status_code == 503
    checks = _by_name(response.json())
    assert checks["database"]["ok"] is False
    assert checks["schema"]["ok"] is False
    assert "unreachable" in checks["schema"]["detail"]
    # Failure details must stay generic — no URLs, paths or credentials.
    assert "sqlite" not in checks["database"]["detail"]


def test_not_ready_when_schema_not_migrated() -> None:
    from backend.app.core.storage import LocalStorageBackend
    import tempfile

    set_malware_scanner(FakeScanner(available=True))
    set_storage_backend(LocalStorageBackend(base_dir=tempfile.mkdtemp()))
    client = _client_for(_memory_session(create_tables=False))
    response = client.get("/health/ready")
    assert response.status_code == 503
    checks = _by_name(response.json())
    assert checks["database"]["ok"] is True
    assert checks["schema"]["ok"] is False
    assert "processing_jobs" in checks["schema"]["detail"]


def test_not_ready_when_storage_is_not_writable() -> None:
    set_malware_scanner(FakeScanner(available=True))
    set_storage_backend(BrokenStorage())  # type: ignore[arg-type]
    client = _client_for(_memory_session())
    response = client.get("/health/ready")
    assert response.status_code == 503
    checks = _by_name(response.json())
    assert checks["storage"]["ok"] is False
    assert checks["database"]["ok"] is True


def test_quarantine_scanner_is_never_available() -> None:
    assert QuarantineScanner().is_available() is False


def test_clamav_scanner_without_host_is_never_available() -> None:
    scanner = ClamAVScanner(host=None)
    scanner.host = None
    assert scanner.is_available() is False
