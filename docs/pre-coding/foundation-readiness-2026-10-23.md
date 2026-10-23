# Foundation readiness audit — 2026-10-23

**Repository:** `rajaryan1111/aicte-compliance-ai`
**Default branch:** `main` at `968ddcf7a4fb1cd1e1d8d4bb73e0b7fc10b44bcf` (unchanged)
**Foundation branch:** `research/grounded-foundation` at
`014403a36bb91eebf1ebca3fdc1733ee91082db2` (PR #1, open, unmerged)
**Audit base (current):** `5bd260f7bf809883f311447ca15182ddc248085f` (PR #5 head)
**Scope:** rule-governance and OCR verification, documentation/CI evidence, development
environment reproducibility, three-workstream preparation, security/regulatory gate.
**Data:** synthetic fixtures only. No AICTE rule was defined, activated or evaluated.

This record supersedes current-status and CI claims in earlier documents; those
documents remain as history.

**Correction trail (not a rewrite of history).** The findings in §2–§4 were produced
against audit base `0cff85a7c3d0eef9c352ae07e6668e9741dfc907`, whose CI evidence is
run `39871758137`. PR #5 then advanced to `5bd260f7bf809883f311447ca15182ddc248085f`
(CI run `39872841910`) with a **documentation-only** commit. This document was updated
on 2026-10-23 to name the current head, without relabelling the earlier pass as if it
had been verified later than it was. `0cff85a` and run `39871758137` are retained below
as explicitly historical evidence only.

## 1. Repository state observed

| Ref | SHA | PR | State |
|---|---|---|---|
| `main` | `968ddcf` | — | default branch, untouched |
| `research/grounded-foundation` | `014403a` | #1 (base `main`) | open, draft |
| `review/cross-repo-integration-audit` | `5922eca` | #2 (base research) | open, draft |
| `feature/ocr-regression-hardening` | `184d678` | #3 (base research) | open, draft |
| `docs/three-person-workstream-split` | `ed5a41a` | #4 (base research) | open, draft |
| `arena/97cf136c-aicte-compliance-ai` | `5bd260f` | #5 (base research) | open, draft (`0cff85a` is the previous head, see §4) |

All four sub-PRs were cut from `9157374`, one docs-only commit behind the research
branch head, so their diffs are unaffected by the base moving forward; they should be
rebased before merge.

## 2. Verified rule-governance behaviour

Inspected `backend/app/rule_catalog.py`, `test_rule_catalog.py`,
`test_rule_activation.py`, and every application call site (there are none: no module
imports `rule_catalog` outside tests, and no HTTP route exposes it).

Behaviour confirmed by execution:

- caller-supplied `lifecycle="active"` is refused by the gate;
- unverified/inconsistent provenance, missing or rejected approval, missing
  `effective_from`, and missing test categories are refused;
- `model_construct`/`model_copy` tampering cannot activate through `RuleRegistry`;
- duplicate versions and a second active version of the same rule ID are refused;
- a failed activation leaves registry state unchanged;
- no rule instance exists in `backend/app/`, and no evaluator exists.

**Defects found and fixed in this audit pass (`338df56`, `0cff85a`)** (all previously produced the wrong failure
mode rather than silently activating — the gate failed closed but noisily and
inconsistently):

| # | Defect | Evidence | Fix |
|---|---|---|---|
| R1 | Tampered objects raised `AttributeError`/`TypeError` (`'str' object has no attribute 'value'`, missing attribute on `model_construct`, `NoneType is not iterable`) instead of a gate error | probe on `b8e1643` | `activation_blockers`/`activation_requirements` now type-check and convert malformed metadata into blockers; `RuleActivationError` raised consistently |
| R2 | Returned active object *was* the stored object; caller mutation (including nested `test_cases`) corrupted registry state | probe: after external mutation `get_active(...).lifecycle == draft` | registry stores and returns deep copies |
| R3 | `effective_from` before `publication_date` was accepted, contradicting the rule's own source timeline | probe: rule with `publication_date=2026-06-01`, `effective_from=2020-01-01` activated | rejected in the ACTIVE schema state and blocked by the gate |
| R4 | Gate error told callers to "supersede" a rule, but no supersede/retire API exists | `dir(registry)` → `activate`, `active_rules`, `get_active` | message and module docstring state that supersession/retirement are unimplemented and require durable storage, authorization and audit |

**Limitations that remain (not fixed, by design):** in-memory process-local state;
`reviewer_id`/`verified_by` are recorded strings, **not authenticated identities**;
no durable audit, no multi-user concurrency, no supersession or retirement, no rule
evaluator, and no active AICTE rule. All AICTE rules stay inactive.

## 3. Verified OCR behaviour

Inspected `backend/app/ocr_pipeline.py`, `ocr_adapter.py`, all OCR tests, the fixture
corpus and the CI smoke-test job. Previously reported fixes were re-verified by
execution: strict `OCRWord`/`OCRRawResult` validation, non-finite confidence handling
(`NaN`/`inf` no longer become `1.0`), the 100,000-character aggregate budget (a single
oversized word, 1,000 × 90-char words and 300,000 one-character words are all bounded),
reversed/equal/multi-year academic-year rejection, duplicate-label determinism,
date-contradiction warnings, and decode-vs-engine error separation.

**Defects found and fixed in this audit pass (`338df56`, `0cff85a`):**

| # | Defect | Evidence | Fix |
|---|---|---|---|
| O1 | Malformed Tesseract output escaped as `AttributeError: 'NoneType' object has no attribute 'get'` when `image_to_data` returned `None`, and `TypeError: 'NoneType' object is not iterable` for `{"text": None, "conf": None}` | stubbed-engine probe on `b8e1643` | engine column mapping is validated (`Mapping` + `Sequence` per column); malformed output raises `RuntimeError("…malformed data…")`, and parsing errors are wrapped |
| O2 | Multi-frame TIFF was silently truncated to the first frame with no warning | 2-frame TIFF probe: `n_frames == 2`, one frame read | adapter records a result warning naming the frame count |

**Documented limitations (not implemented):** PDF input is rejected as an unsupported
image; only the first frame/page of a multi-frame file is processed (now warned);
bounding boxes, deskew/denoise and multi-page assembly are absent; the `OCRAdapter`
protocol in `ocr_adapter.py` (`extract(file_path)`) has no implementation — the CLI
uses `RawOCREngine.recognize(image_bytes)`.

**No accuracy claim:** the corpus is 8 synthetic text fixtures plus generated-image
smoke tests. Hindi is covered at label-extraction level only; the optional CI job
installs `tesseract-ocr-eng` and tests English only. No labelled held-out
English/Hindi evaluation exists.

## 4. Documentation and CI evidence corrections

- `docs/pre-coding/implementation-status-2026-10-23.md` ended with "The latest
  code-inclusive evidence is run #56 linked above", contradicting its own correction
  section. Replaced with explicitly historical and explicitly current sections; the
  run #11 head SHA (`83795cc`) was verified through the API instead of assumed, and
  run #56's head (`f160abc`) is labelled historical.
- `docs/pre-coding/phase-5-coding-readiness.md` still said the workflow run and clean
  install were unverified. A dated correction records that both now exist.
- The three workstream documents live only in PR #4, so a non-conflicting
  `docs/integration/workstream-contracts.md` records ownership, contracts, commands and
  open decisions.

CI evidence, verified against exact head SHAs through the GitHub API:

| PR | Head SHA | Check-runs on that exact SHA |
|---|---|---|
| #1 | `014403a` | `backend-tests` success, `optional-ocr-integration` success (runs 39868597925 push, 39868604125 PR) |
| #2 | `5922eca` | **none** — no workflow run exists for this head |
| #3 | `184d678` | `backend-tests` success, `optional-ocr-integration` success (run 39865712934) |
| #4 | `ed5a41a` | **none** — no workflow run exists for this head |
| #5 | `5bd260f` | `backend-tests` success, `optional-ocr-integration` success (run 39872841910) |

**Commit scope of the current head.** `5bd260f` is a **documentation-only** commit: it
changes exactly two files — `docs/integration/workstream-contracts.md` (+36/−7) and
`docs/pre-coding/foundation-readiness-2026-10-23.md` (+49/−14), 85 insertions and 21
deletions in total — with no application, workflow or dependency change. The rule-gate and OCR code fixes described in §2 and §3
are **not** part of that commit; they live in its ancestry — `0cff85a` (Tesseract
engine-output contract), `338df56` (rule gate and engine boundary hardening) and
`b8e1643` (first gate/OCR hardening pass). The aggregate diff between this branch and
`014403a` therefore spans several commits and must not be described as the latest
commit's own diff.

**Standing rule — this document cannot name the head that contains it.** Each
documentation-only commit advances the PR #5 head and therefore invalidates any SHA this
file names as "current". Read the table above as *the head verified when this section
was written*, not as a permanent fact, and re-check the run list before quoting it.
Known documentation-only commits on this branch, each verified on its own SHA:

| Commit | Own diff | CI run on that SHA |
|---|---|---|
| `5bd260f` | 2 docs files, +85/−21 | `39872841910` — `backend-tests` success, `optional-ocr-integration` success |
| the correction commit that added this table | this file only, documentation | verified separately at push time; its SHA and run are recorded in the audit report rather than here |

No application, workflow or dependency file has changed on this branch since
`0cff85a`.

**Historical CI evidence for the previous head.** Run `39871758137` executed on
`0cff85a7c3d0eef9c352ae07e6668e9741dfc907` (`backend-tests` and
`optional-ocr-integration` both successful). It is retained as history for that SHA only
and is not evidence for `5bd260f`.

Why #2 and #4 have no checks: `pull_request.branches` filters the **base** branch, and
the workflow version used for a same-repository pull request comes from the head. Their
heads still carry the old `branches: ["main"]` workflow, so no job is scheduled; PR #3
and PR #5 carry the fix and therefore do get checks against the research base. The fix
only reaches #2/#4 when their own branches are rebased onto a base (or a head) that
contains it — which requires pushing to those branches.

**Unresolved owner action (recorded, not performed):** rebasing `review/cross-repo-integration-audit`
(`5922eca`) and `docs/three-person-workstream-split` (`ed5a41a`) onto the research base,
so their heads pick up the workflow fix and their exact-head CI can run. A read-only
`git merge-tree` check shows both rebase cleanly onto `014403a` with no conflicts. This
session may only push to the PR #5 branch, so it did not rebase, retarget or force-push
either branch.

PR #3's description said "Automated test execution is pending" and that checks "may not
auto-trigger"; that is stale for head `184d678`, which has passing checks
(run 39865712934). PR #1's description cites run #56 (`f160abc`) and the 54-test suite
of that era while its actual head `014403a` has newer passing runs. Both descriptions
were corrected on 2026-10-23 to cite only exact-head runs, without importing test counts
from another commit.

### Overlapping changes between PR #3 and PR #5

Both branches independently implement OCR hardening in
`backend/app/ocr_pipeline.py` and `backend/tests/test_ocr_pipeline.py`. A read-only
`git merge-tree` between the two heads reports **content conflicts in both files**.
The `.github/workflows/backend-tests.yml` change is byte-identical in both, so that file
does not conflict. This duplication is a real deviation from the plan: one of the two
must be chosen as the implementation (PR #5's is a superset with stricter engine-output
validation), and the other rebased or closed by its owner. Neither PR was merged,
retargeted or closed by this pass.

**Decision required from the owner (not made here):** choose whether PR #5's
engine-output contract supersedes PR #3's OCR hardening, or whether PR #3 should land
first and PR #5 be rebased onto it. Evidence for the comparison: PR #5 head `5bd260f`
contains the stricter `text`/`conf` column contract, metadata-alignment checks and
confidence rejection covered by `backend/tests/test_ocr_adapter_engine.py` (57 tests);
PR #3 head `184d678` carries the text-size cap, academic-year validity and
duplicate-label fixtures with its own tests. Deciding this requires an owner to compare
the two implementations and then push to the losing branch.

Workflow review: `pull_request` triggers on `main` and
`research/grounded-foundation` on the audit branches only (the base branch still
triggers on `main` alone); `permissions: contents: read`; dependencies come from the
pinned requirement files; the optional job installs `tesseract-ocr` and
`tesseract-ocr-eng` before running the smoke test. No permission broadening is needed.

## 5. Development environment

Verified by execution on a clean virtual environment (`/tmp/cleanvenv`, Python 3.11.2):

- `python -m pip install -r backend/requirements-dev.txt` → success; `pip check` →
  "No broken requirements found".
- `python -m pytest -q` → **141 passed, 1 skipped**; bare `pytest -q` → same (previously
  11 collection errors; fixed with `pyproject.toml` `pythonpath`).
- `ruff check backend/` → all checks passed (ruff was previously undocumented and
  unpinned; now pinned in `requirements-dev.txt` and configured in `pyproject.toml`).
- `python -m compileall -q backend/app backend/tests` → exit 0.
- `pytest backend/tests/test_ocr_engine_integration.py` → skipped (no Tesseract binary
  in this sandbox); pip-installable OCR dependencies succeeded.
- API start check: `python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`
  → `/health` 200, `/api/v1/validate` 200 with a synthetic payload.

Declared environment:

- Python **3.11+** (the code uses `StrEnum`); CI uses **3.12**; `.python-version` now
  pins 3.12 for pyenv-style setups. All pins declare `Requires-Python >= 3.9/3.10`.
- Supported/tested OS: Linux (CI and this sandbox) and macOS via the same `pip`
  command; Windows is untested. Tesseract is a system package (`apt-get install
  tesseract-ocr tesseract-ocr-eng` or `brew install tesseract`), verified with
  `tesseract --version`.
- `.env.example` is now a placeholder-only template stating that **no environment
  variables are read today**; `.env`/`.env.*` are ignored while `.env.example` stays
  tracked.
- No Dockerfile, Compose file, packaging metadata or lockfile exists; none was invented.

Unverified: Python 3.12 execution locally (only 3.11 available in the sandbox) — CI
covers 3.12. Tesseract execution locally (system package blocked by the sandbox
network policy) — the CI job covers it.

## 6. Three workstreams

See `docs/integration/workstream-contracts.md`. Current reality: only `backend/` exists;
`frontend/` and `ai/` are proposed in PR #4 and contain no code. OCR stays in
`backend/` until a separate integration PR changes imports, tests, dependencies and
CI. Nothing was moved or stubbed to make folders look complete.

## 7. Security and regulatory gate

| Control | Status |
|---|---|
| Authentication | **Not implemented** (no auth code, no dependency, no route) |
| Authorization / RBAC | **Not implemented** |
| Tenant isolation | **Not implemented** (no persistence at all) |
| Private document storage | **Not implemented** |
| Malware scanning | **Not implemented** |
| Persistent audit trail | **Not implemented** (rule gate keeps no audit events) |
| Retention / deletion | **Not implemented** |
| Secure upload handling | **Not implemented** — no upload route exists; image limits exist only in the library/CLI |
| Authenticated reviewer identity | **Not implemented** — recorded strings only |
| Official-source verification of rules | **Not implemented** — research gate open; no rule active |

Only `/health` and `/api/v1/validate` are exposed; there is no public upload route and
no persistence. Production use, real institutional documents, rule activation and
deployment remain **NO-GO**.

## 8. Remaining blockers, in priority order

1. Official AICTE applicability/amendment verification and SIH statement verification
   (regulatory correctness; no rule may activate before closure).
2. Authentication, RBAC, tenant isolation and durable audit — prerequisites for any
   upload route, for authenticated rule approval, and for multi-user use of the gate.
3. Private storage, malware scanning, retention/deletion and secure upload handling.
4. A labelled, held-out English/Hindi OCR evaluation before any accuracy claim; PDF and
   multi-page support if required.
5. Rebase and merge ordering for stacked PRs #2–#5 (they are one docs-only commit
   behind and duplicate the workflow-trigger line and OCR limits).
6. A durable, authorized, audited rule-publication workflow (supersede/retire, audit
   events) before the gate is used for anything other than synthetic tests.

## 8a. Separate readiness gates

These are distinct gates; passing tests closes only the first two.

| Gate | Verdict | Basis |
|---|---|---|
| Ready for planning | **Yes** | Ownership, contracts, commands and open decisions are recorded (`docs/integration/workstream-contracts.md`); no owner decision is pre-empted |
| Ready for isolated implementation | **Yes, with coordination** | Each workstream can work in its own folder on its own branch; contributors are still unnamed and the shared contracts in §"Proposed contracts" are unagreed |
| Ready for integration | **No** | No API/schema contract is agreed, no frontend or `ai/` code exists, and PR #3/#5 conflict on the same files |
| Ready for production | **No** | Every control in §7 is unimplemented; regulatory and OCR-accuracy gates are open |

## 9. What this pass did not do

No PR was merged, closed, retargeted or marked ready. No deployment, release or
dependency upgrade occurred. No AICTE rule, official requirement or accuracy figure was
invented. `main` is unchanged at `968ddcf`.
