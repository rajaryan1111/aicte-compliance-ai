# Gap Analyzer Release Test Report

Date: 2026-10-31
Branch: `feat/complete-intelligent-compliance-gap-analyzer`

## Commands and results

| Command | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | 497 passed, 21 skipped, 8 dependency deprecation warnings |
| `cd frontend/app && npx tsc -b` | Passed |
| `cd frontend/app && npm run build` | Passed; non-fatal chunk-size advisory (>500 kB) |
| `cd frontend/app && npm run lint` | Exit 0; six warning-level diagnostics in unrelated existing files |
| `cd frontend/app && npm test` | 15 passed, 0 failed |
| `git diff --check` | Passed before commit |

## Added workflow coverage

`backend/tests/test_gap_analyzer_workflow.py` uses FastAPI TestClient and a real in-memory SQLAlchemy SQLite database, seeded with two institutions, memberships, an approved source-verified rule, an application-owned Document Vault version, and an extracted field. It calls real application routes/services to retrieve requirements, reject cross-tenant requirements, create and review evidence mapping, execute deterministic validation, read the saved gap snapshot/findings, verify review persistence after retrieval, reassess into a distinct run, list saved runs, reject cross-tenant run access, and reject unauthenticated analysis. The test does not call external OCR, object storage, Render, or PostgreSQL. Existing middleware/session state isolation is fixture-local.

`frontend/tests/gap-analyzer-api.test.mts` adds three Node tests for authenticated run history, saved-run selection, and persistent review API payload/auth. These are API-client tests, not browser automation.

## Migration and security scope

The backend suite includes local SQLite Alembic migration lifecycle coverage. No live database migration was run. Local tenant isolation is application-level; live PostgreSQL RLS policy inspection was blocked by the database external IP allowlist. SQL checks and redeployment steps are in `GAP_ANALYZER_REDEPLOYMENT_HANDOFF.md`.

## Deployment probes (prior read-only observations)

- Render `aicte-compliance-api-preview` was observed on stale branch `arena/5614862e-aicte-compliance-ai`, commit `1229e3227c20a9f4dfdad1d9306588a4a437ef9f`, health path unset. Warm `/health` and `/health/ready` returned ready; deployed OpenAPI lacked Gap Analyzer paths.
- Vercel feature preview commit `fce00040a739162e1f4f4370def071344d592e32` was READY and `/gap-analyzer` returned SPA HTTP 200. This does not test authenticated backend behavior.
- No infrastructure or production settings were changed.
