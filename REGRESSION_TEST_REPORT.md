# Regression Test Report

Run on 2026-10-31 against the working tree that contains F1 (action plan), F2 (readiness index)
and F3 (bilingual guidance). Nothing was deployed; no production system was touched.

Two rounds are recorded. **Round 1** (§1–§8) covers the three features as browser-local work.
**Round 2** (§9) re-runs every suite after server-side plan persistence, RBAC and the configurable
deadline policy were added, and adds a live multi-user/multi-institution probe against the repo
backend. Round 2 supersedes Round 1's counts; nothing in Round 1 was rewritten.

## 1. Environment

| Item | Value |
|---|---|
| Checkout | `aicte-compliance-ai`, branch `main` at `81d9667`, feature work uncommitted in the working tree |
| Node / npm | v24.10.0 / 11.6.1 |
| Frontend test runner | `node --experimental-strip-types --test --test-isolation=none ../tests/*.test.mts` |
| Backend Python | 3.14 in a local venv (`/tmp/aicte-venv`) with `requirements-dev.txt` and `requirements-ocr.txt` |
| Backend URL used for manual checks | `http://localhost:8000` (repo backend, not Render) |
| Frontend used for manual checks | `npm run dev` → `http://localhost:5173` |

## 2. Commands and results

### Frontend

| Command | Result |
|---|---|
| `cd frontend/app && npm test` | **39 passed, 0 failed** (7 pre-existing + 32 new) |
| `cd frontend/app && npx tsc --noEmit -p tsconfig.json` | exit 0, no diagnostics |
| `cd frontend/app && npm run build` (`tsc -b && vite build`) | **built in 261 ms**; `dist/assets/index-*.js` 589.40 kB (gzip 164.05 kB); one pre-existing chunk-size warning |
| `cd frontend/app && npm run lint` (`oxlint`) | **5 warnings, 0 errors** on 51 files — same warnings as before this change (React Compiler `set-state-in-effect` notes in pre-existing components) |

Test counts by file:

| File | Tests | Origin |
|---|---|---|
| `action-plan.test.mts` | 14 | new (F1) |
| `readiness.test.mts` | 10 | new (F2) |
| `guidance.test.mts` | 8 | new (F3) |
| `findings.test.mts` | 2 | pre-existing, unchanged |
| `report.test.mts` | 2 | pre-existing, unchanged |
| `validation-flow.test.mts` | 3 | pre-existing, unchanged |

### Backend (must stay untouched by this change)

| Command | Result |
|---|---|
| `/tmp/aicte-venv/bin/python -m pytest -q` | **475 passed, 21 skipped, 0 failed** in 23.10 s |
| `pytest -q` (system interpreter, first attempt) | 474 passed, **1 failed**, 21 skipped |

The single failure was `backend/tests/test_ocr_engine_integration.py::test_tesseract_reads_synthetic_institution_document`
raising `ModuleNotFoundError: No module named 'pytesseract'`. `pytesseract` is an **optional** extra
(`backend/requirements-ocr.txt`) that CI installs and this local interpreter did not have;
`/opt/homebrew/bin/tesseract` itself was present. Installing the extra
(`pip install -r backend/requirements-ocr.txt`) made the test pass and the full suite green. This is
an environment gap, not a regression, and no backend file was modified by this work.

The 21 skips are the live-infrastructure tests, all reporting
`Set RUN_LIVE_INTEGRATION_TESTS=true to execute against real services` (Postgres migrations and
persistence, Redis/Celery worker, full e2e workflow). They were not enabled for this pass, so **no
claim of live Postgres or Redis validation is made here**.

## 3. What the new tests actually assert

**F1 — `action-plan.test.mts` (14)**
Prioritisation and owner assignment; due-date offsets and the expiring-soon countdown; overdue
derivation; duplicate findings collapsing to one task; plans built from typed lists when `findings`
is omitted; an expired document not also scheduled as expiring soon; immutable status/note/reset
mutations with the 280-character cap; summary maths and next-due selection; leap-year/month-boundary
date arithmetic; storage codec round-trip and rejection of foreign versions, corrupt JSON and
partially malformed plans; upsert replacement and the 25-plan cap; **plan identity stable across
re-runs of the same checklist and different when the deficiencies differ**; progress merge taking
provenance from the new run and never inventing completed tasks; CSV row count, column order,
formula-prefix neutralisation and clause export.

**F2 — `readiness.test.mts` (10)**
Identifier/alias/label resolution; the zero-tolerance penalty now applying through the id path; a
complete unexpired checklist scoring 100 with a "checklist only" statement; expired statutory
documents penalised once, not twice; clamping at zero while still explaining the raw total; the
expiring-soon window; invalid and missing expiry dates neither crashing nor creating findings; an
empty checklist scoring zero instead of dividing by zero; determinism and the scoring version.

**F3 — `guidance.test.mts` (8)**
Every catalog entry having both languages for every field; ids, aliases and humanised spellings
resolving; unknown documents returning `undefined` rather than an invented citation; the
unofficial-translation and unverified-clause notices present in both languages; plan UI strings
covering every status, priority and action in both languages.

## 4. Existing behaviour preserved

- No pre-existing test file was edited. `findings.test.mts`, `report.test.mts` and
  `validation-flow.test.mts` pass unmodified.
- `lib/report.ts` only exports an existing helper (`safeSpreadsheetValue`) for reuse; its own tests
  are unchanged and pass.
- `computeReadinessScore`, `APH_CLAUSE_CATALOG`, `ReadinessScoreResult` keep their names and all
  previous fields; new fields (`breakdown`, `baseScore`, `scoringVersion`, counts) are additive, so
  `ScrutinyDossierModal` and the print path still compile and render.
- Routes, sidebar, dashboard, header, hero, colours and typography are untouched; the plan panel is a
  new child inside the existing results page.
- No API request was added, so the `POST /api/v1/validate` contract and its 200-response schema are
  unchanged.

## 5. Defect found and fixed during this pass

While verifying F1 in the running app, the plan key was found to include the server's `checked_at`,
which changes on every run. Every re-validation therefore created a new plan and recorded progress
could never be seen again — the feature's headline claim ("leave the page and return with statuses
intact") was false in practice.

Fix: `planIdFor()` now hashes institution + application type + the sorted set of task ids, and
`mergePlanProgress()` carries statuses/notes for tasks that still exist while provenance
(`checkedAt`, `createdAt`) comes from the newest run. Two unit tests cover it, and the earlier
assertion in this change's own test file that had encoded the volatile key was replaced — no
pre-existing test was weakened.

## 6. Manual verification on the real UI (local, 2026-10-31)

Driven in a browser against `http://localhost:5173` with the repo backend on `:8000`:

| Check | Observed |
|---|---|
| Preset "Engineering EoA 2024–27 (Deficiencies)" → 3 steps → results | results render, API chip "API Connected", `attention_required` |
| Action plan panel | 3 tasks: AICTE Approval Letter (expired, P1), Building Occupancy Certificate (missing, P1), Fire Safety Certificate / NOC (missing, P1) |
| Clause pointers | Fire → Clause 2.4, Occupancy → Clause 2.5; **AICTE Approval Letter shows no clause** (catalog has none) — no citation invented |
| Priority mapping | all three P1 (both missing documents are zero-tolerance statutory) |
| Status change | Fire set to "done" via the select → header `1/3 पूर्ण`, progress bar 33 % |
| Hindi toggle | full panel re-renders in Hindi, including owner roles, clause labels ("धारा 2.4"), the stored-locally notice and the unofficial-translation note; preference survives reload |
| Persistence across a re-run | "Start New Validation" → same preset → validation re-run: Fire **still "done"**, `1/3`, stored `checkedAt` updated to the new run — the fix in §5 confirmed live |
| Readiness index | 5 required / 3 submitted / 1 expired / 2 statutory gaps → **0 %**, "Critical", with the itemised basis panel |
| Expiry watchdog | 2 expired rows with day counts and "Generate Memo" actions |

Not exercised in this pass: mobile and narrow viewports, keyboard-only traversal of the new panel,
actual CSV file download to disk (covered by unit tests only), any flow involving sign-in (auth is
not functional on the deployed backend and was not part of this work), and the Vercel deployment
(no deployment was performed, so the production site still serves the previous build).

## 7. Pre-existing issues observed but not in scope

- The readiness index does not react to action-plan progress; they are independent signals, and the
  UI does not imply otherwise.
- `NilDeficiencyGapPredictor` and the plan panel both repeat document names; intentionally kept
  separate so neither component has to know about the other.
- Chunk size warning (589 kB) is unchanged and pre-existing.
- The repository's `main` branch still exposes unauthenticated global run routes, the deployed
  backend lacks a token endpoint, and the Vault nav item has no source here — all documented in
  `PROJECT_DOCUMENTATION/IMPLEMENTATION_STATUS.md` §3 and untouched by this change.

## 8. Verdict

**Pass with one caveat.** Frontend: 39/39 tests, clean typecheck, successful production build,
lint unchanged at 0 errors. Backend: 475/475 with the optional OCR extra installed, 21 live-infra
tests skipped by design. The new panel was exercised against the real API in a browser, including a
re-validation round-trip. The deployed production site has not been updated, and live
Postgres/Redis integration was not enabled.

---

## 9. Round 2 — server-side plan persistence (2026-10-31, later same day)

Scope of this round: authenticated institution-scoped plan storage, RBAC, optimistic concurrency,
audit events, a configurable deadline policy, and the front-end sync/fallback path. No existing
route, page or schema was changed.

### 9.1 Suites, run against the final tree

| Command | Result |
|---|---|
| `/tmp/aicte-venv/bin/python -m pytest -q` (repo root, Python 3.12.4) | **493 passed, 21 skipped, 0 failed** in 29.11 s |
| `cd frontend/app && npm test` | **47 passed, 0 failed** (7 pre-existing + 40 new) |
| `cd frontend/app && npx tsc --noEmit -p tsconfig.json` | exit 0, no diagnostics |
| `cd frontend/app && npm run build` | `built in 725 ms`; `dist/assets/index-nto65OvN.js` 601.20 kB (gzip 167.76 kB); one pre-existing chunk-size warning |
| `cd frontend/app && npm run lint` | **5 warnings, 0 errors** on 52 files — the same 5 React Compiler `set-state-in-effect` notes as Round 1 |
| `/tmp/aicte-venv/bin/python -m alembic -c backend/alembic.ini heads` | `k1f2a3b4c5d6 (head)` — exactly one head |

The 21 skips are unchanged: the live-infrastructure tests still require
`RUN_LIVE_INTEGRATION_TESTS=true`. **No live Postgres or Redis validation is claimed.**

The 18 backend additions are `backend/tests/test_remediation_plans_api.py` (auth required, RBAC,
tenant concealment, idempotent create, stale-version 409 + `X-Current-Version`, audit rows,
validation rejections). The 8 frontend additions are `frontend/tests/plan-sync.test.mts`
(payload shape, response parsing, 401/403/404/409 mapping, merge and no-op detection).

### 9.2 Live multi-user, multi-institution probe

`scripts/live_plan_probe.py` (manual; not collected by pytest) against uvicorn on
`http://127.0.0.1:8000` with SQLite `sqlite:////tmp/aicte-e2e.db`. Synthetic actors only:
`admin` (institution_admin, `DEMO-INST-001`), `reviewer` (scrutiny_officer, `DEMO-INST-001`),
`auditor1` (auditor, `DEMO-INST-001`, created directly in the throwaway DB),
`foreign_admin` (institution_admin, synthetic `SYNTH-INST-002`).

**19 checks, 0 failures:**

| Check | Observed |
|---|---|
| Unauthenticated list / create | `401` / `401` |
| Create plan | `201` |
| Re-post identical body | `200`, same `id` |
| Task update with current version | `200`, `version` 1 → 2, `status_changed_by = admin` |
| Update with stale version | `409` + `x-current-version: 2` |
| Re-post after progress was recorded | `t1` still `done`, `t2` still `open` |
| Auditor writes | `403`; auditor read `200` |
| Foreign institution list / write | `404` / `404` (concealed) |
| `p2_days < p1_days`, duplicate task keys, body/path mismatch | `422`, `422`, `422` |
| Audit trail | `remediation_plan_created` and `remediation_task_updated` rows with actor, before/after |
| Administrator reschedule | `200`; policy stored, open tasks moved, history entry `changed_by=admin`, `rescheduled_tasks=1` |
| Scrutiny officer reschedule | `403` (task edits are allowed, moving commitments are not) |
| Repeat reschedule with the same policy | `200`, no new history entry, no version bump |
| Migration upgrade on an existing database | `j0e1f2a3b4c5` → `k1f2a3b4c5d6` applied in place on the e2e SQLite file; `remediation_deadline_changes` created, `alembic_version` updated |

### 9.3 Production comparison (read-only probes)

| Surface | Version | Paths | Plan routes | `/validation-runs` | `/institutions` |
|---|---|---|---|---|---|
| `aicte-compliance-ai.vercel.app` same-origin `/api` | 0.4.0 | 8 | absent | present | present |
| `aicte-compliance-api-preview.onrender.com` | 0.3.1 | 25 | absent | **404** | **404** |
| This working tree | 0.3.1 + change | 47 | present | present | present |

Consequences verified by request, not inferred:

- The deployed frontend (`index-D0Wiwpzv.js`) calls its own origin and therefore the 0.4.0
  prototype, which has no plan routes. Registered users on production get the local-only fallback.
- Render is **not** a drop-in target for the current frontend build as it stands: it answers `404`
  for `/api/v1/validation-runs` and `/api/v1/institutions`, both of which the frontend calls for
  history and institution lookup. The repo backend implements both, so Render must be upgraded from
  this tree **before** the frontend is deployed. See `PRODUCTION_ROLLOUT_PLAN.md` §1.
- No production write, deployment, migration or credential change was performed in either round.

### 9.4 Round 2 verdict

**Engineering complete and locally verified; deployment deliberately not performed.** Every
mandatory local check passes on the final tree, the plan API behaves correctly for four distinct
synthetic actors across two institutions, and the fallback path is exercised by tests. What remains
is operational: upgrade the backend, run the migration, verify, then deploy the frontend.
