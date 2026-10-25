# Integration and release checklist

Use this before asking for a review, before merging, and before any release conversation.
Tick only what you actually ran, and record the exact head SHA. An unticked box is a
statement of fact, not a failure of the checklist.

## 1. Before opening a PR

- [ ] Branch cut from the current `research/grounded-foundation`, not `main`.
- [ ] Changes are inside your owned directory (see [`../../WORKSTREAMS.md`](../../WORKSTREAMS.md)).
- [ ] No secrets, `.env`, real documents, caches or binaries staged (`git status --short`).
- [ ] `python -m pytest -q` passes locally.
- [ ] `ruff check backend/` passes.
- [ ] `python -m compileall -q backend/app backend/tests` exits 0.
- [ ] New behaviour has a test; fixed defect has a regression test.
- [ ] PR opened as **draft** against `research/grounded-foundation`.

## 2. Contract validation

- [ ] If request/response shapes changed, [`API_CONTRACT.md`](API_CONTRACT.md) is updated
      in the same PR and every change is labelled implemented / proposed / blocked.
- [ ] No endpoint was added that the contract marks **blocked**.
- [ ] If a contract change breaks a consumer, the version note is bumped and the
      consumer is updated in a linked PR.
- [ ] Frontend changes use the contract or clearly labelled mocks — no invented endpoints.
- [ ] Error handling treats 4xx bodies as opaque until an error envelope is agreed.

## 3. Tests and CI

- [ ] Local suite result recorded with counts: `__ passed, __ skipped`.
- [ ] Every skipped test named, with the reason (e.g. Tesseract not installed).
- [ ] CI green on the **exact head SHA** — quote the run URL and SHA in the PR.
- [ ] If CI has no run for your head, say so; do not infer a pass from another PR or an
      earlier commit.
- [ ] No test was weakened, skipped or deleted to make the suite pass.

**Enforcement reality (verified 2026-10-23):** `main` and `research/grounded-foundation`
both report `protected: false`, the repository has no rulesets, and `.github/CODEOWNERS`
only *requests* reviewers. Nothing in this checklist is technically enforced — every item is
a human commitment until an owner configures the protection rules listed in
[`REPOSITORY_STATE.md`](REPOSITORY_STATE.md#enforcement-branch-protection-rulesets-codeowners).
Do not describe any of it as enforced.

## 4. Security gates

Record the true state; do not mark a control done because it is documented.

| Gate | Current state | Required before |
|---|---|---|
| Authentication | **not implemented** | any endpoint returning user/institution data |
| Authorization / RBAC | **not implemented** | same |
| Institution-level tenant isolation | **not implemented** | storing any application or document |
| Private document storage | **not implemented** | any upload |
| Malware scanning | **not implemented** | any upload |
| Secure upload validation (type/size/content) | **not implemented** at the API layer; library-level image limits exist | any upload |
| Durable audit trail | **not implemented** | any reviewer decision or rule approval |
| Retention / deletion controls | **not implemented** | real data |
| Authenticated reviewer identity | **not implemented** (recorded strings only) | any rule activation or review outcome |
| Secret management | `.env` git-ignored; `.env.example` placeholder-only | deployment |
| Rate limiting / abuse controls | **not implemented** | public exposure |

- [ ] No new endpoint exposes documents, personal data or institution-scoped records.
- [ ] No credentials, tokens or keys added to the tree.
- [ ] Any security claim in the PR description is matched by code and a test.

**Until every row above says implemented + tested, production is NO-GO.** Documentation
of a control is not the control.

## 5. Regulatory gates

- [ ] No AICTE rule was activated, and none is described as official.
- [ ] No regulatory requirement was invented or inferred from a URL alone.
- [ ] Any proposed rule carries source URL, document version, publication date, effective
      interval, verification date and reviewer identity.
- [ ] The rule gate still refuses `ACTIVE` unless provenance is verified and an approval
      record exists; supersession remains unimplemented and is not claimed.
- [ ] OCR output is described as advisory and human-review-required.

Official-source verification, applicability and amendment review remain **open**. Phase 0
of `docs/canonical/phases.md` has not closed.

## 6. OCR accuracy gates

- [ ] No accuracy, precision or recall figure is claimed anywhere.
- [ ] Synthetic fixtures are described as regression data, not a benchmark.
- [ ] Stubbed-engine tests are not presented as real-engine evidence.
- [ ] If real-engine behaviour matters, the Tesseract integration test ran (not skipped)
      and its result is quoted.

A labelled, held-out English/Hindi evaluation with a documented methodology is **required**
before any accuracy claim.

## 7. Migration checks

- [ ] No database migration exists in this repository yet; adding one requires selecting
      DB/ORM (owner decision) and a clean-database test.
- [ ] Dependency changes are deliberate, pinned, and installed in a clean virtualenv
      (`pip check` reported clean).
- [ ] No lockfile drift without a stated reason.

## 8. Cross-workstream integration PR

- [ ] One integration PR, not a bundle of unrelated workstreams.
- [ ] All three workstreams reviewed the shared-contract and dependency changes.
- [ ] `git merge-tree --write-tree --name-only origin/research/grounded-foundation HEAD`
      shows no conflicts against the current base.
- [ ] Full regression suite green after combining changes.
- [ ] Overlapping implementations resolved by documented comparison, with the losing
      branch preserved (see [`PR_RECONCILIATION.md`](PR_RECONCILIATION.md)).

## 9. Release gates (all currently blocked)

- [ ] Every security gate implemented and tested.
- [ ] Official-source regulatory verification closed.
- [ ] Labelled held-out OCR evaluation with reported metrics.
- [ ] Deployment target, secrets management and rollback plan approved.
- [ ] Explicit owner go/no-go recorded.

**None of these are satisfied. The project is NOT release ready.**

## 10. Status reconciliation (2026-10-25) — the section 4 table above is historical

The §4 "not implemented" values were recorded before the implementation landed. Re-verified by
copy + execution at integration-branch head `a1784a0` (PR #6), including a fresh local boot
(SQLite demo DB, migrations applied, demo account seeded via `tools/demo/seed_demo.py`, real
HTTP requests) and this session's full local suite. CI run `40129151372` (same head) covers the
shared claims on Linux with real PostgreSQL + Redis.

| Gate | Verified current state | Evidence |
|---|---|---|
| Authentication | **implemented and tested** — JWT bearer; unauthenticated and bad-token requests to protected routes return **401** (reproduced live this session) | `POST /api/v1/auth/token` → 177-char token; `GET /api/v1/applications` unauth → 401, `Bearer garbage` → 401; `backend/tests/test_auth_rbac.py` |
| Authorization / RBAC | **implemented and tested** (server-side roles; officer-only actions refused to institution admin in the live-verified e2e) | CI-run integration suite; §2.1 of `ai/WORKSTREAM_HANDOFF.md` |
| Institution-level tenant isolation | **implemented and tested** — `test_cross_institution_access_denial`, `test_postgres_multi_tenant_isolation` pass against real PostgreSQL in CI | `real-infrastructure-integration` job, run `40129151372` |
| Private document storage | **implemented** (opaque keys, no public serving, traversal-guarded incl. Windows drive syntax on every host); **durability BLOCKED** on the deployed preview (ephemeral disk) | `test_storage_key_hardening.py`; `docs/development/OWNER_ACTIONS.md` §6 storage note |
| Malware scanning | **implemented and fail-closed** — no verdict ⇒ never clean, job parks in `retry_wait`; **a deployed ClamAV daemon is BLOCKED (owner provisioning)**. The CI scanner double is explicitly labelled and never points at port 3310 tests | `test_repeated_transient_failures_reach_terminal_failure`; archived CI job comment on PR #6 |
| Secure upload validation | **implemented and tested** (extension/MIME/content checks, 10 MiB/30 MP limits) | `test_safe_upload_rejection_for_unsupported_or_malformed_files` |
| Durable audit trail | **implemented** (audit events persisted, audit packages with hash verification and tamper detection `verified=false`) | CI e2e comment on PR #6; audit package endpoints in OpenAPI |
| Retention / deletion controls | **not implemented** — unchanged | — |
| Authenticated reviewer identity | **implemented** for review actions (authenticated dependencies); rule-activation reviewer strings remain unresolved pending Phase 0 | — |
| Secret management | **implemented as policy** (`.env` git-ignored; `JWT_SECRET_KEY` required ≥32 chars; no secret in the shipped frontend bundle — verified by bundle inspection this session) | Vercel bundle inspection, run history in PR #6 comments |
| Rate limiting / abuse controls | **not implemented** — public exposure remains gated on this | — |

An untick on §9 release gates remains correct: retention, rate limiting, deployed scanner,
durable storage, official-source regulatory closure and labelled held-out OCR evaluation are
**open**, so the project is still not release ready. What changed is only that the §4 table was
stale; the release verdict is not.
