# Parallel development workflow

How three workstreams work at the same time without overwriting each other. Ownership is
defined in [`../../WORKSTREAMS.md`](../../WORKSTREAMS.md); contracts in
[`API_CONTRACT.md`](API_CONTRACT.md); gates in
[`INTEGRATION_CHECKLIST.md`](INTEGRATION_CHECKLIST.md); first tasks in
[`STARTER_TASKS.md`](STARTER_TASKS.md); owner-only steps in
[`OWNER_ACTIONS.md`](OWNER_ACTIONS.md).

**Command status legend.** Every command below is marked:

- **✅ verified** — run in this repository on 2026-10-23 (Linux, Python 3.11.2) with the
  quoted result.
- **⚠️ documented** — correct as written but not executed here (needs a push, a PR, a
  network fetch or an owner action).
- **⛔ blocked** — cannot be done today for a stated reason.

If a command you rely on is not marked, assume it is untested.

## Branch topology

```text
main                                 968ddcf  stable base; no workflow file, nothing lands here yet
└── research/grounded-foundation     014403a  INTEGRATION BASE — all PRs target this
    ├── feature/frontend-<name>                workstream A
    ├── feature/backend-<name>                 workstream B
    ├── feature/ai-ocr-<name>                  workstream C
    └── docs/<topic>, fix/<issue>              anyone
```

`<name>` above is a placeholder in a diagram, not in a command — never paste it into a
shell (see [Shell safety](#shell-safety)). Use concrete names such as
`feature/frontend-intake-fixtures`.

- **Do not branch from `main`.** `main` has no test suite and no CI workflow, so a branch cut
  from it cannot be checked.
- **Do not branch from another feature branch** unless the PR description says it depends on
  that PR and why. Stacked PRs are allowed but must be declared.
- One branch per task. Never a shared branch for two people.

## Shell safety

Angle brackets are shell redirection, not placeholders. This is the literal command from the
previous revision of this file and its **actual** result (run in a throwaway clone):

```console
$ git worktree add ../aicte-frontend -b feature/frontend-<task> origin/research/grounded-foundation
/bin/bash: line 1: task: No such file or directory        # exit 1, no worktree created
```

Every command below therefore uses a concrete example value. Substitute your own values
**without** angle brackets.

## Before you start: make sure the remote refs exist

```bash
git fetch origin --prune
git rev-parse origin/main origin/research/grounded-foundation
```

**✅ verified** in a fresh clone: both SHAs resolve (`968ddcf` and `014403a`).

If the second command says `unknown revision or path not in the working tree`, your clone has
a restricted fetch refspec (some sandboxes and CI checkouts restrict it to the current
branch). Confirm with `git config --get-all remote.origin.fetch`. Fix it once, then fetch:

```bash
git config --add remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
git fetch origin --prune
git rev-parse origin/research/grounded-foundation      # -> 014403a...
```

**✅ verified**: with a restricted refspec `git rev-parse origin/research/grounded-foundation`
failed; after the two commands above it returned `014403a36bb91eebf1ebca3fdc1733ee91082db2`.
One-off alternative that changes no config:
`git fetch origin 'refs/heads/*:refs/remotes/origin/*'`.

Then re-check the live PR state rather than trusting these numbers:

```bash
gh pr list --state open --json number,isDraft,baseRefName,headRefOid
gh api repos/rajaryan1111/aicte-compliance-ai/commits/$(git rev-parse origin/research/grounded-foundation)/check-runs \
  --jq '.check_runs[] | [.name,.conclusion] | @tsv'
```

If `research/grounded-foundation` has moved, rebase before starting work rather than after.

## Isolated workspaces

Three agents must not share one working directory. Use a separate `git worktree` per person —
one clone, three directories, three branches:

```bash
cd /path/to/aicte-compliance-ai          # your existing clone
git fetch origin --prune

git worktree add ../aicte-frontend -b feature/frontend-intake-fixtures origin/research/grounded-foundation
git worktree add ../aicte-backend  -b feature/backend-response-model  origin/research/grounded-foundation
git worktree add ../aicte-ai       -b feature/ai-ocr-eval-corpus     origin/research/grounded-foundation

git worktree list
```

**✅ verified** end to end in a fresh clone: three worktrees created, each on its own new
branch at `014403a`, `git worktree list` showing one directory per branch. The names above
are real examples — change them to your task, keep the shape.

Each directory gets its **own** `.venv` (a virtualenv is not shareable across worktrees and
must not be committed; `.gitignore` covers it).
**Check before you create.** ✅ verified on 2026-10-23 — `git worktree add` has a
surprising failure mode that can leave a stray branch behind:

```console
$ git worktree add /tmp/p4/wt-frontend -b task/frontend-probe origin/research/grounded-foundation
Preparing worktree (new branch 'task/frontend-probe')
branch 'task/frontend-probe' set up to track 'origin/research/grounded-foundation'.
fatal: '/tmp/p4/wt-frontend' already exists          # exit 128
$ git branch --list 'task/frontend-probe'
  task/frontend-probe                                # the branch WAS created
```

So, before creating anything:

```bash
git worktree list                 # is the directory already a worktree? reuse it
git branch --list 'feature/*'     # does the branch already exist? pick another name
git worktree add ../aicte-frontend -b feature/frontend-intake-fixtures origin/research/grounded-foundation
```

If a stray branch like the above appears, delete it only when you are certain it holds no
work: `git branch -D task/frontend-probe` refuses if it is checked out somewhere. Never
delete a branch you did not create.


Removing a worktree when finished:

```bash
git worktree remove ../aicte-frontend
```

**✅ verified** that it refuses while the directory holds untracked or modified files:
`fatal: '../aicte-frontend' contains modified or untracked files, use --force to delete it`
(exit 128), and succeeds once the directory is clean. Do not add `--force` to silence
that message — commit or stash first.

## Launch verification (executed 2026-10-23)

The three-workstream setup was created and exercised in a fresh clone, not just described.
Two variants exist because the coordination tooling only lives on PR #5:

**Variant 1 — from the research base `014403a`** (what policy says; no tooling yet):

```bash
git worktree add ../aicte-frontend -b feature/frontend-intake-fixtures origin/research/grounded-foundation
git worktree add ../aicte-backend  -b feature/backend-response-model  origin/research/grounded-foundation
git worktree add ../aicte-ai       -b feature/ai-ocr-eval-corpus     origin/research/grounded-foundation
```

Three directories, three branches, all at `014403a`, all clean. `python -m pytest -q` gives
**54 passed, 1 skipped**; `ai/tests` does not exist there (exit 4); no fixtures and no
`tools/check_ownership.py`. Nothing is broken — the base simply predates this work.

**Variant 2 — stacked on PR #5's head** (everything available now):

```bash
git fetch origin 'refs/heads/arena/*:refs/remotes/origin/arena/*'
git worktree add ../wt-frontend -b task/frontend-states origin/arena/97cf136c-aicte-compliance-ai
git worktree add ../wt-backend  -b task/backend-errors  origin/arena/97cf136c-aicte-compliance-ai
git worktree add ../wt-ai       -b task/ai-eval-extend  origin/arena/97cf136c-aicte-compliance-ai
```

Verified in each: suite `223 passed, 1 skipped`, `ai/tests` 17 passed, fixtures 9/9,
evaluator runs, `ruff` clean.

**Isolation was measured, not assumed.** Creating `frontend/_probe.json` in the frontend
worktree left `git status` empty in the other two worktrees; the ownership checker accepted
it as `frontend` and rejected the same path claimed by `backend`. The probe was deleted and
the tree returned to clean.

## Contributor day-one checklist

Run this before writing any code. It takes about two minutes and catches the three mistakes
that cost the most: wrong base, wrong directory, wrong branch.

```bash
git fetch origin --prune
git rev-parse origin/research/grounded-foundation     # know the base SHA you are on

git worktree add ../aicte-frontend -b feature/frontend-intake-fixtures origin/research/grounded-foundation
cd ../aicte-frontend
git status --short --branch          # must be clean, on your own branch, nothing else's
git log --oneline -1                 # must equal the base SHA you just recorded

python3 -m venv .venv && . .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
python -m pytest -q                  # base: 54 passed, 1 skipped; after PR #5: 205 passed (count grows with the PR)
```

- **✅ verified** 2026-10-23: three worktrees created this way from `014403a`, each clean and on
  its own branch; the base suite gives `54 passed, 1 skipped`.
- The base does **not** contain `WORKSTREAMS.md`, `docs/development/`, `frontend/`, `ai/` or
  `pyproject.toml` — those live on unmerged PR #5. Read them from the PR head before you
  start (see [`STARTER_TASKS.md`](STARTER_TASKS.md#read-this-before-you-branch)).
- Do not create `WORKSTREAMS.md`, `docs/development/*`, `frontend/README.md` or
  `ai/README.md` on your branch; PR #4 and PR #5 own those paths.
- Run the ownership check before your first commit and again before pushing:
  `python tools/check_ownership.py --workstream <yours> --base origin/research/grounded-foundation`.
  It exits 0 when every changed path is yours (or shared and declared). **⚠️ documented**:
  `tools/` exists only on this unmerged branch, so the command becomes available once PR #5
  lands, or immediately if you read the file from the PR head.

## Setup

The integration base and this branch differ today, because PR #5 is unmerged. Know which
state your worktree is in:

| | `origin/research/grounded-foundation` today | After PR #5 merges |
|---|---|---|
| `pyproject.toml` (pytest config, ruff config) | absent | present |
| `ruff` in `backend/requirements-dev.txt` | **absent** | present |
| bare `pytest -q` | **fails** (8 collection errors) | works |
| `python -m pytest -q` | works — 54 passed, 1 skipped | works — 205 passed, 1 skipped |
| `backend/tests/test_ocr_adapter_engine.py`, `test_ocr_image_validation.py` | **absent** | present |

Install (identical for all three workstreams):

```bash
cd ../aicte-backend                   # your worktree
python3 -m venv .venv
. .venv/bin/activate                  # Windows: .venv\Scripts\activate
python -m pip install -r backend/requirements-dev.txt
python -m pip check                   # expect: "No broken requirements found"
```

**✅ verified** on the base branch: install succeeded and `pip check` printed
`No broken requirements found`.

If you are on a worktree cut from the base branch and want lint **today** (before PR #5
merges), install it explicitly; this is a local install, not a dependency change:

```bash
python -m pip install ruff==0.13.2    # ✅ verified; the version CI uses
```

Optional OCR engine (workstream C, and anyone touching OCR):

```bash
sudo apt-get install tesseract-ocr tesseract-ocr-eng   # Debian/Ubuntu
brew install tesseract                                  # macOS
tesseract --version
python -m pip install -r backend/requirements-ocr.txt
```

**⚠️ documented, not executed here.** Tesseract is not installed in the audit environment,
so `backend/tests/test_ocr_engine_integration.py` always skips locally. CI's
`optional-ocr-integration` job runs it with Tesseract installed.

**No environment variables are read by the application today.** `.env.example` documents
planned settings as comments only. Never create a real `.env` with credentials, and never
commit one — `.gitignore` covers `.env` and `.env.*` while keeping `.env.example` tracked.

## Run the checks

```bash
python -m pytest -q                                   # whole suite
ruff check backend/                                   # lint
python -m compileall -q backend/app backend/tests     # import/compile check
```

**✅ verified** on this branch: `205 passed, 1 skipped`; ruff `All checks passed!`;
`compileall` exit 0. The skip is `test_ocr_engine_integration.py` (no Tesseract).

On a worktree cut from the base branch: `54 passed, 1 skipped`, `compileall` exit 0,
`ruff` not installed until you install it (see above), and **bare `pytest -q` fails** with 8
collection errors because `pyproject.toml` (which sets `pythonpath = ["."]`) is not on that
branch yet. Use `python -m pytest -q` there.

Workstream subsets (file names below match what exists on **this branch**; on the base
branch drop the two files marked *):

```bash
# backend / platform
python -m pytest -q backend/tests/test_validation.py backend/tests/test_validation_security.py
python -m pytest -q backend/tests/test_rule_catalog.py backend/tests/test_rule_activation.py

# ai / ocr
python -m pytest -q backend/tests/test_ocr_pipeline.py backend/tests/test_ocr_adapter.py \
  backend/tests/test_ocr_adapter_engine.py backend/tests/test_ocr_image_validation.py \
  backend/tests/test_ocr_fixture_corpus.py
python -m pytest -q backend/tests/test_ocr_engine_integration.py   # needs Tesseract

# frontend — no implementation exists yet, so there is no build, lint or test command
```

**✅ verified** on this branch: backend subsets `17 passed` and `36 passed`; OCR subset
`108 passed` (before the two new test modules landed). On the base branch
`test_ocr_adapter_engine.py` and `test_ocr_image_validation.py` do not exist and pytest
answers `ERROR: file or directory not found` — another reason to branch from the base and
expect only base content until PR #5 merges.

A skipped test is not a pass. `test_ocr_engine_integration.py` skips when Tesseract is
missing; say so explicitly in your PR.

## Commit and push

```bash
python tools/check_ownership.py --workstream backend --base origin/research/grounded-foundation
git status --short                       # inspect before staging
git add backend/app/main.py backend/tests/test_api_contract.py   # explicit paths
git diff --cached                        # review exactly what will be committed
git commit -m "feat(backend): pin the validate response model"
git push -u origin HEAD
git rev-parse HEAD                       # record this SHA in the PR description
```

**⚠️ documented** (pushing is per-developer). Never commit: `.env`, real documents, caches,
`.venv`, `__pycache__`, generated binaries. `.gitignore` covers these; check
`git status --ignored` if unsure. Avoid `git add -A` when anything unrelated is in the tree.

## Pull requests

Written into a file first, because `--body-file` with the repository template would submit
the unfilled template itself:

```bash
cp .github/pull_request_template.md /tmp/pr-body.md
$EDITOR /tmp/pr-body.md                 # fill every field, including the exact head SHA
gh pr create --base research/grounded-foundation --draft \
  --title "feat(backend): pin the validate response model" \
  --body-file /tmp/pr-body.md
```

**⚠️ documented**: creating PRs is a per-developer action; this session may only update its
own PR. Known local quirk: `gh pr edit <n> --body-file` exits 1 in this environment
(GraphQL "Projects (classic) deprecated") **without** changing the body. Use:

```bash
gh api --method PATCH repos/rajaryan1111/aicte-compliance-ai/pulls/<number> -F body=@/tmp/pr-body.md
gh pr view <number> --json body --jq '.body | length'    # confirm it actually changed
```

**✅ verified** in this repository (PR #5 body updated this way).

Keep PRs **draft** until the owner marks them ready. Creating a PR or marking one ready is
an owner action, not a convenience.

## Integration sequencing

1. Foundation branch verified and its CI green on its exact head.
2. Shared contract change merged (`API_CONTRACT.md`) — before any consumer codes against it.
3. Backend implementation + tests (starter task B1).
4. Frontend fixtures and state matrix, then UI against the agreed contract or labelled mocks
   (starter task A1).
5. OCR/AI behind the stable interface (starter task C1).
6. One integration PR per workstream, not one giant PR.
7. Overlapping changes resolved by explicit comparison, never by silent replacement.
8. Cross-workstream tests, then the full regression suite.
9. CI green on the exact final head SHA.
10. Update the evidence in the integration docs.
11. Production stays disabled.

## Conflict detection and resolution

```bash
git fetch origin --prune
git merge-tree --write-tree --name-only origin/research/grounded-foundation HEAD   # dry run
```

**✅ verified**: exits 0 and prints only the resulting tree id when the merge is clean; it
lists conflicting paths when it is not. It never touches your working tree.

```bash
git rebase origin/research/grounded-foundation        # ⚠️ documented
```

Rules:

- Resolve in favour of the version the **owner decided**, and say which that was.
- Never resolve by deleting the other side without recording why.
- If the conflict spans another workstream's directory, **stop** and escalate: you are
  probably editing a file you do not own.
- After a rebase and force-push (`--force-with-lease` only, your own branch only), CI
  re-runs on the new head. Old checks do not carry over.

## Recovery

See [`RECOVERY_AND_BACKUP.md`](RECOVERY_AND_BACKUP.md). Summary: commits are recoverable for
weeks via `git reflog` and the branch SHAs recorded in PRs; uncommitted work is not — commit
or stash before any history-rewriting operation.

## Prohibited operations

`git reset --hard` on a shared branch · `git clean -fd` · force-push to a shared branch ·
force-push without `--force-with-lease` · rewriting history on
`research/grounded-foundation` or `main` · pushing directly to `main` · merging a PR without
the owner · merging your own PR unreviewed · deleting another person's branch.

## What this file has not verified

- CI actually running on a branch created by these instructions (only the owner can open the
  PR that would trigger it).
- macOS and Windows command variants.
- The optional Tesseract install and the engine integration test — no Tesseract here.
- `gh pr create` in this environment (documented command, no new PR opened).
