# Part 3 — Platform API, security and integration readiness

**Owner:** Contributor 3 (assign a person before implementation)
**Owned folder:** `workstreams/part-3-platform/`
**Do not edit:** Part 1 or Part 2 folders, root/shared files, existing `backend/` code, workflows or dependency manifests during isolated work.

## Mission
Specify and prototype the platform boundary around the rules and OCR work: API contracts, authentication/authorization, tenant isolation, safe persistence, auditability and operational controls.

## Deliverables in this folder
- API contract and threat model for applicant, reviewer and rule-manager actions.
- Authentication/RBAC and institution-level tenant-isolation design.
- Upload/storage boundary design: private storage, malware scanning, file lifecycle, retention/deletion and size limits.
- Audit event model for access, upload, extraction, review, rule activation and export.
- API error model, rate limiting, logging/privacy rules, and integration checklist.
- Security-focused tests or executable isolated prototypes that do not depend on Parts 1/2 internals.

## Acceptance criteria
- No public upload endpoint without authentication, authorization, tenant isolation, private storage, malware scanning, audit persistence and retention/deletion controls.
- Server-side authorization; never trust client-supplied institution IDs or roles.
- Sensitive documents and OCR text are not written to ordinary logs.
- Fail closed on unauthorized access, missing tenant context and unavailable required controls.
- Clearly distinguish implemented controls from proposals; do not imply a database, auth system or deployment exists unless verified.

## Interface boundary
Keep work in this folder. Define API contracts and mocks without importing private Part 1/2 implementation. Shared root files, backend integration, workflows and dependency manifests require a separate integration PR after interface review.
