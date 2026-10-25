# Deployment runbook — Render backend and Vercel check disposition

**Status as of 2026-10-25.** Everything in this file is labelled by evidence
type: *CI real-infra* (PostgreSQL 16 + Redis 7 + ClamAV service containers on
GitHub Actions — non-production evidence), *live* (probed from outside), or
*owner action required* (needs provider access this workspace does not have).
Nothing here is a claim that the production deployment works.

## 1. Verified state

| Surface | State | Evidence |
|---|---|---|
| CI on the delivery branch | 4/4 jobs green | `real-infrastructure-integration` runs the full upload → scan → extract → persist → terminal-status path against real PostgreSQL, Redis, a real Celery worker subprocess and a live ClamAV daemon (EICAR detected live in CI); `backend-tests` runs the unit/contract suite |
| Recovery sweep (outbox + retry_wait + lost queued jobs) | implemented and tested | `backend/app/core/dispatcher.py::run_recovery_sweep`, scheduled by Celery beat every 30s (`backend/app/worker/celery_app.py`); unit + real-infra tests |
| Strict readiness | implemented | `GET /health/ready` — 200 only when database, migrated schema, a positively-scanning malware engine and writable private storage all pass; 503 with per-component detail otherwise (`backend/tests/test_readiness.py`) |
| Render backend (https://aicte-compliance-api-preview.onrender.com) | **NOT serving** | Live probe on 2026-10-25 returned Render's "Application loading" interstitial, not the API. No worker service, no ClamAV daemon and no durable shared storage are configured there |
| Vercel check | **obsolete integration, failing** | The `aicte-compliance-frontend` Vercel project builds a frontend that does not exist in this repository (`frontend/` holds a README, fixtures and a fixture-verification tool — no UI app). Every commit fails this check by construction, e.g. `dpl_4MxXE3pqSasa5UngRNRACEN2JHzg` on `ecb4e4c` |

## 2. Architecture: one Docker service (do not split it)

`render.yaml` + `Dockerfile` + `scripts/render_entrypoint.sh` implement the
lowest-complexity architecture that satisfies the security gates with the
storage backend that actually exists (`LocalStorageBackend`, local disk):

```text
one Render web service (one container, one disk mounted at /data)
├── clamd            — real ClamAV scan gate, loopback 127.0.0.1:3310 only
├── celery worker    — with embedded --beat (the 30s recovery sweep)
└── uvicorn          — FastAPI on $PORT
```

**Why one service:** the storage backend is local-disk and a Render disk is
attached to exactly one service. A separate worker service could not read the
API's uploads — processing would break silently. Until an object-storage
backend is implemented and tested, keep API and worker together. Scaling to
multiple instances requires moving beat to a single standalone `celery beat`
first (the sweep is idempotent, but it must be scheduled exactly once).

**Fail-closed boot:** the entrypoint refreshes ClamAV signatures, starts clamd
and waits for `zPING`, runs `alembic upgrade head`, then starts worker and
API. If clamd cannot start (no signatures, daemon failure) the instance exits
and Render restarts it — it never serves traffic with the quarantine fallback
active.

## 3. Owner actions to deploy (Render)

1. **Merge the delivery PR** (or set `branch:` in `render.yaml` to the
   delivery branch first).
2. **Create the database** (the blueprint defines `aicte-compliance-db`; the
   app normalizes `postgres://`/`postgresql://` to the psycopg2 driver, so
   Render's connection string works as-is).
3. **Create a Render Key Value (Redis) instance** on private networking —
   never public, never with a `0.0.0.0/0` allowlist. Copy its **internal**
   redis URL into `CELERY_BROKER_URL` and `REDIS_URL` on the service
   (`sync: false` keeps the blueprint from overwriting them).
4. **Create the web service** via "New Blueprint" with this repository's
   `render.yaml` (or "New Web Service" → Docker runtime → root `Dockerfile`,
   then set the same env vars by hand): disk 1 GB mounted at `/data`, health
   check path `/health`.
5. **Environment variables** (names only — set real values in the dashboard,
   never in git): `DATABASE_URL`, `CELERY_BROKER_URL`, `REDIS_URL`,
   `JWT_SECRET_KEY` (≥32 chars; the blueprint generates one), `CLAMAV_HOST=127.0.0.1`,
   `CLAMAV_PORT=3310`, `STORAGE_LOCAL_DIR=/data`. They are documented with
   their readers in [`.env.example`](../../.env.example).
6. **Instance type:** do not use the free tier for real processing — it sleeps,
   which stalls the worker and the recovery sweep between requests.

Plan names in `render.yaml` reflect Render's catalogue as of 2026-10 and may
need adjusting when the blueprint is first imported (the editor validates and
will say). The Dockerfile/entrypoint/blueprint were syntax-checked only — this
workspace has no Docker or Render access, so the first deploy is the real test.

## 4. Post-deploy live verification (owner, against the real URL)

Use a **disposable** test identity/application and a **synthetic** PDF only
(the deterministic builder used in tests:
`backend/tests/integration/test_redis_celery_worker_processing.py::_create_synthetic_pdf`;
never a real institutional or personal document).

1. `GET /health` → 200 `{"status": "ok", "service": "aicte-compliance-assistant"}`.
2. `GET /health/ready` → **200 `status: "ready"`** with all four checks ok.
   A 503 is the honest signal to stop: its `checks` name the failing
   component (database / schema / malware_scanner / storage).
3. Register the disposable user, create an institution + application, upload
   the synthetic PDF → expect document/version/job/outbox created and the job
   dispatched.
4. Poll the job to a terminal state (`completed`/`partial`) and confirm the
   extracted fields persisted and the document `scan_status` is `clean`.
5. Scanner proof on production: a clean upload scanning `clean` plus
   `malware_scanner: ok` in `/health/ready`. **Do not upload EICAR (or any
   malware sample) to production** — EICAR detection is already proven in the
   isolated CI environment (live clamd log line
   `instream(...): Eicar-Test-Signature FOUND`).
6. Tenant isolation: a second tenant must get `404 Resource not found or
   access denied.` (concealment) for the first tenant's document.

## 5. Vercel check — obsolete integration, exact disposition

The failing Vercel check is an **external project misconfiguration**, not a
code defect: the Vercel project `aicte-compliance-frontend`
(`raj-aryans-projects-f2e9eead`) is connected to this repository but there is
no frontend application in the tree to build, so every deployment fails
(e.g. `dpl_4MxXE3pqSasa5UngRNRACEN2JHzg`, status `failure`, on `ecb4e4c`).

**Do not create fake UI files to make it green.** The only correct fixes are
owner actions in the Vercel dashboard:

- remove the Git integration / delete the obsolete
  `aicte-compliance-frontend` project (the check disappears from future
  commits), or
- leave it disabled until the frontend workstream delivers a real app, then
  point the project at that app with the API base URL documented in
  [`API_CONTRACT.md`](API_CONTRACT.md).

Until one of those happens, treat the Vercel check as permanently failing and
non-blocking. The Render frontend configuration is separate and unchanged.

## 6. Product gates still open (by design, not deployment defects)

Retention/deletion controls · verified official AICTE source applicability and
the rule evaluator (rule activation stays blocked) · Phase 0 official-source
verification · real-world OCR benchmarking (all corpora are synthetic) ·
scanned-PDF OCR fallback · a standalone `POST /api/v1/ocr` (extraction is part
of the document pipeline only). Until the security-relevant ones are complete
and security-tested, production use is **NO-GO** regardless of green CI.
