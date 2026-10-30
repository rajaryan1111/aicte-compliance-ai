# Production Rollout Plan — remediation plan persistence

Status: **review-ready, not deployed.** Nothing in this change has been pushed or deployed.
Evidence below was observed on 2026-10-31; re-verify before acting on it.

---

## 1. What production runs today (probed, not assumed)

| Surface | URL | Version | Routes | Notes |
|---|---|---|---|---|
| Website | `https://aicte-compliance-ai.vercel.app` | bundle `index-D0Wiwpzv.js` | — | Contains no `remediation`/`actionPlans` code, so none of the three new features are live |
| Website API (same-origin) | `https://aicte-compliance-ai.vercel.app/api/...` | `0.4.0` | 8 paths / 11 ops | Proxied to the "live" prototype backend |
| Live prototype backend | `https://aicte-compliance-backend-live.vercel.app` | `0.4.0` | 8 paths / 11 ops | `/documents`, `/documents/analyze`, `/validate`, `/validation-runs*`, `/institutions`, `/health` |
| Render backend | `https://aicte-compliance-api-preview.onrender.com` | `0.3.1` | 25 paths / 29 ops | Enterprise core: auth, applications, documents, reviews, audit packages, `/validate`; **no** `/validation-runs`, `/institutions`, `/documents/analyze`, no plan routes |
| Repository working tree | local | `0.3.1` | **47 paths / 54 ops** | Strict superset of Render, plus the remediation-plan routes |

Consequences, stated plainly:

* The current production website is served by an **older frontend**; the repository `main` is far
  ahead of it.
* The repository backend is a **strict superset of Render** (no Render route is missing locally),
  so upgrading Render in place does not break the deployed API.
* The repository backend is **not** a superset of the `0.4.0` prototype: `GET /api/v1/documents`
  and `GET /api/v1/documents/{document_id}/download` are not implemented. No current frontend code
  calls them (`grep` over `frontend/app/src` returns only `/documents/analyze`), but an external
  caller of the prototype would notice.
* The production frontend bundle was built without a base URL, so it calls its own origin. The
  repository's `lib/api.ts` now defaults to the Render base URL when `VITE_API_BASE_URL` is unset
  in a production build. **This must be checked before deploying the frontend**, or the browser
  will call a backend that does not have the new routes.
* Probed directly, today's Render answers `POST /api/v1/validate` with `422` (route exists, payload
  incomplete) but `POST /api/v1/validation-runs` and `POST /api/v1/institutions` with `404`. Both are
  called by the repository frontend (history and institution lookup), so **today's Render cannot
  serve the current frontend build**. The repository backend implements both; upgrade Render from
  this tree first, then deploy the frontend. Do not reorder these two steps.

## 2. Compatibility of this change

| Aspect | Impact |
|---|---|
| Database | Additive only: `remediation_plans`, `remediation_tasks` (revision `j0e1f2a3b4c5`) and `remediation_deadline_changes` (revision `k1f2a3b4c5d6`). Single head `k1f2a3b4c5d6`. Upgrade from an existing plan-revision database was verified in place on SQLite; downgrade drops only these tables. |
| Existing API | No route, request or response schema changed. Five new routes added under a new prefix. The plan response gains an additive `deadline_history` array. |
| RBAC | Three new permissions (`plan:read`, `plan:write`, `plan:policy`); all five roles keep their existing access. Only institution admins and super admins may reschedule. |
| Frontend | Additive panel; the three new modules are only imported by `ValidationResults.tsx`. |
| Behaviour when the backend is old | `syncPlan` receives 404/405 and the panel reports that shared storage is unavailable for this account or deployment, then finishes with "Not saved to the server. Progress stays in this browser." Local progress continues to work; no crash, no data loss. The 404 message names both causes (unlinked account, older backend) because the two are indistinguishable from the client. |
| Behaviour when signed out | Same local-only mode as before this change. |
| Cost | No paid third-party calls. Render free plan + Neon/Postgres already in use. |

## 3. Pre-deployment checklist

1. `python -m alembic -c backend/alembic.ini heads` from the repo root → exactly one head,
   `k1f2a3b4c5d6`.
2. Back up the production database (or confirm the Render snapshot/Neon PITR window).
3. Confirm Render env vars: `DATABASE_URL`, `JWT_SECRET_KEY`, `CORS_ALLOWED_ORIGIN=https://aicte-compliance-ai.vercel.app`,
   `PYTHONPATH=/opt/render/project/src`, `CELERY_TASK_ALWAYS_EAGER=true`.
4. Confirm Vercel env for the frontend. Either:
   * set `VITE_API_BASE_URL` to the upgraded backend origin and keep CORS as above, or
   * set it to empty **only if** Vercel rewrites `/api/*` and `/health` to that backend.
   Record which option was chosen; they are not interchangeable.
5. Freeze writes during the migration window (no known long-running jobs; the migration is two
   `CREATE TABLE`s, so seconds).

## 4. Deployment order

Backend first, frontend second. Each step is independently reversible.

1. **Merge the backend changes** (routes, service, schemas, RBAC, migration, exceptions).
2. **Deploy the backend to Render.** `render.yaml` runs
   `python -m alembic -c backend/alembic.ini upgrade head` from the repository root, so the
   migration applies before the new process starts. (The previous `cd backend && alembic` form
   could not resolve `script_location` and would fail the build — corrected 2026-10-31.)
3. **Verify the backend** (§5.1) before touching the frontend.
4. **Deploy the frontend** to Vercel with the base URL from step 3 of the checklist.
5. **Verify the website** (§5.2).

## 5. Post-deployment verification

### 5.1 Backend

```bash
BASE=https://aicte-compliance-api-preview.onrender.com

curl -s $BASE/health
curl -s $BASE/openapi.json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["paths"]))'
# expect five remediation-plan paths (including deadline-policy); count should rise to 48

# unauthenticated calls must be 401, not 404
for p in "" "/1"; do
  curl -s -o /dev/null -w "%{http_code}\n" "$BASE/api/v1/institutions/SYNTH-1/remediation-plans$p"
done

# no sign of the old unauthenticated behaviour: a bogus token must be 401
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer bogus" \
  "$BASE/api/v1/institutions/SYNTH-1/remediation-plans"
```

Or run the same checks as one command against any base URL that already has the plan routes:

```bash
cd <repo>
PROBE_BASE=$BASE /tmp/aicte-venv/bin/python scripts/live_plan_probe.py
# creates synthetic users in the target DB — use only on a staging database, never production
```

`scripts/live_plan_probe.py` asserts 19 behaviours (401, 201/200 idempotency, version bump, stale
409 with `x-current-version`, progress preservation, 403 for a read-only role, 404 for a foreign
tenant, 422 for three invalid payloads, and audit rows). It writes synthetic accounts directly to
SQLite, so it is a **staging-only** tool.

Then, with two real accounts in two different institutions:

1. Create a plan as user A; confirm `201`.
2. Re-post the identical body; confirm `200` and the same `id`.
3. Update a task with the returned `version`; confirm `200` and `version + 1`.
4. Repeat the update with the stale version; confirm `409` and `X-Current-Version`.
5. Read the same plan as user B (other institution); confirm `404`.
6. Read as an auditor in A's institution; confirm `200`, and confirm a PATCH as that auditor is `403`.
7. Send `PATCH .../deadline-policy` as a scrutiny officer; confirm `403`.
8. Send the same PATCH as an institution admin; confirm `200`, moved due dates, and one new
   `deadline_history` entry with the actor. Repeat it; confirm the history does not grow.

### 5.2 Website

1. Open the Validate page, load a preset, run validation.
2. Signed out: the plan shows "Not saved to the server. Progress stays in this browser."
3. Sign in, reload the results: the panel shows "Saved to this institution's workspace."
4. Change a task status in one browser, reload in another signed-in browser: the status persists.
5. Confirm the browser console has no failed `/remediation-plans` requests and no CORS errors.

## 6. Rollback

| Layer | Action | Effect |
|---|---|---|
| Frontend | Redeploy the previous Vercel build | Panel disappears; no backend call is made |
| Backend code | Redeploy the previous Render build | Routes return 404; frontend falls back to local-only mode |
| Database | `alembic downgrade -1` | Drops `remediation_tasks` then `remediation_plans`; **deletes stored plans** |

Downgrade is safe for every other table because the migration only creates two new tables and no
foreign keys point at them. Export any plans you intend to keep before downgrading; the CSV export
in the UI is the supported way to do that.

## 7. Remaining risks

1. **Two backend deployments.** Render and the `0.4.0` prototype serve different route sets. Until
   one is retired, a route existing in one says nothing about the other. Recommended: point the
   website at one backend and remove the Vercel proxy to the prototype.
2. **No rate limiting or gateway** on either backend. The new routes are authenticated and are not
   expensive, but an authenticated client can still create plans in a loop. Consider a per-account
   quota before public launch.
3. **Plans are not linked to a validation run id.** They are keyed by institution + deficiency
   signature, which is what makes re-validation idempotent, but it also means a plan is not a
   legal record of one specific run. If that is required, store `checked_at`/run id alongside.
4. **No notification delivery.** Due dates are visible but nothing reminds anyone. Email/WhatsApp
   reminders need a provider and consent.
5. **Deadline semantics.** The policy is internal. Do not let it appear in any outward-facing
   document without the disclaimer that already ships in the API `notice` and the UI.
6. **Clause text unverified.** The plan cites clauses from the project catalog; those citations
   remain unverified against the official APH and the panel says so per task.
7. **Storage is a local filesystem on Render.** Unrelated to this change, but document downloads
   will still 404 after a restart until object storage is configured.
