# SIH submission readiness — verified evidence report

**Verified:** 2026-10-24 · **Workstream:** C (AI/OCR) · **Repository state checked at:**
`origin/main` = `00065a7` and `arena/5614862e-aicte-compliance-ai` = `0065459`.

This report records only what was **executed and observed** in a clean sandbox during this
session. Nothing here is inferred from earlier handoffs, and no metric is copied from a
document without re-running it. Where something could not be executed it is marked
`BLOCKED_EXTERNAL` or `NOT_AVAILABLE`, never `PASS`.

> **Scope note.** This workstream owns `ai/**`. `backend/`, `frontend/`, `.github/` and shared
> configuration were **inspected and executed but not modified.** Every defect below that lives
> outside `ai/**` is written as a handoff with a minimal fix, not as a patch.

---

## 1. Repository reality — the most important finding

Two facts must frame everything else:

1. **`main` is far ahead of the reported OCR branch.** `main` (`00065a7`) contains a full
   application: auth, applications, document upload with versions, malware-scan gate,
   processing jobs, validation with findings and review actions, audit packages. The
   `backend/` on the reported branch (`cdbad6a`) is an older, much smaller slice.
   `cdbad6a` is **not** an ancestor of `main`.
2. **There is no frontend application anywhere in the repository.** `frontend/` contains
   `README.md`, `STATE_MATRIX.md`, 8 JSON fixtures and 2 fixture tools. There is **no
   `package.json`, no framework, no build, no runtime code.**

Consequence: "user opens the application, uploads a file, sees a result" **cannot happen
today**. The backend is demonstrable; the product is not.

### 1.1 PR state (verified via `gh`)

| Item | Verified state |
|---|---|
| PR #10 (`feature/ai-ocr-corruption-slice` → `main`) | **OPEN**, `mergeable: MERGEABLE`, `mergeStateStatus: UNSTABLE` |
| PR #10 head | `c8a435d8` — **not** `1a2bf24`; `1a2bf24` is an earlier commit in the same PR |
| PR #10 CI | `backend-tests` **fail**, `real-infrastructure-integration` **fail**, `optional-clamav-integration` pass, `optional-ocr-integration` pass |
| PR #6 (this workstream → feature branch) | OPEN, no CI checks reported on the branch |

---

## 2. What was verified by execution

Environment was rebuilt from scratch in this session (no pre-existing venv):

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt        # fastapi 0.161.0, pydantic 2.14.1, Pillow 11.3.0, pytest 9.1.1
```

| Check | Command | Result |
|---|---|---|
| Backend suite (branch) | `python -m pytest -q` | **224 passed, 1 skipped** (skip = real-Tesseract test, no engine in `PATH`) |
| AI suite (branch) | `python -m pytest -q ai/tests` | **248 passed** |
| Backend suite (`main`) | `python -m pytest -q` in a detached `main` worktree | **388 passed, 22 skipped, 1 FAILED** |
| Lint | `ruff check ai/` | clean |

**The reported "249 AI tests" refers to PR #10's branch, not this one.** 248 is the true count
here. No claim is made that the whole project passes: one backend test fails on `main`.

---

## 3. End-to-end verification (executed against `main`)

Run in a detached worktree of `main` with SQLite, so the real code path was exercised —
not mocks, not the test suite.

```bash
git worktree add --detach /tmp/main-check origin/main
export DATABASE_URL="sqlite:///./demo_e2e.db"
python -m alembic -c backend/alembic.ini upgrade head          # 7 migrations, clean
```

| # | Flow step | Result | Evidence |
|---|---|---|---|
| 1 | Application starts | **PASS** | uvicorn boots, `/openapi.json` serves 22 paths |
| 2 | `GET /health` | **PASS** | `{"status":"ok"}` |
| 3 | Authenticate | **PASS** *after* seeding | `POST /api/v1/auth/token` → JWT; `GET /auth/me` → user profile |
| 4 | Create application | **PASS** | `POST /api/v1/applications` → `201`, `{"id":3,"status":"draft"}` |
| 5 | Document upload (PDF) | **PASS** | `201`, stored with `sha256`, `byte_size: 909`, queued job |
| 6 | Malware scan gate | **PASS** *(with a **test double** — see §6)* | `scan_status: clean` |
| 7 | Background processing | **PASS** with `CELERY_TASK_ALWAYS_EAGER=true` | `job.state: completed`, `processing_status: succeeded` |
| 8 | Field extraction | **PASS** | **5 fields extracted** from a synthetic PDF |
| 9 | Validation run | **PASS** | `201`, `outcome: attention_required`, 8 checks evaluated |
| 10 | Findings produced | **PASS** | 1 finding: `INSTITUTION_MISMATCH` with extracted-vs-expected evidence |
| 11 | Honest limitations surfaced | **PASS** | `"No verified, approved and active AICTE rules found…"`, `"Universal document checklist not configured…"` |
| 12 | Frontend display | **NOT_AVAILABLE** | no frontend application exists |
| 13 | Persistence / history | **PASS** (backend) | validation runs, findings, documents persisted in DB and re-readable |
| 14 | Repeat workflow | **PASS** | multiple applications/documents/validation runs completed in one session |

**Real validation output (verbatim, from the run):**

```json
"summary_counts": {"passed": 4, "failed": 1, "inconclusive": 0, "not_applicable": 1, "not_run": 2}
"outcome": "attention_required"
finding: {"code": "INSTITUTION_MISMATCH", "severity": "warning",
          "summary": "Extracted institution identifier 'Demo Institute of Technology' does not match expected 'INST-DEMO-001'."}
checks: CHECK_DOCUMENT_EXPIRY passed · CHECK_DATE_ORDER passed · CHECK_DUPLICATE_FILES passed
        CHECK_EXTRACTION_CONFIDENCE passed · CHECK_INSTITUTION_CONSISTENCY failed
        CHECK_CROSS_DOCUMENT_CONSISTENCY not_applicable · CHECK_DOCUMENT_READINESS not_run
        CHECK_OFFICIAL_REGULATORY_RULES not_run
```

The two `not_run` checks are **correct behaviour, not defects**: regulatory rules are
deliberately inactive because Phase 0 gates remain open.

---

## 4. Priority matrix

| Area | Status | Note |
|---|---|---|
| Backend API (auth, applications, documents, validation, findings, audit) | **PASS** | 388 tests pass; live flow verified |
| Document upload + storage + SHA-256 + versioning | **PASS** | verified live |
| Field extraction from text PDF | **PASS** | 5 fields extracted live |
| Validation engine + findings + limitations | **PASS** | verified live |
| Review actions / audit packages | **PARTIAL** | routes exist and are tested; not exercised live this session |
| Frontend application | **NOT_AVAILABLE** | no code exists |
| User self-registration / seeding | **FAIL** | no route, no script (§5.1) |
| Background worker without Redis | **PARTIAL** | requires `CELERY_TASK_ALWAYS_EAGER` or Redis+Celery (§5.2) |
| Malware scanning | **BLOCKED_EXTERNAL** | no ClamAV in sandbox; pipeline fails closed (§5.3) |
| Real OCR engine (Tesseract) | **NOT_AVAILABLE** | cannot install (no root, no package lists) (§6) |
| Real-document accuracy | **NOT_AVAILABLE** | no authorised labelled corpus |
| Hindi/bilingual rendering validity | **BLOCKED_EXTERNAL** | no `libraqm`; measurements stay invalid |
| CI green on PR #10 | **FAIL** | traversal + psycopg (§5.4, §5.5) |
| Regulatory rule activation | **NOT_REQUIRED** | correctly inert while Phase 0 gates are open |

---

## 5. P0 / P1 defects with owners and minimal fixes

### 5.1 P0 — No way to create a user (backend)

Verified: `/openapi.json` exposes only `/api/v1/auth/token` and `/api/v1/auth/me`. There is no
register/signup endpoint, no seed script, no management CLI. On a fresh database **every
authenticated route is unreachable**: login returns `401 {"detail":"Incorrect username or password."}`
for any credentials.

- **Owner:** workstream B (backend).
- **Evidence:** the route list in §3; `grep -riE "register|signup|create_user" backend/app/` → no matches.
- **Minimal fix:** either a `POST /api/v1/auth/register` guarded by an admin role, **or** a
  documented `python -m backend.app.scripts.create_user` bootstrap. For a hackathon the
  second is lower risk.
- **Acceptance:** on a fresh migrated DB, documented steps produce a working login without
  hand-editing the database.

### 5.2 P0 — Demo cannot process documents without Redis + Celery (backend/infra)

Verified twice. Without a broker the outbox dispatch fails and the job stays `queued` forever:

```
Outbox dispatch failed for message …: Retry limit exceeded while trying to reconnect to
the Celery result store. Preserving message in outbox.
```

With `CELERY_TASK_ALWAYS_EAGER=true` processing completes inline (§3). **This switch is the
single-line difference between a working demo and a dead one**, and it is not documented in
`README.md`.

- **Owner:** workstream B / infra.
- **Minimal fix:** document eager mode for local/demo runs (`CELERY_TASK_ALWAYS_EAGER=true`),
  or ship a `docker-compose.yml` with Redis + a worker.
- **Acceptance:** a documented command sequence reaches `processing_status: succeeded`.

### 5.3 P0 — Documents are quarantined without ClamAV (by design; blocks the demo)

`backend/app/core/scanner.py` fails **closed**: with no `CLAMAV_HOST` the status is
`scan_unavailable` and the job retries with `SCANNER_UNAVAILABLE`, so extraction never runs.
This is **correct security design** and must not be weakened in product code.

- **Owner:** workstream B / infra.
- **Minimal fix (demo only):** document that a scanner is required, or run ClamAV in compose.
  A dev bypass must **not** be added to product code.
- **Acceptance:** documented environment reaches `scan_status: clean` → extraction proceeds.

### 5.4 P1 — Path traversal contract defect (backend), reproduces on `main`

`backend/tests/integration/test_security_and_failure_paths.py::test_storage_directory_traversal_prevention`
fails: **1 failed, 388 passed** on `main`.

- **Root cause:** `LocalStorageBackend._resolve_key` rejects leading `/`, `\` and `..`
  components, but `"C:\\Windows\\system32\\cmd.exe"` passes all guards on POSIX:
  `os.path.isabs()` is `False`, and after separator normalisation the key resolves **inside**
  `base_dir`, so the containment check passes. On POSIX this silently creates a literal `C:`
  directory inside the store; **on Windows it would be a genuine escape.**
- **Owner:** workstream B.
- **Minimal fix:** reject Windows drive designators before resolution — e.g. after
  normalising separators, `raise PathTraversalError` if `parts[0].endswith(":")` or if `":"`
  appears in any component. Add the failing key as a regression case.
- **Acceptance:** the existing test passes unchanged, and a Windows-style key is rejected on
  both POSIX and Windows.

### 5.5 P1 — CI migration job: psycopg v3 vs psycopg2 (infra)

Reproduced locally and pinned exactly:

- Installed: **SQLAlchemy 2.1.6**, `psycopg2-binary 2.9.13`.
- `backend/alembic.ini` has `sqlalchemy.url = sqlite:///...`, but CI overrides with a
  `postgresql://` URL.
- **SQLAlchemy 2.1 resolves bare `postgresql://` to the psycopg (v3) dialect:**
  `registry.load('postgresql')` → `PGDialect_psycopg`, which imports `psycopg`.
- `backend/requirements.txt` pins `sqlalchemy>=2.0.0,<3.0.0`, so a 2.1.x minor release silently
  changed the default DBAPI → `ModuleNotFoundError: No module named 'psycopg'`.

- **Owner:** infra / workstream B.
- **Minimal fix (choose one):** use `postgresql+psycopg2://` in the CI `DATABASE_URL`
  (smallest, no dependency change); or add `psycopg[binary]` to requirements; or pin
  `sqlalchemy<2.1`.
- **Acceptance:** the migration job passes against PostgreSQL in CI.

---

## 6. Honest limitations of this verification

- **No real OCR engine.** Tesseract could not be installed (`apt-get -s install tesseract-ocr`
  → `Unable to locate package`; no root, no package lists). Extraction in §3 used the
  **PDF text path (`pdfplumber`)**, which is a real code path but **not OCR**. No OCR accuracy
  is claimed here.
- **The malware-scan step used a test double.** To reach extraction I ran a local socket
  responder that implements the clamd `INSTREAM` protocol and always returns `stream: OK`.
  It performs **no scanning**, lives in `/tmp` (never committed), and is **not** evidence that
  virus scanning works. `optional-clamav-integration` passing in CI is the only real scanner
  evidence, and it is a CI job, not this run.
- **Synthetic documents only.** The PDF was generated in-session with an explicit
  "SYNTHETIC DEMO DOCUMENT — NOT A REAL AICTE CERTIFICATE" line. No real institutional
  document was used.
- **Real-document accuracy: `NOT_AVAILABLE`.** Unchanged; no authorised labelled corpus exists.
- **Hindi/bilingual accuracy: still invalid** — no `libraqm`; the rendering-validity flags in
  `ai/raster_benchmark.py` correctly report these measurements as invalid and must not be quoted.
- **`.env.example` is stale** (shared file, not modified): it states "the current prototype
  reads NO environment variables", but `JWT_SECRET_KEY` is **mandatory** (auth returns
  `500 RuntimeError` without it) and `DATABASE_URL`, `CELERY_TASK_ALWAYS_EAGER`,
  `CLAMAV_HOST`, `CLAMAV_PORT` are all read. **Owner:** shared/docs.

---

## 7. Verified demo runbook (these exact commands worked)

```bash
# 1. Environment
git checkout main && python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt

# 2. Database (SQLite is enough for a demo)
export DATABASE_URL="sqlite:///./demo.db"
python -m alembic -c backend/alembic.ini upgrade head

# 3. REQUIRED env vars — auth fails with HTTP 500 without JWT_SECRET_KEY
export JWT_SECRET_KEY="<at-least-32-characters-long>"
export CELERY_TASK_ALWAYS_EAGER=true      # avoids needing Redis + a worker
# a malware scanner is also required, or uploads stay quarantined:
#   CLAMAV_HOST=<host> CLAMAV_PORT=3310

# 4. Seed a user (no register endpoint exists — see §5.1)
python - <<'PY'
from backend.app.db.session import SessionLocal
from backend.app.db.models import User, Institution, InstitutionMembership
from backend.app.core.security import get_password_hash
db = SessionLocal()
i = Institution(institution_id="INST-DEMO-001", display_name="Demo Institute", status="active")
db.add(i); db.commit()
u = User(username="demo", hashed_password=get_password_hash("<password>"), is_active=True)
db.add(u); db.commit()
db.add(InstitutionMembership(user_id=u.id, institution_id=i.id, role="institution_admin", is_active=True))
db.commit()
PY

# 5. Run
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

# 6. Drive the flow
TOK=$(curl -s -X POST localhost:8000/api/v1/auth/token -H 'Content-Type: application/json' \
  -d '{"username":"demo","password":"<password>"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
APP=$(curl -s -X POST localhost:8000/api/v1/applications -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' -d '{"application_type":"eoa","academic_year":"2026-2027"}' \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')
curl -s -X POST "localhost:8000/api/v1/applications/$APP/documents" -H "Authorization: Bearer $TOK" \
  -F document_type=approval_letter -F "file=@sample.pdf;type=application/pdf"
curl -s -X POST "localhost:8000/api/v1/applications/$APP/validate" -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' -d '{}'
```

**Label grammar the extractor actually matches** (from `backend/app/ocr_pipeline.py`) — a
synthetic demo document must use these exact forms or extraction returns 0 fields:

```
Institution Name: <3–160 chars>      Certificate No.: <ref>
Date of Issue: <date>                Valid Upto: <date>
Academic Year: 2026-2027             (also: Application Ref, Institution Name variants)
```

The first synthetic document used "Institution ID:" and "Approval Valid Upto:" and correctly
yielded **0 fields**; only the label-correct version produced 5.

---

## 8. Submission readiness verdict

**`NOT_READY — P0 BLOCKER REMAINS`** for a user-facing demo.

- The **backend** is genuinely demonstrable end-to-end (§3) and can be shown as
  **`READY_WITH_DOCUMENTED_LIMITATIONS`** if the demo is driven by API calls.
- The **product** is not demoable as an application: there is **no frontend** (P0), no way to
  **create a user** (P0), and no documented path to **process a document** without Redis or a
  scanner (P0).

**Smallest set of actions that would change the verdict**, in order:

1. **Frontend** (workstream A): even a single page — upload → POST → render findings. Without
   it there is nothing to show an evaluator.
2. **User bootstrap** (B): a documented script or admin-only register route (§5.1).
3. **Documented demo config** (B/infra): `CELERY_TASK_ALWAYS_EAGER=true` + a scanner, or a
   compose file (§5.2/§5.3), plus correcting `.env.example`.
4. **Fix PR #10 CI** (B/infra): traversal (§5.4) and `postgresql+psycopg2://` (§5.5).

Nothing in this report enables a regulatory rule. Phase 0 gates 2, 3 and 4 remain open; the
`not_run` regulatory checks are correct behaviour and must stay that way until those gates close.

---

### Addendum 2026-10-24 — status of the P0s above

The verdict above is preserved as written (it is the audit trail of that review). Three of the P0s
it names have since been closed on this branch; one has not. Current state, re-verified by execution:

| P0 from §5 | Current status | Evidence |
|---|---|---|
| "no frontend" | **closed** | `frontend/` (React 18 + TS + Vite) committed in `f07744f`, `npm run build` clean |
| "no way to create a user" | **closed** | `tools/demo/seed_demo.py` seeds a reviewer account; login returns 200 through the Vite proxy |
| "no documented path to process a document without Redis or a scanner" | **closed** | `tools/demo/` + `CELERY_TASK_ALWAYS_EAGER=true` + `dev_scanner_testdouble.py`; runbook in `tools/demo/README.md` |
| "no CI evidence on the PR" | **closed** | PR #6 retargeted to `main`; run 40116758478 now reports 4 checks on head `ba6944c` |

The end-to-end flow (health → login → create application → upload → process → validate → review) was
re-verified through the frontend's Vite proxy on port 5173, including the fail-closed path: with the
scanner down, `validate` returns `SCANNER_UNAVAILABLE` and extraction does **not** run.

**Still open, and still outside workstream C's ownership:** §5.4 (Windows drive-letter key rejected
only on Windows) and §5.5 (SQLAlchemy 2.1 resolves bare `postgresql://` to the absent `psycopg` v3).
§5.5 is confirmed as the live cause of the `real-infrastructure-integration` job failing on both
`main` and this PR — reproduced with the CI step's exact `DATABASE_URL`. Neither defect touches the
SQLite-backed demo path, so neither blocks the demo; both block a green CI and a PostgreSQL
deployment. See `WORKSTREAM_HANDOFF.md` §2.1 for the reproductions and candidate patches.

**The demo-relevant verdict is therefore `READY_WITH_DOCUMENTED_LIMITATIONS`** — the application is
demonstrable, and the limitations that remain (no real institutional documents, synthetic-only
accuracy, regulatory checks correctly `not_run`, two red CI jobs owned by `backend/`) are documented
rather than hidden. This addendum does not change any metric, threshold or ground truth, and does
not claim real-world OCR accuracy or regulatory compliance from synthetic data.
