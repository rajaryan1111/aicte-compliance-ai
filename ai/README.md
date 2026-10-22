# AI and document intelligence workstream

**Owner:** Contributor 3 (assign a name before implementation).  
**Ownership boundary:** This contributor works only in `ai/` during independent development.

## Scope
- OCR engine adapters and document preprocessing.
- Institutional-field extraction, conservative normalization and provenance/evidence.
- Confidence signals, unresolved-field handling and human-review support.
- Synthetic labelled fixtures, regression tests and held-out evaluation methodology.
- Optional model/AI components only where a deterministic baseline and limitations are documented.

## Rules
- Do not edit `frontend/` or `backend/` during independent work.
- Do not move or change the current `backend/app/ocr_pipeline.py` as part of the folder setup. Any later migration or integration requires a separate PR and interface review.
- Use synthetic documents only; do not commit real institutional personal data.
- Reject malformed, unsupported, oversized and excessive-pixel inputs before expensive processing.
- Do not guess ambiguous dates or missing values. Keep uncertain output unresolved.
- OCR results are advisory evidence, not proof of authenticity or compliance.
- Synthetic CI success is not a claim of real-world OCR accuracy.

## Current status
This README establishes the AI workstream boundary. The current OCR implementation remains in `backend/` until a separately reviewed integration plan authorizes a move or adapter.
