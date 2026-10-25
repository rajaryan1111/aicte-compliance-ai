from datetime import date, datetime, timezone
from typing import Literal

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from backend.app.core.scanner import get_malware_scanner
from backend.app.core.storage import get_storage_backend
from backend.app.db.session import get_db

app = FastAPI(
    title="AICTE Compliance Assistant",
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


class ReadinessCheck(BaseModel):
    """One dependency probe inside ``GET /health/ready``."""

    name: Literal["database", "schema", "malware_scanner", "storage"]
    ok: bool
    detail: str


class ReadinessResponse(BaseModel):
    """Response of ``GET /health/ready`` — strict deployment readiness.

    ``ready`` means every gate the document pipeline depends on actually
    works: the database answers queries, the intake schema is migrated, a
    real malware engine can positively scan (the fail-closed quarantine
    fallback is *not* ready — it is safe but cannot process anything), and
    private storage accepts writes. HTTP 200 when ready, 503 otherwise.
    Details name the failing component only; they never echo configuration,
    URLs or credentials.
    """

    status: Literal["ready", "not_ready"]
    checks: list[ReadinessCheck]


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


# Tables created by the newest intake migrations. If these are missing the
# database is reachable but the schema was never migrated to head.
_READINESS_TABLES = ("processing_jobs", "outbox_messages")


def _probe_database(db: Session) -> ReadinessCheck:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        return ReadinessCheck(
            name="database", ok=False, detail=f"query failed ({type(exc).__name__})"
        )
    return ReadinessCheck(name="database", ok=True, detail="connection ok")


def _probe_schema(db: Session) -> ReadinessCheck:
    try:
        existing = set(inspect(db.get_bind()).get_table_names())
    except Exception as exc:
        return ReadinessCheck(
            name="schema", ok=False, detail=f"inspection failed ({type(exc).__name__})"
        )
    missing = [name for name in _READINESS_TABLES if name not in existing]
    if missing:
        return ReadinessCheck(
            name="schema",
            ok=False,
            detail=f"migrations not applied; missing tables: {', '.join(missing)}",
        )
    return ReadinessCheck(name="schema", ok=True, detail="intake tables present")


def _probe_scanner() -> ReadinessCheck:
    try:
        available = bool(get_malware_scanner().is_available())
    except Exception as exc:
        return ReadinessCheck(
            name="malware_scanner", ok=False, detail=f"probe failed ({type(exc).__name__})"
        )
    if available:
        return ReadinessCheck(name="malware_scanner", ok=True, detail="scanning engine answering")
    return ReadinessCheck(
        name="malware_scanner",
        ok=False,
        detail="no usable scanning engine (fail-closed quarantine active)",
    )


def _probe_storage() -> ReadinessCheck:
    probe_key = "health/readiness-probe"
    try:
        storage = get_storage_backend()
        storage.put(probe_key, b"readiness-probe")
        storage.delete(probe_key)
    except Exception as exc:
        return ReadinessCheck(
            name="storage", ok=False, detail=f"write probe failed ({type(exc).__name__})"
        )
    return ReadinessCheck(name="storage", ok=True, detail="write probe ok")


@app.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
def readiness_check(db: Session = Depends(get_db)) -> JSONResponse:
    """Strict readiness: 200 only when every processing dependency is usable.

    Liveness stays on ``GET /health`` (fixed 200). Use this endpoint for
    deployment verification and monitoring; a 503 here means the instance
    cannot safely process documents even though the process is up.
    """
    db_check = _probe_database(db)
    if db_check.ok:
        schema_check = _probe_schema(db)
    else:
        schema_check = ReadinessCheck(
            name="schema", ok=False, detail="skipped: database unreachable"
        )
    checks = [db_check, schema_check, _probe_scanner(), _probe_storage()]
    ready = all(check.ok for check in checks)
    payload = ReadinessResponse(
        status="ready" if ready else "not_ready",
        checks=checks,
    )
    return JSONResponse(
        status_code=200 if ready else 503,
        content=payload.model_dump(),
    )


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


