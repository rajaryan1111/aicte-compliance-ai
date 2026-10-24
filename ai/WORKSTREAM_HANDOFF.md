# Workstream handoff — what remains, who owns it, what evidence closes it

**Audience:** repository owner, backend workstream (B), frontend workstream (A), shared integration.
**Author:** workstream C (AI/OCR), 2026-10-23; updated 2026-10-24.
**Scope:** originally review-only. C's default boundary is `ai/**`; the two `backend/` fixes recorded
in §2.1 were made under explicit owner authorization covering **only** those two defects (B-1, B-2)
and their regression tests. Everything else described here remains owned by the named workstream and
was not touched by C.

Ownership contract: [`../WORKSTREAMS.md`](../WORKSTREAMS.md). AI/OCR status and limits:
[`README.md`](README.md), [`EVALUATION.md`](EVALUATION.md). Backend extraction defects:
[`BACKEND_HANDOFF.md`](BACKEND_HANDOFF.md).

---

## 1. Delivering the AI/OCR work: PR #6

| Item | Value |
|---|---|
| PR | #6, `arena/5614862e-aicte-compliance-ai` → **`main`** (retargeted 2026-10-24) |
| Head | `ba6944c` (== `origin`, verified with `git ls-remote`) |
| Commits | `ba38829`, `2b49f0e`, `0065459`, `f07744f` (frontend + `tools/demo`), `ba6944c` (test hardening) |
| Files | 24 — `ai/**` (8), `frontend/**` (13), `tools/demo/**` (3) |
| State | open, `MERGEABLE`, `CLEAN`, no conflicts, `reviewDecision` empty |

**C does not merge this PR.** `WORKSTREAMS.md` prohibits "merging your own PR without owner
review", and step 6 of the integration process says "no automatic merging". The owner merges.

### CI evidence: now exists, and it is red for reasons outside this PR

The PR was retargeted to `main`, so the next push started the workflow instead of leaving the head
SHA with zero check-runs. Two runs are now recorded; the second is after the `backend/` fixes.

| Check | `ba6944c` (run 40116758478) | `e509a93` (run 40118334411) |
|---|---|---|
| `backend-tests` | **fail** (49 s) | **pass** (1 m 5 s) |
| `real-infrastructure-integration` | **fail** (33 s) | **fail** (36 s) — no longer the driver |
| `optional-ocr-integration` | pass | pass |
| `optional-clamav-integration` | pass | pass |

Both original failures also occurred on `main` @ `e88a5bf` (run 40115512499), **before** this branch
is merged, so they were pre-existing rather than introduced here. They are root-caused and **fixed**
in **§2.1**: a SQLAlchemy 2.1 driver-default change that broke every `postgresql://` URL (P1), and
one test asserting Windows path semantics on Linux (P2, no actual escape). The remaining red job is
a different, newly-surfaced set of latent test defects, also listed in §2.1 and also `backend/`-owned.

Consequence for the merge gate: `WORKSTREAMS.md` step 5 requires CI green on the exact head SHA, so
the PR is not mergeable on CI evidence alone until the four latent failures in §2.1 are resolved or
the owner records a waiver. The `ai/**` and `frontend/**` content is not implicated: locally
`pytest -q ai/tests` is 243 passed / 6 skipped, and `pytest -q` is 425 passed / 22 skipped / 0 failed.

**CI logs are not retrievable from this sandbox** — `gh run view --log`, `--log-failed`, and the
per-job logs endpoint all abort with a network EOF (the log blobs redirect to
`*.blob.core.windows.net`, which is outside the sandbox's allowlist). The jobs API also returns no
step detail (`step_count: 0`). Every claim above therefore rests on local reproduction and on the
check conclusions GitHub reports, not on CI output, and is labelled that way.

### Local verification recorded at `e509a93` (reproducible by the reviewer)

```bash
python -m pytest -q ai/tests          # 243 passed, 6 skipped, 0 failed
ruff check .                          # clean
python -m pytest -q                   # backend: 425 passed, 22 skipped, 0 failed
python ai/evaluate_extraction.py --corpus ai/corpus/extraction_cases.jsonl   # 56/56 exact
cd frontend && npm run build          # 161.10 kB JS / 9.50 kB CSS, unchanged
```

The 6 skips are host capabilities, not suppressed failures: no Devanagari font, no Tesseract binary,
no `pytesseract`. Each was proven to pass once the capability was installed (see the commit messages
of `ba6944c` and `e509a93`, and §2.1).

Merge (owner, after review **and** after the §2.1 decision):

```bash
gh pr merge 6 --merge      # or --squash/--rebase per project preference
```

---

## 2. Backend handoff — extraction defects (owner: B)

**Status verified this session:** all **17** documented gaps are still open. The evaluator reports
`known gaps 2` (label corpus) and `known gaps 15` (corruption slice) with **no** case flagged
`FIXED — remove the known_gap flag`.

Reproduce:

```bash
python ai/evaluate_extraction.py --corpus ai/corpus/extraction_cases.jsonl
python ai/evaluate_extraction.py --corpus ai/corpus/ocr_corruption_cases.jsonl
```

Per-defect identifiers, expected vs observed output, synthetic inputs, severity and the acceptance
criteria for the fix PR are in [`BACKEND_HANDOFF.md`](BACKEND_HANDOFF.md). This file adds only the
measurement that was not available when that handoff was written.

### 2.1 The two red CI jobs — fixed, verified, and what they were hiding

Both defects were reproduced on clean `main` (`e88a5bf`) and are now fixed on this branch with
owner authorization (commit `e509a93`), each with regression tests that were first shown to fail
against the pre-fix code.

**B-1 (P1) — every `postgresql://` URL was dead on a fresh install. FIXED.**

SQLAlchemy resolves to 2.1.6, which changed the default PostgreSQL DBAPI for the bare
`postgresql://` scheme from `psycopg2` to `psycopg` (v3). `backend/requirements.txt` pins
`psycopg2-binary` and the documented `DATABASE_URL` format is a bare `postgresql://…`, so the
driver was imported at engine construction and failed with
`ModuleNotFoundError: No module named 'psycopg'` before any connection was attempted.

The fix (`normalize_database_url` in `backend/app/db/session.py`) makes the DBAPI explicit at every
point where a URL is consumed: `create_db_engine`, Alembic's `get_url`, and the integration
harness's `POSTGRES_URL`. The documented bare form keeps working, `sqlite://` is untouched, an
operator can still opt into psycopg v3 by naming it, and `get_database_url()` still returns what was
configured (so the existing contract in `test_persistence.py` is unchanged).

The integration harness was the last call site: it built its own engine from `POSTGRES_URL`, so
after the application fix that job still failed with the same error, one layer down.

Verified against a **real PostgreSQL server** (bundled PostgreSQL via the `pgserver` package,
started locally on `localhost:5432` with the CI's credentials; TCP, trust auth). The exact CI
migration command now succeeds:

```console
$ DATABASE_URL="postgresql://aicte_test:aicte_test_pass@localhost:5432/aicte_test_db" \
    python -m alembic -c backend/alembic.ini upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> 80f49ac7e2e2, initial_persistence_foundation
... (all 7 revisions) ...
INFO  [alembic.runtime.migration] Running upgrade f6a7b8c9d0e1 -> g7b8c9d0e1f2, audit_packages
EXIT=0     # 16 tables created, alembic_version = g7b8c9d0e1f2
```

Pre-fix control, same command, same shell: `import psycopg` → `ModuleNotFoundError`, exit 1. So this
is a genuine before/after, not an assertion about driver initialisation alone. The offline form
(`upgrade head --sql`, exit 0) is also now a regression test, since it needs no server.

**B-2 (P2) — Windows drive-qualified keys were refused only on Windows. FIXED.**

`LocalStorageBackend._resolve_key` relied on `os.path.isabs()`, which treats `C:\Windows\…` as
absolute only on Windows. On POSIX the key was stored as a literal filename. Containment was never
violated (the resolved path stayed inside `base_dir`), but the refusal depended on the host OS,
which is why `test_storage_directory_traversal_prevention` failed on Linux and passed on Windows.

A colon anywhere in the key is now refused, on every host: it is what carries Windows path meaning
(drive-qualified, drive-relative, and NTFS alternate data streams). Opaque keys from
`generate_storage_key()` never contain one, and backslash separator normalisation for valid keys is
preserved. The pre-existing failing test is **unchanged** and now passes; `exists()` keeps its
documented behaviour of reporting an unsafe key as absent rather than raising.

Pre-fix control: `backend/tests/test_storage_key_hardening.py` → 8 failed on clean `main`. The
valid-key cases passed before *and* after, which is the check that the guard did not over-reach.

**CI on `e509a93` (run 40118334411):** `backend-tests` **pass** (was failing — B-2 confirmed),
`optional-ocr-integration` pass, `optional-clamav-integration` pass,
`real-infrastructure-integration` **still fail** — and the reason is no longer the driver.

#### What fixing B-1 uncovered (owner: B, **outside this fix's scope**)

With the driver working, the live integration suite runs for the first time and four **latent**
failures surface. None is a PostgreSQL compatibility problem; all are test-vs-implementation drift:

| Test | Observed |
|---|---|
| `test_postgres_multi_tenant_isolation` | `AttributeError: 'list' object has no attribute 'id'` — the repository returns rows, the test assumes ORM objects |
| `test_postgres_validation_run_snapshots_and_reviews` | `TypeError: 'consumed_document_versions' is an invalid keyword argument for ValidationRun` |
| `test_cross_institution_access_denial` | `assert 404 == 403` — the API returns 404 (non-enumerable) where the test expects 403; this may be the *stronger* security posture, so the expectation may be the stale side |
| `test_authentication_rejection_invalid_or_expired_token` | asserts the substring `"invalid"`, receives `"Could not validate authentication credentials."` |

Local live run: `RUN_LIVE_INTEGRATION_TESTS=true` + real PostgreSQL → **10 passed, 1 skipped,
4 failed, 7 errors**; the 7 errors are Redis-dependent (`redis://localhost:6379/1` is not running
here) and in CI that service exists, so those are expected to run there. Status of those seven
against real Redis is **unverified locally** and is not claimed.

These four are deliberately **not** fixed here: two of them hinge on intentional behaviour
(403-vs-404 disclosure semantics), which is an owner decision, not a driver fix.

**Test totals after the fix:** `pytest -q` (live tests off) → **425 passed, 22 skipped, 0 failed**
(was 388 / 22 / **1**); `pytest -q ai/tests` → **243 passed, 6 skipped, 0 failed**; `ruff check .` →
clean; frontend production build unchanged (`index-BNJNb1ey.js` 161.10 kB, `index-DUURRiLi.css`
9.50 kB); extraction evaluation still **56/56 exact** with 0 spurious extractions on 20 negative
cases. `requirements-dev.txt` is unchanged — no new runtime dependency was introduced for any of
this; the PostgreSQL server was started only to verify, outside the repo.

### New measured evidence: Hindi/bilingual field extraction (real OCR, clean pages)

Source: `ai/reports/real_tesseract_5.5.2_multiseed_3x24.json`, clean (uncorrupted) pages, three seeds.
Counts recomputed from the stored per-case rows.

| Language | TP | FP | FN | Cases | Field F1 |
|---|---:|---:|---:|---:|---:|
| `en` | 60 | 0 | 60 | 24 | 0.6667 |
| `hi` | 1 | 0 | 119 | 24 | 0.0165 |
| `bilingual` | 0 | 0 | 120 | 24 | 0.0000 |

Reading: on clean Hindi and bilingual pages the extractor loses essentially every institutional
field. Recall — not precision — is the failure: there are no false positives, so the labels are
simply not recognised. The single-seed report shows exactly `0.000` for both; the multi-seed run
contains one successful Hindi extraction out of 120, which is why the pooled figure is `0.0165`
rather than `0.000`. Either way the field extraction is unusable for those languages.

This is **not a new defect id**. It is the aggregate impact of the documented label-coverage gaps
(`HI-005`/`CLH-005` and the missing Hindi label forms) plus the absence of any pattern for
`Label / लेबल:` bilingual lines.

### Proposed regression tests and acceptance criteria (owner: B)

1. `backend/tests/test_ocr_extraction_hi.py` (new): one test per Hindi label form used in the
   raster dataset — `संस्थान`, `प्रमाणपत्र संख्या`, `शैक्षणिक सत्र`, `मान्यता तक`,
   `जारी करने की तिथि` — asserting the value is extracted from clean single-line text.
2. A bilingual test asserting `Institution / संस्थान: Alpha Institute of Technology` yields
   `institution_name = "Alpha Institute of Technology"`.
3. Re-run of the AI raster benchmark as the acceptance gate, not a unit test: clean-page field
   micro-F1 for `hi` and `bilingual` must rise above `0.000` and `en` must not regress.
4. Only then remove the corresponding `known_gap` flag from `ai/corpus/*.jsonl`; the evaluator
   flags a passing gap as `FIXED — remove the known_gap flag`, so a flag removed early is visible.

Priority: **high** — this is the largest measured accuracy gap in the pipeline and it depresses the
Phase 6 accuracy claim for every Devanagari document.

---

## 3. Phase 6 handoff — accessibility, demo script, deployment fallback (owners: A and B)

Canonical wording (`docs/canonical/phases.md`):

> **Phase 6 — Demo quality and measurement (P1/P2)**
> Deliverables: labelled synthetic corpus, OCR evaluation, accessibility, performance observations,
> demo script and deployment fallback.
> Gate: claims about accuracy/performance are supported by recorded measurements.

| Deliverable | Status | Evidence on disk | Owner |
|---|---|---|---|
| Labelled synthetic corpus | **Done (C)** | `ai/corpus/extraction_cases.jsonl` (56 cases), `ai/corpus/ocr_corruption_cases.jsonl` (30 cases) | C |
| OCR evaluation | **Done (C)** | evaluator + raster benchmark; real-engine reports in [`reports/`](reports/README.md) | C |
| Performance observations | **Partial (C)** | `duration_seconds` in both reports; explicitly *not* throughput/latency under load | C reports, B measures |
| Accessibility | **Not started** | none — `frontend/` contains a README and fixtures only | A |
| Demo script | **Not started** | none | A + B (shared run-through) |
| Deployment fallback | **Not started** | none — no deployment exists | B |

### 3.1 Accessibility (owner: A)

- **Requirement:** the applicant/reviewer UI must be usable with a keyboard and a screen reader, and
  must not rely on colour alone to convey status. Canonical source for the gate is Phase 6 plus the
  product requirements in `docs/canonical/prd.md`; the frontend state matrix
  (`frontend/STATE_MATRIX.md`) already enumerates the states that need accessible treatment.
- **Missing:** any UI at all — `frontend/` has fixtures, a state matrix and tooling, no application.
- **Steps:** choose the framework; build the evidence/status views; add landmark structure, labels,
  focus order, contrast and `aria-live` for async validation errors; test with a keyboard-only pass
  and one screen reader; record the pass in the frontend README.
- **Completion evidence:** a recorded accessibility check (tool + manual keyboard pass) against a
  named commit, and every `STATE_MATRIX.md` row reachable without a mouse.
- **Dependency:** blocked on the frontend application existing.

### 3.2 Demo script (owner: A, with B for the backend run-through)

- **Requirement:** a scripted end-to-end demonstration of the compliance flow.
- **Missing:** everything. There is no persistence, auth or review workflow yet (Phases 1, 3, 4),
  so a demo today can only show `/health` and `/api/v1/validate`.
- **Steps:** write the script against what exists (validation + evidence display), mark the stages
  that need Phases 1/3/4, and extend it as those land.
- **Completion evidence:** a script a second person can follow start to finish on a clean machine,
  with expected output per step and a recorded run.
- **Dependency:** the review workflow (Phase 4) for any demo that claims an approval decision.

### 3.3 Deployment fallback (owner: B)

- **Requirement:** a documented fallback so the demo survives a failed deployment.
- **Missing:** no deployment, no container image, no hosted environment.
- **Steps:** reproducible local run instructions from a clean environment (also gate G7 of
  `docs/pre-coding/phase-5-coding-readiness.md`), a container or equivalent, and a recorded
  pre-demo checklist with a rollback/offline path.
- **Completion evidence:** a clean machine can bring the system up from the documented steps, and a
  rehearsed failure path is written down.
- **Dependency:** G7 (reproducible setup) and the Phase 1 stack decisions.

**C will not touch `frontend/**`, `backend/**` or `.github/**` for any of the above.**

---

## 4. Phase 0 research closure — decision memo for the repository owner

Canonical wording (`docs/canonical/phases.md`, "Updated Phase 0 gate — research snapshot 2026-10-23"):

> Phase 0 remains **open**. […] Closure requires: (1) retrieve and reconcile the complete 1 April
> 2024 scrutiny document; (2) establish official publication/finality/effective date of the 2026–27
> addendum; (3) check Annexure-2 §2.1 pagination and Clause 7.17 directly in the official handbook
> PDF; (4) resolve the NBA-validity-through-30-April-2025 reference for AY 2026–27; (5) verify the
> official SIH statement and deadline; and (6) resolve reuse-repository licensing/authorship/
> data-history risks before copying anything. API availability remains unresearched, not disproven.
> No candidate document rule becomes active while these gates are open.

| # | Gate (canonical wording) | Evidence required | Status | Decision-maker | Blocks |
|---|---|---|---|---|---|
| 1 | Retrieve and reconcile the complete 1 April 2024 scrutiny document | Full official document, completeness check, reconciliation record in `docs/research/` | **Open** — document not retrieved complete | repository owner | Phase 3 rules |
| 2 | Official publication/finality/effective date of the 2026–27 addendum | Official publication record, effective date, finality | **Open** — addendum status unresolved | repository owner | Phase 3, Phase 6 claims |
| 3 | Annexure-2 §2.1 pagination and Clause 7.17 verified in the official handbook PDF | Direct citation with page numbers from the official PDF | **Open** — not verified directly | repository owner | Phase 3 |
| 4 | NBA-validity-through-30-April-2025 reference for AY 2026–27 | Interpretation with source basis, recorded as a decision | **Open** — unresolved wording | repository owner | Phase 3 |
| 5 | Official SIH26261 statement and deadline | Official portal record (currently mirror-reported only) | **Open** — not directly verified | repository owner | Scheduling / submission |
| 6 | Reuse-repository licensing/authorship/data-history risks | Licence basis, authorship and data-history assessment | **Open** — reuse prohibited until resolved | repository owner | Any code/data reuse |

Also recorded (not numbered by the canonical gate, still unresolved): **AICTE API availability is
unresearched, not disproven** — do not claim an API exists or does not exist.

**Consequences of leaving these open:** no regulatory rule may become active, so Phase 3 cannot
start; the compliance claims in the demo cannot be made; and the Phase 5 coding-readiness gate
stays `BLOCKED` (gate G3 and G9).

**What the owner must produce to close each gate:** the official artefact (or an explicit
"unavailable" decision with a recorded rationale), a dated decision entry naming the decision-maker,
and a link from `docs/research/official-source-verification-report.md`. C does not research or
interpret regulations.

---

## 5. What C is *not* doing, and why

- **Not merging PR #6** — `WORKSTREAMS.md` reserves the merge to the owner. B-1 and B-2 are fixed
  (§2.1), but CI on the head SHA is still red for the four latent test defects that fixing B-1
  uncovered; C cannot fix or waive those without a further scope decision.
- **Not fixing the four latent integration defects in §2.1** — they surfaced only because B-1 was
  fixed, and at least one (`404` vs `403`) is an intentional-security-posture question, which is an
  owner decision rather than a driver fix.
- **Not editing `backend/app/ocr_*.py`** — backend-owned until an approved migration
  (`WORKSTREAMS.md`, "OCR placement").
- **Not adding real or scanned institutional documents** — the corpora must stay synthetic.
- **Not extending the reproduction beyond synthetic pages** — every AI/OCR number here is
  Pillow-rendered synthetic text, not a scan of a real certificate. Nothing in this repository may
  be quoted as real-world OCR accuracy, compliance or authenticity evidence.
- **Not starting new OCR features** — no AI/OCR canonical requirement is currently unblocked.
