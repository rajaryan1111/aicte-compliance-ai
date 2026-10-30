# Feature Proposal — Three Additions, No New Architecture

Selected: **3** features. All are deterministic, client-side, additive, and independent of the
deployed backend contract. None replaces an existing screen.

---

## F1 — Remediation Action Plan

**Problem.** A validation result ends at "2 missing, 1 expired". The officer still has to decide
who chases what, by when, and with which evidence. That work happens in a separate spreadsheet
and is the step where small institutions lose weeks.

**Who.** Compliance officers and principals without a legal/consulting team.

**Why current functionality is insufficient.** `FindingsTable` is read-only. `ExpiryWatchdogMatrix`
shows dates, not ownership. CSV export is a record, not a plan.

**Solution.** From the same response, derive plan items, one per deficiency (plus certificates
expiring within 60 days). Each item carries:

- priority (`P1` statutory + missing/expired, `P2` other missing/expired, `P3` expiring soon)
- owner role (Registrar/Principal, Estate & Fire Safety Officer, Finance Officer, Academic Dean)
- due date from a fixed, transparent offset (`P1` +3 days, `P2` +7, `P3` min(expiry−14, +21))
- the evidence that closes it
- status (`open` / `in_progress` / `blocked` / `done`) and an optional note
- clause reference where the catalog has one

Progress, overdue count and next due date are derived. The plan can be exported as CSV and
persists in the browser for the same run.

**Measurable benefit.** Turns a read-only report into a tracked list in one click; removes the
manual transcription step. Success signal: an officer can leave the page and return to the same
run with statuses intact.

**Changes.** New `lib/action-plan.ts`, new `components/RemediationActionPlan.tsx`, one insertion
in `ValidationResults`. No schema, no API, no dependency.

**Risks.** Browser storage is per-device and clearable — disclosed in the UI and in the exported
CSV. Statuses are not attributable to a user; with auth broken, they cannot be. This is a
single-user tool until the enterprise review workflow is live.

**Testing.** Pure-function tests for prioritisation, due-date arithmetic, overdue math, status
transitions, storage codec tolerance to corrupt data, CSV injection safety.

---

## F2 — Transparent, Repaired Readiness Index

**Problem.** The readiness number is labelled "Nil-Deficiency Probability" and is computed with a
broken lookup: the clause catalog is keyed by display names while callers pass IDs, so the
zero-tolerance penalty never applies. Users see a confident percentage with no derivation.

**Who.** Anyone deciding whether to submit this week.

**Why current functionality is insufficient.** It is both opaque and, in the ID path, wrong.

**Solution.**

1. Resolve clauses by ID, alias, display label and normalised form, so `fire_safety_certificate`
   and `"Fire Safety Certificate"` both find the entry.
2. Compute the index from an explicit, itemised formula and return a `breakdown[]` of every
   adjustment with points and a reason.
3. Rename the surface to a **readiness index** and show the derivation in an expandable panel.
   It is not an AICTE rating; the UI says so.

**Measurable benefit.** A user can point at any movement in the number and see the cause. It also
removes a real false-negative: statutory documents were not being penalised.

**Changes.** `lib/aicte-rules.ts` (resolver, breakdown, scoring version),
`components/NilDeficiencyGapPredictor.tsx` (label + basis panel).

**Risks.** The weights remain a product judgement, not a regulation. Mitigation: show every
weight, label the index as a heuristic, and keep the tier wording factual.

**Testing.** Alias resolution, penalty application for missing and expired statutory documents,
score clamping, breakdown summing to the score, determinism.

---

## F3 — Bilingual Deficiency Guidance (English / हिन्दी)

**Problem.** The people who fix deficiencies are often not comfortable reading English
regulatory prose, while the rule text and citations are English.

**Who.** Compliance clerks, office superintendents and faculty coordinators at regional
institutions.

**Solution.** A curated Hindi rendering of each document's requirement, impact and mitigation,
shown beside the English original, with an explicit note that the Hindi text is an unofficial aid
and the English/APH text prevails. Documents without a catalog entry show operational guidance
(owner, evidence, timeline) and no invented clause.

**Measurable benefit.** A Hindi-reading officer can act on a finding without translating
regulatory language; English remains available at all times.

**Changes.** `lib/compliance-guidance.ts` (bilingual catalog), language toggle inside the plan
panel, persisted preference.

**Risks.** Translation drift as the handbook changes. Mitigation: translations live beside the
English source in one object, are versioned with it, and are marked unofficial.

**Testing.** Every catalog entry has both languages; unknown documents fall back safely; the
language preference persists and defaults to English on corrupt storage.

---

## Explicitly out of scope

- No new API endpoint, database table, migration, or background job.
- No changes to `POST /api/v1/validate` or any response field.
- No redesign of dashboard, sidebar, header, hero, or existing cards.
- No new npm dependency.
- No LLM, OCR, or authenticity scoring.
