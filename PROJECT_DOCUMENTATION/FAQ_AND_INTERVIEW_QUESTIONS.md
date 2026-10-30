# FAQ and Interview Questions

Answers match the code and the deployed behaviour. Where we do not know, the answer says so.
Do not upgrade an answer into a claim you cannot demonstrate.

---

## Part A — Ten technical questions and answers

**1. What is the validation algorithm, precisely?**
`POST /api/v1/validate` validates the payload with Pydantic (trimming, case-insensitive
de-duplication, ISO dates, no future expiry dates), then computes
`missing = required − submitted` and
`expired = submitted ∩ date_supplied ∩ expiry < evaluation_date`. If either set is non-empty,
status is `attention_required`; otherwise `preliminary_checks_passed`. Findings are generated per
item with a code, description, severity, evidence, possible impact and mitigation undertaking.
It is a set difference plus a date comparison — O(n).

**2. Why request/response and not server-side state?**
The public path stores nothing, which keeps privacy exposure at zero and makes the endpoint
trivially reproducible. Persistence requires sign-in, institution membership, retention rules
and audit obligations; the repository implements that on the `/api/v1` enterprise routes, and it
is deliberately not enabled on the public page.

**3. What exactly is in the "evidence" field?**
Code-specific dictionaries. `MISSING_DOCUMENT` → `{"source": "submitted_document_list",
"observed": "not_submitted"}`. `DOCUMENT_EXPIRED` → `{"source": "synthetic_demo_input",
"expiry_date": "...", "evaluation_date": "..."}`. Both were observed verbatim in the live
response archived in [API_DOCUMENTATION.md](API_DOCUMENTATION.md).

**4. How is the result typed so a client cannot misread it?**
`validation_scope` is a `Literal["caller_supplied_checklist_only"]`. You cannot construct a
response without declaring the scope. `checked_at` is server time in UTC, `source` distinguishes
synthetic demo payloads from user input, and `notice` states that the result is not an AICTE
approval, not an AICTE ruleset evaluation, and not an authenticity check.

**5. How do you prevent the disclaimer from being edited out by a caller?**
The response model is authoritative: values are set server-side, not echoed from the request.
The frontend additionally renders a permanent scope banner. A caller could re-render the JSON
however they like — that is true of any public API — which is why the API also emits the scope
field.

**6. What does the enterprise document pipeline actually check?**
Upload: magic bytes (`%PDF`, JPEG, PNG, TIFF), 10 MiB limit, PDF ≤ 50 pages, ≤ 30 MP, no
encryption, malware scan (ClamAV), SHA-256 hash. Parse: `pdfplumber` text or optional Tesseract;
candidate fields `expiry_date`, `issue_date`, `certificate_number`, `issuing_authority`, each
with a confidence value. Validate: eight check families — mandatory presence, expiry, date
order, institution identity, cross-document consistency, duplicate hash, cross-institution reuse,
low confidence — plus an optional statutory rule engine. Every result stores consumed document
version IDs and the rule snapshot.

**7. How does the rule engine prevent unverified regulation being enforced?**
`RuleVersionDraft` activation requires: all provenance fields present, `verified_at` set,
`source_sha256` matching `^[0-9a-f]{64}$`, an approval record, `effective_from <=
source_retrieved_at`, and at least one each of positive, negative, boundary and exception test
cases. The six seeded APH drafts have none of these, so the engine evaluates nothing and returns
a non-executable summary with a reason. This is tested (`test_unverified_rules_not_evaluated`).

**8. Is the malware scan fail-closed?**
Yes. `ScannerClient.scan_bytes` raises `ScannerUnavailable` on timeout, connection error or
non-200. The service marks the document `quarantined`, never `clean`. An upload therefore fails
closed if ClamAV is down — by design.

**9. What is your authentication design and its current state?**
Design: JWT HS256, `SECRET_KEY` must be ≥32 chars, `python-jose` for tokens, `passlib`+bcrypt for
hashes, role claims in the token, five roles mapped to twelve permissions in `core/rbac.py`, and
tenant isolation that returns 404 rather than 403 for foreign resources. Current state: the
frontend sign-in depends on a Supabase client; the deployed backend is FastAPI on Render;
`/api/v1/auth/token` exists with tests, but the end-to-end sign-in flow is **not working in the
deployed site**, so history and the vault are gated off.

**10. How would you prove a validation result six months later?**
Persist the result with `checked_at`, the normalized input, the finding set, the evaluation
engine version, `consumed_version_ids`, and `rule_snapshot`. The enterprise tables carry exactly
those fields plus append-only audit events. The public endpoint does not persist, so for that
path the caller must keep the JSON body — which is itself a complete, self-describing record.

---

## Part B — Ten challenging questions judges may ask

**1. "You say AI, but where is the model?"**
There is no model, and calling it AI would be wrong. Compliance decisions need to be
reproducible and explainable, and a set difference plus date comparison is exact. The domain
intelligence is the clause knowledge base and the check families. If you want a model, the
honest place for one is document classification, and we would gate it behind human review.

**2. "What happens if AICTE changes the checklist?"**
The public checklist is user-entered, so a change requires no code deployment. The enterprise
rule catalog is versioned: each rule version carries source provenance, citation, effective
dates and test cases, and a change produces a new version rather than mutating history. Results
snapshot the rule version used.

**3. "This looks like a form with a diff. Why is it a project?"**
The diff is the least interesting part. The work is the contract (typed scope, evidence,
statuses), the clause mapping (codes → citation → impact → undertaking), the document pipeline
(magic bytes through quarantine), the rule governance gate, and the audit model. A form that
diffs lists would not survive a scrutiny officer's "show me why".

**4. "Can it detect a forged certificate?"**
No, and no OCR-based system can reliably. We do not claim authenticity. We check presence,
expiry, internal consistency, duplicates and cross-institution reuse, and we flag for human
verification. The issuing-authority integration is architected (SSRF-allowlisted adapter) but
has never been validated against a live authority.

**5. "Your own site's sign-in is broken. Is this finished?"**
No, and we say so on the site: history and the vault are gated, and the Sign In page states that
this deployment is not connected to the authentication service. The core validation and cadre
features work without an account. We could have hidden the broken paths; instead we gated them
and disclosed them.

**6. "23% worse than naive persistence — isn't your model useless?"**
That number belongs to a different repository in this workspace, not to this product. For this
project the relevant honesty test is different: the engine reports **zero active rules**, says
it cannot verify authenticity, and labels its own output "preliminary". We would rather ship a
narrow true thing than a broad false one.

**7. "What stops someone uploading 500 certificates and DoS-ing you?"**
The public endpoint is a JSON list, not uploads; the deployed document-analysis endpoint caps
size at 10 MiB and batch at 5 files, and rejects non-PDF by magic bytes. There is no rate limiter
in the deployed API — that is a genuine gap for public launch, listed in the roadmap. Enterprise
uploads are size-, page- and pixel-capped and scanned before parsing.

**8. "You store government documents. What is your data protection position?"**
The public validation path stores nothing. Enterprise storage is private-object storage with
authorized downloads, 365-day retention with a hard-delete job, append-only audit events, and
no third-party document processors. The privacy policy is explicitly a draft and the site says
it is not ready for launch pending operator, hosting-region, backup-retention and legal review.

**9. "Why should an institution trust a student project over its consultant?"**
It should not replace the consultant. It is a pre-check that reduces the number of avoidable
round trips, with an export the consultant can use. Trust comes from the audit envelope and the
refusal to claim approval, not from the brand.

**10. "What is genuinely novel here?"**
The epistemic discipline: a scope-typed API that cannot return a verdict without declaring what
it did not check; a rule activation gate that refuses unverified regulation; fail-closed
scanning; and a UI that disables features rather than faking them. Most compliance tools sell
certainty. This one is engineered to withhold it.

---

## Part C — Limitations to state plainly

| Limitation | Consequence |
|---|---|
| No LLM or trained model | No document understanding beyond regex/OCR; no classification |
| OCR optional, not installed | Scanned PDFs and images yield no extracted dates |
| Zero active statutory rules | Only checklist, date and heuristic document checks run |
| Sign-in not functional in deployment | No saved history, no vault, no enterprise review in production |
| No authenticity verification | Forged documents pass presence/expiry checks |
| No rate limiting / WAF | Public endpoint is abusable; not launch-ready |
| Rule catalog is a draft | Clause text is paraphrased and must be checked against the APH |
| Frontend preset data is illustrative | "Typical private college" framing is an assumption, not evidence |
| Enterprise UI partially wired | Workbench has mock documents and a demo "verified" state |

---

## Part D — Future scope, in dependency order

1. **Make auth work** (Supabase ↔ FastAPI token exchange or a native auth page) — unblocks
   history, vault, and all enterprise routes.
2. **Enable OCR** (Tesseract + `pytesseract` in the backend image, or a managed OCR service with
   a documented data-processing agreement).
3. **Verify rules** — obtain the APH PDFs, record SHA-256 provenance, write the four test-case
   categories per rule, approve, and activate. Only then does the rule engine execute.
4. **Rate limiting and abuse controls** on the public endpoints.
5. **Real document retention UI** (delete-my-data, export) once auth exists.
6. **Authority verification adapters** for the documents that actually have public verification
   endpoints, with allowlists and evidence capture.
7. **Pilot with one institution**, compare findings against a human scrutiny pass, and publish
   the disagreement rate — the only honest accuracy metric for this product.

---

## Part E — Claims in older files to avoid repeating

`SIH_SUBMISSION.md` describes an "85% reduction in manual verification time" and an "AI-powered"
system. Neither is measured in this repository; the first is unsourced and the second is not
implemented. Do not repeat them. The truthful position is in
[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).
