# Gap Analyzer Release Remediation

## Starting point

- Branch: `feat/complete-intelligent-compliance-gap-analyzer`
- Local and remote head at start: `6af070e446a0aea742004c4234685de8ed083fce`
- PR #20 is open and draft, targeting `main` at `93b7850d3bf5af4a54d504f412986f61bc6ad723`.
- `git status`, `git diff`, and `git diff --check` were clean at the start. `git fetch origin` confirmed neither `main` nor the feature branch had moved.
- The existing Gap Analyzer implementation, migration, APIs, services, schemas, tests, canonical documents, and status report were inspected. Canonical docs were previously reviewed in full; file counts and paths were rechecked for this continuation.

## Reproduced defects

| Check | Reproduced result | Root cause found |
|---|---|---|
| `npm --prefix frontend/app run build` | TypeScript failure across Consistency code | `ConsistencyPage.tsx` is a truncated/incomplete workbench: it references missing imports, mismatched state shapes and undefined handlers. `ConsistencyDetailView.tsx` contains misplaced Sidebar JSX/imports and undefined state/route variables. `consistency-api.ts` calls a transport API that does not exist and redeclares `ConsistencyStatus`. |
| `npm --prefix frontend/app test` | 7 tests pass; Consistency API suite fails parsing | `consistency-api.test.mts` contains literal invalid syntax (`...toMatch(/^\\s/)n  })`) and mixed test syntax. |
| Original adjacent checkout `npm run build` | Passed | A complete authenticated Consistency workbench and typed authenticated API implementation exist as uncommitted work there. This checkout is read-only and remains untouched. It is being used as a reference for compatible repairs. |
| Live frontend URL | HTTP 200 (previously verified) | Confirms only frontend availability, not backend operation. |
| Render `/health` URL | Timed out (previously verified) | Requires service and workspace inspection; no production change is safe until this is diagnosed. |
| Vercel project | Latest production deployment on `main` reports `ERROR` (previously verified) | Production build/deployment is already unhealthy; inspect build logs after local build passes. |

## Existing Gap Analyzer verified/reused

- Requirement assessments use active, verified, source-hashed and approved `RuleApprovalRecord` versions.
- Existing deterministic validators, Document Vault versions, extracted fields, findings, auth, institution membership and review audit are reused.
- Assessment/evidence snapshots and mapping decisions persist; metrics are computed from saved assessments.
- AI/RAG remains unconfigured. No provider or privacy boundary is present; institutional evidence will not be sent externally.

## Missing workflows to complete

- Evidence detail that shows actual document/version metadata, extracted field, excerpt, page and review history.
- A safe authorized route to the existing source document; page navigation only if the vault supports it.
- Request-information and sufficient/insufficient review actions with persisted actor/reason/history.
- Finding detail and navigation through the saved assessment, requirement source and evidence snapshots.
- Tenant-scoped API and UI regression coverage for those workflows.
- Full frontend build/test/lint and full backend/migration regression reruns.

## Planned remediation

1. Restore the authenticated Consistency list/detail workflow using compatible existing API client patterns; preserve both routes and functions.
2. Replace the malformed Consistency test with valid Node test-runner tests and meaningful assertions.
3. Complete Gap Analyzer evidence detail/review and finding navigation using only saved backend data and authorized document endpoints.
4. Add backend/API/UI tests for assessment history, mapping decisions, evidence access, finding links and cross-tenant denial.
5. Re-run migrations, all backend tests, all frontend tests, TypeScript/build/lint, then verify actual Vercel/Render settings and health. Keep PR #20 draft until these gates pass.

## Deployment blockers

- Frontend build/test are red until the reproduced defects are fixed.
- Render health timed out and the Vercel production deployment is `ERROR`.
- AI/RAG remains deferred pending an approved provider and privacy/data-transfer boundary.
- Production migration/deploy is not safe until local gates pass and infrastructure health is confirmed.
