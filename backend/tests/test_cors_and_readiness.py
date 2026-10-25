"""CORS preflight and readiness behaviour.

Why these exist
---------------
1. **CORS.** The frontend is a Render static site on a different origin from the
   API, so the browser sends an ``OPTIONS`` preflight before ``POST
   /api/v1/auth/token``. If that preflight is refused the browser reports a bare
   network error ("Cannot reach the API"), which is indistinguishable from the
   backend being down. The allowlist is therefore asserted here with a real
   preflight, not assumed from the presence of middleware.

2. **Readiness.** ``/health`` is a liveness probe and answers 200 for a process
   that cannot serve a single authenticated request. ``/health/ready`` inspects
   the database, the migration revision and the ``users`` table, so an empty
   SQLite deployment reports ``not_ready`` with a reason instead of "ok".
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.app.db.session as session_module
from backend.app.db.models import Base
from backend.app.main import _cors_origins, app

FRONTEND_ORIGIN = "https://aicte-compliance-frontend-preview.onrender.com"
# The UI is also served from Vercel; both deployed origins must be able to call
# the API, and a regression in either one shows up as the same opaque browser
# network error.
VERCEL_ORIGIN = "https://aicte-compliance-frontend.vercel.app"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("origin", [FRONTEND_ORIGIN, VERCEL_ORIGIN])
def test_preflight_for_each_deployed_frontend_origin_is_allowed(
    client: TestClient, origin: str
) -> None:
    response = client.options(
        "/api/v1/auth/token",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["access-control-allow-origin"] == origin
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


def test_preflight_allows_the_authorization_header(client: TestClient) -> None:
    """Bearer tokens are sent by the client, so the header must survive preflight."""
    response = client.options(
        "/api/v1/applications",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200, response.text
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_unknown_origin_gets_no_allow_origin_header(client: TestClient) -> None:
    """An arbitrary site must not be told it may read authenticated responses."""
    response = client.options(
        "/api/v1/auth/token",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.headers.get("access-control-allow-origin") is None
    assert response.status_code != 200


def test_actual_responses_carry_the_cors_header(client: TestClient) -> None:
    """Preflight is not enough: error responses must be readable by the browser.

    A rejected request whose 4xx body the frontend cannot read is reported as a
    network failure, which is exactly the confusing symptom this guards against.
    ``/api/v1/auth/me`` without a token returns 401 before any database access,
    so this assertion stays independent of database state.
    """
    ok_response = client.get("/health", headers={"Origin": FRONTEND_ORIGIN})
    unauthorized = client.get("/api/v1/auth/me", headers={"Origin": FRONTEND_ORIGIN})

    assert unauthorized.status_code == 401
    assert ok_response.headers.get("access-control-allow-origin") == FRONTEND_ORIGIN
    assert unauthorized.headers.get("access-control-allow-origin") == FRONTEND_ORIGIN


def test_origins_can_be_configured_without_a_redeploy_of_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS",
        "https://one.example/ , https://two.example",
    )

    assert _cors_origins() == ["https://one.example", "https://two.example"]


def test_wildcard_origins_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bearer-token API must never be readable by every site."""
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://ok.example,*")

    with pytest.raises(RuntimeError) as excinfo:
        _cors_origins()

    assert "exact origins" in str(excinfo.value)


def test_default_origins_are_used_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)

    assert FRONTEND_ORIGIN in _cors_origins()


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


def _sqlite_url(tmp_path, name: str = "ready.db") -> str:
    return f"sqlite:///{tmp_path / name}"


def test_ready_when_database_is_migrated(
    client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = _sqlite_url(tmp_path)
    engine = create_engine(url)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"
        )
        connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('test-revision')")
    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setenv("DATABASE_URL", url)

    response = client.get("/health/ready")
    body = response.json()

    assert response.status_code == 200, body
    assert body["status"] == "ready"
    assert body["database_reachable"] is True
    assert body["users_table_present"] is True
    assert body["migration_revision"] == "test-revision"
    assert body["reasons"] == []


def test_not_ready_when_tables_are_missing(
    client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """This is the "fresh SQLite container" state that broke login."""
    url = _sqlite_url(tmp_path, "empty.db")
    engine = create_engine(url)
    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setenv("DATABASE_URL", url)

    response = client.get("/health/ready")
    body = response.json()

    assert response.status_code == 503, body
    assert body["status"] == "not_ready"
    assert body["users_table_present"] is False
    assert any("users table missing" in reason for reason in body["reasons"])
    assert any("alembic_version" in reason for reason in body["reasons"])


def test_not_ready_when_the_database_is_unreachable(
    client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{tmp_path / 'missing-directory' / 'nope.db'}"
    monkeypatch.setattr(
        session_module,
        "SessionLocal",
        sessionmaker(bind=create_engine(url)),
    )
    monkeypatch.setenv("DATABASE_URL", url)

    response = client.get("/health/ready")
    body = response.json()

    assert response.status_code == 503, body
    assert body["database_reachable"] is False
    assert any("database unreachable" in reason for reason in body["reasons"])


def test_readiness_never_echoes_the_connection_string(
    client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = _sqlite_url(tmp_path, "secret-path-name.db")
    monkeypatch.setattr(
        session_module,
        "SessionLocal",
        sessionmaker(bind=create_engine(url)),
    )
    monkeypatch.setenv("DATABASE_URL", url)

    body = json.dumps(client.get("/health/ready").json())

    assert "secret-path-name" not in body
    assert "sqlite:///" not in body
