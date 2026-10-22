# Three-person technical work split

**Structure:** Frontend / Backend / AI  
**Status:** Folder ownership plan; not a claim that all three applications are implemented.  
**Base:** `research/grounded-foundation` (still unmerged into `main`).

## Repository layout

```text
aicte-compliance-ai/
├── frontend/             # Contributor 1 — UI and user workflows
├── backend/              # Contributor 2 — API, validation, persistence and security
├── ai/                   # Contributor 3 — OCR, extraction and AI/evaluation
├── docs/                 # Shared project and research documentation
├── .github/              # Shared CI/workflow configuration
└── WORKSTREAMS.md        # Ownership and integration rules
```

The `backend/` folder already exists and contains the current FastAPI prototype. This PR does not move or rewrite existing application code. `frontend/` and `ai/` start with ownership/readme files; implementation can be added there independently.

## Ownership

| Person | Owns | Main deliverables |
|---|---|---|
| Contributor 1 | `frontend/` | Applicant/reviewer UI, forms, status/evidence views, accessibility and frontend tests |
| Contributor 2 | `backend/` | API contracts/implementation, validation, authorization, tenant isolation, persistence and audit controls |
| Contributor 3 | `ai/` | OCR adapters/pipeline, field extraction, normalization, confidence/evidence, synthetic corpus and evaluation |

Assign the three actual names before work starts. The folders are boundaries for independent work; they do not by themselves establish production readiness.

## Strict non-overlap rules

1. Each person edits only their owned folder during independent work.
2. Do not edit another person's folder. Open an issue or ask its owner to make the change.
3. `docs/`, `.github/`, root files, dependency manifests and shared contracts are shared surfaces: propose changes separately and obtain agreement from all three owners.
4. Do not move existing backend OCR code into `ai/` as part of this folder setup. Contributor 3 develops in `ai/`; a separate integration PR can later migrate/adapt components after interfaces and tests are agreed.
5. Work on separate branches and submit separate PRs. Never push directly to `main` or merge your own PR.
6. Define API/schema contracts and synthetic examples before cross-folder integration. No contributor should import another contributor's private implementation before the interface is agreed.
7. Use synthetic test data only. OCR output is advisory and requires human review. Unverified regulations must not be encoded as active rules.
8. No public upload, production rule activation or deployment until authentication, authorization, tenant isolation, private storage, malware scanning, audit, retention/deletion and official-source review gates are met.

## Integration process

1. Each owner commits only within their folder and opens a PR.
2. All three review the shared contracts and dependency assumptions.
3. A separate integration PR handles cross-folder wiring, root configs and CI.
4. Run tests on the exact integration head SHA and record the evidence before any merge.

This plan creates a clear frontend/backend/AI split while preserving the existing prototype.
