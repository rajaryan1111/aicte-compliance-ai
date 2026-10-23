# Pull-request reconciliation

**Observed:** 2026-10-23 (second pass; first pass 2026-10-22T23:58Z). Re-verify before
acting; SHAs change.

Purpose: record, for each open PR, whether it is independent, stacked, blocked, redundant
or superseded, and what work would be lost if it were closed. This document **does not**
change any PR: no base was retargeted, nothing was merged, closed or marked ready.

## Summary

| PR | Verdict | Blocking action |
|---|---|---|
| #1 foundation | Foundation for everything else | Needs owner review; it is the base of #2–#5 |
| #2 cross-repo audit | Independent, docs only, **no CI on its head** | Owner action: new commit after the trigger fix lands (rebasing alone does not help) |
| #3 OCR hardening | **Superseded in behaviour by #5**; its 2 extra fixtures are now ported into #5 | Owner decision on closing |
| #4 workstream split | Independent docs only, **no CI on its head**; its content is now reconciled into #5 | Owner decision; see the `WORKSTREAMS.md` overlap below |
| #5 audit branch | Current integration branch | Keep as draft until the decisions below land |

## Per-PR inventory

### PR #1 — `research/grounded-foundation` → `main`

- Head `014403a`, base `968ddcf`, 39 files, +2610/−17.
- CI on the exact head: both jobs success.
- Content: research reconciliation, rule-catalogue scaffolding, advisory OCR pipeline,
  local CLI, synthetic fixtures, tests, README, implementation-status record.
- Nothing supersedes it: #2–#5 all target it as their base. **Do not close.**

### PR #2 — `review/cross-repo-integration-audit` → research

- Head `5922eca`, base `9157374`, 1 file, +120/−0 (`docs/research/cross-repository-review-2026-10-23.md`).
- CI on the exact head: **none** (stale workflow on the head; see REPOSITORY_STATE).
- Independent: touches no file that #3 or #5 touches. A read-only `git merge-tree`
  against PR #5's head completes cleanly.
- Risk if closed: loses the cross-repository review record, which is not duplicated
  elsewhere. **Preserve.**

### PR #3 — `feature/ocr-regression-hardening` → research

- Head `184d678`, base `9157374`, 4 files, +54/−2.
- CI on the exact head: both jobs success (run 39865712934).
- Overlaps PR #5 on `backend/app/ocr_pipeline.py`, `backend/tests/test_ocr_pipeline.py`
  and `.github/workflows/backend-tests.yml`.
- Ownership: its own branch; nothing from it has been merged anywhere.

### PR #4 — `docs/three-person-workstream-split` → research

- Head `ed5a41a`, base `9157374`, 4 files, +114/−0:
  `WORKSTREAMS.md`, `frontend/README.md`, `backend/WORKSTREAM.md`, `ai/README.md`.
- CI on the exact head: **none** (same stale-workflow cause).
- Contains **only** ownership/planning documents — no frontend or `ai/` application code.
- Overlap: PR #5 now also adds `WORKSTREAMS.md` (see below).

### PR #5 — `arena/97cf136c-aicte-compliance-ai` → research

- Head advances with each commit; at `f96feee` it was base `014403a`, 32 files,
  +3641/−57. CI on that exact head: both jobs success (run 39875377670).
- Content: rule-activation gate hardening, OCR engine-boundary hardening, reproducible
  development environment, documentation/CI-evidence corrections, the coordination set in
  `WORKSTREAMS.md` + `docs/development/`, a CI-trigger regression guard, a docs link check,
  and (see below) PR #3's two fixture cases and PR #4's workstream split.

## PR #3 vs PR #5 — OCR implementation overlap

### What each actually changes

Inspected per commit, not summarised from the PR description.

| Behaviour | PR #3 (`184d678`) | PR #5 (`e3d24a2`) |
|---|---|---|
| 100,000-character text budget | yes | yes |
| Aggregate engine-output budget | yes | yes |
| Non-string text rejected | yes (`TypeError`) | yes (`TypeError`) |
| Reversed / equal academic year rejected | yes | yes |
| Multi-year academic year (e.g. `2026-2030`) | **accepted** | **rejected** (requires `end == start + 1`) |
| `OCRWord`/`OCRRawResult` validation | no | yes |
| Confidence never clamped/inflated | no (clamping still present) | yes |
| Issue-date vs valid-until contradiction warning | no | yes |
| Engine column contract (`text`/`conf` required, alignment) | no | yes |
| Multi-frame warning | no | yes |
| Workflow trigger fix | yes | yes (byte-identical file) |
| Synthetic corpus cases | 10 | 8 |

### Evidence run for this reconciliation

Executed locally against PR #5's implementation, in a throwaway directory
(`/tmp/pr3check`), without modifying either branch:

- PR #3's full test module (`test_ocr_pipeline.py`, 18 cases including parametrisation,
  extracted from `184d678`) → **18 passed** against PR #5's implementation.
- PR #3's fixture corpus (10 cases incl. `SYNTH-009` reversed academic year and
  `SYNTH-010` duplicate labels) → **10/10 pass** against PR #5's implementation.

### Assessment

PR #5's implementation is a **behavioural superset**: it satisfies every test and every
fixture PR #3 introduces, and adds stricter engine-output and confidence handling. The
only behavioural contraction is that multi-year academic years are rejected rather than
accepted, which is stricter and is covered by PR #5 tests.

The **one thing PR #3 has that PR #5 does not** is two fixture lines:

```json
{"case_id":"SYNTH-009","text":"Academic Year: 2027-2026","expected_fields":{}}
{"case_id":"SYNTH-010","text":"Institution Name: First Example College\nInstitution Name: Second Example College","expected_fields":{"institution_name":"First Example College"}}
```

Those cases are already covered by equivalent Python tests in PR #5
(`test_invalid_or_ambiguous_academic_years_are_not_extracted`,
`test_duplicate_labels_keep_first_value_deterministically`), so no behavioural coverage
would be lost, but the data-driven corpus would stay at 8 cases.

### What was done in this pass (no decision taken on PR #3 itself)

Because the fixtures are data, not implementation, PR #3's two unique cases were **ported
into this branch's corpus** (`backend/tests/fixtures/institution_ocr_cases.jsonl`, 8 → 10
cases, commit `c5f9061`). This preserves PR #3's only unique contribution without choosing
between the two implementations and without touching PR #3's branch.

Re-verified against the current head before porting: PR #3's 18-case test module passes
(18 passed) and all 10 of its fixtures pass, including `SYNTH-009` and `SYNTH-010`. After
the port, the corpus test and the full suite pass.

### Decision — still required from the repository owner

**Not decided by this audit.** The evidence supports adopting PR #5's implementation and
closing PR #3 as superseded, but closing is an owner action.

Recommended, evidence-backed option: **adopt PR #5's implementation** (it is a behavioural
superset; its two extra fixtures are already carried here), then close PR #3 as superseded.
That keeps every test PR #3 wrote, keeps its fixture data, and avoids maintaining two OCR
implementations.

Alternative: land PR #3 first and rebase PR #5 onto it — this requires resolving conflicts in
`ocr_pipeline.py` and `test_ocr_pipeline.py` in favour of PR #5's stricter code anyway, so it
produces the same end state with more conflict work.

**Both branches remain intact and recoverable**; nothing was deleted, retargeted or closed.

## `WORKSTREAMS.md` overlap between PR #4 and PR #5

PR #4 adds `WORKSTREAMS.md` on the research branch; this branch also adds it. Both are *new
files* on their respective branches, so merging both produces an add/add conflict in that
one file.

**Reconciled in this pass** (commit `d9e10d6`), without touching PR #4's branch:

- `WORKSTREAMS.md` now carries both texts: this branch's ownership contract (shared-file
  owners and reviewers, OCR placement rule, handoff/escalation, integration process, gate
  status) and PR #4's split (repository layout, per-folder scope, eight non-overlap rules
  including "never merge your own PR" and "no public upload until the gates are met").
  Where they differed, the stricter rule was kept; no rule from either version was dropped.
- PR #4's three per-folder documents were carried over to `frontend/README.md`,
  `backend/WORKSTREAM.md` and `ai/README.md`, marked explicitly as placeholders (README
  only, no code, no framework chosen).
- A provenance note at the top of `WORKSTREAMS.md` records that it merges both versions.

**Consequence for PR #4:** its content is now fully represented here, so if this branch
lands first, PR #4 becomes a pure add/add conflict on four paths with nothing left to add.
An owner may then close it as superseded — that is an owner decision, not taken here.

Resolution plan if PR #4 lands first instead:

1. Land PR #4.
2. On this branch, resolve `WORKSTREAMS.md` by keeping the merged version and restoring the
   provenance note; keep the three folder documents as they are.
3. Re-run CI on the rebased head.

## Missing CI on PR #2 / PR #4 — exact remaining action

**Correction to the first pass.** The earlier note implied that rebasing these branches would
give them CI. It does not. Tested locally: rebasing PR #2's branch onto the current base
(`014403a`) yields a head whose workflow still filters `pull_request: branches: ["main"]`,
because the base itself still carries the old filter. Rebasing alone changes nothing.

Verified sequence (local experiment, nothing pushed):

1. The one-line trigger fix must reach `research/grounded-foundation` first. PR #3 and PR #5
   both contain it; either landing applies it to the base.
2. Then each branch needs a **new commit** to produce a new head and a `synchronize` event:
   either a rebase onto the updated base, or a plain commit editing the filter in place.
3. Re-running the guard test `backend/tests/test_ci_configuration.py` against the rebased
   head passes; against the current base workflow it fails on exactly this defect.

Owner commands, once the fix is on the base (not run by this session — it needs a push to
someone else's branch):

```bash
git fetch origin
git switch review/cross-repo-integration-audit        # or docs/three-person-workstream-split
git rebase origin/research/grounded-foundation
git push --force-with-lease origin HEAD                # rewrite: rebase rewrote commits
git rev-parse HEAD                                     # record the new head SHA
```

No force-push is needed if the owner instead adds a small commit on top of the existing
head. Either way, confirm a `pull_request` run appears for the new SHA before treating the
PR as validated. Until then, #2 and #4 remain **unverified by CI**, not "passing by
inspection".
