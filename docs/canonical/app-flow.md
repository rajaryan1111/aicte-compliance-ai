# Product Flows — Current and Proposed

**Status:** Existing flows are implemented in part; flows marked proposed are future work. A UI route does not prove that the workflow behind it exists.

## Existing application and evidence flow

1. User signs in and accesses an institution through active membership/role.
2. Authorized institution admin creates an application for type and academic year.
3. User uploads a document to an application slot. API validates the upload, writes privately, creates a version and processing job/outbox message.
4. Worker scans/processes the version and stores extracted fields with available OCR provenance and processing status.
5. Authorized user requests validation. System freezes eligible version IDs, rule snapshot/context and evaluation date; evaluates configured readiness/consistency/expiry and approved rules; stores run, check results and findings. Async execution can return 202 and polling URL.
6. User/reviewer reads findings and evidence, records review actions and rationale, and may use audit package export. The legacy `/api/v1/validate` is separate caller-supplied demo validation and is not an authoritative rules workflow.

## Proposed Gap Analyzer flow

1. Resolve institution/application context and candidate requirements; show applicability reason, source version, unknown conditions and reviewer controls.
2. Retrieve only evidence authorized for this institution/application; display document version, extraction status and field/page provenance.
3. Map evidence to requirements; user/reviewer confirms ambiguous mappings.
4. Run deterministic checks and only approved optional AI-assisted cited analysis. A missing/unreadable/conflicting input remains distinct from a failure/pass.
5. Persist a new assessment with exact input/version snapshot and evidence-linked findings.
6. Route uncertain/high-impact cases to a reviewer, who accepts, rejects or requests more evidence with rationale.
7. Reassessment creates another run; prior assessments/findings remain accessible.

## Proposed Action Planner flow

1. Authorized user converts an actionable reviewed finding into a task, preserving finding/run/requirement links; reviews/edits any suggested instructions.
2. Authorized admin assigns user/department, priority and due date. Validate scope on server.
3. Owner updates progress and uploads corrective evidence through existing secure document intake; files become new document versions linked to the task.
4. Reviewer approves/rejects evidence or requests more, with reason. Approval alone does not change compliance result.
5. Reviewer triggers revalidation; system creates a new assessment. Authorized reviewer confirms task closure or sends it back/reopens with reason.
6. Append every assignment, status transition, comment, evidence and decision to task history/audit. Overdue state is derived from due date and open status unless product decision says otherwise.

## Proposed Regulatory Change flow

1. Authorized process discovers an official publication, captures original file and source metadata, checksum and retrieval time.
2. Verify source identity and publication version; unverified/contradictory items stay quarantined from authoritative evaluation.
3. Extract clauses and compare with predecessor using text/structured comparison; semantic output is advisory. Human verifies clause alignment and whether change is substantive.
4. Map approved change to governed requirement versions and affected application/evidence; reviewers confirm applicability and impact.
5. Approving impact can queue explicit reassessment with a new requirement/source snapshot. Discovery itself changes no institution status and invalidates no document.
6. Reassessment may produce findings; confirmed actionable findings may create tasks; corrective evidence follows the revalidation flow above.

## Authorization, state and errors

Every listed protected action authenticates the user and verifies active membership, permission and record ownership server-side. Worker rechecks ownership and current authorization constraints from durable IDs. Current global roles are the source for initial design; department scoping and new roles require decision. Show separate states for queued, processing, partial, failed, source unverified, applicability unknown, review pending, evidence rejected, overdue and resolved. Never convert failure or missing information to successful compliance. Use 404 concealment consistently for inaccessible tenant resources.

## External/regulatory state vocabulary

Reuse honest states `not_attempted`, `simulated`, `unavailable`, `inconclusive`, and `externally_verified` only for their existing source verification meaning. Regulatory source verification must be distinguished from a clause interpretation approval, a detected change, an impact approval and an institution compliance decision. Proposed action states and transitions are in `prd.md`.
