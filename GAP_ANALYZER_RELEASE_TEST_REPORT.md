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


## Preview deployment probe

- Vercel preview for commit `fce00040a739162e1f4f4370def071344d592e32`: READY.
- Authenticated Vercel fetch of `/gap-analyzer`: HTTP 200 and SPA HTML returned.
- This confirms deployment and SPA route fallback only; authenticated API calls and end-to-end assessment remain unverified because Render service inspection is pending.


## Render infrastructure probes

- Confirmed workspace exposes `aicte-compliance-api-preview` on Free plan, branch `arena/5614862e-aicte-compliance-ai`, commit `1229e3227c20a9f4dfdad1d9306588a4a437ef9f`; `healthCheckPath` is unset.
- First cold health probe timed out after 35 seconds during a newly started process; Render logs show Uvicorn startup followed by Alembic PostgreSQL initialization. A subsequent warm `/health` returned 200 and `/health/ready` returned `ready`, PostgreSQL reachable, migration revision `g7b8c9d0e1f2`.
- The live service OpenAPI has no Gap Analyzer routes. The historical backend hostname also returned health 200 but its OpenAPI had no matching Gap Analyzer/Consistency routes.
- A read-only Postgres metadata query was denied because the database external IP allowlist excludes the connector. No allowlist or database settings were changed.
