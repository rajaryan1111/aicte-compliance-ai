# Phase 3 — Proposal: Three High-Impact Features

Status: **proposal only. No Phase 3 code exists yet.** This document is written against the code
that is actually in the tree, including what already works, so the proposals do not duplicate it.

---

## 0. What already exists (so we do not rebuild it)

| Capability | Where it lives today |
|---|---|
| Per-document field extraction with provenance and confidence | `backend/app/services/document_processing_service.py` (`ExtractedField`, native text → OCR fallback) |
| Advisory cross-document checks inside a run | `backend/app/services/validation_orchestration_service.py` — check C date order, check D institution-identifier consistency, check E duplicate file (SHA-256), check F cross-institution reuse |
| Persisted findings and check results | `Finding`, `ValidationCheckResult`, `ValidationRun` in `backend/app/db/models.py` |
| Rule versioning primitives with an activation gate | `backend/app/rule_catalog.py` — `RuleVersionDraft` (`version`, `effective_from/to`, `SourceProvenance`), `RuleActivationError`, `RuleApprovalRecord` table |
| Institutional record snapshots | `backend/app/services/institutional_record_service.py`, `InstitutionalRecordSnapshot` |
| Remediation plans (Phase 1, done) | `remediation_plans`, `remediation_tasks`, `remediation_deadline_changes` |

Consequence: Feature A is **not** "build consistency checking from zero" — it is "turn the existing
advisory checks into a reviewable, evidence-backed workspace". Feature B is **not** "add versioning"
— it is "compare versions and report impact". Feature C is genuinely new.

---

## Feature A — Cross-Document Consistency Intelligence

### Goal
A signed-in institution can see, for one application, every field that appears in more than one
document, the values each document reports, and whether they agree — with the page and text that
supports each value, and a recorded human decision on every conflict.

### Data model (additive)
```
consistency_resolutions
  id, institution_id, application_id
  finding_key           -- deterministic: "<field>|<doc_a>:<value_a>|<doc_b>:<value_b>"
  document_ids (json)   -- documents involved
  decision              -- "confirmed_mismatch" | "acceptable_variation" | "ocr_error" | "deferred"
  note, decided_by, decided_at, version
  UNIQUE (application_id, finding_key)
```
No change to `documents`, `extracted_fields` or `findings`; resolutions are a separate layer so a
re-run of validation never mutates an earlier human decision.

### Computation
1. Group `ExtractedField` rows for the application by canonical field name.
2. Compare with field-specific rules: identifiers/dates normalized and compared exactly; names
   compared after case/punctuation folding with edit distance ≤2 tolerated **and labelled as such**;
   amounts compared numerically.
3. Every comparison carries `source_a`, `source_b`, `page` (where the extractor recorded one),
   `excerpt` (bounded, e.g. 240 chars), and `confidence` = minimum of the two field confidences.
4. Findings from OCR text only are tagged `source=ocr`; only native-text findings may be reported as
   `confirmed` without human review. Nothing is ever labelled fraudulent.

### API (authenticated, institution-scoped, read + review only)
```
GET  /api/v1/applications/{id}/consistency-report      -> field matrix + conflicts + resolutions
POST /api/v1/applications/{id}/consistency-resolutions -> upsert one decision (idempotent by key)
```
`GET` requires any member; `POST` requires `institution_admin` or `reviewer` role, is idempotent via
`finding_key`, uses optimistic `version`, and writes an `AuditEvent` containing the decision, not the
document text.

### UI
A panel inside the existing Scrutiny Workspace results view (no new route, no redesign): a table of
fields × documents with agree/conflict badges, "why" popover showing excerpt and page, and
per-conflict actions. Conflict counts also appear in the existing readiness breakdown as a separate
line, never folded into the pass/fail score.

### Safety rules
Never auto-declare a document forged; never change a validation run's stored status; ambiguous
(mixed OCR/native or low-confidence) conflicts are forced to `deferred` until a human acts.

### Tests
Unit: comparison matrix (same value different formatting; OCR digit substitution; date off-by-one;
institution id prefix differences), resolution idempotency, RBAC (reviewer vs faculty), tenant
isolation, audit payload contains no raw document text. Integration: upload two synthetic PDFs with a
deliberate name mismatch and one benign formatting difference; assert one `confirmed_mismatch`
candidate and one suppressed.

### Effort / risk
~2–3 days. Risk: OCR noise generates false conflicts — mitigated by the confidence tag and by
suppressing same-normalized-value pairs.

---

## Feature B — Regulatory Change Impact Analyzer

### Goal
When a rule version changes, an administrator can see exactly which requirements, checklist items and
stored evidence are affected before anything in the institution's status changes.

### What is missing today
`RuleVersionDraft` can describe a version and `RuleApprovalRecord` can gate activation, but there is
no stored history of *published* versions, no comparison, and no mapping from a rule to the checklist
items and document types it touches.

### Data model (additive)
```
regulatory_versions
  id, rule_id, version, effective_from, effective_to,
  source_document, source_url, publication_date, verified_by, verified_at,
  payload (json)          -- the structured rule as stored at publication time
```
A version row is only written when `RuleVersionDraft` passes the existing gate; the payload is stored
verbatim so a later comparison cannot be retroactively rewritten.

### Diff and impact
- `GET /api/v1/regulatory-versions?rule_id=` — timeline.
- `GET /api/v1/regulatory-versions/{a}/diff/{b}` — deterministic diff over structured fields
  (thresholds, required document types, applicability, effective dates) producing
  `added | modified | removed` entries with `before`/`after` and the source citation of each version.
- Impact = the document types and checklist items whose rule id appears in the diff, plus existing
  `Document` rows of those types with their validity state. Unknown mappings are reported as
  `unmapped`, not guessed.
- `GET /api/v1/regulatory-versions/{a}/impact/{b}?institution=...` returns the report.
- Adoption is explicit: `POST /api/v1/regulatory-versions/{b}/adopt` requires `institution_admin`,
  records who adopted and when, and **never** edits validation runs, findings or readiness.

### UI
A "Regulatory changes" section in the Compliance Guide explaining the diff in plain English/Hindi,
with the original text shown verbatim beside it and a badge stating whether the change applies to the
institution's application type.

### Safety rules
No synthetic regulatory text; no automatically generated "official" deadlines; nothing is labelled
effective until a version row carries `verified_by` + `verified_at` + a source URL. Draft proposals
render in a separate, clearly labelled block.

### Tests
Diff determinism on fixture versions; affected-item mapping; adoption RBAC and audit; a version with
a missing source URL is rejected at write time; the report never returns a compliance status.

### Effort / risk
~3–4 days. Risk: the largest cost is **verified source data**, not code. Until real handbook versions
are entered with citations, this feature can only demonstrate on synthetic fixtures — and the UI must
say so.

---

## Feature C — Intelligent Evidence Reuse

### Goal
An institution uploads a document once, and the platform shows which other requirements that same
document could satisfy, subject to validity and human approval.

### Why it is new
`Document` rows belong to an application and slot; duplicate SHA-256 detection already exists inside
one run, but there is no institution-level evidence library, no requirement↔document mapping, and no
approval record for reuse.

### Data model (additive)
```
evidence_mappings
  id, institution_id, document_id, document_version_id,
  requirement_code, application_id (nullable)
  status  -- "suggested" | "approved" | "rejected" | "expired"
  suggested_by (algorithm/user), decided_by, decided_at, note, version
  UNIQUE (institution_id, document_version_id, requirement_code)
```

### Suggestion engine (deterministic, explainable)
For each requirement with a required document type, score candidate documents by: exact type match
(strong), issuer/authority match, validity window covering the evaluation date, and extraction
confidence. Output a ranked list with the reason for each suggestion. No model inference, no
"AI score" presented as truth.

### API
```
GET  /api/v1/institutions/{ref}/evidence?requirement=   -> library + suggestions
POST /api/v1/institutions/{ref}/evidence-mappings       -> create suggestion (idempotent)
PATCH /api/v1/institutions/{ref}/evidence-mappings/{id} -> approve/reject (admin/reviewer)
```
All routes are institution-scoped, idempotent by the unique key, versioned for concurrency, and
audited. Reuse never changes a validation result on its own; a later run records which approved
mappings it used.

### Safety rules
Suggestions are never auto-approved; expired documents cannot be approved; a document already used by
another institution is blocked (the existing cross-institution reuse check feeds this); every mapping
keeps the exact `document_version_id` so a re-upload cannot silently rebind an approval.

### Tests
Suggestion ranking on fixtures; approval RBAC; expiry blocks; idempotent re-post returns the same row;
cross-tenant mapping rejected; audit trail; a document with two requirements yields two mappings.

### Effort / risk
~3–4 days. Risk: over-suggestion erodes trust — mitigate with a hard cap (top 3) and explicit
"why this was suggested" text.

---

## Sequencing and dependencies

| Order | Item | Depends on |
|---|---|---|
| 1 | Feature A | nothing beyond Phase 1 |
| 2 | Feature C | A (shares the resolution/audit pattern) |
| 3 | Feature B | verified source data from the institution/regulator side |

Phase 3 must start only after the Phase 1 tree is deployed and verified on the real backend
(see [PRODUCTION_READINESS_REPORT.md](PRODUCTION_READINESS_REPORT.md) §5–6).

## Explicitly out of scope

No chatbot, no "AI score" without evidence, no automatic fraud claims, no fabricated handbook text,
no RL component, no redesign of the dashboard/sidebar/auth flow, and no change to the existing API
contracts — every addition above is a new route or a new table.
