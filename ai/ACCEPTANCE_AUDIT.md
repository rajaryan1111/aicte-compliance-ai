# AI/OCR acceptance audit — canonical requirement → evidence

Status as of 2026-10-24, branch `feature/ai-ocr-corruption-slice` at `4f74b14`, pushed and
opened for review as **[PR #10](https://github.com/rajaryan1111/aicte-compliance-ai/pull/10)**
to `origin/main` (OPEN, MERGEABLE — `00065a7` is a strict ancestor); merge remains an owner
authorization. Checks: `optional-ocr-integration` **SUCCESS**; `backend-tests` and
`real-infrastructure-integration` failures both verified pre-existing on `main`
(run `40070848311`) — see BACKEND_HANDOFF.md CI section. On top of the `origin/main` merge `14d27fc`, which brings backend milestone
commits through `4a79d73` and the corpus-gap alignment `7c15e01` into the AI branch;
update this line with each milestone.
Sources of truth: [`docs/canonical/prd.md`](../docs/canonical/prd.md),
[`docs/canonical/phases.md`](../docs/canonical/phases.md),
[`WORKSTREAMS.md`](../WORKSTREAMS.md), [`ai/EVALUATION.md`](EVALUATION.md),
[`ai/BACKEND_HANDOFF.md`](BACKEND_HANDOFF.md).

Labels: `PASS` (reproducible evidence), `PARTIAL`, `BLOCKED_EXTERNAL`,
`NOT_AVAILABLE` (external evidence absent, not implementable), `NOT_REQUIRED`.

## Workstream C deliverables (WORKSTREAMS.md)

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| OCR adapters and engine integration | `ai/raster_benchmark.py` (`RealTesseractEngine`, `MockRasterOCREngine`, availability + language-pack checks), `backend` adapter consumed read-only | 67 raster tests; real Tesseract 5.5.3 artifacts in `ai/reports/` | PASS |
| Pre-processing and normalization | `ai/normalize.py` (evidence-only; deliberately scoped) + `--normalize` diagnosis in evaluator | evaluator tests; `--normalize` output documented in EVALUATION.md | PASS |
| Normalization contract tests | `ai/tests/test_normalize.py` | test suite | PASS |
| Confidence handling (never invented) | evaluator passes through engine-supplied confidences only; scorer never fabricates values | `ai/tests/test_evaluate.py` confidence passthrough tests | PASS |
| Evidence/provenance distinction | engine/version/report fields (`engine`, `engine_version`, `dataset_fingerprint`, `rendering`) in every raster report | report schema tests | PASS |
| Evaluation corpus and accuracy measurement | text corpora (56 extraction cases — all 56 scored after backend fix merged — + 30 corruption cases) + evaluator; raster image benchmark with CER/WER/F1 | `ai/evaluate_extraction.py --check` exit 0; 249 AI tests; extraction slice 56/56 exact | PASS |
| AI tests | `ai/tests/` | `pytest -q ai/tests` → 249 passed (2026-10-24, includes 4 PSM-configuration tests) | PASS |

## Canonical gates (PRD / phases.md)

| Requirement | Evidence | Status |
|---|---|---|
| OCR engine/version selection via a labelled synthetic-data bake-off (PRD open blocker) | evaluation half exists (`--engine module:attribute` bake-off; real/mock raster benchmark with recorded engine/version/seeds). Configuration-level comparison measured 2026-10-24: Tesseract 5.5.3 psm 6 vs psm 3 on identical datasets (`--tess-psm`; seeds 11/23, 16 pooled pairs, fingerprints matched) — recommendation recorded in EVALUATION.md (keep psm 6). Cross-engine comparison requires a second installable OCR engine (dependency + licensing review — BLOCKED_EXTERNAL); the final adoption decision remains an owner decision | PARTIAL (measured config evidence; pending owner decision) |
| Phase 6 gate: labelled synthetic corpus + OCR evaluation; claims supported by recorded measurements | corpora + evaluator + raster/multiseed artifacts; EVALUATION.md states exactly what each measurement does and does not mean; no unmeasured performance claim | PASS (with recorded synthetic-only scope) |
| Phase 6: performance observations | evaluator performance note measured (600 cases ≈ 0.08 s); no unmeasured claims elsewhere | PASS (scoped) |
| Phase 6: accessibility, demo script, deployment fallback | frontend/demo workstreams; not AI-owned | NOT_REQUIRED (other owner) |
| OCR text/confidence are observations, not proof (rules.md) | enforced structurally: synthetic-only corpora, explicit "What these numbers do not mean" section, `accuracy_invalid_languages` invalidation | PASS |

## Known limitations and blockers

| Item | Status | Detail |
|---|---|---|
| Faithful Devanagari shaping on this host | BLOCKED_EXTERNAL | Pinned Pillow 11.3.0 official macOS wheels do not bundle libraqm; no system libraqm. Fixing needs an authorized environment change (install libraqm + rebuild Pillow, or run corpora generation on a Linux manylinux-wheel environment). Reports now carry `rendering`/`accuracy_invalid_languages`/`accuracy_valid` so unavailable-shaping measurements are machine-detectable and flagged, never silently quoted. |
| Real-document accuracy | NOT_AVAILABLE | No human-labelled held-out set of representative scanned AICTE certificates exists. The actionable protocol (strata, annotation discipline, metrics, uncertainty bounds, acceptance pre-registration) is specified in [`ai/REAL_CORPUS_PROTOCOL.md`](REAL_CORPUS_PROTOCOL.md); nothing synthetic is quoted as real-world accuracy. |
| Backend extraction/corruption gaps (15 remaining of original 17) | BLOCKED_EXTERNAL | Backend commit `eec3a81` (merged via PR #7, now merged into the AI branch) resolved `BND-002` and `HI-005`; corpus metadata migrated them into the scored denominator (56/56 exact, verified live 2026-10-24). The remaining 15 corruption-slice gaps were re-verified still failing against the fixed extractor on the merged branch; details in `ai/BACKEND_HANDOFF.md`. |
| Backend test font-path portability (`backend/tests/test_ocr_engine_integration.py`) | BLOCKED_EXTERNAL | Backend-owned; hard-coded Linux font path fails on macOS with Tesseract installed (`OSError: cannot open resource`). Documented 2026-10-24 in BACKEND_HANDOFF.md. Full-repo suite on this branch (re-run 2026-10-24): `2 failed, 388 passed, 21 skipped` — both failures backend-owned. |
| Windows-drive storage-key traversal (POSIX accepts `C:\...` keys) | BLOCKED_EXTERNAL | Backend-owned; `LocalStorageBackend._resolve_key` (`backend/app/core/storage.py`) accepts a `C:\Windows\system32\cmd.exe` key on POSIX because the drive prefix is not treated as absolute there; reproduced in the storage traversal test 2026-10-24. **CI-confirmed on Linux** (branch run `40104526342`; identical pre-existing failure on `main` run `40070848311`) — the PR's `backend-tests` red is this pre-existing main-branch defect, not a branch regression. Documented in BACKEND_HANDOFF.md. |
| Regulatory rule activation / Phase 0 research | BLOCKED_EXTERNAL | Not AI-owned; phases.md Phase 0 gate remains open; no rule activated. |

## Rule integrity (verified 2026-10-24)

- `git diff --check` clean; only `ai/**` files changed by the workstream.
- No backend/frontend/docs/.github file modified by AI/OCR work.
- Historical benchmark artifacts preserved; new artifacts use descriptive names.

## Status update (2026-10-25) — two blocker rows above are now fixed on this branch

The two rows below are dated audit entries, preserved as written; their live status changed on
this branch and is re-verified here:

- **Windows-drive storage-key traversal — FIXED on this branch** by `e509a93` (a colon anywhere
  in a storage key is now refused on every host OS, `backend/app/core/storage.py`), with
  regression tests first shown to fail against the pre-fix code (`test_storage_key_hardening.py`).
  Detailed before/after in `ai/WORKSTREAM_HANDOFF.md` §2.1 (B-2). Still **open on `main`**
  (`e88a5bf`, run `40115512499`: the same traversal test fails) until PR #6 merges.
- **psycopg-v3 migration-job failure — FIXED on this branch** by `e509a93` + `6f431d5`
  (`normalize_database_url` pinning the declared psycopg2 DBAPI at every URL consumer, including
  the integration harness), with a live real-PostgreSQL before/after reproduction; §2.1 (B-1).
  Still **open on `main`** until PR #6 merges. The root cause documented below and in
  `ai/BACKEND_HANDOFF.md` (SQLAlchemy ≥ 2.1 default dialect) is what the fix addresses.

Post-fix verification at this branch's head (fresh session, isolated worktree, Python 3.12 venv,
macOS): `pytest -q` → **459 passed, 22 skipped, 1 failed**; the single local failure is the
already-documented font-path portability defect (backend-owned, passes on Linux CI). Targeted
set for both fixes: **51 passed**. `pytest -q ai/tests` → **248 passed, 1 skipped**. CI on head
`0e4624a`: run `40128878853`, **all four GitHub jobs pass** including `backend-tests` and
`real-infrastructure-integration` (the two jobs red on `main`). The 15 corruption gaps, the
font-path defect, Hindi/bilingual `BLOCKED_EXTERNAL`, real-document `NOT_AVAILABLE` and Phase 0
remain unchanged and open.
