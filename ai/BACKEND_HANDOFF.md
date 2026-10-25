# Backend handoff: OCR extraction defects (known gaps)

Audience: the backend workstream that owns `backend/app/ocr_pipeline.py`. The
AI/OCR evaluation corpora pin these 17 defects as documented known gaps so the
evaluator keeps them visible instead of scoring them as passes or failures.
Every row below was reproduced live against the current extractor on this
branch; nothing here is inferred from tests alone.

## Status update (2026-10-24, post-merge of `feature/backend-ocr-gap-fixes`)

Backend commit `eec3a81` (merged to `main` in PR #7 and now merged into the
AI/OCR branch) resolved **2 of the 17** defects:

- ✅ `BND-002` (institution_name 3-character minimum enforced; captured value
  must be non-space-first and trimmed ≥3/≤160).
- ✅ `HI-005` (`शैक्षणिक सत्र` spelling added to the academic_year pattern).

The corpus metadata followed in `ai` commit `7c15e01` style (mirrored by the
merge): both `known_gap` flags were removed and both cases now score in the
label corpus's scored denominator (extraction slice: 56/56 exact, 0 known
gaps, verified live on the merged branch).

**The remaining 15 corruption-slice cases were all re-verified as still
failing** against the fixed extractor (evaluator `--check` exit 0, 15 known
gaps reported, 15/15 scored cases exact). Everything below therefore describes
today's state except for the two resolved rows, marked ✅ above and in the
table comments; the PR acceptance criteria now apply to cases
`CNL-001…CMIS-009`, `CLH-005`, `CCO-002/003/005` only.

## Status update (2026-10-25, `arena/677eccaa-aicte-compliance-ai`, PR #11)

**All 15 remaining corruption-slice gaps are resolved**, and both
backend-owned findings below are fixed. The table and reproductions under
this section are retained as the historical audit record; the case list it
describes is now the scored regression corpus.

- Resolved in `5a4061c` (`fix(ocr): resolve the 15 documented extraction gaps;
  re-score corruption corpus`): `CNL-001…004`, `CMIS-001…004`, `CMIS-007…009`,
  `CLH-005`, `CCO-002/003/005`. Per the acceptance criteria above, every
  `known_gap` flag was removed in the same commit so the cases migrated into
  the scored denominator.
- Resolved in `e9569e6`: the `LocalStorageBackend` Windows-drive traversal
  defect (volume-qualified keys are now rejected with `PathTraversalError` on
  every platform; `test_storage_directory_traversal_prevention` passes).
- Resolved in `437e447`: the test font path is now portable
  (`backend/tests/test_ocr_engine_integration.py` probes a cross-platform font
  candidate list and skips with a reason when none is present), alongside
  three raster-suite CI-parity fixes.
- Resolved in `889d9eb`: the psycopg root cause below is fixed by
  `normalize_database_url()` (bare `postgresql://`/`postgres://` URLs resolve
  to the installed `psycopg2` driver at every engine-construction site;
  two regression tests pin the behavior).

Acceptance evidence for the extractor rework (old extractor + flagged corpora
as a stored baseline report vs this branch):

```bash
python ai/evaluate_extraction.py --corpus ai/corpus/extraction_cases.jsonl \
  --corpus ai/corpus/ocr_corruption_cases.jsonl --check --compare <baseline>
```

- `extraction_cases.jsonl`: 56/56 exact, micro F1 1.000
- `ocr_corruption_cases.jsonl`: 30/30 exact (the 15 former gaps re-scored),
  micro F1 1.000; negative false positives 0 of 7 slice negatives (0 of 27
  across both corpora)
- `--check --compare` exits 0: no NEW REGRESSIONS and no NEW negative false
  positives; the diff records only the 15 gap→scored migrations and the
  corpus-byte change.

The label-level recovery (letter confusions, doubled separators, zero-width
characters, rejoined wrapped labels) is conservative and applied to labels
only; values are still parsed strictly (ISO dates only, identifier charset,
3–160 character names). Wrong-value cases (`CMIS-007`, `CNL-003`) now end in
the correct value.

## How to reproduce

```bash
.venv/bin/python ai/evaluate_extraction.py \
  --corpus ai/corpus/extraction_cases.jsonl \
  --corpus ai/corpus/ocr_corruption_cases.jsonl   # --check optional; documented gaps exit 0
```

Per-case observed extraction (the `Actual` column below comes from this):

```bash
# corpus paths are passed to python after the heredoc marker, so they arrive
# in sys.argv[1:] (verified: `python - arg` puts `arg` at sys.argv[1])
.venv/bin/python - <<'PY' ai/corpus/extraction_cases.jsonl ai/corpus/ocr_corruption_cases.jsonl
import json, sys
sys.path.insert(0, ".")
from backend.app.ocr_pipeline import extract_institution_fields
for corpus_path in sys.argv[1:]:
    cases = [json.loads(l) for l in open(corpus_path, encoding="utf-8") if l.strip()]
    for c in cases:
        if c.get("known_gap"):
            got = extract_institution_fields(c["text"])
            got = {k: (v.value if hasattr(v, "value") else v) for k, v in got.items()}
            print(c["case_id"], "->", json.dumps(got, ensure_ascii=False))
PY
```

The evaluator's own report shows the same status: each case prints
`STILL FAILING` with its note, is excluded from the scored denominator, and a
gap that starts passing is flagged `FIXED — remove the known_gap flag`.

## Severity convention

- **High** — the extractor silently returns *wrong data* (worse than omitting).
- **Medium** — an unambiguous field is dropped (omission, no wrong value).

## The 17 documented defects

| # | Case ID | Severity | Synthetic input (one line) | Expected (correct behavior) | Actual (observed this audit) | Impact | Corpus command |
|---|---------|----------|----------------------------|------------------------------|------------------------------|--------|----------------|
| 1 | `BND-002` | High | `Institution Name: AB` | `{}` | {"institution_name": "AB"} | wrong value returned where correct data is expected | `--corpus ai/corpus/extraction_cases.jsonl` |
| 2 | `HI-005` | Medium | `शैक्षणिक सत्र: 2026/2027` | `{"academic_year": "2026-2027"}` | {} (no field extracted) | field dropped; value unambiguous | `--corpus ai/corpus/extraction_cases.jsonl` |
| 3 | `CNL-001` | Medium | `Institution Name: Example Technical Insti...` | `{"institution_name": "Example Technical I...` | {} | field dropped; value unambiguous | `--corpus ai/corpus/ocr_corruption_cases.jsonl` |
| 4 | `CNL-002` | Medium | `Valid Until: 2027-04-30` | `{"valid_until": "2027-04-30"}` | {} | field dropped; value unambiguous | `--corpus ai/corpus/ocr_corruption_cases.jsonl` |
| 5 | `CNL-003` | High | `Institution Name: Example Technical Insti...` | `{"institution_name": "Example Technical I...` | {"institution_name": "Example Technical"} (truncated) | wrong value returned where correct data is expected | `--corpus ai/corpus/ocr_corruption_cases.jsonl` |
| 6 | `CNL-004` | Medium | `प्रमाणपत्र संख्या: CERT/2026/0099` | `{"certificate_number": "CERT/2026/0099"}` | {} | field dropped; value unambiguous | `--corpus ai/corpus/ocr_corruption_cases.jsonl` |
| 7 | `CMIS-001` | Medium | `Instituti0n Name: Example Technical Insti...` | `{"institution_name": "Example Technical I...` | {} | field dropped; value unambiguous | `--corpus ai/corpus/ocr_corruption_cases.jsonl` |
| 8 | `CMIS-002` | Medium | `Certificate N0: CERT/2026/0099` | `{"certificate_number": "CERT/2026/0099"}` | {} | field dropped; value unambiguous | `--corpus ai/corpus/ocr_corruption_cases.jsonl` |
| 9 | `CMIS-003` | Medium | `Valid Untill: 2027-04-30` | `{"valid_until": "2027-04-30"}` | {} | field dropped; value unambiguous | `--corpus ai/corpus/ocr_corruption_cases.jsonl` |
| 10 | `CMIS-004` | Medium | `lssue Date: 2026-04-30` | `{"issue_date": "2026-04-30"}` | {} | field dropped; value unambiguous | `--corpus ai/corpus/ocr_corruption_cases.jsonl` |
| 11 | `CLH-005` | Medium | `शैक्षणिक सत्र: 2026/2027` | `{"academic_year": "2026-2027"}` | {} | field dropped; value unambiguous | `--corpus ai/corpus/ocr_corruption_cases.jsonl` |
| 12 | `CCO-002` | Medium | `Institution Name Certificate No Example T...` | `{"institution_name": "Example Technical I...` | {} | 2 fields lost; both unambiguous | `--corpus ai/corpus/ocr_corruption_cases.jsonl` |
| 13 | `CCO-003` | Medium | `Certificate No: CERT/2026/0099 Institutio...` | `{"certificate_number": "CERT/2026/0099", ...` | {} | 2 fields lost; both unambiguous | `--corpus ai/corpus/ocr_corruption_cases.jsonl` |
| 14 | `CCO-005` | Medium | `Valid Until: 2027-04-30 Institution Name:...` | `{"valid_until": "2027-04-30", "institutio...` | {} | 2 fields lost; both unambiguous | `--corpus ai/corpus/ocr_corruption_cases.jsonl` |
| 15 | `CMIS-007` | High | `Institution Name:: Example Technical Inst...` | `{"institution_name": "Example Technical I...` | {"institution_name": ": Example Technical Institute"} (leading ": ") | wrong value returned where correct data is expected | `--corpus ai/corpus/ocr_corruption_cases.jsonl` |
| 16 | `CMIS-008` | Medium | `Certificate No; CERT/2026/0099` | `{"certificate_number": "CERT/2026/0099"}` | {} | field dropped; value unambiguous | `--corpus ai/corpus/ocr_corruption_cases.jsonl` |
| 17 | `CMIS-009` | Medium | `Institution​ Name: Example College` | `{"institution_name": "Example College"}` | {} | field dropped; value unambiguous | `--corpus ai/corpus/ocr_corruption_cases.jsonl` |

Every input is single-label, single-line OCR text with exactly the corruption
described; the full multi-line `text` for each row is in the corpus files:
`ai/corpus/extraction_cases.jsonl` (BND-002, HI-005) and
`ai/corpus/ocr_corruption_cases.jsonl` (the 15 corruption cases, categories
`ocr-inserted-newline`, `ocr-misread-label`, `ocr-latin-hindi-mix`,
`ocr-column-order`).

## Acceptance criteria for the fix PR

1. All 17 cases stop failing; then remove each case's `known_gap` flag in the
   corpus commit so it migrates into the scored denominator (a flagged case
   that passes is reported as `FIXED — remove the known_gap flag`).
2. Run the two corpora with `--check`; the run must stay exit 0 and the
   micro/exact-match numbers must only improve. Use `--compare <baseline.json>`
   against a stored baseline report to prove no scored case regressed and no
   new negative false positive appeared (both conditions make `--compare` exit 1).
3. Wrong-value defects (BND-002, CMIS-007, CNL-003) must end in the correct
   value or a defensible omission — never a silently corrupted value.

## Scope statement

These are the 17 **documented, reproduced** gap cases from the corpora. During
this audit no *new, previously unreported* extractor defect was observed beyond
them; the evaluator's two earlier diagnostic defects (gap-exception visibility
in human output, `--check --help` wording) were fixed separately in commit
`0d92cc0` and are not backend-owned. The corpora are synthetic, hand-written
cases: they prove per-case behavior, not real-world OCR accuracy.

## New backend-owned finding (2026-10-24): LocalStorageBackend accepts Windows-drive path keys on POSIX

`backend/tests/integration/test_security_and_failure_paths.py::
test_storage_directory_traversal_prevention` fails on 1 of its 6 traversal keys:
`C:\Windows\system32\cmd.exe`.

- Reproduce: `.venv/bin/python -m pytest -q
  backend/tests/integration/test_security_and_failure_paths.py::test_storage_directory_traversal_prevention`
  (fails on every POSIX host — Linux CI included).
- Root cause (read-only inspection of `backend/app/core/storage.py`):
  `LocalStorageBackend._resolve_key` rejects absolute POSIX paths, leading slashes,
  and `..`/`.` components, but a Windows drive path (`C:\…`) has none of those. On
  POSIX `os.path.isabs` is False for it and its `\`-split parts contain no `..`, so
  it resolves to `base_dir/C:/Windows/system32/cmd.exe` and `put()` succeeds —
  `pytest.raises(PathTraversalError)` then fails with DID NOT RAISE.
  Verified key-by-key: the other 5 keys all raise.
- Severity: medium-hardening (no user-facing write path today feeds raw keys to
  `LocalStorageBackend`; the injectable backend accepts arbitrary keys, so every
  future caller needs this guard).
- Expected: reject keys containing a Windows drive-letter component (or any
  backslash-separated segment resolving outside base_dir) with `PathTraversalError`,
  consistently on every OS.
- Attribution: backend-owned file (`backend/app/core/storage.py`, milestone B6) —
  not modified by the AI/OCR workstream.

## New backend-owned finding (2026-10-24): test font path is not portable

`backend/tests/test_ocr_engine_integration.py::
test_tesseract_reads_synthetic_institution_document` loads a hardcoded Linux
font path and therefore fails on any non-Linux host that has Tesseract
installed (the test's own `skipif` then stops skipping).

- Reproduce: `.venv/bin/python -m pytest -q backend/tests/
test_ocr_engine_integration.py` on macOS with `tesseract` in PATH.
- Expected: the test itself resolves a usable font (e.g. falls back to a
  bundled/system font list) or skips when no supported font is available.
- Actual: `PIL.ImageFont.truetype("/usr/share/fonts/truetype/dejavu/
  DejaVuSans.ttf", 58)` raises `OSError: cannot open resource` (macOS has no
  `/usr/share/fonts` truetype tree).
- Severity: low (test-only, no production extraction behavior); it flips the
  repository suite from `224 passed, 1 skipped` to `1 failed, 224 passed` on
  macOS hosts, so CI parity depends on it.
- Attribution: backend-owned file — not modified by the AI/OCR workstream.
  Evidence recorded here because the failure invalidates the historical
  `pytest -q` full-suite counts reported for this branch.

## CI verification (2026-10-24): GitHub Actions on this branch and `main`

Fetched check results for HEAD `580faf6` ([PR #10](https://github.com/rajaryan1111/aicte-compliance-ai/pull/10) state OPEN, MERGEABLE):

- **`backend-tests` check FAILURE** (run `40104526342`, 19 s): exactly the
  Windows-drive traversal defect above on Linux CI —
  `FAILED backend/tests/integration/test_security_and_failure_paths.py::
  test_storage_directory_traversal_prevention - Failed: DID NOT RAISE
  PathTraversalError`, suite `1 failed, 388 passed, 22 skipped`. Confirms the
  finding is OS-independent despite the macOS-specific test page: the traversal
  gap reproduces on every platform. The font-path test **passes on Linux CI**
  as predicted by its section above (hard-coded Linux path resolves there).
- **`real-infrastructure-integration` check FAILURE**: `ModuleNotFoundError:
  No module named 'psycopg'` in the "Apply Alembic migrations to fresh
  PostgreSQL" step. Root cause narrowed from the live stack trace (run
  `40070848311`): SQLAlchemy resolved the **psycopg v3 dialect**
  (`site-packages/sqlalchemy/dialects/postgresql/psycopg.py` → `import psycopg`),
  but the installed environment only supplies the v2 driver
  (`psycopg2-binary`, imported as `psycopg2`). **VERIFICATION (reproduced
  locally in the project venv 2026-10-24): the URL is a plain
  `postgresql://…`** — `.github/workflows/backend-tests.yml` sets
  `DATABASE_URL: postgresql://aicte_test:…`, `backend/alembic/env.py` injects
  `DATABASE_URL` into `sqlalchemy.url`, and no `+psycopg` suffix exists
  anywhere. The v3 import happens because the project's SQLAlchemy **2.1.6**
  resolves a bare `postgresql://` URL to its unified **psycopg (v3) dialect by
  default** (the exact failing frame
  `sqlalchemy/dialects/postgresql/psycopg.py:497 → import psycopg` reproduced
  identically locally). The earlier hypothesis that the URL carries a
  `postgresql+psycopg://` suffix was wrong and is corrected here.
  Verified fix options (both validated locally; the implementing files are
  backend/infra-owned — not modified by this workstream):
  - **A (no new dependency, verified working)**: force the declared v2 driver —
    normalize the URL to `postgresql+psycopg2://` in
    `backend/alembic/env.py::get_url()` (and optionally
    `backend/app/db/session.py::get_database_url()`), or pin
    `SQLAlchemy>=2.0,<2.1` in `backend/requirements.txt`. Local venv proof:
    `create_engine("postgresql+psycopg2://…")` selects `PGDialect_psycopg2`
    with `psycopg2 2.9.13` under SQLAlchemy 2.1.6.
  - **B (new dependency)**: add `psycopg[binary]` to `backend/requirements.txt`
    to match the SQLAlchemy ≥ 2.1 default dialect.
  Not an OCR or backend-logic defect on the OCR path; pre-existing on `main`
  (same run proves it). Acceptance check: `python -m alembic -c
  backend/alembic.ini upgrade head` against a live `DATABASE_URL` exits 0.
  Owner correction note 2 (requirements intent): option A keeps the declared
  dependency unchanged; option B changes a backend-owned requirements file —
  both require the backend owner's authorization either way.
- **`optional-ocr-integration` check SUCCESS** — the OCR-specific integration
  gate for this workstream passes.
- **Both failures pre-exist on `main`**: run `40070848311` (`main`, 06:36 UTC
  same day) shows the identical traversal failure (`1 failed, 388 passed,
  22 skipped`) and the identical psycopg migration error. PR #10 therefore
  introduces **no new check failure**; merge-readiness is not degraded by the
  branch. Both reds remain backend/CI-owner action items.
