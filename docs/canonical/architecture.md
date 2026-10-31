# Architecture — Existing Platform and Proposed Expansion

**Status:** Current implementation and target architecture are distinguished below. This file does not claim proposed modules already exist.

## Current system

- React 19/TypeScript/Vite client (`frontend/app`); FastAPI/Pydantic API (`backend/app`); SQLAlchemy 2 and Alembic; SQLite development/PostgreSQL deployment; private local storage abstraction; Celery/Redis worker with transactional outbox and eager dispatcher option. Manifests: `frontend/app/package.json`, `backend/requirements*.txt`, `render.yaml`, `docker-compose.integration.yml`.
- Authenticated application, document, validation, compliance, review, audit-package and consistency routers. Server-side RBAC/membership helpers are in `core/rbac.py`, `api/deps.py`. Not every legacy route is protected: `/api/v1/documents/analyze` and `/api/v1/institutions` are mounted directly in `main.py`; audit and resolve those separately before real institutional data is accepted.
- Current pipeline: institution/application → private document slot/version → scan and durable processing job → PDF text/OCR extraction → `ExtractedField` observations → application validation and rule evaluation → persisted run/check results/findings → human review actions/audit package. `ValidationRun` snapshots consumed version IDs, rule metadata, counts and limitations.
- Deterministic rule catalog/engine and durable rule verification/approval are implemented (`rule_catalog.py`, `services/rule_engine.py`, `RuleApprovalRecord`). Requirement coverage and applicability remain limited; the code catalogue is not a regulatory-publication repository. Current source research gates remain open.
- No LLM, RAG, vector database, task planner, or regulatory change ingestion/impact service is present in manifests/source.

## Capability audit summary

| Feature | Overall status | Reusable components | Missing boundary |
|---|---|---|---|
| Gap Analyzer | **PARTIAL** | Application/academic year; secure document versions; extraction; deterministic checks/rules; findings/runs; human review and audit. | Explicit requirements/applicability and evidence mappings; generalized cross-document analysis; verified source retrieval; LLM analysis; requirement-scoped dashboard. |
| Action Planner | **NOT IMPLEMENTED** | Finding links, review workflow/history, secure document intake, RBAC, audit events, worker/outbox. | Task persistence, assignments/deadlines, state machine, corrective-evidence review, notifications/escalations, revalidation-to-closure workflow. |
| Regulatory Change Impact | **NOT IMPLEMENTED** | Rule provenance/approval, source checksum fields, role `regulatory_director`, audit and background job infrastructure. | Source/publication/version/clause/change/dependency/impact records; ingestion, diffing, impact assessment UI/API and reassessment trigger. |

Feature evidence paths and test references are listed in `prd.md`. Existing review `resolved` or consistency `resolved` states do not mean an action task exists or that a requirement was revalidated.

## Target connected lifecycle

`Official source` → immutable `regulatory version` → `clause` → governed `requirement` → explicit `applicability` → existing institution/application `evidence versions` → `assessment` → shared `finding` → optional `corrective action` → new `evidence version` → new `assessment` → human resolution.

A regulatory change creates a reviewable impact case and may enqueue reassessment of affected requirement/application pairs. The reassessment uses the changed requirement only after source and interpretation approval. It creates a new run and never mutates prior run, finding, evidence, task, or regulatory version. Task creation is a user/reviewer action from an actionable confirmed finding; no automatic status changes on model output.

## Logical components and boundaries

1. **Source governance** (new): official source registry, original artifact, immutable publication versions and extracted clauses. Human verification and interpretation approval precede authoritative use. Reuse rule source provenance/approval patterns; do not duplicate their purpose without a migration plan.
2. **Requirement/applicability registry** (new or justified extension): stable requirement identity, immutable version, source clause references, applicability logic, expected evidence and test cases. Existing rules encode checks, not complete requirements or institutional applicability records.
3. **Evidence** (existing plus mapping): existing `Document`/`DocumentVersion` and `ExtractedField` remain canonical uploaded evidence/extraction records. Add explicit requirement↔evidence associations only after decisions on direct requirement IDs versus assessment-scoped mappings.
4. **Assessment** (extend existing): `ValidationRun` is canonical assessment execution/history; `Finding` is canonical finding. Extend only with justified requirement/source/evidence references, confidence and classification; do not create a second analyzer/findings table. Preserve existing endpoint contracts compatibly.
5. **Action management** (new): task aggregate references an existing finding and requirement; uses existing auth, evidence upload, audit and outbox. Task state is separate from finding review and compliance outcomes.
6. **Impact engine** (new): compare approved source versions, map clause dependencies, create human-reviewable impact cases, and emit idempotent reassessment work through outbox/Celery.
7. **Optional AI adapter** (new only after model decision): model-neutral interface for extraction assistance, cited retrieval, summarization and semantic diff. Deterministic rules remain authoritative for deterministic checks. No direct model-provider calls in domain logic.

## Proposed workflow and failure semantics

- Assessment inputs are frozen to exact document versions, requirement/rule/source versions and evaluation context. Idempotency key protects duplicate job dispatch. Failed/incomplete model or worker calls result in explicit queued/running/partial/failed states; never success-shaped empty results.
- Official source ingestion is idempotent by canonical source/version/checksum. Preserve original and extracted artifacts, and record OCR/parser/model version. Quarantine unverified or contradictory publications; never use them as active requirements.
- Impact review does not automatically mark documents invalid, open statutory failures, or change institution status. It can propose a new assessment for a human-authorized scope.
- Cross-tenant authorization is performed before retrieval and before queueing; worker payloads contain opaque authorized IDs and recheck tenant ownership at execution.

## API boundaries

Keep established `/api/v1/applications/{application_id}/...` routes for application documents, validation runs and findings/review. Existing governance is `/api/v1/compliance/rules...`; consistency CRUD is currently unversioned `/consistency`. New APIs should be versioned under `/api/v1`, follow current Pydantic response-model and `get_current_user`/membership/permission conventions, and be added to `docs/development/API_CONTRACT.md` before implementation. Proposed endpoint candidates and contracts are in `trd.md`; they are not live APIs.

## Security and operations

Use private storage, bounded streaming uploads, file validation/scanning and retention controls already present. Add department scope only after role/organizational ownership decision. Audit source verification, rule publication, impact decisions, task assignment/state/evidence/revalidation and permission-sensitive downloads. Avoid logging source/evidence contents or secrets. Celery/outbox retries must be bounded, idempotent, observable and preserve terminal failures. No service choice or performance target beyond current infrastructure is presumed.

## Feature 1 implementation status (2026-10-31)

This addendum supersedes earlier phase/audit statements in this document where they describe Feature 1 as unimplemented or blocked locally. The branch now contains an authenticated application-scoped Gap Analyzer using approved rule versions, the existing validation engine, Document Vault versions and extracted fields, persisted evidence mappings/review history, requirement assessments, findings and saved run history. The page supports loading and selecting saved runs, requirement findings and source citations, mapping extracted evidence, reviewer decisions, and authorized original-version download. Missing evidence is not presented as proof of statutory non-compliance.

Local verification: `python3 -m pytest backend/tests -q` → 497 passed, 21 skipped; frontend TypeScript/build passed; frontend tests 15 passed; lint exited 0 with existing warnings. Feature 1 still is not production-ready: Render is pinned to a stale branch without these routes, live PostgreSQL RLS inspection was blocked by IP allowlisting, and authenticated deployed workflow testing has not occurred. AI/RAG remains deferred pending provider/privacy approval; no institutional documents are sent to an external model. See `GAP_ANALYZER_FINAL_RELEASE_REPORT.md` and `GAP_ANALYZER_REDEPLOYMENT_HANDOFF.md`.
