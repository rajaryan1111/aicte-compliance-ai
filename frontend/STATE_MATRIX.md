# Frontend state matrix

Every screen state the UI must be able to render, which fixture proves it, and what the
screen is allowed to claim. Fixtures are captured from the running API by
`frontend/tools/capture_fixtures.py` and checked against it by
`frontend/tools/verify_fixtures.py` — a fixture that drifts fails CI.

Contract: [`../docs/development/API_CONTRACT.md`](../docs/development/API_CONTRACT.md)
`0.1.0-draft`. Only two HTTP endpoints exist: `GET /health` and `POST /api/v1/validate`.
Everything else below is a **local UI state** with no endpoint behind it.

| # | State | Trigger | Fixture / source | Render | Must not claim |
|---|---|---|---|---|---|
| 1 | **Initial** | screen opened, nothing submitted | none | empty form, submit disabled until `required_documents` has ≥ 1 item | that any check has run |
| 2 | **Loading** | request in flight | none | spinner/skeleton, inputs disabled, no partial result | a result before the response arrives |
| 3 | **Empty checklist** | user has selected no required documents | `validate-422-empty-checklist.json` (the server rejects it too) | inline explanation: add at least one required document | that the application passed |
| 4 | **Request error (local)** | `application_type` missing, body invalid | `validate-422-missing-fields.json`, `validate-422-duplicate-documents.json` | field-level messages mapped from `detail[].loc`; keep user input | that the institution is non-compliant |
| 5 | **Success** | all required documents supplied, none expired | `validate-ok.json` (`status: preliminary_checks_passed`) | neutral confirmation + the `notice` text verbatim or paraphrased faithfully | "compliant", "approved", "eligible", a green "pass" badge implying regulatory clearance |
| 6 | **Missing documents** | at least one `MISSING_DOCUMENT` finding | `validate-missing.json` | list `missing_documents` with the finding message | that the document is fraudulent or the institution ineligible |
| 7 | **Expired document(s)** | `DOCUMENT_EXPIRED` finding | `validate-expired.json` | show `evidence.expiry_date` and `evidence.evaluation_date` | that an expiry date proves non-compliance (expiry is computed from caller-supplied dates) |
| 8 | **Multiple problems** | both codes present | `validate-missing-and-expired.json` | group by finding code; keep server order | a severity ranking the API does not provide |
| 9 | **Future expiry** | expiry supplied but in the future | `validate-future-expiry.json` | no expiry warning | "verified valid until …" — the date is caller-supplied |
| 10 | **Server error** | 5xx or unparseable body | none — no fixture exists | generic retry panel, log a correlation id if one is ever added | any interpretation of what failed |
| 11 | **Network failure** | fetch rejects / timeout | none | offline/retry state, never a cached "success" | that a previous result still applies |
| 12 | **OCR: unresolved field** | future OCR view | none — **no HTTP OCR endpoint exists** | field shown as "unresolved, needs review", with `requires_human_review` | a guessed value, or a confidence presented as correctness |
| 13 | **OCR: advisory result** | future OCR view | none — OCR is a Python module (`backend/app/ocr_pipeline.py`), not a route | extracted fields as *evidence for a reviewer*, each with provenance | proof of authenticity or compliance |

## Rules that apply to every state

1. **`preliminary_checks_passed` is not a compliance verdict.** It means the two lists the
   caller supplied agree. Any wording implying regulatory approval is a defect.
2. **Show `validation_scope`.** The result only covers the caller-supplied checklist; the
   API loads no AICTE checklist and no rule set.
3. **Never invent a field.** If the UI needs data the contract does not define, the fix is a
   contract change, not a mock. `verify_fixtures.py` rejects undocumented top-level keys and
   forbidden verdict-like keys (`compliant`, `approved`, `verdict`, `eligible`, `accuracy`, …).
4. **`checked_at` is a timestamp, not a validity period.** Do not show it as "verified at".
5. **OCR output stays advisory** and every result carries `requires_human_review=True`. No
   accuracy percentage may be displayed; none exists (the corpus is synthetic).
6. **No optimistic success.** State 5 renders only from a 200 response body, never from
   client-side validation.

## Adding a state

1. Add the case to `CASES` in `frontend/tools/capture_fixtures.py` (never hand-write JSON).
2. Re-capture: `python frontend/tools/capture_fixtures.py`.
3. Verify: `python frontend/tools/verify_fixtures.py`.
4. Add a row to this table, including what the screen must not claim.
5. If the state needs a new API field, stop: that is a contract change (see
   [`../WORKSTREAMS.md`](../WORKSTREAMS.md#shared-files-and-how-they-are-coordinated)).
