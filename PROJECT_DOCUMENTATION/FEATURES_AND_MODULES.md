# Features and Modules

Every module below was verified against source, tests, and — where it exists — the live
deployment. Status vocabulary is fixed:

| Status | Meaning in this document |
|---|---|
| **Fully implemented** | Code path exists end to end, is exercised by tests or a live call, and produces the described output |
| **Partially implemented** | Works, but a material part is missing, heuristic, or unavailable in production |
| **UI only** | Renders controls; the action has no real effect |
| **Mock/demo** | Shows canned or simulated data; not computed from user input |
| **Not implemented** | Described/expected but absent |
| **Blocked** | Code exists but cannot run without an external permission, credential, or infrastructure |

Repository: `main` @ `81d9667`. "Production" = `https://aicte-compliance-ai.vercel.app` calling
`https://aicte-compliance-backend-live.vercel.app` (verified 2026-10-30).

---

## 0. Navigation map

| Sidebar label | Route (repo) | Present in production? | Component |
|---|---|---|---|
| Dashboard | `/` | yes | `pages/DashboardPage.tsx` |
| Validate | `/validate` | yes | `pages/ValidatePage.tsx` |
| Cadre & FSR Norms | `/cadre-calculator` | yes | `pages/CadreCalculatorPage.tsx` |
| Audit History | `/history`, `/history/:runId` | yes (gated) | `pages/HistoryPage.tsx` |
| Compliance Guide | `/about` | yes | `pages/AboutPage.tsx` |
| — | `/privacy`, `/terms`, `/signin` | yes | legal + auth pages |
| — | `/vault` | **production only** | not in this repository |
| Handbook Guidelines & API | links to `/about` | yes | static anchor, no API explorer |

The repository has **no** `/vault` route (`App.tsx`), yet the public site's sidebar offers
"Document Vault" and the page loads. That screen comes from a build that is not represented in
this repository and cannot be maintained from it.

---

## 1. Dashboard

**1. What it does.** Landing page. States the tool's scope, lists four "workstations" that
link into the product, and shows a health indicator for the backend.

**2. Why it exists.** To prevent the single most dangerous misreading of the product — that a
green result equals AICTE approval. The hero copy and the repeated scope notice set
expectations before any check is run.

**3. How it works internally.** Static JSX content: a hero, a "Institutional Review Framework"
section of principle cards, and a grid of four module cards built from a local array. No API
call except the health probe (`checkHealth()` → `GET /health`) rendered by
`components/HealthIndicator.tsx`. No user data, no personalisation, no server-side rendering.

**4. How a user accesses it.** `/` or the "Dashboard" sidebar item; also the logo link.

**5. Input required.** None.

**6. Output.** Four navigation cards ("Run Scrutiny Workspace", "Cadre & FSR Evaluator",
"Saved Audits & Reports", "AICTE Handbook & Specs"), scope language, backend status chip.

**7. Backend dependency.** `GET /health` only.

**8. Status.** **Fully implemented** — and it is the safest module to demo, because it makes
no claims about compliance.

**9. Limitations.** Purely presentational; the "health" chip reflects reachability, not
correctness. The card copy ("Saved Audits & Reports") implies persistence that is gated behind
sign-in.

---

## 2. Validate (4-step wizard)

**1. What it does.** Collects institution context, required document names, submitted document
names, and optional expiry dates; calls the comparison API; renders the result page.

**2. Why it exists.** This is the core product. Everything else supports or reports on it.

**3. How it works internally.**
* State machine: `form → loading → success | error` (`FormState` in `ValidatePage.tsx`).
* Four steps with per-step validation from `lib/form-validation.ts`
  (`validateValidationStep`, `validateCompleteRequest`).
* Document lists are free-text tag inputs (`components/DocumentTagInput.tsx`), trimmed and
  de-duplicated with a user-visible notice.
* Expiry dates are optional per document; empty strings are stripped before the request.
* Submission is guarded by a `useRef` flag (`submissionInProgress`) so a double click cannot
  fire two requests.
* On success the request+response pair is optionally persisted via
  `saveRunUnified()` (`lib/history-storage.ts`) — server first, `localStorage` fallback.
* Network layer: `validateDocuments()` in `lib/api.ts` — 15 s `AbortController` timeout,
  JSON parse guarded, discriminated `ApiResult<T>` union, response shape validated by
  `isValidationResponse()` before being trusted.

**4. How a user accesses it.** Sidebar "Validate", the dashboard CTA, or "Run Scrutiny
Workspace".

**5. Input required.**
| Field | Required | Constraint |
|---|---|---|
| `institution_id` | yes | free text, no format enforcement |
| `application_type` | yes | `eoa` \| `new_program` \| `intake_change` |
| `required_documents` | yes | ≥1 tag, unique after trim |
| `submitted_documents` | yes (may be empty list) | unique after trim |
| `expiry_dates` | no | `YYYY-MM-DD` per document name |

**6. Output.** `ValidationResponse` → status banner, counts, comparison table, findings table,
readiness estimate, expiry matrix, workbench, CSV, print view, JSON dossier.

**7. Backend dependency.** `POST /api/v1/validate` (public, no auth).

**8. Status.** **Fully implemented** for the comparison path. Verified live: the demo preset
returned `attention_required`, 2 missing, 1 expired, 3 findings, readiness 40 %.

**9. Limitations.**
* "Submitted" is a **typed claim**, not evidence. There is no upload, so nothing proves the
  document exists or is the document named.
* Document identity is a free-text string; `"Fire Safety Certificate"` and
  `"fire_safety_certificate"` are different documents to the engine.
* Three bundled presets exist (`AICTE_PRESETS`), all synthetic and labelled as such.

### 2a. Demo presets

| Preset | Institution ID | Expected |
|---|---|---|
| Engineering EoA 2024–27 (Deficiencies) | `SYNTH-INST-001` | 2 missing, 1 expired |
| New Technical Campus Setup (Deficiencies) | `NEW-CAMPUS-2026` | 2 missing (fire NOC present) |
| Clean Passing Submission (Zero Deficiencies) | `PASS-DEMO-001` | `preliminary_checks_passed` |

Status: **Mock/demo** (hardcoded), by design, and clearly identifiable by institution ID.

### 2b. PDF Analysis & Metadata Verification (OCR assistant)

**What.** Drag-and-drop a PDF; the backend extracts text, dates, certificate identifiers and
issuing authority; the user confirms an expiry date, which populates the wizard's date field.

**How.** `components/DocumentOcrVerifier.tsx` → `analyzeDocument()` → `POST /api/v1/documents/analyze`
(multipart, ≤10 MiB, `.pdf` only). Rendered inside step 3 of the wizard.

**Status.** **Partially implemented.** PDF text extraction is real (`pdfplumber`). Verified
live on 2026-10-30: a synthetic one-page PDF with a fire NOC returned `200` with
`extracted_text`, `sha256`, `page_count`, one extracted `certificate_number`, and
`requires_human_review: true`. Caveats:
* **Schema drift.** The live response uses `extracted_text` + `fields{name:{value,confidence,
  page_number,evidence_text}}`; this repository's client expects `extracted_text_preview` +
  flat `candidate_fields{expiry_date,...}`. Against the live backend, this code finds
  `candidate_fields === undefined` and therefore cannot prefill or display fields.
* **Date recall is imperfect.** In the live test the text contained
  "Valid until 14/04/2027" yet no expiry date was extracted; only the certificate number was.
  Always confirm dates by hand.
* Scanned/image-only PDFs yield nothing unless Tesseract is installed **and** the
  `pytesseract` path is present; the deployed analyzer is `pdfplumber` only and flags such
  files as scanned.
* "Sample Benchmarks" mode is **mock**: three hardcoded `OCR_SAMPLES` with fabricated
  certificate numbers, `confidence` values (94.2–98.6 %) and SHA-256 digests that are not
  computed from any file. They must never be cited as accuracy evidence.
* The wizard passes the human-readable document name (e.g. `"Fire Safety Certificate"`) into
  `expiry_dates`, while presets use snake_case keys — a type mismatch that silently produces
  an unused expiry entry.

### 2c. Nil-Deficiency Smart Gap Predictor

**What.** Derives a 0–100 "readiness" score, a tier, and per-finding impact + mitigation
undertaking from the same inputs.

**How.** `computeReadinessScore()` in `lib/aicte-rules.ts`: base = valid submitted ÷ required,
minus 18 per zero-tolerance finding, minus 5 per document expiring within 60 days; tiers at
≥95 (nil-deficiency), ≥65 (conditional), else critical. Clause text comes from
`APH_CLAUSE_CATALOG`.

**Status.** **Partially implemented — with a real defect.**
`APH_CLAUSE_CATALOG` is keyed by human labels (`"Fire Safety Certificate"`,
`"Occupancy Certificate"`), but the calculator looks up with document IDs from the form
(`"fire_safety_certificate"`). Every lookup misses, so `isStatutoryZeroTolerance` is always
`false`, the −18 penalty is never applied, and every finding falls back to generic text
("Application checklist deficiency noted."). Live confirmation: 2 zero-tolerance documents
missing produced a score of **40 %**, not the 22 % the intended formula yields. The label
"Probability of Nil-Deficiency" is also statistically unjustified — no calibrated model exists.

### 2d. Expiry Watchdog Matrix

**What.** Renders supplied expiry dates as a timeline with days-to-expiry, status bands, and an
issuing-authority hint.

**How.** `components/ExpiryWatchdogMatrix.tsx` — pure client-side date arithmetic against the
browser clock; `components/issuing authority` mapping is a lookup table; "Generate Memo" copies
a pre-written text block to the clipboard.

**Status.** **Partially implemented.** No server call, no notification, no scheduler — the
"watchdog" does not watch anything when the tab is closed. Client date math can disagree with
the API's UTC evaluation near midnight.

### 2e. Regulatory Scrutiny Workbench

**What.** A decision-support panel that simulates an issuing-authority verification attempt and
lists adjudication checkpoints.

**How.** `components/RegulatoryScrutinyWorkbench.tsx`. Adapter selector defaults to
`simulated_demo_adapter`; `isSimulated` short-circuits to a synthetic result labelled
`simulated_demo`. A `catch` block fabricates a `fallbackAttempt` when the API is unreachable.

**Status.** **Mock/demo.** No issuing-authority API is called anywhere in the repository; there
is no government integration to call. Present it as a workflow mock, never as verification.

### 2f. Scrutiny Dossier

**What.** Modal that assembles a printable/JSON dossier of the run.

**How.** `components/ScrutinyDossierModal.tsx` — serialises the client-side run and offers
download/copy. No signing, no timestamp authority, no server record.

**Status.** **Partially implemented.** Useful for hand-off; not an evidentiary artifact.

---

## 3. Cadre & FSR Norms

**1. What it does.** Given annual intake, programme duration, target FSR, and the actual cadre
counts (with PhD counts), computes required faculty, the 1:2:6 cadre split, deficits/surpluses,
and the resulting student-faculty ratio.

**2. Why it exists.** Documentary deficiencies are only half of AICTE scrutiny; cadre shortfall
is the other common failure and is pure arithmetic.

**3. How it works internally.** Entirely client-side in `pages/CadreCalculatorPage.tsx`:

```
totalStudents   = max(1, intake × duration)
requiredFaculty = ceil(totalStudents / targetFsr)
reqProfessors   = max(1, ceil(requiredFaculty × 1/9))
reqAssocProfs   = max(1, ceil(requiredFaculty × 2/9))
reqAsstProfs    = max(1, requiredFaculty − (reqProfessors + reqAssocProfs))
deficit(cadre)  = required(cadre) − actual(cadre)
```

Programme presets in `lib/aicte-rules.ts` (`CADRE_PROGRAM_NORMS`) set a default FSR (20 for
UG/PG, 25 for diploma) and PhD expectations. Presets for departments (deficient, compliant,
diploma) are hardcoded in the page.

**4. Access.** Sidebar "Cadre & FSR Norms" or the dashboard card.

**5. Input.** Programme type, annual intake, duration, target FSR, professors / associate /
assistant counts, PhD counts.

**6. Output.** Required vs actual table per cadre, deficit/surplus badges, computed ratio, PhD
gap, disclaimer.

**7. Backend.** **None.** No API call; results are not saved.

**8. Status.** **Fully implemented** as a calculator; **not** a rule engine. The page itself
states the ratios are "illustrative, configurable assumptions".

**9. Limitations.** No persistence, no export, no server validation, no programme-specific
AICTE table, and `Math.max(1, …)` floors can overstate requirements for tiny departments.
Worked example in [CADRE_FSR_GUIDE.md](CADRE_FSR_GUIDE.md).

---

## 4. Audit History

**1. What it does.** Lists saved validation runs, opens one in detail, deletes, exports CSV.

**2. Why it exists.** Scrutiny is a process; a record of what was checked, when, and with what
result is the audit trail.

**3. How it works internally.** `pages/HistoryPage.tsx` → `fetchRunsUnified()` in
`lib/history-storage.ts`, which tries the server (`GET /api/v1/validation-runs`, Bearer token)
and falls back to `localStorage` key `aicte_local_validation_runs_v1`. Runs are stored as
`{id, request, response, savedAt}` (local) or a server DTO. Route `/history/:runId` opens detail
via `fetchRunByIdUnified()`.

**4. Access.** Requires a session: `RequireAuth` redirects to `/signin`.

**5. Input.** None beyond being signed in.

**6. Output.** Run list with status/counts/time, detail view, CSV export, delete.

**7. Backend.** `GET/POST /api/v1/validation-runs`, `GET/DELETE /api/v1/validation-runs/{id}`
when authenticated; `localStorage` otherwise.

**8. Status.** **Partially implemented**, and effectively **blocked in production**. The live
backend's history routes are auth-gated (`GET /api/v1/validation-runs` → `401 "Sign in to
access validation history."`) but it has no `/api/v1/auth/token`, so the page cannot obtain a
session. The Render deployment does not expose these routes at all (`404`). In this repository,
the same paths exist but are **unauthenticated** and backed by a process-global list.

**9. Limitations.** Local runs vanish with browser storage; two browsers do not share history;
no pagination in the local path; no export of full evidence bundle. On the repository backend,
public `/validate` runs are held in **process memory** (lost on restart, shared by all callers,
and deletable by anyone) while authenticated enterprise runs persist in Postgres.

---

## 5. Compliance Guide

**1. What it does.** Long-form reading aid: document catalog with clause citations, common
deficiency patterns, expiry consequences, EVC expectations, FAQs.

**2. Why it exists.** The tool can say "fire NOC missing"; the guide explains why that matters
and what the mitigation undertaking looks like.

**3. How it works internally.** Static content arrays in `pages/AboutPage.tsx` + clause data in
`lib/aicte-rules.ts`. Tabs/accordions are client state only. No fetch.

**4. Access.** Sidebar "Compliance Guide" / `/about`; also the "Handbook Guidelines & API"
link.

**5. Input.** None.

**6. Output.** Rendered guidance with clause numbers (`Clause 2.4`, `Clause 1.7`, …) and a
prominent notice that it is not the official document.

**7. Backend.** None.

**8. Status.** **Fully implemented** as static content.

**9. Limitations.** Hardcoded, undated at clause level, and unverified against the official APH
in this audit. Updating a norm means editing TypeScript. There is **no** "API" documentation
surface behind that nav label — FastAPI's `/docs` is a separate host and is not linked from the
UI.

---

## 6. Sign In / Authentication

**1. What it does.** Accepts username/password, stores a session, gates `/history`.

**2. Why it exists.** History is per-institution data; it must not be world-readable.

**3. How it works internally.**
* Repository path: `POST /api/v1/auth/token` (OAuth2 password form) → JWT (HS256, 60 min),
  `sub` = user id, verified by `get_current_user()` (`api/deps.py`), tenant-scoped by
  `verify_institution_membership()`.
* Frontend: `AuthContext.tsx` — tries the backend token endpoint; if the deployment reports
  Supabase configured, uses Supabase instead. Session persisted in `sessionStorage`.
* Role is derived from the username string (contains "scrutiny" → `scrutiny_officer`, else
  `institution_admin`).

**4. Access.** `/signin`, or automatic redirect from `/history`.

**5. Input.** Username, password.

**6. Output.** Session (token, user id, institution id, role), header avatar, sign-out.

**7. Backend.** `POST /api/v1/auth/token`, `GET /api/v1/auth/me`.

**8. Status.** **Partially implemented; blocked in production.**
* Live frontend backend: `/api/v1/auth/token` is absent → **404**.
* Render backend: the endpoint exists and accepts **JSON** `{username,password}` (not a form);
  the documented demo credentials return **401**, and `/api/v1/seed` is **404**, so no user can
  currently be created there through the API.
* Repository backend: works when a user row is seeded locally (form-encoded OAuth2 password);
  there is no public registration route, by design.

**9. Limitations.** No password reset, no MFA, no email verification, no accounts screen, no
refresh token (re-login after 60 min), role inferred from a username substring, and a JWT in
`sessionStorage` readable by any XSS on the origin. See
[SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md).

---

## 7. Document Vault (production only)

**1. What it does (as observed).** Lists institution documents with type, status, size, and
dates; offers upload and download.

**2. Why it exists.** Presumably to give the institution a file store backing the checklist.

**3. How it works internally.** In the deployed bundle: `GET /api/v1/documents` (list) and
`POST /api/v1/documents` (upload) against the live Vercel backend, which returns
`401 Not authenticated` because that backend has no auth endpoint. Upload also requires the
`documents:upload` permission server-side.

**4. Access.** Sidebar "Document Vault" on the public site.

**5. Input.** A file plus document metadata (per the form).

**6. Output.** In practice: an empty/unauthorised state and a 401 on submit.

**7. Backend.** Live-only routes absent from this repository.

**8. Status.** **UI only** in production; **not implemented** in this repository.

**9. Limitations.** The screen cannot be reproduced, fixed, or tested from this codebase. Do
not demo it. If it is to be kept, its source must be located and merged into `main`.

---

## 8. Enterprise API surface (backend only, no UI)

These are implemented and unit-tested but **nothing in the frontend calls them**. They matter
for "what have we built", not for "what can a user do".

| Capability | Routes | Evidence |
|---|---|---|
| Applications lifecycle | `/api/v1/applications` (+ `/{id}`, `/status`, `/assign`, `/submit`, `/approve`, `/reject`) | `api/v1/applications.py`, 262 lines |
| Document versions, upload, download, extraction | `/api/v1/applications/{id}/documents`, `/api/v1/documents/*` | `api/v1/documents.py`, 456 lines |
| Malware scanning, quarantine, ClamAV adapter | `core/scanner.py`, job pipeline | tests |
| Validation runs + scrutiny report | `/api/v1/applications/{id}/validate`, `/reports/scrutiny` | `services/validation_orchestration_service.py`, 891 lines |
| Review queue and decisions | `/api/v1/reviews/*` | `api/v1/reviews.py` |
| Audit packages (hash-chained evidence) | `/api/v1/audit-packages/*` | `api/v1/audit_packages.py` |
| Rule governance (draft → verify → approve → activate) | `/api/v1/compliance/rules*` | `services/rule_engine.py`, `rule_catalog.py` |
| Issuing-authority verification adapters | `/api/v1/compliance/verification-attempts` | `services/issuing_authority_service.py` |
| Retention policies and purges | `/api/v1/retention/*` | `main.py` |
| Seed endpoint | `/api/v1/seed` | dev/demo only |

**Status.** **Fully implemented** in code and covered by the 493-test suite, but **not exposed
in any UI and not deployed** to either live backend. This is the largest gap between capability
and demonstrable product.

---

## 9. Feature status summary

| # | Feature | Status | Primary evidence | Biggest limitation |
|---|---|---|---|---|
| 1 | Dashboard | Fully implemented | `DashboardPage.tsx` | Static; health chip ≠ correctness |
| 2 | Validate wizard | Fully implemented | `ValidatePage.tsx` → `POST /validate` | "Submitted" is typed, not proved |
| 3 | Demo presets | Mock/demo | `AICTE_PRESETS` | Synthetic only |
| 4 | PDF analysis / expiry extraction | Partially implemented | `document_analyzer.py`, `pdfplumber` | Live schema differs from repo client; no OCR for scans; date sometimes missed |
| 5 | Sample OCR benchmarks | Mock/demo | `OCR_SAMPLES` | Fabricated confidence values |
| 6 | Readiness index (was "nil-deficiency predictor") | Fully implemented (fixed 2026-10-31) | `computeReadinessScore` | Weights are a published heuristic; clause text unverified |
| 7 | Expiry watchdog | Partially implemented | `ExpiryWatchdogMatrix.tsx` | No scheduling/persistence |
| 8 | Regulatory workbench | Mock/demo | `simulated_demo_adapter` | No authority integration exists |
| 9 | Scrutiny dossier | Partially implemented | `ScrutinyDossierModal.tsx` | Unsigned, client-assembled |
| 10 | Cadre & FSR calculator | Fully implemented | `CadreCalculatorPage.tsx` | No persistence/export; illustrative norms |
| 11 | Audit history | Partially implemented | `history-storage.ts` | Live routes 401 with no way to sign in; repo runs are public and in-memory |
| 12 | Compliance guide | Fully implemented | `AboutPage.tsx` | Hardcoded, unverified clause text |
| 13 | Sign in | Partially implemented | `AuthContext.tsx`, `auth.py` | No token route on live backend |
| 14 | Document Vault | UI only (production) | deployed bundle only | Source not in repository |
| 15 | Enterprise API + rule governance | Fully implemented (backend) | 55 operations, 493 tests | No UI, not deployed |
| 16 | Remediation action plan | Fully implemented (server persistence 2026-10-31) | `lib/action-plan.ts`, `lib/plan-sync.ts`, `RemediationActionPlan.tsx`, `api/v1/remediation_plans.py` | Needs sign-in + deployed backend; local-only fallback otherwise; due dates are internal policy, not AICTE deadlines; only an institution administrator can reschedule the shared plan, and every reschedule is recorded |
| 17 | Readiness basis panel | Fully implemented (2026-10-31) | `NilDeficiencyGapPredictor.tsx` | Shows its own heuristic weights; still not a regulation |
| 18 | Bilingual deficiency guidance (EN/हिन्दी) | Fully implemented (2026-10-31) | `lib/compliance-guidance.ts` | Hindi is an unofficial aid; 4 of 12 documents carry no clause |

Feature details, limits and verification for items 16–18: [../NEW_FEATURES_DOCUMENTATION.md](../NEW_FEATURES_DOCUMENTATION.md).
Phase 1 tasks and files: [../IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md). Phase 1 test evidence:
[../REGRESSION_TEST_REPORT.md](../REGRESSION_TEST_REPORT.md). Deployment order and probes:
[../PRODUCTION_ROLLOUT_PLAN.md](../PRODUCTION_ROLLOUT_PLAN.md). Live-vs-repo comparison and go/no-go:
[../PRODUCTION_READINESS_REPORT.md](../PRODUCTION_READINESS_REPORT.md). Phase 3 proposals:
[../PHASE_3_PLAN.md](../PHASE_3_PLAN.md).
Prioritised remediation is in [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).
