# Implementation Plan — Three Connected Compliance Capabilities

**Status:** Proposed, based on source audit of `origin/main` at `93b7850d3bf5af4a54d504f412986f61bc6ad723`. Documentation-only work is complete when reviewed; no implementation is authorized by this plan.

## Existing functionality to extend

- **Gap analysis:** reuse authenticated applications/memberships, versioned private uploaded documents, scan/OCR processing, extracted fields, deterministic validation and rule engine, persisted validation runs/check results/findings, review workflow, audit packages and consistency observations. Missing: persisted requirement applicability and evidence mapping, broad structured/cross-document checks, model/RAG interpretation and requirement-backed metrics.
- **Action planning:** reuse finding identity/review history, existing evidence upload/versioning, worker/outbox, RBAC and audit. Do not call `ReviewAction` a task or duplicate `Finding`. No tasks/assignees/due dates/evidence reviews/remediation notifications currently exist.
- **Regulatory impact:** reuse source verification and approval governance, code rule catalogue, audit, worker/outbox and reassessment API. No official publication archive, immutable document version/clause model, clause diff/dependency graph or impact assessment currently exists.

`FEATURE_AUDIT_REPORT.md` was not present. `docs/canonical/truthful-baseline-audit.md` is an earlier audit; its no-auth/no-persistence/no-evaluator statements conflict with current code and have not been used as current fact. See `prd.md` for capability statuses and exact test/source references.

## Ordered delivery

### Gate 0 — Product and regulatory decisions

Verify current official sources and close issues listed in `docs/research/`; decide requirement identity, applicable institution/program context, source/interpretation authority and any model/privacy policy. No statutory feature is considered ready while its sources/applicability remain unresolved.

### Phase 1 — Shared data foundation

**Depends on:** Gate 0; reviewed data model. **Deliver:** link requirements/applicability to current application context and evidence versions; add justified finding/source references while keeping `DocumentVersion`, `ValidationRun`, `Finding` canonical. Decide many-to-many association and version/retention behavior. **Likely files:** `backend/app/db/models.py`, repositories/services, Alembic, schemas, `docs/development/API_CONTRACT.md`; source evidence detail components in `frontend/app/src`. **API:** requirement/applicability retrieval and review, evidence mapping. **Tests:** migrations, tenant access, FK ownership, cardinality, immutable snapshots, old clients/contract. **Risks:** duplicate rule/requirement catalogues. **Done:** sources of truth and no-duplication design approved; migrations upgrade and rollback plan reviewed; cross-tenant negatives pass.

### Phase 2 — Gap Analyzer

**Depends on:** Phase 1. **Deliver:** applicability reason, evidence mapping, deterministic requirement validation and human review. Add optional AI/RAG only with approved model/provider and verified-source retrieval. **Files:** validation/rule services, finding schema/review API, frontend requirements/evidence/finding flows. **Migration/API/UI:** justified run/finding/evidence refs, proposed versioned assessment contracts. **Tests:** applicable/not applicable/unknown, missing/incomplete/invalid/expired/inconsistent, low confidence, source citations, provider failure, reproducibility, reviewer decisions and tenant isolation. **Risks:** overclaiming non-compliance. **Done:** Feature 1 criteria in `prd.md` satisfied; historical runs preserved; dashboard metrics live.

### Phase 3 — Action Planner

**Depends on:** reviewed actionable findings and evidence upload. **Deliver:** task persistence, assignment and reassignment policy, owner/department decision, dates/priorities, legal state machine, comments/history, corrective evidence review, revalidation and reviewer-controlled closure. Reuse outbox/worker for reminders only after channels/policy are selected. **Files:** new task service/repository/router/schema/migration; existing document upload, audit and revalidation extensions; task UI. **Tests:** legal transitions/concurrency, tenant+department scope, due/overdue edge cases, evidence rejection/retry, audit, revalidation and notification dedupe. **Risks:** false closure and notification noise. **Done:** Feature 2 criteria pass; evidence approved is distinct from compliance resolved.

### Phase 4 — Regulatory Change Impact

**Depends on:** source governance, immutable requirements, approved applicability. **Deliver:** source/doc version registry, clause extraction, ingestion idempotency, exact and structured diff, optional semantic suggestions, impact review/report and human-triggered reassessment. **Files:** source ingestion/extraction/impact services, worker/outbox, models/repositories/API, regulatory library/comparison UI. **Tests:** source verification, checksum and duplicate ingestion, version immutability, clause alignment and editorial/substantive cases, mapped impact evidence, approval/rejection, source/worker failure, tenant boundary. **Risks:** source identity errors, ambiguous amendments and false positive semantic diff. **Done:** Feature 3 criteria pass; no silent status/document invalidation.

### Phase 5 — End-to-end lifecycle

**Depends on:** Phases 1–4. **Deliver:** approved change queues impacted reassessment; assessment creates traceable findings; reviewer action creates tasks; corrective evidence triggers new assessment and controlled closure; old versions remain visible. **Tests:** synthetic full journey, async retries/idempotency, failure recovery, permissions, historical reports, audit completeness, frontend accessibility and measured workload. **Done:** complete provenance path from official source to human resolution; user-facing dashboards match persisted data.

## Cross-cutting test/operational plan

Unit rule/transition tests; service integration with DB/storage/worker; API schema and error tests; anonymous/role/cross-tenant/cross-department security tests; migration tests from deployed baseline; end-to-end synthetic workflow; regression tests for existing validation/review/consistency/document contracts. Use existing `backend/tests`, `backend/tests/integration`, frontend Node tests and CI conventions. Avoid real personal/institutional records without approval. Define latency, throughput, retention and availability targets only after workload, hosting tier and measurement are agreed.

## Unresolved decisions and risks

Official current source/application applicability, data model boundaries, owner of regulatory source approvals, source update/correction process, department scope, notification/escalation policy, external AI provider/retention/evaluation, version retention and service-level targets. Principal risks are rule misinterpretation, unsupported/weak OCR, cross-tenant exposure through new async jobs, status conflation, unverified regulatory ingestion and duplicate data models. Decision records belong in `memory.md` until a dedicated ADR convention is selected.
