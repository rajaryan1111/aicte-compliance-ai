# Cadre & Faculty–Student Ratio (FSR) Guide

Module: `frontend/app/src/pages/CadreCalculatorPage.tsx`
Norms data: `frontend/app/src/lib/aicte-rules.ts` (`CADRE_PROGRAM_NORMS`)
Backend involvement: **none**. This module never calls an API and saves nothing.

> The page itself states: *"The 1:15 / 1:20 faculty–student ratios, the 1:2:6 cadre quota and
> the PhD composition targets are illustrative, configurable assumptions for planning. No
> AICTE rule is active in this prototype."* Treat the numbers below as arithmetic on
> **your** assumptions, not as an AICTE determination.

---

## 1. What "cadre" means here

Cadre = the sanctioned teaching hierarchy of a department:

| Cadre | Code | Role |
|---|---|---|
| Professor | `P` | Senior-most; usually Head of Department or research lead |
| Associate Professor | `AP` | Mid-level |
| Assistant Professor | `ATP` | Bulk of teaching load |

AICTE scrutiny does not only ask "do you have enough teachers?" It asks two separate questions:

1. **Is the total strength enough for the students?** → Faculty–Student Ratio (FSR).
2. **Is the strength distributed correctly across the hierarchy?** → cadre ratio, conventionally
   **1 : 2 : 6** (P : AP : ATP), i.e. 1 professor and 2 associate professors for every 6
   assistant professors — 1/9, 2/9, 6/9 of the sanctioned posts.

A department can pass FSR and still fail cadre: 24 assistant professors and one professor is
24 teachers for 480 students (FSR 20) but a 1:0:24 cadre, which is a deficiency.

---

## 2. Implemented formulas (verbatim)

```ts
const totalStudents   = Math.max(1, annualIntake * durationYears);
const requiredFaculty = Math.ceil(totalStudents / targetFsr);

// 1:2:6 ratio (1+2+6 = 9 parts)
const reqProfessors = Math.max(1, Math.ceil(requiredFaculty * (1 / 9)));
const reqAssocProfs = Math.max(1, Math.ceil(requiredFaculty * (2 / 9)));
const reqAsstProfs  = Math.max(1, requiredFaculty - (reqProfessors + reqAssocProfs));

const totalExistingFaculty = professors + assocProfs + asstProfs;
const currentRatio = totalStudents / totalExistingFaculty;      // shown to 1 dp

const profDeficit  = reqProfessors - professors;
const assocDeficit = reqAssocProfs - assocProfs;
const asstDeficit  = reqAsstProfs  - asstProfs;
const totalDeficit = requiredFaculty - totalExistingFaculty;
```

Notes on intent and edge behaviour:

* `Math.ceil` always rounds **up**, so a fractional requirement becomes a whole post (correct
  for a minimum).
* `Math.max(1, …)` guarantees at least one professor and one associate professor even in a tiny
  department. This can overstate the requirement for very small intakes.
* Assistant-professor posts absorb the remainder, so
  `reqP + reqAP + reqATP == requiredFaculty` whenever `requiredFaculty ≥ 3`.
* `totalStudents` is **intake × duration**, i.e. the sanctioned four-year cohort, not the
  current enrolled headcount. Lateral-entry admissions and dropouts are not modelled.
* The denominator is the *sum* of the three cadres — part-time, visiting, and
  workshop/instructional staff are not separated out.

### Programme defaults

| Key | Programme | Default FSR | PhD expectation (P / AP / ATP) |
|---|---|---|---|
| `engineering_ug` | B.Tech / B.E. | 20 (Tier 2); 15 selectable | 100 % / 100 % / 20 % |
| `management_pg` | MBA / PGDM | 20 | 100 % / 100 % / 10 % |
| `mca_pg` | MCA | 20 | 100 % / 100 % / 10 % |
| `polytechnic_diploma` | Diploma | 25 | 50 % / 20 % / 0 % |

The **target FSR is a user-editable field**, so 15 (Tier 1) can be applied to any programme.
The app does not decide which tier applies to an institution — that is a user assumption.

---

## 3. Worked example A — the page's default state (synthetic)

Inputs as the page loads them:

| Input | Value |
|---|---|
| Programme | Engineering UG |
| Annual intake | 120 |
| Duration | 4 years |
| Target FSR | 20 |
| Professors (PhD) | 0 (0) |
| Associate Professors (PhD) | 2 (1) |
| Assistant Professors | 18 |

Calculation:

```
totalStudents   = 120 × 4                       = 480
requiredFaculty = ceil(480 / 20)                = 24
reqProfessors   = max(1, ceil(24 × 1/9)) = ceil(2.67) = 3
reqAssocProfs   = max(1, ceil(24 × 2/9)) = ceil(5.33) = 6
reqAsstProfs    = 24 − (3 + 6)                  = 15
existing        = 0 + 2 + 18                    = 20
currentRatio    = 480 / 20                      = 24.0
```

Output shown to the user:

| Cadre | Required | Actual | Result |
|---|---|---|---|
| Professor | 3 | 0 | **Deficit 3** |
| Associate Professor | 6 | 2 | **Deficit 4** |
| Assistant Professor | 15 | 18 | Surplus 3 |
| **Total** | 24 | 20 | **Deficit 4** |

Plus: current FSR **24.0** (worse than the target 20), PhD gap: 1 associate professor without a
doctorate. The page shows a non-compliance banner warning that cadre shortfall can trigger
intake reduction or withholding of extension.

Interpretation: this department is *close* on headcount (20 vs 24) but badly shaped — it has no
professor at all and three extra assistant professors. Hiring three professors and four
associate professors fixes both the total and the shape; hiring seven assistant professors
would fix neither.

---

## 4. Worked example B — a compliant department (synthetic)

| Input | Value |
|---|---|
| Annual intake | 120, duration 4, target FSR **15** | 
| P / AP / ATP | 4 / 8 / 20 |

```
totalStudents   = 480
requiredFaculty = ceil(480 / 15) = 32
reqP  = ceil(32/9) = 4
reqAP = ceil(64/9) = ceil(7.11) = 8
reqATP = 32 − 12 = 20
existing = 32 ; ratio = 480/32 = 15.0
```

All three cadres exactly meet requirement, total deficit 0, ratio 15.0 → the page reports
compliance.

---

## 5. How a user operates it

1. Sidebar → **Cadre & FSR Norms** (or the dashboard card "Cadre & FSR Evaluator").
2. Choose a programme preset (this sets duration and default FSR; both remain editable).
3. Optionally load a department preset (hardcoded synthetic examples):
   "Common Deficient Engineering Dept (360 Seats)",
   "Compliant Tier-1 Engineering Dept (1:15)",
   "Management Dept (MBA - 120 Seats)".
4. Enter annual intake and duration; enter actual P / AP / ATP counts and PhD counts.
5. Read the required-vs-actual table, deficit badges, computed ratio and PhD gap.
6. Nothing to save — screenshot or print the page if a record is needed.

**What not to do.** Do not enter real staff names; the form takes counts only. Do not present
the output as an AICTE finding — no rule is active.

---

## 6. Regulatory references used (editorial, unverified in this audit)

| Concept | Cited as | Where |
|---|---|---|
| FSR 1:15 / 1:20 | APH faculty norms | page copy, `CADRE_PROGRAM_NORMS` |
| Cadre 1:2:6 | APH faculty cadre | page copy, formula |
| PhD composition | APH faculty qualifications | `phdRequirement` |
| Consequence of shortfall | intake reduction / EoA withholding | page copy, `aicte-rules.ts` deficiency impacts |

No clause numbers are attached to these ratios in code, and the repository contains no AICTE
handbook PDF. If an interviewer asks "which clause mandates 1:2:6?", the honest answer is:
*"The ratio is from AICTE faculty norms as commonly published; our implementation treats it as
a configurable planning assumption and we have not machine-verified the citation."*

---

## 7. Limitations and known issues

1. **No persistence.** Refresh loses everything; no PDF/CSV export from this page.
2. **No server validation.** A crafted value (e.g. intake 0) is clamped in the UI
   (`Math.max(1, …)`) but there is no authoritative record.
3. **Cohort approximation.** `intake × duration` ignores lateral entry, supernumerary seats,
   and actual enrolment.
4. **Single department.** No aggregation across departments or institute-level totals.
5. **PhD gap is partial.** Only professor and associate-professor deficits are surfaced; the
   assistant-professor PhD expectation from `CADRE_PROGRAM_NORMS` is not evaluated in the UI.
6. **Ratios are assumptions.** Tier selection, programme classification and whether diploma
   norms apply are all user choices.
7. **No link to validation.** A cadre shortfall does not appear as a finding in the Validate
   result, even though both live on the same site.

### Reasonable next steps

* Add CSV/PDF export and optional server-side save alongside validation history.
* Ask for *actual enrolled strength* as an override for `intake × duration`.
* Evaluate the assistant-professor PhD target and show a consolidated PhD register.
* Gate the 1:15 tier behind an explicit "Tier-1 institution" toggle with a recorded assumption.
* Only after a source-verified rule is approved, feed cadre results into the validation engine
  as a `CHECK_CADRE_COMPLIANCE` check.
