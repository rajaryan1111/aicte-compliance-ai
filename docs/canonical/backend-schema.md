# Backend Schema — Current Source of Truth and Proposed Extensions

**Status:** Existing tables are based on `backend/app/db/models.py` and Alembic migrations. Proposed rows are design candidates, not migration instructions. First decide whether to extend existing entities.

## Current persisted entities

| Concept/table | Current purpose and key links | Relevance / limitation |
|---|---|---|
| `institutions`, `users`, `institution_memberships` | Tenant; credentials/identity; unique user-institution membership and role. | Canonical tenant/access records. No departments/program catalog. |
| `applications` | Institution FK, type, academic year, status and timestamps. | Assessment context, but no program/course or institution profile applicability attributes. |
| `documents`, `document_versions` | Logical application slot; version, opaque storage key, hash, type, size, scan/process state. | Canonical institutional uploaded evidence. Never create a second vault. |
| `extracted_fields` | Version FK, field/raw/normalized values, confidence, page, bounding box, engine/version and status. | Canonical extraction observation; location can be absent and corrections need provenance review. |
| `validation_runs`, `validation_check_results`, `findings` | Application/run; date/rule snapshot/consumed version IDs/counts/limitations; deterministic check and finding results; finding optionally points to one document version. | Canonical assessment and finding history. No requirement FK, model metadata, confidence field on main finding, or many-to-many evidence references. |
| `review_actions`, `audit_events`, `audit_packages` | Review actor/action/rationale/history; scoped audit event; exported integrity package. | Reuse for review/audit. Not action tasks; audit integrity claims remain bounded by implementation. |
| `consistency_checks`, `consistency_findings` | Application-linked manually persisted check and discrepancy values/confidence/evidence/resolved flag. | Generic record CRUD; not a comparison engine or canonical regulatory finding. |
| `processing_jobs`, `outbox_messages` | Durable async job state/retry and transactional message publication. | Reuse for ingestion, assessment and notification jobs where suitable. |
| `verification_attempts`, `institutional_record_snapshots`, `infrastructure_evidence` | Application/document verification; institution snapshot; document-linked infra metrics/inspection recommendation. | Reuse only for these concepts; not regulatory source versions or generalized requirements. |
| `rule_approvals`, `retention_runs` | Rule version/source/checksum/reviewer/approval/effective dates/definition; auditable retention job. | Rule governance base and retention, not official source document archive or clause-change history. |

Migrations currently cover the initial persistence/auth foundation, document metadata, jobs/outbox, validation results, review actions, audit packages, verification/infrastructure records, rule approvals/retention, and consistency records (see `backend/alembic/versions/`).

## Candidate extensions to evaluate

| Concept | Existing equivalent? | Proposed purpose/keys and tenant policy | Version/retention note |
|---|---|---|---|
| Regulatory source | No dedicated entity; source fields appear in rule approval. | Source identity, official issuer/URL, verification status; centrally governed, separate permission. | Preserve source changes and verification events. |
| Regulatory document/publication version | No. Rule checksum identifies a referenced source artifact but does not preserve it. | Immutable original publication, source FK, title/version/dates/retrieval/hash/artifact key. | Retain original and checksum; new publication creates version, never overwrite. |
| Regulatory clause | No. Rule has citation text only. | Version FK, stable clause key, exact extracted text/page/section and extraction provenance. | Clause correction creates a new publication extraction/version. |
| Requirement + requirement version | Partial conceptual equivalent in code-defined `RuleVersionDraft`/approval, but no durable independent requirement registry. | Stable requirement identity; immutable definition/version, source clause refs, expected evidence, interpretation/test evidence. | Approval and supersession explicit; do not duplicate rule evaluator. Decide whether rules are requirement versions or link to them. |
| Requirement applicability | No persisted entity; rule filters type/year only. | Requirement version + application/institution/program/year scope, effective dates, decision/reason and reviewer. Tenant data scoped to institution. | Preserve evaluated applicability snapshot in each assessment. |
| Evidence-to-requirement mapping | No. Application document slot is not a mapping. | Requirement↔document version/extracted field or source record; include mapping provenance/status/actor. | Mapping changes append history; assessment snapshots exact mapping. |
| Assessment/finding evidence references | Existing run/finding covers part. | Prefer extending existing run/finding with requirement and source refs, and a child evidence-reference relation for many-to-many. | Assessment snapshot immutable; preserve nullable legacy fields and API compatibility. |
| Corrective action/task | No. `ReviewAction` is a review event, not task. | Task FK to institution/application/finding/requirement; assignee, department if approved, priority, due, status, creator/version. | Append `TaskEvent`/audit history; task links evidence versions and revalidation run. Tenant is derivable through application but verify joins. |
| Regulatory change/impact assessment | No. Rule approval history is not a diff/impact record. | Change points to old/new clause/version; impact records requirement/application/evidence, reason, category, confidence, review state/actor. Institution scoped when it references institution data. | Immutable source versions and impact decisions; reassessment links to new `ValidationRun`. |
| Notification | No general notification table/channel identified. | Add only after delivery/channel decision; recipient and tenant, template/event, delivery/retry status. | Define retention and dedupe/idempotency.

## Data invariants

- Tenant-owned records must be linked by FK to an institution or derive a fully verified path through application; query and mutation must validate that path and permission.
- Add composite constraints/indexes for the actual tenant/query patterns; avoid redundant institution IDs unless required for safe row-level scoping and constrained to parent ownership.
- `DocumentVersion`, publication version, approved requirement version and completed assessment are append-only evidence snapshots. Corrections/reassessment create new records.
- Task/event, source verification, requirement approval, impact review and revalidation are attributable. Avoid cascading deletes where legal/audit retention needs historical records; align with documented retention and deletion policy.
- Store originals in private object storage and persist opaque keys, hashes and metadata only. Minimize personal data; define retention separately for evidence, extraction, prompts/results and regulatory artifacts.
- Do not claim DB immutability from application conventions alone. Define backup, retention, access and audit integrity controls.

## Canonical concept ownership

Application and institution membership remain tenant context. `DocumentVersion` is the evidence-byte/version source of truth; `ExtractedField` is an observation, not source truth. `ValidationRun` is assessment history; `Finding` is the current finding record; `ReviewAction` is human finding review; `AuditEvent` is sensitive-operation history. `RuleApprovalRecord` governs rule definitions but is not a source document archive. New requirement/applicability, task, regulatory-version and impact concepts have no existing canonical table and require an ADR/migration design before coding.
