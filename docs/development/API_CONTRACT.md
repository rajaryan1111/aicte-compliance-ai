# API and integration contract

**Contract version:** `0.1.0-draft`. The application itself reports version `0.3.1` in
`/openapi.json`; the two are not the same thing — see
[Versioning](#versioning-and-compatibility).

Every item below is labelled:

- **implemented** — exists in code and has tests; the label cites the file and the
  behaviour was observed by executing the application.
- **proposed** — designed but not agreed and not implemented. Do not build against it.
- **blocked** — cannot be built until a named gate is passed.

The implementation is the source of truth; this document is the agreement around it. If
they disagree, the difference is a defect in the contract — report it, do not pick one.

## Implemented HTTP surface

Verified by starting `backend.app.main:app` and calling the endpoints. These routes are
unauthenticated, which is acceptable only because no user data is stored anywhere.

### `GET /health` — implemented

```http
GET /health
200 {"status": "ok", "service": "aicte-compliance-assistant"}
```

`HealthResponse` / `health_check` in `backend/app/main.py`. No side effects, no input.
This is the **liveness** check (fixed 200); strict dependency readiness is
`GET /health/ready` below.

### `GET /health/ready` — implemented (2026-10-25)

```http
GET /health/ready
200 {"status": "ready", "checks": [{"name": "...", "ok": true, "detail": "..."}, ...]}
503 {"status": "not_ready", "checks": [...]}
```

`ReadinessResponse` / `readiness_check` in `backend/app/main.py`; pinned by
`backend/tests/test_readiness.py`. Four checks, always in this order:
`database` (answers `SELECT 1`), `schema` (intake tables present — migrations
applied), `malware_scanner` (a real engine answers `zPING`; the fail-closed
quarantine fallback is **not** ready), `storage` (private storage accepts a
write probe). HTTP 200 only when every check passes, 503 otherwise; `detail`
names the component and error class only — never URLs, paths or credentials.
Use this endpoint for deployment verification and monitoring; `GET /health`
remains the restart-safe liveness probe.

### `POST /api/v1/validate` — implemented

`validate_application` in `backend/app/main.py`. Compares caller-supplied lists; it loads no AICTE checklist and
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

## Reconciliation addendum (2026-10-25)

The "Proposed endpoints" table below is **historical** (it describes the state
before the backend integration work landed on `main`). Since then the
document-application surface has been implemented with authentication, RBAC,
institution tenant isolation, private storage, a fail-closed malware scan gate
and durable jobs — the table's listed blockers except **retention**, which
remains unimplemented and is still a production blocker:

- Document upload, document/version/processing-status reads — implemented under
  `/api/v1/applications/{application_id}/documents` (not `POST /api/v1/documents`)
  with the nested `DocumentUploadResponse` shape (`document`, `version`, `job`,
  `polling_url`); see `backend/app/api/v1/documents.py` and
  `backend/tests/test_document_upload_api.py`.
- Application CRUD and application-scoped validation/review/audit-package
  routes — implemented under `/api/v1/applications/...`; see
  `backend/app/api/v1/` and the corresponding unit suites.
- `POST /api/v1/rules` and any rule evaluator — **still blocked** exactly as
  described below (no verified rule source; no evaluator exists).
- Server-side OCR as a standalone `POST /api/v1/ocr` route — **not implemented**;
  extraction runs inside the document processing pipeline only.

The authoritative request/response shapes for the implemented surface are the
Pydantic schemas in `backend/app/schemas/` as reflected by the live
`/openapi.json` of the running application and the unit tests that pin them.
This addendum does not revise the historical table; when the two disagree for
the implemented routes, the code + schemas above are the source of truth.

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
