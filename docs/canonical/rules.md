# Product, Engineering and AI Rules

**Status:** Normative guardrails for existing and proposed features. A rule written here is not itself an activated AICTE requirement.

## Source and interpretation rules

- Use official AICTE publications, amendments, corrigenda and relevant official government publications as authoritative sources. Preserve source URL, issuer, title, retrieved original, checksum, publication/effective dates, version and verification record. Mark third-party material unverified.
- The repository research register reports unresolved current-source/applicability questions (`docs/research/official-source-verification-report.md`, `source-register.md`, `reconciliation.md`). Close relevant questions against official source before activating or changing regulatory interpretation. Do not invent requirements or describe provisional handbook extraction as universally applicable.
- Preserve exact clause/page/version and interpretation rationale. Keep rule severity and model confidence separate. A wording diff is not automatically a substantive change.
- Existing governance at `backend/app/rule_catalog.py`, `services/rule_engine.py` and `/api/v1/compliance/rules...` is a base to extend. Code-defined rules, source verification records, and source publication versions are distinct concepts; do not conflate them.

## Evidence and assessment rules

- `DocumentVersion` is immutable evidence. Replacements create a version; past runs keep their consumed version snapshot.
- OCR/extraction results are observations, not truth. Keep raw and normalized value, engine/version, confidence and available page/location provenance. Unreadable/ambiguous is not a pass.
- Evidence acceptance does not mean requirement satisfaction. A new assessment is required; preserve prior assessment/finding history.
- Every proposed finding states what evidence was observed or missing, why the rule applies, exact source and limitations. A missing record is not by itself proof of statutory non-compliance.
- Never mark a requirement compliant solely from an LLM result. Use deterministic logic for machine-verifiable conditions. Flag ambiguity, low confidence, unsupported/contradictory source and high-impact interpretation for authorized human review.
- Severity is based on approved rules/criteria and may be reviewed by an authorized human. Model confidence and regulatory change impact are separate fields. The model cannot select arbitrary severity.

## Security and privacy rules

- Authenticate all protected APIs and authorize each operation server-side using current user's active institution membership, role/permission, and, if approved, department scope. Never trust a frontend guard or client institution ID by itself.
- Return the established concealed 404 for inaccessible institution-scoped objects where current API patterns do so. Apply the same boundary to file downloads, search, task/impact views and background jobs.
- Send AI services only data the initiating user is authorized to access. Minimize prompt content; do not log document text, credentials, tokens or unnecessary personal data. Approve provider retention/region/training terms before production use.
- Reuse upload streaming limits, content validation, private storage, malware scanning and retention controls. Do not expose storage keys or raw paths.
- Audit every source/rule approval, finding decision, task assignment/state/evidence decision, impact decision and revalidation, with authenticated actor, timestamp, target and rationale where needed. Keep audit history append-only at application level; do not claim cryptographic immutability without external anchoring.
- Existing legacy public routes must be reviewed before real user data is enabled (`/api/v1/documents/analyze`, `/api/v1/institutions` in `backend/app/main.py`).

## State and integration rules

- Keep separate state machines for document processing, validation run, finding review, action task, source verification, regulatory change review and compliance outcome. Do not reuse `resolved` to mean all of them.
- Status updates follow explicit server-validated transitions. Reopen/cancel/waive/reject decisions require the relevant permission and recorded reason.
- Regulatory source/version and published requirement versions are immutable. Corrections publish a new version and preserve supersession links.
- Discovery of a regulatory change may queue a proposed impact assessment; it must not silently invalidate evidence, alter institution compliance, or make tasks appear resolved.
- Background work is idempotent, bounded-retry, tenant-rechecked and auditable. Failure is visible and cannot create a misleading completed assessment.

## Existing, proposed and API contract discipline

- Existing functionality claims must cite current source and tests; a page, table, mock or README claim alone is insufficient. Use capability labels in `prd.md`.
- Proposed contracts must be labeled proposed and added to `docs/development/API_CONTRACT.md` before implementation. Do not break current response shapes/status meanings silently.
- Keep the user's source changes isolated; documentation work does not justify editing application code, schema or dependencies.
- All displayed dashboard metrics must derive from authorized persisted data. Label demo/synthetic values and states.
