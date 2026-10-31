# Document Validation Workflow

Two distinct validation pipelines exist. They share a vocabulary but not a code path, and
confusing them is the most common source of overclaiming in this project.

| | **Pipeline A — Preliminary comparison** | **Pipeline B — Evidence-based scrutiny** |
|---|---|---|
| Where | `backend/app/main.py` (`POST /api/v1/validate`) | `services/validation_orchestration_service.py` + `rule_engine.py` |
| Input | Typed lists + dates | Stored, scanned, extracted document versions |
| Used by UI | **Yes**, every validation | **No** |
| Deployed publicly | Yes (live backend) | No |
| Rules | None — set difference only | Gate-approved rules only; currently **zero** |
| Output | `missing_documents`, `expired_documents`, `findings` | Runs, per-check results, findings, summary counts, rule snapshot |

---

# PART A — Preliminary comparison (what the website actually runs)

## A.1 Supported inputs

| Item | Accepted | Rejected |
|---|---|---|
| Institution ID | 1–100 chars, trimmed | blank (422) |
| Application type | `eoa`, `new_program`, `intake_change` | anything else (422) |
| Document names | non-empty strings, trimmed, unique | blanks, duplicates (422) |
| Expiry dates | `YYYY-MM-DD` per document name | invalid date (422), duplicate keys (422) |
| File types | **none** — no file is read on this path | — |

## A.2 Exact sequence

```mermaid
sequenceDiagram
    participant B as Browser (ValidatePage)
    participant V as form-validation.ts
    participant A as POST /api/v1/validate
    participant P as Pydantic
    participant S as Set comparison
    B->>V: user clicks "Run preliminary validation"
    V->>V: step 4 complete? institution, type, ≥1 required
    V-->>B: ok
    B->>A: JSON {institution_id, application_type, required[], submitted[], expiry_dates{}}
    A->>P: trim institution_id; trim names; reject blanks/dupes; parse dates
    alt validation fails
        P-->>B: 422 with field errors
    else valid
        P->>S: required − submitted = missing
        S->>S: expired = submitted where expiry < today(UTC)
        S-->>B: 200 {status, missing[], expired[], findings[], checked_at, scope, source, notice}
    end
    B->>B: render results, optional saveRunUnified()
```

**Step 1 — client pre-validation.** `validateValidationStep()` checks the step the user is
leaving; `validateCompleteRequest()` re-checks everything before submit. Errors render in an
error summary and focus moves to the first invalid field.

**Step 2 — request.** `validateDocuments()` (`lib/api.ts`) `POST`s JSON to
`/api/v1/validate`, with a 15 s abort timeout.

**Step 3 — server normalisation** (`ValidationRequest` in `main.py`):
* `institution_id.strip()`; empty → error.
* Every name `strip()`ed; a blank name or a duplicate **rejects the whole request** with 422
  (the frontend de-duplicates first, so users normally never see this).
* Expiry-date keys `strip()`ed; duplicates rejected.

**Step 4 — comparison** (`validate_application`):

```python
required  = set(request.required_documents)
submitted = set(request.submitted_documents)
missing   = sorted(required - submitted)
today     = datetime.now(timezone.utc).date()
expired   = sorted(d for d in submitted
                   if d in request.expiry_dates and request.expiry_dates[d] < today)
```

**Step 5 — findings.** One `MISSING_DOCUMENT` per missing name (evidence
`{source: "submitted_document_list", observed: "not_submitted"}`), then one
`DOCUMENT_EXPIRED` per expired name (evidence
`{source: "synthetic_demo_input", expiry_date, evaluation_date}`). Missing findings always
come first.

**Step 6 — status.** `attention_required` if any missing **or** expired, else
`preliminary_checks_passed`. There is no third state and no scoring.

**Step 7 — response envelope.** `checked_at` = server UTC ISO timestamp;
`validation_scope = "caller_supplied_checklist_only"`;
`source = "synthetic_demo_input"`; `notice` = fixed disclaimer text.

## A.3 Boundary and edge-case behaviour (verified in code)

| Case | Behaviour | Why it matters |
|---|---|---|
| Expiry date == today | **not** expired (`<`, not `<=`) | Matches "valid through the end of the stated date"; the client-side readiness score uses a different convention and may disagree |
| Expiry date supplied for a document that was not submitted | **ignored** | Prevents a phantom expiry finding for a document the institution never claimed |
| Expiry date for a document submitted but not required | checked and can produce a finding | The check is over `submitted`, not `required` |
| Case/whitespace differences (`"Land Deed"` vs `"land deed"`) | treated as different documents | String identity, not fuzzy matching |
| Required duplicates | 422 | Frontend prevents it |
| Empty submitted list | all required are missing | Valid but maximal deficiency |
| Same name in required and submitted, no date | passes | "Submitted" is a claim, not evidence |
| Malformed date string | 422 | Pydantic `date` |
| Server unavailable / timeout | UI shows a network/timeout alert; **no result is fabricated** | Correct: no fallback synthesis on this path |

## A.4 What is automated vs human

| Check | Automated? | Notes |
|---|---|---|
| Required vs submitted name comparison | ✅ | Deterministic |
| Expiry date vs server UTC date | ✅ | Deterministic |
| Duplicate-in-request detection | ✅ | 422 |
| Document actually exists | ❌ | No upload on this path |
| Document belongs to the named institution | ❌ | Nothing to compare |
| Certificate authenticity / forgery | ❌ | Out of scope |
| Whether the certificate satisfies the clause's *substance* | ❌ | Clause text is editorial |
| Whether a "passing" result means AICTE approval | ❌ | Explicitly not |

**Preliminary vs final.** The product only ever produces *preliminary* results. Every response
carries the disclaimer; the UI repeats it in a `ScopeNotice` and again in the result banner.
Final compliance is a human/committee determination.

---

# PART B — Evidence-based scrutiny (repository backend, not deployed)

## B.1 Supported documents and formats

| Aspect | Value | Source |
|---|---|---|
| Formats | PDF, PNG, JPEG (magic-byte detected) | `core/upload_validator.py` |
| Max size | 10 MiB (`MAX_UPLOAD_BYTES`) | same |
| Max PDF pages | 50 | same |
| Max image pixels | 30 MP (decompression-bomb guard) | same |
| Encrypted PDFs | rejected | same |
| Malformed structure | rejected | same |
| Filename handling | sanitised; storage key is opaque (`docs/xx/<uuid>`) | `core/storage.py` |

Logical document "slots" are typed (`fire_safety_certificate`,
`building_occupancy_certificate`, `aicte_approval`, …). A slot contains one `Document` row and
many immutable `DocumentVersion` rows.

## B.2 Upload → processing sequence

```mermaid
flowchart TD
    U[POST /applications/{id}/documents] --> V{size / magic bytes / pages / encryption}
    V -->|fail| E[400 or 413, nothing stored]
    V -->|ok| S[(Private storage: opaque key)]
    S --> DB[(DocumentVersion: pending_scan, queued)]
    DB --> OB[OutboxMessage in same transaction]
    OB --> D{dispatcher}
    D -->|Celery| W[worker]
    D -->|CELERY_TASK_ALWAYS_EAGER=true| I[in-request execution]
    W --> M{malware scan}
    M -->|infected| Q[rejected + quarantined, never parsed]
    M -->|clean| X{text extraction}
    M -->|scanner unavailable| N[scan_unavailable → stays quarantined]
    X -->|PDF with text| P[pdfplumber + regex fields]
    X -->|image| T[Tesseract OCR if installed]
    X -->|no text| Z[NO_EXTRACTABLE_TEXT warning]
    P --> F[(ExtractedField rows + confidence)]
    T --> F
    Z --> F
    F --> R[processing_status: succeeded / partial / failed]
```

Details worth knowing:

* **Scanning fails closed.** `QuarantineScanner` never claims a file is clean; if ClamAV is not
  reachable the file stays `scan_unavailable` and is not parsed. A rejected file is *never*
  read for content.
* **Extraction is regex-based**, not ML: dates (`valid until`, `expiry date`, `expires on`,
  `date of issue`, `dated`), certificate/NOC numbers, and an issuing-authority label from four
  keyword families (`app/document_analyzer.py`).
* **Confidence** is attached per extracted field; low-confidence fields (below
  `LOW_CONFIDENCE_THRESHOLD`) generate a `LOW_CONFIDENCE_EXTRACTION` finding rather than being
  trusted silently.
* **No LLM is involved anywhere.** See [AI_OCR_ARCHITECTURE.md](AI_OCR_ARCHITECTURE.md).

## B.3 The eight validation check families

`ValidationOrchestrationService.execute_validation_for_run()` runs, in order:

| # | Check ID | Category | What it decides | Failure code |
|---|---|---|---|---|
| A | `CHECK_DOCUMENT_READINESS` | readiness | For each required slot: rejected, pending, failed, no extractable text, missing, or clean | `MALWARE_SCAN_REJECTED`, `DOCUMENT_PROCESSING_PENDING`, `DOCUMENT_PROCESSING_FAILED`, `NO_EXTRACTABLE_TEXT`, `MISSING_DOCUMENT` |
| B | `CHECK_DOCUMENT_EXPIRY` | validity | Extracted expiry vs `evaluation_date`; inconclusive when the date is unreadable | `DOCUMENT_EXPIRED` |
| C | `CHECK_DATE_ORDER` | consistency | Issue date after expiry date | `INVALID_DATE_ORDER` |
| D | `CHECK_INSTITUTION_CONSISTENCY` | identity | Extracted institution identifier vs application | `INSTITUTION_MISMATCH` |
| E | `CHECK_CROSS_DOCUMENT_CONSISTENCY` | consistency | Same field with conflicting values across documents | `INCONSISTENT_DOCUMENT_FIELDS` |
| F | `CHECK_DUPLICATE_FILES` | provenance | Same SHA-256 across distinct slots | `DUPLICATE_FILE_INDICATOR` |
| F2 | `CHECK_CROSS_APPLICATION_DUPLICATES` | provenance | Same SHA-256 submitted by a **different institution** | `CROSS_INSTITUTION_HASH_COLLISION` |
| G | `CHECK_EXTRACTION_CONFIDENCE` | confidence | Any extracted field below threshold | `LOW_CONFIDENCE_EXTRACTION` |
| H | `CHECK_OFFICIAL_REGULATORY_RULES` | regulatory | Gate-approved rules only | `REGULATORY_DEFICIENCY_<rule_id>` |

Check H currently records `status="not_run"` with the message *"No active, approved statutory
rules in registry for this cycle."* — because every draft rule has
`source_provenance.status = unverified` and `approval = None`.

## B.4 Outcome synthesis

```
pending_versions non-empty            → processing_incomplete
any failed check or any finding       → attention_required
any inconclusive check                → inconclusive
any passed check                      → preliminary_checks_passed
otherwise                             → inconclusive
```

The run stores `evaluation_date`, `ruleset_version`, `consumed_version_ids`, `rule_snapshot`,
`summary_counts`, `limitations`, and writes a `VALIDATION_RUN_COMPLETED` audit event. That
snapshot is what makes a run reproducible after documents are replaced.

## B.5 Checklist provenance

Three sources, recorded in `rule_snapshot.source`:

| `checklist_type` | Source label | Meaning |
|---|---|---|
| `caller_specified` | `caller_specified_checklist` | The caller's list; still not official |
| `synthetic_demo` | `synthetic_demo_ruleset` | Hardcoded demo list + a limitation note |
| `default` | `unconfigured_default` | No checklist at all; limitation note added, checks not run |

This is why the product cannot claim to "know" the AICTE checklist: it refuses to invent one.

## B.6 Error handling

| Situation | Response |
|---|---|
| Oversize file | 413 with human-readable MiB message |
| Non-PDF/non-image, wrong magic bytes, encrypted, >50 pages, >30 MP | 400 |
| Unauthorised/foreign tenant | 404 (deliberately not 403) |
| Insufficient role permission | 403 |
| Scanner down | document stays `scan_unavailable`; validation returns `processing_incomplete` |
| Extraction gap | `partial` + warning, never a silent pass |
| Validation exception | run marked `failed`, limitation recorded, committed, returned |
| Rule evaluation exception | isolated per rule; recorded as `inconclusive` |

---

## C. Known gaps in the validation story

1. **The deployed product cannot run Pipeline B at all.** The live backend has the single-file
   `/documents/analyze` endpoint, but no applications/documents/validation-run routes and no
   auth, so evidence-based scrutiny is unreachable from the public site.
2. **The deployed analyzer's contract differs from this repo's client.** Live returns
   `extracted_text` + `fields{}`; the repo expects `extracted_text_preview` +
   `candidate_fields{}`. A live upload succeeds (`200`) but this UI would render no fields.
3. **No OCR in the deployed analyzer.** `pdfplumber` only; scanned certificates are flagged as
   image-only with no fields.
4. **No official checklist.** Zero active rules is a deliberate safety gate, but it also means
   "missing document" can only ever mean "missing from the list you typed".
5. **The client and server disagree on expiry edges** (client: `≤60` days warning and
   local-midnight dates; server: strict `<` on UTC dates).
6. **Readiness score is not a probability.** It is a heuristic with an unexplained −18/−5
   penalty and a broken clause lookup. Do not present it as a model output.

See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for severity ordering.
