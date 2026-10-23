# Recorded benchmark reports (workstream C / `ai/`)

Machine-readable output of the AI/OCR evaluation modules, committed so that every
accuracy claim in [`../EVALUATION.md`](../EVALUATION.md) points at an artefact a reviewer
can re-run and diff.

**None of these are real-world document accuracy.** They are measurements of a real OCR
engine on *synthetic, programmatically rendered* pages. Read the limits at the bottom of
this file before quoting a number.

## Files

| File | Engine | Dataset | Notes |
|---|---|---|---|
| `real_tesseract_5.5.2_count24_seed42.json` | real Tesseract 5.5.2 | 24 synthetic documents, seed 42 | paired clean/corrupted raster benchmark, `eng`/`hi`/`bilingual` |
| `real_tesseract_5.5.2_multiseed_3x24.json` | real Tesseract 5.5.2 | 3 seeds (42, 7, 13) × 24 synthetic documents = 72 cases | paired clean/corrupted raster benchmark, pooled metrics plus per-seed variance |

A mock-engine report is deliberately **not** stored here: the calibrated mock is a test
double, its numbers come from the reference text rather than the pixels, and storing one
next to a real-engine report invites the two being confused. Mock behaviour is pinned by
`ai/tests/test_raster_benchmark.py` instead.

## Provenance of `real_tesseract_5.5.2_count24_seed42.json`

| Item | Value |
|---|---|
| Generated | 2026-10-23 |
| Command | `python ai/raster_benchmark.py --count 24 --seed 42 --real-engine --json ai/reports/real_tesseract_5.5.2_count24_seed42.json` |
| Engine | Tesseract `5.5.2-23-g397887` (Leptonica 1.88.0) |
| Language data | `tessdata_fast`: `eng`, `hin` (also `deu` present, unused) |
| Language settings | `en → eng`, `hi → hin+eng`, `bilingual → eng+hin` |
| Render font, Latin | `DejaVuSans.ttf` |
| Render font, Devanagari | `NotoSansDevanagari.ttf` (OFL 1.1, Google Fonts), supplied through `AICTE_DEVANAGARI_FONT`; in the recording container it lived at `/tmp/fonts/NotoSansDevanagari.ttf` (an ephemeral path — the report stores it verbatim rather than pretending it is reproducible) |
| Dataset | 24 cases = 3 languages × 2 layouts × 8 corruption types, paired clean/corrupted |
| Cases scored | 24 evaluated, 0 unavailable, 0 errors |
| Wall time | 18.8 s |
| Determinism | a second run in a separate process produced a byte-identical report apart from `duration_seconds` |

### Reproducing it on another host

```bash
# Tesseract 5.x + the eng/hin packs must be installed (OS package manager, or the
# `tesseract-bin` PyPI wheel for a self-contained binary).
python -m pip install pytesseract Pillow

# Devanagari rendering needs a font with Devanagari glyphs. Without one, every
# hi/bilingual case is reported "unavailable" instead of being silently scored
# against images that contain replacement boxes.
export AICTE_DEVANAGARI_FONT=/path/to/NotoSansDevanagari.ttf

python ai/raster_benchmark.py --count 24 --seed 42 --real-engine \
  --json ai/reports/real_tesseract_5.5.2_count24_seed42.json
```

`AICTE_DEVANAGARI_FONT` is only an override: on macOS the system Devanagari fonts and on
Linux the Noto/Lohit/Gargi/Samyak paths are found automatically.

## Provenance of `real_tesseract_5.5.2_multiseed_3x24.json`

Same engine, packs, fonts and dataset shape as the single-seed report above, run over three
seeds so the spread is visible instead of a single number being quoted as if it were stable.

| Item | Value |
|---|---|
| Generated | 2026-10-23 |
| Command | `python ai/raster_benchmark.py --count 24 --seeds 42,7,13 --real-engine --json ai/reports/real_tesseract_5.5.2_multiseed_3x24.json` |
| Cases | 72 (3 seeds × 24), 24 per language, 72 evaluated, 0 unavailable, 0 errors |
| Pooling | case-weighted: pooled figures come from all 72 per-case rows, never a mean of per-seed means |
| Variance | sample standard deviation (`n-1`) across the three per-seed aggregates |
| Wall time | 59.2 s |
| Determinism | per-case rows are identical to running each seed individually; `duration_seconds` is the only varying field |

### Measured (pooled, 72 synthetic pages)

| Metric | Clean | Corrupted |
|---|---:|---:|
| CER | 0.1857 | 0.4443 |
| WER | 0.3404 | 0.9823 |
| Exact match | 0.1667 | 0.0833 |
| Field micro-F1 | 0.2898 | 0.1527 |

Seed-to-seed spread (CER): clean mean 0.1857, sd 0.0184 (0.1662–0.2028); corrupted mean
0.4443, sd 0.0245 (0.4264–0.4722). The spread is reported so a single seed's figure is not
mistaken for a precise estimate.

## Verification performed on this report

- Every per-case `cer`, `wer`, `tp`, `fp`, `fn` was recomputed by a **separate
  implementation** (pure-Python Levenshtein, independent field counting) straight from the
  stored `case_results`: 48 of 48 case-sides matched for the single-seed report and 144 of 144
  for the multi-seed report (0 mismatches across 432 metric checks).
- Pooled multi-seed aggregates were recomputed from the concatenated per-case rows and matched
  exactly; the `variance` block was recomputed with `statistics.stdev` and matched.
- Aggregate `clean_baseline` / `corrupted_evaluation` were recomputed from the per-case
  rows and matched to 4 decimal places.
- `evaluated_count + unavailable_count` accounts for every generated case (24 + 0).
- The report was regenerated in a fresh process and compared field by field, i.e. the
  measurement is the reproducible one described here, not a one-off.

## What these reports do not prove

- **Not real-world OCR accuracy.** The pages are rendered by Pillow from synthetic labels:
  one font family, one layout grid, straight-on synthetic paper, no real scanner, no
  handwriting, no stamps or seals, no multi-page PDFs.
- **Not representative of AICTE certificates.** No real institution, person, certificate
  number or document is in the corpus, and none may be added (`ai/tests/test_evaluate.py`
  enforces the synthetic-only rule).
- **Not a compliance or authenticity signal.** Extracted text is advisory evidence for a
  human reviewer.
- **Not production performance.** `duration_seconds` measures a single process on one
  container, not throughput or latency under load.
- **Not a fair ranking of Tesseract vs. another engine.** They were not run on the same
  corpus under the same settings.
- **Statistically thin.** 24 cases per seed (8 per language, 3 per corruption). The three-seed
  report exists to show the spread — about ±0.02 CER — which is itself an estimate from three
  points, not a confidence interval.
