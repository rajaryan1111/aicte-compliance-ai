# Technical Requirements and Proposed API Contracts

**Status:** The stack and current routes below are implemented; endpoints marked **proposed** are design candidates only and must be reviewed into `docs/development/API_CONTRACT.md` before implementation.

## Verified stack and API conventions

React 19 + TypeScript + Vite; FastAPI + Pydantic v2; SQLAlchemy 2 + Alembic; SQLite/PostgreSQL; private storage abstraction; Celery + Redis + transactional outbox, with eager dispatcher configuration available. OCR uses pdfplumber/Pillow/Tesseract adapter and regex normalization. No LLM, embeddings or vector store currently exist. Sources: dependency manifests, `render.yaml`, `docker-compose.integration.yml`, backend modules.

Routes use `/api/v1` for core application APIs. Application operations are nested under `/api/v1/applications/{application_id}`; reviews are nested under `/api/v1`; rule governance is `/api/v1/compliance/rules...`. The consistency API is an existing exception at `/consistency`. Current contracts use Pydantic response schemas, FastAPI validation/errors, JWT-authenticated `get_current_user`, membership/permission checks, and 404 concealment for cross-tenant records. Async document/validation operations use 202 and polling URLs. Preserve existing response semantics.

## Existing endpoint reuse

- `POST /api/v1/applications/{application_id}/documents`, list/get/version/download and processing status: secure versioned evidence intake.
- `POST /api/v1/applications/{application_id}/validate`; validation runs/report/findings under that application: assessment execution/history.
- `/api/v1/applications/{application_id}/findings`, review summary/queue/actions and run/finding details: human review.
- `/api/v1/compliance/rules`, `/rules/{rule_id}/verify-source`, `/approve`, `/history`: existing code-defined rule catalogue and governance.
- `/api/v1/compliance/...`: issuer verification, infrastructure review, institutional record comparisons, extracted field correction and retention operations.
- `/consistency`: persisted discrepancy record CRUD; does not run an analysis engine.
- `/api/v1/audit-packages...`: audit export and integrity verification.

The stateless `/api/v1/validate` still evaluates only caller-supplied lists/dates. `/api/v1/documents/analyze` and `/api/v1/institutions` in `main.py` are legacy direct routes and need auth/scope review before sensitive production use.

## Proposed API surface

All proposed paths are candidates under `/api/v1`; exact route naming and DTOs remain a contract decision. All endpoints are authenticated and tenant/permission scoped. Do not expose client-chosen institution authority.

| Operation (proposed candidate) | Request/response contract outline | Authorization |
|---|---|---|
| `GET /api/v1/applications/{id}/requirements` | Query academic/program context; return requirement ID/version, applicability state/reason, source clause/version, expected evidence, status. | application read; applicability edits separately permissioned |
| Extend `POST /api/v1/applications/{id}/validate` | Existing validation request gains reviewed requirement/context selectors and optional idempotency key; response continues to use the existing run/report contract, returning 202 + polling URL or the synchronous report. | application update |
| Extend `GET /api/v1/applications/{id}/validation-runs/{run_id}` and `.../findings` | Existing `ValidationRun`/`Finding` response adds requirement, source and multiple evidence references, confidence and limitations compatibly. | application/review read |
| Reuse existing `POST /api/v1/applications/{id}/validation-runs/{run_id}/findings/{finding_id}/actions` | Existing review action + decision/rationale/request ID append immutable review history; do not add a parallel finding-review operation. | review action; role policy |
| `POST /api/v1/applications/{id}/tasks` (proposed) | Body carries `finding_id`, title, description, expected evidence, priority, due date and optional owner/department; returns task with source links and initial state. Finding must belong to this authorized application; kept distinct from existing review-action route. | application update/action create |
| `GET/PATCH /api/v1/actions`, `.../{task_id}` | Scoped list filters; patch only legal fields/state transition with expected record version and rationale where needed. | assigned scope, department/institution permission |
| `POST /api/v1/actions/{task_id}/evidence` and `.../evidence/{id}/review` | Reference existing secure upload or create linked version; reviewer decision + reason. | task update/review permission |
| `POST /api/v1/actions/{task_id}/revalidations` | Idempotency key and target requirement; returns new validation run, never updates previous run. | review/action permission |
| `GET /api/v1/regulatory/sources`, `/documents/{id}/versions`, `/changes/{id}` | Source status and metadata, immutable versions/checksums, clause diff and review state. | regulatory read permission |
| `POST /api/v1/regulatory/documents` | Source reference and uploaded/approved artifact; returns queued ingestion job. Verification workflow required before authoritative use. | regulatory ingest permission |
| `POST /api/v1/regulatory/changes/{id}/impact-assessments` | Scope and idempotency key; return queued impact assessment and affected requirement/evidence references. | regulatory impact permission |
| `POST /api/v1/regulatory/changes/{id}/review-actions` | Approve/reject/correct applicability with rationale; may queue explicit reassessment. | regulatory review/approve permission |

### Shared data shapes

- `RequirementRef`: stable `requirement_id`, immutable `requirement_version`, clause/source-version reference, application applicability result and reason.
- `EvidenceRef`: document/version, extracted-field or record ID, page/location where available, observed and normalized values, confidence/engine where relevant, evidence role and limitations.
- `Finding`: existing ID/run/status compatibility plus requirement ref, category, description, missing/deficient detail, why it matters, source ref, `evidence_refs[]`, severity, confidence (nullable, separate), suggested correction and review state. No model-generated unsupported citation.
- `Task`: institution/application/finding/requirement refs, description, expected evidence, owner/department, priority, due date, controlled status, creator/timestamps and optimistic version.
- `RegulatoryVersion`: source, title, issuer, URL, publication/effective dates, retrieval time, checksum, verification state and predecessor. `ImpactAssessment` records old/new clauses, affected requirements/evidence, reason, classification, confidence, review outcome and actor.

These are proposed DTOs, not existing schemas. Error codes/status meanings, pagination and filtering must be added to the contract before coding; preserve FastAPI behavior elsewhere.

## Non-functional requirements

- Tenant/role enforcement at API, query, file download and worker execution boundaries; negative tests for cross-institution and (if added) cross-department access.
- Assessment reproducibility snapshots exact evidence, rule, requirement, source and model versions and evaluation date.
- Ingestion and analysis jobs are idempotent, bounded-retry, observable and explicit on partial/failure. Outbox messages commit with state; no fake success.
- Regulatory versions and submitted evidence are immutable; correction adds a version. Audit sensitive state changes.
- File/model calls have resource and timeout bounds. Minimize personal data; approve provider retention and region before use.
- Accessibility follows the frontend design standard. No numeric latency, accuracy or scale target is set until workload and deployment constraints are measured.

## Dependencies and open decisions

Resolve source and applicability gates; requirement/mapping schema; action roles and department model; notification provider/escalation policy; regulatory source intake/approval; optional model selection and evaluation/privacy; storage/version retention; dashboard metrics. Add no dependencies or migrations as part of this documentation-only update.

## Feature 1 implementation status (2026-10-31)

This addendum supersedes earlier phase/audit statements in this document where they describe Feature 1 as unimplemented or blocked locally. The branch now contains an authenticated application-scoped Gap Analyzer using approved rule versions, the existing validation engine, Document Vault versions and extracted fields, persisted evidence mappings/review history, requirement assessments, findings and saved run history. The page supports loading and selecting saved runs, requirement findings and source citations, mapping extracted evidence, reviewer decisions, and authorized original-version download. Missing evidence is not presented as proof of statutory non-compliance.

Local verification: `python3 -m pytest backend/tests -q` → 497 passed, 21 skipped; frontend TypeScript/build passed; frontend tests 15 passed; lint exited 0 with existing warnings. Feature 1 still is not production-ready: Render is pinned to a stale branch without these routes, live PostgreSQL RLS inspection was blocked by IP allowlisting, and authenticated deployed workflow testing has not occurred. AI/RAG remains deferred pending provider/privacy approval; no institutional documents are sent to an external model. See `GAP_ANALYZER_FINAL_RELEASE_REPORT.md` and `GAP_ANALYZER_REDEPLOYMENT_HANDOFF.md`.
