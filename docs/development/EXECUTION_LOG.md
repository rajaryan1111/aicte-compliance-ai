# Execution log

Append-only record of work done on branch `arena/97cf136c-aicte-compliance-ai` (PR #5).
Purpose: whoever picks this up next knows what was run, what passed, and what is still
blocked — without re-running the whole investigation.

Commands are quoted as executed. Numbers are from the run above them, on the branch state at
that point in time; they grow as tests are added.

## 2026-10-23 — session 4 (implementation)

Starting state: `main` `968ddcf`, `research/grounded-foundation` `014403a`, branch head
`a549f19`, clean tree, PRs #1–#5 all open and draft, `main` and the research branch both
`protected: false`, rulesets `[]`.

| Commit | Change |
|---|---|
| `d294863` | frontend fixtures (9), capture + verify tools, `STATE_MATRIX.md` |
| `c8b124e` | backend response models + 16 contract tests, no JSON change |
| `e420bd3` | AI corpus (56 cases), scorer, 17 tests, `EVALUATION.md` |
| `4deeb36` | CI runs the AI tests and the fixture check, guarded against silent removal |
| `67605a9` | README submission rework, starter tasks retargeted to A2/B2/C2 |
| `1fe44c2` | launch verification and state-report refresh |
| `647cbdb` | `--declare-shared` accepts several paths; real PR invocations recorded |

Verification at each commit — `python -m pytest -q` (223→224 passed, 1 skipped),
`python -m pytest -q ai/tests` (17), `python frontend/tools/verify_fixtures.py` (9/9),
`ruff check backend/ ai/ frontend/ tools/` (clean), `compileall` (exit 0),
`pytest backend/tests/test_docs_links.py` (anchors + links, 0 broken).

CI on exact heads: `4deeb36` run `39907824415` — both jobs success, and the job log confirms
the two new steps ran; `a549f19` run `39906490019`; `d046ea1` run `39906339858`.

Defects found by writing tests, not by inspection:

1. `git worktree add <existing dir>` creates the branch and *then* fails (exit 128),
   leaving a stray branch. Documented with the reproduction.
2. `evaluate_extraction.py` crashed when `--corpus` pointed outside the repo
   (`relative_to` ValueError). Fixed; the CLI now prints an absolute path in that case.
3. `--declare-shared a b c` failed: the option took one value per flag. Fixed + tested.
4. Two OCR extraction defects, documented as corpus *known gaps* and left for the backend
   workstream: `Institution Name: AB` extracts `AB` (3-char minimum bypassed by regex
   backtracking), and the Hindi spelling `शैक्षणिक सत्र` is not matched.

Still blocked, unchanged: landing the CI trigger fix on the base (owner merge), branch
protection (owner settings), the OCR PR #3/#5 choice, PR #4's disposition, contributor
names, and every production control.

## 2026-10-23 — sessions 1–3 (audit, coordination, ownership)

`b8e1643`, `338df56`, `0cff85a`, `5bd260f`, `4d1108f`, `e3d24a2` (hardening and audits),
then `f633d43`…`a549f19` (state report, PR reconciliation, `WORKSTREAMS.md`, parallel
workflow, API contract, integration checklist, recovery, starter tasks, PR template,
CODEOWNERS, ownership checker). Details in `REPOSITORY_STATE.md` and
`PR_RECONCILIATION.md`.

## Next actions, in order

1. Owner: merge PR #5 (or apply `docs/development/patches/ci-pr-trigger.patch` first if CI is
   needed on the base sooner).
2. Owner: branch protection for `main` and `research/grounded-foundation`, with required
   checks `backend-tests` and `optional-ocr-integration` — only after step 1.
3. Owner: decide PR #3 vs PR #5 (recommendation: #5) and PR #4's disposition (its content is
   already carried here).
4. Contributor A: A2 error mapping + state-coverage checker.
5. Contributor B: B2 error-envelope tests; then the two OCR known gaps as their own PR.
6. Contributor C: C2 realistic OCR corruption slice.
