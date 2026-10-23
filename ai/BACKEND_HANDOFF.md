# Backend handoff: OCR extraction defects (known gaps)

Audience: the backend workstream that owns `backend/app/ocr_pipeline.py`. The
AI/OCR evaluation corpora pin these 17 defects as documented known gaps so the
evaluator keeps them visible instead of scoring them as passes or failures.
Every row below was reproduced live against the current extractor on this
branch; nothing here is inferred from tests alone.

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

## Real-engine evidence for the extractor gaps (2026-10-23)

The raster benchmark was run against real Tesseract 5.5.2 (`eng` + `hin`) on 24 synthetic
rendered pages (3 languages x 2 layouts x 8 corruption types, seed 42). Report:
`ai/reports/real_tesseract_5.5.2_count24_seed42.json`.

Aggregate structured-field results on **clean** pages, i.e. with no image corruption at all:

| Language | Clean field micro-F1 | Corrupted field micro-F1 | Cases |
|---|---:|---:|---:|
| `en` | 0.667 | 0.400 | 8 |
| `hi` | 0.000 | 0.000 | 8 |
| `bilingual` | 0.000 | 0.000 | 8 |

Reading: every Hindi-only and bilingual page loses **all** institutional fields even when the
OCR text is clean, because `backend/app/ocr_pipeline.py` has no Hindi label coverage for
these documents (`संस्थान`, `मान्यता तक`, `जारी करने की तिथि`) and no handling for
`Label / लेबल:` bilingual lines. This is the same class as defects #2 and #11 in the table
above and is covered by the acceptance criteria above - it is **not** a new defect id, it is
the measured aggregate impact of the documented ones.

Two AI-side defects were found and fixed while producing the measurement, so they are *not*
backend work:

- Hindi pages were rendered with a Latin font when no Devanagari font was installed, and
  `hi` cases were OCR'd with `-l hin` alone, which destroyed the Latin certificate numbers
  and institution names. `hi` now maps to `hin+eng`; the renderer resolves a
  Devanagari-capable font or marks the case unavailable.
- `--language` did not actually override the per-case language mapping.

Reproduce (real engine, Devanagari font required):

```bash
AICTE_DEVANAGARI_FONT=/path/to/NotoSansDevanagari.ttf \
  python ai/raster_benchmark.py --count 24 --seed 42 --real-engine \
  --json ai/reports/real_tesseract_5.5.2_count24_seed42.json
```
