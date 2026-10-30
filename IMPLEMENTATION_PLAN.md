# Implementation Plan

Backward-compatible, no destructive changes. Approval gate: nothing here alters the API contract,
database schema, deployment configuration, or production credentials.

## 1. File map

| File | Change | Why |
|---|---|---|
| `frontend/app/src/lib/compliance-guidance.ts` | **new** | Bilingual catalog keyed by document ID, with owner/evidence/timeline and optional clause mapping |
| `frontend/app/src/lib/action-plan.ts` | **new** | Pure plan builder, deadline policy, due-date math, storage codec, summary, CSV |
| `frontend/app/src/lib/plan-sync.ts` | **new** | Institution plan API client: payload builder, response validation, progress merge |
| `backend/app/api/v1/remediation_plans.py` | **new** | Authenticated, institution-scoped plan routes (create-or-get, list, read, task update) |
| `backend/app/services/remediation_plan_service.py` | **new** | Transactional plan/task persistence, optimistic concurrency, audit events |
| `backend/app/schemas/remediation_plan.py` | **new** | Request/response schemas, including the configurable deadline policy |
| `backend/alembic/versions/j0e1f2a3b4c5_remediation_plans.py` | **new** | Additive migration: `remediation_plans`, `remediation_tasks` |
| `backend/alembic/versions/k1f2a3b4c5d6_remediation_deadline_history.py` | **new** | Separate additive revision for `remediation_deadline_changes`, so an already-migrated database upgrades in place |
| `backend/app/services/remediation_plan_service.py` | **new/edit** | Adds administrator rescheduling with append-only deadline history and audit events |
| `backend/tests/test_remediation_plans_api.py` | **new** | Auth, RBAC, tenancy, idempotency, concurrency, audit |
| `frontend/tests/plan-sync.test.mts` | **new** | Payload/response contract against a captured backend response |
| `frontend/app/src/lib/report.ts` | edit (export existing helper) | Reuse spreadsheet-injection guard instead of duplicating it |
| `frontend/app/src/lib/aicte-rules.ts` | edit | Clause resolver by ID/alias/label; itemised, corrected score |
| `frontend/app/src/components/RemediationActionPlan.tsx` | **new** | Plan UI + language toggle + CSV export |
| `frontend/app/src/components/NilDeficiencyGapPredictor.tsx` | edit | Humanise names, expose scoring basis, factual labels |
| `frontend/app/src/components/ValidationResults.tsx` | edit | Insert the plan panel after findings |
| `frontend/tests/readiness.test.mts` | **new** | Resolver + scoring tests |
| `frontend/tests/action-plan.test.mts` | **new** | Plan, dates, status, storage, CSV tests |
| `frontend/tests/guidance.test.mts` | **new** | Bilingual completeness + fallback tests |

## 2. Data and API impact

- **Schema:** two new tables (`remediation_plans`, `remediation_tasks`) via one additive Alembic
  revision. No existing table, column or constraint changes, so the migration can be rolled back
  without touching application, validation or audit data.
- **API:** five new routes under `/api/v1/institutions/{institution_ref}/remediation-plans`,
  including the administrator-only `PATCH .../deadline-policy`.
  Existing routes are untouched; the plan is still derived in the browser from the
  `ValidationResponse`, and the server stores it rather than evaluating compliance.
- **Auth/RBAC:** new `plan:read` / `plan:write` / `plan:policy` permissions. Auditors and
  regulatory directors read only; institution admins, scrutiny officers and super admins can
  update tasks; only institution admins and super admins can reschedule the shared plan.
- **Env:** none new. The backend uses its existing `DATABASE_URL` and `JWT_SECRET_KEY`.
- **Persistence:** server record per (institution, plan signature) once signed in. `localStorage`
  keys `aicte.actionPlans.v1`, `aicte.guidance.lang` and `aicte.deadlinePolicy.v1` remain as an
  offline cache and fallback; when the API rejects or is unreachable, the panel says progress is
  not saved to the server.
- **Deadlines:** the P1/P2/expiry-buffer offsets are a configurable planning policy stored with the
  plan. They are labelled as internal recommendations everywhere and are never presented as AICTE
  deadlines.

## 3. Order of work

1. Guidance catalog (IDs, aliases, English + Hindi, clause mapping only where the existing catalog
   has a citation).
2. Clause resolver and scoring rewrite in `aicte-rules.ts`; keep all existing result fields so
   `ScrutinyDossierModal` keeps working.
3. Action-plan module (pure functions first, then storage helpers).
4. UI: plan panel, then readiness basis panel, then insertion.
5. Tests, lint, typecheck, production build.
6. Documentation and regression report.

## 4. Compatibility rules

- Export names used by other components (`computeReadinessScore`, `APH_CLAUSE_CATALOG`,
  `ReadinessScoreResult`) remain.
- New result fields are additive (`breakdown`, `baseScore`, `scoringVersion`).
- Existing tests must pass unchanged; no assertion is weakened.
- Existing routes, nav, and page structure untouched.

## 5. Regression checks

```bash
cd frontend/app && npm test          # existing 7 tests + new suites
cd frontend/app && npm run lint      # oxlint
cd frontend/app && npm run build     # tsc -b && vite build
cd <repo> && pytest -q              # backend suite: 493 passed, 21 skipped (incl. 18 plan tests)
cd frontend/app && npm test          # 47 passed
```

Plus a manual check of the Validate flow with a preset, and a check that the CSV export still
opens and contains the same columns.

## 6. Rollback

Frontend-only rollback: delete the new components/modules and revert the three edits. The
localStorage keys are namespaced and ignored if the components are absent.

Backend rollback: `alembic downgrade -1` drops the two plan tables (no other data is touched) and
reverting the deploy removes the four routes. The frontend then reports that progress is kept in
this browser only, which is the pre-change behaviour.
