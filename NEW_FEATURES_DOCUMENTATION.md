# New Features Documentation

Three additions, all shipped in the existing frontend. They are deterministic, client-side,
additive and independent of the deployed backend contract: no route, API field, database table,
migration, environment variable or npm dependency was added or changed.

| # | Feature | New code | Tests |
|---|---|---|---|
| F1 | Remediation Action Plan | `lib/action-plan.ts`, `components/RemediationActionPlan.tsx` | `frontend/tests/action-plan.test.mts` (14) |
| F2 | Transparent, repaired Readiness Index | `lib/aicte-rules.ts`, `components/NilDeficiencyGapPredictor.tsx` | `frontend/tests/readiness.test.mts` (10) |
| F3 | Bilingual deficiency guidance (EN / हिन्दी) | `lib/compliance-guidance.ts`, toggle in `RemediationActionPlan.tsx` | `frontend/tests/guidance.test.mts` (8) |

Selection rationale, rejected ideas and scope boundaries are in
[INNOVATION_RESEARCH.md](INNOVATION_RESEARCH.md) and [FEATURE_PROPOSAL.md](FEATURE_PROPOSAL.md);
the file-level plan is [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

---

## F1 — Remediation Action Plan

### The real problem

A validation run ends at "2 missing, 1 expired". The officer still has to work out **who** chases
**what**, **by when**, and **with which piece of paper**. In practice that happens in a separate
spreadsheet that someone retypes from the screen, and it is where small institutions lose weeks
between the deficiency letter and the reply.

This exists because the results screen is deliberately read-only evidence: `ValidationResults`
shows findings, the expiry matrix shows dates, and CSV export is a record of what the engine said,
not a work plan.

### Who uses it

The compliance officer, registrar or principal of an institution that does not have a consultant
or a legal cell — typically one or two people doing this alongside their actual job.

### What it produces

From the same in-memory `ValidationRequest` + `ValidationResponse` that produced the results, one
task per deficiency, plus one per certificate that lapses inside a 60-day window:

| Field | Rule (all in `lib/action-plan.ts`) |
|---|---|
| `priority` | `P1` missing/expired statutory (zero-tolerance) document; `P2` other missing/expired; `P3` expiring soon |
| `ownerRole` | From the guidance catalog per document (e.g. Estate & Fire Safety Officer); `Registrar / Principal` when unknown |
| `dueDate` | `P1` today + 3 days, `P2` today + 7, `P3` min(expiry − 14 days, today + 21), never in the past |
| `evidenceRequired` | The specific evidence that closes the item, phrased per finding type |
| `clause` | Catalog citation, or `null` — never synthesised |
| `status` | `open` → `in_progress` → `blocked` → `done`, set by the user |
| `note` | Free text, capped at 280 characters |

Derived in the header: completion percentage, `done/total`, overdue count (due date in the past and
not done), next due date, blocked count.

### Plan identity — why re-validating does not lose progress

`planIdFor(institutionId, applicationType, deficiencySignature)` hashes the **set of task ids**, not
the server's `checked_at`. Two consequences:

- Re-running the same checklist reopens the **same** plan, so recorded statuses and notes return.
- Correcting a document changes the deficiency set, which is a genuinely different plan; a task
  that disappears is never resurrected and a new task never inherits a completed state
  (`mergePlanProgress` copies only matching task ids).

Provenance is not lost: the stored plan always carries the **latest** run's `checkedAt`, because the
component upserts on every plan change.

> This was a real defect found during the live verification pass and fixed before delivery: the
> original key included `checked_at`, so every re-validation produced a new plan and progress could
> never be seen again. See [REGRESSION_TEST_REPORT.md](REGRESSION_TEST_REPORT.md) §5.

### Storage

**Signed in:** the plan is persisted server-side per institution by
`POST /api/v1/institutions/{institution_ref}/remediation-plans`, keyed by the deficiency signature
(`plan-<hash>`), so the same checklist always reopens the same record. Progress is shared by every
member of the institution, attributed to the signed-in username, and status changes are written to
the audit log. Updates use optimistic concurrency (`version`), so a stale tab gets a 409 instead of
overwriting a colleague.

**Not signed in, or API unavailable:** `localStorage` key `aicte.actionPlans.v1`, versioned envelope
(`version: 1`), at most 25 plans, newest first. Every read is inside `try/catch`; corrupt,
foreign-version or partially malformed data is discarded rather than thrown (`parseStoredPlans`,
`sanitizePlan`, `sanitizeItem`). Pre-sign-in progress is pushed to the server on the first successful
sync, so signing in does not discard work already recorded in the browser.

**What this is not:** an official AICTE record. The plan is derivative work produced from a
preliminary validation result; the API returns a `notice` saying so, and the panel and CSV repeat it.
Due dates come from a configurable internal policy and are never presented as AICTE deadlines.
On a stored plan an institution administrator can change that policy with `PATCH
.../remediation-plans/{plan_id}/deadline-policy`: open tasks are re-dated, completed tasks and
certificate-expiry tasks keep their dates, moved tasks get a version bump, and the change is
appended to `remediation_deadline_changes` and `audit_events`. A scrutiny officer editing tasks
gets `403` for this route, and the panel explains why.

### CSV export

15 columns: plan and run identifiers, priority, document, finding, owner role, due date, status,
clause, evidence required, note, and a fixed guidance note. Every cell goes through
`safeSpreadsheetValue` (reused from `lib/report.ts`), so a value like `=INST` cannot execute as a
formula, and quotes are doubled.

### Where it appears

`ValidationResults.tsx` renders `<RemediationActionPlan request={request} response={data} />`
directly after the findings table. It renders `null` when the plan has no tasks, so a clean
validation is not given an empty panel. No existing element was moved or restyled.

### How an institution uses it

1. Run a validation (preset or own document list).
2. Read the plan: red dot items are this week's statutory work.
3. Assign by owner role, set each item to `in progress` as it is chased.
4. Expand an item for the evidence, the consequence, the corrective action and the clause pointer.
5. Export CSV and circulate it, or print the dossier.
6. Correct the documents, re-validate: unchanged gaps keep their status; fixed gaps leave the plan.

---

## F2 — Transparent, repaired Readiness Index

### The defect that existed

`NilDeficiencyGapPredictor` passed document **ids** (`fire_safety_certificate`) into a clause catalog
keyed by **display labels** (`"Fire Safety Certificate"`). Every lookup missed, so
`isStatutoryZeroTolerance` was always false, the statutory penalty was never applied, and every
finding fell back to the text "Application checklist deficiency noted." The number was both opaque
and, in the id path, wrong. It was also labelled "Probability of Nil-Deficiency", which no calibrated
model supported.

### What it does now

- `resolveClauseForDocument()` resolves an id, an alias, a display label, or a normalised spelling,
  so both call shapes find the entry; ids map through `DOCUMENT_ID_TO_CATALOG_KEY`.
- The score is computed from a published formula and returned with an itemised `breakdown[]`.

```
base    = (submitted − expired − missing) / required × 100        (0 when required is empty)
adjust  = −18 per statutory zero-tolerance gap  (READINESS_WEIGHTS.statutoryGap)
          −5  per certificate expiring within 60 days (READINESS_WEIGHTS.expiringSoon)
score   = clamp(base + adjust, 0, 100)
```

Tiers: `≥ 95` no gaps detected, `≥ 65` conditional, otherwise critical. The result carries
`scoringVersion` (`readiness-2026-10-30.1`), counts of required/submitted/missing/expired/
expiring-soon/statutory gaps, and the raw pre-clamp value so a clamped 0 can still be explained.

- The surface is renamed a **readiness index**, and a `HOW THIS INDEX IS CALCULATED` panel lists
  every adjustment with its points and reason. The UI states that it is derived from the caller's
  checklist and is **not an AICTE rating**.
- Document names are humanised, so rows read "Fire Safety Certificate / NOC", not `fire_safety_certificate`.

### Worked example (the synthetic Engineering EoA preset, observed live)

5 required, 3 submitted, 1 of those expired, fire safety and occupancy missing (both statutory):
base = (3 − 1 − 1)/5 × 100 = 20, penalties = 2 × −18 = −36, raw = −16, clamped score = **0 %**,
tier "Critical (0–64)". Two zero-tolerance documents missing is a genuine stop — the number now says
so instead of reporting 40 %.

### Limits

The weights are a product judgement, not a regulation; they are published in the UI, versioned, and
tested for determinism. Document guidance clause text comes from this project's APH catalog and is
**not yet verified** against the official handbook (the UI's `GUIDANCE_SOURCE_NOTE` says exactly
that).

---

## F3 — Bilingual Deficiency Guidance (English / हिन्दी)

### The problem

The people who actually fix deficiencies — clerks, office superintendents, faculty coordinators at
regional institutions — often read Hindi more comfortably than English regulatory prose. The rule
text and every citation, however, are English and must stay English.

### What it provides

`lib/compliance-guidance.ts` holds one curated object per document with English **and** Hindi for
label, requirement, impact, corrective action, owner role and evidence required:

- 12 documents: `aicte_approval`, `mandatory_disclosure`, `land_use_certificate`,
  `fire_safety_certificate`, `building_occupancy_certificate`, `land_ownership_affidavit`,
  `trust_deed`, `master_plan_architect_certificate`, `fd_corpus_fund_receipt`,
  `nba_accreditation`, `state_pollution_noc`, `building_stability_certificate`.
- 8 carry a clause pointer from the existing catalog; **4 deliberately carry none** (approval letter,
  land ownership affidavit, trust deed, master plan certificate) — the panel then shows operational
  guidance only and an explicit "no verified clause" line instead of inventing a citation.
- `GUIDANCE_VERSION = "2026-10-30.1"` and `GUIDANCE_SOURCE_NOTE` travel with the text.

The language toggle lives in the plan header and persists in `localStorage`
(`aicte.guidance.lang`, default English on absent or corrupt storage). Switching language re-labels
the panel but never the underlying record: the CSV keeps English identifiers and the run's original
values.

### Honesty rules encoded in the UI

- Hindi is an unofficial aid; the English/APH text prevails — shown under the toggle in Hindi mode.
- Clause labels render as "धारा 2.4" for readability, but the stored citation stays `Clause 2.4`.
- A document outside the catalog gets generic operational guidance and a visible "unknown document"
  notice, never a fabricated requirement.

---

## Impact, verification and cost

| Question | Answer |
|---|---|
| New API calls? | Four plan routes, called only when signed in. Signed out, everything is still derived from data already in the browser and no backend call is made. |
| Schema / migration? | One additive Alembic revision (`j0e1f2a3b4c5`): `remediation_plans`, `remediation_tasks`. No existing table, column or constraint changes. |
| New dependency? | None — `lucide-react`, `react`, Tailwind components already present. |
| Existing screens changed? | `ValidationResults.tsx` gains one child; `NilDeficiencyGapPredictor.tsx` gains a basis panel and corrected labels. Layout, navigation, routes, colours untouched. |
| Backend touched? | Yes: four routes, one service, two models, two schemas, one migration, two RBAC permissions. `pytest` 489 passed / 21 skipped (14 new plan tests). |
| Frontend tests | 45 passed (7 pre-existing + 38 new). |
| Typecheck / lint / build | `tsc --noEmit` clean, `oxlint` 5 pre-existing warnings 0 errors, `vite build` succeeds. |
| Measurable benefit | A read-only report becomes a tracked, owned, exportable plan; wrong readiness numbers become explainable ones; Hindi-reading staff can act without translating regulatory prose. |

## Known limitations and next steps

1. **Plans are keyed by institution + deficiency signature, not by validation run.** That is what
   makes re-validation idempotent, but it also means a stored plan is not a legal record of one
   specific run. If that is required, store the run id alongside `checked_at`.
2. **Persistence needs the newer backend.** The deployed Render backend and the prototype website
   API do not expose the plan routes yet, so production stays in local-only mode until the backend
   is upgraded. See [PRODUCTION_ROLLOUT_PLAN.md](PRODUCTION_ROLLOUT_PLAN.md).
3. **No notifications.** Due dates are visible, not sent. A digest job would need the outbox/worker
   that already exists in the backend.
4. **Hindi text needs a domain review.** It is project-authored; it must be checked before being
   described as official terminology, and re-checked whenever the APH clause text changes.
5. **Clause verification remains open** (unchanged by this work): the catalog is a pointer for human
   review, not regulation.

## Demo path (2 minutes)

Validate → *Engineering EoA 2024–27 (Deficiencies)* → Continue ×3 → the results screen shows the
readiness index with its basis → the deficiency register with clause and mitigation → the action
plan with three prioritised tasks → set one to `पूर्ण` → switch to हिन्दी and back → export CSV →
re-validate the same preset and show the completed task still ticked.
