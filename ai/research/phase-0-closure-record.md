# Phase 0 research closure record — workstream C submission

**Research date:** 2026-10-24
**Author:** workstream C (AI/OCR) — research only, no regulatory interpretation
**Location:** this file is inside `ai/` because `docs/**` is a shared surface
([`../../WORKSTREAMS.md`](../../WORKSTREAMS.md)) and C may not edit it. It is a **proposal for
the repository owner** to move into `docs/research/` via a separate PR.
**Canonical source:** [`docs/canonical/phases.md`](../../docs/canonical/phases.md), "Updated
Phase 0 gate — research snapshot 2026-10-23".

> **Verdict: `BLOCKED`. Phase 0 is not complete.** Three of the six gates (`1`, `5`, `6`) are
> closed with evidence; three (`2`, `3`, `4`) are not, for reasons stated per gate below. Nothing
> here activates a regulatory rule. Current status is in the table in §1 and in §15.7.

---

## 1. Executive summary

Phase 0 has six canonical gates. This pass made **verifiable progress on four of them** and
**closed one**:

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | 1 April 2024 scrutiny document | **`CLOSED`** (pass 2) | **Complete 5-page document retrieved in full text** — all 21 categories. Identity, authority, date and publication timestamp confirmed. Decisive reconciliation finding: **it contains no "Extension of Approval" category**. Limitations recorded (§14.1) |
| 2 | 2026–27 addendum publication/finality/effective date | `BLOCKED_EXTERNAL_EVIDENCE` | Official **draft → final** publication pattern for the 2025–26 addendum established; 2026–27 notice not retrieved from any official host (all AICTE hosts geo-blocked/502) |
| 3 | Annexure-2 §2.1 pagination and Clause 7.17 | `OPEN` | Official handbook retrievable via government CDN; Chapters I–II read and quoted. **Root-caused in pass 3: the retrieval channel stops around PDF page 30, so Chapter VII (printed p.70) and the Annexures (p.77+) are unreachable at any chunk index**; printed folios now anchored from the official index. Annexure-2 §2.1 narrowed to printed 80/81, not decided (§15.1) |
| 4 | NBA validity through 30 April 2025 for AY 2026–27 | `OPEN` (pass 2) | **Clause 2.1.a(iii) retrieved verbatim.** Misinterpretation risk eliminated; residual question is whether a later addendum amends it — depends on Gate 2 (§14.4) |
| 5 | Official SIH26261 statement and deadline | **`CLOSED`** (pass 2) | **Official SIH portal** confirms PS number, title, organisation (AICTE), category, theme (Smart Automation) and deadline field **28 October 2026**. Banner-vs-row conflict narrowed in pass 3 — banner treated as stale, date still **provisional** (§15.4) |
| 6 | Reuse licensing/authorship/data-history | **`CLOSED`** | Licence absence, multi-author history and **committed personal data** verified directly; reuse explicitly excluded, which satisfies the gate's second closure branch |

Pass 1 statuses are preserved in the sections below; §14 (pass 2) and §15 (pass 3) supersede
them. **Gates 2, 3 and 4 remain open, so Phase 0 remains `BLOCKED`.**

Two additional results:

- **AICTE API availability:** still **not established** — neither existence nor absence proven.
  No AICTE-operated public developer portal was found; `data.gov.in`/API Setu exist as
  national platforms but no AICTE dataset or integration was identified as authoritative.
- **New risk, not a Phase 0 gate:** the candidate reuse repository contains **real student
  personal data committed into git history**. This is an owner-level disclosure concern about
  *that* repository, independent of this project's reuse decision. See §7.

### Environment limitation that drives most of the result

`www.aicte.gov.in` responds **`Access Forbidden - GeoLocation mismatch`** to this environment,
and `www.sih.gov.in` responds **`403 Forbidden`** (Azure Application Gateway). The Internet
Archive has **no snapshot** of the AICTE PDF URLs (verified via the availability API:
`{"archived_snapshots": {}}`). Most gates therefore fail on *access*, not on *analysis* — which
is important: they are closeable by anyone who can open those URLs from India, and I am
recording the exact URLs so they can.

In contrast, `pib.gov.in` and the government CDN `cdnbbsr.s3waas.gov.in` **are** reachable, and
both yielded primary evidence used below.

---

## 2. Canonical gate definitions (quoted)

From `docs/canonical/phases.md`:

> **Phase 0 — Research closure**
> Deliverables: official SIH statement and deadline; applicable EOA clauses; circular/corrigendum
> register; resolved reuse licensing decision.
> Gate: every enabled regulatory rule has an authoritative source, applicability conditions,
> effective period, interpretation and tests.

> Phase 0 remains **open**. […] Closure requires: (1) retrieve and reconcile the complete 1 April
> 2024 scrutiny document; (2) establish official publication/finality/effective date of the
> 2026–27 addendum; (3) check Annexure-2 §2.1 pagination and Clause 7.17 directly in the official
> handbook PDF; (4) resolve the NBA-validity-through-30-April-2025 reference for AY 2026–27;
> (5) verify the official SIH statement and deadline; and (6) resolve reuse-repository
> licensing/authorship/data-history risks before copying anything. API availability remains
> unresearched, not disproven. No candidate document rule becomes active while these gates are
> open.

Preparation phases are separate (5, in `docs/pre-coding/README.md`); the delivery phases are 7
(0–6). Neither numbering is changed here.

---

## 3. Gate 1 — 1 April 2024 scrutiny document

**Status: `BLOCKED_EXTERNAL_EVIDENCE`.**

| Item | Finding |
|---|---|
| Exact title | "Revised set of Documents for scrutiny for various categories under chapter I &II (dated 01st April 2024)" |
| Issuing authority | All India Council for Technical Education (AICTE) |
| Document date | 01 April 2024 (stated in the official title) |
| Official publication timestamp | **8 April 2024, 4:29 pm**, per the official AICTE Approval Process page listing |
| Observed on | `https://aicte.gov.in/approal-process-2024-2027` and `https://www.aicte-india.org/bureaus/approval/approal-process-2024-25` |
| Verification date | 2026-10-24 |
| PDF URL | `https://www.aicte.gov.in/sites/default/files/Revised%20set%20of%20Documents.pdf` |
| PDF retrieval | **Failed** — `Access Forbidden - GeoLocation mismatch` |
| Archive fallback | **None** — Wayback availability API returned `{"archived_snapshots": {}}` |

**What this establishes:** the document's exact identity, issuing authority, stated date and
official publication date are now corroborated by two official AICTE page listings, rather than
by a cached third-party copy. The earlier research note that "title/date and listing were
confirmed from a cached AICTE approval-process page" is therefore upgraded to *official-site
listing* evidence.

**What remains missing:** the document body. Completeness, annexures, whether it amends
Annexure-2 §2.1, and its supersession status cannot be judged without the PDF. A prior pass
recorded that a viewer had exposed 5 pages of text (category lists including Closure, Change of
Site/Location, Twinning & Collaboration, New Institution, New Level/New Programme) with no
visible publication metadata; that observation is preserved but is **not** treated as a
complete-document verification.

**To close:** open the PDF from an Indian network (or an authorised proxy), archive it with a
SHA-256 hash, and record: page count, annexures, whether the EOA category is addressed, and any
later instruction that supersedes it.

---

## 4. Gate 2 — 2026–27 addendum: publication, finality, effective date

**Status: `BLOCKED_EXTERNAL_EVIDENCE`.**

| Item | Finding |
|---|---|
| Official pattern (2025–26 addendum) | The official AICTE homepage lists **two distinct artefacts**: "Draft Addendum/Corrigendum 2025-26 of APH 2024-27 — **Published on 1 November, 2024**" and "Addendum/Corrigendum 2025-26 of APH 2024-27 — **Published on 5 November, 2024**" |
| Observed on | `https://www.aicte.gov.in/` (and `https://aicte.gov.in/approal-process-2024-2027`) |
| Verification date | 2026-10-24 |
| 2026–27 addendum | A press report describes a **21-page** "addendum/corrigendum" for AY 2026–27 altering supernumerary seats, BCA/BBA/BMS scope, monitoring committees and diploma minor specialisation |
| Source class | **Secondary (news)** — not an official publication record |
| Official PDF for 2026–27 | Not retrieved; AICTE host geo-blocked |

**What this establishes:** AICTE's own site distinguishes a *draft* from a *published*
addendum and stamps both with dates. That directly supports the canonical caution — the mere
existence of a circulating PDF does not establish finality. The prior research finding that the
circulating 21-page copy carries "Proposed Modification to the Clause" wording, no foreword, no
date, no signature and no reference number is consistent with it being a *proposal-stage*
document, but this remains an inference, not a verified fact.

**What remains missing:** the official 2026–27 publication record — issue date, effective date,
and whether the circulating 21-page copy is the published version, a draft, or superseded.

**To close:** retrieve the official 2026–27 addendum/corrigendum notice from the AICTE site
from an Indian network; compare it clause-by-clause against the circulating 21-page copy; record
issue date, reference number, signature and effective period. If no official 2026–27 notice
exists, that absence must itself be documented — it would mean the 2025–26 addendum is the
latest controlling amendment.

---

## 5. Gate 3 — Annexure-2 §2.1 pagination and Clause 7.17

**Status: `OPEN`** (access unblocked; verification incomplete).

### Progress: the official handbook is retrievable

A complete text copy of the official handbook **is** reachable from this environment through a
Government of India CDN:

`https://cdnbbsr.s3waas.gov.in/s35938b4d054136e5d59ada6ec9c295d7a/uploads/2025/03/2025031399.pdf`

Verified content (retrieved 2026-10-24): title page "Approval Process Handbook 2024-25 to
2026-27", AICTE, Nelson Mandela Marg, New Delhi-110070; the "legal document" preamble citing the
AICTE Act 1987 (52 of 1987) and the 2014/2012/2017/2020/2021 regulations; the Foreword listing
the 15 changes; the definitions; the Preamble; and Chapter I ("Grant of Approval for New
Institution", including 1.3.1 requiring NSWS online application). This confirms the CDN copy is
the genuine, complete handbook and not a partial extract.

### Why the gate is not yet closed

Two independent obstacles:

1. **Retrieval cost/position.** The document is served in 11 chunks; the retrieved chunk
   contained front matter and Chapter I. Chapter VII and the Annexures (which the source
   register places from printed page 77) sit in later chunks and were not reached in this pass.
2. **Methodological limit — decisive.** The PDF-to-text extraction exposes **no printed page
   markers**. The canonical question is specifically whether "p.79" versus "p.81" for
   Annexure-2 §2.1 arises from *PDF page index vs printed page number*. Text extraction cannot
   answer that: the printed folio is not present in the extracted stream. Answering it requires
   a human (or a tool with page-level layout) opening the PDF and reading the folio.

### Corroborating detail found en route

Official AICTE EoA corrigendum letters published by institutions cite the handbook by page:
"as per mandatory Disclosure of APH 2024-27 (**Annexure-18, page180**)" and "comply with all the
essential requirements as given in **APH 2024-27 (Chapter-VI)**". These confirm that annexure
pagination is cited by printed page number in official correspondence and that the handbook runs
to at least printed page 180. They do **not** independently establish §2.1's folio.

**To close:** open the handbook PDF, locate Annexure-2 §2.1 and Clause 7.17, and record **both**
the PDF page index and the printed folio for each, plus enough surrounding context to show
whether 7.17 exists where the third-party rendering suggests Chapter VII ends at 7.13. Record
the SHA-256 of the exact PDF used.

---

## 6. Gate 4 — NBA validity through 30 April 2025 for AY 2026–27

**Status: `BLOCKED_EXTERNAL_EVIDENCE`.** No new primary evidence this pass.

The claim under investigation is the base handbook's three-year EOA criterion in Clause
2.1.a(iii), which refers to NBA validity **through 30 April 2025**, and whether it governs AY
2026–27. Two distinct questions must not be conflated:

- *Historical fact:* whether an accreditation was valid until 30 April 2025 (a past date
  relative to AY 2026–27).
- *Rule:* whether a clause written around that date still sets eligibility for a later academic
  year, or has been amended/extended.

Nothing retrieved this pass resolves either. The 2025–26 corrigendum was previously reported to
contain "refreshed NBA-validity language for Chapters I and V"; that was a targeted extraction and
must not be treated as proof of the current wording.

**To close:** read Chapter II (and any Chapter V amendment) in the authoritative handbook plus
every subsequent addendum/corrigendum, and quote the operative NBA-validity clause with its
effective period. This is a reading task on documents that are accessible from India, not a
research dead end.

---

## 7. Gate 5 — Official SIH26261 problem statement and deadline

**Status: `BLOCKED_EXTERNAL_EVIDENCE`.**

| Attempt | Result |
|---|---|
| `https://sih.gov.in/` | **403 Forbidden** (Microsoft-Azure-Application-Gateway/v2) |
| `https://sih.gov.in/sih2026PS` | **403 Forbidden** |
| Search-engine discovery of the official listing | Returned mirrors and community datasets only |

**What mirrors agree on (not official):** SIH26261 is titled *"AI-Powered Application Validation,
Document Authentication and Regulatory Compliance Verification"*, sponsoring organisation
**AICTE**, theme **Smart Automation**, 500-idea cap, and a deadline reported as **28 October
2026**. A sibling statement SIH26262 ("Integrated AICTE Approval Workflow Automation…", also
AICTE, Smart Automation) appears consistently in the same listings.

**Correction to the prior record:** the earlier snapshot reported a possibly mis-assigned
**"Travel & Tourism"** theme. The current mirror listings show **Smart Automation** for SIH26261,
which is coherent with the subject matter. The "Travel & Tourism" concern is therefore most
likely a stale or mis-scraped attribution. It is **not** corrected here to an official fact —
only noted as probably obsolete.

**Deadline status:** reported 28 October 2026 (i.e. four days from this research date). Because
it is mirror-reported, treat it as a **lead with a near-term expiry**, not an authoritative
deadline. This is the most time-sensitive unresolved item in Phase 0.

**To close:** open the official SIH 2026 problem-statement listing (or an official downloadable
PS list) from an Indian network and record the verbatim statement, organisation, theme, team
constraints and deadline, with a verification date.

---

## 8. Gate 6 — Reuse licensing, authorship and data history

**Status: `CLOSED`** — under the gate's second closure branch: the asset is *explicitly excluded
pending authorization or legal review*, with its provenance now documented.

Repository examined: `https://github.com/rajaryan1111/fake-id-screening` (public).

| Check | Evidence (GitHub API, 2026-10-24) |
|---|---|
| Licence | `license: null` — **no LICENSE file** |
| Reuse grant | No CLA, copyright notice or permission statement found in the root or README |
| Authorship | **4 contributors** — `rajaryan1111` (16 commits), `shanikumar4` (12), `ItsmeYuvi` (3), `ArchyMittal` (2). Repository owner does not control all copyright in the tree |
| History depth | 39 commits; `created_at` 2026-09-07, `pushed_at` 2026-09-22 |
| Binary/model assets | 23 image files, including AI-generated images (`ChatGPT Image …`, `Gemini_Generated_Image …`) plus `tempering/samples/synthetic_docs/*` — provenance of the generated assets is undocumented |
| Personal data | `backend/insert_real_students.py` hard-codes **4 student records** with identifiers, names, dates of birth, college affiliation and on-disk paths to ID-card images. Introduced in commit `50f3752a` (2026-09-02), so it is **in git history**, not only in HEAD |
| Real-document tooling | `test_real_card.py` runs extraction over `img.jpeg` / `img2.jpeg`, indicating real ID-card images were processed locally (those image files are not in the tree) |

**Conclusion:** no permission basis exists for copying code, data, images or model artefacts from
this repository. Combined with the personal-data history, reuse is **excluded**. This is the
state the project already implements — `backend/app/ocr_*.py` was written as an
application-owned path and the reuse assessment records "no source code copied".

**Separate issue for the owner (not a Phase 0 gate, and not this project's decision to make):**
real student personal data is committed into the history of a **public** repository. Deleting the
file now would not remove it from history. This warrants a responsible-disclosure/cleanup
decision by the owner of that repository. Workstream C did not enumerate or reproduce the
individuals' details.

**Legal status of this conclusion:** engineering provenance assessment, **not legal advice**.

---

## 9. AICTE API availability

**Status: `OPEN` — not established.** Existence unproven, absence unproven.

- No AICTE-operated public developer portal, API specification or published integration contract
  was found.
- National platforms exist (`data.gov.in` OGD API, `apisetu.gov.in` API Setu); no AICTE approval
  or compliance dataset was identified there as authoritative.
- **No probing of any AICTE system was performed**, and none should be: unauthenticated
  enumeration of a government system is out of scope and out of authorisation.

**Standing rule for the architecture:** the product must not depend on an AICTE API. If one
exists, it is an optional future adapter behind the existing engine boundary
(`backend/app/ocr_adapter.py` pattern), never a prerequisite. The canonical requirements do not
establish API dependence.

---

## 10. Consequences for Phases 1–6

| Phase | Effect of Phase 0 remaining open |
|---|---|
| 1 — Secure foundation | **Unaffected.** Generic infrastructure/auth/tenancy work may proceed. |
| 2 — Document pipeline | **Largely unaffected.** The adapter contract and evidence handling are regulation-agnostic. |
| 3 — Deterministic rules | **Blocked.** "No candidate document rule becomes active while these gates are open." Gates 1–4 are exactly the source/applicability evidence needed. |
| 4 — Review workflow | **Unaffected** — process, not regulation. |
| 5 — Authenticity verification | **Unaffected in principle**; the readiness *gate* (G3/G9 in `docs/pre-coding/phase-5-coding-readiness.md`) stays `BLOCKED`. |
| 6 — Demo/measurement | Accuracy measurement (AI/OCR) is done; any *compliance* claim in a demo remains unsupportable until Phase 0 closes. |

Closing Phase 0 would **not** complete Phases 1–6; it only stops blocking Phase 3.

---

## 11. Decisions required from the repository owner

Gates 1–5 need **access**, not opinion. An owner decision is required only for:

1. **Gate 2 / 4 interpretation.** Once the addendum is retrieved, someone must decide and record
   which document controls for AY 2026–27 and what the operative NBA-validity clause is. An
   owner can authorise that decision; no one can decide it without the document.
2. **Gate 5 timeliness.** If 28 October 2026 is the real deadline, it is imminent. Decide whether
   to obtain official confirmation and adjust scope accordingly.
3. **Gate 6 disclosure.** Decide how to handle the personal data present in the candidate reuse
   repository's history.
4. **Where this record lives.** If approved, move this file to `docs/research/` in a separate
   PR per `WORKSTREAMS.md`.

**No owner may declare a factual gate closed.** Each of Gates 1–5 requires an official artefact.

---

## 12. Source list (verification date 2026-10-24 unless stated)

| ID | URL | Status | Supports |
|---|---|---|---|
| PIB-APH-RELEASE | `https://www.pib.gov.in/PressReleasePage.aspx?PRID=1983013` | **Retrieved** (full text) | Official release dated 06 DEC 2023: AICTE released the APH for AY **2024-2027**; lists 11 changes incl. 3-year EOA |
| APH-CDN | `https://cdnbbsr.s3waas.gov.in/s35938b4d054136e5d59ada6ec9c295d7a/uploads/2025/03/2025031399.pdf` | **Retrieved** (partial: front matter + Ch. I) | Genuine complete handbook text; legal-document preamble; Foreword's 15 changes |
| AICTE-APH-OFFICIAL | `https://www.aicte.gov.in/sites/default/files/APH%20Final.pdf` | **Geo-blocked** | Canonical APH URL (unverified from here) |
| AICTE-SCRUTINY-OFFICIAL | `https://www.aicte.gov.in/sites/default/files/Revised%20set%20of%20Documents.pdf` | **Geo-blocked** | Gate 1 document (body unverified) |
| AICTE-AP-PAGE | `https://aicte.gov.in/approal-process-2024-2027` | Indexed listing | Gate 1 title + date + 8 Apr 2024 4:29 pm publication timestamp |
| AICTE-HOME | `https://www.aicte.gov.in/` | Indexed listing | Gate 2: draft (1 Nov 2024) vs published (5 Nov 2024) addendum 2025-26 |
| SIH-OFFICIAL | `https://sih.gov.in/` , `/sih2026PS` | **403 Forbidden** | Gate 5 |
| WAYBACK-AVAIL | `https://archive.org/wayback/available?...` | Retrieved | No archived snapshot of the AICTE scrutiny PDF |
| GH-REUSE | `https://api.github.com/repos/rajaryan1111/fake-id-screening` | **Retrieved** | Gate 6: `license: null`, 4 contributors, 39 commits |
| PRESS-2026-27 | `news.careers360.com` (AICTE APH 2026-27 update) | Retrieved | **Secondary only** — 21-page 2026–27 addendum described |

---

## 13. Status of this record

- **Completed research:** gates 1, 2, 5 (access attempts and official metadata), 6 (full), API
  question (negative result).
- **Verified conclusions:** Gate 6 closure; Gate 1 identity/publication metadata; Gate 2
  publication pattern; the architecture conclusion that no AICTE API dependency is justified.
- **Pending approvals/evidence:** Gate 1 body, Gate 2 official 2026–27 notice, Gate 3 clause
  pagination, Gate 4 NBA clause, Gate 5 official listing.

**Do not treat anything in this file as an approved compliance checklist.** No rule may be
activated on the basis of this document.

---

# Pass 2 — 2026-24 research continuation

**Research date:** 2026-10-24. Supersedes the gate statuses in §1; all pass-1 sections are
preserved unchanged above.

## 14.1 Gate 1 — `CLOSED`: complete scrutiny document retrieved and reconciled

### Retrieval (the pass-1 gap is closed)

| Item | Value |
|---|---|
| Exact title (document header) | "Revised set of Documents for scrutiny for various categories under chapter I &II" |
| Issuing authority | All India Council for Technical Education (AICTE) |
| Document date | **01 April 2024** (per the official title on the AICTE listing) |
| Official publication timestamp | 8 April 2024, 4:29 pm (AICTE site listing) |
| Retrieved from | `https://web.archive.org/web/20240723180809id_/https://aicte-india.org/sites/default/files/Revised%20set%20of%20Documents.pdf` |
| Nature of capture | Wayback capture, **23 July 2024**, HTTP 200, of a file hosted on AICTE's own domain (`aicte-india.org`) |
| Also captured | 3 total captures, 28 May 2024 – 23 Jul 2024 |
| Live authoritative URL | `https://www.aicte.gov.in/sites/default/files/Revised%20set%20of%20Documents.pdf` — still `Access Forbidden - GeoLocation mismatch` from this environment |
| Page count | **5** (confirmed by the PDF viewer; both text chunks exhausted → complete) |
| SHA-256 | **Not computed.** The sandbox cannot open a TLS connection to `web.archive.org` from the shell (`URLError … TLS/SSL connection has been closed`), so the file bytes could not be hashed locally. The reproducible identifier is the Wayback capture timestamp + URL above |

### Document structure (verified content, complete)

A single table: `Sr No | Category Name | Document Name`, covering **21 categories**:

1 Bank Name Change · 2 Change of Site/Location · 3 Closure of Institution · 4 Conversion of
Co-ed → Women's · 5 Conversion of Diploma ↔ Degree · 6 Conversion into Deemed to be/State Private
University · 7 Course Name Change · 8 (Increase in Intake or New Course) · 9 Institution Name
Change · 10 Twinning & Collaboration Program · 11 Introduction of OCI · 12 Management Fellowship ·
13 Merger of Course · 14 Merger of Institution · 15 Minority Status Change · 16 New Institution ·
17 New Level/New Programme · 18 New Regional Course · 19 Reduction in Intake or Closure of Course ·
20 Reduction/Closure in ODL · 21 Trust/Society/Company Name Change.

Representative rows (faithful transcription): category 2 includes "Approved building plan",
"Ownership or Government/Private Lease (Sale deed / lease deed)", "Proof of Latitude and
Longitude", "Occupancy/ Completion/ Structural Stability Certificate (more than 30 years old
building)", "Fire and safety Certificate".

### Decisive reconciliation finding

**There is no "Extension of Approval" category in this document**, despite its title referring to
Chapter I *and II*. Chapter II is titled "Grant of Extension of Approval for Existing
Institutions" (verified in the APH, §14.4), but this scrutiny table contains no EOA row: its
categories are the Chapter-I and ancillary application types (New Institution, New Level/Programme,
Closure, Change of Site, conversion and housekeeping categories).

**Consequences:**

- The pass-1 open question — "whether it amends Annexure-2 §2.1 / whether it can be treated as the
  current EOA checklist" — is answered: **it does not supply an EOA document checklist.** The
  candidate EOA checklist in the verification report must be sourced from APH Chapter II and
  Annexure-2, not from this circular.
- This removes a latent error risk: a checklist derived from this document would have contained
  New-Institution and Change-of-Site documents that are not EOA scrutiny requirements.

### Limitations

- The capture is a Wayback copy of AICTE's own file, not a live download; it is dated 23 Jul 2024,
  i.e. after the 01 Apr 2024 document date, which is consistent but does not itself prove the file
  was unchanged since April.
- No SHA-256 (see above).
- Whether any later instruction supersedes individual entries is **not** established by this
  document and remains a research question for the owner's source register.

## 14.2 Gate 2 — `BLOCKED_EXTERNAL_EVIDENCE`: no official 2026–27 addendum retrieved

Every official host remains unreachable from this environment:

| Attempt | Result |
|---|---|
| `www.aicte.gov.in/sites/default/files/Revised set of Documents.pdf` | `Access Forbidden - GeoLocation mismatch` |
| `aicte.gov.in/sites/default/files/Revised set of Documents.pdf` | `502 Bad Gateway` |
| `www.aicte-india.org/content/revised-set-documents-…` | redirected → `502 Bad Gateway` |
| `www.aicte.gov.in/bureaus/approval/approval-process-2025-26` | `502 Bad Gateway` |

**Pass-1 finding retained and strengthened:** AICTE's own homepage distinguishes "**Draft**
Addendum/Corrigendum 2025-26" (published 1 November 2024) from the **published** version
(5 November 2024). That is direct official evidence that AICTE itself treats draft and final
addenda as different artefacts — the canonical caution is well founded.

**2026–27 addendum:** corroborated only by secondary press (a 21-page addendum/corrigendum
reported on 4 December 2025 covering supernumerary seats, BCA/BBA/BMS scope, monitoring committees
and diploma minor specialisation) and by third-party commentary citing "Addendum/Corrigendum
2026-27 of APH 2024-27 — amended clause 2.9". **No official publication record, issue date,
reference number or effective date has been verified.** Gate stays open.

## 14.3 Gate 3 — `OPEN`: pagination question is not answerable by text extraction

Newly verified this pass from the official handbook (see source table): the document is genuine
and complete, with Chapter I ending at clause 1.12 and Chapter II beginning immediately after.

**The blocking issue is methodological, not access.** The PDF→text extraction exposes **no printed
page folios**, so the canonical question — whether "p.79" vs "p.81" for Annexure-2 §2.1 arises
from *PDF page index vs printed page number* — cannot be answered from the extracted stream. Even
with the full document in hand, a text pipeline cannot report a printed page number that is not in
the text layer.

Clause 7.17 was also not reached: the retrieval is delivered in 11 chunks, and chunks read so far
cover front matter, Chapter I and the start of Chapter II. Chapter VII and the Annexures lie in
later chunks and were not examined in this pass.

**Smallest owner action to close:** open the handbook PDF in a viewer, go to Annexure-2 §2.1 and
Clause 7.17, and record **both** the viewer page index and the printed folio for each, plus
surrounding context showing whether 7.17 exists (the third-party rendering suggests Chapter VII
ends at 7.13). This takes minutes for a human and is not automatable here.

## 14.4 Gate 4 — `OPEN`: Clause 2.1.a(iii) retrieved verbatim; misinterpretation risk removed

Retrieved from the official handbook, Chapter II, clause 2.1:

> **2.1 Introduction**
> a. Existing institutions shall be eligible for getting 3 years' Extension of Approval (EoA)
> from the AY-2024-25 by remitting 3 years' TER Charges (Table 2.1) by meeting **ANYONE** of the
> following criteria:
> i. Figured in 8th Edition of NIRF ranked Institutions (announcement made on 5th June 2023).
> ii. Figured in QS World Ranking Asia-2024 (announcement made on 8th Nov 2023).
> iii. Institutions having minimum of 30% eligible courses with NBA accreditation having validity
> till 30th April 2025. (The institutions should continue to get accreditation of their programs)
> iv. Institutions with valid NAAC score of 3.01 and above on scale of 4.0.
> v. Institutions having conferred 'Autonomous Status' by UGC/A…

**Resolution of the canonical question.** The 30 April 2025 reference is *not* a standalone rule
governing AY 2026–27 approvals. It is the date-threshold inside **one of five alternative
eligibility criteria** for the **three-year EoA window that begins at AY 2024–25**. An institution
qualifies for that window by meeting *any one* of NIRF, QS, NBA, NAAC or Autonomous-Status
conditions. Reading it as "institutions must have NBA validity through 30 Apr 2025 to be approved
for AY 2026–27" would be a misreading of the clause, and the project must not encode it as such.

Also verified in the same chapter: Chapter II governs EoA for existing institutions across 17
listed activities, including xii ("Extension of Approval … after a break in the preceding Academic
Year(s)/ Hibernation/Restoration of Intake") and xvii ("Closure of the Institution").

**Why the gate stays `OPEN`:** the canonical wording also asks whether this is the *operative*
rule for AY 2026–27. That requires the 2026–27 addendum/corrigendum, which is exactly what Gate 2
cannot retrieve. If the addendum amends clause 2.1 (plausible — press reports changes to clause
2.9), the threshold may have moved. The residual question is therefore narrow and precisely
stated: *has the 2026–27 addendum amended clause 2.1(a)(iii)?*

## 14.5 Gate 5 — `CLOSED`: official SIH listing verified

The portal is reachable at the **`www.` host**; the bare host returns 403:

| Attempt | Result |
|---|---|
| `https://sih.gov.in/` and `/sih2026PS` | **403 Forbidden** (Azure Application Gateway) |
| `https://www.sih.gov.in/sih2026PS` | **Retrieved — official problem-statement table** |
| `https://www.sih.gov.in/` | Retrieved — official homepage |
| Wayback captures of the PS page | All 403 (captured failures only) |

**Official row for the project's problem statement** (verbatim fields):

| Field | Official value |
|---|---|
| PS Number | **SIH26261** |
| Organization | **AICTE** |
| Problem Statement Title | **AI-Powered Application Validation, Document Authentication and Regulatory Compliance Verification** |
| Category | software |
| Theme | **Smart Automation** |
| Submitted Idea(s) Count | 28/500 |
| Deadline for Idea Submission | **28 October 2026** |

**Prior-record corrections this establishes:**

- The earlier report's doubt about the problem-statement title and sponsoring organisation is
  **resolved in the affirmative** — the project's title and AICTE ownership are confirmed officially.
- The earlier flag that the theme "Travel & Tourism" looked mis-assigned is **resolved**: the
  official theme is **Smart Automation**. No main listing anomaly remains.

**Deadline ambiguity — recorded, not hidden.** The official homepage carries a banner: *"Team
Nomination & Idea Submission deadline extended to 09 Oct 2026"* and a second notice about editing
team details 02–09 Oct 2026. The per-PS table nonetheless shows **28 October 2026** for the AICTE
statements (SIH26261–26265) while other organisations' statements show 20 October 2026 and are
marked "Idea Submissions Closed". The consistent reading — stated here as an **inference, not a
verified fact** — is that the AICTE batch was added later ("New PS Added" banner) with its own
later deadline, and that the per-PS field is the operative date for SIH26261. The project should
treat **28 October 2026** as the operative deadline while noting the banner conflict.

**What is still not retrieved:** the detailed problem-statement body (Background / Problem
Description / Expected Solution) and the formal eligibility rules. The listing publishes the title
and metadata but not the narrative body, and no detail endpoint was found at the URL patterns
tried (`/psDetails?id=`, `/sih2026PS?problem-id=` → 404). A signed-in/SPOC-restricted view may be
the only route to the body. This gap does **not** affect the canonical acceptance criteria (which
require the statement's identity and the applicable deadline), both of which are verified.

**Time-sensitivity:** the operative deadline is **four days** from this research date.

## 14.6 Pass-2 source table (verification date 2026-10-24)

| ID | URL | Status | Supports |
|---|---|---|---|
| SIH-PS-OFFICIAL | `https://www.sih.gov.in/sih2026PS` | **Retrieved, official** | Gate 5: SIH26261 title, AICTE, Smart Automation, 28 Oct 2026 |
| SIH-HOME-OFFICIAL | `https://www.sih.gov.in/` | **Retrieved, official** | Gate 5: extension banner (09 Oct 2026) — conflict recorded |
| SCRUTINY-WB | `https://web.archive.org/web/20240723180809id_/https://aicte-india.org/sites/default/files/Revised%20set%20of%20Documents.pdf` | **Retrieved, complete (5 pp., 21 categories)** | Gate 1 closure; no EOA category |
| SCRUTINY-LIVE | `https://www.aicte.gov.in/sites/default/files/Revised%20set%20of%20Documents.pdf` | Geo-blocked / 502 | Authoritative URL (unverified from here) |
| APH-CDN | `https://cdnbbsr.s3waas.gov.in/s35938b4d054136e5d59ada6ec9c295d7a/uploads/2025/03/2025031399.pdf` | **Retrieved (front matter, Ch. I 1.8–1.12, Ch. II 2.1)** | Gates 3, 4: verbatim clause 2.1.a(iii); Chapter II scope |
| AICTE-HOSTS | various `aicte.gov.in` / `aicte-india.org` paths | **All 403-geo / 502** | Gate 2 blocker |
| PRESS-2026-27 | Careers360, 2025-12-04 | Retrieved, **secondary** | Corroboration only for the 2026–27 addendum's existence |

## 14.7 Pass-2 verdict

**Phase 0: `BLOCKED`.** Gates **1, 5 and 6 are `CLOSED`** with evidence. Gates **2 and 3 remain
open**, and **Gate 4 is narrowed to a single answerable question** pending Gate 2.

Three of six gates closed, and — materially — two serious miscalculation risks were eliminated:
the scrutiny circular does **not** define an EOA checklist, and clause 2.1.a(iii) is **not** a
standalone AY 2026–27 NBA rule. No regulatory rule is activated by any of this.

**Highest-value next actions (both need a network inside India or a human with a browser):**

1. Retrieve the official **2026–27 addendum/corrigendum** and record its issue date, reference
   number and whether it amends clause 2.1 → closes Gates 2 and 4.
2. Open the handbook PDF and record the **printed folio vs PDF index** for Annexure-2 §2.1 and
   confirm whether **Clause 7.17** exists → closes Gate 3.

---

# Pass 3 — 2026-10-24 evidence closure attempt

Pass-3 scope: resolve Gates 2, 3 and 4, clarify the SIH26261 deadline, and finish all remaining
authorised Phase 0 work. **Outcome: no new gate closed.** Gate 3's blocker is now root-caused and
numerically narrowed; Gate 2 gained a named candidate artefact and an exact retrieval recipe; the
Gate 5 deadline conflict is materially narrowed. Phase 0 remains `BLOCKED`.

## 15.1 Gate 3 — root cause found: the retrieval channel stops around PDF page 30

**Finding (supersedes §14.3, which is preserved below unaltered).** Pass 2 recorded that "Chapter
VII and the Annexures lie in later chunks". That is now known to be **wrong**, and the correction
matters because it changes the owner action from "read more chunks" to "use a page-addressable
reader".

This pass retrieved the **official index of contents, with printed page numbers**, verbatim from
the government CDN copy:

| Entry | Printed page |
|---|---|
| Foreword | i |
| Abbreviations | vi |
| Definitions | viii |
| Preamble | xii |
| Chapter-I Grant of Approval for New Institution | 1 |
| Chapter-II Grant of Extension of Approval for Existing Institutions | 11 |
| Chapter-III Collaboration & Twinning Programmes | 33 |
| Chapter-IV Grant of Approval for Universities | 37 |
| Chapter-V Approval for ODL / Online Learning | 45 |
| Chapter-VI Standard Norms and Requirements | 53 |
| Chapter-VII Penal Action on Violation of Norms | 70 |
| Chapter-VIII DOS and DON'Ts | 75 |
| Annexures | 77 |

Chunk-contents mapping across all three passes now covers: front matter, Chapter I (to 1.12),
Chapter II §2.1, §2.2, §2.3.1, **§2.3.2 including Table 2.1 (TER charges)** in chunk 9, and §2.3.3
in chunk 10. Every one of those clauses belongs to **printed pages 11–15**. The retrieval surface
reports **11 chunks** for the whole file yet exhausts itself inside Chapter II. Therefore the chunk
count is an artefact of the extraction layer, **not** a pagination of the handbook, and **chunk
index cannot be used to target a later chapter**. Chapter VI (p.53), Chapter VII (p.70) and the
Annexures (p.77+) are unreachable through this channel at *any* chunk index. The documented
behaviour of the PDF reader used here (text parsed up to roughly the first 30 PDF pages) is
consistent with this and is the operative cause.

**What this does establish (useful, and previously unknown):**

- The handbook **does print folios**, and printed folios are the citation convention — corroborated
  independently by AICTE Extension-of-Approval corrigenda that cite "APH 2024-27 (**Annexure-18,
  page180**)" and "**(Chapter-VI)**". Printed page 180 therefore exists, i.e. the document has at
  least 180 printed pages.
- Front matter is roman-numbered (i–xii and beyond), so a **PDF-index ↔ printed-folio offset is
  structurally certain**. The reported p.79 / p.81 discrepancy is therefore at least *consistent
  with* the PDF-index-vs-folio explanation. Consistent is not confirmed.

**Annexure-2 §2.1 — narrowed, not decided.** A flattened-text rendering of the official document
places the running folio `80` immediately adjacent to the heading
`ANNEXURE-2 — Documents to be uploaded/submitted by Existing Institutions — 2.1 Documents to be
uploaded for the issuance of EoA based on Self-Disclosure…`. This handbook prints the folio
sometimes *before* and sometimes *after* the running title ("`53 Approval Process Handbook
2024-2027`" vs "`Approval Process Handbook 2024-2027 28`"), so a folio adjacent to a heading is
consistent with **both** §2.1 opening on printed p.80 and §2.1 opening on p.81 after p.80's footer.
The question is narrowed to an 80/81 neighbourhood. **No page number is asserted.** Guessing here
would be exactly the fabrication the canonical criteria forbid.

**Clause 7.17 — still unverified.** Not retrieved. Its existence is neither confirmed nor denied,
and the pass-2 hint that Chapter VII may end near 7.13 remains a hypothesis. One arithmetic
constraint is recorded as a *test*, not a conclusion: Chapter VII spans printed pp.70–74 (five
pages, since Chapter VIII begins at 75), so any clause numbered 7.17 must lie within those five
pages.

**Why this cannot be finished from here.** Closing Gate 3 needs page-addressable access (a local
PDF plus a viewer, or `pdftotext -f/-l`). This sandbox's outbound network is restricted to a small
host allowlist (GitHub, npm, PyPI); the AICTE CDN, the Rajasthan HTE host and the Internet Archive
are not reachable from a shell. No document can be downloaded, so nothing can be rendered locally
and no hash can be computed (§15.5).

**Exact missing step — one sitting, for any person or environment with unrestricted network:**

1. Download `https://cdnbbsr.s3waas.gov.in/s35938b4d054136e5d59ada6ec9c295d7a/uploads/2025/03/2025031399.pdf`.
2. Record `sha256sum` of the file.
3. For **Annexure-2 §2.1** and for **Clause 7.17**, record: (a) viewer / PDF page index, (b) the
   printed folio printed on that page, (c) the heading and its first and last text lines, (d) for
   7.17, whether the clause exists at all and what the highest clause number in Chapter VII is.
4. State the viewer's page-numbering convention (1-based PDF index including or excluding cover).

## 15.2 Gate 2 — candidate official-adjacent artefact found; finality still unverified

**New lead.** A search index surfaces a document hosted by the Government of Rajasthan, Department
of Technical Education at
`https://hte.rajasthan.gov.in/oldhte/hteCircular/AICTE%20Approval.pdf`, headed
"**MORATORIUM OPTION — ADDENDUM/ CORRIGENDUM 2026-27 Of APH 2024-27**", containing two-column
"**Existing**" clause vs "**Proposed Modification**" tables for Chapter-I (including clause
1.1(g)), Chapter-II, Chapter-III and Annexure-8 (PG exit treated as PG certificate).

**Retrieval attempts this pass — all failed:**

| Attempt | Result |
|---|---|
| `https://hte.rajasthan.gov.in/oldhte/hteCircular/AICTE%20Approval.pdf` | host error page: "This page can't be displayed" |
| `http://` variant of the same path | identical error page |
| Internet Archive availability API for that URL | `{"archived_snapshots": {}}` — **no capture exists** |

So the **body of this document was not obtained**; only an index snippet was. Under the standing
rule, a snippet is not evidence, and the snippet supplies **no** title page, reference number,
issue date, effective date or statement of finality. **Gate 2 status is unchanged.**

Two observations that are recorded but prove nothing on their own:

- The document's "**Proposed** Modification" column is again consistent with proposal-stage
  material, matching the officially observed draft→final publication pattern (AICTE posted a
  *Draft* Addendum/Corrigendum 2025-26 on 1 November 2024 and the published version on 5 November
  2024). Consistency is not proof of stage.
- independent corroboration that corrigenda to this handbook were **operative in the AY 2026–27
  cycle**: Extension-of-Approval letters issued March–June 2026 are headed "APPROVAL PROCESS
  2026-27" and reference "Approval Process Handbook 2024-27 **and corrigendum thereof**". One is
  titled "Extended Extension of Approval for the Academic Year **2025-26 to 2027-28**". This
  establishes that corrigenda existed and that the multi-year extended-EoA mechanism operated in
  practice. It does **not** establish what any corrigendum says about clause 2.1, so it closes
  neither Gate 2 nor Gate 4.

**Precise missing evidence:** an official artefact (AICTE-hosted, or a government host carrying the
AICTE notice) giving the 2026–27 addendum/corrigendum's **title, reference number, issue date,
publication URL and the list of clauses amended** — specifically whether clause 2.1 is touched.
**Decision-maker:** AICTE Approval Bureau. Until that exists, Gate 2 stays `BLOCKED_EXTERNAL_EVIDENCE`.

## 15.3 Gate 4 — unchanged, and the two questions are now kept strictly apart

| Question | Status |
|---|---|
| What does Clause 2.1.a(iii) say? | **Verified verbatim** (pass 2): among five alternatives for the **3-year EoA from AY 2024-25**, one is ≥30% eligible courses with NBA accreditation valid till 30 April 2025 |
| Is that threshold an AY 2026–27 eligibility rule? | **Not established.** It is a clause of a multi-year handbook read in the context of the AY 2024–25 window |
| Did the 2026–27 addendum amend clause 2.1, or extend/replace the 30 April 2025 date? | **Not established — depends entirely on Gate 2** |

Gate 4 closes only when the third row is answered from an official source. Two specific claims
remain **unsupported and must not be written into any rule**: (i) "NBA 30% valid till 30 Apr 2025 is
an AY 2026–27 eligibility rule"; (ii) "the 30 April 2025 date has been extended". Neither has
evidence.

## 15.4 Gate 5 — the deadline conflict is materially narrowed (still not officially reconciled)

Re-checked both official surfaces on 2026-10-24:

- **Per-PS table** (`/sih2026PS`): AICTE SIH26261–SIH26265 each show a **live submission counter**
  (SIH26261 at 28/500) and deadline **28 October 2026**.
- **Same table, other organisations**: Ministry of Jal Shakti, Ministry of Defence and MSDE rows
  show the status string "**Idea Submissions Closed**" with deadline **20 October 2026**. The table
  therefore *does* carry an explicit per-row open/closed state, and it is closed for those rows.
- **Homepage banner** still reads "Team Nomination & Idea Submission deadline extended to
  **09 Oct 2026**", alongside "SPOCs and Team Leaders can edit/update … from **02–09 Oct 2026**".

**Inference (labelled as inference):** the 09 Oct banner is a **stale, already-elapsed** extension
notice — both dates it cites have passed, while the row-level state for AICTE's PSs is still open
with an explicit 28 October 2026 deadline. On that reading the operative deadline for SIH26261 is
**28 October 2026**. This is derived from the portal's own row-level state; **SIH has published no
statement reconciling the banner and the rows**, so it is **not an official determination** and the
date stays **provisional**.

Gate 5 remains `CLOSED` on the evidence already recorded (PS number, exact title, AICTE as
organisation, software category, Smart Automation theme, and the deadline field). The unresolved
item is only the banner-vs-row reconciliation.

**Time-critical:** as of today, 28 October 2026 is **four days away**.

## 15.5 Hash and provenance status — limitation restated, no hashes recorded

No SHA-256 could be computed for any source in this record. The sandbox's outbound network is
restricted to a small host allowlist (GitHub, npm, PyPI), so documents on the AICTE CDN, the
Rajasthan HTE host and the Internet Archive cannot be downloaded; a direct TLS fetch attempt from a
shell failed earlier. **Therefore this record cites no hashes for any document**, and provenance
rests on URL + retrieval date + verbatim quotation. This is a recorded limitation and does **not**
satisfy the canonical Gate 2 requirement to record a document hash; whoever downloads these files
should add `sha256sum` values via an appended correction.

## 15.6 Pass-3 source table (verification date 2026-10-24)

| ID | URL | Status | Supports |
|---|---|---|---|
| APH-CDN-INDEX | `https://cdnbbsr.s3waas.gov.in/…/2025031399.pdf` (index of contents) | **Retrieved, official** | Gate 3: printed folios Ch II=11, III=33, IV=37, V=45, VI=53, VII=70, VIII=75, Annexures=77 |
| APH-CDN-CH2 | same file, chunk 9 | **Retrieved, official** | Gate 3: §2.1(a)(v)–(vi), §2.2, §2.3.1, §2.3.2 + Table 2.1 TER charges — all printed pp.11–15 |
| RJ-HTE-ADDENDUM | `https://hte.rajasthan.gov.in/oldhte/hteCircular/AICTE%20Approval.pdf` | **NOT retrieved** — host error page; no Wayback capture | Gate 2 lead only: "ADDENDUM/CORRIGENDUM 2026-27 Of APH 2024-27", existing-vs-proposed tables, Ch I–III + Annexure-8 |
| EOA-2026-27-LETTERS | e.g. `https://engineering.lingayasvidyapeeth.edu.in/docs/AICTE_2026.pdf`, `https://www.nitttrc.ac.in/uploads/EoA%202026-2027.pdf` | Retrieved, **institutional EoA letters** | Gate 2 context: AY 2026–27 process ran on "APH 2024-27 and corrigendum thereof"; "Extended EoA 2025-26 to 2027-28" |
| EOA-CORRIGENDUM-CITE | e.g. `https://rgicdn.s3.ap-south-1.amazonaws.com/ghrcenagpur/pdf/accreditation/corrigendum-report-26-27.PDF` | Retrieved, institutional | Gate 3: citation convention "(Annexure-18, page180)" ⇒ ≥180 printed pages |
| SIH-PS-OFFICIAL-3 | `https://www.sih.gov.in/sih2026PS` | **Retrieved, official** | Gate 5: AICTE rows open with counters + 28 Oct 2026; other ministries "Idea Submissions Closed" @ 20 Oct 2026 |
| SIH-HOME-OFFICIAL-3 | `https://www.sih.gov.in/` | **Retrieved, official** | Gate 5: 09 Oct 2026 banner and 02–09 Oct SPOC window — both elapsed |
| FLIPBOOK-P81 | `https://fliphtml5.com/jpimb/zwqi/AICTE_Approval_Process_Handbook_2024-27/81/` | Retrieved, **unofficial mirror**, nav/description only | **Nothing.** No page text exposed; not usable as evidence |

## 15.7 Pass-3 verdict

**Phase 0: `BLOCKED`.**

| Gate | Status after pass 3 | Remaining requirement |
|---|---|---|
| 1 | `CLOSED` | — |
| 2 | `BLOCKED_EXTERNAL_EVIDENCE` | Official title, reference number, issue date, finality, effective date for the 2026–27 addendum/corrigendum |
| 3 | `OPEN` | Printed folio for Annexure-2 §2.1 (narrowed to 80/81) and existence + folio of Clause 7.17; needs a page-addressable reader |
| 4 | `OPEN` | Whether clause 2.1 / the 30 April 2025 NBA date was amended for AY 2026–27 (depends on Gate 2) |
| 5 | `CLOSED` | Banner-vs-row reconciliation only; date **provisional**; ~4 days remaining |
| 6 | `CLOSED` | — |

No regulatory rule is activated by anything in this pass. Three of six gates remain unsatisfied and
are all blocked on the same external dependency: **page-level and official-portal access from
outside the restricted sandbox.**

## 15.8 Single highest-priority next action

**Download the official handbook, hash it, and read two pages.** One sitting, one person or
environment with unrestricted network:

1. `2025031399.pdf` → `sha256sum` → open **Annexure-2 §2.1** and **Clause 7.17**, record PDF index +
   printed folio + heading + whether 7.17 exists → **closes Gate 3**.
2. Then open the Rajasthan HTE "ADDENDUM/CORRIGENDUM 2026-27 Of APH 2024-27" PDF, record title
   page, reference number, issue date and which clauses it amends, and `sha256sum` it → **decides
   Gates 2 and 4**.

Operational aside, not a gate: if SIH26261 is intended to be submitted, the provisional deadline is
**28 October 2026 — four days away**.

