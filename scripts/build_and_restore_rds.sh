#!/usr/bin/env bash
# =============================================================================
# AIS Engine Build, Test, and RDS Restore Script
#
# Runs on the dedicated engine build host:
#   1. Builds all engine tables into local PostgreSQL via `ais engine build`
#   2. Runs engine & API tests against the local build
#   3. Dumps the local DB (`pg_dump`)
#   4. Restores the dump to the inactive RDS instance (or `dev` with --dev)
#   5. Runs engine validation tests against the restored RDS instance
#   6. Generates downstream reports
#
# RDS Blue-Green swapping is intentionally decoupled into:
#   `python3 scripts/rds_blue_green.py swap` (or pass `--auto-swap`).
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

DEV_DEPLOY=false
TARGET_COLOR=""
SKIP_BUILD=false
SKIP_TESTS=false
SKIP_REPORTS=false
AUTO_SWAP=false
SKIP_API_TESTS=""
SKIP_ENGINE_TESTS=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dev)              DEV_DEPLOY=true; shift ;;
        --target)           TARGET_COLOR="$2"; shift 2 ;;
        --skip-build)       SKIP_BUILD=true; shift ;;
        --skip-tests)       SKIP_TESTS=true; shift ;;
        --skip-reports)     SKIP_REPORTS=true; shift ;;
        --auto-swap)        AUTO_SWAP=true; shift ;;
        --skip-api-tests)   SKIP_API_TESTS="$2"; shift 2 ;;
        --skip-engine-tests) SKIP_ENGINE_TESTS="$2"; shift 2 ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

if [[ -f "$REPO_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_DIR/.env"
    set +a
fi

LOG_DIR="$REPO_DIR/ais/engine/log"
DUMP_FILE="$REPO_DIR/ais/engine/backup/ais_engine.dump"
DATESTAMP="$(date +%Y-%m-%d)"
mkdir -p "$LOG_DIR" "$(dirname "$DUMP_FILE")"

notify_teams() {
    local msg="$1"
    echo "[AIS] $msg"
    if [[ -n "${TEAMS_WEBHOOK_URL:-}" ]]; then
        curl -s -H "Content-Type: application/json" \
            -d "{\"text\": \"<pre>${msg}</pre>\"}" \
            "$TEAMS_WEBHOOK_URL" >/dev/null || true
    fi
}

# 1. Determine active & target RDS instances
if $DEV_DEPLOY; then
    TARGET_COLOR="dev"
    ACTIVE_COLOR="$(python3 "$REPO_DIR/scripts/rds_blue_green.py" active-color)"
else
    ACTIVE_COLOR="$(python3 "$REPO_DIR/scripts/rds_blue_green.py" active-color)"
    if [[ -z "$TARGET_COLOR" ]]; then
        TARGET_COLOR="$(python3 "$REPO_DIR/scripts/rds_blue_green.py" inactive-color)"
    fi
fi

get_rds_host() {
    local color="$1"
    case "$color" in
        blue)  echo "${BLUE_RDS_HOST:-ais-engine-blue.cfuoybzycpox.us-east-1.rds.amazonaws.com}" ;;
        green) echo "${GREEN_RDS_HOST:-ais-engine-green.cfuoybzycpox.us-east-1.rds.amazonaws.com}" ;;
        dev)   echo "${DEV_RDS_HOST:-ais-engine-dev.cfuoybzycpox.us-east-1.rds.amazonaws.com}" ;;
        *)     echo "Invalid RDS color: $color" >&2; exit 1 ;;
    esac
}

PROD_DB_HOST="$(get_rds_host "$ACTIVE_COLOR")"
TARGET_DB_HOST="$(get_rds_host "$TARGET_COLOR")"
echo "Active prod RDS: $ACTIVE_COLOR ($PROD_DB_HOST)"
echo "Restore target:  $TARGET_COLOR ($TARGET_DB_HOST)"

# 2. Build local engine tables
if ! $SKIP_BUILD; then
    notify_teams "Starting AIS engine build on $(hostname)."
    export ENGINE_DB_HOST="${LOCAL_ENGINE_DB_HOST:-localhost}"
    export ENGINE_DB_PASS="${LOCAL_ENGINE_DB_PASS:?LOCAL_ENGINE_DB_PASS must be set}"
    ais engine build \
        > >(tee -a "$LOG_DIR/build_log_${DATESTAMP}.txt") \
        2> >(tee -a "$LOG_DIR/build_errors_${DATESTAMP}.txt" >&2)
    notify_teams "AIS engine build completed."
fi

# 3. Run local engine & API tests
if ! $SKIP_TESTS; then
    echo "Running engine tests (localhost vs $PROD_DB_HOST)..."
    ENGINE_TO_TEST="localhost" \
    ENGINE_TO_COMPARE="$PROD_DB_HOST" \
    ENGINE_DB_HOST="localhost" \
    ENGINE_DB_PASS="${LOCAL_ENGINE_DB_PASS:?LOCAL_ENGINE_DB_PASS must be set}" \
        pytest "$REPO_DIR/ais/tests/engine" -vvv -ra --tb=short ${SKIP_ENGINE_TESTS:+--skip="$SKIP_ENGINE_TESTS"}

    echo "Running API tests against localhost..."
    ENGINE_DB_HOST="localhost" \
    ENGINE_DB_PASS="$LOCAL_ENGINE_DB_PASS" \
        pytest "$REPO_DIR/ais/tests/api" -vvv -ra --tb=short ${SKIP_API_TESTS:+--skip="$SKIP_API_TESTS"}
fi

# 4. Dump local database
echo "Dumping local database to $DUMP_FILE..."
rm -f "$DUMP_FILE"
PGPASSWORD="$LOCAL_ENGINE_DB_PASS" pg_dump \
    -Fcustom -Z0 --create --clean \
    -U "${LOCAL_ENGINE_DB_USER:-ais_engine}" \
    -h "${LOCAL_ENGINE_DB_HOST:-localhost}" \
    -n public "${LOCAL_ENGINE_DB_NAME:-ais_engine}" > "$DUMP_FILE"

# 5. Restore to target RDS
notify_teams "Restoring AIS engine DB to $TARGET_COLOR ($TARGET_DB_HOST)..."
python3 "$REPO_DIR/scripts/rds_blue_green.py" wait --target "$TARGET_COLOR"

RDS_SUPER_PASS="${RDS_SUPER_ENGINE_DB_PASS:?RDS_SUPER_ENGINE_DB_PASS must be set}"
RDS_APP_PASS="${RDS_ENGINE_DB_PASS:?RDS_ENGINE_DB_PASS must be set}"

PGPASSWORD="$RDS_SUPER_PASS" psql -U postgres -h "$TARGET_DB_HOST" -d ais_engine \
    -c "DROP SCHEMA IF EXISTS public CASCADE;"
PGPASSWORD="$RDS_APP_PASS" psql -U ais_engine -h "$TARGET_DB_HOST" -d ais_engine \
    -c "CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO postgres; GRANT ALL ON SCHEMA public TO public;"
PGPASSWORD="$RDS_SUPER_PASS" psql -U postgres -h "$TARGET_DB_HOST" -d ais_engine \
    -c "CREATE EXTENSION postgis WITH SCHEMA public; CREATE EXTENSION pg_trgm WITH SCHEMA public; GRANT ALL ON TABLE public.spatial_ref_sys TO ais_engine;"

PGPASSWORD="$RDS_APP_PASS" pg_restore -v -j 6 -h "$TARGET_DB_HOST" -d ais_engine -U ais_engine -c "$DUMP_FILE" || true

DB_SIZE_BYTES="$(PGPASSWORD="$RDS_SUPER_PASS" psql -U postgres -h "$TARGET_DB_HOST" -d ais_engine -AXqtc "SELECT pg_database_size('ais_engine');")"
DB_SIZE_GB=$(( DB_SIZE_BYTES / 1024 / 1024 / 1024 ))
echo "Restored DB size: ${DB_SIZE_GB} GB"
if (( DB_SIZE_GB < 8 )); then
    notify_teams "ERROR: Restored DB on $TARGET_DB_HOST is only ${DB_SIZE_GB} GB (< 8 GB)."
    exit 1
fi

python3 "$REPO_DIR/scripts/rds_blue_green.py" wait --target "$TARGET_COLOR"

# 6. Validate restored RDS against active prod RDS
if ! $SKIP_TESTS && ! $DEV_DEPLOY; then
    echo "Running engine validation tests ($TARGET_DB_HOST vs $PROD_DB_HOST)..."
    ENGINE_TO_TEST="$TARGET_DB_HOST" \
    ENGINE_TO_COMPARE="$PROD_DB_HOST" \
    ENGINE_DB_HOST="$TARGET_DB_HOST" \
    ENGINE_DB_PASS="$RDS_APP_PASS" \
        pytest "$REPO_DIR/ais/tests/engine" -vvv -ra --tb=short ${SKIP_ENGINE_TESTS:+--skip="$SKIP_ENGINE_TESTS"}
fi

# 7. Optional automatic blue-green RDS swap
if $AUTO_SWAP && ! $DEV_DEPLOY; then
    python3 "$REPO_DIR/scripts/rds_blue_green.py" swap --target "$TARGET_COLOR"
fi

# 8. Downstream reports
if ! $SKIP_REPORTS && ! $DEV_DEPLOY; then
    bash "$REPO_DIR/ais/engine/bin/make_reports.sh"
fi

notify_teams "AIS engine build & restore to $TARGET_COLOR finished successfully."
