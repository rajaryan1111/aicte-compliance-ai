# Implementation Phases — Existing Platform Expansion

**Status:** Proposed roadmap. This task updates documentation only. Do not start Phase 1 without explicit approval after this specification is reviewed.

## Phase 0 — Close source and product gates

**Dependencies:** official source register and product owner. **Deliverables:** retrieve/reconcile the outstanding circular/amendment and applicability questions recorded in `docs/research/`; define approved sources, requirement authority, institution/program/academic-year context and review roles; decide whether a model provider is needed and its privacy terms. **Likely areas:** `docs/research/*`, rule catalogue seed definitions. **DB/API/UI:** none. **Tests:** evidence checks/source review only. **Risks:** unverified current rules create incorrect findings. **Done:** no target requirement is activated without provenance, applicability, interpretation approval and tests; unresolved claims remain explicitly unavailable.

## Phase 1 — Shared requirement/evidence foundation

**Dependencies:** Phase 0 and data-model ADR. **Deliverables:** canonical requirement/version/applicability representation; many-to-many evidence mapping; finding references to requirement/source and multiple evidence observations; migration plan that preserves existing `DocumentVersion`, `ValidationRun`, `Finding`, `RuleApprovalRecord`. **Likely areas:** `backend/app/db/models.py`, repositories/services, Alembic, Pydantic schemas, API contract and evidence detail components. **API:** versioned requirement/applicability and mapping operations, exact schemas to be approved first. **Tests:** migrations from clean and prior DB, tenant isolation, immutable history, mapping cardinality, source gate. **Risks:** duplicating rule catalogue or findings. **Done:** source of truth per concept documented; no parallel evidence store; old clients still work.

## Phase 2 — Intelligent Compliance Gap Analyzer

**Dependencies:** approved requirement/applicability and evidence mapping. **Deliverables:** requirement selection/explanation, evidence retrieval, deterministic validation extension, optional model-neutral cited analysis only if approved, finding review, new assessment/revalidation and backend-backed summary. **Likely areas:** validation orchestration/rule engine, finding schema/service/review API, frontend app routes and reviewer components. **Migrations:** justified requirement/evidence/assessment references only. **Tests:** applicability boundaries, missing/incomplete/expired/invalid/inconsistent states, source/evidence citation, low confidence, reproducibility, AI failure, RAG citation validity and cross-tenant negatives. **Risk:** confusing absence/uncertainty with non-compliance. **Done:** all Feature 1 acceptance criteria in `prd.md` pass; human review and prior run history remain intact.

## Phase 3 — Compliance Action Planner

**Dependencies:** actionable reviewed finding and Phase 1 links. **Deliverables:** persistent action records, assignment/department scope decision, due dates/priorities, legal transition service, comments/history, corrective evidence via existing upload, reviewer evidence decision and closure after revalidation. Reuse current outbox/worker; notification channels remain a separate decision. **Likely areas:** new action service/repository/schema/router/migration, frontend routes/components, audit hooks. **Tests:** transition table, unauthorized assignment/reassignment, tenant/department boundary, due-date behavior, evidence rejection/retry, revalidation history, concurrency/idempotency and audit. **Risk:** coupling task status to finding/compliance status. **Done:** all Feature 2 acceptance criteria; no automatic AI task closure or permission change.

## Phase 4 — Regulatory Change Impact Analyzer

**Dependencies:** source authority and version/applicability decisions plus requirement graph. **Deliverables:** source registry, immutable publication versions/checksums, clause records, idempotent ingestion and text/OCR extraction, exact/structured comparison, optional reviewed semantic comparison, impact case and human approval. **Likely areas:** regulatory source/ingestion services and worker jobs, persistence/API/UI, dashboards/reports. **Tests:** checksum/idempotency, source spoofing, version immutability, clause alignment, editorial/substantive test set, human overrides, tenant scope, import failures and provenance reports. **Risks:** false impacts, outdated or unverified sources, scraper/legal constraints. **Done:** all Feature 3 acceptance criteria; no silent compliance/evidence changes.

## Phase 5 — End-to-end lifecycle and operational readiness

**Dependencies:** Phases 1–4. **Deliverables:** approved regulatory change can queue scoped reassessments; new findings can be reviewed and converted to actions; new evidence results in a new assessment and human closure; historical reports and metrics are complete. **Likely areas:** outbox/Celery tasks, orchestration, UI workflow, audit package/report. **Tests:** full synthetic journey, retry/idempotency, failure recovery, authorization, audit completeness, accessibility and measured performance. **Risks:** cross-feature state drift and partial failure. **Done:** user can trace each outcome through source, versions, evidence, assessment, finding, action and reviewer decision.

## Cross-phase gates

- Each migration is reviewed for ownership, FK/index, retention, immutability and rollback; never add candidate tables solely because they were listed in a prompt.
- Every API contract is agreed before frontend/backend parallel work; document it in `docs/development/API_CONTRACT.md`.
- Verify with unit, service, API, authorization, integration and end-to-end tests. Use synthetic or authorized data only.
- Measure actual workload before committing latency/scale SLOs. No numeric targets are approved yet.
- Existing source-only audit found tests for related foundation behavior (see `prd.md`), but this documentation update does not claim those tests were rerun.

## Feature 1 implementation status (2026-10-31)

This addendum supersedes earlier phase/audit statements in this document where they describe Feature 1 as unimplemented or blocked locally. The branch now contains an authenticated application-scoped Gap Analyzer using approved rule versions, the existing validation engine, Document Vault versions and extracted fields, persisted evidence mappings/review history, requirement assessments, findings and saved run history. The page supports loading and selecting saved runs, requirement findings and source citations, mapping extracted evidence, reviewer decisions, and authorized original-version download. Missing evidence is not presented as proof of statutory non-compliance.

Local verification: `python3 -m pytest backend/tests -q` → 497 passed, 21 skipped; frontend TypeScript/build passed; frontend tests 15 passed; lint exited 0 with existing warnings. Feature 1 still is not production-ready: Render is pinned to a stale branch without these routes, live PostgreSQL RLS inspection was blocked by IP allowlisting, and authenticated deployed workflow testing has not occurred. AI/RAG remains deferred pending provider/privacy approval; no institutional documents are sent to an external model. See `GAP_ANALYZER_FINAL_RELEASE_REPORT.md` and `GAP_ANALYZER_REDEPLOYMENT_HANDOFF.md`.
