# Workstreams — authoritative ownership contract

**Status:** three workstreams are defined and independently workable. This is **not** a
claim that three applications exist: only `backend/` contains code. `frontend/` and `ai/`
contain a README and no implementation (see [Current reality](#current-reality)).

**Scope:** ownership, edit permissions, shared-file rules, integration and escalation.
This file is the single source of truth for *who may edit what*.
It is **not** the source of truth for integration contracts or gate status — those live in
[`docs/development/API_CONTRACT.md`](docs/development/API_CONTRACT.md) and
[`docs/development/INTEGRATION_CHECKLIST.md`](docs/development/INTEGRATION_CHECKLIST.md).
Process details (branch names, worktrees, PR mechanics) are in
[`docs/development/PARALLEL_WORKFLOW.md`](docs/development/PARALLEL_WORKFLOW.md).

Anything not written down here is **not** permission. Ask before assuming.

> **Provenance.** This file merges two contributions: the ownership contract introduced on
> this branch, and the folder-ownership split proposed in PR #4
> (`docs/three-person-workstream-split`). PR #4's per-folder documents now live at
> [`frontend/README.md`](frontend/README.md), [`backend/WORKSTREAM.md`](backend/WORKSTREAM.md)
> and [`ai/README.md`](ai/README.md). Both versions meant the same thing; where they differed
> in detail, this file keeps the stricter rule. The comparison is recorded in
> [`docs/development/PR_RECONCILIATION.md`](docs/development/PR_RECONCILIATION.md).

## Repository layout

```text
aicte-compliance-ai/
├── frontend/             # workstream A — UI and user workflows (README only)
├── backend/              # workstream B — API, validation, security, and today's OCR code
├── ai/                   # workstream C — OCR/AI adapters and evaluation (README only)
├── docs/                 # shared project, research, development and integration docs
├── .github/              # shared CI configuration and PR template
└── WORKSTREAMS.md        # this ownership contract
```

## Current reality

| Area | Location | State |
|---|---|---|
| Checklist validation API | `backend/app/main.py` | Implemented (`/health`, `/api/v1/validate`) |
| OCR contract + pipeline + adapter | `backend/app/ocr_adapter.py`, `ocr_pipeline.py` | Implemented, synthetic tests only |
| Local OCR CLI | `backend/app/ocr_cli.py` | Implemented |
| Rule catalogue + activation gate | `backend/app/rule_catalog.py` | Implemented; **no rule defined or active**, no evaluator |
| Backend tests | `backend/tests/` | Implemented (186 passing, 1 skipped on this branch) |
| Frontend application | `frontend/` | **README only**, no code, no framework chosen |
| AI/OCR service | `ai/` | **README only**, no code |
| Persistence, auth, storage, audit | — | **Does not exist** |

The `frontend/` and `ai/` directories contain a single documentation file each. That is an
honest placeholder, not an application. **Do not add stub code that fakes persistence, auth,
compliance or OCR behaviour to make the layout look complete.**

## Workstreams

| Workstream | Owns | Deliverables | Unassigned until |
|---|---|---|---|
| **A — Frontend** | `frontend/` | Applicant/reviewer UI, forms and validation feedback, document/status and evidence views, loading/error/empty/success states, accessibility and responsive layout, mock fixtures, API client against the approved contract, frontend tests | an owner names the contributor |
| **B — Backend / Platform** | `backend/` | FastAPI endpoints, request/response schemas, server-side validation, service boundaries, auth/RBAC, tenant isolation, upload security, persistence, audit, retention/deletion, error contract, integration contracts, backend tests | an owner names the contributor |
| **C — AI / OCR** | `ai/` | OCR adapters and engine integration, pre-processing, normalization and confidence handling, evidence/provenance, evaluation corpus and accuracy measurement, AI tests | an owner names the contributor |

**Contributor names are deliberately unassigned.** Record the assignment in this table
(one line, with the date) when the owner provides it; do not infer it from commit authors.

## Allowed and prohibited paths

| Path | Owner | Others may |
|---|---|---|
| `frontend/**` | A | not edit |
| `backend/app/**`, `backend/tests/**`, `backend/requirements*.txt` | B (see exceptions) | not edit |
| `ai/**` | C | not edit |
| `docs/**` | shared | propose via separate PR |
| `.github/**` | shared | propose via separate PR |
| root files (`README.md`, `pyproject.toml`, `.gitignore`, `.env.example`, `.python-version`) | shared | propose via separate PR |
| `WORKSTREAMS.md` | shared | propose via separate PR |

**OCR exception.** `backend/app/ocr_*.py`, `backend/tests/test_ocr_*.py` and
`backend/tests/fixtures/institution_ocr_cases.jsonl` are the *current* OCR implementation
and are owned by **B** until a migration is approved. Workstream C may propose changes to
them, but must not land them alone. See
[OCR placement](#ocr-placement--stays-in-backend-until-an-approved-migration).

**Prohibited for everyone:** pushing to `main`; force-pushing a shared branch; editing
another workstream's directory; adding real institutional or personal documents;
committing secrets or `.env` files; activating a regulatory rule; adding a public upload
route; weakening a test to make CI pass; merging your own PR without owner review.

## Automated ownership check

Ownership is enforced by a script, not only by this document:

```bash
python tools/check_ownership.py --workstream backend \
  --base origin/research/grounded-foundation
```

Exit `0` means every changed path is yours, or is shared and declared. Exit `1` lists the
offending paths; exit `2` means a bad argument or an unusable base ref. Workstreams are
`frontend`, `backend`, `ai` and `integration`. `--declare-shared <path> [<path> ...]` records
a deliberate shared change (repeatable, and several paths may follow one flag); a declaration
is an assertion for review, not proof that the other owners agreed.

Real examples, run against the open PRs:

```console
$ # PR #3 touches backend/ *and* the workflow
$ python tools/check_ownership.py --workstream backend --paths-from <(git diff --name-only \
    origin/research/grounded-foundation...origin/feature/ocr-regression-hardening)
  - .github/workflows/backend-tests.yml: shared path changed without --declare-shared …
# add --declare-shared .github/workflows/backend-tests.yml  ->  ownership OK

$ # PR #4 touches three workstream folders plus the root contract
$ python tools/check_ownership.py --workstream integration --paths-from … --declare-shared \
    ai/README.md backend/WORKSTREAM.md frontend/README.md
ownership OK: 4 changed path(s) fit workstream 'integration'
```

What it enforces:

| Change | Allowed for | Notes |
|---|---|---|
| `frontend/**` | `frontend`, or `integration` with a declaration | |
| `backend/**`, `ai/**` | the owning workstream | |
| `backend/app/ocr_*`, `backend/tests/test_ocr_*`, `backend/tests/fixtures/institution_ocr_cases.jsonl` | `backend` only | `ai` may propose, never land alone |
| `docs/**`, `.github/**`, `tools/**`, root files (`README.md`, `WORKSTREAMS.md`, `pyproject.toml`, `.gitignore`, `.env.example`, `.python-version`) | any workstream **with** `--declare-shared`; `integration` freely | separate proposal/integration PR |
| unrecognised root paths | treated as shared | do not rely on being unlisted |

**Integration guard tests.** Three tests live under `backend/tests/` because that is the only
directory pytest collects, but they are owned by the integration workstream, not by B:
`test_ci_configuration.py`, `test_docs_links.py`, `test_ownership_boundaries.py`. A change to
any of them is reported as a violation for every workstream, so a backend PR cannot quietly
weaken the checks that police backend PRs. Changing them requires the integration PR.

The script checks **paths, not intent**: it cannot tell that frontend logic was placed in
`frontend/` badly, and it cannot verify that a declaration was actually reviewed. Review
still does that work.

## Shared files and how they are coordinated

Shared files are the ones that break two people at once. Rule: **one nominated owner per
change, the other workstreams review.**

| Shared surface | Nominated owner for change | Reviewers |
|---|---|---|
| `docs/development/API_CONTRACT.md` | B | A, C |
| `README.md` | B | A, C |
| `.github/workflows/**` | B | A, C |
| root config (`pyproject.toml`, `.gitignore`, `.env.example`, `.python-version`) | B | A, C |
| dependency manifests `backend/requirements*.txt` | B | A, C |
| OCR interface + shared fixtures | B (until migration) | C |
| `docs/**` research and pre-coding records | the author of the change | one other |

A change to `docs/development/API_CONTRACT.md` is a **contract change**. It needs its own
PR, merged before dependent implementation starts. Do not change a contract and a
consumer in the same PR.

## Dependency and integration rules

1. Each workstream works on its own branch in its own directory. No shared feature branch.
2. Contract before implementation: agreed request/response and evidence shapes first,
   mocks or stubs second, real integration last.
3. Cross-directory wiring happens only in a **separate integration PR** that all three
   owners review.
4. Frontend consumes only the contract. It must not invent endpoints or infer response
   shapes that `docs/development/API_CONTRACT.md` marks `proposed` or `blocked`.
5. Backend must not change a response shape a merged frontend depends on without bumping
   the contract version.
6. OCR output stays advisory. No workstream may present extracted text as verified
   evidence or as regulatory compliance.
7. Regulatory rules stay inactive until an owner records official-source verification,
   applicability, effective dates and reviewer identity. The gate in
   `backend/app/rule_catalog.py` enforces the mechanical part; it does not verify sources.
8. No workstream may import another workstream's private implementation before the
   interface is agreed.
9. Never resolve a conflict by discarding the other side. Compare, record the decision,
   and keep the losing branch recoverable (see
   [`RECOVERY_AND_BACKUP.md`](docs/development/RECOVERY_AND_BACKUP.md)).

## OCR placement — stays in `backend/` until an approved migration

The OCR pipeline currently lives in `backend/`. Moving it to `ai/` would change import
paths used by six test modules, the CI smoke-test job and the documented CLI command.

If C wants the OCR implementation in `ai/`, that requires its own migration PR that:

1. states the new import path and keeps or rewrites every existing OCR test;
2. keeps `Pillow`/`pytesseract` optional and out of `backend/requirements.txt`;
3. re-verifies both CI jobs and the CLI command;
4. says whether `backend/` keeps a thin adapter or loses OCR entirely.

**Do not create empty placeholder applications or move files to make the layout look
complete.**

## Handoff and escalation

**Handoff** — before you stop working on a shared surface, push the branch, update the PR
description with the exact head SHA and what you verified, and state what the next person
must do. A handoff without a pushed SHA has not happened.

**Escalate to the repository owner** when a decision changes ownership, a shared
contract, PR topology, branch protection, or anything security- or regulation-shaped.
Escalation is a PR comment naming the decision and the options — not a silent change.

Escalate immediately if you find: a real credential or personal document in the tree, a
security control claimed but not implemented, a rule that looks active, or two
workstreams having edited the same file.

## Integration process

1. Each owner commits only within their directory and opens a PR against
   `research/grounded-foundation`.
2. All three review shared-contract and dependency changes.
3. A separate integration PR handles cross-folder wiring, root config and CI.
4. Run the checks in [`INTEGRATION_CHECKLIST.md`](docs/development/INTEGRATION_CHECKLIST.md)
   and record the exact head SHA that passed.
5. CI must be green on the exact head SHA being merged — not on an earlier commit and not
   on a different PR.
6. No automatic merging, no automatic deployment, no production enablement.

## Gates this document does not satisfy

Ownership rules do not make the project production-ready. Authentication,
authorization, tenant isolation, private storage, malware scanning, durable audit,
retention/deletion, authenticated reviewer identity and official-source rule verification
are all **unimplemented**. Production remains **NO-GO**.

Branch protection is also **not configured**: as observed on 2026-10-23, both `main` and
`research/grounded-foundation` report `protected: false` and the repository has no rulesets.
Nothing here is technically enforced — see
[`docs/development/REPOSITORY_STATE.md`](docs/development/REPOSITORY_STATE.md#enforcement-branch-protection-rulesets-codeowners).

## Status update 2026-10-25 — the applications exist now; the ownership rules stand

The "README only" statements above reflect the PR #4-era snapshot and are historical as of this
date. Verified on the integration branch (PR #6 head `a1784a0`, re-run by execution this session,
Python 3.12 fresh venv on macOS / Node via npm ci):

- `frontend/` contains a React 18 + TypeScript + Vite application. `npm ci && npm run build`
  succeeds (`tsc -b`, 161.16 kB JS / 9.50 kB CSS); `python frontend/tools/verify_fixtures.py`
  replays 9 fixture cases against the live API and returns OK. Workstream A's scope above is
  still its scope.
- `ai/` contains the OCR/evaluation workstream: 248 tests passing (`pytest -q ai/tests`),
  benchmark scripts and dated evidence reports under `ai/reports/`.
- `backend/` (never a placeholder) passes 456+ tests including the live PostgreSQL/Redis
  integration suite in CI (real `real-infrastructure-integration` job).

What this note does **not** change:

- The **ownership tables above remain in force** for every new change — including the workstream
  paths, the shared-file rules, and the requirement that contract changes (`docs/development/
  API_CONTRACT.md`) are reviewed changes.
- Branch protection is **still not configured** (re-verified 2026-10-25: `protected: false`,
  rulesets `[]`). Nothing is technically enforced; only the human commitment is.
- **No PR below has been merged by an unauthorised session and no formal review decision exists
  on any open PR** — that remains the owner's gate.
