# Production Readiness Report

Date: 2026-10-31. Scope: release preparation for the uncommitted Phase 1 work in this repository.
All production statements come from unauthenticated HTTP probes made today; all local statements
come from commands whose output is recorded in [RELEASE_REPORT.md](RELEASE_REPORT.md) and
[REGRESSION_TEST_REPORT.md](REGRESSION_TEST_REPORT.md).

**Nothing was deployed, migrated, pushed to `main`, or reconfigured in a hosting dashboard.**

---

## 1. There are three distinct backends, not two

| # | Surface | Version | Paths | What it is |
|---|---|---|---|---|
| 1 | `https://aicte-compliance-ai.vercel.app` (the "production" domain) | **0.4.0** | 8 | A separate Vercel-hosted API at the same origin. Serves the website the user calls production. |
| 2 | `https://aicte-compliance-api-preview.onrender.com` | 0.3.1 | 25 | The repo's Render service (`render.yaml`), an **older** deployment of this code. |
| 3 | Repository working tree | 0.3.1 + unreleased | 48 | The full hardened API, including the new plan routes. |

The frontend served on the production domain is **not built from this repository**. Evidence:

- Its bundle is `assets/index-D0Wiwpzv.js` (749,615 B). The repo's own Vercel project serves
  `assets/index-DgCmBDo5.js` (540,906 B).
- The production bundle contains a hardcoded Supabase client (`https://qhclgxquuiqijlsbsouc.supabase.co`
  with a publishable key), a Document Vault, and institution-level `/api/v1/documents` calls. None of
  these strings exist anywhere in this repository or its history (`git log -S "Document Vault"` is empty).
- The production bundle has **zero** references to `onrender.com`; the repo bundle has exactly one,
  because the repository frontend defaults to the Render origin.

Vercel commit statuses exist for this repository (`aicte-compliance-frontend`), so the repo has its
own Vercel project — it is simply a **different project** from the one serving the production domain.

## 2. API compatibility matrix

Legend: ✅ present, ❌ absent.

| Endpoint | Production domain API | Render | Repo working tree |
|---|---|---|---|
| `/api/v1/validate` | ✅ | ✅ | ✅ |
| `/api/v1/auth/token`, `/api/v1/auth/me` | ❌ | ✅ | ✅ |
| `/api/v1/institutions` (lookup) | ✅ | ❌ | ✅ |
| `/api/v1/validation-runs` (list/create/get/delete) | ✅ | ❌ | ✅ |
| `/api/v1/applications*`, documents, reviews, audit packages | ❌ | ✅ | ✅ |
| `/api/v1/documents/analyze` | ✅ | ❌ | ✅ |
| `/api/v1/documents` (institution library) | ✅ | ❌ | ❌ |
| `/api/v1/compliance/*` (rules, retention, verification) | ❌ | ❌ | ✅ |
| `/api/v1/institutions/{ref}/remediation-plans*` | ❌ | ❌ | ✅ |
| `/health` | ✅ | ✅ | ✅ |

No single deployed backend satisfies the repository frontend. The repository frontend calls
`auth/token` + `institutions` + `validation-runs` + `documents/analyze` + plans; only the repo backend
provides all of them, and it is not deployed anywhere.

## 3. Deployment defect found and fixed

`render.yaml` declared:

```bash
cd backend && python -m alembic upgrade head
```

`backend/alembic.ini` sets `script_location = backend/alembic`, so from inside `backend/` Alembic
looks for `backend/backend/alembic` and aborts:

```
FAILED: Path doesn't exist: backend/alembic. Please use the 'init' command ...
```

Reproduced locally. Any build using the declared command fails before the service starts, which is
consistent with Render still serving a 25-path build. Corrected to:

```bash
python -m alembic -c backend/alembic.ini upgrade head
```

The same command appears in `PROJECT_DOCUMENTATION/TECHNICAL_ARCHITECTURE.md`,
`PROJECT_DOCUMENTATION/DATABASE_AND_DATA_FLOW.md` and `PRODUCTION_ROLLOUT_PLAN.md`; all corrected.

## 4. Local verification (final tree)

| Check | Result |
|---|---|
| Backend `pytest -q` | **493 passed, 21 skipped** (skips are live-infra only) |
| Frontend `npm test` | **47 passed, 0 failed** |
| `npx tsc --noEmit` | clean |
| `npm run build` | success |
| `npm run lint` (oxlint) | 0 errors, 5 pre-existing warnings, 52 files |
| Alembic heads | exactly one: `k1f2a3b4c5d6` |
| Migration scenario on synthetic data at `i9d0e1f2a3b4` | upgrade → data intact, unique constraint enforced, downgrade → only new tables dropped, re-upgrade OK |

## 5. Production risks that block a release today

1. **The production domain is a different product.** Deploying this repository over it would replace
   an application whose source is not here, dropping the Document Vault and changing auth from
   Supabase to backend-issued JWTs. That is a product migration, not a release.
2. **No credentials for the authoritative surfaces.** No Vercel token (CLI absent), no Render API key,
   and no production database connection string. Render rebuilds and domain cutovers cannot be
   triggered or verified from this environment.
3. **No production database backup possible.** `render.yaml` points at a Render-managed Postgres, but
   the connection string is not available here, so the required pre-migration backup cannot be taken.
   The migrations are additive and downgrade-tested, but the user's own release rule requires a
   recoverable backup before applying them.
4. **Production auth cannot be exercised.** The production API exposes no login route; its frontend
   relies on a hardcoded Supabase project. Creating test accounts there would write real rows to a
   database this release does not own.
5. **Render is stale and its build was broken** (§3), so "deploy" there would also be the first
   successful build in some time — an unverified path.
6. **Repo staging would still be unusable for sign-in.** With `ENABLE_DEMO_ENDPOINTS` off, the repo
   backend has no self-service signup, so a fresh staging deployment cannot create an account to
   verify shared plans without seeding users.
7. **No rate limiting / gateway** on either deployed backend.
8. **Backend tokens are kept in `localStorage`** in native-auth mode.

## 6. Go / No-Go

| Decision | Verdict | Reason |
|---|---|---|
| Merge the Phase 1 branch after review | **GO** | Tests green, additive migrations, one head, defect fixed |
| Deploy to the production domain (`aicte-compliance-ai.vercel.app`) | **NO-GO** | Different codebase; would replace an unowned product |
| Deploy the repo frontend to its own Vercel project | **CONDITIONAL** | Requires a deployed repo backend; otherwise its API calls fail |
| Deploy the repo backend to Render | **CONDITIONAL** | Blocked on Render access **and** a DB backup; additive migration is safe once backed up |
| Claim production runs this release | **NO** | Production still serves the other application |

**Overall: release candidate is ready and verified locally; production deployment is blocked on
ownership and credentials for the production domain and its database, not on code.**
