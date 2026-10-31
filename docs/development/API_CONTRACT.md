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

The base service routes below remain available. `/health` and legacy caller-supplied `/api/v1/validate` are unauthenticated; the latter only evaluates the caller-provided checklist and must not be treated as the institution-backed Gap Analyzer. Application, document, finding, and Gap Analyzer routes require authentication and enforce application membership/permissions.

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

## Consistency API — implemented

The persistence backend implements seven institution-scoped routes under `/consistency`.
This is separate from the frontend's existing historical-record comparison endpoint at
`/api/v1/compliance/applications/{application_id}/institutional-records`; that existing
response contract is unchanged. The consistency API records a check and its findings. It
does not claim to run an AI or statutory evaluation.

Every route requires a valid active database-backed user through `get_current_user`.
Read access uses the existing `application:read` permission; mutations use
`application:update`. Membership and role checks are applied to the parent application's
institution. Missing and cross-institution resources return the same `404` response;
same-institution roles without the required permission receive `403`. Writes and audit
events commit together.

| Method and path | Purpose | Permission |
|---|---|---|
| `POST /consistency/` | Create a check for an existing `application_id`; initial status is `pending`. | `application:update` |
| `GET /consistency/{check_id}` | Retrieve an authorized check. | `application:read` |
| `GET /consistency/` | List checks visible to the caller; optional `application_id` and `status_filter` query parameters further filter results. | `application:read` |
| `POST /consistency/findings` | Add a finding to an authorized check; check status becomes `discrepancy_detected`. | `application:update` |
| `GET /consistency/findings/{finding_id}` | Retrieve a finding through its parent check and application. | `application:read` |
| `GET /consistency/checks/{check_id}/findings` | List authorized findings; optional `severity_filter` and `resolved` filters. | `application:read` |
| `PATCH /consistency/findings/{finding_id}` | Update finding severity, description, evidence, or resolution. When all findings are resolved, the parent status becomes `resolved`. | `application:update` |

Create-check fields: `application_id`, `check_name`, optional `description` and
`related_field`. Create-finding fields: `consistency_check_id`, `field_name`, `value_1`,
`value_2`, `severity`, `description`, optional `confidence` in `[0, 1]` and optional
structured `evidence`. Finding updates accept one or more of `severity`, `description`,
`evidence` and `resolved`; parent IDs and compared values are immutable through this API.
Responses expose database IDs, parent IDs, persisted values, status/resolution and UTC
timestamps. Request models reject unknown fields.

The check's `pending` and `discrepancy_detected` states describe record workflow only.
They do not imply that a comparison engine ran or that an AICTE requirement was met.
Finding severity remains a string to match the existing persisted finding model, which
uses both validation (`error`/`warning`/`info`) and review (`high`/`medium`) labels.

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

The consistency API documented above requires a valid database-backed user and applies
institution membership and permission checks on every route. Other endpoints retain their
own authentication contracts; in particular, do not infer that one route's enforcement
applies to another. The following statements describe only the rule-gate endpoints in the
earlier proposal:

- The rule gate does not authenticate the reviewer identity; it remains a string assertion,
  not proof of identity.
- Do not expose institution-scoped data from any endpoint that lacks its own authentication
  and tenant-scoping checks.

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


## Gap Analyzer application routes (implemented)

These endpoints are mounted under `/api/v1/applications` and require a valid bearer token plus institution membership and the permission appropriate to the operation. Application IDs are resolved through the authenticated user’s memberships; document/version IDs are checked against that application. Cross-tenant or mismatched objects are concealed/rejected by the API.

- `GET /{application_id}/gap-requirements` — active, approved and source-verified requirement versions with applicability/source metadata.
- `GET /{application_id}/documents` — authorized Document Vault records/versions.
- `GET /{application_id}/documents/{document_id}/versions/{version_id}/fields` — extracted fields for the application-owned version.
- `GET /{application_id}/requirement-evidence-mappings` and `POST` on the same path — list/create mappings.
- `PATCH /{application_id}/requirement-evidence-mappings/{mapping_id}` — reviewer decision, sufficiency, and rationale/history.
- `POST /{application_id}/validate` — run the existing deterministic validation and save a new run.
- `GET /{application_id}/validation-runs?skip=&limit=` — paginated assessment history.
- `GET /{application_id}/gap-analysis?run_id=` — read saved requirement assessment/finding snapshot for a run (latest when omitted).
- `GET /{application_id}/validation-runs/{run_id}/requirement-assessments` and `PATCH /{application_id}/validation-runs/{run_id}/requirement-assessments/{assessment_id}` — read/review saved assessments.
- `GET /{application_id}/documents/{document_id}/versions/{version_id}/download` — authorized original document version.

The exact schemas and permission dependencies are in `backend/app/api/v1/gap_analyzer.py`, `documents.py`, and `validation.py`; this list is not a substitute for the generated OpenAPI schema. The deployed Render service inspected for this report is stale and does not expose these paths.
