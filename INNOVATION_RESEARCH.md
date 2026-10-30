# Innovation Research — What Institutions Actually Need

Scope: the AICTE Compliance AI repository (public site + repo backend), audited on 2026-10-30.
No competitor claim is made here; this is a problem-first analysis of our own users.

---

## 1. Who we are actually serving

| User | Situation | What they do today |
|---|---|---|
| Compliance officer at a 3,000-student private college | Owns the EoA file; no legal team | Maintains a spreadsheet of certificates and expiry dates |
| Principal / Director | Signs the submission | Discovers gaps in the scrutiny letter, after submission |
| Trust / finance officer | Owns FDR, land papers | Sends scanned PDFs over WhatsApp |
| Small institution ( <5 programmes) | No dedicated compliance staff | Relies on a consultant who serves 20 colleges |
| Scrutiny officer (AICTE/RO) | Receives incomplete files | Sends deficiency letters that repeat the same categories |

The common failure is not "we cannot read a PDF". It is **"we did not know which paper was
missing or expired until someone rejected the file"**.

## 2. Observed failure modes in our own product

Audited in the deployed app and the repository:

1. **Silent expiry gaps.** `POST /api/v1/validate` compares `expiry_dates` keys against
   `submitted_documents` by exact string. If a user types a display label while the document list
   uses an ID (or vice versa), the date is silently ignored and the run can return
   `preliminary_checks_passed` with an expired certificate. Reproduced live on 2026-10-30.
2. **Dead statutory lookups.** `APH_CLAUSE_CATALOG` is keyed by display labels
   (`"Fire Safety Certificate"`), but the form and presets send IDs
   (`fire_safety_certificate`). Every lookup misses, so impact and mitigation text is generic.
3. **Opaque score.** The readiness number is presented as "Nil-Deficiency Probability" with no
   derivation. Users cannot see why it moved, so they cannot trust or act on it.
4. **Findings are terminal.** A finding tells you what is wrong. It does not become a task with
   an owner, a deadline, the evidence that closes it, or a status.
5. **English-only regulatory language.** Most compliance staff in aided and rural institutions
   read Hindi more comfortably than English regulatory prose, but the guidance is English-only.

## 3. Candidate ideas evaluated

| Idea | Real problem | Feasible now | Verdict |
|---|---|---|---|
| Corrective action plan with owners, deadlines, evidence, progress | Findings do not turn into work | Yes — client-side, no schema change | **Selected** |
| Transparent readiness basis (fix + explain score) | Opaque, currently wrong number | Yes | **Selected** |
| Bilingual deficiency guidance | English-only regulatory prose | Yes — curated strings | **Selected** |
| Regulatory change impact analyzer | Handbook versions change | Needs verified handbook versions we do not have | Deferred |
| Document authenticity / tamper detection | Forged certificates | No reliable signal; would mislead | Rejected |
| LLM document assistant | Extraction from arbitrary scans | No verified model, OCR not deployed | Rejected |
| Duplicate / cross-document consistency | Conflicting documents | Already implemented in the repo backend | Not duplicated |
| Server-side team workflow | Multi-user task assignment | Requires working auth + DB in production | Deferred |
| Hindi UI translation of the whole app | Accessibility | Large surface, low marginal value vs guidance | Partial |

## 4. What we deliberately did not build

- **No chatbot.** A compliance question needs a citation, not a fluent paragraph.
- **No new score.** The existing score is repaired and explained; a second index would add noise.
- **No AI authenticity claim.** An explainable indicator set without validation would be worse
  than no indicator.
- **No new backend endpoint or table.** The three selected features are deterministic functions
  over data the browser already has, so they cannot break the API contract or the deployed
  backend, and they work for signed-out users — the only mode that currently works in production.

## 5. Constraints accepted

1. The production frontend is built from a revision that is not identical to this repository
   (it contains a `/vault` page absent here). These features are implemented in this repository
   and require a normal frontend deployment to appear in production.
2. Sign-in is not functional in the deployed site, so plans are stored **in the browser** and
   exported as CSV. This is stated in the UI, not hidden.
3. Clause citations come from the existing catalog, which is **unverified against the APH PDF**.
   Every guidance surface says so and links the requirement to human verification. Documents
   without a catalog entry show no clause rather than an invented one.
