# Protocol for real-document OCR evaluation (not yet executed)

Status: `NOT_AVAILABLE` — the corpus described here does not exist. No accuracy
percentage may be quoted for real documents anywhere in this repository until a
run following this protocol is recorded. This document exists so the required
evidence is precisely specified *before* any data collection starts, per
[`EVALUATION.md`](EVALUATION.md) ("A real accuracy statement needs a labelled,
held-out set …").

## What this corpus is for

A single claim only: **field-level extraction quality of the current OCR +
extraction pipeline on representative jurisdiction-style certificate scans**,
reported per field, per stratum, with uncertainty bounds. It establishes
neither document authenticity, nor regulatory compliance, nor "production
readiness" (see [`../WORKSTREAMS.md`](../WORKSTREAMS.md): OCR output is
advisory, never verified evidence).

## Corpus design

- **Source.** Documents must be either (a) synthetic images rendered from
  generated ground truth using the raster pipeline in
  [`raster_benchmark.py`](raster_benchmark.py), or (b) real institutional
  documents imported only with explicit written authorization from a named
  owner. Personal names, certificate numbers and signatures in real documents
  must be replaced or anonymized at collection time; the repository never
  stores real institutional data (WORKSTREAMS prohibited list).
- **Strata (each ≥ 30 documents, pre-registered before any evaluation run):**
  1. English clean label layout, clean render
  2. English, degraded scan (noise/contrast)
  3. Hindi clean label layout (`hin` + `eng`, shaped rendering required)
  4. English/Hindi bilingual single page
  5. Flattened/reordered column output (the class the 15 corruption gaps
     model: `ocr-column-order`)
  6. rotated/skewed page (±1–3° realistic skew)
  Stratification fields: language, degradation level, layout class, DPI,
  engine config.
- **Held-out discipline.** Cases authored by a person who has read the
  extractor's rules are annotated in the authoring set; the evaluation set
  must be labelled by someone who has *not* read `backend/app/ocr_pipeline.py`
  and frozen (corpus sha256 recorded) before any tuning or threshold
  adjustment. No corpus line may be edited after freezing;
  `ai/tests/test_evaluate.py` already enforces the no-real-data rule.

## Ground truth and annotation

- Ground truth is the **field dictionary** matching the extractor contract:
  `institution_name`, `certificate_number`, `application_reference`,
  `issue_date`, `valid_until`, `academic_year` — ISO dates, `YYYY-YYYY`
  academic sessions, and the exact certificate string including separators.
- Two independent annotators per document; disagreement adjudicated by a
  third; report raw inter-annotator agreement before adjudication. Fields not
  legible to a human at 100% zoom are marked `NOT_GROUND_TRUTH` and excluded
  from both numerator and denominator (never scored as a model failure).

## Metrics and analysis

- Field extraction: reuse the evaluator unchanged (`evaluate_extraction.py`
  with `--engine` pointing at the full image→fields pipeline): per-field
  precision/recall/F1, true/false-positive accounting, exact-match rate, per
  stratum — never only corpus-wide aggregates.
- Text layer: document-level CER/WER via the raster benchmark report, only
  where rendering validity is established (`accuracy_valid` true; see the
  `rendering` fields in raster reports — a Hindi/bilingual sample rendered
  without proper Devanagari shaping must be excluded from the measurement rather
  than scored).
- Uncertainty: stratified bootstrap 95% CIs (≥ 2,000 resamples, case-level);
  a delta is only reported as an improvement when the CI excludes 0.
- Failure analysis: every non-exact case categorized (OCR text error /
  label mismatch / segmentation / engine failure) with counts; engine identity,
  version, language packs, and rendering capabilities recorded in every report.

## Acceptance before any percentage is quoted

1. `--check`-style run recorded in `ai/reports/` with corpus fingerprint,
   engine version, annotation-agreement figures and reconciliation
   (evaluated + unavailable + failed == total).
2. Two evaluators (or a scripted independent recomputation) reproduce headline
   numbers from the raw JSON.
3. The write-up states the corpus authoring relationship to the code (who saw
   what, when) and repeats the synthetic-only scope limitation.

## What is explicitly out of scope

Real-world accuracy, authenticity, compliance, or production readiness remain
outside what this protocol can establish. Closing regulatory/Phase-0 gates and
real institutional data authorization belong to their owning workstreams.
