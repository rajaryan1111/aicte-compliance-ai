# Frontend workstream

**Owner:** workstream A — **contributor not yet named** (see
[`../WORKSTREAMS.md`](../WORKSTREAMS.md)).
**Boundary:** this contributor works only in `frontend/` during independent development.
**Status:** placeholder. No framework, build tooling or application has been selected or
added. This directory contains documentation only.

## Scope

- Applicant and reviewer interface, navigation, forms and document/status views.
- A clear distinction between preliminary automated checks, OCR observations and
  human-approved decisions. The UI must never imply that an automated result is an
  approval.
- Evidence display, validation feedback, accessibility and responsive layout.
- Frontend unit/component tests and synthetic mock data.

## Rules

- Do not edit `backend/`, `ai/`, root configuration, `docs/` or `.github/` as part of
  independent work. Propose shared changes in a separate PR.
- Use mocked API responses until the backend owner publishes an agreed contract. The
  contract is [`../docs/development/API_CONTRACT.md`](../docs/development/API_CONTRACT.md);
  endpoints it marks **blocked** must not be mocked as if they exist.
- Never treat client-side checks as authorization or compliance decisions. The server is
  the only authority.
- Do not include real institutional documents or personal data in fixtures.
- Shared API changes go through a contract change and a separate integration PR.

## First task

[`../docs/development/STARTER_TASKS.md`](../docs/development/STARTER_TASKS.md) — task A1.
