# Repository state report

**Observed:** 2026-10-23T06:20Z (11:50 IST) — fourth observation pass
**Earlier passes:** 2026-10-23T05:45Z, 05:0xZ, 2026-10-22T23:58Z
**Observer:** repository audit session on branch `arena/97cf136c-aicte-compliance-ai`
**Method:** read-only inspection — `git status`, `git branch -avv`, `git ls-remote`,
`gh pr list/api`, `gh api .../check-runs`, `gh api .../branches/<b>`,
`gh api .../rulesets`, plus local test and setup runs in fresh clones and worktrees.

This is a point-in-time snapshot. Re-verify before quoting it; see
[PARALLEL_WORKFLOW.md](PARALLEL_WORKFLOW.md#before-you-start-make-sure-the-remote-refs-exist) for the re-check commands.
The session branch has advanced past the SHA recorded here — a document cannot name the
commit that contains it.

## Repository

| Item | Value |
|---|---|
| Repository | `https://github.com/rajaryan1111/aicte-compliance-ai` (public) |
| Default branch | `main` (`gh api repos/... --jq .default_branch`) |
| `main` SHA | `968ddcf7a4fb1cd1e1d8d4bb73e0b7fc10b44bcf` — **unchanged across both passes** |
| Merge methods allowed | merge commit, squash and rebase all enabled |
| Auto-merge | disabled (`allow_auto_merge: false`) |
| Delete branch on merge | disabled |
| Merged PRs | **0** |

## Branches

| Branch | Head | PR | Base |
|---|---|---|---|
| `main` | `968ddcf` | — | default |
| `research/grounded-foundation` | `014403a` | #1 | `main` |
| `review/cross-repo-integration-audit` | `5922eca` | #2 | `research/grounded-foundation` |
| `feature/ocr-regression-hardening` | `184d678` | #3 | `research/grounded-foundation` |
| `docs/three-person-workstream-split` | `ed5a41a` | #4 | `research/grounded-foundation` |
| `arena/97cf136c-aicte-compliance-ai` | advancing (see PR #5); workflow now also runs the AI and frontend checks | #5 | `research/grounded-foundation` |

PRs #2, #3 and #4 are all cut from `9157374`, one docs-only commit behind the research head
`014403a`. The repository was previously observed as a shallow clone; `git fetch --unshallow`
was run to obtain real merge bases, so branch comparisons here are based on history rather
than on truncated refs.

## Pull requests

| PR | State | Draft | Base SHA | Head SHA | Files | +/− | Mergeable |
|---|---|---|---|---|---|---|---|
| #1 | open | yes | `968ddcf` | `014403a` | 39 | +2610/−17 | clean |
| #2 | open | yes | `9157374` | `5922eca` | 1 | +120/−0 | clean |
| #3 | open | yes | `9157374` | `184d678` | 4 | +54/−2 | clean |
| #4 | open | yes | `9157374` | `ed5a41a` | 4 | +114/−0 | clean |
| #5 | open | yes | `014403a` | `f96feee` → advancing | 32 | +3641/−57 | clean |

No PR is merged or closed.

## CI on exact head SHAs

| SHA | PR | Check-runs on that exact SHA |
|---|---|---|
| `014403a` | #1 | `backend-tests` success, `optional-ocr-integration` success (runs 39868597925, 39868604125) |
| `5922eca` | #2 | **none** |
| `184d678` | #3 | both success (run 39865712934) |
| `ed5a41a` | #4 | **none** |
| `a7676db` | #5 | both success (run 39905353382) |
| `4deeb36` | #5 | both success (run 39907824415) — 223 tests, plus the new AI-evaluation and frontend-fixture steps |
| `968ddcf` | `main` | **none** — no workflow file exists on `main` |

### Why #2 and #4 have no runs, and what actually fixes it

A `pull_request` trigger's `branches` filter is matched against the pull request's **base**
branch, and the workflow definition that runs comes from the pull request's merge commit,
which includes the head branch's version of the file. Both heads still carry
`pull_request: branches: ["main"]`, and the current base (`014403a`) carries the same old
filter, so the event is filtered out and no run is created.

Tested consequences (local experimentation, nothing pushed):

| Scenario | Result |
|---|---|
| Plain rebase of #2's branch onto `014403a` | **still no checks** — the rebased head's workflow still reads `branches: ["main"]` |
| Rebase onto a base that contains the one-line trigger fix | head carries `["main", "research/grounded-foundation"]`; the guard test passes |
| `backend/tests/test_ci_configuration.py` against the current base workflow | fails on the `pull_request` filter — the guard catches this defect |

So a rebase alone does **not** repair #2/#4; the trigger fix must reach the base first
(PR #3 and PR #5 both contain it and either can land it), and then each branch needs a new
commit — rebase or a one-line edit — to produce a new head and a `synchronize` event.

## Enforcement (branch protection, rulesets, CODEOWNERS)

This pass could read the branch and ruleset APIs, which the first pass could not:

| Check | Endpoint | Result |
|---|---|---|
| `main` protected? | `GET /branches/main` | **`protected: false`** |
| `research/grounded-foundation` protected? | `GET /branches/research/grounded-foundation` | **`protected: false`** |
| Repository rulesets | `GET /rulesets` | HTTP 200, **`[]`** — none configured |
| Classic protection detail | `GET /branches/<b>/protection` | HTTP 403 "Resource not accessible by integration" |

**Conclusion: nothing is enforced.** No required reviews, no required status checks, no
force-push restriction, no CODEOWNERS requirement. `.github/CODEOWNERS` requests reviewers
only; it cannot block a merge without a protection rule, and no such rule exists.

An owner must configure, in GitHub → Settings → Branches (or Rulesets, targeting both
`main` and `research/grounded-foundation`):

1. Require a pull request before merging, with at least one approval.
2. Dismiss stale approvals on new commits.
3. Require review from Code Owners (this is what activates `CODEOWNERS`).
4. Require status checks to pass: `backend-tests` and `optional-ocr-integration`.
5. Require branches to be up to date before merging.
6. Block force-pushes and branch deletion.
7. Restrict direct pushes to `main` (and to the research branch, if that is the policy).
8. Optionally: require linear history; disallow the merge methods you do not want.

Item 4 must be configured **after** the trigger fix lands on the base, or the required check
will never report for PRs targeting that base.

## Setup verification

Run on 2026-10-23 in a fresh clone and fresh worktrees (Linux, Python 3.11.2).

| Check | `research/grounded-foundation` @ `014403a` | Session branch @ `f96feee` |
|---|---|---|
| `pip install -r backend/requirements-dev.txt` | works | works |
| `pip check` | `No broken requirements found` | same |
| `ruff` available after install | **no** (not in that branch's requirements) | yes (0.13.2) |
| `python -m pytest -q` | **54 passed, 1 skipped** | **180 passed, 1 skipped** |
| bare `pytest -q` | **fails — 8 collection errors** (no `pyproject.toml` → no `pythonpath`) | works |
| `python -m compileall -q backend/app backend/tests` | exit 0 | exit 0 |
| OCR subset files (`test_ocr_adapter_engine.py`, `test_ocr_image_validation.py`) | **absent** | present |

Three `git worktree add` commands against `origin/research/grounded-foundation` produced
three independent branches at `014403a`; a worktree with untracked files refused removal
(`contains modified or untracked files`), and removed cleanly once emptied.

The base branch is also **not starter-task ready** in three specific ways: `ruff` is absent
from its requirements, `ruff check backend/` reports one pre-existing `F401` in
`backend/app/ocr_adapter.py`, and none of the coordination documents exist there. Per-task
commands, the verified workaround and the collision rules are in
[STARTER_TASKS.md](STARTER_TASKS.md#verified-commands-2026-10-23).

## CI workflows present

| Workflow | Triggers | Permissions |
|---|---|---|
| `.github/workflows/backend-tests.yml` | push to `main`, `research/grounded-foundation`; PRs targeting either **(on this branch; the base still targets `main` only)** | `contents: read` |

Jobs: `backend-tests` (pytest, Python 3.12) and `optional-ocr-integration` (installs
Tesseract, then runs the engine smoke test).

## Baseline local verification (this branch)

| Command | Result |
|---|---|
| `python -m pytest -q` | **223 passed, 1 skipped** |
| `ruff check backend/` | all checks passed |
| `python -m compileall -q backend/app backend/tests` | exit 0 |
| relative markdown link check (test) | 0 broken links, anchors included |
| `python -m pytest -q ai/tests` | **17 passed** |
| `python frontend/tools/verify_fixtures.py` | `fixtures OK: 9 case(s)` |
| `python ai/evaluate_extraction.py --quiet` | 54 scored cases, micro F1 1.000, 0 negative false positives, 2 documented known gaps |
| `ruff check backend/ ai/ frontend/ tools/` | clean |

The single skip is `backend/tests/test_ocr_engine_integration.py`, which requires the
Tesseract binary; it is **not installed** here, so real-engine behaviour was not exercised
locally. CI's `optional-ocr-integration` job does install it.

## What this snapshot does not establish

- It is not evidence of OCR accuracy: the corpus and engine tests are synthetic.
- It is not evidence of production readiness: no authentication, authorization, tenant
  isolation, private storage, malware scanning, durable audit or retention control exists
  (see [INTEGRATION_CHECKLIST.md](INTEGRATION_CHECKLIST.md#4-security-gates)).
- It does not establish that any rule is active: none is defined.
- It cannot confirm what a maintainer sees in the GitHub UI; it reports API responses only.
