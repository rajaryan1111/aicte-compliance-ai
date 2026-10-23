## What this changes

<!-- One paragraph: what behaviour changes and why. Link the issue if there is one. -->

## Ownership

- Workstream: <!-- frontend | backend | ai-ocr | integration -->
- Owned paths touched: <!-- e.g. backend/app/main.py -->
- Shared surfaces touched (needs cross-workstream review): <!-- none | .github/… | docs/… | root config | API_CONTRACT.md -->
- Ownership check: <!-- paste the command and its result, e.g.
  `python tools/check_ownership.py --workstream backend --base origin/research/grounded-foundation`
  -> ownership OK, 3 changed path(s) -->
- Declared shared paths (if any) and who reviewed them: <!-- none | docs/development/API_CONTRACT.md (reviewed by B) -->

## Verification

- Exact head SHA verified: `<!-- full 40-char SHA -->`
- Local commands and observed results:
  - `python -m pytest -q` → <!-- e.g. 180 passed, 1 skipped -->
  - `ruff check backend/` → <!-- pass/fail -->
  - `python -m compileall -q backend/app backend/tests` → <!-- exit code -->
- Skipped tests and why: <!-- e.g. test_ocr_engine_integration.py — Tesseract not installed -->
- CI on the exact head SHA: <!-- run URL, or "no run scheduled for this head" -->

Do not paste a pass from another commit or another PR. A skipped test is not a pass.

## Contract and dependencies

- Targets contract version: `0.1.0-draft` <!-- update if API_CONTRACT.md changed -->
- `docs/development/API_CONTRACT.md` updated in this PR? <!-- yes/no, and why -->
- Depends on another PR? <!-- no | #N (reason) -->
- Adds an endpoint the contract marks **blocked**? <!-- no | justification (should be "no") -->

## Checklist

- [ ] Changes stay inside owned paths (see `WORKSTREAMS.md`)
- [ ] `python tools/check_ownership.py --workstream <yours> --base origin/research/grounded-foundation`
      exits 0, and every `--declare-shared` path was actually reviewed
- [ ] New behaviour has a test; fixed defect has a regression test
- [ ] No secrets, `.env`, real institutional/personal documents, caches or binaries added
- [ ] No AICTE rule activated; no regulatory requirement invented
- [ ] OCR described as advisory (no accuracy claim from synthetic data)
- [ ] No security control claimed that is not implemented and tested
- [ ] Opened as **draft** against `research/grounded-foundation`

## Notes for the next person

<!-- Anything the reviewer or the next contributor must know: follow-ups, decisions, risks. -->
