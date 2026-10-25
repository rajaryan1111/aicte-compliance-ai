# AI and document intelligence workstream

**Owner:** workstream C — **contributor not yet named** (see
[`../WORKSTREAMS.md`](../WORKSTREAMS.md)).
**Boundary:** this contributor works only in `ai/` during independent development.
**Status:** deterministic evaluation support is implemented here: a clean labelled corpus,
a separate realistic OCR-corruption slice, a reproducible multi-corpus scorer with corpus
fingerprints, per-category coverage, machine-readable per-case results, baseline
comparison (`--compare`), engine-swap evaluation (`--engine module:attribute`) for the
canonical synthetic-data bake-off, confidence passthrough, and an evidence-only
preprocessing diagnosis built on the conservative normalization library
[`ai/normalize.py`](normalize.py). An OCR benchmark module
([`ai/ocr_benchmark.py`](ocr_benchmark.py)) provides the engine adapter contract,
transcription metrics (CER, WER, exact match), structured-field scoring,
deterministic synthetic data generation, held-out partitioning, and mock-based
engine contract tests. The working OCR implementation is still in `backend/`
(see the OCR placement rule); no model or external provider is introduced by this work.

## Scope

- OCR engine adapters and document pre-processing.
- Institutional-field extraction, conservative normalization and provenance/evidence.
- Confidence signals, unresolved-field handling and human-review support.
- Synthetic labelled fixtures, regression tests and a held-out evaluation methodology.
- Transcription and structured-field extraction metrics.
- OCR benchmark infrastructure: adapter contract, synthetic data generation, and
  engine contract tests.
- Optional model/AI components only where a deterministic baseline and its limitations are
  documented.

## Module reference

| Module | Purpose |
|---|---|
| [`evaluate_extraction.py`](evaluate_extraction.py) | Corpus-driven extraction scorer with CLI (`--check`, `--json`, `--compare`, `--engine`, `--normalize`). |
| [`ocr_benchmark.py`](ocr_benchmark.py) | OCR engine adapter contract (`OCREngine` ABC), transcription metrics (CER, WER), structured-field scoring, synthetic case generation, corpus I/O, and held-out partitioning. |
| [`raster_benchmark.py`](raster_benchmark.py) | Genuine raster-image OCR evaluation: synthetic document image rendering (Pillow), pixel-level corruptions (blur, skew, low-res, JPEG compression, contrast, noise, rotation), paired clean/corrupted benchmark, engine evaluation, and the `--tess-psm` configuration bake-off vehicle. |
| [`normalize.py`](normalize.py) | Conservative text normalization with provenance (zero-width removal, NFKC, line-break unification). |
| [`corpus/extraction_cases.jsonl`](corpus/extraction_cases.jsonl) | 56 labelled extraction cases, all 56 scored (the 2 former known gaps were resolved by backend commit `eec3a81`). |
| [`corpus/ocr_corruption_cases.jsonl`](corpus/ocr_corruption_cases.jsonl) | 30 OCR corruption cases (15 scored, 15 documented known gaps). |
| [`tests/test_evaluate.py`](tests/test_evaluate.py) | Tests for the extraction evaluator, corpus validation, and scoring semantics. |
| [`tests/test_ocr_benchmark.py`](tests/test_ocr_benchmark.py) | Tests for the OCR benchmark module: metrics, generation, scoring, contracts, corpus loading, partitioning. |
| [`tests/test_raster_benchmark.py`](tests/test_raster_benchmark.py) | Tests for the raster benchmark module: pixel transforms, document rendering, paired scoring, engine availability, CLI. |
| [`EVALUATION.md`](EVALUATION.md) | What the evaluation measures, its limitations, and how to run it. |
| [`BACKEND_HANDOFF.md`](BACKEND_HANDOFF.md) | Documented extraction defects owned by the backend workstream (2 of the original 17 resolved; 15 remain). |

## OCR benchmark: metric definitions

**Character Error Rate (CER):** Levenshtein edit distance between reference and
hypothesis strings, divided by the reference length. CER = 0 for identical strings,
CER > 1 possible when the hypothesis has many extra characters.

**Word Error Rate (WER):** Levenshtein edit distance between the whitespace-split
token sequences of reference and hypothesis, divided by the number of reference tokens.
Same empty-input conventions as CER.

**Exact Transcription Rate:** 1.0 if reference == hypothesis, 0.0 otherwise.

**Structured-field scoring:** Per-field and micro-averaged precision/recall/F1 from
aggregate TP, FP, FN counts. The extractor receives the case `text` (a string) and
returns a dict of field names to values.

Empty-input conventions: both empty → 0.0; reference empty → 1.0; hypothesis empty → 1.0.

## OCR benchmark: text vs. image evaluation

The workstream supports two levels of evaluation:

1. **Text-level extraction benchmark** ([`ai/ocr_benchmark.py`](ocr_benchmark.py)):
   Measures text-to-field extraction on synthetic labelled texts with controlled
   textual corruption (character misreads, inserted newlines, column order, language mixing).
2. **Genuine raster-image benchmark** ([`ai/raster_benchmark.py`](raster_benchmark.py)):
   Renders synthetic document images (English, Hindi, bilingual, certificates, tables)
   and applies true pixel transformations:
   - Gaussian blur (`ImageFilter.GaussianBlur`)
   - Affine shear / skew
   - Low-resolution downsampling and upsampling
   - Real 8x8 block discrete cosine transform JPEG compression artifacts
   - Low contrast / illumination reduction
   - Pixel-level sensor/scanner noise
   - 90-degree document rotation
   Evaluates paired clean vs. corrupted images, reporting degradation deltas,
   per-corruption breakdowns, and language breakdowns. If Tesseract is not installed on
   the host system, the benchmark explicitly reports the missing prerequisite and
   supports a calibrated mock engine for automated regression verification.

## Running tests and evaluations

```bash
# All AI/OCR tests (189 tests: evaluator + benchmark + raster)
python -m pytest -q ai/tests

# Extraction evaluation (human-readable)
python ai/evaluate_extraction.py

# Multi-corpus evaluation with check mode
python ai/evaluate_extraction.py \
  --corpus ai/corpus/extraction_cases.jsonl \
  --corpus ai/corpus/ocr_corruption_cases.jsonl --check

# Baseline comparison
python ai/evaluate_extraction.py --json baseline.json
python ai/evaluate_extraction.py --compare baseline.json

# Raster image OCR benchmark (calibrated mock or real engine)
python ai/raster_benchmark.py --count 16
python ai/raster_benchmark.py --count 16 --json raster_report.json

# Attempt real Tesseract raster evaluation (requires tesseract in PATH)
python ai/raster_benchmark.py --real-engine

# Preprocessing diagnosis
python ai/evaluate_extraction.py --corpus ai/corpus/ocr_corruption_cases.jsonl --normalize

# Lint
ruff check ai/
```

## Rules

- Do not edit `frontend/` or `backend/` during independent work.
- Do not move or change the current `backend/app/ocr_pipeline.py` as part of folder setup.
  Any migration needs a separate PR, rewritten import paths and a reviewed interface; see
  [`../WORKSTREAMS.md`](../WORKSTREAMS.md#ocr-placement--stays-in-backend-until-an-approved-migration).
- Use synthetic documents only; never commit real institutional or personal data.
- Reject malformed, unsupported, oversized and excessive-pixel inputs before expensive
  processing.
- Do not guess ambiguous dates or missing values. Keep uncertain output unresolved.
- OCR results are advisory evidence, not proof of authenticity or compliance.
- Synthetic CI success is not a claim of real-world OCR accuracy. No accuracy number may be
  published without a labelled, held-out evaluation and a stated method.

## Known gaps and limitations

- The 17 backend-owned extraction defects are documented in [`BACKEND_HANDOFF.md`](BACKEND_HANDOFF.md).
- Real Tesseract engine execution requires the Tesseract system binary (`tesseract`) in PATH;
  when absent, the raster benchmark explicitly reports the missing prerequisite.
- The synthetic document images use programmatic layouts and font rendering; they are not
  photographed real-world paper documents.
- Font selection probes rendered glyph bitmaps (see `_font_renders_sample` in
  `raster_benchmark.py`): fonts that substitute a shared "tofu" box for missing
  characters — which once made every English letter OCR as O/0 while digits stayed
  correct — are rejected, and a Devanagari-capable font is required for `hi`/`bilingual`.
- Pillow on this host is built without libraqm (`PIL.features.check('raqm') == False`;
  the pinned official Pillow 11.3.0 macOS wheels simply do not bundle libraqm — Linux
  manylinux wheels do), so Devanagari is rendered glyph-by-glyph without complex-script
  shaping (conjuncts/matra ordering). Images generated without shaping do not faithfully
  contain the `hi`/`bilingual` ground truth, so their metrics are **invalid
  measurements** — neither a lower nor an upper bound on OCR quality on faithful input.
  Every raster benchmark report carries `rendering`, `accuracy_invalid_languages` and
  `accuracy_valid`; reports listing a language in `accuracy_invalid_languages` must not
  be quoted as accuracy for that language. Real-world Hindi accuracy remains unvalidated.
  Resolution path (needs an authorized environment change): install libraqm and rebuild
  Pillow, or generate the corpus on a Linux manylinux-wheel environment.
- No held-out split exists for the text extraction corpus (cases were written alongside patterns).
- Hindi coverage is limited to five label variants and rendered Devanagari fonts.

| [`SIH_READINESS.md`](SIH_READINESS.md) | SIH submission readiness from executed evidence: end-to-end flow verification, P0/P1 defects with owners, verified demo runbook, honest limitations. |

## First task

[`../docs/development/STARTER_TASKS.md`](../docs/development/STARTER_TASKS.md) — task C1.
