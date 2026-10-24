# Extraction evaluation — synthetic corpus

A reproducible measurement of the institutional-field extractor against a synthetic
labelled corpus. **It is not a benchmark and not an accuracy claim.** Read
[What these numbers do not mean](#what-these-numbers-do-not-mean) before quoting anything.

## Run it

```bash
python -m pip install -r backend/requirements-dev.txt     # the only dependency set used
python ai/evaluate_extraction.py                          # human-readable report
python ai/evaluate_extraction.py --json report.json       # machine-readable
python ai/evaluate_extraction.py --check                  # exit 1 on any scored mismatch
python ai/evaluate_extraction.py \
  --corpus ai/corpus/extraction_cases.jsonl \
  --corpus ai/corpus/ocr_corruption_cases.jsonl --check   # separate slice reports
python -m pytest -q ai/tests                              # corpus and scorer tests (also runs in CI)
python ai/evaluate_extraction.py --json b.json --compare b.json  # compare against a baseline
python ai/evaluate_extraction.py --engine module:attribute ...    # evaluate a candidate engine (bake-off)
python ai/evaluate_extraction.py --corpus ai/corpus/ocr_corruption_cases.jsonl --normalize
                                                                 # evidence-only preprocessing diagnosis
```

By default the scorer imports `extract_institution_fields` from `backend.app.ocr_pipeline`
**read-only**. It does not modify, wrap or reimplement backend code, and no OCR engine is
required — the input is text, so Tesseract is irrelevant here. `--engine module:attribute`
substitutes any callable with the same input/output shape (`str` in, mapping of
field-name → `OCRField`-like object or plain value out) so candidate engines can be scored
against the same corpora without touching `backend/`. Invalid specs (`malformed`,
missing module, missing attribute) exit 1 with a clear error.

The loader validates each corpus before scoring: a missing path, malformed JSONL, a
missing or non-object `expected`, an empty file, or duplicate `case_id`s fails the run
with exit 1 and a message naming the file (and line). Each `--json` run fully replaces
its report file; it never merges with a previous report. Results are deterministic:
identical inputs and corpus produce byte-identical reports.

## What is measured

Label corpus: `ai/corpus/extraction_cases.jsonl` — 56 cases, all 56 scored. The 2 former
documented known gaps (`BND-002`, `HI-005`) were resolved by the backend fix merged from
`feature/backend-ocr-gap-fixes` (commit `eec3a81`) and migrated into the scored denominator.
Corruption slice: `ai/corpus/ocr_corruption_cases.jsonl` — 30 cases, 15 scored, 15 documented
known gaps. When more than one `--corpus` is supplied, the scorer reports each slice
independently and never combines their denominators.

| Category | Count | What it exercises |
|---|---|---|
| clean-label-en | 16 | every English label variant, `:` and `-` separators, spacing |
| clean-label-hi | 6 | Hindi labels for institution, certificate, dates, session |
| multi-field | 3 | realistic certificates with 3–5 fields |
| noise | 6 | surrounding prose, label without separator, empty value, unrelated text |
| ocr-corruption | 4 | doubled spaces, all-caps, mixed case, trailing punctuation |
| ambiguous-date | 6 | `DD/MM/YYYY`, long-form months, reversed/equal/multi-year sessions |
| invalid-date | 2 | impossible day (`2026-02-30`), impossible month (`2026-13`) |
| duplicate-labels | 3 | first label wins, deterministically |
| boundary | 7 | 3- and 160-character names, 2-character certificate, leap day |
| personal-data | 2 | applicant name and DOB must **not** be extracted |
| table-like | 1 | spaced columns |

The corruption slice categories are:

| Category | Count | What it exercises |
|---|---:|---|
| ocr-inserted-newline | 7 | labels and values split across OCR lines; CRLF line endings |
| ocr-misread-label | 9 | character substitutions, separator doubling and replacement, zero-width noise |
| ocr-latin-hindi-mix | 7 | Hindi labels with Latin values, mixed context, NFD-decomposed accent data |
| ocr-column-order | 7 | flattened, reordered or merged column output; order-independent labelled lines |

Per case, each expected field is compared **exactly** (string equality after the
extractor's own normalisation). Outcomes are true positives, false positives (wrong value
or unexpected field), and false negatives (expected but absent). For a case labelled `{}`,
*any* extracted field is a false positive. A case that raises is counted as a failure —
never skipped.

Reported: per-field precision/recall/F1, micro average, case exact-match rate, the number
of negative cases and how many produced a spurious extraction, and every wrong value.

## Current result

Run on 2026-10-24 on the post-merge state (backend fix `eec3a81` present):

```
micro (all fields)  tp=46  fp=0  fn=0   precision 1.000  recall 1.000  f1 1.000
case exact-match:   56/56
negative cases:     20, with a spurious extraction: 0
known gaps:         0
```

The separate corruption slice currently reports:

```
corruption slice:    15 scored cases, exact-match 15/15
negative cases:      7, with a spurious extraction: 0
known gaps:          15 (all still failing)
```

The 15 corruption-slice known gaps are deliberately excluded from its scored denominator.
They record recovery behaviour that is desirable but not implemented; they are not evidence
that the current extractor handles those corruptions.

**A perfect score here is expected and nearly meaningless.** The cases were written from
the extractor's documented behaviour on clean synthetic text. What this proves is that the
extractor still does what its documentation says, and that it refuses to guess on ambiguous
dates, reversed academic years, and personal data. It says nothing about a photographed,
skewed, low-resolution AICTE certificate.

## Known gaps (documented, not hidden)

Known gaps are reported in a separate section of the output and excluded from the scored set,
so they cannot inflate the numbers. If a gap starts passing, the report says
**"FIXED — remove the known_gap flag"**.

The two former label-corpus known gaps are resolved as of 2026-10-24:

| Case | Former defect | Resolution |
|---|---|---|
| `BND-002` | The documented minimum of 3 characters for `institution_name` was not enforced: `Institution Name: AB` extracted `AB`, because the `\s*` before the capture group backtracked and let `. {3,160}` consume the leading space. | Fixed by backend commit `eec3a81` (trimmed-length validation in `[3, 160]` + non-space first capture char); the `known_gap` flag was removed in commit `7c15e01`. |
| `HI-005` | The common Hindi spelling `शैक्षणिक सत्र` was not matched; only `शैक्षिक सत्र` was in the pattern. | Fixed by backend commit `eec3a81` (pattern now lists both spellings); the `known_gap` flag was removed in commit `7c15e01`. |

Neither was fixed here: `ai/**` must not edit `backend/**` (see
[`../WORKSTREAMS.md`](../WORKSTREAMS.md)). The fixes landed in the backend's own reviewed
PR (`feature/backend-ocr-gap-fixes`, PR #7) with OCR regression tests, and the corpus
metadata migrated the two cases into the scored denominator in a separate AI commit.

## Report fields and baseline comparison

Beyond the printed table, every report (human or `--json`) carries:

| Field | Meaning |
|---|---|
| `corpus` / `corpus_sha256` | Which corpus produced the numbers, and the exact bytes of it |
| `case_results` | Every scored case with its expected/extracted values, match status, error and category — the machine-readable failure artifact |
| `by_category` | Scored-case coverage per category: cases, exact matches and failing case ids |
| `known_gaps` | Documented broken behaviour, each with `still_failing` and its own `error` when it raises |
| `engine` | Which extractor produced the numbers (default `backend.app.ocr_pipeline:extract_institution_fields`); set by `--engine` |
| `confidences` (per case) | Field→confidence as reported by the engine (`OCRField.confidence`), present only when the engine supplies them; the scorer never invents confidence values |

To compare a change against a stored result, capture a baseline once and compare later:

```bash
python ai/evaluate_extraction.py --json baseline.json --quiet      # store a baseline
python ai/evaluate_extraction.py --compare baseline.json          # compare a current run
```

`--compare` reads the baseline only — it never writes to it. It reports, per corpus:
corpus-byte changes (a sha256 mismatch is shown explicitly; case ids are still compared),
scored cases that appear or disappear, **newly failing scored cases** (`NEW REGRESSIONS`,
exit 1), newly passing cases, known-gap flips in either direction, new/removed documented
gaps, new negative false positives (exit 1), and the micro-F1 delta. A corpus absent from
the baseline reports `no matching corpus in the baseline` and does not gate the run.
Multi-corpus baselines (`{"corpora": [...]}`) compare slice by slice, never as one merged
score.

### Exit-code policy for `--compare`

The command exits 1 (baseline verification failed) exactly when:

1. a case that scored success in the baseline now fails (mismatch or
   extraction error) - reported as `NEW REGRESSIONS`;
2. a slice with no baseline negative false positives now reports one -
   reported as `NEW REGRESSIONS`;
3. the stored baseline cannot be read or parsed.

Everything else is a visible note with exit 0: corpus-byte changes,
known-gap flags appearing or disappearing, cases added or removed, the
micro-F1 delta, and newly added cases that fail - no baseline result yet -
capture the next baseline with `--check` so they become protected).
A corpus absent from the baseline never gates the run. A
gapped case that starts passing is reported as `FIXED - remove the
known_gap flag` so a human reviews the flag before the case enters the
scored denominator.

A useful developer loop after touching anything the extractor depends on:

```bash
# before the change
python ai/evaluate_extraction.py --json /tmp/before.json
# after the change
python ai/evaluate_extraction.py --json /tmp/after.json --compare /tmp/before.json
```

Performance note (2026-10-23, this MacBook, .venv): a 600-case synthetic corpus scores in
~0.08 s wall time including interpreter startup. No optimisation is warranted or claimed.


## Engine bake-offs and preprocessing diagnosis

Canonical `docs/canonical/prd.md` requires OCR engine selection "via a labelled
synthetic-data bake-off". `--engine module:attribute` implements the evaluation half of
that requirement: any candidate callable is scored on the same corpora with the same
semantics, and the report names the engine it measured.

`--normalize` prints an **evidence-only** preprocessing diagnosis after the report: it
re-extracts every known-gap case from conservatively normalized text
(`ai/normalize.py`) and reports which gaps normalization alone would exact-match, plus
the rules that fired and `extraction_raised` ids. On the current corruption corpus it
fixes exactly `1/15` (`CMIS-009`, `remove-invisible-chars`) — the diagnosis quantifies
what preprocessing can and cannot contribute, it scores nothing and changes no exit
code. Deliberate scope limits of `ai/normalize.py` (each with provenance in its
docstring): it removes only characters that are never meaningful (zero-width/soft
hyphen/control characters), unifies representations (CRLF, U+2028/U+2029, NFKC,
whitespace) and does **not** attempt label re-joining, column reordering or fuzzy OCR
confusion correction — those need real policy decisions and belong to the backend-owned
extraction fix (`ai/BACKEND_HANDOFF.md`).

`ai/tests` runs in the shared `backend-tests` CI workflow; any regression the evaluator can
detect is therefore also a pull-request gate without an AI-specific configuration change.

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
not exist yet, so no percentage may be quoted anywhere. The full protocol a future
corpus must follow (strata, annotation discipline, uncertainty bounds, acceptance
criteria) is specified in [`REAL_CORPUS_PROTOCOL.md`](REAL_CORPUS_PROTOCOL.md).

## Adding cases

1. Append one JSON object per line to the appropriate corpus:
   `ai/corpus/extraction_cases.jsonl` for clean label behaviour or
   `ai/corpus/ocr_corruption_cases.jsonl` for realistic corruption:
   `{"case_id", "category", "notes", "text", "expected": {field: value, ...}}`.
   Use `"known_gap": true` only for behaviour you are deliberately documenting as broken.
2. Never include a real institution, person, certificate number or document — synthetic
   markers only (`ai/tests/test_evaluate.py` enforces this).
3. Run `python ai/evaluate_extraction.py --corpus <each corpus>`; a case that fails is a
   finding, not something to delete. Use repeated `--corpus` arguments to compare slices,
   not to create one merged score.
4. Run `python -m pytest -q ai/tests`.

Target the failure modes, not the count: duplicate near-identical clean-label cases add
nothing.

## OCR benchmark module (`ai/ocr_benchmark.py`)

A separate benchmark infrastructure module provides:

- **`OCREngine` abstract base class:** Adapter contract for image-to-text engines.
  Concrete subclasses implement `extract(image) -> dict[str, Any]`.
- **Transcription metrics:** Character Error Rate (CER) and Word Error Rate (WER)
  computed via standard Levenshtein edit distance. CER divides character-level edits by
  reference length; WER divides token-level edits by reference token count. Both return
  0.0 for identical inputs and 1.0 when either input is empty.
- **Structured-field scoring:** Per-field and micro-averaged precision/recall/F1 from
  aggregate TP, FP, FN counts. The extractor receives the case `text` string and returns
  a dict of field values.
- **Synthetic case generation:** Deterministic, seeded generation of labelled text
  fixtures with controlled corruption types (none, blur, skew, low_res, compression,
  low_contrast, spacing, latin_hindi_mix, inserted_newline, column_order).
- **Corpus I/O:** JSONL loading with strict validation (missing files, malformed JSON,
  duplicate case IDs, empty corpora all raise actionable errors) and writing.
- **Held-out partitioning:** Deterministic seed-based shuffled split with configurable
  fraction. Validates fraction bounds and minimum case count. Partition integrity checks
  detect case-ID overlap and text-level leakage.
- **Engine contract tests:** Mock-based checks that an engine returns dicts with
  string-or-None values without raising.

### Text-only vs. image-level evaluation

The workstream provides two distinct evaluation modules:

1. **Text extraction evaluator & benchmark** (`ai/evaluate_extraction.py`, `ai/ocr_benchmark.py`):
   Operates on text strings. Measures rule-based field extraction against hand-crafted synthetic
   cases and textual corruptions (misread characters, inserted newlines, column order).
2. **Genuine raster-image benchmark** (`ai/raster_benchmark.py`):
   Renders synthetic document images using Pillow and applies true raster pixel transformations
   (Gaussian blur, affine skew, low-resolution down/upsampling, JPEG compression artifacts,
   low contrast, sensor noise, 90-degree rotation). Measures paired clean vs. corrupted
   degradation deltas across transcription (CER/WER) and field extraction (precision/recall/F1).
   Works with real Tesseract when installed or a calibrated mock engine when system binaries are absent.
   Reports self-declare their rendering limits: without libraqm the `hi`/`bilingual`
   entries appear in `accuracy_invalid_languages` and their metrics are **not valid
   accuracy measurements** (the ground truth was not faithfully on the rendered image).
   They are not a bound on real accuracy in either direction.

### Running benchmark tests and evaluations

```bash
python -m pytest -q ai/tests/test_ocr_benchmark.py     # benchmark module tests
python -m pytest -q ai/tests/test_raster_benchmark.py  # raster image tests (67 tests)
python -m pytest -q ai/tests                            # all AI/OCR tests

# Run raster image benchmark CLI (generates paired images and computes degradation delta)
python ai/raster_benchmark.py --count 16 --json raster_report.json

# Pooled multi-seed evaluation with the real Tesseract engine
python ai/raster_benchmark.py --real-engine --seeds 11,23 --count 8 \
  --json ai/reports/tesseract_5.5.3_multiseed_s11_s23_count8_fontfix.json
```

### Pooled multi-seed evaluation (`--seeds`)

`run_benchmark_multiseed(seeds, count=…, engine=…)` or the CLI form
`--seeds 11,23,42 --count 8` evaluates one deterministic dataset **per seed** and
reports a pooled result alongside every per-seed baseline:

- **Dataset independence:** every seed has a distinct `dataset_fingerprint`. Duplicate
  seeds are rejected (`ValueError`; the CLI exits 1) instead of silently collapsing.
- **Pooling semantics:** pooled `pooled.clean_baseline` / `pooled.corrupted_evaluation`
  are micro-aggregated over **all evaluated cases of all seeds** — not the mean of
  per-seed means. With equal evaluated counts per seed these coincide; the
  `test_pooled_corrupted_cer_matches_equal_weight_mean` test pins that equivalence.
- **Per-metric summary:** `per_seed_summary.<metric>` carries
  `mean` / `sample_stddev` (ddof=1; `0.0` for fewer than two seeds) / `min` / `max` /
  `seeds` over that metric's per-seed baseline values.
- **Reconciliation:** `evaluated_pairs + unavailable_pairs + failed_pairs ==
  total_case_pairs` is verified inside the report
  (`reconciliation.…_equals_total`) — a broken sum is a bug, never hidden.
- **Rendering validity:** every report also carries `rendering`
  (`{raqm, raqm_version}` — the complex-script shaping availability of the
  generating environment) and `accuracy_invalid_languages`. Languages whose
  ground truth can only be faithfully rendered with shaping (`hi`,
  `bilingual`) are listed there when shaping is unavailable, together with
  `accuracy_valid: false`; the CLI prints an explicit warning line. Do not
  quote metrics for a listed language as accuracy.
- **Mid-run engine loss:** if a real engine disappears between seeds, the remaining
  seeds are **not** pooled; the report marks `available: false` and lists the seeds
  actually completed.

Sample artifacts: `ai/reports/tesseract_5.5.3_multiseed_s11_s23_count8_fontfix.json`
(real Tesseract 5.5.3, seeds 11/23, 16/16 pairs evaluated — corrupted CER spread across
seeds was ±0.005) and the historical older reports in the same directory.

### Engine-configuration comparison (`--tess-psm`)

The backend OCR adapter hard-codes `--psm 6`. To make the canonical
"engine/version selection via a labelled synthetic-data bake-off" requirement
measurable without new dependencies, `RealTesseractEngine` accepts `psm=` (0–13,
validated; CLI `--tess-psm`). `psm=6` keeps the backend-adapter contract path;
any other value runs a benchmark-only direct `pytesseract` call labelled
`tesseract-psm<N>` that mirrors the backend preprocessing exactly — the two
vehicles are distinguishable in every measurement (`recognition_vehicle`,
`engine` name, `psm` field), so a configuration comparison can never be
confused with the backend contract path.

Measured comparison (same seeds 11/23, count 8, count 16 pooled pairs, dataset
fingerprints identical per seed — the same raster images were scored):

| Metric (pooled) | psm 6 (backend, `…fontfix.json`) | psm 3 (`…psm3…json`) |
|---|---|---|
| clean CER / WER / F1 | **0.266 / 0.410 / 0.400** | 0.422 / 0.569 / 0.261 |
| corrupted CER / WER / F1 | 0.511 / 1.070 / **0.222** | 0.540 / 0.754 / 0.140 |
| degradation +CER / −F1 | 0.245 / **0.178** | 0.117 / 0.121 |

**Recommendation (owner decision pending):** keep `--psm 6` for field
extraction — it dominates psm 3 on clean and corrupted F1 and on corrupted
CER on this corpus. Corrupted WER is the one metric favouring psm 3 (1.070 vs
0.754): inspection shows the difference is spurious-word insertion on the
rotated/blur corruptions, not stronger recovery. Limitations: small pooled
sample (16 pairs), synthetic single-institution naming, and hi/bilingual
strata are rendering-invalid in this environment (no libraqm) — this
comparison is registered as a configuration bake-off, not cross-engine
evidence and not real-world accuracy. A cross-engine bake-off needs a second
installable OCR engine, blocked externally (dependency + licensing review).


