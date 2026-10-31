# Product Requirements — AICTE Compliance AI

**Status:** Existing platform plus proposed capability expansion. This product is an advisory decision-support prototype, not an official AICTE system. Proposed features below are not implemented unless explicitly marked in the baseline audit.

## Product goal and users

Help institution representatives prepare application evidence and help authorized reviewers assess submissions against applicable, source-governed requirements. The next product increment adds requirement-level gap analysis, accountable corrective actions, and impact review when official regulations change. Authorized humans retain all compliance and statutory decisions.

Current roles are `institution_admin`, `scrutiny_officer`, `auditor`, `regulatory_director`, and `super_admin` (see `backend/app/core/rbac.py`). Department roles and task owners are future concepts; add no role until its authority and scope are defined. Application access is institution-membership scoped.

## Verified baseline and capability matrix

Evidence is on the current `main` source tree at audit time; this is a source audit, not a claim that the test suite was rerun. The older `truthful-baseline-audit.md` is useful context but predates current source and is not authoritative where it conflicts.

| Capability | Status | Evidence and limitation |
|---|---|---|
| Application/year applicability | **PARTIAL** | `backend/app/services/rule_engine.py` defines application-type and academic-year conditions; `validation_orchestration_service.py` filters active rules on those fields. No institution/program/academic-year applicability record or reviewable applicability decision exists. |
| Explicit requirement applicability and evidence mapping | **NOT IMPLEMENTED** | No requirement/applicability/evidence-link entities or migrations. `Document` is an application document slot, not a requirement mapping. |
| Upload, ownership and document versions | **IMPLEMENTED** | Authenticated application-scoped upload, private storage, malware scan gate and immutable `DocumentVersion`: `api/v1/documents.py`, `core/storage.py`, `core/scanner.py`, models/migrations. Reuse these; no second vault. |
| OCR and structured extraction | **PARTIAL** | `ocr_pipeline.py`, `ocr_adapter.py`, `document_processing_service.py` and worker persist `ExtractedField` values with confidence/page/engine metadata. Image OCR and PDF processing paths exist; supported formats, parser paths and field coverage are limited. No general evidence schema or complete bounding-box/location provenance guarantee. |
| Deterministic validation | **PARTIAL** | `validation_orchestration_service.py`, `rule_engine.py`, `rule_catalog.py` evaluate readiness, expiry, identity/cross-document observations and approved APH rule drafts. No generalized applicability engine or verified coverage of every regulatory requirement. |
| Regulatory rule governance | **PARTIAL** | `RuleApprovalRecord`, verify/approve APIs and audit events provide source hash, clause/page, dates and reviewer metadata. Rules are a fixed code catalogue; this is not an official-source registry, immutable publication archive, or regulatory change/version comparison service. Source research gaps remain in `docs/research/official-source-verification-report.md`. |
| Cross-document consistency | **PARTIAL** | Validation compares extracted institution identity/name; `/consistency` persists manually supplied discrepancy checks and findings. It does not run a general-purpose comparison engine. |
| Evidence-backed finding generation | **PARTIAL** | Findings link to validation run and optionally one document version, with serialized evidence; no requirement link or many-to-many evidence references. |
| Human finding review/history | **IMPLEMENTED** | `/api/v1` review endpoints, `ReviewAction`, transitions, rationale, optimistic concurrency and audit events. Review resolution is not remediation task management. |
| Backend-backed review metrics | **PARTIAL** | Review summary and queue APIs exist. Main dashboard contains presentation/demo content; do not treat all shown figures as live institution metrics. |
| AI interpretation/RAG | **NOT IMPLEMENTED** | No LLM, embeddings, vector store, regulatory retrieval, or model-provider integration found in manifests/source. OCR is not semantic AI analysis. |
| Corrective-action task planner | **NOT IMPLEMENTED** | No task, assignment, due-date, task-evidence or notification model/API/UI. Review actions and finding status are not tasks. |
| Regulatory change impact analyzer | **NOT IMPLEMENTED** | No regulatory publication/version/clause/change/impact entities, ingestion, comparison, dependency map or impact workflow. Rule source metadata/approvals are reusable governance, not this feature. |

Relevant existing regression evidence includes `backend/tests/test_application_validation_api.py`, `test_validation_orchestration.py`, `test_rule_engine_aph.py`, `test_rule_governance_hardening.py`, `test_document_processing.py`, `test_ocr_pipeline.py`, `test_review_api.py`, `test_review_rbac.py`, `test_consistency_api.py`, `test_tenant_isolation_negative.py`, and integration tests under `backend/tests/integration/`. These tests exist; this documentation task did not execute them.

## Proposed Feature 1 — Intelligent Compliance Gap Analyzer

Evaluate whether evidence supports a requirement that applies to a specific institution/application context, rather than treating document presence as satisfaction.

1. Resolve a versioned requirement and its applicability using institution type, program/course, academic year, application type, regulatory context and effective dates. An authorized reviewer can inspect and correct applicability; unknown applicability yields `manual_verification_required`, not a failing statutory conclusion.
2. Reuse the existing application, document slot/version, private storage, malware scan, extraction worker, `ExtractedField`, deterministic rule engine, `ValidationRun`, `Finding`, review and audit services. Add a requirement-to-evidence mapping only after defining its relation to these existing entities.
3. Map one requirement to many evidence items and one evidence item to many requirements. Preserve document version, extracted field, page/location when available, observed/normalized value, extraction confidence and source limitations.
4. Run deterministic checks first. AI interpretation/RAG is a later optional adapter behind a model-neutral interface; retrieve only verified and applicable official clauses. No model may invent a clause or declare institutional compliance.
5. A finding records institution/application, requirement, assessment run, category, description, deficient information, rationale, source clause and regulatory version, evidence references, severity, separate confidence, suggested correction, review state, reviewer decision/rationale and timestamps. Candidate categories: missing, incomplete, invalid, expired, inconsistent, unsatisfied, manual verification required. Candidate severity: critical/high/medium/low/informational; severity is rule/reviewer controlled, never arbitrary LLM output.
6. Revalidation creates a new immutable assessment and findings; it never rewrites prior results. Missing evidence means evidence was not supplied, not automatically that a statutory breach occurred.

Acceptance: applicable requirements and reason are inspectable; evidence mappings are persisted; deterministic results are reproducible; every claim links to evidence and a verified source/version where relevant; uncertainty routes to review; authorized users can record a rationale; cross-tenant access is blocked; repeat assessment preserves history; dashboard counts are computed from persisted scoped data.

## Proposed Feature 2 — Compliance Action Planner

Create a corrective action only from a reviewer-confirmed or otherwise explicitly actionable finding. The task retains immutable links to its original finding, assessment and requirement. A user reviews/edits any AI-suggested text before saving.

Task data: institution/application, finding and requirement references, title, instructions, expected evidence, assigned user/department, priority, due date, status, creator, timestamps and optimistic version. Assignment/reassignment requires permission in the institution and (if adopted) department scope. Proposed transitions: `open → assigned → in_progress → evidence_submitted → under_review → resolved`; rejection/request-more-evidence returns to `in_progress`; authorized reopen requires reason; cancellation requires reason and authorization; overdue is preferably a derived flag, not a competing terminal status. Enforce transitions server-side.

Assigned users submit new evidence through existing secure document intake, linked as corrective evidence without overwriting prior versions. A reviewer accepts/rejects evidence with rationale. Evidence acceptance does not equal compliance resolution: trigger a new assessment of the linked requirement and allow an authorized reviewer to confirm closure. Keep comments, assignments, evidence decisions, status history and revalidation attributable. AI may draft instructions/summaries only; it cannot assign, approve, close, or alter compliance status.

Acceptance: tasks preserve finding/requirement links; authorized assignment and reassignment work; due dates/priorities and legal transitions persist; submitted evidence uses existing tenant controls; reviewer decisions require rationale; revalidation creates a new run; closure is human controlled; history is auditable; institution/department views enforce scope.

## Proposed Feature 3 — Regulatory Change Impact Analyzer

Maintain an authoritative-source registry and immutable publication versions; ingest only approved official publications (AICTE notifications, APHs, regulations, circulars, amendments/corrigenda and relevant government publications). Preserve issuer, canonical URL, title, publication/effective dates, retrieval time, version, checksum and verification decision. Third-party sources remain explicitly unverified and cannot support active regulatory findings.

An idempotent ingestion workflow retains the original artifact, extracts text/metadata and clauses (OCR only where needed), then compares exact text and structured requirements; semantic comparison is optional and advisory. Classify added, removed, changed, threshold/date/eligibility/evidence/applicability edits, clarifications and editorial changes. Do not interpret every wording edit as substantive. Human reviewers verify source, extracted clause, change type and applicability.

Map `Source → Version → Clause → Requirement → Applicability → Institution/Application → Evidence`; preserve old and new clause references, affected requirements/evidence, reason, suggested review, impact category, separate confidence/review state, and human decision. A change can queue reassessment; it must not invalidate evidence or silently change compliance. New assessments may produce findings; confirmed findings may create actions; accepted corrective evidence drives revalidation. Historical source versions, assessments and actions remain readable.

Acceptance: verified official source is required before authority claims; version/checksum/history is preserved; clause diffs are traceable; requirement/evidence impact is reviewable; reports cite source clauses; human approval is recorded; reassessment can be triggered without changing status by discovery alone.

## Shared policy, security and scope

All protected operations require authenticated user, active institution membership, permission checks and server-side tenant scoping. Use existing roles until any new department/task roles are decided. Do not trust client-supplied institution IDs. AI only receives the authorized evidence subset. Keep `confidence`, `finding severity`, `regulatory impact`, `evidence acceptance`, `compliance result`, and human decision as distinct concepts. No statutory interpretation is enabled until official-source research and rule-approval gates are closed. Metrics must be live backend data, not mock values.

## Open decisions

Confirm the regulatory source ingest owner and approval authority; program/institution applicability vocabulary; exact new entity boundaries versus extending `Finding`/`ValidationRun`; whether department scope exists and who manages it; task notification channels/escalations; AI provider/model and retention terms; target performance/SLO after workload measurement; and legal/source verification status for current APH requirements. See `memory.md` and `implementation-plan.md` for gates.

## Feature 1 implementation status (2026-10-31)

This addendum supersedes earlier phase/audit statements in this document where they describe Feature 1 as unimplemented or blocked locally. The branch now contains an authenticated application-scoped Gap Analyzer using approved rule versions, the existing validation engine, Document Vault versions and extracted fields, persisted evidence mappings/review history, requirement assessments, findings and saved run history. The page supports loading and selecting saved runs, requirement findings and source citations, mapping extracted evidence, reviewer decisions, and authorized original-version download. Missing evidence is not presented as proof of statutory non-compliance.

Local verification: `python3 -m pytest backend/tests -q` → 497 passed, 21 skipped; frontend TypeScript/build passed; frontend tests 15 passed; lint exited 0 with existing warnings. Feature 1 still is not production-ready: Render is pinned to a stale branch without these routes, live PostgreSQL RLS inspection was blocked by IP allowlisting, and authenticated deployed workflow testing has not occurred. AI/RAG remains deferred pending provider/privacy approval; no institutional documents are sent to an external model. See `GAP_ANALYZER_FINAL_RELEASE_REPORT.md` and `GAP_ANALYZER_REDEPLOYMENT_HANDOFF.md`.
