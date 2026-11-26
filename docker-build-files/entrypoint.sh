#!/usr/bin/env bash
set -euo pipefail

cd /ais

if [[ -z "${ENGINE_DB_HOST:-}" ]]; then
    echo "ERROR: ENGINE_DB_HOST environment variable is not set." >&2
    exit 1
fi

if [[ -z "${ENGINE_DB_PASS:-}" ]]; then
    echo "ERROR: ENGINE_DB_PASS environment variable is not set." >&2
    exit 1
fi

echo "Starting AIS API against ${ENGINE_DB_HOST}..."
exec gunicorn -c /ais/gunicorn.conf.py ais.api:app
