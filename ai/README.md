# AI and document intelligence workstream

**Owner:** workstream C — **contributor not yet named** (see
[`../WORKSTREAMS.md`](../WORKSTREAMS.md)).
**Boundary:** this contributor works only in `ai/` during independent development.
**Status:** placeholder. No model, pipeline, dataset or evaluation result exists here. The
working OCR implementation is still in `backend/` (see the OCR placement rule).

## Scope

- OCR engine adapters and document pre-processing.
- Institutional-field extraction, conservative normalization and provenance/evidence.
- Confidence signals, unresolved-field handling and human-review support.
- Synthetic labelled fixtures, regression tests and a held-out evaluation methodology.
- Optional model/AI components only where a deterministic baseline and its limitations are
  documented.

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

## First task

[`../docs/development/STARTER_TASKS.md`](../docs/development/STARTER_TASKS.md) — task C1.
