# Demo and Presentation Guide

Everything here is calibrated to what the deployed site actually does. The demo deliberately
avoids sign-in, the vault, and the workbench's "verified" framing, because those are the parts
most likely to fail or mislead.

**URL:** https://aicte-compliance-ai.vercel.app/
**Pre-flight:** open the site and run one validation 5 minutes before you present (free hosting
sleeps). Keep a CSV export on the desktop as a fallback.

---

## 1. The two-minute explanation

> "AICTE scrutiny rejects applications for two boring, preventable reasons: a required
> certificate is missing from the upload set, or a certificate on file has expired. Both are
> discoverable before submission, but today they are found by a human reading a checklist.
>
> We built a pre-scrutiny tool. An institution enters the checklist AICTE asks for, the
> documents it actually has, and their expiry dates. In under a second it returns exactly what
> is missing, what has lapsed, and for each gap the clause that is implicated and the kind of
> undertaking that usually resolves it. It exports a deficiency register the principal's office
> can act on, and it includes a cadre calculator for the 1:2:6 faculty ratio — the other common
> failure.
>
> Two design decisions matter. First, the checks are deterministic: same input, same output,
> every time, so a result can be defended. Second, the product never claims compliance. Every
> response says it evaluated only the list you supplied and is not an AICTE approval. We would
> rather be useful and honest than impressive and wrong."

If asked "is it AI?": *"No LLM. Compliance needs reproducibility and explainability, so the
engine is rule and date logic. The 'intelligence' is the clause knowledge base. We have an OCR
adapter for scanned certificates, but it is optional and not enabled in this deployment, and we
say so."*

---

## 2. Five-minute demo script

### 0:00–0:30 — Frame the problem (Dashboard)

* Open the site. Point at the scope banner.
* Say: *"This is a pre-scrutiny checker, not an approval system. The banner is part of the
  product, not legal decoration."*
* Scroll to the four workstations. Do **not** click Audit History or Document Vault.

### 0:30–1:15 — Load a realistic case (Validate → preset)

* Click **Validate**.
* Choose preset **"Engineering EoA 2024–27 (Deficiencies)"**.
* Say: *"Five documents required, three submitted, two dates supplied. This mirrors a typical
  private engineering college in an EoA year — approval letter, mandatory disclosure, land
  certificate present; fire NOC and occupancy certificate absent; the AICTE approval itself
  expired in March 2024."*
* Walk the four steps quickly: Application → Documents → Expiry dates → Final review.

### 1:15–2:00 — Run and read the result

* Click **Run preliminary validation**.
* Expected: amber banner, **3 findings**, 2 missing, 1 expired.
* Point at the finding codes and evidence:
  * `MISSING_DOCUMENT` with `observed: not_submitted`.
  * `DOCUMENT_EXPIRED` with `expiry_date 2024-03-31` and `evaluation_date` today.
* Say: *"Note the envelope: `validation_scope: caller_supplied_checklist_only`, `source:
  synthetic_demo_input`, and the notice. A reviewer can see exactly what was and was not
  checked."*

### 2:00–2:30 — Turn it into an action

* Click **Download CSV**. Open it briefly (or show the file name).
* Say: *"One row per finding plus a summary row, formula-injection safe, so it can go straight
  into the principal's tracker."*
* Point at **Print Summary** for the human-readable version.

### 2:30–3:15 — Cadre & FSR

* Sidebar → **Cadre & FSR Norms**.
* Load **"Common Deficient Engineering Dept (360 Seats)"**.
* Read the numbers: 480 students, 24 required at FSR 20, cadre 3/6/15 versus actual 0/2/18 →
  deficits 3 professors, 4 associate professors; ratio 24.0.
* Say: *"This is the second failure mode: headcount is close, but the shape is wrong. Three
  assistant professors too many and no professor at all. Hiring seven assistant professors
  would fix neither ratio nor cadre."*

### 3:15–3:45 — Context, not just a checklist

* Sidebar → **Compliance Guide**.
* Show the clause catalog and the expiry-consequence section.
* Say: *"The tool tells you what is missing; the guide tells you why it matters and what the
  mitigation undertaking looks like. Both cite clause numbers, and both say they must be
  checked against the official handbook."*

### 3:45–4:30 — Architecture in one breath

* Say: *"React SPA, FastAPI, deterministic comparison endpoint, JWT and role-based access on the
  enterprise routes, Postgres with immutable document versions, malware scanning that fails
  closed, and an audit trail that records which document versions and which rule versions were
  used. The public validation path stores nothing."*
* If a slide is available, show the architecture diagram from
  [TECHNICAL_ARCHITECTURE.md](TECHNICAL_ARCHITECTURE.md).

### 4:30–5:00 — Honest limits and close

* Say: *"Three things are deliberately incomplete. Authentication is not working on this
  deployment, so history and the vault are gated off. OCR for scanned certificates is optional
  and not installed. And no AICTE rule is active in the engine yet, because we require
  attributable source verification and human approval before a rule can execute. The checklist
  engine does not need those rules to be useful today; the enterprise backend is ready for them
  when they are verified."*

### If the demo breaks

| Failure | Recovery line | Action |
|---|---|---|
| Backend asleep / red chip | "Free hosting cold start — give it a moment." | Retry validation; keep talking |
| 500/network error | "That is the deployed API, not the logic; here is the same run exported earlier." | Open the saved CSV |
| PDF upload empty | "Scanned documents need OCR, which is not enabled." | Type the date manually |
| Someone clicks Vault | "That screen is from a build we have not merged; it is gated." | Return to Validate |

---

## 3. Detailed technical explanation for judges

**Problem formulation.** Given a required-document set `R`, a submitted set `S`, and expiry
dates `E`, produce a deficiency set `D = (R \ S) ∪ {d ∈ S | E[d] < today}` with per-item
evidence. This is decidable in O(|R|+|S|) and requires no model.

**Why not ML.** The decision is a set difference and a date comparison. A model would add
variance, hide the reasoning, and create a false impression of judgement. The valuable
"intelligence" is the mapping from deficiency to clause and mitigation, which is curated
knowledge, not inference.

**Contract design.** `POST /api/v1/validate` returns `status`, `validation_scope`,
`missing_documents`, `expired_documents`, `findings[]`, `checked_at`, `source`, `notice`.
`validation_scope` is a `Literal` — clients cannot receive a result without being told the scope.
Evidence objects are code-specific (`MISSING_DOCUMENT` carries `{source, observed}`;
`DOCUMENT_EXPIRED` carries `{source, expiry_date, evaluation_date}`), so an auditor can
reconstruct the decision.

**Enterprise pipeline (repository, not deployed to the public site).** Uploads are validated by
magic bytes, size (10 MiB), page count (50), pixel count (30 MP) and encryption state; stored
under opaque keys; scanned by ClamAV (fail-closed; unavailable scanner means quarantine, never
"clean"); parsed with `pdfplumber` or optional Tesseract; fields carry confidence; validation
runs eight check families including expiry, date order, institution identity, cross-document
consistency, duplicate hashes, cross-institution reuse, confidence, and statutory rules; results
persist with `consumed_version_ids` and `rule_snapshot` for reproducibility, plus audit events.

**Rule governance.** Rules are `RuleVersionDraft`s with source provenance, page/clause citation,
applicability, test cases (positive/negative/boundary/exception), and an approval record.
Activation is blocked unless provenance is verified with a 64-char SHA-256, an approval exists,
dates are coherent, and all four test categories are present. The six APH drafts ship
unverified and unapproved, so the engine correctly evaluates nothing.

**Security.** JWT HS256 with a ≥32-char secret enforced at startup, bcrypt hashes, 5 roles and
12 permissions, tenant isolation returning 404 for foreign resources, private file storage with
authorized downloads, SSRF allowlists for authority adapters, and no third-party document
processors.

**What is engineering vs configuration.** The comparison engine, cadre calculator, document
pipeline, rule gate and audit chain are engineering. Auth wiring, OCR installation, authority
credentials and rule verification are configuration/authorisation items, and they are the
remaining blockers.

---

## 4. Non-technical explanation for institutional users

> "Think of it as a pre-flight checklist for your AICTE file.
>
> You tell it the certificates AICTE asks for, the ones you have, and the dates on them. It
> tells you, in plain language, which ones are not there and which have expired. For each one it
> shows the rule that applies and the kind of letter or undertaking that usually fixes it. You
> can download the list and hand it to the principal or the consultant.
>
> It also checks your faculty numbers: for a given intake, how many professors, associate
> professors and assistant professors you should have, and how far your department is from that.
>
> It will not tell you that you are approved. It cannot check whether a certificate is genuine.
> It is a checklist assistant, and it says so on every screen — which is exactly what you want
> from a tool you show a committee."

---

## 5. What differentiates this from a document-upload website

| Typical upload portal | This project |
|---|---|
| Stores files, maybe runs OCR | Compares declared checklist and dates deterministically |
| "Success" means the upload completed | "Passed" means the two lists agree, and says so explicitly |
| No explanation of a gap | Clause, impact and mitigation undertaking per finding |
| No provenance | `checked_at`, `source`, `validation_scope`, version IDs, rule snapshot |
| Silent failures | Explicit `attention_required` vs `preliminary_checks_passed`, plus inconclusive states |
| Claims AI | Refuses to claim AI; ML would weaken reproducibility |
| Hand-waves authenticity | States it cannot verify authenticity and requires human review |
| Faculty ratio in a separate spreadsheet | Integrated cadre/FSR calculator with deficit register |

The differentiator is not the feature list; it is the **epistemics**: the system is designed to
tell you what it did not check.

---

## 6. Demo data sheet (all synthetic)

| Item | Value |
|---|---|
| Institution ID | `SYNTH-INST-001` |
| Application type | `eoa` |
| Required | `aicte_approval`, `mandatory_disclosure`, `land_use_certificate`, `fire_safety_certificate`, `building_occupancy_certificate` |
| Submitted | first three only |
| Expiry | `aicte_approval=2024-03-31`, `fire_safety_certificate=2025-12-31` |
| Expected | `attention_required`; missing = occupancy + fire; expired = approval; 3 findings |
| Cadre | intake 120, duration 4, FSR 20, P/AP/ATP = 0/2/18 → required 3/6/15, ratio 24.0 |

**Never present these as real institutional data.** The IDs and numbers are chosen to be
obviously synthetic.

---

## 7. Slide skeleton (6 slides)

1. **Problem**: two preventable deficiency types, discovered too late.
2. **Product**: one screen, input → findings → export (screenshot of the live result).
3. **Why deterministic**: same input, same output; no model; audit envelope.
4. **Architecture**: SPA → API → comparison / document pipeline → Postgres + audit.
5. **Scope discipline**: zero active rules until verified; fail-closed scanning; disclaimers.
6. **Status + roadmap**: what works, what is gated, what is next (auth, OCR, rules,
   authority verification).

For likely questions, see [FAQ_AND_INTERVIEW_QUESTIONS.md](FAQ_AND_INTERVIEW_QUESTIONS.md).
