# Cross-Repository Review — AICTE Compliance Assistant and Fake ID Screening

Date: 2026-10-23

## Repositories and refs inspected

- Target: https://github.com/rajaryan1111/aicte-compliance-ai
  - Base: `main` at `968ddcf7a4fb1cd1e1d8d4bb73e0b7fc10b44bcf`
  - Review target: `research/grounded-foundation` at `91573743d8056bfa426888ae2eddddac3a56a537`
  - PR #1 remains open, draft, and unmerged.
- Reference: https://github.com/rajaryan1111/fake-id-screening
  - Inspected branch: `main` at `2fc89caee3c7f0ba42f1a7d6a810c980ce7579e7`
  - Source CI for that commit reports success: https://github.com/rajaryan1111/fake-id-screening/actions/runs/35765577728
  - Target CI on reviewed branch head reports success: https://github.com/rajaryan1111/aicte-compliance-ai/actions/runs/39864290259

## Summary verdict

No source code, datasets, model artifacts, biometric code, mobile assets or personal identity records were copied from fake-id-screening. The target OCR pipeline is a deliberately smaller, application-owned implementation of the relevant concepts. The source repository does not contain a root `LICENSE` file at the inspected `main` ref, so wholesale code reuse is not treated as cleared merely because the repository is public.

The target does not need a second OCR engine added immediately. The useful next improvements are a wider safe institutional-field vocabulary, stricter academic-year validation, more regression tests for OCR ambiguity/limits, and explicit provenance for future additions. These are suitable to implement independently without importing the source project.

## What was compared

### Reference repository capabilities observed

- PaddleOCR wrapper with lazy singleton engine initialization and multiple passes over preprocessed/original/ROI images.
- OpenCV/Pillow preprocessing: grayscale, CLAHE contrast enhancement, denoising, deskewing, resizing, and a bottom-region crop.
- Regex/keyword/spatial field extraction with per-field confidence and bounding boxes.
- Date/text normalizers accepting several formats.
- Dual-sided identity-document processing and a mobile app with camera capture flow.
- CI for backend, frontend and mobile typecheck. The latest inspected run succeeded.

### Target repository already contains

- Engine-neutral OCR contract and optional Tesseract adapter.
- Safe image input validation (10 MiB byte cap, supported formats, maximum pixel count, Pillow verify).
- Basic grayscale/autocontrast and bounded upscaling.
- Institutional context-labelled fields, selected Hindi labels, page/evidence metadata, source SHA-256, engine/version, human-review warning.
- Conservative ISO-only date parsing; ambiguous date formats remain unresolved.
- Local-only CLI, synthetic fixture corpus, unit tests and a separate Tesseract integration smoke test.
- No public OCR upload API, no OCR compliance verdict, no personal-name/DOB/student-ID extraction.

## Findings and recommendations

| Area | Verdict | Action |
|---|---|---|
| OCR engine | Target Tesseract path is lighter and optional; source PaddleOCR is heavier and currently aimed at identity cards | Do not add PaddleOCR or a second engine without a measured benefit, dependency/licensing review and representative benchmark |
| Preprocessing | Source provides denoise/deskew/CLAHE and ROI ideas; target currently has grayscale, autocontrast and upscale | Consider a separately benchmarked optional preprocessing strategy later; do not copy source code |
| Field schema | Target has institution name, certificate number, application reference, issue/expiry dates, academic year | Extend only when official form/document requirements establish needed fields |
| Dates | Source normalizer supports many formats, but some ambiguous numeric dates can be interpreted as day/month | Keep target's strict ISO-only policy unless locale/source format is authoritative; add regression tests |
| Confidence | OCR confidence is not calibrated field correctness probability | Present as an engine score plus review cue, never as authenticity probability |
| Bounding boxes | Useful for a reviewer to locate evidence; target currently stores source line evidence, not coordinates | Future UX improvement after the output contract and page/geometry semantics are designed |
| Dual-sided images | Reference merges front/back identity cards using identity-specific field priorities | Not suitable for institutional accreditation evidence without an explicit multi-page/source merge contract |
| Face verification | Out of scope for institutional compliance and creates biometric privacy risk | Do not integrate |
| Mobile UI | Source camera workflow belongs to its product's use case | Do not import into current backend-only prototype absent an approved UI scope |
| Security | Target avoids public upload while auth, tenant isolation, private storage, malware scanning, persistent audit and deletion controls are missing | Preserve this gate; don't expose file uploads yet |
| Provenance | Source has no root LICENSE at reviewed ref; model/data/asset licenses remain unverified | No wholesale copy; confirm authorship, third-party notices and provenance first |

## Regressions and gaps to close next

1. Add adversarial/edge-case tests: academic-year range validity, malformed/duplicate labels, very long OCR text, extreme aspect ratios, image decoder failures and inconsistent engine metadata.
2. Add an explicit parse result/status for field values (accepted / unresolved / absent) if the API contract is expanded. Do not represent unknown as a guessed value.
3. Add line/bounding-box geometry only with deterministic tests and source-coordinate definitions.
4. Build a labelled, held-out synthetic English/Hindi corpus and report precision/recall by field before claiming OCR accuracy. The existing 8-case fixture set is a regression corpus, not an accuracy benchmark.
5. Complete official AICTE applicability/source reconciliation before activating any regulatory rule.
6. Keep production deployment blocked until auth/RBAC, tenant isolation, secure private storage, malware scanning, audit persistence and retention/deletion are designed and tested.

## Validation status

- Target latest inspected Actions run for head `91573743d8056bfa426888ae2eddddac3a56a537`: completed successfully.
- Previous code-inclusive verified run #56 recorded 54 passed, 1 skipped in the base backend job and 1 passed in the optional Tesseract smoke-test job.
- Reference repo's latest inspected CI run completed successfully. This demonstrates its configured checks passed, not OCR accuracy or production readiness.

## Safety and scope

- This review is source-level against the refs stated above; no local runtime execution or new OCR accuracy experiment was performed in this review.
- No code was copied from fake-id-screening.
- PR #1 remains open and draft. `main` was not modified or merged, and no deployment was performed.

## Follow-up review — 2026-10-23

This section records a subsequent read-only review of the proposed foundation and stacked OCR hardening changes. It does not supersede the refs and evidence above.

### Pull-request dependency reconciliation

- PR #1 (`research/grounded-foundation`) is the foundation change set.
- Comparing `research/grounded-foundation` to `review/cross-repo-integration-audit` returned exactly one additional commit and one changed file: this audit document.
- Therefore PR #2 should target `research/grounded-foundation`, not `main`, so its review diff shows only this document rather than repeating the entire foundation. Retargeting is a review-structure change only; it does not merge either PR.
- PR #3 (`feature/ocr-regression-hardening`) is stacked on the foundation branch. Its current changes cover OCR output limits, academic-year validation, duplicate-field behavior, regression tests and workflow branch triggers. Recheck its base and rerun CI after the foundation's disposition is known.

### Follow-up OCR review

The inspected OCR implementation enforces a 10 MiB upload cap, a 30-million-pixel cap, supported image formats, image verification and a 100,000-character OCR output cap. The extractor rejects non-string text, leaves ambiguous non-ISO dates unresolved, skips equal/reversed academic years and keeps the first matching field. The OCR result remains advisory and requires human review.

The regression test suite and optional Tesseract smoke test passed on the inspected PR #3 head `184d678790f3c7442cb158d36a2f909a22188af2` in workflow run https://github.com/rajaryan1111/aicte-compliance-ai/actions/runs/39865712934. This validates configured synthetic tests only; it is not evidence of real-world field accuracy or production readiness.

### Rule catalogue activation gap

The rule schema currently checks that an `ACTIVE` rule has an effective-from date and positive, negative, boundary and exception test categories. It does not, by itself, require recorded reviewer identity, an approval decision or a verified source-status field before activation.

This is a design gap to close before implementing a rule-publication workflow, not evidence that an unverified official AICTE rule is currently active. Before any production rule can become executable, require:
1. explicit source verification status and provenance (issuer, exact document/version, clause/page, retrieval date and effective interval);
2. a recorded reviewer identity and approval decision;
3. tests covering applicability, boundaries, exceptions and unresolved inputs;
4. a server-enforced transition gate so draft/unresolved rules cannot execute; and
5. an audit event for activation, supersession and retirement.

The catalogue is currently metadata/schema groundwork; do not describe it as a deployed regulatory rules engine.

### Current blockers remain

- Verify the official SIH26261 problem statement, stage and deadline against the official source. Do not mix in SIH26118, which is a separate project identifier and is not established as relevant to this AICTE compliance project.
- Verify the authoritative AICTE documents and amendments applicable to the target academic year before encoding or activating regulatory requirements.
- Complete license/authorship/provenance checks before copying code, datasets or assets from the reference repository.
- Keep public document upload blocked until authentication, authorization/RBAC, tenant isolation, private storage, malware scanning, audit persistence and retention/deletion controls are implemented and tested.
- Do not claim real-world OCR accuracy from a synthetic regression corpus; establish a labelled, held-out evaluation and report per-field precision/recall first.

### Scope of this follow-up

This was a GitHub source/patch review; no local execution or new OCR benchmark was performed. No application code was changed by this follow-up review. The document update is intended to preserve review findings and clarify the PR dependency structure.
