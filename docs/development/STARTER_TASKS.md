# Starter and follow-up tasks — one per workstream

**Status:** the three original starter tasks (A1, B1, C1) are **implemented** on this
branch (PR #5) as reference implementations, so a contributor does not start from a blank
page and no two people write the same files. Their next tasks are A2, B2, C2 below.

Every command here was executed on 2026-10-23 against the branch that contains the code it
references. Where a command needs PR #5 to be merged first, that is stated.

Ownership, shared files and prohibitions: [`../../WORKSTREAMS.md`](../../WORKSTREAMS.md).
Setup and worktrees: [`PARALLEL_WORKFLOW.md`](PARALLEL_WORKFLOW.md).

---

## What is already built (do not rebuild these)

| Task | Where it lives | How to check it |
|---|---|---|
| **A1** frontend fixtures + state matrix + checker | `frontend/fixtures/*.json` (9 cases, captured from the API), `frontend/tools/capture_fixtures.py`, `frontend/tools/verify_fixtures.py`, `frontend/STATE_MATRIX.md` | `python frontend/tools/verify_fixtures.py` → `fixtures OK: 9 case(s)` |
| **B1** response models + contract tests | `backend/app/main.py` (`HealthResponse`, `ValidationResponse`, `Finding`), `backend/tests/test_api_contract.py` (16 tests) | `python -m pytest -q backend/tests/test_api_contract.py` |
| **C1** synthetic evaluation corpus + scorer | `ai/corpus/extraction_cases.jsonl` (56 cases), `ai/evaluate_extraction.py`, `ai/tests/test_evaluate.py` (17 tests), `ai/EVALUATION.md` | `python ai/evaluate_extraction.py --quiet` |

B1 did not change the emitted JSON: the A1 fixtures were captured **before** the models
existed and still replay byte-identically. Keep that property — if you change a response,
re-capture the fixtures in the same PR and update `docs/development/API_CONTRACT.md`.

## Read this before you branch

The research base (`014403a`) contains **none** of the coordination files, the
`frontend/fixtures/`, the `ai/corpus/` or `pyproject.toml`. They exist only on PR #5. So:

- **Preferred:** wait for PR #5 to be merged, then branch from `research/grounded-foundation`.
- **If you cannot wait:** branch from PR #5's head and declare the dependency in your PR
  description:

```bash
git fetch origin 'refs/heads/arena/*:refs/remotes/origin/arena/*'
git worktree add ../aicte-frontend -b feature/frontend-error-mapping origin/arena/97cf136c-aicte-compliance-ai
```

- **Never** create `WORKSTREAMS.md`, `docs/development/*`, `frontend/README.md` or
  `ai/README.md` on your branch: PR #4 and PR #5 own those paths and you would create an
  add/add conflict.

---

## A2 — Error mapping and state coverage (workstream A / `frontend/`)

**Why.** The API rejects bad input with a three-shape `422` envelope (`missing`,
`literal_error`, `value_error`). A UI that parses `detail[].msg` for logic breaks on the next
wording change. This task turns the envelope into a tested, framework-free mapping, and adds
a checker that keeps `STATE_MATRIX.md` honest as the UI grows.

**Files (all new, inside `frontend/`)**

- `frontend/tools/map_errors.py` — pure function
  `map_validation_errors(body: dict) -> dict[str, str]` mapping `detail[].loc[-1]` to a
  message, with an `"_unknown"` bucket for unrecognised `loc`. No framework, no imports
  outside the standard library.
- `frontend/tests/test_map_errors.py` — pytest cases built from the real fixtures
  (`validate-422-*.json`), including an unknown-`loc` body and a body with no `detail`.
- `frontend/tools/check_state_matrix.py` — asserts every row of `STATE_MATRIX.md` names
  either an existing fixture file or the literal phrase `none` / `no HTTP OCR endpoint`.
- `frontend/STATE_MATRIX.md` — add the A2 rows if you introduce a new state.

**Acceptance criteria**

- Mapping never raises on a malformed body; unknown shapes land in `_unknown`.
- Messages come from `detail[].msg` **verbatim** — do not invent friendlier text that
  could contradict the server.
- `python -m pytest -q frontend/tests` passes (run explicitly; pytest's `testpaths` only
  covers `backend/tests`).
- `python frontend/tools/check_state_matrix.py` exits 0.
- No framework, no bundler, no `package.json`.

**Dependencies.** Fixtures (A1) — present on PR #5. Wiring `frontend/tests` into CI is a
shared-file change (`.github/**`): propose it as a separate integration PR, do not edit the
workflow yourself.

**Prohibited.** Anything outside `frontend/`; parsing `detail[].msg` to decide *behaviour*
(map it for display only); treating a `422` as a compliance outcome.

**PR base / order.** `research/grounded-foundation` after PR #5 lands, else stacked on #5.

---

## B2 — Explicit error envelope without changing the wire format (workstream B / `backend/`)

**Why.** Error bodies are currently FastAPI's default `{"detail": [...]}`. The contract marks
a stable application envelope as **proposed**, and the frontend must treat 4xx bodies as
opaque until it exists. This task makes the 422 shape explicit and testable — documenting it
precisely — without inventing a new envelope consumers do not expect.

**Files**

- `backend/tests/test_validation_errors.py` (new) — one test per rejection rule
  (`institution_id` blank/too long, unknown `application_type`, empty or duplicate
  `required_documents`, blank `submitted_documents`, duplicate expiry keys, malformed
  `expiry_dates` date), asserting status `422`, `list(body) == ["detail"]`, and the
  `type`/`loc` for each. Plus a test that a *valid* request never returns 4xx.
- `docs/development/API_CONTRACT.md` — extend the error table **only if it already exists on
  your branch** (PR #5 owns that file; on the base, record the finding in your PR instead).
- Do **not** add middleware or a custom exception handler in this task: a new envelope is a
  breaking contract change that needs agreement from A and C first.

**Acceptance criteria**

- Existing tests pass unmodified (currently `223 passed, 1 skipped`).
- Every rejection rule is covered by at least one test; none is asserted from memory of
  the source.
- No change to any 200 response body (`python frontend/tools/verify_fixtures.py` still OK).
- No new dependency, no auth, no persistence, no upload route, no rule activation.

**Dependencies.** None. Pairs with A2 (same envelope, opposite side).

**Prohibited.** `backend/app/ocr_*.py`; `.github/**`; dependency changes; replacing the 422
envelope.

---

## C2 — Second corpus slice: realistic OCR corruption (workstream C / `ai/`)

**Why.** The current corpus is label-level text. The extractor's real risk is the text an
OCR engine actually produces: misread characters, inserted newlines mid-label, missing
colons, language mixing, and columns flattened in the wrong order. Those are not covered.

**Files (all new or additive, inside `ai/`)**

- `ai/corpus/ocr_corruption_cases.jsonl` — 20–30 cases in the existing schema, category
  values `ocr-inserted-newline`, `ocr-misread-label`, `ocr-latin-hindi-mix`,
  `ocr-column-order`. Add `"known_gap": true` for any behaviour you document as broken.
- `ai/evaluate_extraction.py` — accept `--corpus` more than once (or a directory) so the new
  slice is reported **separately** from the label corpus; never merge the two scores.
- `ai/tests/test_evaluate.py` — tests for the multi-corpus behavior.
- `ai/EVALUATION.md` — record the new slice, its categories and its limitations.

**Acceptance criteria**

- New cases are labelled with the *behaviour that is correct*, not with the current output:
  if the extractor gets it wrong and you believe it should be right, mark `known_gap`.
- Negative cases remain a real proportion; the report keeps separating slices.
- `python -m pytest -q ai/tests` passes; the banner still appears on every run.
- Still no real document, no engine dependency, no accuracy claim.

**Dependencies.** C1 (present on PR #5). No relation to A2/B2.

**Prohibited.** Editing `backend/`; moving the OCR module; adding an OCR dependency; any
real or scanned document; quoting a percentage anywhere.

---

## Verified commands (2026-10-23)

Executed in a fresh clone with three worktrees, on the PR #5 head (`4deeb36`) and on the
research base (`014403a`) for comparison.

| Command | PR #5 head | Research base `014403a` |
|---|---|---|
| `pip install -r backend/requirements-dev.txt` + `pip check` | OK | OK |
| `python -m pytest -q` | **223 passed, 1 skipped** | **54 passed, 1 skipped** |
| `python -m pytest -q ai/tests` | **17 passed** | exit 4, `ai/tests` does not exist |
| `python frontend/tools/verify_fixtures.py` | `fixtures OK: 9 case(s)` | file does not exist |
| `python ai/evaluate_extraction.py --quiet` | `54 cases, 54/54, F1 1.000, 0 spurious, 2 known gaps` | file does not exist |
| `ruff check backend/ ai/ frontend/ tools/` | clean | `ruff` not installed; 1 pre-existing `F401` |
| `python -m compileall -q backend/app backend/tests` | exit 0 | exit 0 |
| three `git worktree add … -b …` | 3 branches, 3 directories, all clean | same |

**On the base you get 54 tests, not 223.** Quote the number you actually saw.

## What these tasks deliberately do not do

- No framework, database, identity provider, storage vendor or hosting decision.
- No authentication, authorization, tenancy, upload, persistence or audit work.
- No regulatory rule activation and no OCR accuracy claim.
- No edits to `WORKSTREAMS.md`, `docs/development/*`, `.github/*` or root configuration;
  those are shared surfaces and need a separate proposal/integration PR.
