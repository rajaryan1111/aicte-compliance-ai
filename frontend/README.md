# Frontend workstream

**Owner:** workstream A — **contributor not yet named** (see
[`../WORKSTREAMS.md`](../WORKSTREAMS.md)).
**Boundary:** this contributor works only in `frontend/` during independent development.
**Status:** application implemented (2026-10-24). React 18 + TypeScript + Vite, talking to
the real backend API. `npm run build` produces a working production bundle.

> **Provenance.** Until this session this directory held documentation and fixtures only.
> The application was written during the SIH integration pass because no frontend existed on
> any of the 13 remote branches (verified by scanning every branch for `package.json` and any
> `.ts`/`.tsx`/`.js`/`.jsx` file: zero hits). The fixtures below were **not** used as a source
> of truth; all types in `src/types.ts` are transcribed from the live `/openapi.json`.

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


## Running the application

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to the backend on :8000
npm run build    # type-check (tsc -b) + production bundle in dist/
```

Configuration is via `VITE_BACKEND_ORIGIN` (dev proxy target, default
`http://127.0.0.1:8000`) and optional `VITE_API_BASE_URL`. Leave the latter empty in dev so
requests stay same-origin and go through the proxy — the browser never calls the backend
host directly.

A full local run (database, migrations, required secrets, demo user, scanner) is documented in
[`../tools/demo/README.md`](../tools/demo/README.md).

## Screens

1. **Sign in** — JWT against `POST /api/v1/auth/token`. No self-registration; an operator
   provisions the demo account.
2. **Workspace** — application list (`GET /api/v1/applications`) and creation
   (`POST /api/v1/applications`).
3. **Application panel** — document upload (`POST …/documents`, multipart), live
   scan/processing badges with polling (`GET …/versions/{id}/processing`), extracted-field
   counts, and pre-scrutiny (`POST …/validate`) rendering every check, finding, limitation and
   the backend disclaimer, plus the human-review summary.

## Honesty rules encoded in the UI

- Every result surface states that the output is advisory and **not** an approval.
- Machine-produced findings are labelled as such and shown separately from human review
  counts; a finding's `open` state is never presented as a decision.
- `not_run` regulatory checks are rendered as a limitation, not hidden. Regulatory rules are
  inactive by design while Phase 0 gates remain open.
- `SCANNER_UNAVAILABLE` is explained in the UI as correct fail-closed security behaviour, so
  quarantine is never mistaken for a UI bug.
- No mock or hardcoded success path exists. There is no demo mode that fakes API responses.

## Known gaps

- No component/unit test runner is configured yet (build + type-check only).
- No review-action UI (acknowledge/resolve) — the API supports it but the demo does not need it.
- No document preview/download in the UI.

## First task

[`../docs/development/STARTER_TASKS.md`](../docs/development/STARTER_TASKS.md) — task A1.
