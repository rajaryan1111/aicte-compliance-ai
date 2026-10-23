# Extraction evaluation — synthetic corpus

A reproducible measurement of the institutional-field extractor against a synthetic
labelled corpus. **It is not a benchmark and not an accuracy claim.** Read
[What these numbers do not mean](#what-these-numbers-do-not-mean) before quoting anything.

## Run it

```bash
python -m pip install -r backend/requirements-dev.txt     # the only dependency set used
python ai/evaluate_extraction.py                          # human-readable report
python ai/evaluate_extraction.py --json report.json       # machine-readable
python ai/evaluate_extraction.py --check                  # exit 1 on a spurious extraction
python -m pytest -q ai/tests                              # 17 tests for corpus and scorer
```

The scorer imports `extract_institution_fields` from `backend.app.ocr_pipeline`
**read-only**. It does not modify, wrap or reimplement backend code, and no OCR engine is
required — the input is text, so Tesseract is irrelevant here.

## What is measured

Corpus: `ai/corpus/extraction_cases.jsonl` — 56 cases, 54 scored, 2 documented known gaps.

| Category | Count | What it exercises |
|---|---|---|
| clean-label-en | 16 | every English label variant, `:` and `-` separators, spacing |
| clean-label-hi | 5 | Hindi labels for institution, certificate, dates, session |
| multi-field | 3 | realistic certificates with 3–5 fields |
| noise | 6 | surrounding prose, label without separator, empty value, unrelated text |
| ocr-corruption | 4 | doubled spaces, all-caps, mixed case, trailing punctuation |
| ambiguous-date | 6 | `DD/MM/YYYY`, long-form months, reversed/equal/multi-year sessions |
| invalid-date | 2 | impossible day (`2026-02-30`), impossible month (`2026-13`) |
| duplicate-labels | 3 | first label wins, deterministically |
| boundary | 7 | 3- and 160-character names, 2-character certificate, leap day |
| personal-data | 2 | applicant name and DOB must **not** be extracted |
| table-like | 1 | spaced columns |
| known-gap | 2 | behaviour the extractor is known to get wrong (see below) |

Per case, each expected field is compared **exactly** (string equality after the
extractor's own normalisation). Outcomes are true positives, false positives (wrong value
or unexpected field), and false negatives (expected but absent). For a case labelled `{}`,
*any* extracted field is a false positive. A case that raises is counted as a failure —
never skipped.

Reported: per-field precision/recall/F1, micro average, case exact-match rate, the number
of negative cases and how many produced a spurious extraction, and every wrong value.

## Current result

Run on 2026-10-23:

```
micro (all fields)  tp=45  fp=0  fn=0   precision 1.000  recall 1.000  f1 1.000
case exact-match:   54/54
negative cases:     19, with a spurious extraction: 0
known gaps:         2 (both still failing)
```

**A perfect score here is expected and nearly meaningless.** The cases were written from
the extractor's documented behaviour on clean synthetic text. What this proves is that the
extractor still does what its documentation says, and that it refuses to guess on ambiguous
dates, reversed academic years, and personal data. It says nothing about a photographed,
skewed, low-resolution AICTE certificate.

## Known gaps (documented, not hidden)

Both are reported in a separate section of the output and are excluded from the scored set,
so they cannot inflate the numbers. If either starts passing, the report says
**"FIXED — remove the known_gap flag"**.

| Case | Defect | Owner |
|---|---|---|
| `BND-002` | The documented minimum of 3 characters for `institution_name` is not enforced: `Institution Name: AB` extracts `AB`, because the `\s*` before the capture group backtracks and lets `. {3,160}` consume the leading space. | backend workstream (OCR file) |
| `HI-005` | The common Hindi spelling `शैक्षणिक सत्र` is not matched; only `शैक्षिक सत्र` is in the pattern. | backend workstream (OCR file) |

Neither was fixed here: `ai/**` must not edit `backend/**` (see
[`../WORKSTREAMS.md`](../WORKSTREAMS.md)), and both changes deserve their own reviewed PR
with OCR regression tests.

## What these numbers do not mean

- **Not OCR accuracy.** The corpus is text. No image, scan, skew, blur, compression
  artefact, DPI variation or handwriting is involved. Real OCR errors are the hard part and
  are entirely absent.
- **Not a held-out evaluation.** The cases were written alongside the extractor's patterns.
  There is no train/test split, no independent annotator, and no inter-annotator agreement.
- **Not representative.** One synthetic institution naming convention, one date format
  family, five Hindi labels. Regional languages other than Hindi are uncovered.
- **Not compliance.** Extracting a date or a certificate number is evidence for a human
  reviewer; it proves neither authenticity nor regulatory compliance.
- **Not a regression guarantee for the engine.** `backend/tests/test_ocr_engine_integration.py`
  exercises Tesseract and skips when it is absent; the evaluator here never runs an engine.

A real accuracy statement needs a labelled, held-out set of representative scanned
documents with a stated annotation protocol, per-field metrics and error analysis. That does
not exist yet, so no percentage may be quoted anywhere.

## Adding cases

1. Append one JSON object per line to `ai/corpus/extraction_cases.jsonl`:
   `{"case_id", "category", "notes", "text", "expected": {field: value, ...}}`.
   Use `"known_gap": true` only for behaviour you are deliberately documenting as broken.
2. Never include a real institution, person, certificate number or document — synthetic
   markers only (`ai/tests/test_evaluate.py` enforces this).
3. Run `python ai/evaluate_extraction.py`; a case that fails is a finding, not something to
   delete.
4. Run `python -m pytest -q ai/tests`.

Target the failure modes, not the count: duplicate near-identical clean-label cases add
nothing.
