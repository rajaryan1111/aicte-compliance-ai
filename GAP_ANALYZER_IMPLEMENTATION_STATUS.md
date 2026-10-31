# Gap Analyzer Implementation Status

Audit basis: repository source at `93b7850d3bf5af4a54d504f412986f61bc6ad723`, fetched from `origin/main` before changes. This is source review; tests/runtime have not yet been executed for the Feature 1 branch.

## Labels

- **Verified in source:** behavior/path found by inspecting committed code.
- **Verified in tests:** matching tests exist; their current result is not asserted unless run below.
- **Verified at runtime:** exercised against a running build (none yet).
- **Proposed:** design intent not implemented at audit time.
- **Unverified:** configuration or behavior cannot be established from the repository alone.

## Existing components to reuse

| Capability | Status at audit | Evidence | Test evidence |
|---|---|---|---|
| Authenticated application and institution memberships | Verified in source | `backend/app/api/deps.py`, `core/rbac.py`, `api/v1/applications.py`, `db/models.py` (`Institution`, `Application`, `User`, `InstitutionMembership`) | `test_auth_rbac.py`, `test_tenant_isolation_negative.py`; not run in this audit |
| Document Vault/versioning/private storage | Verified in source | `api/v1/documents.py`, `core/storage.py`, `core/upload_validator.py`, `core/scanner.py`, `Document`, `DocumentVersion`; Alembic persistence foundation and document metadata migrations | `test_document_upload_api.py`, `test_document_storage.py`, `test_persistence.py`; not run |
| Text/OCR extraction with field provenance | Verified in source | `document_analyzer.py`, `ocr_pipeline.py`, `ocr_adapter.py`, `services/document_processing_service.py`, `worker/tasks.py`, `ExtractedField` | `test_document_processing.py`, `test_ocr_pipeline.py`, `test_ocr_adapter.py`, integration worker tests; not run |
| Deterministic checks and regulated rule governance | Verified in source | `services/validation_orchestration_service.py`, `services/rule_engine.py`, `rule_catalog.py`, `RuleApprovalRecord`, `/api/v1/compliance/rules...` | `test_validation_orchestration.py`, `test_rule_engine_aph.py`, `test_rule_governance_hardening.py`, `test_compliance_api.py`; not run |
| Persisted runs, findings and review history | Verified in source | `ValidationRun`, `ValidationCheckResult`, `Finding`, `ReviewAction`, `AuditEvent`; validation and review routers/services | `test_application_validation_api.py`, `test_review_api.py`, `test_review_service.py`; not run |
| Background processing/outbox | Verified in source | `ProcessingJob`, `OutboxMessage`, `core/dispatcher.py`, Celery app/tasks | `test_document_jobs.py`, `test_redis_celery_worker_processing.py`; not run |
| Frontend routes/components | Verified in source | `frontend/app/src/App.tsx`, `ValidatePage.tsx`, `ValidationResults.tsx`, `DocumentOcrVerifier.tsx`, `FindingsTable.tsx`, `ExpiryWatchdogMatrix.tsx`, `RegulatoryScrutinyWorkbench.tsx`, auth context and API client | Frontend tests exist under `frontend/tests`; no dedicated Gap Analyzer tests at audit |

## Missing or partial at audit

| Capability | Status | Gap to close in this branch |
|---|---|---|
| Structured requirement registry | Partial source foundation | Use an approved `RuleApprovalRecord` as the canonical requirement version. Add authorized listing and stable code/version/source/applicability/required evidence response. Do not duplicate rule definitions. |
| Application-specific applicability result | Implemented, locally verified | Per-run applicability status and rationale are persisted against the approved version. Conditional states remain limited by the existing rule schema. |
| Many-to-many evidence mapping | Implemented, locally verified | Application-scoped mapping to exact `DocumentVersion` and optional `ExtractedField`, with review status and audit event. |
| Evidence sufficiency | Partial | Confirmed mappings plus deterministic evaluator outcomes are snapshotted with reasons. The existing evaluators do not yet support every sufficiency class in the prompt. |
| Requirement-level assessment and metrics | Implemented, locally verified | Per requirement/run records and source/evidence snapshots; scoped APIs; metrics computed from saved records. |
| Requirement/evidence-linked findings | Partial | Existing findings can link to assessment and evidence snapshots. Finding navigation/detail UX is incomplete. |
| AI/RAG assistance | Missing | No provider, embeddings, vector store or AI key/config found in manifests/environment examples/source. Build deterministic retrieval and an optional provider boundary only if privacy/provider configuration is explicitly supplied; no external transfer is verified/authorized by this repository. |
| Requirement/evidence review UX | Partial | Authenticated `/gap-analyzer` page, approved requirement list, saved metrics, vault version mapping, and mapping confirmation/rejection. Detailed excerpts, extracted-field picker, filtering, pagination and navigation remain incomplete. |
| Runtime/deployment readiness | Blocked | Local migration passes. Frontend build and test commands are blocked by pre-existing TypeScript/syntax errors in the consistency feature. Read-only production probes: reported frontend URL returned HTTP 200; reported Render health endpoint timed out. Vercel project inspection shows latest production deployment on `main` is `ERROR`. No production migration/deploy was attempted. |

## Implementation and limitations

The implementation adds migration `k1f2a3b4c5d6_requirement_evidence_and_assessments.py`, tenant-scoped gap analyzer APIs, and the authenticated UI. Only active, verified, source-hashed, interpreted and approved `RuleApprovalRecord`s are listed. Missing evidence is recorded as an evidence gap and does not establish non-compliance. The deterministic workflow remains available without an AI provider.

No provider, embeddings, vector store or approved privacy boundary was found in the repository. AI/RAG is therefore explicitly unimplemented rather than represented by a placeholder. The page supports requirements, metrics, document version mappings and reviewer mapping decisions, but does not yet meet all detailed UI acceptance items.

## Source/document discrepancy

The earlier `docs/canonical/truthful-baseline-audit.md` predates current `main` and says there is no persistence, auth, or rule evaluator. That is contradicted by current source. The ten updated canonical documents and this implementation follow current source plus the rule-approval source of truth. The prompt's `backend/app/aicte_rules.py`, `backend/app/api.py`, `backend/app/models.py`, and `frontend/src` paths do not exist here; actual equivalents are under `backend/app/services/rule_engine.py`, `backend/app/api/v1/`, `backend/app/db/models.py`, and `frontend/app/src/`.

## Verification log

| Check | Status |
|---|---|
| Branch base | Verified in source: clean `origin/main` commit `93b7850d3bf5af4a54d504f412986f61bc6ad723` |
| Focused backend checks | Passed: 25 rule engine/orchestration tests; compileall passed |
| Full backend suite | Passed: 494 passed, 21 skipped after installing optional local `pytesseract`; 8 deprecation warnings. |
| Alembic upgrade to head | Passed against a local SQLite database |
| Frontend production build | Blocked by existing TypeScript errors in consistency modules/pages; no errors from the new Gap Analyzer files after fixes |
| Frontend tests | 7 passed; existing `consistency-api.test.mts` fails to parse |
| AI/RAG | Not implemented; no approved provider, vector store or data transfer configuration exists. No AI output is fabricated. |
| GitHub branch/push/PR | Verified: pushed branch `feat/complete-intelligent-compliance-gap-analyzer`; draft PR #20 opened |
| Production | Not deployed: frontend build/tests fail in pre-existing consistency code; Render health probe timed out; production migration not attempted |
