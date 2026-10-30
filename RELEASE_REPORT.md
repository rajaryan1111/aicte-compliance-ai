# Phase 1 Release Report

Date: 2026-10-31. Branch: `release/phase-1-remediation-plans`, based on `main` @ `81d9667`.
The exact release commit SHA is recorded in the pull-request description and in the hand-off message;
a document cannot contain the hash of the commit that introduces it.

---

## 1. What is in this release

| Area | Change | Evidence |
|---|---|---|
| Server-side plans | `remediation_plans`, `remediation_tasks`, `remediation_deadline_changes` models | `backend/app/db/models.py` |
| API | 5 authenticated, institution-scoped routes | `backend/app/api/v1/remediation_plans.py` |
| Rules | Idempotent create, versioned task updates, policy rescheduling | `backend/app/services/remediation_plan_service.py` |
| RBAC | `plan:read`, `plan:write`, `plan:policy` mapped to existing roles | `backend/app/core/rbac.py` |
| Migrations | `j0e1f2a3b4c5`, `k1f2a3b4c5d6` (additive, one head) | `backend/alembic/versions/` |
| Frontend | Shared plan panel with local fallback | `RemediationActionPlan.tsx`, `lib/plan-sync.ts`, `lib/action-plan.ts` |
| Guidance | EN/हिन्दी deficiency text, clause mapping | `lib/compliance-guidance.ts`, `lib/aicte-rules.ts` |
| Readiness | Weight breakdown published in the UI | `NilDeficiencyGapPredictor.tsx` |
| Deploy fix | Render Alembic command corrected | `render.yaml` |
| Docs | 14 product documents + Phase 1/3 and readiness reports | `PROJECT_DOCUMENTATION/`, `PHASE_3_PLAN.md`, `PRODUCTION_READINESS_REPORT.md` |

No existing route, request schema, response contract, layout, route or auth flow was removed or
renamed. `git diff --stat` for tracked files: 9 files, +348/−41.

## 2. Audit results

- **Secrets:** none. Scanned for private keys, service-role keys, cloud access keys, GitHub/Slack
  tokens across source, docs, JSON and YAML — zero matches. `.env`, `*.db`, `__pycache__` are
  gitignored and untracked. The only credential-like strings are the public seeded demo accounts used
  by `seed`/the manual probe (`admin/admin123456`), which are created by `/api/v1/seed` in
  non-production mode only.
- **Overwritten canonical docs:** none. `git status` shows no modification to `README.md`,
  `PRD.md`, `ARCHITECTURE.md`, `WORKSTREAMS.md` or `docs/canonical/*`.
- **Environment leakage in tooling:** `scripts/live_plan_probe.py` contained an absolute
  `/Users/.../worktrees/...` import path and a fixed `/tmp` database. Fixed to resolve the repo from
  `__file__` and to take `PROBE_DB`/`PROBE_BASE` from the environment.
- **Duplication:** the plan service keeps all tenant resolution in the route module's
  `_resolve_institution` and reuses the shared `ReviewAuditRepository`; no second copy of audit,
  membership or hash logic was introduced.

## 3. Test results (fresh, final tree)

| Check | Command | Result |
|---|---|---|
| Backend | `/tmp/aicte-venv/bin/python -m pytest -q` | **493 passed, 21 skipped**, 70.1 s |
| Frontend | `npm test` | **47 passed, 0 failed** |
| Types | `npx tsc --noEmit` | clean |
| Build | `npm run build` | success |
| Lint | `npm run lint` | 0 errors, 5 pre-existing warnings, 52 files |
| Docs links | `pytest backend/tests/test_docs_links.py` | pass |
| OCR | `test_ocr_engine_integration.py` (venv with `requirements-ocr.txt`) | pass |

Skipped tests are all live-infrastructure tests gated on external credentials; no test was deleted,
skipped or weakened for this release.

## 4. Migration safety

No production database is reachable from this environment, so the required backup cannot be made and
**no migration was applied anywhere**. Instead the exact upgrade path was exercised on a synthetic
database containing representative rows (institution, user, membership, application, audit event):

1. `upgrade i9d0e1f2a3b4` → 21 tables.
2. Insert representative rows; record counts.
3. `upgrade head` → plan tables created; all counts unchanged.
4. Duplicate `(institution_id, plan_key)` → `IntegrityError`, as designed.
5. `downgrade j0e1f2a3b4c5` → only the history table dropped.
6. `downgrade i9d0e1f2a3b4` → plan/task tables dropped; all original counts unchanged.
7. `upgrade head` → clean re-apply.

Both revisions carry real `downgrade()` implementations, so rollback is a two-step
`alembic downgrade i9d0e1f2a3b4` that touches no pre-existing table.

## 5. Backend selection

The repository's backend is the only one that implements the complete contract the repository
frontend needs (auth, applications, institutions, validation runs, document analysis, compliance,
plans) — 48 paths versus 25 on Render and 8 on the production-domain API. If this repository is to be
released, **Render** (the service declared in `render.yaml`) is the correct host, because it is the
only deployed backend that belongs to this codebase.

It must not be treated as the backend of the production website: that site calls its own Vercel-hosted
API, authenticated by a Supabase project embedded in a build that is not in this repository. Details
and evidence: [PRODUCTION_READINESS_REPORT.md](PRODUCTION_READINESS_REPORT.md) §1–2.

## 6. What was not done, and why

| Step | Status | Blocker |
|---|---|---|
| Backup production DB | **Blocked** | No connection string or hosting credentials for the production database |
| Apply migrations to production | **Blocked** | Same; applying without a backup violates the release rule |
| Deploy backend to Render | **Blocked** | No Render API key; the build command is now fixed, but a deploy would run the migration |
| Deploy frontend | **NO-GO** | The production domain runs a different codebase; replacing it is a product migration |
| Live backend probe (Step 5) | **Not run against production** | No deployable backend and no test accounts in the production DB; the identical probe passes locally |
| Verify production URL | **Impossible as specified** | The URL serves an application whose source is not in this repository |

## 7. Deployment sequence once access is granted

1. `git checkout main && git merge --ff-only release/phase-1-remediation-plans` (or merge the PR).
2. Take a database snapshot from the Render dashboard; record its timestamp.
3. Deploy Render. The build now runs `python -m alembic -c backend/alembic.ini upgrade head`;
   confirm `j0e1f2a3b4c5` and `k1f2a3b4c5d6` appear in `alembic_version`, and `/openapi.json` reports
   48 paths.
4. Run `PROBE_BASE=https://aicte-compliance-api-preview.onrender.com PROBE_DB=... python
   scripts/live_plan_probe.py` with synthetic accounts created through `/api/v1/seed` (staging only).
5. Deploy the frontend to the repository's Vercel project with `VITE_API_BASE_URL` pointing at
   Render; verify sign-in, validation, history, Cadre/FSR, guidance, readiness and the plan panel.
6. Only then decide, as a separate product decision, whether the production domain should be
   repointed at this application.

## 8. Rollback

- Application: redeploy the previous Render build (dashboard "Rollback"), then
  `python -m alembic -c backend/alembic.ini downgrade i9d0e1f2a3b4` if the schema must revert.
- Frontend: promote the previous Vercel deployment.
- Data: plan/task/history rows live only in the new tables, so no existing row is rewritten by this
  release; dropping the new tables loses plan progress only, which is expected.
