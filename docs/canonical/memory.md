# Project Memory and Decisions

**Purpose:** stable verified project facts and unresolved decisions. Detailed requirements belong in `prd.md`, `architecture.md`, `backend-schema.md` and `trd.md`.

## Verified repository facts at this documentation update

- Intended repository: `rajaryan1111/aicte-compliance-ai`; documentation work was based on fetched `origin/main` commit `93b7850d3bf5af4a54d504f412986f61bc6ad723`.
- Current stack: React 19/TypeScript/Vite; FastAPI/Pydantic; SQLAlchemy/Alembic; SQLite/PostgreSQL; private storage abstraction; Celery/Redis and outbox. Confirm manifests and deployment config before future changes.
- Existing platform includes institution/application membership, document versions/extraction, processing jobs, validation runs/findings, rule approval records, review actions, audit events/packages, consistency records, verification/infrastructure records and retention records.
- Prior file named `FEATURE_AUDIT_REPORT.md` is absent. `docs/canonical/truthful-baseline-audit.md` exists but predates current source and contains statements now contradicted by main (including no persistence/auth/rule evaluator); use source and current tests, not stale rows, as truth. It was not modified in this task.
- Gap Analyzer is partial; Action Planner and Regulatory Change Impact Analyzer are not implemented. See `prd.md` for capability-by-capability source and test evidence.
- No LLM/RAG/vector stack is present in the current manifests/source. Do not infer AI reasoning from OCR or “AI” branding.
- Current regulatory source research has open issues tracked under `docs/research/`; no newly assumed clause or universal requirement is approved by this specification.
- Existing main branch routes include some legacy unprotected/stateless endpoints in `backend/app/main.py`; review before handling real sensitive data.

## Durable product invariants

- Outputs are advisory; authorized humans decide. Evidence absence, extraction uncertainty, finding severity, model confidence, task status and compliance outcome remain separate.
- Uploaded document versions, regulatory versions, assessments and review/action history are traceable and never silently overwritten.
- Tenant and permission checks apply on the server for APIs, workers, downloads, dashboards and AI context.
- Every active requirement has official source provenance, applicability, interpretation approval and tests. Unresolved status remains explicit.
- Existing entities/services are extended where they own the concept; no duplicate document vault, validator, finding system or task-like workflow without an ADR.

## Decisions still required

1. Canonical requirement identity/version and whether to extend code-defined rules or create persisted requirement records.
2. Institution type, program/course, academic year and applicability condition vocabulary and governance.
3. Many-to-many evidence mapping and whether links are requirement-level, assessment-level or both.
4. Task owner/department permissions, overdue/escalation rules, notification channel and retention.
5. Regulatory source ingestion method, responsible authority, verification/review quorum, artifact retention and correction/supersession semantics.
6. Whether AI-assisted interpretation/semantic comparison is needed; provider/model, data region, training/retention terms, evaluation set and human-review thresholds.
7. Target workload and service-level/performance objectives, to be measured before setting numbers.

Record each decision in an ADR with context, chosen option, alternatives, evidence, consequences, confidence, reversibility and revisit trigger. Keep the current project research issues in the source register rather than copying unverified claims into this memory.

## Feature 1 implementation status (2026-10-31)

This addendum supersedes earlier phase/audit statements in this document where they describe Feature 1 as unimplemented or blocked locally. The branch now contains an authenticated application-scoped Gap Analyzer using approved rule versions, the existing validation engine, Document Vault versions and extracted fields, persisted evidence mappings/review history, requirement assessments, findings and saved run history. The page supports loading and selecting saved runs, requirement findings and source citations, mapping extracted evidence, reviewer decisions, and authorized original-version download. Missing evidence is not presented as proof of statutory non-compliance.

Local verification: `python3 -m pytest backend/tests -q` → 497 passed, 21 skipped; frontend TypeScript/build passed; frontend tests 15 passed; lint exited 0 with existing warnings. Feature 1 still is not production-ready: Render is pinned to a stale branch without these routes, live PostgreSQL RLS inspection was blocked by IP allowlisting, and authenticated deployed workflow testing has not occurred. AI/RAG remains deferred pending provider/privacy approval; no institutional documents are sent to an external model. See `GAP_ANALYZER_FINAL_RELEASE_REPORT.md` and `GAP_ANALYZER_REDEPLOYMENT_HANDOFF.md`.
