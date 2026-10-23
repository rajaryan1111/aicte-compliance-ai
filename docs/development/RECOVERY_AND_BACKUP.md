# Recovery and backup

The goal is that no work is ever unrecoverable. Most Git mistakes are recoverable for
weeks; the dangerous ones destroy *uncommitted* work and *unpushed* branches. This page
covers the safe habits and the recovery steps.

## Golden rules

1. **Commit before rewriting history.** `rebase`, `checkout`, `worktree remove` and
   `branch -D` all refuse to destroy committed work but will happily sit on top of
   uncommitted changes in some cases. Run `git status --short` first.
2. **Never `git reset --hard`** on a branch someone else might have based work on, and
   never `git clean -fd` in a tree you did not create.
3. **Push early.** An unpushed branch exists on exactly one disk.
4. **Record SHAs.** Every PR description should name the head SHA that was verified. A SHA
   is a permanent pointer even after a force-push.

## Protecting uncommitted work

```bash
git status --short                 # know what is at risk
git stash push -u -m "wip: <what>" # includes untracked files
git stash list
git stash pop                      # or `git stash apply` to keep the stash entry
```

Better: commit to a scratch branch instead of stashing. A stash is easy to forget and is
not pushed anywhere.

```bash
git switch -c wip/<your-name>-<topic>
git add -p && git commit -m "wip: <topic>"
git push -u origin HEAD            # now it is recoverable off-machine
```

`git worktree remove` refuses to delete a worktree with modifications. If you *want* to
drop it: `git worktree remove --force` — decide deliberately, it discards those changes.

## Recovering commits

| Situation | Recovery |
|---|---|
| Bad commit, not pushed | `git reset --soft HEAD~1` (keeps changes staged) |
| Bad commit, already pushed to your feature branch | `git revert <sha>` — safe, keeps history |
| Lost a commit after a bad reset/rebase | `git reflog` then `git reset --hard <good-sha>` **only on your own branch** |
| Wrong branch committed to | `git cherry-pick <sha>` onto the right branch, then revert on the wrong one if pushed |
| Rebase went wrong mid-way | `git rebase --abort` |
| Rebase finished but was wrong | `git reflog` → `git reset --hard HEAD@{n}` (your own branch only) |

`git reflog` keeps roughly 30–90 days of local moves; pushed SHAs survive independently of
the reflog.

## Restoring a branch

```bash
git fetch origin --prune
git branch -a                    # what exists remotely
git switch -c <branch> origin/<branch>      # recreate a local branch from the remote
git branch -D <branch>                      # delete local only; remote is untouched
```

Deleting a remote branch requires `git push origin --delete <branch>` and should be an
owner decision. Recoverable afterwards via `git push origin <sha>:refs/heads/<branch>` if
you recorded the SHA.

## Handling a failed integration

1. **Do not force anything.** Stop and inspect:
   `git merge-tree --write-tree --name-only origin/research/grounded-foundation HEAD`
2. Preserve your branch as-is: `git push -u origin HEAD` (or note the SHA).
3. Rebase in a scratch copy so the original is untouched:
   ```bash
   git switch -c tmp/rebase-<topic>
   git rebase origin/research/grounded-foundation
   ```
4. If conflicts are not yours (another workstream's directory), stop and escalate. Do not
   resolve someone else's code.
5. If the integration is genuinely wrong after merging, revert the merge commit on the
   integration branch rather than rewriting history:
   `git revert -m 1 <merge-sha>`.

## Overlapping implementations

When two branches implement the same thing (currently PR #3 and PR #5 for OCR), **never**
discard one silently:

1. Compare them with evidence, not by date. See
   [`PR_RECONCILIATION.md`](PR_RECONCILIATION.md) for the method used here.
2. Record the decision in the PR that wins *and* in the PR that loses.
3. Keep the losing branch on the remote until the decision is merged and accepted. Tag or
   note its SHA in the reconciliation record so it is findable after branch deletion.
4. Only then close, and only the owner closes.

## Force-push policy

`--force-with-lease` only, only on **your own** feature branch, only after a rebase, and
never on `main` or `research/grounded-foundation`. Plain `--force` can silently overwrite a
colleague's push; `--force-with-lease` refuses if the remote moved since your last fetch.

## What this repository does not have

- No automated backup or snapshot job.
- No branch protection verified by this session (`403` on the protection API), so nothing
  technically prevents a force-push to `main`. Treat that as a live risk and see
  [PARALLEL_WORKFLOW.md](PARALLEL_WORKFLOW.md#prohibited-operations).
- No release artifacts, so nothing to restore from a previous version.

These are process-level protections, not enforced controls. Do not describe them as
enforcement.
