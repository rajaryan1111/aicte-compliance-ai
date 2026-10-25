#!/usr/bin/env bash
# Single-instance startup for the Render deployment (see
# docs/development/DEPLOYMENT.md). Runs clamd + the Celery worker (with
# embedded beat for the recovery sweep) + the FastAPI server in one instance
# so the durable storage disk at STORAGE_LOCAL_DIR is shared by the API and
# the worker. Exactly one worker with --beat runs here by construction; if you
# ever scale instances, move beat to a single standalone `celery beat` so the
# recovery sweep is scheduled exactly once.
#
# Fail-closed boot: if the scan gate cannot start, this script exits non-zero
# and Render restarts the instance. It never serves traffic without a working
# ClamAV daemon.
set -euo pipefail

echo "[entrypoint] refreshing ClamAV signature database..."
if ! freshclam --stdout; then
    echo "[entrypoint] freshclam failed; continuing only if a signature database already exists" >&2
    if ! ls /var/lib/clamav/main.cvd /var/lib/clamav/main.cld /var/lib/clamav/bytecode.cvd 1>/dev/null 2>&1; then
        echo "[entrypoint] no signature database present and freshclam failed — refusing to start" >&2
        exit 1
    fi
fi

echo "[entrypoint] starting clamd (scan gate)..."
clamd --config-file=scripts/clamd.conf &
CLAMD_PID=$!

python - <<'PY'
import socket, sys, time

deadline = time.time() + 120
while time.time() < deadline:
    try:
        with socket.create_connection(("127.0.0.1", 3310), timeout=2) as sock:
            sock.sendall(b"zPING\0")
            if b"PONG" in sock.recv(1024):
                print("[entrypoint] clamd ready")
                sys.exit(0)
    except OSError:
        pass
    time.sleep(2)
sys.exit("[entrypoint] clamd did not become ready within 120s")
PY

echo "[entrypoint] applying database migrations..."
python -m alembic -c backend/alembic.ini upgrade head

echo "[entrypoint] starting Celery worker with embedded beat..."
python -m celery -A backend.app.worker.celery_app worker --beat -l INFO -c 2 &
WORKER_PID=$!

echo "[entrypoint] starting API server on port ${PORT:-10000}..."
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-10000}" &
API_PID=$!

# If any supervised process exits, take the instance down so Render restarts
# it; a half-running instance (e.g. API up, worker dead) must not look healthy.
wait -n "$CLAMD_PID" "$WORKER_PID" "$API_PID"
echo "[entrypoint] a supervised process exited; shutting down for a clean restart" >&2
kill "$CLAMD_PID" "$WORKER_PID" "$API_PID" 2>/dev/null || true
exit 1
