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
engine contract tests. The raster benchmark has now been executed against a **real
Tesseract 5.5.2** engine (eng + hin packs) on synthetic pages, and the report is committed
under [`reports/`](reports/README.md) with its provenance and verification record. The
working OCR implementation is still in `backend/` (see the OCR placement rule); no model or
external AI provider is introduced by this work.

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
| [`raster_benchmark.py`](raster_benchmark.py) | Genuine raster-image OCR evaluation: synthetic document image rendering (Pillow), pixel-level corruptions (blur, skew, low-res, JPEG compression, contrast, noise, rotation), paired clean/corrupted benchmark, and engine evaluation. |
| [`normalize.py`](normalize.py) | Conservative text normalization with provenance (zero-width removal, NFKC, line-break unification). |
| [`corpus/extraction_cases.jsonl`](corpus/extraction_cases.jsonl) | 56 labelled extraction cases (54 scored, 2 documented known gaps). |
| [`corpus/ocr_corruption_cases.jsonl`](corpus/ocr_corruption_cases.jsonl) | 30 OCR corruption cases (15 scored, 15 documented known gaps). |
| [`tests/test_evaluate.py`](tests/test_evaluate.py) | Tests for the extraction evaluator, corpus validation, and scoring semantics. |
| [`tests/test_ocr_benchmark.py`](tests/test_ocr_benchmark.py) | Tests for the OCR benchmark module: metrics, generation, scoring, contracts, corpus loading, partitioning. |
| [`tests/test_raster_benchmark.py`](tests/test_raster_benchmark.py) | Tests for the raster benchmark module: pixel transforms, document rendering, paired scoring, engine availability, script/font coverage, language override, measurement honesty, CLI. |
| [`reports/`](reports/README.md) | Committed benchmark reports (real Tesseract 5.5.2 on 24 synthetic pages) with provenance, reproduction steps and verification record. |
| [`EVALUATION.md`](EVALUATION.md) | What the evaluation measures, its limitations, and how to run it. |
| [`BACKEND_HANDOFF.md`](BACKEND_HANDOFF.md) | 17 documented extraction defects owned by the backend workstream. |

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
# All AI/OCR tests (237: evaluator 66, benchmark module 105, raster 66)
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

# Real Tesseract raster evaluation (requires tesseract in PATH; Devanagari cases need
# a Devanagari-capable font, auto-detected or set via AICTE_DEVANAGARI_FONT)
AICTE_DEVANAGARI_FONT=/path/to/NotoSansDevanagari.ttf \
  python ai/raster_benchmark.py --count 24 --seed 42 --real-engine \
  --json ai/reports/real_tesseract_5.5.2_count24_seed42.json

# Multi-seed stability check (per-seed metrics, case-weighted pooling, per-metric variance)
AICTE_DEVANAGARI_FONT=/path/to/NotoSansDevanagari.ttf \
  python ai/raster_benchmark.py --count 24 --seeds 42,7,13 --real-engine \
  --json ai/reports/real_tesseract_5.5.2_multiseed_3x24.json

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
- Real Tesseract execution requires the `tesseract` binary in PATH; when absent, the raster
  benchmark reports the missing prerequisite and refuses to fabricate a result.
- Devanagari raster cases additionally require a Devanagari-capable font for rendering
  (system fonts are auto-detected; `AICTE_DEVANAGARI_FONT` overrides). Without one, real-engine
  runs mark those cases `unavailable` with the reason instead of scoring replacement boxes.
- The recorded real-engine numbers (see [`EVALUATION.md`](EVALUATION.md#real-engine-raster-evaluation--tesseract-552-2026-10-23))
  come from 24 synthetic, Pillow-rendered pages — not scans of real certificates.
- The synthetic document images use programmatic layouts and font rendering; they are not
  photographed real-world paper documents.
- No held-out split exists for the text extraction corpus (cases were written alongside patterns).
- Hindi coverage is limited to five label variants and rendered Devanagari fonts.

## First task

[`../docs/development/STARTER_TASKS.md`](../docs/development/STARTER_TASKS.md) — task C1.
