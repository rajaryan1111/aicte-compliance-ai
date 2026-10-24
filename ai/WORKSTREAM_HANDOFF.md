# Workstream handoff — what remains, who owns it, what evidence closes it

**Audience:** repository owner, backend workstream (B), frontend workstream (A), shared integration.
**Author:** workstream C (AI/OCR), 2026-10-23.
**Scope:** review-only. This file changes nothing outside `ai/**`; it records the state of work that
is **not** owned by C so the owners can act on it.

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
SHA with zero check-runs. Run **40116758478** on head `ba6944c`:

| Check | Result |
|---|---|
| `backend-tests` | **fail** (49 s) |
| `real-infrastructure-integration` | **fail** (33 s) |
| `optional-ocr-integration` | pass |
| `optional-clamav-integration` | pass |

Both failures also occur on `main` @ `e88a5bf` (run 40115512499), **before** this branch is merged,
so they are pre-existing. They are root-caused in **§2.1** below: a SQLAlchemy 2.1 driver-default
change that breaks every `postgresql://` URL (P1), and one test that asserts Windows semantics on
Linux (P2, no actual escape). Both live in `backend/**`, which workstream C does not own.

Consequence for the merge gate: `WORKSTREAMS.md` step 5 requires CI green on the exact head SHA.
That cannot be satisfied by this PR alone — it needs the two `backend/` fixes or an explicit owner
waiver recorded on the PR. The `ai/**` and `frontend/**` content in this PR is not implicated in
either failure: locally `pytest -q ai/tests` is 243 passed / 6 skipped, and the only backend test
that fails is the pre-existing traversal test, which fails identically on clean `main`.

**CI logs are not retrievable from this sandbox** — `gh run view --log` and `--log-failed` both abort
with a network EOF against `results-receiver.actions.githubusercontent.com`, and the jobs API returns
no step detail (`step_count: 0`). Every claim above therefore rests on local reproduction, not on
CI output, and is labelled that way.

### Local verification recorded at `ba6944c` (reproducible by the reviewer)

```bash
python -m pytest -q ai/tests          # 243 passed, 6 skipped, 0 failed
ruff check ai/                        # clean
python -m pytest -q                   # backend: 1 failed, 388 passed, 22 skipped
                                      #   the 1 failure is B-2 below, pre-existing on main
```

The 6 skips are host capabilities, not suppressed failures: no Devanagari font, no Tesseract binary,
no `pytesseract`. Each was proven to pass once the capability was installed (see §2.1 and the commit
message of `ba6944c`).

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

### 2.1 The two red CI jobs on `main` — root-caused, both `backend/`-owned (owner: B)

`main` @ `e88a5bf` has two failing jobs (`backend-tests`, `real-infrastructure-integration`). CI logs
were unreadable from this sandbox (`gh run view --log` aborts with a network EOF), so both were
**reproduced locally** instead. Neither is an `ai/` defect; neither has been patched by C, because
both live in `backend/**`, which C does not own.

**B-1 (P1) — every `postgresql://` URL is dead on a fresh install: SQLAlchemy 2.x resolved to 2.1.6
flipped the default PostgreSQL DBAPI from `psycopg2` to `psycopg` (v3).** `backend/requirements.txt`
pins `psycopg2-binary>=2.9.0` and `sqlalchemy>=2.0.0,<3.0.0`, so a clean `pip install` gets 2.1.6 +
`psycopg2` — and SQLAlchemy then tries to import the *absent* `psycopg`. This is a time bomb, not a
stale branch state: it breaks the CI job's `alembic upgrade head` step, and it would break a real
PostgreSQL deployment just as completely. The SQLite demo path is unaffected, which is why it has
gone unnoticed.

```console
$ python -c 'import sqlalchemy; sqlalchemy.create_engine("postgresql://u:p@h:5432/db")'
ModuleNotFoundError: No module named 'psycopg'      # sqlalchemy 2.1.6, psycopg2 2.9.13 installed

$ DATABASE_URL="postgresql://a:p@localhost:5432/x" python -m alembic -c backend/alembic.ini upgrade head
  File ".../sqlalchemy/dialects/postgresql/psycopg.py", line 497, in import_dbapi
    import psycopg
ModuleNotFoundError: No module named 'psycopg'      # exit 1 — this is the CI step, verbatim

$ DATABASE_URL="postgresql+psycopg2://a:p@localhost:5432/x" python -m alembic -c backend/alembic.ini upgrade head
(Background on this error at: ...)                  # driver import OK; fails only on "no server here"
```

Smallest fixes, owner's choice — pin the driver or pin the major:

1. `backend/requirements.txt`: `sqlalchemy>=2.0.0,<2.1` (reverts to the `psycopg2` default), **or**
2. keep SQLAlchemy and add `psycopg[binary]>=3.1` (adopt the v3 driver), **or**
3. normalise the scheme in `backend/app/db/session.py::create_db_engine` and `backend/alembic/env.py`
   (`postgresql://` → `postgresql+psycopg2://`) so the driver is always explicit rather than
   inherited from a library default.

Option 3 is the only one that also protects the alembic CLI path and any operator-supplied
`DATABASE_URL`; option 1 is the smallest diff. Acceptance: `real-infrastructure-integration` green
against its Postgres service, and a test asserting the engine/dialect driver resolves with only
`requirements.txt` installed.

**B-2 (P2) — `test_storage_directory_traversal_prevention` is a Windows-semantics test run on Linux.**
It walks six keys and expects `PathTraversalError` for each. Five pass; `C:\Windows\system32\cmd.exe`
does not, because `os.path.isabs()` is false for a drive-letter path on POSIX, so the key is treated
as an ordinary filename. **There is no escape:** `LocalStorageBackend._resolve_key` rewrites `\` to
`/` and the resolved target stays inside the root (verified:
`/tmp/aicte_private_storage/C:/Windows/system32/cmd.exe`, `relative_to(base_dir)` succeeds). On
Windows the same key *is* absolute and is correctly rejected — so this is behaviour that differs by
host OS, not a hole in the demo path. It only breaks the suite because CI runs Linux.

```console
$ python -m pytest -q backend/tests/integration/test_security_and_failure_paths.py::test_storage_directory_traversal_prevention
E  Failed: DID NOT RAISE PathTraversalError
1 failed                                        # backend suite: 1 failed, 388 passed, 22 skipped
```

Recommended fix (owner B): reject Windows drive prefixes/UNC (`^[A-Za-z]:` , `^\\\\`) explicitly in
`_resolve_key` *before* the `isabs` check, so the rejection no longer depends on the host OS, and
keep the test as is. Defense in depth rather than a demo blocker; do **not** mark the suite green by
deleting the key from the test.

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

- **Not merging PR #6** — `WORKSTREAMS.md` reserves the merge to the owner, and CI on the head
  SHA is red for the two pre-existing `backend/` reasons in §2.1, which C cannot fix or waive.
- **Not editing `backend/app/ocr_*.py`** — backend-owned until an approved migration
  (`WORKSTREAMS.md`, "OCR placement").
- **Not adding real or scanned institutional documents** — the corpora must stay synthetic.
- **Not extending the reproduction beyond synthetic pages** — every AI/OCR number here is
  Pillow-rendered synthetic text, not a scan of a real certificate. Nothing in this repository may
  be quoted as real-world OCR accuracy, compliance or authenticity evidence.
- **Not starting new OCR features** — no AI/OCR canonical requirement is currently unblocked.
