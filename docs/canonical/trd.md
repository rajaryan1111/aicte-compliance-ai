# Technical Requirements — Provisional

**Status:** technology selection pending dependency and deployment review.

## Confirmed current baseline
- Python FastAPI API under `backend/app/main.py`.
- Pydantic request validation.
- Current endpoint accepts caller-supplied document lists and expiry dates; it does not load an authoritative AICTE ruleset, persist applications or process uploaded files.
- Backend tests live in `backend/tests/` and run in the `Backend tests` GitHub Actions workflow for `main`, `research/grounded-foundation` and pull requests targeting either branch.

## Technical requirements
1. API requests and responses use documented schemas and consistent error structures.
2. Authentication and authorization run server-side; all application/document/finding queries are tenant-scoped.
3. Database migrations are version-controlled and tested from a clean database.
4. Uploaded files are treated as hostile input; impose byte/page/time limits, validate content signatures and store privately using opaque names.
5. Document versions and validation runs are preserved; hashes identify bytes but do not establish authenticity.
6. Extraction records raw text, normalized value, confidence when available, engine/version and page/bounding-box provenance.
7. Rule evaluation is deterministic for a given input, rule version and evaluation date.
8. Failures are explicit and observable; no broad exception swallowing or success-shaped empty results.
9. External providers use adapters, timeouts and safe retries; never imply a call succeeded when it was not performed.
10. Logs exclude credentials and unnecessary document contents; secrets are supplied through environment/secret management, not committed.
11. Tests include authorization, tenant isolation, malformed uploads, rule boundaries, processing failures and historical version behaviour.

## Decisions still open
- Database and migration tooling.
- Authentication provider or local-auth approach.
- Private file storage backend.
- OCR engine and language/model configuration.
- Synchronous versus background processing threshold.
- Deployment target and cost constraints.

## Decision rule
Choose the smallest supported stack that meets tenant isolation, traceability, safe file processing and reliable end-to-end demonstration. Record the selected version, reason, alternatives, migration implications and rollback plan in `docs/decisions/` before adding dependencies.

## Research-informed technical constraints — 2026-10-23
- Store research/source provenance and rule lifecycle status so provisional or unresolved material cannot be activated by default.
- Record exact source document/version, URL, clause/page, retrieval date, effective interval and reviewer decision for active rules.
- Keep official integration status honest: current research did not establish an AICTE public API or authorized issuer integrations. “Not researched/confirmed” is not equivalent to “does not exist.”
- Regulatory blockers remain: missing contents of the 1 April 2024 scrutiny document; unverified official status/effective date of the 2026–27 addendum; unresolved Annexure-2 §2.1 pagination and Clause 7.17 reference; unresolved applicability of the NBA validity date ending 30 April 2025; official SIH listing/deadline not directly verified.
- These findings do not choose the database, auth provider, storage or OCR engine. Those remain explicit decisions for the pre-coding phase.
