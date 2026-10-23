# Phase 0 research closure record — workstream C submission

**Research date:** 2026-10-24
**Author:** workstream C (AI/OCR) — research only, no regulatory interpretation
**Location:** this file is inside `ai/` because `docs/**` is a shared surface
([`../../WORKSTREAMS.md`](../../WORKSTREAMS.md)) and C may not edit it. It is a **proposal for
the repository owner** to move into `docs/research/` via a separate PR.
**Canonical source:** [`docs/canonical/phases.md`](../../docs/canonical/phases.md), "Updated
Phase 0 gate — research snapshot 2026-10-23".

> **Verdict: `BLOCKED`. Phase 0 is not complete.** One of the six gates can be closed; five
> cannot, for reasons stated per gate below. Nothing here activates a regulatory rule.

---

## 1. Executive summary

Phase 0 has six canonical gates. This pass made **verifiable progress on four of them** and
**closed one**:

| # | Gate | Status | Change in this pass |
|---|---|---|---|
| 1 | 1 April 2024 scrutiny document | `BLOCKED_EXTERNAL_EVIDENCE` | Title, date and publication timestamp **confirmed from the official AICTE site listing**; PDF body still unreachable |
| 2 | 2026–27 addendum publication/finality/effective date | `BLOCKED_EXTERNAL_EVIDENCE` | Official **draft → final** publication pattern for the 2025–26 addendum established from the official site; 2026–27 addendum existence corroborated only by press |
| 3 | Annexure-2 §2.1 pagination and Clause 7.17 | `OPEN` | **The official handbook is now retrievable in full text** via a government CDN (previously recorded as inaccessible); clause-level verification not completed |
| 4 | NBA validity through 30 April 2025 for AY 2026–27 | `BLOCKED_EXTERNAL_EVIDENCE` | Not located in retrieved text; no change |
| 5 | Official SIH26261 statement and deadline | `BLOCKED_EXTERNAL_EVIDENCE` | `sih.gov.in` returns **HTTP 403** to this environment on every path tried; mirror data only |
| 6 | Reuse licensing/authorship/data-history | **`CLOSED`** | Licence absence, multi-author history and **committed personal data** verified directly; reuse explicitly excluded, which satisfies the gate's second closure branch |

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
