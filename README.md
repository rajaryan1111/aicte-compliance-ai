# AICTE Compliance Assistant

A prototype for **preliminary checklist validation**, **secure institutional-document
intake**, and **advisory institutional-document OCR**. It does not authenticate
documents, verify institutional status, or decide regulatory compliance.

## What is implemented

### 1. Checklist validation — caller-supplied data only
`POST /api/v1/validate` compares the `required_documents` / `submitted_documents`
lists and `expiry_dates` supplied in the request. It returns missing and expired
documents with `validation_scope: "caller_supplied_checklist_only"`.

- The service loads no AICTE checklist and no rule set; the caller supplies both lists.
- `preliminary_checks_passed` means only that the supplied lists agree. It is not a
  compliance, eligibility, or authenticity finding.

### 2. Document intake pipeline (FastAPI + PostgreSQL)
`backend/app/` implements an authenticated document intake and review pipeline:

- **Authentication and RBAC** — JWT bearer auth, users and institution memberships,
  three roles (`institution_admin`, `scrutiny_officer`, `auditor`) with
  server-side permission checks (`backend/app/core/rbac.py`, `backend/app/api/deps.py`).
- **Institution tenant isolation** — every application, document, review and
  audit route resolves ownership server-side; cross-tenant reads are concealed
  with `404` (`verify_institution_membership`), role denials use `403`.
- **Private document storage** — opaque server-generated storage keys
  (`docs/{prefix}/{uuid}{ext}`), directory-traversal and volume-qualified key
  rejection, atomic writes (`backend/app/core/storage.py`).
- **Upload validation** — size, extension, MIME and content checks with
  deterministic rejection paths (`backend/app/core/upload_validator.py`).
- **Fail-closed malware gate** — a ClamAV `clamd` INSTREAM client; when no
  scanner is reachable the file stays quarantined and never reaches OCR
  (`backend/app/core/scanner.py`).
- **Asynchronous processing** — durable `ProcessingJob` state machine with
  retry backoff and attempt limits, a transactional outbox dispatcher and a
  Celery worker (`backend/app/worker/`); jobs run scan → PDF text extraction
  or OCR → persisted evidence and advisory findings.
- **Review workflow and audit packages** — attributable review actions
  (acknowledge / comment / resolve / reopen / escalate), immutable validation
  snapshots, and tamper-evident audit package export with Merkle root
  verification (`backend/app/services/audit_package_service.py`).
- **Persistence** — SQLAlchemy 2 models and Alembic migrations for SQLite
  (local dev/tests) and PostgreSQL (integration and deployment).

### 3. Advisory OCR — optional engine, local only
`backend/app/ocr_pipeline.py` implements an engine-neutral OCR contract
(`ocr_adapter.py`), an optional Tesseract adapter, field extraction for a small set
of context-labelled institutional fields (English and selected Hindi labels), and a
local CLI: `python -m backend.app.ocr_cli <image>`.

Implemented input/output limits: 10 MiB compressed bytes, 30 megapixels,
JPEG/PNG/TIFF/WEBP only, a 100,000-character aggregate OCR text budget, strict ISO
`YYYY-MM-DD` dates (ambiguous formats stay unresolved), single-year academic sessions
only, engine confidence confined to `0.0–1.0`, page/line/evidence provenance, source
SHA-256, and `requires_human_review=True` on every result.

- OCR output is evidence for a human reviewer, never proof of authenticity. The
  pipeline is used inside the document intake flow **after** the clean-scan gate;
  `extract_institution_fields` itself makes no external call.
- **No real-world accuracy claim is made.** The corpora in `ai/corpus/` and
  `backend/tests/fixtures/` are synthetic regression data (56 extraction cases +
  30 OCR-corruption cases, all scored, 0 known gaps after the 2026-10-25
  extractor rework), not a labelled held-out benchmark; the Tesseract test is a
  synthetic smoke test. Every accuracy number in `ai/EVALUATION.md` describes
  those synthetic corpora only.
- PDF inputs to the OCR **adapter** are rejected as unsupported images; the
  document pipeline extracts PDF text layers natively (pdfplumber). A scanned
  PDF with no text layer yields no fields (reported as partial) — OCR fallback
  on scanned PDFs is **not implemented**. Multi-page/multi-frame image files are processed from the first
  frame only and report a warning; submit pages separately. Bounding boxes are
  not recorded. Hindi coverage is label extraction plus synthetic text fixtures
  only — the optional engine test is English.
- Engine output is validated before use. `text` and `conf` are **required** columns and
  must be equal-length sequences; `page_num`/`line_num` are optional (default 1) but must
  align with `text` if present. A missing required column, a length mismatch, or a
  non-string `text` value raises an engine error instead of yielding a success-shaped
  partial result, and text values are never stringified. A structurally valid empty
  result stays valid. A per-word confidence that is non-numeric, non-finite, boolean, or
  outside the Tesseract 0–100 percentage range is **dropped, never clamped or
  inflated**; valid values are scaled to the `0.0–1.0` contract.

### 4. Rule catalogue and activation gate — no rules, no evaluator
`backend/app/rule_catalog.py` defines metadata schemas plus a server-side activation
gate. It is governance scaffolding, not a regulatory rules engine.

- **No AICTE rule is defined, active, or executable** in this repository.
- The gate requires a verified source (exact document version, retrieval date, named
  reviewer and verification date), an attributable approval record with decision
  `approved`, an `effective_from` date, and positive/negative/boundary/exception tests.
- `RuleRegistry.activate` is the only transition to `ACTIVE`. It refuses
  caller-declared `ACTIVE` states, unverified or unapproved rules, incomplete test
  coverage, and conflicting duplicate versions.
- No rule expression is executed anywhere; there is no evaluator to call.
- Prototype limits: the registry is in-memory (lost on restart, not shared between
  workers), `reviewer_id`/`verified_by` are **recorded strings, not authenticated
  identities**, there is no durable audit trail, and supersession/retirement are not
  implemented. All AICTE rules stay inactive until authoritative applicability and
  amendment checks are complete.

## Not implemented (planned, not claimed)

A frontend application (only API fixtures, a state matrix and a fixture checker
exist under `frontend/`), an `ai/` production extraction service (the `ai/`
package is an evaluation harness), a real-world labelled OCR benchmark, OCR
fallback for scanned PDFs, bounding-box provenance, retention/deletion controls,
a rule evaluator with **active** regulatory rules (the catalogue is empty and the
activation gate is unpopulated), an official-source verification workflow, and
any AICTE integration.

## Production blockers

Public document upload and any production use remain blocked until retention and
deletion controls, official-source verification of applicable AICTE documents and
amendments (Phase 0 research closure is still open), and live-deployment
verification of the background worker, the real malware scanner and durable
shared document storage are completed and security-tested. Testing uses synthetic
data only; no real institutional or personal documents are stored.

**Deployment note (as of 2026-10-25):** the codebase supports a dedicated Celery
worker (`python -m celery -A backend.app.worker.celery_app worker --beat` —
exactly one instance runs `--beat`; it schedules the 30s recovery sweep that
re-dispatches undelivered outbox messages, due `retry_wait` jobs and lost
queued jobs), a real ClamAV daemon (`CLAMAV_HOST`/`CLAMAV_PORT`), PostgreSQL
(`DATABASE_URL`) and a strict readiness endpoint (`GET /health/ready`, which
reports `ready` only when the database, the migrated schema, a positively
scanning malware engine and writable private storage all pass). CI exercises
the full pipeline against real PostgreSQL, Redis and ClamAV services. The
Render preview services have **not** been verified end-to-end from this
workspace (no Render API access here): the backend preview URL answered with
Render's cold-start page on 2026-10-25, and there is no configured worker
service, no scanner daemon and no durable shared storage there yet. The exact
owner runbook — `render.yaml` blueprint (single Docker service with clamd +
worker + API sharing one durable disk), post-deploy verification checklist,
and the disposition of the obsolete Vercel `aicte-compliance-frontend`
integration — is in
[`docs/development/DEPLOYMENT.md`](docs/development/DEPLOYMENT.md).

## Quick start and a five-minute demo

Verified on a clean clone (Linux, Python 3.11.2; CI uses 3.12):

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt

python -m pytest -q                                    # 391 passed, 22 skipped
python -m pytest -q ai/tests                           # 244 passed, 5 skipped
python frontend/tools/verify_fixtures.py               # fixtures OK: 9 case(s)
python ai/evaluate_extraction.py                       # synthetic report + caveat banner
ruff check backend/ ai/ frontend/ tools/
```

Start the API and exercise it:

```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

```bash
curl -s localhost:8000/health
# {"status":"ok","service":"aicte-compliance-assistant"}

curl -s localhost:8000/api/v1/validate -H 'content-type: application/json' -d '{
  "institution_id": "SYNTH-INST-001",
  "application_type": "eoa",
  "required_documents": ["aicte_approval", "mandatory_disclosure"],
  "submitted_documents": ["aicte_approval"],
  "expiry_dates": {"aicte_approval": "2020-01-01"}
}'
```

That returns `status: attention_required` with two findings — one `MISSING_DOCUMENT` for
`mandatory_disclosure`, one `DOCUMENT_EXPIRED` for `aicte_approval` carrying the supplied
expiry date and the server's evaluation date — plus
`validation_scope: caller_supplied_checklist_only` and a `notice` explaining that this is
not a compliance decision. Removing the expired entry, or supplying both documents with no
expiry dates, returns `preliminary_checks_passed`. The full set of request/response shapes,
including the three `422` error shapes, is captured in `frontend/fixtures/`.

**What the demo proves:** the checklist comparison, the date comparison, the evidence
payloads and the advisory wording. **What it does not prove:** that any AICTE requirement
is satisfied, that a document is authentic, or that OCR is accurate.

## Project status at a glance

| Area | State |
|---|---|
| Checklist validation API | **implemented**, tested, synthetic data only |
| Auth, RBAC, institution tenancy | **implemented**, unit + live-PostgreSQL integration tested |
| Document intake pipeline (upload validation, private storage, fail-closed scan gate, jobs/outbox/worker, review, audit packages) | **implemented**, tested against real PostgreSQL + Redis + ClamAV in CI |
| Advisory OCR pipeline (Python) | **implemented**, unit + synthetic engine smoke test; 0 known gaps in the synthetic corpora |
| Frontend | **no application**; fixtures, a 13-state matrix and a fixture checker exist |
| AI/OCR evaluation | **synthetic corpus + scorer implemented**; no real-document benchmark |
| Rule catalogue | **gate implemented, no rule defined or active, no evaluator** |
| Retention/deletion controls | **not implemented** (production blocker) |
| Live deployment (Render) | **unverified** from this workspace; see Production blockers |

## Requirements and local setup

- **Python 3.11+** (the code uses `StrEnum`). CI runs **3.12**; `.python-version` pins
  3.12 for pyenv-style tools. Tested on Linux (CI and audit sandbox) and expected to
  work on macOS with the same commands; Windows is untested.
- No database, container, Node or frontend toolchain is required for the local
  demo and unit suite — SQLite is the default and the frontend has no
  application. The **live integration suite** (`backend/tests/integration`)
  needs real PostgreSQL, Redis and optionally ClamAV
  (`docker compose -f docker-compose.integration.yml up -d`); CI runs it
  against service containers on every PR.

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install -r backend/requirements-dev.txt

python -m pytest -q             # full suite; `pytest -q` is equivalent
ruff check backend/             # lint (pinned in requirements-dev.txt)
python -m compileall -q backend/app backend/tests
```

Run the API from the repository root:

```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
# GET  http://127.0.0.1:8000/health
# POST http://127.0.0.1:8000/api/v1/validate
```

The optional OCR engine needs the Tesseract system binary (not a Python package):

```bash
# Debian/Ubuntu
sudo apt-get install tesseract-ocr tesseract-ocr-eng
# macOS
brew install tesseract
tesseract --version   # verify the installation

python -m pip install -r backend/requirements-dev.txt -r backend/requirements-ocr.txt
python -m pytest -q backend/tests/test_ocr_engine_integration.py
python -m backend.app.ocr_cli path/to/synthetic-document.png --language eng
```

Environment variables actually read by the code: `DATABASE_URL`, `JWT_SECRET_KEY`
(required, ≥32 chars), `STORAGE_LOCAL_DIR`, `CLAMAV_HOST`/`CLAMAV_PORT`,
`CELERY_BROKER_URL`/`REDIS_URL`, and `CELERY_TASK_ALWAYS_EAGER` (tests only).
`.env.example` documents them without values. `.env` and `.env.*` are git-ignored.

## Tests

Optional real-engine smoke test (requires the Tesseract system binary and
`backend/requirements-ocr.txt`):

```bash
python -m pip install -r backend/requirements-dev.txt -r backend/requirements-ocr.txt
python -m pytest -q backend/tests/test_ocr_engine_integration.py
```

The `Backend tests` workflow runs the pytest suite, the AI extraction evaluation
tests (`python -m pytest -q ai/tests`) and the frontend fixture verification
(`python frontend/tools/verify_fixtures.py`) in the `backend-tests` job. Separate
jobs cover the optional Tesseract engine, the live PostgreSQL/Redis/ClamAV
integration suite, and an independent live ClamAV probe (see **CI scope** below).

**CI scope.** The `Backend tests` workflow runs four jobs on every PR and push to
`main`/`research/grounded-foundation`: the unit suite (`backend-tests`), the
optional Tesseract smoke test (`optional-ocr-integration`), the live
infrastructure suite against real PostgreSQL, Redis **and ClamAV** service
containers (`real-infrastructure-integration`), and an independent live ClamAV
job (`optional-clamav-integration`, non-blocking). Passing synthetic tests does
not establish OCR accuracy, regulatory correctness, or production readiness.

*(Historical)* An earlier CI gap — `pull_request` filtering that gave PRs
against `research/grounded-foundation` no checks — was fixed and merged to
`main`; the patch is preserved in `docs/development/patches/ci-pr-trigger.patch`.

## Working in this repository

Three workstreams share the repository; `WORKSTREAMS.md` is the authoritative ownership
contract, and `python tools/check_ownership.py --workstream <yours> --base <base>` enforces
it before a PR.

| Path | Workstream | Start here |
|---|---|---|
| `frontend/` | A — frontend | `frontend/STATE_MATRIX.md`, `frontend/fixtures/` |
| `backend/` | B — backend (also owns today's OCR code) | `docs/development/API_CONTRACT.md` |
| `ai/` | C — AI/OCR | `ai/EVALUATION.md`, `ai/corpus/` |

Process: `docs/development/PARALLEL_WORKFLOW.md` (worktrees, commits, PRs, conflicts) and
`docs/development/INTEGRATION_CHECKLIST.md` (gates). Owner-only actions:
`docs/development/OWNER_ACTIONS.md`. The older `docs/integration/workstream-contracts.md`
is kept as history.

See `docs/` for the research record, the audit trail
(`docs/pre-coding/foundation-readiness-2026-10-23.md`) and remaining gates.
