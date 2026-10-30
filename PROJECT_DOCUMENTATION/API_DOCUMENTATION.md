# API Documentation

Generated from the FastAPI OpenAPI schema of the working tree (2026-10-31, including the
unreleased remediation-plan routes): **48 paths / 55 operations**. Earlier `main` (`81d9667`) had
44 paths / 50 operations. Live deployments re-checked on 2026-10-31 differ and are called out
throughout.

| Deployment | Base URL | OpenAPI version | Operations | Notes |
|---|---|---|---|---|
| Repository working tree / local dev | `http://127.0.0.1:8000` (proxied by Vite) | `0.3.1` | **55** | Form-encoded token; public prototype runs; remediation plans + administrator reschedule |
| Render | `https://aicte-compliance-api-preview.onrender.com` | `0.3.1` | 29 | JSON token; enterprise core only |
| Live (used by the website) | `https://aicte-compliance-backend-live.vercel.app` | `0.4.0` | **11** | No auth; vault + analyze + guarded history |

Interactive docs exist at `/docs` and `/redoc` on any deployment that serves them. The
public frontend does **not** link to them.

---

## 1. Conventions

* **Content type**: `application/json` except document upload/analysis (`multipart/form-data`).
* **Auth**: `Authorization: Bearer <JWT>` (HS256, 60-minute expiry, `sub` = user id).
  Missing/invalid/expired/inactive → `401` with `WWW-Authenticate: Bearer`.
* **Tenant isolation**: every authenticated resource is scoped by institution membership.
  A foreign tenant returns **404** (not 403) by design, to prevent probing.
* **Role permission failure**: `403` with the missing permission name.
* **Validation error**: `422` with FastAPI's `detail[]` array of `{loc, msg, type}`.
* **Errors**: `{"detail": "<human readable>"}`.
* **CORS**: explicit origins plus regex `https://.*\.vercel\.app`, `allow_credentials=true`.
  CORS is a browser control, not authorization.
* **No rate limiting** and no API gateway in front of either live backend.
* **No versioning beyond `/api/v1`**; breaking changes would require a new prefix.

### Authentication flow

```http
POST /api/v1/auth/token
Content-Type: application/x-www-form-urlencoded

username=admin&password=********
```

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

The frontend stores this in `sessionStorage` (`AuthContext.tsx`), sends it on history calls,
and calls `GET /api/v1/auth/me` to hydrate the profile. No refresh token exists; after 60
minutes the user must sign in again.

**Deployment difference.** The repository and local dev accept an OAuth2 **form** body at
`/api/v1/auth/token`. The Render deployment accepts a **JSON** body
`{"username":"…","password":"…"}` instead; sending a form returns `422`
(`model_attributes_type`). The live Vercel backend has no token route (`404`). Any auth client
must account for all three behaviours.

---

## 2. Worked examples (real, observed)

### 2.1 `POST /api/v1/validate` — the public comparison

Request:

```json
{
  "institution_id": "SYNTH-INST-001",
  "application_type": "eoa",
  "required_documents": [
    "aicte_approval",
    "mandatory_disclosure",
    "land_use_certificate",
    "fire_safety_certificate",
    "building_occupancy_certificate"
  ],
  "submitted_documents": ["aicte_approval", "mandatory_disclosure", "land_use_certificate"],
  "expiry_dates": {
    "aicte_approval": "2024-03-31",
    "fire_safety_certificate": "2025-12-31"
  }
}
```

Response — **captured from the live backend on 2026-10-30** (abridged only in whitespace):

```json
{
  "institution_id": "SYNTH-INST-001",
  "application_type": "eoa",
  "status": "attention_required",
  "validation_scope": "caller_supplied_checklist_only",
  "missing_documents": ["building_occupancy_certificate", "fire_safety_certificate"],
  "expired_documents": ["aicte_approval"],
  "findings": [
    {
      "code": "MISSING_DOCUMENT",
      "document_type": "building_occupancy_certificate",
      "message": "Required document 'building_occupancy_certificate' was not submitted.",
      "evidence": { "source": "submitted_document_list", "observed": "not_submitted" }
    },
    {
      "code": "MISSING_DOCUMENT",
      "document_type": "fire_safety_certificate",
      "message": "Required document 'fire_safety_certificate' was not submitted.",
      "evidence": { "source": "submitted_document_list", "observed": "not_submitted" }
    },
    {
      "code": "DOCUMENT_EXPIRED",
      "document_type": "aicte_approval",
      "message": "Document expiry date 2024-03-31 is before the evaluation date 2026-10-30.",
      "evidence": {
        "source": "synthetic_demo_input",
        "expiry_date": "2024-03-31",
        "evaluation_date": "2026-10-30"
      }
    }
  ],
  "checked_at": "2026-10-30T18:07:29.970147+00:00",
  "source": "synthetic_demo_input",
  "notice": "Preliminary validation only. This endpoint evaluates only the checklist and dates supplied in the request; it does not load an authoritative AICTE ruleset. A passing result does not establish regulatory compliance or document authenticity. Expiry checks use supplied dates and require appropriate review."
}
```

Notes: `fire_safety_certificate` has an expiry date but was not submitted, so it produces only
a missing finding. `missing_documents` is sorted; findings list missing before expired.

### 2.2 `GET /health`

```json
{ "status": "ok", "service": "aicte-compliance-assistant" }
```

### 2.3 `GET /health/ready` (Render only)

```json
{
  "service": "aicte-compliance-assistant",
  "engine": "postgresql",
  "deployed_environment": true,
  "database_reachable": true,
  "migration_revision": "g7b8c9d0e1f2",
  "users_table_present": true,
  "status": "ready",
  "reasons": [],
  "notice": "Readiness probe — advisory deployment status only."
}
```

`status` is `degraded` if the DB is unreachable, the `users` table is missing, or a migration
has not run. This is the single most useful production diagnostic in the project.

### 2.4 `POST /api/v1/documents/analyze` (public, repo/Render)

```http
POST /api/v1/documents/analyze
Content-Type: multipart/form-data

file=@Fire_Safety_NOC_2024_2027.pdf
```

```json
{
  "filename": "Fire_Safety_NOC_2024_2027.pdf",
  "filesize_bytes": 184320,
  "sha256": "<64 hex chars>",
  "page_count": 2,
  "is_scanned_only": false,
  "extracted_text_preview": "DIRECTORATE OF FIRE AND EMERGENCY SERVICES ... Valid until 14/04/2027 ...",
  "candidate_fields": {
    "expiry_date": "2027-04-14",
    "issue_date": "2024-04-15",
    "certificate_number": "NOC/DFS/MUM/2024/8912",
    "issuing_authority": "Directorate of Fire and Emergency Services"
  },
  "warnings": [],
  "notice": "Advisory extraction only. Extracted fields must be verified by a human reviewer and do not establish document authenticity or AICTE compliance."
}
```

The values above are **illustrative** (no sample file is committed); the shape and field names
are exact for this repository. Errors: `400` (not a PDF / empty / corrupt / encrypted), `413`
(over 10 MiB), `422` (missing file part).

**The live deployment returns a different shape** (observed 2026-10-30, generated one-page
PDF, HTTP `200`):

```json
{
  "filename": "synthetic_fire_noc.pdf",
  "sha256": "c9f458bd…895be",
  "page_count": 1,
  "extracted_text": "[Page 1]\nFIRE SAFETY CERTIFICATE\nDirectorate of Fire and Emergency Services\nCertificate No: NOC/DFS/MUM/2024/8912\nDate of issue: 15/04/2024\nValid until 14/04/2027",
  "fields": {
    "certificate_number": {
      "value": "NOC/DFS/MUM/2024/8912",
      "confidence": null,
      "page_number": 1,
      "evidence_text": "Certificate No: NOC/DFS/MUM/2024/8912"
    }
  },
  "warnings": ["PDF contents are processed for this request only and are not stored by this endpoint."],
  "requires_human_review": true,
  "notice": "Advisory extraction only. … A qualified reviewer must compare every result with the original document."
}
```

`extracted_text`, `fields`, `requires_human_review` replace `extracted_text_preview`,
`candidate_fields`, `is_scanned_only`. Note that the expiry date present in the text was **not**
extracted in this live run.

### 2.5 Application + document upload (authenticated, repository only)

```http
POST /api/v1/applications
Authorization: Bearer <jwt>
Content-Type: application/json

{"institution_id": 1, "application_type": "eoa", "academic_year": "2026-2027"}
```

→ `201` `ApplicationRead` `{id, institution_id, application_type, academic_year, status,
created_at, updated_at}`.

```http
POST /api/v1/applications/1/documents
Authorization: Bearer <jwt>
Content-Type: multipart/form-data

file=@fire_noc.pdf
document_type=fire_safety_certificate
```

→ `201` document version descriptor including `document_version_id`, `scan_status`,
`processing_status`, `sha256`. Processing then proceeds through the outbox (or inline when
`CELERY_TASK_ALWAYS_EAGER=true`). Poll
`GET /api/v1/applications/1/documents/{doc_id}/versions/{version_id}/processing`.

---

## 3. Complete endpoint table

Legend for **Caller**: `—` = no frontend code calls it.

### 3.1 Prototype/public surface

| Method | Path | Purpose | Auth | Input | Response | Caller |
|---|---|---|---|---|---|---|
| GET | `/` | Service banner + notice | — | — | `{service,status,docs,health,frontend,notice}` | — |
| GET | `/health` | Liveness | — | — | `{status:"ok",service}` | `HealthIndicator` (every page) |
| GET | `/health/ready` | DB + migrations + users table | — | — | readiness object (§2.3) | — |
| POST | `/api/v1/validate` | Compare caller lists + expiry | — | `ValidationRequest` | `ValidationResponse` | `ValidatePage` |
| POST | `/api/v1/documents/analyze` | PDF metadata + candidate fields | — | multipart `file` | analysis object (§2.4) | `DocumentOcrVerifier` (wizard step 3) |
| GET | `/api/v1/institutions` | List institutions | — | — | institution list | — |
| POST | `/api/v1/seed` | Create demo user/institution | — (**403 in production**) | — | seed summary | — |
| POST | `/api/v1/validation-runs` | Save a run (in-memory) | — | `ValidationRequest` | `SavedValidationRun` | `history-storage.saveRunUnified` |
| GET | `/api/v1/validation-runs?limit&offset` | List saved runs | — | query | `{items,has_more}` | `HistoryPage` |
| GET | `/api/v1/validation-runs/{run_id}` | One saved run | — | path | `SavedValidationRun` | `HistoryPage` detail |
| DELETE | `/api/v1/validation-runs/{run_id}` | Delete saved run | — | path | `204` | `HistoryPage` |

> **Latent security finding in this repository.** In `main`, the four `validation-runs`
> endpoints are unauthenticated and operate on a single process-global `_SAVED_RUNS` list, so
> any caller can read or delete every run and lose everything on restart. This code is **not**
> what the live backend runs: there, all four return `401 "Sign in to access validation
> history."`, and on Render they are absent (`404`). Fix it before deploying `main`.
> The authenticated, Postgres-backed equivalent is
> `GET /api/v1/applications/{id}/validation-runs`.

### 3.1a Remediation plans (authenticated, institution-scoped)

Added 2026-10-31. The plan is derived in the browser from a preliminary `ValidationResponse`; these
routes persist it and record progress. They never evaluate compliance and never change a validation
outcome. Permissions: `plan:read` (all five roles) and `plan:write` (institution admin, scrutiny
officer, super admin; auditors and regulatory directors read only).

| Method | Path | Purpose | Auth | Input | Response | Caller |
|---|---|---|---|---|---|---|
| POST | `/api/v1/institutions/{institution_ref}/remediation-plans` | Create-or-get by deficiency signature | Bearer + `plan:write` | `RemediationPlanCreateRequest` | `201` on create, `200` on reopen, `RemediationPlanRead` | `lib/plan-sync.ts` `syncPlan` |
| GET | `/api/v1/institutions/{institution_ref}/remediation-plans?plan_key&limit` | List plans (optionally by key) | Bearer + `plan:read` | query | `{items,total}` | `fetchStoredPlan` |
| GET | `/api/v1/institutions/{institution_ref}/remediation-plans/{plan_id}` | Read one plan with tasks | Bearer + `plan:read` | path | `RemediationPlanRead` | `pushTaskUpdate` (reads the current version first) |
| PATCH | `/api/v1/institutions/{institution_ref}/remediation-plans/{plan_id}/tasks/{task_key}` | Update status and/or note | Bearer + `plan:write` | `{status?,note?,version}` | `RemediationTaskRead` | `pushTaskUpdate` |
| PATCH | `/api/v1/institutions/{institution_ref}/remediation-plans/{plan_id}/deadline-policy` | Reschedule open tasks from a new internal policy; appends deadline history | Bearer + `plan:policy` (institution admin / super admin) | `{policy:{p1_days,p2_days,p3_buffer_days,p3_max_days,expiring_window_days}}` | `RemediationPlanRead` (with `deadline_history`) | `lib/plan-sync.ts` `updateDeadlinePolicy` |

Behaviour that a client may rely on:

* **Idempotent create.** Re-posting the same `plan_key` returns the stored plan unchanged, so
  re-running a validation never resets progress. Task metadata is not patched on reopen.
* **Optimistic concurrency.** `version` is mandatory. A stale version returns **409** with
  `X-Current-Version`; an identical update is a no-op that does not bump the version.
* **Tenancy.** `institution_ref` in the path and body must match; a foreign or unknown institution
  is **404**, a missing permission is **403**.
* **Audit.** Creation and every status change write an `audit_events` row with actor and
  before/after values. Note text is never copied into the audit log (only its length).
* **Deadline policy.** `p1_days`/`p2_days`/`p3_buffer_days`/`p3_max_days`/`expiring_window_days`
  are stored with the plan and bounded to 1–365 days. The response `notice` states they are
  internal recommendations, not AICTE deadlines.

Example (synthetic):

```http
POST /api/v1/institutions/SYNTH-DEMO-001/remediation-plans
Authorization: Bearer <token>
Content-Type: application/json

{"institution_ref":"SYNTH-DEMO-001","plan_key":"plan-0123abcd","application_type":"eoa",
 "deadline_policy":{"p1_days":3,"p2_days":7,"p3_buffer_days":14,"p3_max_days":21,"expiring_window_days":60},
 "items":[{"task_key":"fire_safety_certificate::MISSING_DOCUMENT","document_id":"fire_safety_certificate",
   "document_label":"Fire Safety Certificate / NOC","finding_code":"MISSING_DOCUMENT","priority":"P1",
   "owner_role":"Estate & Fire Safety Officer","due_date":"2026-11-03",
   "evidence_required":"Valid fire NOC covering all blocks.","clause":"Clause 2.4"}]}
```

```json
{"id":1,"institution_ref":"SYNTH-DEMO-001","plan_key":"plan-0123abcd",
 "deadline_policy":{"p1_days":3,"p2_days":7,"p3_buffer_days":14,"p3_max_days":21,"expiring_window_days":60},
 "created_by":"officer7",
 "tasks":[{"task_key":"fire_safety_certificate::MISSING_DOCUMENT","status":"open","note":"","version":1,
   "due_date":"2026-11-03","status_changed_by":null}],
 "notice":"Stored institutional work plan derived from a preliminary validation result. It is not an AICTE determination, and its due dates are internal recommendations, not AICTE deadlines."}
```

### 3.2 Authentication

| Method | Path | Purpose | Auth | Input | Response | Caller |
|---|---|---|---|---|---|---|
| POST | `/api/v1/auth/token` | Issue JWT | — | form `username,password` | `{access_token,token_type}` | `SignInPage` / `AuthContext` |
| GET | `/api/v1/auth/me` | Current profile | Bearer | — | user + memberships | `AuthContext` hydration |

**Not present on the live backend** — sign-in therefore fails there with 404; on Render the
route exists but the documented demo credentials were rejected (401) during this audit.

### 3.3 Applications

| Method | Path | Purpose | Auth | Input | Response |
|---|---|---|---|---|---|
| POST | `/api/v1/applications` | Create application | Bearer + `application:create` | `{institution_id?, application_type, academic_year, status?}` | `ApplicationRead` |
| GET | `/api/v1/applications` | List in authorized scope | Bearer | `institution_id?`, paging | application list |
| GET | `/api/v1/applications/{application_id}` | Retrieve one | Bearer | path | `ApplicationRead` |
| PATCH | `/api/v1/applications/{application_id}` | Update status/year | Bearer + `application:update` | `{status?, academic_year?}` | `ApplicationRead` |

All callers: `—`. There is **no** separate submit/approve/reject/assign endpoint; status is
changed through `PATCH`, and decisions are recorded through review actions on findings.

### 3.4 Documents

| Method | Path | Purpose | Auth | Input | Response |
|---|---|---|---|---|---|
| POST | `/api/v1/applications/{id}/documents` | Upload to slot | Bearer + `application:update` | multipart `file`, `document_type` | version descriptor |
| GET | `/api/v1/applications/{id}/documents` | List slots | Bearer | — | document list |
| GET | `/api/v1/applications/{id}/documents/{document_id}` | Slot metadata | Bearer | — | document |
| GET | `/api/v1/applications/{id}/documents/{document_id}/versions` | Version history | Bearer | — | versions |
| GET | `…/versions/{version_id}/download` | Download bytes | Bearer + `application:read` | — | binary stream |
| GET | `…/versions/{version_id}/processing` | Job status | Bearer | — | `{scan_status,processing_status,attempts,warnings}` |

Callers: `—`. Downloads are served from private storage by opaque key; no public URL exists.

### 3.5 Validation and findings

| Method | Path | Purpose | Auth | Input | Response |
|---|---|---|---|---|---|
| POST | `/api/v1/applications/{id}/validate` | Run scrutiny | Bearer + `application:update` | `{checklist_type?, required_documents?}` | `ValidationRun` + checks + findings |
| GET | `/api/v1/applications/{id}/validation-runs` | Run history | Bearer | paging | runs |
| GET | `/api/v1/applications/{id}/validation-runs/{run_id}` | Consolidated report | Bearer | — | report |
| GET | `…/validation-runs/{run_id}/findings` | Findings | Bearer | — | findings |
| GET | `…/findings/{finding_id}` | Finding + review history | Bearer | — | finding detail |
| POST | `…/findings/{finding_id}/actions` | Record review action | Bearer + `review:read` at route, action-specific permission (`review:action` / `finding:waive`) in service | `{action, rationale}` | action record |
| GET | `/api/v1/applications/{id}/findings` | All findings + status | Bearer | — | findings |
| GET | `/api/v1/applications/{id}/review-summary` | Status counts | Bearer | — | summary |
| GET | `/api/v1/reviews/queue` | Reviewer queue | Bearer + review | paging | queue |

Callers: `—`. This is the capability the UI does not expose.

### 3.6 Audit packages

| Method | Path | Purpose | Auth | Input | Response |
|---|---|---|---|---|---|
| POST | `/api/v1/applications/{id}/audit-packages` | Seal an evidence package | Bearer | — | package + manifest |
| GET | `/api/v1/applications/{id}/audit-packages` | List packages | Bearer | — | packages |
| GET | `…/audit-packages/{package_id}` | Package detail | Bearer | — | manifest |
| GET | `…/audit-packages/{package_id}/download` | Download archive | Bearer | — | archive stream |
| POST | `/api/v1/audit-packages/verify` | Verify integrity | Bearer | manifest/archive | verification result |

Hash-chained manifests make tampering detectable after export. No UI.

### 3.7 Compliance, rules, verification, retention

| Method | Path | Purpose | Auth | Input | Response |
|---|---|---|---|---|---|
| GET | `/api/v1/compliance/rules` | Draft rules + approval state | Bearer | — | rules with `activation_blockers` |
| GET | `/api/v1/compliance/rules/history` | Approval records | Bearer | — | history |
| POST | `/api/v1/compliance/rules/{rule_id}/verify-source` | Record source verification | Bearer + `rules:verify` | `{document_sha256, rationale, verification_date}` | verification record |
| POST | `/api/v1/compliance/rules/{rule_id}/approve` | Approve a verified rule | Bearer + `rules:approve` | `{rationale, statutory_interpretation_approved}` | approval record |
| GET | `/api/v1/compliance/verification-adapters` | List adapters | — | — | adapter descriptors |
| PATCH | `/api/v1/compliance/applications/{id}/documents/{doc_id}/versions/{v_id}/fields/{field_name}` | Human field correction | Bearer + `application:update` | `{corrected_value, rationale}` | extracted field |
| POST | `/api/v1/compliance/applications/{id}/documents/{doc_id}/versions/{v_id}/verify` | Trigger authority verification | Bearer + `application:update` | adapter id | `verification_attempt` |
| GET | `/api/v1/compliance/applications/{id}/verifications` | Attempt history | Bearer | — | attempts |
| POST | `/api/v1/compliance/applications/{id}/infrastructure/review` | Infrastructure checks | Bearer | evidence payload | review result |
| GET | `/api/v1/compliance/applications/{id}/institutional-records` | Compare with records | Bearer | — | comparison |
| POST | `/api/v1/compliance/retention/purge` | Run retention pass | Bearer + `retention:manage` | `{dry_run}` | run summary |
| GET | `/api/v1/compliance/retention/runs` | Retention history | Bearer | — | runs |
| GET | `/api/v1/compliance/retention/status` | Scheduler/policy status | Bearer | — | status |

`verify-source` requires a 64-character lowercase SHA-256 of the authoritative document, a
verification date not before retrieval, and a ≥10-character rationale. `approve` requires
`rules:approve`, a verified source, and an approval timestamp not before verification. Both
write audit events. **No rule has been through this flow**, which is why the engine is empty.

---

## 4. What the live backend actually serves (11 operations)

```
GET  /health
POST /api/v1/validate               POST /api/v1/documents/analyze
GET  /api/v1/institutions           POST /api/v1/documents          (vault)
GET  /api/v1/documents             GET  /api/v1/documents/{id}/download
POST /api/v1/validation-runs       GET  /api/v1/validation-runs  (+ /{id})
```

Consequences for the website: validation and PDF analysis work; the vault and history routes
return **401** (`"Sign in to access validation history."`) and there is no token endpoint, so
`/history` and `/vault` are unreachable; the analyzer's response shape does not match this
repository's client.

---

## 5. Error reference

| Status | Typical cause | Body |
|---|---|---|
| 400 | Not a PDF, empty, corrupt, encrypted, >50 pages | `{"detail":"..."}` |
| 401 | Missing/expired token, inactive user, vault/history without auth (live backend wording differs) | `{"detail":"Authentication credentials were not provided."}` / `{"detail":"Sign in to access validation history."}` |
| 403 | Role lacks permission; demo endpoints disabled in production | `{"detail":"Forbidden: Insufficient permissions..."}` |
| 404 | Unknown id, or foreign-tenant resource (deliberate) | `{"detail":"Resource not found or access denied."}` |
| 409 | Invalid state transition | `{"detail":"..."}` |
| 413 | Upload over 10 MiB | `{"detail":"File exceeds the 10 MiB processing limit (… MiB)."}` |
| 422 | Schema violation (blank/duplicate names, bad date, bad enum) | FastAPI validation array |
| 500 | Unhandled defect | `{"detail":"Internal Server Error"}` |

---

## 6. Gaps a new developer should know

1. **No OpenAPI client generation** — the frontend's `lib/api.ts`/`lib/plan-sync.ts` are
   hand-written and cover a minority of the 54 operations, with response-shape guards.
2. **Two backends, two versions, different route sets** — never assume a route exists in
   production because it exists in the repo.
3. **The saved-runs API is both unauthenticated and non-durable** — do not build features on it.
4. **No pagination contract for findings/reviews** beyond limit/offset on some routes.
5. **No idempotency keys** on create/upload; retrying an upload creates a new version, which is
   actually desirable for documents but not for applications.
6. **No rate limits, quotas, or request-size limits at the edge** — only the 10 MiB application
   limit inside the app.
