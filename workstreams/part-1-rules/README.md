# Part 1 — Regulatory sources and rule governance

**Owner:** Contributor 1 (assign a person before implementation)
**Owned folder:** `workstreams/part-1-rules/`
**Do not edit:** Part 2 or Part 3 folders, root/shared files, existing `backend/` code, workflows or dependency manifests during isolated work.

## Mission
Build the source-governed regulatory rule domain: traceable sources, rule versions, applicability, review decisions and safe lifecycle transitions. This is not permission to encode unverified regulations.

## Deliverables in this folder
- Source/provenance record schema: issuer, exact document/version, official URL, clause/page, publication/retrieval dates, effective interval, applicability and verification status.
- Rule draft/version schema and deterministic validation.
- Explicit reviewer identity, approval decision and audit event design.
- Tests for missing/unverified source, incomplete provenance, invalid effective dates, applicability gaps, boundary cases, exceptions, and blocked activation.
- A short decision log and a list of unresolved official-source questions.

## Acceptance criteria
- An unverified or unresolved rule cannot reach an executable/active state.
- Activation requires verified source provenance, named reviewer, explicit approval, effective interval and required test evidence.
- Superseding/retiring a rule preserves history and produces an auditable event.
- No fabricated AICTE requirements; unknowns remain blocked and labelled.
- All tests and limitations are documented. No claim of regulatory correctness without authoritative evidence.

## Interface boundary
Publish proposed request/response schemas and examples here first. Do not import Part 2 or Part 3 implementation. Integration into the existing backend requires a separate reviewed integration PR.
