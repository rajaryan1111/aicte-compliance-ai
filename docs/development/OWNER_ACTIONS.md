# Owner-only actions

Things this session cannot do, prepared so the repository owner can execute them in a few
minutes. Each block states what is verified, what is not, and how to tell it worked.

**Why a session cannot do these:** it may push only to
`arena/97cf136c-aicte-compliance-ai` (PR #5), and it must not merge, close, retarget, mark
ready, change repository settings, or create branches. Everything below needs either a new
branch, a push to someone else's branch, or an admin setting.

---

## 1. Land the CI trigger fix on the research base — highest priority

**Problem.** `research/grounded-foundation` filters PR checks to `main` only, so every PR
targeting the research base gets **no checks at all** (PRs #2 and #4 have none).

**Fix.** One line in the workflow plus the regression test. The change already exists on
PR #5's head; this block extracts it as a standalone, minimal PR.

**Which route to take now.** PR #5 already carries the trigger fix plus the workstream CI
steps, so the simplest path is to **merge PR #5**. Use the standalone routes below only if
you need CI to work on the base *before* #5 merges.

**Two equivalent routes.** Route A applies the checked-in patch; route B recreates the commit.
Both were executed on 2026-10-23 against `014403a`. Note that both add
`backend/tests/test_ci_configuration.py` (6 guard tests, the pre-workstream version), which
PR #5 supersedes with an 8-test version — expect a trivial add/add conflict on that one file
if you apply the patch and later merge #5.

Route A — apply the verified patch (SHA-256
`d3c9256e652e61dabf5553d61e9453c2269106c3249f396f4964769f31570716`):

```bash
git fetch origin --prune
git switch -c fix/ci-pr-trigger origin/research/grounded-foundation
git apply --check docs/development/patches/ci-pr-trigger.patch   # must print nothing
git apply docs/development/patches/ci-pr-trigger.patch

python -m pip install -r backend/requirements-dev.txt
python -m pytest -q backend/tests/test_ci_configuration.py   # 6 passed
python -m pytest -q                                          # 60 passed, 1 skipped

git add .github/workflows/backend-tests.yml backend/tests/test_ci_configuration.py
git commit -m "ci: run checks for pull requests targeting the research base"
git push -u origin fix/ci-pr-trigger
gh pr create --base research/grounded-foundation --draft \
  --title "ci: run checks for PRs targeting the research base" \
  --body-file /tmp/ci-fix-body.md
```

Route B — extract the same two files from PR #5's head:

```bash
git fetch origin --prune
git switch -c fix/ci-pr-trigger origin/research/grounded-foundation

git checkout origin/arena/97cf136c-aicte-compliance-ai -- \
  .github/workflows/backend-tests.yml \
  backend/tests/test_ci_configuration.py

git diff --stat            # expect: 2 files changed, 92 insertions(+), 1 deletion(-)
python -m pytest -q backend/tests/test_ci_configuration.py   # expect: 6 passed
python -m pytest -q                                          # expect: 60 passed, 1 skipped

git commit -m "ci: run checks for PRs targeting the research base"
git push -u origin fix/ci-pr-trigger
gh pr create --base research/grounded-foundation --draft \
  --title "ci: run checks for PRs targeting the research base" \
  --body-file /tmp/ci-fix-body.md
```

Either route produces the same two-file change (`+92/−1`). PR body to paste into
`/tmp/ci-fix-body.md`:

```markdown
The `pull_request.branches` filter is matched against the PR's **base** branch. It listed
only `main`, so every PR targeting `research/grounded-foundation` — which is where all
workstream PRs go — was filtered out and received no checks (see PRs #2 and #4).

This changes the filter to cover both long-lived branches and adds a dependency-free test
that fails if either branch loses coverage, if `pull_request_target` appears, if workflow
permissions gain write access, or if the full suite stops running in CI.

Verified locally on the exact base this branches from (`014403a`):
- `python -m pytest -q backend/tests/test_ci_configuration.py` → 6 passed
- `python -m pytest -q` → 60 passed, 1 skipped (the skip needs Tesseract)
- Reverting only the workflow line makes the new test fail on `pull_request` coverage

`permissions: contents: read` is unchanged. No application code, dependency or test
behaviour changes. No `pull_request_target`.
```

**Why this PR will get CI when PRs #2/#4 do not:** the workflow definition used for a
`pull_request` event comes from the PR's merge commit, which includes the head branch's
version of the file. This branch *changes* that file, so the fixed filter applies to its own
run. Evidence that this works for a PR into the research base is PR #3, whose head carries the
identical one-line change and has a successful run (`39865712934`).

**Expected result:** a `backend-tests` and an `optional-ocr-integration` check on the new
head SHA. Record both, then merge when you are ready — merging is yours to decide.

---

## 2. Refresh PR #2 and PR #4 heads (only after block 1 lands)

Both heads contain the old filter, and the base's version is what a plain rebase inherits.

**Verified:** rebasing PR #2 onto the *current* base `014403a` still yields a head whose
workflow reads `branches: ["main"]` — a rebase alone does **not** produce CI. After block 1
lands, the same rebase does (tested against a simulated fixed base: the guard test passes).

```bash
git fetch origin
git switch review/cross-repo-integration-audit           # PR #2
git rebase origin/research/grounded-foundation
git push --force-with-lease origin HEAD

git switch docs/three-person-workstream-split            # PR #4
git rebase origin/research/grounded-foundation
git push --force-with-lease origin HEAD
```

`--force-with-lease` only, on these two contributor branches, with the author's agreement. If
you prefer no history rewrite: add a one-line commit editing the filter on each branch
instead — that also creates a new head and a `synchronize` event.

Then confirm a run exists for each **new** head SHA:

```bash
gh api repos/rajaryan1111/aicte-compliance-ai/commits/<new-sha>/check-runs \
  --jq '.check_runs[] | [.name,.conclusion] | @tsv'
```

Until then, #2 and #4 remain **unverified by CI** — not "passing by inspection".

---

## 3. Branch protection / rulesets (nothing is enforced today)

**Verified 2026-10-23:** `GET /branches/main` → `protected: false`;
`GET /branches/research/grounded-foundation` → `protected: false`;
`GET /rulesets` → HTTP 200, `[]`. The classic protection detail endpoint returns 403
("Resource not accessible by integration") for this credential, so this is a report of the
`protected` flag and the ruleset list, not of settings this session could configure.

`.github/CODEOWNERS` exists but only *requests* reviewers. Without a protection rule it
cannot block a merge.

Configure, in **Settings → Branches** (or a ruleset targeting both branches):

| Setting | Why |
|---|---|
| Require a pull request before merging | stops direct pushes to `main` |
| Require at least 1 approval | a second pair of eyes on every change |
| Dismiss stale approvals on new commits | approval must match the head SHA |
| Require review from Code Owners | makes `CODEOWNERS` effective |
| Require status checks: `backend-tests`, `optional-ocr-integration` | blocks merges on red CI |
| Require branches to be up to date before merging | prevents "green on stale base" |
| Block force-pushes and branch deletion | protects contributor work |
| Restrict direct pushes to `main` (and the research branch) | only integration PRs land |
| Named maintainers as the only merge actors | integration stays deliberate |

**Order matters:** enable the required status checks **after** block 1 lands, otherwise the
check never reports on PRs targeting the research base and the branch becomes unmergeable.

Item 5 has a catch worth knowing: "up to date before merging" forces a rebase for every
workstream PR as soon as the base moves. If you want a lighter process, drop it and rely on
the exact-head CI rule instead.

---

## 4. Integration decisions only you can make

| Decision | Evidence | If you take the recommendation |
|---|---|---|
| Which OCR implementation survives: PR #3 or PR #5 | PR #5's code passes all 18 of PR #3's tests and all 10 of its fixtures; PR #3's two unique fixtures (`SYNTH-009` reversed year, `SYNTH-010` duplicate labels) are now already carried on PR #5's branch | Adopt PR #5, close #3 as superseded |
| What happens to PR #4 | Its four files are reproduced on PR #5's branch (`WORKSTREAMS.md` merged, three folder READMEs carried) | Close #4 as superseded, or merge it first — either is safe |
| Merge order of #1 → #5 | #5 targets the research base, which is #1's head | #1 first, then #5 |
| Names of the three contributors | `WORKSTREAMS.md` intentionally leaves them unassigned | Fill the table in one commit |
| Frontend framework, database/ORM, identity provider, storage vendor | none chosen anywhere in the repo | Record the decision before A1's UI work starts |

Nothing above was executed by this session: no PR was merged, closed, retargeted or marked
ready, and no setting was changed.

---

## 5. Production gates — still open, regardless of test results

Authentication and authorization/RBAC · institution/tenant isolation · private document
storage · malware scanning and secure upload handling · persistent audit logging · retention
and deletion controls · verified official AICTE source applicability and amendment tracking ·
representative labelled held-out OCR evaluation · dependency, licensing and provenance
review.

Until those exist and are security-tested, production is **NO-GO**; passing tests do not
change that.
