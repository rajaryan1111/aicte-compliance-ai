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

---

## 6. Render deployment — exact remaining steps (verified 2026-10-25)

Context: the deployed login screen reported *"Cannot reach the API. Is the backend running
and the proxy configured?"*, and the backend log showed
`sqlite3.OperationalError: no such table: users`. Two independent defects, both now fixed in
code, plus configuration that only the dashboard owner can set.

### What the code now does (no dashboard action needed)

| Behaviour | Where |
|---|---|
| Refuses to start on a deployed platform with a missing or SQLite `DATABASE_URL`, instead of serving a healthy-looking API over an empty file | `backend/app/db/session.py` |
| Applies Alembic migrations at startup when deployed (`MIGRATE_ON_START`, default on), and fails startup if migration fails | `backend/app/db/migrations.py`, `backend/app/main.py` |
| `GET /health/ready` reports engine family, Alembic revision, `users` table presence and reasons, returning **503** when not ready (never echoes the URL) | `backend/app/main.py` |
| CORS allowlist configurable via `CORS_ALLOW_ORIGINS` (exact origins, `*` refused), defaulting to the preview origin | `backend/app/main.py` |
| Frontend network error names the URL it tried; a 401 now shows the server's message instead of a blanket "session expired" | `frontend/src/api.ts` |

### Steps that need the Render dashboard (in this order)

1. **Backend → Environment → `DATABASE_URL`** = the **Internal Database URL** of
   `dpg-dbefnlo473hc73d5or0g-a` (Postgres → *Connect* → *Internal*). Do not paste it into
   GitHub, an issue, or a chat.
2. **Backend → Environment → `CORS_ALLOW_ORIGINS`** = the origins that actually serve the UI,
   comma-separated. Both `https://aicte-compliance-frontend.vercel.app` and
   `https://aicte-compliance-frontend-preview.onrender.com` are allowed by default; set this
   variable only if the deployed origins differ (Vercel *preview* URLs are per-commit and need
   listing explicitly; wildcards and prefix rules are refused).
3. **Backend → Environment → `JWT_SECRET_KEY`** must be set (≥32 chars). Signing raises
   `RuntimeError` without it, so a missing key shows up as 500s on login.
4. **Backend → Health Check Path** = `/health/ready`. This is what marks the service unhealthy
   while the database is unreachable or unmigrated, instead of advertising a working API.
5. **Backend → redeploy** the branch head. Startup logs should show
   `Applying database migrations to head` followed by `Database is at Alembic revision …` on the
   first deploy and no migration lines afterwards.
6. **Frontend → Environment → `VITE_API_BASE_URL`** = `https://aicte-compliance-api-preview.onrender.com`
   then **Manual Deploy → Clear build cache & deploy**. This variable is baked into the bundle at
   build time (`frontend/src/api.ts`), so changing it without a rebuild changes nothing.
7. **Provision the demo account** against the Render database, from a machine that can reach it
   (Render Shell or a trusted host):
   `DATABASE_URL=<internal url> JWT_SECRET_KEY=<same key> python tools/demo/seed_demo.py --username demo_operator --password '<strong temporary password>'`
   The script creates the institution, the user (bcrypt hash) and an `institution_admin`
   membership. Share the password privately — never in the repository.

### Verify after deploying — one command

Run this in the backend's Render Shell. It checks the database configuration, connectivity,
migration revision against the code's head, required tables, provisioned accounts, Redis, the
scanner and storage, prints PASS/FAIL per item, redacts every connection string, and exits
non-zero if anything required fails:

```
python tools/deploy/preflight.py
```

Expected last line: `RESULT: READY (required checks passed; WARN items are documented limitations)`.
WARN on storage means the instance has an ephemeral disk; WARN on scanner means uploads will park
in `retry_wait` (fail-closed, never clean).

Then the two HTTP checks:

```
curl -s <backend>/health/ready          # expect 200, "status":"ready", users_table_present:true
curl -s -D- -o /dev/null -X OPTIONS <backend>/api/v1/auth/token \
  -H 'Origin: https://aicte-compliance-frontend.vercel.app' \
  -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: content-type'
# expect 200 + access-control-allow-origin: that exact origin
```

### Still NOT claimed

Nothing in this repository proves the Render services are configured as above — this environment
has no network route to `*.onrender.com` and no Render integration. The Redis/Key Value instance
has persistence disabled and no Celery worker is verified; document storage is a local directory
unless `STORAGE_LOCAL_DIR` points at a mounted disk; and the ClamAV scanner is not deployed, so
uploads would park in `retry_wait` with `SCANNER_UNAVAILABLE` (fail-closed, not clean). Keep
public uploads disabled until storage, scanning and a worker are verified.
