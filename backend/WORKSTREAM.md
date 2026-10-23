# Backend workstream

**Owner:** workstream B — **contributor not yet named** (see
[`../WORKSTREAMS.md`](../WORKSTREAMS.md)).
**Boundary:** this contributor owns the existing `backend/` directory, including the
current OCR implementation until an approved migration says otherwise.

## Scope

- FastAPI endpoints, request/response schemas and server-side validation.
- Authentication/RBAC, institution-level tenant isolation and authorization checks.
- Persistence, audit events, retention/deletion controls and safe error handling.
- Integration contracts for the frontend and AI workstreams
  ([`../docs/development/API_CONTRACT.md`](../docs/development/API_CONTRACT.md)).
- Backend unit, integration and security tests.

## Rules

- Do not edit `frontend/` or `ai/` during independent work.
- Keep shared root files, `docs/`, `.github/` and dependency manifests unchanged until an
  integration PR is agreed.
- Never trust client-supplied roles or institution identifiers.
- Do not expose a public document-upload endpoint until the security controls in
  [`../docs/development/INTEGRATION_CHECKLIST.md`](../docs/development/INTEGRATION_CHECKLIST.md)
  are implemented and tested.
- Do not activate a regulatory rule because the API accepts it; the ingestion gate checks
  provenance mechanically, and a human must still approve.
- Clearly distinguish implemented controls from proposals in code, tests and docs.

## Current state

The FastAPI prototype lives here: `app/main.py` (`/health`, `/api/v1/validate`),
`app/ocr_*.py`, `app/rule_catalog.py`. `app.rule_catalog` implements an activation gate but
**no rule is defined or active**, and there is no evaluator. Authentication, persistence,
tenant isolation, storage, audit and retention do **not** exist. This file records
ownership; it does not claim those controls exist.

## First task

[`../docs/development/STARTER_TASKS.md`](../docs/development/STARTER_TASKS.md) — task B1.
