#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_DIR"

export PYTHONUNBUFFERED=TRUE

if [[ -f "$REPO_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_DIR/.env"
    set +a
fi

export ENGINE_DB_HOST="${LOCAL_ENGINE_DB_HOST:-localhost}"
export ENGINE_DB_PASS="${LOCAL_ENGINE_DB_PASS:-${ENGINE_DB_PASS:-}}"

echo "Starting NG911 address points report..."
python3 "$REPO_DIR/ais/engine/bin/output_address_points_for_ng911.py"

echo "Running make_reports.py..."
python3 "$REPO_DIR/ais/engine/bin/make_reports.py"

echo "Engine reports have completed."
