# Security and Privacy

Scope: `backend/app/core/*`, `api/deps.py`, `api/v1/*`, `core/upload_validator.py`, `worker/*`,
`services/verification_adapter.py`, frontend `AuthContext.tsx`, `lib/api.ts`, plus what the live
deployments actually expose. Nothing here is a certification; every claim points to code or an
observed response.

---

## 1. Authentication

| Property | Implementation |
|---|---|
| Scheme | JWT, HS256 (`JWT_ALGORITHM` fixed, no `none`, no RS256) |
| Secret | `JWT_SECRET_KEY`, **minimum 32 characters enforced at runtime** — shorter/absent raises `RuntimeError` instead of signing |
| Expiry | 60 minutes (`DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES`) |
| Claims | `sub`, `iat`, `exp`; decode requires all three |
| Password hashing | bcrypt via `bcrypt.hashpw` / `checkpw`, per-password salt |
| User lookup | On every request, re-read from DB and reject `is_active = false` |
| Refresh | **None** — re-login after expiry |
| Revocation | Effectively "deactivate the user"; changing a password does not invalidate issued JWTs |
| Storage | `sessionStorage` (cleared when the tab closes) |

**Where it fails today.** The live backend has no `/api/v1/auth/token` (`404`), so the deployed
site cannot authenticate at all. On Render the route exists and expects a **JSON** body; the
documented demo credentials return `401` and `/api/v1/seed` is `404`, so no account can be
created there through the API. In this repository the route uses a **form** body and the seed
endpoint exists but is disabled when `ENVIRONMENT=production`.

---

## 2. Authorization (RBAC)

5 roles, 12 permissions, central map in `core/rbac.py`:

| Permission | institution_admin | scrutiny_officer | regulatory_director | auditor | super_admin |
|---|:--:|:--:|:--:|:--:|:--:|
| `application:create` | ✅ | | | | ✅ |
| `application:read` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `application:update` | ✅ | ✅ | | | ✅ |
| `review:read` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `review:action` | | ✅ | ✅ | | ✅ |
| `finding:waive` | | | | | ✅ |
| `audit_package:create` | ✅ | ✅ | | | ✅ |
| `audit_package:read` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `rule:read` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `rule:verify` | | | ✅ | | ✅ |
| `rule:approve` | | | ✅ | | ✅ |
| `retention:manage` | | ✅ | ✅ | | ✅ |

Enforcement points:

* Route-level via `verify_institution_membership(..., required_permission=...)`.
* Service-level for review actions (`ReviewService` re-checks `review:action` / `finding:waive`),
  rule verification/approval, and retention.
* **Tenant isolation**: membership lookup by `(user_id, institution_id)`; non-members receive
  **404**, deliberately indistinguishable from "not found".

**Design weakness.** The frontend infers role from the username substring (`"scrutiny"` →
`scrutiny_officer`) for UI affordances. The server never trusts that; it reads the membership
row. This is acceptable, but it means the UI can show controls the server will reject.

---

## 3. Transport, headers, CORS

| Item | Status |
|---|---|
| HTTPS | Enforced by Vercel and Render |
| HSTS | Not configured in this repository (may be platform default) |
| CSP | **None** — no `Content-Security-Policy` header in `render.yaml`/`vercel.json` |
| `X-Frame-Options` / `frame-ancestors` | None in repo |
| `X-Content-Type-Options` | None configured in app |
| Referrer-Policy | Not set |
| CORS | Explicit list **plus regex `https://.*\.vercel\.app`**, `allow_credentials=true`, methods `*`, headers `*` |

**CORS implications.** Any `*.vercel.app` deployment is allowed, including an attacker's. Because
authentication is a Bearer header (not a cookie), an attacker's page cannot read a victim's
token from another origin, so the practical risk is limited to unauthenticated endpoints —
which are already fully public. Still, this is broader than necessary; replace the regex with
the exact production origin(s).

**CSRF.** Not applicable to the token-based API (no cookie auth). If auth ever moves to
cookies, CSRF protection must be added first.

---

## 4. Input and upload hardening

| Control | Implemented |
|---|---|
| Size cap | 10 MiB, checked client-side and server-side, stream read bounded |
| Magic-byte detection | PDF (`%PDF-`), PNG, JPEG — extension alone is not trusted |
| PDF page cap | 50 |
| Image decompression bomb | 30 MP cap |
| Encrypted PDF | rejected |
| Malformed/empty | rejected with 400 |
| Filename | sanitised; never used as a storage path |
| Storage key | opaque `docs/xx/<uuid>` |
| Zip/archive upload | not supported at all |
| Magic bytes vs MIME | both checked |

**Not implemented:** content disarm and reconstruction (CDR), per-tenant quota, virus-total-style
multi-engine scanning, and file-type allow-listing by document type (a JPEG can be uploaded to a
slot labelled "fire NOC").

---

## 5. Malware scanning and quarantine

* `ClamAVScanner` speaks the clamd `INSTREAM` protocol over TCP when `CLAMAV_HOST` is set.
* `QuarantineScanner` is the default when ClamAV is absent: it **never returns clean**, marking
  files `scan_unavailable`. A quarantined file is never parsed and never served.
* `MockCleanScanner` exists only behind `ALLOW_DEV_MOCK_SCANNER=true` and must never be enabled
  in production.
* Rejected files are quarantined permanently; validation reports them as
  `MALWARE_SCAN_REJECTED` and refuses to evaluate their content.

This is genuinely fail-closed. It also means that without ClamAV, uploaded documents are never
processed — a deliberate availability/security trade-off that should be stated in an operations
runbook.

---

## 6. Document privacy

| Property | Behaviour |
|---|---|
| Public URL for uploads | **None** — downloads require a Bearer token + `application:read` + tenant membership |
| Storage | Local filesystem under `STORAGE_LOCAL_DIR`, outside the web root |
| DB | Metadata and hashes only; bytes are not stored in Postgres |
| Hash | SHA-256 per version, used for duplicate and cross-institution reuse detection |
| Processing | Reed-solids into memory for scan/extract; no third-party upload |
| Third-party processors | **None** for documents — no S3, no OCR SaaS, no LLM API |
| Ephemeral disk risk | Render free plan loses files on redeploy while metadata remains → 404 downloads |
| Backup | Not configured by the project |

**Cross-institution hash matching** intentionally compares hashes across institutions to detect
document reuse. This is a privacy-sensitive feature: it reveals to one institution that *some*
other institution uploaded an identical file (it exposes the other institution's identifier in
the finding). This must be documented in any privacy notice and may need legal review before
production.

---

## 7. The "saved runs" endpoints (latent defect in `main`)

In this repository, `/api/v1/validation-runs` is unauthenticated and backed by a
module-global list:

```python
_SAVED_RUNS: list[SavedValidationRun] = []
```

If `main` were deployed as-is, `GET /api/v1/validation-runs` would return **every run created
by anyone** (including `institution_id` and the full request/result), and
`DELETE /api/v1/validation-runs/{id}` would let anyone delete anyone's run. Data also vanishes
on restart, so it is not an audit trail.

**Not currently exploitable in production.** Verified 2026-10-30: the live backend returns
`401 "Sign in to access validation history."` for list/get/create/delete, and Render returns
`404` (route absent). This is therefore a defect to fix **before** the next deployment, not an
active incident. The authenticated, Postgres-backed equivalent is
`/api/v1/applications/{id}/validation-runs`.

Mitigation used by the UI: it calls these routes with a token when one exists and otherwise
falls back to `localStorage`. That does not protect the endpoints themselves.

---

## 7a. Remediation plan data (added 2026-10-31)

Remediation plans are institutional work records derived from a preliminary validation result.

| Question | Answer |
|---|---|
| Where is it stored? | Postgres tables `remediation_plans` and `remediation_tasks`, scoped by `institution_id`; browser `localStorage` only as an offline fallback |
| Who can read it? | Any member of that institution with `plan:read` (all five roles). Foreign institutions get `404`, missing permission `403`. |
| Who can change it? | `plan:write`: institution admin, scrutiny officer, super admin. Auditors and regulatory directors are read-only. |
| Is it attributable? | Yes. `created_by` and `status_changed_by` store the username; each status change writes an `audit_events` row with before/after values. |
| Are free-text notes audited? | Notes are stored on the task but **not** copied into the audit log — only the field name and length are recorded, so a phone number typed into a note does not spread into the audit trail. |
| Is it a compliance determination? | No. The API response carries a `notice`; the UI and CSV repeat it. |
| What happens on downgrade? | `alembic downgrade -1` drops both tables and therefore deletes stored plans. Export the CSV first. |
| What is not stored? | No uploaded files, no OCR text, no notification history, and no link to a specific validation run id. |

Operational note: the note field is free text with a 280-character limit. The UI asks for an
evidence reference, but nothing prevents a user from typing personal data. Say so in any pilot
briefing, and treat plan rows as institution-confidential rather than public.

---

## 8. Privacy notice accuracy (material discrepancy)

`frontend/app/src/pages/PrivacyPage.tsx` is a draft that says, among other things:

> *"This interface has no file upload or OCR endpoint."*
> *"The application stores … in Supabase Postgres. Records are scheduled for hard deletion after
> 365 days."*
> *"Authentication uses Supabase Auth."*

All three statements are **false for the current system**:

1. The Validate wizard has a real PDF upload/analysis panel, and
   `POST /api/v1/documents/analyze` **works on the live backend** (`200` with extracted text on
   2026-10-30).
2. Persistence is FastAPI + SQLAlchemy on Render Postgres (or the in-process list), not Supabase;
   no 365-day deletion job exists anywhere in the repository.
3. Authentication is FastAPI JWT (with an optional, unconfigured Supabase path).

The page does carry a "Not ready for launch" warning, which limits the harm, but publishing a
privacy policy that misdescribes data handling is a real compliance defect. It must be rewritten
to describe: what the validation API receives, that the server does not persist it, that
browsers may keep a local copy, that document uploads are processed in memory on the analyzer
endpoint, and what the enterprise pipeline stores. This is a **high-priority fix before any
pilot with real institution data**.

---

## 9. Logging, monitoring, and data minimisation

* Logs: stdlib `logging`; no structured fields, no request IDs, no PII scrubbing layer.
  Exception handlers log class names and messages; DB errors could include DSN fragments or
  document names.
* No APM, no Sentry, no metrics, no uptime alerting configured in the repository.
* No analytics or tracking SDK in the frontend.
* No cookies are set by the app; `sessionStorage` and `localStorage` are used for session and
  history.
* Public `/validate` deliberately stores nothing server-side; that is good minimisation.

**Recommendation:** add request IDs, redact `DATABASE_URL`/tokens from logs, and add a
privacy-safe error reporter before pilot use.

---

## 10. Secrets handling

* All secrets via environment variables; `.env.example` contains placeholders only.
* `.env` is git-ignored; no secret is committed (verified by scanning tracked files for key
  patterns).
* Render generates `JWT_SECRET_KEY`; the value is never exposed to the frontend.
* `VITE_*` variables are public by construction — only the Supabase *publishable* key is used.
* Demo credentials (`admin` / `admin123456`) are documented in the seed function. They are not a
  secret, but they are a liability: they must never work in production, and the production gate
  (`ENABLE_DEMO_ENDPOINTS`) must stay closed.
* No provider API keys (DigiLocker, fire portal, university portal) are configured anywhere, so
  those adapters cannot make live calls.

---

## 11. False positives and false negatives

| Failure | Cause | User-visible effect |
|---|---|---|
| **False positive** (says missing when present) | Name mismatch — `"Fire NOC"` vs `"fire_safety_certificate"`; trailing punctuation; different language | Coordinator chases a document they already have |
| **False positive** (says expired when valid) | Expiry date transcribed wrong; client/server clock or convention difference (client `≤60`, server strict `<` UTC) | Panic renewal |
| **False negative** (says present when absent/forged) | "Submitted" is typed, not uploaded; no authenticity check | **The most dangerous case** — a passing screen can be mistaken for approval |
| False negative (expired not flagged) | No expiry date entered; date unreadable in scanned PDF | Deficiency discovered at scrutiny |
| Extraction error | Regex picks the wrong date or authority label | Wrong expiry populated; human confirmation is mandatory |
| OCR absent | Tesseract not installed | Scanned NOC yields no fields at all |

The UI mitigates the worst case with a persistent scope notice, a `source:
synthetic_demo_input` envelope and a final "this is not approval" line. It does not eliminate
it; a screenshot of a green banner can still travel out of context.

---

## 12. Why preliminary validation ≠ AICTE approval

1. No official checklist is loaded; the caller supplies both sides of the comparison.
2. No document is uploaded on that path, so nothing is verified to exist.
3. No authenticity, signature, seal, or issuer check is performed.
4. No active statutory rule exists in the engine; rule activation is human-gated and has never
   happened.
5. The output is a list of differences, not an eligibility decision.
6. AICTE approval is issued by a committee after scrutiny, inspection and fee compliance —
   none of which this software performs.

Every response carries this in the `notice` field; any claim beyond it is unsupported.

---

## 13. Prioritised security fixes

| Priority | Fix | Why |
|---|---|---|
| P0 | Remove or authenticate `/api/v1/validation-runs` **before deploying `main`** | Latent unauthenticated global read/write/delete of other institutions' runs |
| P0 | Rewrite the privacy page to match reality | Publishing false data-handling statements (including "no upload endpoint") |
| P1 | Make production auth work end-to-end (token route + seeded admin on the deployed backend) | Without it, no protected feature is usable |
| P1 | Replace CORS regex with exact origins; add security headers (CSP, nosniff, frame-ancestors) | Standard hardening |
| P2 | Add rate limits to `/validate`, `/documents/analyze`, `/auth/token` | Abuse and credential stuffing |
| P2 | Add log redaction and request IDs | Incident response |
| P2 | Persist documents to object storage with lifecycle rules | Ephemeral disk loses evidence |
| P3 | Add account lifecycle: password reset, MFA, token revocation | Real deployments need it |
| P3 | Legal review of cross-institution hash matching and retention | Privacy exposure |
