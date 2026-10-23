# AICTE Compliance Assistant

A prototype for **preliminary checklist validation** and **advisory institutional-document
OCR**. It does not authenticate documents, verify institutional status, or decide
regulatory compliance.

## What is implemented

### 1. Checklist validation — caller-supplied data only
`POST /api/v1/validate` compares the `required_documents` / `submitted_documents`
lists and `expiry_dates` supplied in the request. It returns missing and expired
documents with `validation_scope: "caller_supplied_checklist_only"`.

- The service loads no AICTE checklist and no rule set; the caller supplies both lists.
- `preliminary_checks_passed` means only that the supplied lists agree. It is not a
  compliance, eligibility, or authenticity finding.

### 2. Advisory OCR — optional, local only
`backend/app/ocr_pipeline.py` implements an engine-neutral OCR contract
(`ocr_adapter.py`), an optional Tesseract adapter, field extraction for a small set
of context-labelled institutional fields (English and selected Hindi labels), and a
local CLI: `python -m backend.app.ocr_cli <image>`.

Implemented input/output limits: 10 MiB compressed bytes, 30 megapixels,
JPEG/PNG/TIFF/WEBP only, a 100,000-character aggregate OCR text budget, strict ISO
`YYYY-MM-DD` dates (ambiguous formats stay unresolved), single-year academic sessions
only, engine confidence confined to `0.0–1.0`, page/line/evidence provenance, source
SHA-256, and `requires_human_review=True` on every result.

- OCR output is evidence for a human reviewer, never proof of authenticity.
- There is **no upload endpoint**, no persistence and no external call.
- **No accuracy claim is made.** The fixture corpus is synthetic regression data, not a
  labelled held-out benchmark; the Tesseract test is a synthetic smoke test.
- PDFs are rejected as unsupported images. Multi-page/multi-frame files are processed
  from the first frame only and now report a warning; submit pages separately. Bounding
  boxes are not recorded. Hindi coverage is label extraction plus synthetic text
  fixtures only — the optional engine test is English.
- Engine output is validated before use. `text` and `conf` are **required** columns and
  must be equal-length sequences; `page_num`/`line_num` are optional (default 1) but must
  align with `text` if present. A missing required column, a length mismatch, or a
  non-string `text` value raises an engine error instead of yielding a success-shaped
  partial result, and text values are never stringified. A structurally valid empty
  result stays valid. A per-word confidence that is non-numeric, non-finite, boolean, or
  outside the Tesseract 0–100 percentage range is **dropped, never clamped or
  inflated**; valid values are scaled to the `0.0–1.0` contract.

### 3. Rule catalogue and activation gate — no rules, no evaluator
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

Frontend application, `ai/` extraction service, authentication/authorization/RBAC,
institution-level tenant isolation, private document storage, malware scanning,
persistent audit logging, retention/deletion controls, PDF/scan ingestion, a rule
evaluator, an official-source verification workflow, and any AICTE integration.

## Production blockers

Public document upload and any production use remain blocked until authentication and
RBAC, tenant isolation, private storage, malware scanning, durable audit, retention
and deletion controls, and official-source verification of applicable AICTE documents
and amendments are implemented and security-tested. Testing uses synthetic data only;
no real institutional or personal documents are stored.

## Quick start and a five-minute demo

Verified on a clean clone (Linux, Python 3.11.2; CI uses 3.12):

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt

python -m pytest -q                                    # 223 passed, 1 skipped
python -m pytest -q ai/tests                           # 17 passed
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
| Advisory OCR pipeline (Python, no HTTP route) | **implemented**, unit + synthetic engine smoke test |
| Frontend | **no application**; fixtures, a 13-state matrix and a fixture checker exist |
| AI/OCR evaluation | **synthetic corpus + scorer implemented**; no real-document benchmark |
| Rule catalogue | **gate implemented, no rule defined or active, no evaluator** |
| Auth, RBAC, tenancy, storage, upload, audit, retention | **not implemented** (production blockers) |

## Requirements and local setup

- **Python 3.11+** (the code uses `StrEnum`). CI runs **3.12**; `.python-version` pins
  3.12 for pyenv-style tools. Tested on Linux (CI and audit sandbox) and expected to
  work on macOS with the same commands; Windows is untested.
- No database, container, Node or frontend toolchain is required — none is implemented.

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

No environment variables are read today; `.env.example` documents planned settings as
comments only. `.env` and `.env.*` are git-ignored.

## Tests

Optional real-engine smoke test (requires the Tesseract system binary and
`backend/requirements-ocr.txt`):

```bash
python -m pip install -r backend/requirements-dev.txt -r backend/requirements-ocr.txt
python -m pytest -q backend/tests/test_ocr_engine_integration.py
```

The `Backend tests` workflow runs three checks in the `backend-tests` job: the pytest
suite, the AI extraction evaluation tests (`python -m pytest -q ai/tests`) and the frontend
fixture verification (`python frontend/tools/verify_fixtures.py`). A separate
`optional-ocr-integration` job installs Tesseract and runs the engine smoke test.

**Known CI gap on the integration base.** `research/grounded-foundation` still filters
`pull_request` to `["main"]`, so PRs opened against that branch get **no checks** — PRs #2
and #4 have none. The one-line fix and its regression test exist on this branch and as a
tested patch in `docs/development/patches/ci-pr-trigger.patch`; it takes effect only once
it is merged into the base. Passing synthetic tests does not establish OCR accuracy,
regulatory correctness, or production readiness.

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
