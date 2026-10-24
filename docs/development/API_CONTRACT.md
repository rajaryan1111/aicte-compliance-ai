# API and integration contract

**Contract version:** `0.1.0-draft`. The application itself reports version `0.3.1` in
`/openapi.json`; the two are not the same thing — see
[Versioning](#versioning-and-compatibility).

> ## Reconciliation addendum 2026-10-25 — read before the historical sections below
>
> The sections below this notice describe the **0.1.0-era surface** and are preserved as
> historical record. The implementation is far ahead of that snapshot. Everything in this
> addendum was verified by execution at integration-branch head `a1784a0` (PR #6) on
> 2026-10-25: fresh local boot (migrations applied, demo account seeded through
> `tools/demo/seed_demo.py`), real HTTP requests, OpenAPI dump, plus the full local pytest
> suite (456+ tests, 459 observed in CI at this head when the font-dependent engine test runs
> on Linux) and the live-infra CI job (real PostgreSQL + Redis, run `40129151372`).
>
> **Implemented HTTP surface (verified live).** `GET /openapi.json` publishes **25 paths /
> 29 operations**, OpenAPI 3.1.0:
>
> - `GET /health`, `GET /health/ready` (readiness: DB reachable, Alembic revision
>   `g7b8c9d0e1f2` reported, `users` table present; 503 with reasons otherwise)
> - `POST /api/v1/validate` (see below — unchanged semantics)
> - `POST /api/v1/auth/token`, `GET /api/v1/auth/me`
> - `POST|GET /api/v1/applications`, `GET|PATCH /api/v1/applications/{id}`
> - `POST|GET /api/v1/applications/{id}/documents`, document detail, version list,
>   per-version processing status, and `/download`
> - `POST /api/v1/applications/{id}/validate`, validation-run list/detail, findings list/detail,
>   `GET /api/v1/applications/{id}/findings`, `GET /api/v1/reviews/queue`,
>   `POST .../findings/{fid}/actions`, review summary
> - audit packages: create/list/detail/`PATCH-style` download + `POST /api/v1/audit-packages/verify`
>
> **Authentication is enforced.** Reproduced live this session: `POST /api/v1/auth/token` with
> the seeded credentials → 177-character JWT; `GET /api/v1/applications` with no token → **401**;
> with `Bearer garbage` → **401**. The assumption section below ("None are implemented",
> "every endpoint is anonymous") is historical and wrong today.
>
> **Tenant isolation / RBAC / persistence are enforced and tested** with real PostgreSQL in the
> CI integration job (`test_cross_institution_access_denial`,
> `test_postgres_multi_tenant_isolation`, RBAC refusal tests, rollback-guarantee tests).
>
> **The `/api/v1/validate` description below is still accurate** and its semantics have not
> drifted: it remains `caller_supplied_checklist_only`, returns
> `preliminary_checks_passed|attention_required`, uses no AICTE rule set, and was reproduced
> this session (`{"status":"attention_required",...}` with a missing document).
>
> **Upload/scanner processing** lives on `POST /api/v1/applications/{id}/documents` → extraction
> via a processing job; a without-verdict upload fails closed (`SCAN_UNAVAILABLE`,
> `retry_wait`) and never reaches OCR — verified live on the branch (fail-closed e2e).
>
> **Frontend consumers** must use the runtime contract, not this document. The frontend
> `api.ts` client's 9 captured fixture cases replay OK against the live API
> (`frontend/tools/verify_fixtures.py` — re-run this session).
>
> **Not implemented to date (unchanged, still true):** rate limiting, a stable application
> error envelope (4xx bodies remain framework-format; treat as opaque), public unauthenticated
> upload/OCR HTTP endpoints, psycopg-v3 dial support (declared DBAPI is pinned psycopg2), and
> public-documents rules routes. Remaining known limits: deployed ClamAV daemon absent (owner
> provisioning), durable deployed storage pending a persistent disk, retention/deletion
> controls not implemented.

Every item below is labelled:

- **implemented** — exists in code and has tests; the label cites the file and the
  behaviour was observed by executing the application.
- **proposed** — designed but not agreed and not implemented. Do not build against it.
- **blocked** — cannot be built until a named gate is passed.

The implementation is the source of truth; this document is the agreement around it. If
they disagree, the difference is a defect in the contract — report it, do not pick one.

## Implemented HTTP surface

Verified by starting `backend.app.main:app` and calling the endpoints. Both routes are
unauthenticated, which is acceptable only because no user data is stored anywhere.

### `GET /health` — implemented

```http
GET /health
200 {"status": "ok", "service": "aicte-compliance-assistant"}
```

`backend/app/main.py:65`. No side effects, no input.

### `POST /api/v1/validate` — implemented

`backend/app/main.py:73`. Compares caller-supplied lists; it loads no AICTE checklist and
no rule set.

**Request body** (`ValidationRequest`, `backend/app/main.py:29`)

| Field | Type | Rules | Required |
|---|---|---|---|
| `institution_id` | string | 1–100 chars, trimmed, must not be blank | yes |
| `application_type` | enum | `eoa` \| `new_program` \| `intake_change` | yes |
| `required_documents` | string[] | ≥ 1 item; non-blank; unique after trimming | yes |
| `submitted_documents` | string[] | non-blank; unique after trimming | no (default `[]`) |
| `expiry_dates` | object<string, `YYYY-MM-DD`> | keys trimmed; duplicate keys rejected | no (default `{}`) |

**Response body** — 200

```json
{
  "institution_id": "string",
  "application_type": "eoa",
  "status": "attention_required | preliminary_checks_passed",
  "validation_scope": "caller_supplied_checklist_only",
  "missing_documents": ["string"],
  "expired_documents": ["string"],
  "findings": [
    {
      "code": "MISSING_DOCUMENT | DOCUMENT_EXPIRED",
      "document_type": "string",
      "message": "string",
      "evidence": {"...": "code-specific"}
    }
  ],
  "checked_at": "ISO-8601 with UTC offset",
  "source": "synthetic_demo_input",
  "notice": "string"
}
```

Evidence shapes:

- `MISSING_DOCUMENT` → `{"source": "submitted_document_list", "observed": "not_submitted"}`
- `DOCUMENT_EXPIRED` → `{"source": "synthetic_demo_input", "expiry_date": "YYYY-MM-DD", "evaluation_date": "YYYY-MM-DD"}`

**Response models — implemented.** Since this version the endpoints declare Pydantic
response models (`HealthResponse`, `ValidationResponse`, `Finding` in
`backend/app/main.py`), so the schema is enforced at runtime and published in
`/openapi.json`. Key order in the JSON above is the field order in `ValidationResponse`
and is part of what consumers see.

Backward compatibility was verified, not assumed: fixtures captured **before** the models
were added (`frontend/fixtures/*.json`) still replay byte-identically against the running
app (`python frontend/tools/verify_fixtures.py`), and `ValidationResponse.model_validate(body)`
round-trips. Contract tests: `backend/tests/test_api_contract.py`.

**Semantics that must not drift**

- `preliminary_checks_passed` means only that the supplied lists agree. It is not
  compliance, eligibility or authenticity.
- Expiry uses the server's UTC date at request time, not a caller-supplied date.
- `validation_scope` is always `caller_supplied_checklist_only` on this endpoint.

### Error format — implemented (framework default), custom envelope **proposed**

Observed: `422` with FastAPI's `{"detail": [{"type", "loc", "msg", "input", "ctx"}]}`.

Three shapes are pinned by tests and fixtures:

| Trigger | `detail[].type` | Example `loc` |
|---|---|---|
| required field absent | `missing` | `["body","application_type"]` |
| wrong enum value | `literal_error` | `["body","application_type"]` |
| blank id, duplicate/blank document names, list shorter than 1 | `value_error` | `["body","required_documents"]` |

`detail[].input` echoes the offending value, so **never log an error body verbatim** once
real institution data is accepted — it is caller data. Today only synthetic data is used.

A stable application error envelope is **proposed** and needs agreement before the
frontend codes against error bodies:

```json
{"error": {"code": "STRING_CODE", "message": "human readable", "field": "optional.path"}}
```

Until that is agreed, the frontend must treat 4xx bodies as opaque and display the
`status_code` plus a generic message. Do not parse `detail[].msg` for logic; map
`detail[].loc` to form fields only if you also handle an unknown `loc` gracefully.

There is **no** authentication, rate limiting, request-size limit or CORS configuration on
either endpoint. That is acceptable only because the service evaluates caller-supplied
JSON and stores nothing — it does not make the endpoints safe to expose.

## Implemented OCR contract (Python, not HTTP)

`backend/app/ocr_adapter.py` defines the boundary; there is **no HTTP endpoint** and no
upload route.

| Type | Fields | Notes |
|---|---|---|
| `OCRField` | `value: str \| None`, `confidence: float \| None`, `page_number: int \| None`, `evidence_text: str \| None` | confidence constrained to `0.0–1.0`, page ≥ 1, value non-blank |
| `OCRDocumentResult` | `fields: dict[str, OCRField]`, `engine: str`, `engine_version`, `source_sha256`, `warnings`, `requires_human_review` | `requires_human_review` cannot be false; `source_sha256` must be a 64-char hex digest |

Entry point: `process_institution_document(image_bytes, engine) -> OCRDocumentResult`
(`backend/app/ocr_pipeline.py`).

Engine boundary (`TesseractOCRAdapter.recognize`): `text` and `conf` are **required**
columns and must be equal-length sequences; `page_num` / `line_num` are optional but must
align with `text` when present; structural violations raise `RuntimeError("Tesseract OCR
returned malformed data; …")`; per-word confidence outside a finite 0–100 percentage is
dropped, never clamped. Contract tests: `backend/tests/test_ocr_adapter_engine.py`.

Limits: 10 MiB bytes, 30 MP, JPEG/PNG/TIFF/WEBP, 100,000-character aggregate text.
Not implemented: PDF input, multi-frame coverage (first frame only, warned), bounding boxes.

## Implemented rule-activation gate (Python, not HTTP)

`backend/app/rule_catalog.py`. `RuleRegistry.activate()` is the only transition to
`ACTIVE` and requires verified source provenance, an approved approval record, an
`effective_from` date not preceding the publication date, and all four test categories.

- **No rule is defined or active** in this repository, and there is no evaluator.
- `reviewer_id` / `verified_by` are recorded strings, **not authenticated identities**.
- State is in-memory: no durability, no audit trail, no concurrency handling.
- Supersession and retirement are **not implemented**.

## Proposed endpoints — do not build against these

| Endpoint | Status | Blocker |
|---|---|---|
| `POST /api/v1/documents` (upload) | **blocked** | authentication, RBAC, tenant isolation, private storage, malware scanning, retention |
| `GET /api/v1/applications/{id}` | blocked | no persistence layer |
| `POST /api/v1/ocr` (server-side OCR) | blocked | same as upload, plus resource limits and job isolation |
| `GET /api/v1/rules` | blocked | no verified rule source; publishing an unverified rule list is prohibited |
| Error envelope (above) | proposed | owner agreement; no implementation |
| Evidence/provenance payload for findings | proposed | owner agreement; current `evidence` is code-specific |
| OpenAPI-derived frontend client | proposed | frontend framework not chosen |

Rules for anything marked blocked: adding the route without the gate is a security
regression, not progress. A stub returning fake data is prohibited — it implies
functionality that does not exist.

## Authentication assumptions

**None are implemented.** There is no auth dependency, no session, no token, no role.
Therefore:

- Every endpoint is anonymous. No endpoint may return institution-scoped data until
  authentication and tenant scoping exist.
- The frontend must not implement a login screen that implies server-side enforcement.
- The rule gate's reviewer identity is a string assertion, never proof.

## Versioning and compatibility

- Path version is `v1`; there is no `v2` and no deprecation policy yet.
- Adding an optional response field is backwards compatible. Removing or retyping a field,
  changing a `status` value, or changing the meaning of an existing value requires a
  contract change PR reviewed by all three workstreams.
- The frontend must tolerate unknown extra fields.

## Synthetic examples

All example payloads in tests and docs use synthetic institution names
(`SYNTH-…`, "Example Technical Institute"). No real institutional or personal data may be
added to fixtures. `backend/tests/validation`-related tests are the reference examples.
