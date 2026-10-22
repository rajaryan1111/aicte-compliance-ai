# Part 2 — Document intake and OCR

**Owner:** Contributor 2 (assign a person before implementation)
**Owned folder:** `workstreams/part-2-ocr/`
**Do not edit:** Part 1 or Part 3 folders, root/shared files, existing `backend/` code, workflows or dependency manifests during isolated work.

## Mission
Develop a bounded, testable OCR pipeline that extracts institutional document fields as evidence for human review—not as proof of authenticity or regulatory compliance.

## Deliverables in this folder
- Document intake and image-validation design; allowed formats, byte/pixel limits and malformed-file handling.
- OCR adapter contract independent of any optional engine.
- Field extraction/normalization with conservative parsing; ambiguous values stay unresolved.
- Synthetic labelled fixtures, regression tests, and a reproducible benchmark plan for held-out documents.
- Field-level confidence/evidence representation and known limitations.

## Acceptance criteria
- Enforce file size, image dimensions/pixel limits, supported formats and extracted-text limits before expensive processing.
- Reject corrupt, malformed, oversized and unexpected inputs safely.
- Strict date parsing; never guess ambiguous day/month order. Reject invalid/reversed academic years.
- Keep duplicate-field behaviour deterministic and tested.
- No real personal records in fixtures; do not extract personal identity fields unless separately justified and approved.
- OCR output is advisory, with evidence and human review. Synthetic CI success is not a real-world accuracy claim.

## Interface boundary
Keep all work in this folder and publish proposed input/output contracts here first. Do not modify existing `backend/app/ocr_pipeline.py` or shared workflow files while working independently. A separate integration PR is required.
