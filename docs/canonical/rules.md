# Compliance Rules — Source-Governed Catalogue

**Status:** provisional policy; EOA checklist is not frozen.

## Rule admission gate
A rule may be activated only when the record includes:
- Stable rule ID (never reuse retired IDs).
- Title and plain-language explanation.
- Source document, issuer, version, URL, clause and page.
- Publication date, effective dates and supersession relationship.
- Application type, academic year and applicability conditions.
- Required inputs and their provenance.
- Deterministic logic and documented interpretation.
- Evidence requirements and limitations.
- Output status, severity and reviewer action.
- Positive, negative, boundary and exception tests.
- Reviewer/approver and review timestamp.

Rules without verified regulatory support must be labelled reasonable consistency checks, not statutory requirements.

**Implementation status (2026-10-22 audit):** `backend/app/rule_catalog.py` enforces the
provenance and approval parts of this gate. An activation requires a verified source
(document version, retrieval date, named reviewer and verification date), an
attributable approval record, an effective date and positive/negative/boundary/exception
tests. `RuleRegistry.activate` is the only transition to `ACTIVE` and refuses
caller-declared `ACTIVE`, unverified or unapproved rules. No AICTE rule is defined or
active, and no rule evaluator exists; the remaining admission-gate items above are still
policy, not code.

## Provisional status vocabulary
| Status | Meaning |
|---|---|
| passed | Deterministic local check passed for available inputs; not proof of authenticity. |
| mandatory_missing | A source-backed unconditional requirement is missing. |
| conditional_missing | A verified condition applies and its required document is missing. |
| trigger_unevaluable | Applicability cannot be determined from reliable inputs. |
| present_unreadable | File exists but extraction failed or was insufficient. |
| expired | Parsed validity date fails the approved validity rule. |
| inconsistent_fields | Extracted or normalized fields conflict. |
| authenticity_concern | Preliminary indicator fired; not proof of forgery. |
| verification_not_attempted | No external check was performed. |
| verification_unavailable | Authorized source was attempted but could not be reached. |
| verification_inconclusive | Source responded but did not resolve the question. |
| externally_verified | Authorized authoritative source returned a result supporting the exact recorded claim. |
| human_review_required | A human must resolve ambiguity or inspect evidence. |
| not_applicable | Verified rule does not apply to this application. |
| simulated | Demo-only result; never represent as a live external check. |

## Safety and interpretation
- A missing required document is a completeness finding, not a fraud finding.
- OCR text and confidence are observations, not proof the text is true.
- A hash identifies bytes; it does not prove authenticity.
- Metadata or visual anomalies are indicators only.
- A signature check reports cryptographic integrity/trust-chain facts, not substantive truth.
- A QR code resolving to a URL does not prove the destination is authoritative.
- Fuzzy name matching alone must not establish identity.
- An unreadable date must not be treated as a pass.
- An unevaluable condition must not silently become not applicable.
- No automated finding may make the final AICTE approval/rejection decision.

## Date policy
The expiry boundary and authoritative evaluation timezone remain unresolved in the research dossiers. Before activation, settle them from authoritative instructions or approve a clearly labelled product policy. Test the day before, exact boundary, day after, invalid date, missing date and ambiguous OCR date.

## Versioning and reproducibility
Each validation run records exact rule-version IDs and source versions. Rule edits create a new version; they never rewrite past runs. Re-uploading a file creates a new document version and validation run, preserving earlier evidence and findings.

## Research leads — not an activated checklist
The dossiers discuss Affidavit 2, TER payment receipt, building approval alternatives, structural stability, fire safety, satellite location maps, audited accounts, accreditation and other category-dependent documents. Because retrieval claims conflict and the 1 April 2024 scrutiny circular remains unread, these are research leads until the source register is closed. Do not encode them as universally mandatory from this list.

## Source verification update — 2026-10-23
The detailed evidence and gaps are tracked in [the official-source verification report](../research/official-source-verification-report.md), [source register](../research/source-register.md) and [reconciliation memo](../research/reconciliation.md).

**No EOA checklist is approved by this update.** The AICTE Approval Process Handbook 2024–25 to 2026–27 is identified as the base source, but the 1 April 2024 revised-scrutiny document has not been retrieved/read in this research, the official status and effective date of the circulating 2026–27 addendum remain unverified, and the Annexure-2 §2.1 / Clause 7.17 cross-reference needs direct official-PDF review. The base handbook's NBA validity date ending 30 April 2025 also requires current applicability review. The extracted Affidavit 2, TER receipt, building approval, structural stability, fire safety, satellite map and audited-account items are research leads only; do not encode them as a universally mandatory active checklist.

SIH26261 title, theme, team constraints and reported 28 October 2026 deadline were not verified directly from the official SIH portal in the research pass. The deadline is unconfirmed. No public AICTE API was established; API availability is **not researched/confirmed**, not a verified negative.

## Gate hardening — 2026-10-23 audit

`backend/app/rule_catalog.py` was re-verified and hardened after the 2026-10-22 pass:

- tampered or partially constructed rule objects (for example via Pydantic
  `model_construct`) now fail with `RuleActivationError` and a blocker message instead of
  `AttributeError`/`TypeError`;
- `RuleRegistry` stores and returns deep copies, so mutating a returned active object
  cannot change registry state;
- an `effective_from` date earlier than the rule's `publication_date` is refused in the
  `ACTIVE` state and at the gate;
- the gate's "supersede it" wording was corrected: supersession and retirement are
  **not implemented** in this prototype.

The gate is still prototype-only: process-local memory, no durable audit, no
authenticated approver identity, no concurrency handling, no evaluator. No AICTE rule is
defined or active.
