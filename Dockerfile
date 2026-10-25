# Single-service image for the Render deployment — see
# docs/development/DEPLOYMENT.md for the full runbook and the reason this is
# intentionally ONE service (API + Celery worker/beat + clamd): the storage
# backend is local-disk (backend/app/core/storage.py) and a Render disk is
# visible to exactly one service, so API and worker must share an instance to
# share durable private document storage. Do not split the worker out while
# STORAGE_LOCAL_DIR is the only storage backend.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# clamav + clamav-daemon: the real scan engine behind the fail-closed malware
# gate (never a test double in production). clamav-freshclam keeps the
# signature database updatable; the entrypoint refreshes it at every boot.
RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        clamav \
        clamav-daemon \
        clamav-freshclam \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/run/clamav /var/lib/clamav /var/log/clamav \
    && chown -R clamav:clamav /var/run/clamav /var/lib/clamav /var/log/clamav

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

# Seed the signature database at build time when the ClamAV CDN is reachable.
# Failure is not fatal here: the entrypoint retries at boot and refuses to
# serve with a non-functioning scan gate (fail-closed), so a build without
# signatures still deploys safely instead of silently skipping scanning.
RUN freshclam --stdout || echo "freshclam seed at build time failed; entrypoint will retry at boot"

COPY backend/ backend/
COPY scripts/ scripts/
RUN chmod +x scripts/render_entrypoint.sh

# Durable private document storage lives on the Render disk mounted here.
ENV STORAGE_LOCAL_DIR=/data

# Render injects PORT at runtime (default below for local runs).
EXPOSE 10000

CMD ["bash", "scripts/render_entrypoint.sh"]
