import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Apply database migrations in a deployed environment, then serve.

    A deploy that starts against an unmigrated database serves 500s with
    "no such table: users" while ``/health`` reports "ok". Migrating here (or
    failing loudly) removes that failure mode without depending on a dashboard
    setting nobody configured. Local runs and tests are unaffected.
    """
    from backend.app.db.migrations import migrate_if_deployed

    migrate_if_deployed()
    yield


app = FastAPI(
    title="AICTE Compliance Assistant",
    lifespan=lifespan,
    description=(
        "Prototype for application validation and compliance assistance. "
        "Results are advisory and use synthetic demonstration data."
    ),
    version="0.3.1",
)


def _clean_document_names(value: object) -> object:
    """Normalize document identifiers and reject blanks/duplicates."""
    if not isinstance(value, list):
        return value
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError("Document names must be non-empty strings.")
    cleaned = [item.strip() for item in value]
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("Document names must not contain duplicates.")
    return cleaned


class ValidationRequest(BaseModel):
    institution_id: str = Field(min_length=1, max_length=100)
    application_type: Literal["eoa", "new_program", "intake_change"]
    required_documents: list[str] = Field(min_length=1)
    submitted_documents: list[str] = Field(default_factory=list)
    expiry_dates: dict[str, date] = Field(default_factory=dict)

    @field_validator("institution_id")
    @classmethod
    def normalize_institution_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("institution_id must not be blank.")
        return value

    @field_validator("required_documents", "submitted_documents", mode="before")
    @classmethod
    def normalize_document_names(cls, value: object) -> object:
        return _clean_document_names(value)

    @field_validator("expiry_dates", mode="before")
    @classmethod
    def normalize_expiry_date_keys(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized: dict[object, object] = {}
        for key, expiry in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Expiry-date document names must be non-empty strings.")
            clean_key = key.strip()
            if clean_key in normalized:
                raise ValueError("Expiry-date document names must not contain duplicates.")
            normalized[clean_key] = expiry
        return normalized


class HealthResponse(BaseModel):
    """Response of ``GET /health``. Both values are fixed."""

    status: Literal["ok"]
    service: Literal["aicte-compliance-assistant"]


class Finding(BaseModel):
    """One preliminary-check finding.

    ``evidence`` is code-specific: ``MISSING_DOCUMENT`` carries
    ``{source, observed}``; ``DOCUMENT_EXPIRED`` carries
    ``{source, expiry_date, evaluation_date}``.
    """

    code: Literal["MISSING_DOCUMENT", "DOCUMENT_EXPIRED"]
    document_type: str
    message: str
    evidence: dict[str, str]


class ValidationResponse(BaseModel):
    """Response of ``POST /api/v1/validate`` — a preliminary checklist result.

    ``preliminary_checks_passed`` means the caller-supplied document lists agree.
    It is **not** a compliance, eligibility or authenticity finding: this service
    loads no AICTE checklist and no rule set.
    """

    institution_id: str
    application_type: Literal["eoa", "new_program", "intake_change"]
    status: Literal["attention_required", "preliminary_checks_passed"]
    validation_scope: Literal["caller_supplied_checklist_only"]
    missing_documents: list[str]
    expired_documents: list[str]
    findings: list[Finding]
    checked_at: str
    source: Literal["synthetic_demo_input"]
    notice: str


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="aicte-compliance-assistant")


# ---------------------------------------------------------------------------
# Readiness: the probe that would have caught the "no such table: users" deploy
# ---------------------------------------------------------------------------
# ``/health`` is a liveness probe and stays deliberately trivial -- it answers
# 200 as soon as the process serves HTTP, which is why a backend running against
# an empty SQLite file reported "ok" while every login failed. This endpoint
# inspects the database instead: reachable, migrated, and actually carrying the
# tables authentication needs.
#
# It reports only shapes and names (engine family, revision, booleans). It never
# echoes DATABASE_URL, hostnames, usernames or passwords.
@app.get("/health/ready", include_in_schema=True)
def readiness_check(response: Response) -> dict[str, object]:
    """Report whether the API can actually serve authenticated requests."""
    from sqlalchemy import text as _sql

    from backend.app.db.session import SessionLocal, get_database_url, is_deployed_environment

    url = get_database_url()
    engine_family = ("sqlite" if url.startswith("sqlite") else "postgresql") if url else "unknown"
    details: dict[str, object] = {
        "service": "aicte-compliance-assistant",
        "engine": engine_family,
        "deployed_environment": is_deployed_environment(),
        "database_reachable": False,
        "migration_revision": None,
        "users_table_present": False,
    }
    reasons: list[str] = []

    try:
        db = SessionLocal()
        try:
            db.execute(_sql("SELECT 1"))
            details["database_reachable"] = True
            try:
                revision = db.execute(_sql("SELECT version_num FROM alembic_version")).scalar()
                details["migration_revision"] = revision
            except Exception:
                reasons.append("alembic_version table missing: migrations have not been applied")
            try:
                db.execute(_sql("SELECT 1 FROM users LIMIT 1"))
                details["users_table_present"] = True
            except Exception:
                reasons.append("users table missing: authentication cannot work")
        finally:
            db.close()
    except Exception as exc:  # connection failure, wrong credentials, DB down
        reasons.append(f"database unreachable ({type(exc).__name__})")

    if engine_family == "sqlite" and details["deployed_environment"]:
        reasons.append("SQLite is in use on a deployed service: data will not persist")

    ready = not reasons
    response.status_code = 200 if ready else 503
    details["status"] = "ready" if ready else "not_ready"
    details["reasons"] = reasons
    details["notice"] = (
        "Readiness only. It reports database, migration and table presence; "
        "it does not certify compliance, document authenticity or data correctness."
    )
    return details


@app.post("/api/v1/validate", response_model=ValidationResponse)
def validate_application(request: ValidationRequest) -> ValidationResponse:
    required = set(request.required_documents)
    submitted = set(request.submitted_documents)

    missing = sorted(required - submitted)
    today = datetime.now(timezone.utc).date()

    expired = sorted(
        document
        for document in submitted
        if document in request.expiry_dates
        and request.expiry_dates[document] < today
    )

    findings = []

    for document in missing:
        findings.append({
            "code": "MISSING_DOCUMENT",
            "document_type": document,
            "message": f"Required document '{document}' was not submitted.",
            "evidence": {
                "source": "submitted_document_list",
                "observed": "not_submitted",
            },
        })

    for document in expired:
        expiry_date = request.expiry_dates[document]
        findings.append({
            "code": "DOCUMENT_EXPIRED",
            "document_type": document,
            "message": (
                f"Document expiry date {expiry_date.isoformat()} "
                f"is before the evaluation date {today.isoformat()}."
            ),
            "evidence": {
                "source": "synthetic_demo_input",
                "expiry_date": expiry_date.isoformat(),
                "evaluation_date": today.isoformat(),
            },
        })

    needs_attention = bool(missing or expired)

    return ValidationResponse(
        institution_id=request.institution_id,
        application_type=request.application_type,
        status=(
            "attention_required" if needs_attention else "preliminary_checks_passed"
        ),
        validation_scope="caller_supplied_checklist_only",
        missing_documents=missing,
        expired_documents=expired,
        findings=[Finding(**finding) for finding in findings],
        checked_at=datetime.now(timezone.utc).isoformat(),
        source="synthetic_demo_input",
        notice=(
            "Preliminary validation only. This endpoint evaluates only the "
            "checklist and dates supplied in the request; it does not load an "
            "authoritative AICTE ruleset. A passing result does not establish "
            "regulatory compliance or document authenticity. Expiry checks "
            "use supplied dates and require appropriate review."
        ),
    )


# Mount versioned API routes
from backend.app.api.v1.applications import router as applications_router  # noqa: E402
from backend.app.api.v1.audit_packages import router as audit_packages_router  # noqa: E402
from backend.app.api.v1.auth import router as auth_router  # noqa: E402
from backend.app.api.v1.documents import router as documents_router  # noqa: E402
from backend.app.api.v1.reviews import router as reviews_router  # noqa: E402
from backend.app.api.v1.validation import router as validation_router  # noqa: E402

app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(applications_router, prefix="/api/v1/applications", tags=["applications"])
app.include_router(documents_router, prefix="/api/v1/applications", tags=["documents"])
app.include_router(validation_router, prefix="/api/v1/applications", tags=["validation"])
app.include_router(reviews_router, prefix="/api/v1", tags=["reviews"])
app.include_router(audit_packages_router, prefix="/api/v1", tags=["audit-packages"])




# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# The frontend is a separate static-site origin, so the browser sends a
# preflight OPTIONS before POSTing JSON to /api/v1/auth/token. Without an
# allowlist entry that preflight fails and the browser reports a bare network
# error -- the failure mode that looked like "the backend is down".
#
# The list is configurable because hard-coding one hostname means a renamed or
# second preview URL is a code change and a redeploy. Credentials are disabled:
# this API authenticates with a bearer token in the Authorization header, not
# with cookies, so no wildcard-with-credentials footgun is needed or allowed.
_DEFAULT_CORS_ORIGINS = (
    "https://aicte-compliance-frontend-preview.onrender.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _cors_origins() -> list[str]:
    """Resolve allowed browser origins from CORS_ALLOW_ORIGINS, or the defaults."""
    raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if not raw:
        return list(_DEFAULT_CORS_ORIGINS)
    origins = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
    if "*" in origins:
        raise RuntimeError(
            "CORS_ALLOW_ORIGINS must list exact origins. '*' is refused: with a "
            "bearer-token API any site could then read authenticated responses."
        )
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Prefer"],
)


@app.get("/", include_in_schema=False)
def service_landing_page() -> dict[str, object]:
    """Expose a small service index instead of a confusing root 404."""
    return {
        "service": "AICTE Compliance Assistant",
        "status": "prototype",
        "docs": "/docs",
        "health": "/health",
        "frontend": "https://aicte-compliance-frontend-preview.onrender.com",
        "notice": (
            "Advisory prototype only. Results do not establish AICTE compliance "
            "or document authenticity. Use synthetic demo data only."
        ),
    }
