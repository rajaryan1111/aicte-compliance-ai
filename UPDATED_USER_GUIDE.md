# Updated User Guide — What Is New on the Validation Screen

This guide covers only what was added in this change. The full product manual for every screen is
[PROJECT_DOCUMENTATION/USER_GUIDE.md](PROJECT_DOCUMENTATION/USER_GUIDE.md); nothing there has been
removed or renamed.

Everything below happens **after** you run a validation on **Validate** (`/validate`). No new page,
login or upload step is involved.

---

## 1. What you get now

| You used to get | You now also get |
|---|---|
| A list of missing and expired documents | A **remediation plan**: one task per gap, with owner, deadline, evidence and status |
| A single readiness percentage with no explanation | A **readiness index** with an expandable panel showing every point that was added or deducted |
| English-only guidance | A one-click **English / हिन्दी** toggle for the guidance text |

---

## 2. The remediation plan

### Where it is

On the results screen, immediately **below the findings table** ("Findings review"). If the
validation found nothing to fix, the panel is not shown at all.

### What one task contains

| Element | Meaning |
|---|---|
| Coloured dot | Red = statutory (zero-tolerance) gap, amber = other gap, blue = certificate expiring soon |
| `P1` / `P2` / `P3` | Priority. `P1` statutory gap, `P2` other gap, `P3` expiring within 60 days |
| `Clause 2.4` chip | The handbook clause this document maps to in our catalog. If no verified mapping exists, **no chip is shown** — we do not invent a citation |
| Owner role | Who normally holds this evidence, e.g. "Estate & Fire Safety Officer", "Registrar / Principal" |
| Due date | `P1` = today + 3 days, `P2` = today + 7 days, `P3` = two weeks before the certificate lapses (never in the past) |
| Overdue badge | Appears when the due date has passed and the task is not done |

### Working a task

1. **Click the task title** to expand it. You get four sections: the evidence that closes it, why it
   matters, the corrective action, and the requirement with its clause (or a line saying no verified
   clause exists).
2. **Change its status** with the dropdown on the right: `Open` → `In progress` → `Blocked` →
   `Done`. The header updates immediately: completion percentage, `done/total`, overdue count and the
   next due date.
3. **Add a short note** (up to 280 characters) inside the expanded task — for example
   "renewal filed with the fire office". Notes travel with the CSV export.
4. **Reset progress** clears `Done` back to `Open` but keeps your notes, so you can reuse the plan
   for the next cycle.

### Exporting

**Export plan (CSV)** downloads the whole plan: plan and run identifiers, priority, document,
finding, owner role, due date, status, clause, evidence required, your note and a fixed disclaimer.
It opens in Excel or LibreOffice. Text that begins with `=`, `+`, `-` or `@` is prefixed so a
spreadsheet cannot execute it as a formula.

### Re-validating: what carries over

When you fix documents and run the validation again **for the same institution and application type**:

- Gaps that are **still there** keep their status and note.
- Gaps that are **now fixed** disappear from the plan.
- **New** gaps start as `Open` — they never inherit a completed state from an old task.
- The plan's "last checked" timestamp updates to the newest run.

So the intended rhythm is: validate → work the list → correct documents → validate again → the list
shrinks and your completed items stay completed.

### Where your progress is stored — read this

**If you are signed in,** the plan is saved to your institution's workspace on the server. That
means:

- colleagues with access to the same institution see the same statuses and notes,
- progress survives switching browser or device,
- every status change is attributed to the signed-in user and recorded in the audit log,
- the schedule (due-date policy) is stored with the plan, so everyone sees the same dates;
- an institution administrator can change those dates with **Update shared schedule**; every
  change is recorded with who made it, and officers without that role see a clear message instead
  of a silent failure.

**If you are not signed in, or the server cannot be reached,** the panel says so and keeps the
plan **in this browser** (`localStorage`). In that mode it is not shared and is lost if you clear
site data or switch device. Export the CSV if the plan matters.

Either way the CSV export and the "not an AICTE determination" notice are unchanged. The due
dates are internal recommendations from a policy you can adjust; they are **not AICTE deadlines**.

---

## 3. The readiness index

Above the plan, the results screen shows a **readiness index** out of 100 and a tier.

- It is computed only from **the checklist you entered**: how many required documents you listed as
  submitted and unexpired, minus a published penalty for statutory gaps and for certificates that
  lapse within 60 days.
- Open **"How this index is calculated"** to see every adjustment with its points and reason, plus
  the raw value before it was clamped to 0–100.
- It is **not an AICTE rating, score or probability**, and it does not predict approval. The screen
  says so next to the number.

Example (the built-in "Engineering EoA 2024–27" preset): 5 required, 3 submitted, 1 of those expired,
2 statutory documents missing → base 20, two −18 penalties, raw −16, shown as **0 % / Critical**.

Read it as "how much of my own declared evidence set is in place", not as "will we be approved".

---

## 4. English / हिन्दी guidance

Use the toggle in the plan header (**English** / **हिन्दी**).

- The choice is remembered in this browser; English is the default.
- Hindi mode translates the labels, the requirement, the impact, the corrective action, the owner
  role and the evidence text, and renders clause chips as "धारा 2.4".
- The Hindi text is an **unofficial reading aid** written for this project. The English text and the
  AICTE handbook prevail, and the panel states this in Hindi whenever the toggle is on.
- Documents with no verified clause show operational guidance (owner, evidence, deadline) and an
  explicit note instead of a fabricated citation.

---

## 5. Troubleshooting

| Symptom | Cause | What to do |
|---|---|---|
| The plan panel is missing | Your validation produced no findings, or only documents with no guidance mapping | Check the findings table; a clean run intentionally shows no plan |
| Statuses reset to `Open` | Different browser, incognito window, cleared site data, or you changed the required/submitted lists so the deficiency set changed | Export the CSV next time; re-apply statuses on the new plan |
| No clause chip on a task | Our catalog has no verified citation for that document (e.g. AICTE Approval Letter, Trust Deed) | Use the "Requirement" text and confirm against the official handbook |
| Hindi text looks unfamiliar | It is project-authored, not an AICTE translation | Refer to the English text and the handbook for authoritative wording |
| "Export plan (CSV)" does nothing | The browser blocked the download | Allow downloads for the site, or use the existing "Download CSV" / "Print Summary" actions on the results screen |

---

## 6. What these features deliberately do not do

- They do not decide compliance, approve anything, or replace AICTE scrutiny.
- They do not upload, verify or authenticate documents; the checklist is still what **you** declare.
- They do not send reminders or emails, and they do not create accounts or share plans between users.
- They do not claim a probability of approval.
