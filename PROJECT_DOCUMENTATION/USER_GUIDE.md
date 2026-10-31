# User Guide

A practical walkthrough of the deployed site as it behaves on **2026-10-30**, not as the
repository intends it to behave. Where a control cannot actually be used, this guide says so
instead of inventing steps.

**Site:** https://aicte-compliance-ai.vercel.app/

> **Read this first.** Validation and the Cadre calculator work without an account. Sign-in
> does **not** work on the deployed backend, so Audit History and the Document Vault cannot be
> used in production today. Document analysis works for text-based PDFs.

---

## 1. Open the site

1. Go to https://aicte-compliance-ai.vercel.app/ in any modern browser.
2. The dashboard loads immediately; no account, cookie consent, or installation is required.
3. The first API call you may notice is a health check. If the backend is awake, the status chip
   shows a healthy state. On a cold start (free hosting) the first call can take 30–60 seconds;
   a transient "unreachable" chip usually clears on retry.

**What you should see:** a hero statement about preliminary validation, a scope notice, a
"Institutional Review Framework" section, and four module cards.

---

## 2. Understand the dashboard

| Area | What it shows | What it means |
|---|---|---|
| Hero + scope notice | That results are preliminary and checklist-driven | The product is not an approval authority |
| Framework cards | Principles of documentary scrutiny | Reading material, not data |
| "Institutional Compliance Workstations" | Four cards: Run Scrutiny Workspace, Cadre & FSR Evaluator, Saved Audits & Reports, AICTE Handbook & Specs | Shortcuts into the modules |
| Backend status chip | Reachability of `/health` | Reachability only, not correctness |

Nothing on this page is personalised. There is no "your institution" state.

---

## 3. Navigate the sidebar

The sidebar is on the left (collapsible on desktop, a drawer on mobile):

| Item | Goes to | Works without sign-in? |
|---|---|---|
| **Dashboard** | `/` | ✅ |
| **Validate** | `/validate` | ✅ |
| **Cadre & FSR Norms** | `/cadre-calculator` | ✅ |
| **Audit History** | `/history` | ❌ redirects to Sign In |
| **Compliance Guide** | `/about` | ✅ |
| **Document Vault** (deployed build only) | `/vault` | ❌ loads, but every action returns 401 |
| **Handbook Guidelines & API** | anchors to the Compliance Guide | ✅ static |

The bottom of the sidebar repeats the review-scope notice: *"EoA 2026–27 rule review is
pending. Current checks use only the lists supplied."*

---

## 4. Open the Scrutiny Workspace

1. Click **Validate** in the sidebar (or **Run Scrutiny Workspace** on the dashboard).
2. The page opens a four-step wizard with a progress indicator:
   **Application → Documents → Expiry dates → Final review**.
3. You can move with **Continue** / **Back**; each step validates before it lets you proceed.
4. A preset selector lets you load a synthetic example (see §5).

The workspace is client-side until the final step; nothing is sent while you type.

---

## 5. Supply documents (the normal path)

This is the path that actually produces results. "Documents" here are **names**, not files.

1. **Step 1 — Application**
   * *Institution identifier*: any non-empty string, e.g. `SYNTH-INST-001` or your real
     institution code. It is a label; nothing is looked up.
   * *Application type*: Extension of Approval (EOA), New Program, or Intake Change.
2. **Step 2 — Documents**
   * Under **Required documents**, type each document the scrutiny checklist asks for and press
     Enter. Example: `aicte_approval`, `mandatory_disclosure`, `land_use_certificate`,
     `fire_safety_certificate`, `building_occupancy_certificate`.
   * Under **Submitted documents**, type only the ones you actually have on file.
   * Names are trimmed and de-duplicated; a duplicate notice appears if you add the same name
     twice.
   * **Naming consistency matters.** `fire_safety_certificate` and `Fire Safety Certificate`
     are treated as two different documents.
3. **Step 3 — Expiry dates** (optional but important)
   * For each submitted document, enter the expiry date printed on the certificate.
   * Leave blank for documents that do not expire (e.g. a land deed) — they will not be
     expiry-checked.
   * A date entered for a *missing* document is ignored, because expiry is evaluated over
     submitted documents only.

**Fast demo path.** Use the preset menu at the top of the wizard:
* *Engineering EoA 2024–27 (Deficiencies)* — 5 required, 3 submitted, 2 expiring/expired.
* *New Technical Campus Setup (Deficiencies)*.
* *Clean Passing Submission (Zero Deficiencies)*.

### 5b. Upload a PDF (optional, separate from the checklist)

In the **Expiry dates** step there is a **PDF Analysis & Metadata Verification** panel:

1. Drag a `.pdf` (≤10 MiB) onto the drop zone, or click to choose a file.
2. **Upload Real PDF** sends it to `POST /api/v1/documents/analyze`. The server extracts text
   in memory and returns page count, SHA-256, and any detected certificate number/dates.
3. Review the result. The backend does not store the file.
4. Enter or confirm an expiry date and choose the target document type; the value populates the
   wizard's date field.

**Limits you will notice.**
* Scanned/image-only PDFs produce no fields. The server has no OCR engine (Tesseract is not
  installed), so a photographed NOC cannot be read.
* Date detection is imperfect. In a live test on 2026-10-30, a PDF containing "Valid until
  14/04/2027" returned a certificate number but **no expiry date**. Type the date yourself if
  it does not appear.
* The panel's **Sample Benchmarks** tab is demonstration data with invented confidence scores.
  Do not cite it as evidence.
* Non-PDF files, files over 10 MiB, encrypted PDFs, and corrupt files are rejected with a
  readable message.

---

## 6. Execute validation

1. Continue to **Final review**; check the institution, type, required list, submitted list and
   dates.
2. Click **Run preliminary validation** (the primary button).
3. The request is `POST /api/v1/validate` with a 15-second timeout.
4. While it runs, the button shows a loading state; double submission is blocked.
5. On success the wizard is replaced by the results page. On failure an inline alert explains
   whether it was a network error, a timeout, a server error, or invalid input.

---

## 7. Interpret the results

### 7.1 The banner

* **Checks Passed** (green) — every required name appears in the submitted list and no supplied
  expiry date is in the past. This means *the two lists agree*, nothing more.
* **N Finding(s)** (amber) — at least one missing or expired document.

### 7.2 Counts and comparison

Four stat cards show required, submitted, missing, expired. Below them, a comparison table
marks each required document as present or missing, and flags expired ones.

### 7.3 Findings table

| Code | Meaning | Evidence shown |
|---|---|---|
| `MISSING_DOCUMENT` | A required name is absent from the submitted list | `source: submitted_document_list`, `observed: not_submitted` |
| `DOCUMENT_EXPIRED` | A submitted document's expiry is **before today (UTC)** | `expiry_date`, `evaluation_date` |

A document expiring **today** is not expired (the check is strictly "before today"). A document
with no date is never expired.

### 7.4 Additional panels

* **Nil-Deficiency Readiness** — a 0–100 planning score with a tier. Treat it as a heuristic,
  not a probability. Its clause lookups are currently broken, so impact/mitigation text falls
  back to generic wording.
* **Expiry Watchdog** — timeline of supplied dates with days remaining. Recalculated in your
  browser; it does not run in the background.
* **Regulatory Scrutiny Workbench** — a **simulated** adjudication panel. It says
  `simulated_demo`; no government system is contacted.

### 7.5 Export

* **Download CSV** — one row per finding plus a summary row, with spreadsheet-formula
  injection neutralised.
* **Print Summary** — print-friendly layout including validation scope and timestamps.
* **Download Scrutiny Dossier** — JSON/printable bundle assembled in the browser; unsigned.
* **Start New Validation** — clears the form.

---

## 8. Use Cadre & FSR Norms

1. Sidebar → **Cadre & FSR Norms**.
2. Choose a programme (sets duration and a default FSR; both remain editable).
3. Enter **annual intake** and **duration**.
4. Enter actual counts: professors, associate professors, assistant professors, and PhD counts
   for P/AP.
5. Read:
   * required vs actual per cadre with deficit/surplus badges,
   * computed student–faculty ratio,
   * PhD gap,
   * a compliance banner.

The page recomputes as you type and calls no server. Nothing is saved; screenshot or print if
you need a record. The page states its ratios are illustrative assumptions, not an AICTE
determination. Worked examples are in [CADRE_FSR_GUIDE.md](CADRE_FSR_GUIDE.md).

---

## 9. Audit History — read this before trying

**What it is meant to do:** list saved validation runs, open one, delete it, export.

**What happens on the deployed site:**

1. Click **Audit History**. Because the route is protected, you are redirected to **Sign In**.
2. Sign-in calls the deployed backend's token endpoint.
3. That endpoint **does not exist** on the live backend (`404`), so no session is created.
4. You cannot reach `/history` with server data.

If you sign in against a *different* backend that has auth (for example a local development
instance), the page lists runs from the API and falls back to this browser's
`localStorage` when the API is unavailable. Local runs are per-browser and disappear if site
data is cleared.

**Practical workaround today:** export the CSV/print/dossier from the result page immediately.
That is the only durable record the deployed product gives you.

---

## 10. Use the Compliance Guide

1. Sidebar → **Compliance Guide** (or **Handbook Guidelines & API**, which anchors here).
2. Read the document catalog, deficiency patterns, expiry consequences and FAQs.
3. Clause citations (e.g. "Clause 2.4") come from hardcoded content, not a live handbook.

It is static text: no search index, no PDF download, no API explorer. The banner states it is
not the official document and must be checked against AICTE's published handbook.

---

## 11. Authentication — what to expect

| Behaviour | Detail |
|---|---|
| Where | `/signin`, or automatic redirect from `/history` |
| What it asks | Username and password |
| What it does | Tries the backend token endpoint; if the deployment advertises Supabase, tries that instead |
| Where the session lives | `sessionStorage` (per tab; gone when the tab closes) |
| Expiry | 60 minutes, no refresh |
| Sign out | Header menu; clears the session |

**On the deployed site, sign-in cannot succeed** because the live backend lacks the token
route. If you see "Sign-in failed" or a 404 message, that is the known deployment gap, not your
password. Do not enter a real password you use elsewhere.

---

## 12. When something goes wrong

| Symptom | Likely cause | What to do |
|---|---|---|
| "Unable to reach the server" | Backend asleep/unreachable, offline, DNS | Wait 30–60 s and retry; check the health chip |
| "Request timed out" | 15 s client timeout, cold start, slow network | Retry once; if persistent, the backend is unhealthy |
| 422 / "check the highlighted fields" | Blank institution, duplicate names, invalid date, missing required list | Fix the highlighted field; duplicates must be removed |
| 401 on History/Vault | No valid session; no token endpoint in production | Expected today; use CSV/print export instead |
| 404 from PDF analysis | You are on a deployment without the endpoint | Use the checklist path; type dates manually |
| "Document analysis failed" on a scanned PDF | No OCR installed | Enter the date from the paper certificate |
| Empty readiness/impact text | Clause lookup misses snake_case names | Ignore the generic text; read the finding itself |
| Page blank after deploy | Stale bundle cache | Hard refresh |

There is no in-app support channel, feedback form, or error-report ID. Note the time and the
visible message if you need to report a defect.

---

## 13. Privacy and safety rules for users

1. **Do not upload real, unredacted certificates to a public demo.** The analyzer does not
   persist files, but the site is a prototype and the privacy page is out of date.
2. **Do not enter personal data** (staff names, Aadhaar, phone numbers). The forms need none.
3. **Saved runs stay in your browser** if the API is unavailable. On a shared computer, clear
   site data after use.
4. **A green result is not approval.** Attach the disclaimer whenever you forward a screenshot.
5. **Verify every extracted date** against the original document.

---

## 14. One-page quick start

```
1. Open https://aicte-compliance-ai.vercel.app/
2. Sidebar → Validate
3. Load the "Engineering EoA 2024–27" preset (or type your own lists)
4. Check required vs submitted names; add expiry dates
5. Final review → Run preliminary validation
6. Read the banner, counts, and findings
7. Download CSV / Print Summary (do this before leaving)
8. Sidebar → Cadre & FSR Norms → enter intake and cadre counts
9. Sidebar → Compliance Guide for clause context
10. History/Vault: unavailable until production auth is fixed
```

---

> **Changing the schedule (administrators).** Signed in as an institution administrator, the plan
> header's **Update shared schedule** button re-dates every open task from the policy you enter. A
> scrutiny officer sees the same inputs but receives "Only an institution administrator can change
> the shared schedule", and the plan keeps the dates everyone else sees. Each change is logged
> with the actor's username and the number of tasks moved.

## 15. After the results: remediation plan, readiness basis, Hindi

Added 2026-10-31, below the findings table on the results screen. In short:

- A **remediation plan** turns each gap into a task with a priority, owner role, due date, the
  evidence that closes it, a status you set, and an optional note. **Export plan (CSV)** shares it.
- Progress is saved to your **institution's workspace** when you are signed in, so colleagues see
  the same statuses and the changes are attributed to you. Without sign-in (or if the server is
  unreachable) it is kept in this browser only, and the panel says which mode is active.
- Due dates are **recommended internal deadlines** from an adjustable policy. They are not AICTE
  deadlines.
- A **readiness index** now shows an expandable "How this index is calculated" panel. It is not an
  AICTE rating or a probability of approval.
- An **English / हिन्दी** toggle translates the guidance; the Hindi text is an unofficial aid and
  the English handbook wording prevails.

Full instructions, including what carries over on re-validation and the troubleshooting table, are
in [../UPDATED_USER_GUIDE.md](../UPDATED_USER_GUIDE.md).
