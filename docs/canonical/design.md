# Product Design — Evidence-First Compliance Workflow

**Status:** Product requirements, not a claim that every screen exists. Reuse the current React layout, route conventions, cards, badges, tables, forms and `RegulatoryScrutinyWorkbench`, `DocumentOcrVerifier`, `FindingsTable`, `ExpiryWatchdogMatrix`, and `ScrutinyDossierModal` where fit. Do not redesign the whole application.

## Navigation

Keep the existing Dashboard, Validate, Cadre & FSR Norms, Audit History, Consistency Check and Compliance Guide. Proposed destinations may group Gap Analyzer, Action Planner and Regulatory Intelligence under the current application/compliance workspace after user testing. A label or route is not evidence of a working feature. The new screens must be authenticated and backend-authorized.

## Gap Analyzer screens

1. **Compliance overview:** scoped totals by applicable requirement, evidence sufficiency, open/review findings and trend; each metric linked to its filterable source records. No static demo counts presented as live.
2. **Requirements:** application/year/program context; applicability state and why; source/version/clause; expected evidence; filters by category/status. Unknown applicability is conspicuous and not a failure.
3. **Evidence and analysis:** original document viewer with page/location when available, document version and extraction provenance; separate extracted value, confidence, correction history and rule result; show source alongside the claim.
4. **Finding detail/review:** category, severity, confidence, deficient information, rationale, affected requirement, regulatory citation/version, evidence references, limitations and proposed corrective action. Accept, reject or request evidence with mandatory rationale as policy requires; show immutable review history.

## Action Planner screens

Proposed views: My Tasks; authorized Department Tasks; Institution Overview; list/board/calendar views; task detail; evidence submission; review queue; task history. Detail shows originating finding/requirement, owner/department, priority/deadline, expected evidence, valid next transitions, comments, uploaded evidence and review/revalidation outcomes. Use role-scoped views; never expose institution-wide lists to ordinary members. Overdue indicator is explicit and does not erase workflow status.

## Regulatory Intelligence screens

Proposed views: verified/unverified source library; publication/version detail; clause comparison; change record; impacted requirement/evidence list; impact report; review/approval queue; history. Visibly label source verification, publication/effective date, retrieval time, version and checksum. Show old/new text and machine-detected classification separately from reviewer decision. Allow authorized reviewers to correct extracted clauses, confirm applicability, approve/reject change and queue reassessment. Discovery must not look like a compliance status change.

## Shared interaction states and content

All screens need loading, empty, error, permission denied, partial processing, stale data and retry states. Preserve user input after recoverable failures. Use accessible labels, keyboard operation, visible focus and text/icon status (never color alone); responsive layouts and readable evidence citations. Explain successful upload, failed scan, extraction uncertainty, async polling and processing retry.

Use precise labels: “preliminary checks passed” for limited local checks; “evidence missing” for absence; “manual verification required” for uncertainty; “evidence approved” distinct from “requirement revalidated”; “DEMO — SIMULATED” for any simulation. Avoid “compliant”, “forged”, or “regulation changed” absent an approved basis and human decision.

## Product signals

Finding severity, extraction confidence, regulatory impact, task priority and review status have distinct text labels and filters. Every AI summary links to source evidence and carries its model/version/status. Dashboard counts are computed from authorized persisted data; if source data is unavailable, show unavailable rather than zero. Historical versions and assessment results are reachable without overwriting the current view.

## Feature 1 implementation status (2026-10-31)

This addendum supersedes earlier phase/audit statements in this document where they describe Feature 1 as unimplemented or blocked locally. The branch now contains an authenticated application-scoped Gap Analyzer using approved rule versions, the existing validation engine, Document Vault versions and extracted fields, persisted evidence mappings/review history, requirement assessments, findings and saved run history. The page supports loading and selecting saved runs, requirement findings and source citations, mapping extracted evidence, reviewer decisions, and authorized original-version download. Missing evidence is not presented as proof of statutory non-compliance.

Local verification: `python3 -m pytest backend/tests -q` → 497 passed, 21 skipped; frontend TypeScript/build passed; frontend tests 15 passed; lint exited 0 with existing warnings. Feature 1 still is not production-ready: Render is pinned to a stale branch without these routes, live PostgreSQL RLS inspection was blocked by IP allowlisting, and authenticated deployed workflow testing has not occurred. AI/RAG remains deferred pending provider/privacy approval; no institutional documents are sent to an external model. See `GAP_ANALYZER_FINAL_RELEASE_REPORT.md` and `GAP_ANALYZER_REDEPLOYMENT_HANDOFF.md`.
