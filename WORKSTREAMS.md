# Three-person technical work split

**Status:** Proposed work allocation; implementation must stay in isolated workstream folders until integration review.
**Baseline:** `research/grounded-foundation` (PR #1 is still open and unmerged).
**Goal:** Three contributors can work in parallel without editing each other's deliverables.

## Folder ownership

| Workstream | Folder | Primary responsibility |
|---|---|---|
| Part 1 | [`workstreams/part-1-rules/`](workstreams/part-1-rules/README.md) | Regulatory-source provenance, rule lifecycle, rule validation and tests |
| Part 2 | [`workstreams/part-2-ocr/`](workstreams/part-2-ocr/README.md) | Document intake design, OCR extraction, normalization, evidence and OCR tests |
| Part 3 | [`workstreams/part-3-platform/`](workstreams/part-3-platform/README.md) | API contracts, access control, tenant isolation, audit, storage/retention and integration readiness |

## Non-overlap contract

1. Each contributor edits only their assigned `workstreams/part-N-*/` folder while working independently.
2. Do not edit another workstream's folder, even for a small fix. Open an issue or request the owner to change it.
3. Do not edit shared root files, `.github/workflows/`, dependency manifests, or existing `backend/` code during isolated work. Such changes must be proposed separately as integration changes and reviewed by all three owners.
4. Keep each workstream's code, tests, decisions, and acceptance evidence in its own folder. Do not import another workstream's private implementation. Agree on documented interfaces first.
5. Use separate feature branches and pull requests. Do not commit directly to `main`, do not merge your own PR, and do not claim CI passed unless the exact head SHA has a successful run.
6. Never use real institutional personal data or unverified regulatory claims in fixtures. Use synthetic examples. OCR findings remain advisory and human-reviewed.
7. No production/public upload, rule activation, deployment, or release until required security, source-verification, testing and human-approval gates are satisfied.

## Integration protocol

- Each part first publishes its interface/schema and acceptance tests inside its folder.
- Integration happens only after all three owners review the interface contract.
- A designated integrator prepares a separate integration PR; it must not silently rewrite a workstream's implementation.
- Resolve changes through owner-to-owner review, not by editing another person's folder.
- Record dependencies and decisions in the relevant workstream README. If workstream boundaries need to change, agree before changing files.

## Suggested sequence

1. All three owners inspect this contract and their own README.
2. Work independently in isolated folders.
3. Each PR includes tests, limitations, and exact verification evidence.
4. Review interfaces together; only then prepare a separate integration PR.

This split creates ownership boundaries; it does not mean the existing prototype is production-ready or that regulatory rules have been verified.
