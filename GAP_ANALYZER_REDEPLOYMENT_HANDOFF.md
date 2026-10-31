# Gap Analyzer backend redeployment handoff

Date: 2026-10-31
Repository: `https://github.com/rajaryan1111/aicte-compliance-ai`
Branch: `feat/complete-intelligent-compliance-gap-analyzer`
Required commit: update to the final commit reported by the accompanying release report after this handoff is committed.
PR: #20, draft; do not merge as part of this handoff.

## Confirmed service and deployment state

The Render workspace inspection identified `aicte-compliance-api-preview` (`srv-dbefphcs728c73c3q50g`), currently configured to the old `arena/5614862e-aicte-compliance-ai` branch and commit `1229e3227c20a9f4dfdad1d9306588a4a437ef9f`. It is on Free plan, root directory `.`, Singapore region, and currently has no health-check path. The deployed OpenAPI schema has no Gap Analyzer paths. Do not deploy until the responsible operator confirms this is the intended preview service and agrees the target database/data.

The inspected database resource is `aicte-compliance-db` (`dpg-dbefnlo473hc73d5or0g-a`), database `aicte_compliance_db`, Singapore region. Read-only metadata access from the available connector was blocked by the external IP allowlist. No Render settings, secrets, DB settings, allowlists, or production data were changed in this task.

## Repository configuration to reconcile before deployment

The checked-in `render.yaml` currently declares an Oregon service/database named `aicte-db` and database `aicte_compliance`; this does not match the inspected Singapore service/database above. It also runs `cd backend && python -m alembic upgrade head`, while `backend/alembic.ini` has a `backend/alembic` script location; from that working directory this can resolve to a duplicated `backend/backend/alembic` path. Do not apply this Blueprint blindly or allow it to create a second database. Reconcile the Blueprint with the intended existing service/database, preserve existing data, and validate the migration command before using it.

Observed service commands are root `.`; build `pip install -r backend/requirements.txt`; start `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`. A repository-root migration command consistent with the checked-in Alembic configuration is:

```sh
python -m alembic -c backend/alembic.ini upgrade head
```

Use a database backup/snapshot and the approved migration procedure before applying any migration. Never run a database reset/downgrade against the shared service. Review the new revision and current DB revision first. Migration command above is a repository-derived recommendation, not a command executed against Render.

## Environment variable names

Set/retain values using the authorized secret-management process; this handoff contains names only:

- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `CELERY_TASK_ALWAYS_EAGER`
- `PYTHONPATH`
- `CORS_ALLOWED_ORIGIN`
- Frontend build-time `VITE_API_BASE_URL`

Do not rotate or print secret values as part of feature deployment.

## Safe deployment and verification sequence

1. Fetch the repository, check out `feat/complete-intelligent-compliance-gap-analyzer`, and verify the exact final commit listed in the release report. Keep PR #20 draft.
2. Confirm the target is the existing preview service and obtain the database owner’s confirmation of the database and backup. Resolve the Blueprint/service/database mismatch above without creating or replacing a DB.
3. Confirm a backup and current Alembic revision. Apply only the reviewed forward migration using the approved service procedure.
4. Deploy the preview backend from the required branch/commit with the observed start command. Configure a health check at `/health/ready` only after the operator confirms that endpoint is suitable for their service checks.
5. Verify `GET /health`, `GET /health/ready`, then inspect `/openapi.json`. Confirm it includes `/api/v1/applications/{application_id}/gap-requirements`, `/requirement-evidence-mappings`, `/gap-analysis`, and validation-run assessment routes. A healthy process alone is insufficient.
6. Build/deploy the frontend preview with `VITE_API_BASE_URL` pointing to the intended preview API and the allowed origin configured in `CORS_ALLOWED_ORIGIN`.
7. With test accounts for two institutions, run the authenticated workflow: list requirements/documents, map an extracted field, review its evidence, run an assessment, open a saved run, inspect finding/source evidence, refresh, and verify saved decisions. Confirm unauthenticated requests fail and cross-institution application/document/run IDs cannot be read or changed.
8. Capture deployment commit, migration revision, probe results, and test outcomes in PR #20. Production deployment remains a separate authorized release step.

## Database/RLS inspection still required

The live metadata/RLS query could not run because the database rejected the connector address under its IP allowlist. Do not widen the allowlist just for this handoff. An authorized DBA can run these read-only checks using an approved connection:

```sql
SELECT current_database();
SELECT version_num FROM alembic_version;
SELECT schemaname, tablename, rowsecurity
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename;
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename, policyname;
```

This is an external release gate. Local SQLite tenant-isolation tests do not prove PostgreSQL RLS behavior.

## Rollback precautions

Keep the previous service deployment available for rollback; record its commit and health. Do not roll back schema destructively. If the new service fails, restore the prior application deployment and follow the DBA’s forward-fix/backup recovery plan for any migration compatibility issue. Do not point the new code at an unconfirmed database or change allowlists as a deployment shortcut.
