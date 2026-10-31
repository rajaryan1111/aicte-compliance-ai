# Gap Analyzer Release Test Report

Date: 2026-10-31
Branch: `feat/complete-intelligent-compliance-gap-analyzer`

## Commands and results

| Command | Result |
|---|---|
| `python3 -m compileall -q backend/app backend/alembic` | Passed |
| `python3 -m pytest backend/tests -q` | 496 passed, 21 skipped (including the added extracted-field endpoint regression test) |
| `cd frontend/app && npx tsc -b` | Passed |
| `cd frontend/app && npm run build` | Passed; Vite reports a non-fatal large-chunk advisory |
| `cd frontend/app && npm run lint` | Exit 0; existing warning-level diagnostics remain |
| `cd frontend/app && npm test` | 12 passed, 0 failed |
| `git diff --check` | Passed |

## Coverage and limits

- Existing migration lifecycle coverage is included in the backend suite; no production database was touched.
- Added API regression coverage for authenticated extracted-field access, missing versions, and unauthenticated access.
- Frontend tests exercise the existing Node API/helper suite; no browser E2E or end-to-end live backend workflow was run.
- Production RLS policies and Supabase behavior were not independently verified in a live project.
