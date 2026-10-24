# Integration Testing & Real Infrastructure Guide (Milestone B11)

This document provides instructions for executing the AICTE Compliance AI integration test suite against real external infrastructure (PostgreSQL, Redis, Celery worker process, and optional ClamAV daemon).

---

## 1. Architecture Overview

While the standard test suite (`pytest -q backend/tests`) runs fast unit tests in-memory with SQLite and Celery eager execution, Milestone B11 introduces dedicated integration test suites under `backend/tests/integration/`:

1. **PostgreSQL Persistence & Migrations** (`test_postgres_migrations_and_persistence.py`):
   - Tests Alembic sequential migration upgrades and downgrades on a live PostgreSQL database.
   - Verifies PostgreSQL schema tables, foreign keys, unique constraints, and indexes.
   - Tests multi-institution data isolation across distinct database sessions.
   - Validates transaction rollback guarantees and audit preservation.

2. **Redis & Celery Background Processing** (`test_redis_celery_worker_processing.py`):
   - Operates with real Redis brokers (`task_always_eager=False`).
   - Dispatches tasks through the Celery queue.
   - Tests real background worker execution, state transitions, retry backoff, and idempotency.

3. **End-to-End Application Workflow** (`test_e2e_full_workflow.py`):
   - Full synthetic institution lifecycle: Authentication -> Application creation -> PDF intake -> Scanner gating -> Background extraction -> Validation orchestration -> Scrutiny report generation -> Human review actions -> Audit package export with Merkle tree tamper verification.

4. **Security & Failure Path Verification** (`test_security_and_failure_paths.py`):
   - Verifies cross-tenant access rejection, auditor role read-only enforcement, quarantine protections, and sanitised error envelopes.

---

## 2. Environment Variables

| Variable | Default (Local / CI) | Description |
|---|---|---|
| `RUN_LIVE_INTEGRATION_TESTS` | `false` | Must be set to `true` to run live service tests. If `true` and a service is unreachable, tests fail explicitly. |
| `DATABASE_URL` / `POSTGRES_TEST_URL` | `postgresql://aicte_test:aicte_test_pass@localhost:5432/aicte_test_db` | Connection string to isolated PostgreSQL test database. |
| `REDIS_URL` / `REDIS_TEST_URL` | `redis://localhost:6379/1` | Redis connection URL for Celery message broker. |
| `CELERY_BROKER_URL` | `${REDIS_URL}` | Celery broker URL. |
| `CELERY_TASK_ALWAYS_EAGER` | `false` | Must be `false` during live queue integration tests. |
| `AICTE_CLAMAV_HOST` | `localhost` | ClamAV daemon host (optional). |
| `AICTE_CLAMAV_PORT` | `3310` | ClamAV daemon TCP port (optional). |

> [!WARNING]
> Never point integration tests at production or shared databases. The test fixtures create, alter, and clean isolated test tables.

---

## 3. Local Startup with Docker Compose

To start the isolated integration services:

```bash
# Start PostgreSQL (port 5432) and Redis (port 6379)
docker compose -f docker-compose.integration.yml up -d

# Check service health
docker compose -f docker-compose.integration.yml ps
```

To include ClamAV (starts daemon on port 3310):

```bash
docker compose -f docker-compose.integration.yml --profile full up -d
```

---

## 4. Running the Integration Tests

Once the containers are healthy:

```bash
# 1. Apply migrations to the test database
python -m alembic -c backend/alembic.ini upgrade head

# 2. Run the integration test suite
$env:RUN_LIVE_INTEGRATION_TESTS="true"
$env:DATABASE_URL="postgresql://aicte_test:aicte_test_pass@localhost:5432/aicte_test_db"
$env:REDIS_URL="redis://localhost:6379/1"
$env:CELERY_TASK_ALWAYS_EAGER="false"
python -m pytest -v backend/tests/integration
```

---

## 5. Teardown

To shut down and remove the integration containers and volumes:

```bash
docker compose -f docker-compose.integration.yml down -v
```
