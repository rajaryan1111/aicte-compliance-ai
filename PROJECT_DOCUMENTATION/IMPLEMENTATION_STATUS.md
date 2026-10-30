# Implementation Status

Status vocabulary (fixed for this document): **Fully implemented**, **Partially implemented**,
**UI only**, **Mock/demo**, **Not implemented**, **Blocked**.

Evidence is code + tests + live observation on 2026-10-30. "Production" means
`aicte-compliance-ai.vercel.app` with `aicte-compliance-backend-live.vercel.app`.

---

## 1. Feature matrix

| Feature | Status | Evidence in code | Limitations | Next steps |
|---|---|---|---|---|
| Dashboard | **Fully implemented** | `pages/DashboardPage.tsx`; health via `HealthIndicator.tsx` | Static; health chip ≠ correctness; card copy implies saved reports work | Add an honest "prototype" badge and link to known limitations |
| Validation wizard | **Fully implemented** | `pages/ValidatePage.tsx` + `lib/form-validation.ts` → `POST /api/v1/validate` | "Submitted" is a typed claim, not evidence; string identity only | Add file-backed mode using the enterprise document model |
| Demo presets (3) | **Mock/demo** | `AICTE_PRESETS` in `ValidatePage.tsx` | Synthetic only; institution IDs look fabricated by design | Keep; label visibly in the UI |
| PDF analysis (expiry/metadata) | **Partially implemented** | `document_analyzer.py` (pdfplumber), `POST /documents/analyze`, `DocumentOcrVerifier.tsx` | Live schema ≠ repo client; expiry sometimes missed; no OCR for scans; UI junk samples | Align API contract; switch client to live schema or pin backend; add real sample PDF |
| Sample OCR benchmarks | **Mock/demo** | `OCR_SAMPLES` (3 hardcoded docs, 94–98 % confidence) | Fabricated confidence, cert numbers, hashes | Remove or relabel "illustrative" |
| Readiness index (formerly "nil-deficiency probability") | **Fully implemented** (2026-10-31) | `computeReadinessScore`, `resolveClauseForDocument`, `READINESS_WEIGHTS` in `lib/aicte-rules.ts`; `NilDeficiencyGapPredictor.tsx` basis panel; `frontend/tests/readiness.test.mts` | Weights (−18 statutory gap, −5 expiring ≤60 d) are a published product judgement, not a regulation; clause text still unverified against the official APH | Verify clause text against the handbook; keep the basis panel visible |
| Remediation action plan | **Fully implemented** (server persistence added 2026-10-31) | `lib/action-plan.ts`, `lib/plan-sync.ts`, `components/RemediationActionPlan.tsx`; `api/v1/remediation_plans.py`, `services/remediation_plan_service.py`; `backend/tests/test_remediation_plans_api.py`, `frontend/tests/plan-sync.test.mts` | Requires sign-in and a deployed backend with the remediation migrations (`j0e1f2a3b4c5`, `k1f2a3b4c5d6`); without either, progress stays in `localStorage` and the panel says so. Due dates are an internal policy, not AICTE deadlines: an institution administrator can reschedule them (audited, with append-only history), and a scrutiny officer cannot. No notification/reminder delivery. | Deploy the migration and routes (see `../PRODUCTION_ROLLOUT_PLAN.md`); add reminders once an email channel exists |
| Bilingual deficiency guidance (EN/हिन्दी) | **Fully implemented** (2026-10-31) | `lib/compliance-guidance.ts` (12 documents), toggle in `RemediationActionPlan.tsx`, `frontend/tests/guidance.test.mts` | Hindi is an unofficial aid; English/APH prevails (stated in the UI); translations are project-authored, not AICTE translations | Review Hindi wording with a domain reviewer when the APH is verified |
| Expiry watchdog matrix | **Partially implemented** | `ExpiryWatchdogMatrix.tsx` | Client clock; no scheduling or alerts; memo is clipboard text | Add server-side expiry register and notifications |
| Regulatory scrutiny workbench | **Mock/demo** | `simulated_demo_adapter` default; synthetic fallback in `catch` | No issuing-authority integration; fallback fabricates an attempt | Label "simulation"; or wire real adapter with credentials |
| Scrutiny dossier | **Partially implemented** | `ScrutinyDossierModal.tsx` | Browser-assembled, unsigned, no timestamp authority | Sign server-side; store hash in audit package |
| Cadre & FSR calculator | **Fully implemented** | `CadreCalculatorPage.tsx`; `CADRE_PROGRAM_NORMS` | No save/export; intake×duration cohort; illustrative ratios; P/AP PhD only | Add export + server persistence; evaluate ATP PhD target |
| Audit history | **Partially implemented** | `HistoryPage.tsx`, `history-storage.ts`, `RequireAuth` | Production auth impossible; repo saved-run routes unauthenticated/in-memory; local-only fallback | Fix auth; use Postgres runs; remove prototype routes |
| Compliance guide | **Fully implemented** | `pages/AboutPage.tsx` + `aicte-rules.ts` | Hardcoded, undated, unverified against official APH | Add source version + last-reviewed date; link official PDF |
| Sign in / auth | **Partially implemented** | `AuthContext.tsx`, `api/v1/auth.py`, `core/security.py` | Live backend: no token route; Render: JSON login, demo creds rejected; repo: form login | Ship one auth contract; seed production admin securely |
| Document Vault | **UI only** (production) / **Not implemented** (repo) | Deployed bundle only; live `GET/POST /documents` → 401 | Source absent from repo; no way to fix or test here | Locate source, merge, or remove the nav item |
| Enterprise API (applications, documents, runs, reviews, audit packages) | **Fully implemented** | 50 operations; `api/v1/*`; 474 backend tests | **No UI** consumes it; not deployed to the public backend | Build reviewer workspace; deploy `main` |
| Rule engine (APH drafts) | **Blocked** | 6 evaluators; `rule_catalog.py` gate; all drafts `unverified`, `approval=None` | Cannot activate without attributable source verification + approval | Complete verification with official APH hash and reviewer sign-off |
| Issuing-authority verification | **Blocked** | `verification_adapter.py` (DigiLocker/fire/university) with SSRF allowlists | No credentials or portal endpoints; workbench is simulated | Obtain partner credentials; sandbox test |
| OCR engine (Tesseract) | **Blocked** (optional) | `ocr_pipeline.py`, `requirements-ocr.txt` | Not installed in Render; no image path in public analyzer | Add apt package/custom image + integration test |
| Retention/purge | **Partially implemented** | `retention_service.py`, `/compliance/retention/*` | Scheduler off; no policy configured; no storage-level cleanup | Configure policy; schedule; test deletion |
| Malware scanning | **Blocked** (no scanner) | `ClamAVScanner`, `QuarantineScanner` | No ClamAV deployed → all uploads `scan_unavailable` | Deploy clamd or use a scanning service; keep fail-closed |
| Background jobs | **Fully implemented** | Celery app, outbox, dispatcher, worker tasks | Render runs `CELERY_TASK_ALWAYS_EAGER=true`; no queue isolation | Run a worker; monitor queue depth |
| Audit packages | **Fully implemented** (backend) | `api/v1/audit_packages.py`, hash chain | No UI; no signing key management | Expose in reviewer UI; add key rotation |

---

## 2. What is genuinely strong

1. **Deterministic validation core** with explicit scope/source/notice in the schema.
2. **Fail-closed security gates** (scanner, rule activation, upload validation).
3. **Provenance by design**: version snapshots, SHA-256, rule snapshots, audit events.
4. **Honest disclaimers in the API**, not just the UI.
5. **A substantial backend suite and CI** covering OCR and real-infrastructure adapters.

> Test-count note: `pytest -q` at `main` reports **474 passed, 21 skipped, 1 failed** on a
> machine without Tesseract. The failure is the optional OCR integration test; CI installs
> Tesseract and runs the OCR job separately. Always state the environment with the number.

---

## 3. Severity-ordered remediation

### P0 — fix before showing to an evaluator or deploying

| # | Issue | Why | Concrete fix |
|---|---|---|---|
| 1 | Repository `main` exposes unauthenticated global `validation-runs` | Read/delete anyone's runs if deployed | Require Bearer + membership scope, or delete the routes |
| 2 | Privacy page describes a system that does not exist ("no upload endpoint", Supabase, 365-day deletion) | Publishing false data-handling claims | Rewrite from the actual architecture |
| 3 | Production sign-in impossible → History/Vault dead | Core navigation dead-ends | Add `/auth/token` to the deployed backend and seed an admin, or hide those nav items |
| 4 | PDF analyzer contract drift | Live 200 but repo UI shows nothing | Pin one schema; regenerate client types |
| 5 | ~~Readiness clause lookup broken~~ **Resolved 2026-10-31** | Wrong score + generic advice | `resolveClauseForDocument` now resolves ids, aliases and labels; score is itemised in the UI |

### P1 — fix before a pilot

6. Deploy `main` to one backend and point the frontend at it; retire the split-brain.
7. Migrate Render DB from `g7b8c9d0e1f2` to `i9d0e1f2a3b4` (run migrations, verify `/health/ready`).
8. Replace CORS regex with exact origins; add CSP/nosniff/frame-ancestors.
9. Rate-limit `/validate`, `/documents/analyze`, `/auth/token`.
10. Persistent object storage for documents (ephemeral disk loses files).
11. Make the workbench's synthetic fallback explicit in the UI at all times.

### P2 — engineering debt

12. Expose applications/documents/validation/reviews in a UI (largest capability gap).
13. Add frontend build + test to CI; add a migration smoke test.
14. Structured logs, request IDs, redaction, `/metrics`.
15. Split the 540 kB JS bundle; lazy-load routes.
16. Normalise `document_type` against a catalog; constrain `academic_year`.
17. Remove `OCR_SAMPLES` fabricated confidence values.
18. Add pagination/export to Cadre and History.

### P3 — roadmap

19. Enable Tesseract + a labelled accuracy set.
20. Verify APH sources and activate rules through the gate.
21. Integrate issuing-authority adapters with real credentials.
22. Retention policy, backups, restore drill.
23. Account lifecycle (reset, MFA, revocation).

---

## 4. What could fail during a live demonstration

| Risk | Probability | Mitigation |
|---|---|---|
| Render cold start makes the health chip red | High | Pre-warm the URL 2 minutes before; or demo the live backend |
| Sign-in attempted on stage → 404 | High | Do not demo auth; say it is intentionally gated |
| Vault clicked → 401 | High | Remove or skip; explain the build mismatch |
| PDF upload on a scanned certificate → no fields | Medium | Use a text-based PDF; have a typed date ready |
| Expiry date not extracted → empty field | Medium | Type it; frame as human-in-the-loop |
| Readiness score questioned | Medium | Expand "How this index is calculated" and show the itemised basis; say "planning heuristic", not probability |
| Workbench mistaken for real verification | Medium | Point at `simulated_demo` label |
| History empty after save | High | Export CSV/print immediately |
| Duplicate document names → 422 | Low | Use the preset or keep names unique |
| Audience asks "is this AICTE-approved?" | Certain | Quote the notice; state it is a prototype |

---

## 5. How to describe status in one line

> "The deterministic checklist engine and the cadre calculator are complete and live. The
> document-evidence backend is complete and tested but has no user interface and is not the
> backend the public site uses. Authentication, the vault, OCR, rule activation and authority
> verification are the open items, and we say so in the product."

---

## 6. Scorecard by area

| Area | Grade | Reason |
|---|---|---|
| Validation correctness | A− | Deterministic, well-tested, honest envelope; free-text identity limits it |
| Backend engineering | A− | 50 routes, 20 tables, outbox, audit chain, RBAC, tests |
| Frontend engineering | B | Clean components, good a11y touches, but one chunk and contract drift |
| Deployment reproducibility | D | Three divergent revisions; vault source missing |
| Security posture | C+ | Strong primitives, weak edges (no rate limit/headers, latent public runs) |
| Privacy/legal readiness | D | Outdated privacy page; no DPA/retention policy |
| Demo readiness | B− | Validation + cadre demo well; auth/vault/history do not |
| Documentation accuracy (before this set) | C | Canonical docs stale; privacy page false |
