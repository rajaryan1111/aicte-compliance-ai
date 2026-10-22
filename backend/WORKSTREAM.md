# Backend workstream

**Owner:** Contributor 2 (assign a name before implementation).  
**Ownership boundary:** This contributor owns the existing `backend/` directory.

## Scope
- FastAPI endpoints, request/response schemas and server-side validation.
- Authentication/RBAC, institution-level tenant isolation and authorization checks.
- Persistence, audit events, retention/deletion controls and safe error handling.
- Integration contracts for the frontend and AI workstreams.
- Backend unit, integration and security tests.

## Rules
- Do not edit `frontend/` or `ai/` during independent work.
- Keep shared root files, `docs/`, `.github/` and dependency manifests unchanged until an integration PR is agreed.
- Never trust client-supplied roles or institution identifiers.
- Do not expose a public document-upload endpoint until required security controls are implemented and tested.
- Do not activate regulatory rules merely because the API accepts them; require the rule-governance approval gate.
- Clearly distinguish implemented controls from proposals.

## Current status
The existing FastAPI prototype lives here. This file records ownership; it does not claim that authentication, persistence, tenant isolation or production controls already exist.
