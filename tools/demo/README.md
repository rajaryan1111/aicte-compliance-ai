# Local demo harness

Everything needed to run the SIH demo on one machine. Nothing here is production code.

| File | Purpose | Security note |
|---|---|---|
| `seed_demo.py` | Provisions the demo operator + institution (the API has no registration route) | Writes only to `DATABASE_URL`; never prints or stores the password |
| `dev_scanner_testdouble.py` | Speaks the clamd protocol so intake can proceed without a real scanner | **PERFORMS NO SCANNING.** Loudly labelled; test/demo only |

## Why the two scripts exist

Both work around **correct product behaviour**, not product bugs:

- **No registration endpoint** — an institutional system should not allow self-signup. So a
  fresh database legitimately has no users and login can only return 401. `seed_demo.py` is the
  documented, operator-run provisioning step.
- **The malware gate fails closed** — with no scanner configured, every upload is quarantined
  and never processed. That is the security control working. The test double is for local demos
  only and is never wired into product configuration.

## Full local run

```bash
# 0. from the repository root, install backend + frontend dependencies
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
(cd frontend && npm install)

# 1. database
export DATABASE_URL="sqlite:///./demo.db"
python -m alembic -c backend/alembic.ini upgrade head

# 2. REQUIRED: auth raises HTTP 500 without a >=32 character JWT secret
export JWT_SECRET_KEY="local-demo-secret-key-at-least-32-chars-long"

# 3. run background jobs inline so Redis + a worker are not needed
export CELERY_TASK_ALWAYS_EAGER=true

# 4. provision the demo operator
python tools/demo/seed_demo.py --username demo --password 'demo-pass-123'

# 5. scanner: EITHER a real ClamAV (production-like) ...
#      export CLAMAV_HOST=127.0.0.1 CLAMAV_PORT=3310
#    ... OR the labelled test double, in a second terminal (local demo only):
python tools/demo/dev_scanner_testdouble.py --port 3310
export CLAMAV_HOST=127.0.0.1
export CLAMAV_PORT=3310

# 6. API
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

# 7. UI (separate terminal) — http://localhost:5173
cd frontend && npm run dev
```

Sign in with `demo` / `demo-pass-123`, create an application, upload a **synthetic**
document, watch scan → processing → extraction, then run pre-scrutiny.

## Synthetic demo document

The extractor matches specific English/Hindi labels. A document that does not use them
yields **zero** extracted fields (correctly — nothing is invented). Minimal synthetic PDF
content that extracts five fields:

```
DEMO INSTITUTE OF TECHNOLOGY
SYNTHETIC DEMO DOCUMENT - NOT A REAL AICTE CERTIFICATE
Institution Name: Demo Institute of Technology
Certificate No.: AICTE/DEMO/2026/001
Date of Issue: 2026-07-01
Valid Upto: 2027-06-30
Academic Year: 2026-2027
```

To build one without extra dependencies, see the generator used during verification
(`make_synthetic_pdf` in the integration notes): it writes a single-page PDF with a
Helvetica `Tj` text stream, which `pdfplumber` reads.

## Real-worker path (TLS broker, verified 2026-10-25)

The eager path above runs everything in one process. The presentation-quality path drives a
**real Celery worker over a verified-TLS broker** — the same code a deployed service uses.
Verified end-to-end on 2026-10-25: upload → verified-TLS publish → worker claim → real ClamAV
scan → extraction → `processing_status: succeeded`, and a failed outbox message recovering
through the retry sweep.

TLS is mandatory for `rediss://` URLs: `backend/app/worker/celery_app.py` attaches
`CERT_REQUIRED` redis-py options automatically (override CA with `REDIS_SSL_CA_CERTS`), so a
plain `rediss://` URL is already correct — there is no bypass switch. The bootstrap module is
still useful locally because it also defaults ClamAV and storage paths.

```bash
# broker+result: point CELERY_BROKER_URL at a TLS-secured Redis (rediss://…) in .env
# then, from the repo root:
.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
.venv/bin/celery -A local_worker_bootstrap:celery_app worker --loglevel=INFO -P solo &   # macOS
.venv/bin/celery -A local_worker_bootstrap:celery_app beat   --loglevel=INFO &          # retry sweep
.venv/bin/celery -A local_worker_bootstrap:celery_app worker --loglevel=INFO            # Linux
```

Notes:

- **`-P solo` is macOS-only**: this Mac's prefork pool aborts; Linux (and CI) used prefork fine.
- **The CLI form matters**: `celery -A local_worker_bootstrap:celery_app worker`, *not*
  `python -m local_worker_bootstrap` — the module has no `main`, so `-m` imports and exits
  silently.
- **A beat must be running** for retry_wait jobs and for failed outbox messages (below the
  retry cap) to be republished; the worker log line `Outbox recovery: N failed message(s),
  N republished` confirms it.
- A failed dispatch is recoverable by design: the message stays in the outbox and the periodic
  sweep republishes it once the broker is back.

## What the demo does and does not prove

- **Does**: the real backend pipeline (upload → scan gate → processing → extraction →
  validation → findings → review summary) driven by the real UI.
- **Does not**: real OCR accuracy, regulatory compliance, or document authenticity. Regulatory
  rules are inactive by design while Phase 0 gates remain open, so the
  `CHECK_OFFICIAL_REGULATORY_RULES` check reports `not_run`.
