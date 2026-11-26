# Address Information System (AIS)

AIS provides address verification, standardization, geocoding, and City data integration for Philadelphia.

See [docs/APIUSAGE.md](docs/APIUSAGE.md) for API endpoint documentation.

## Requirements

- **Python 3.14+**
- **PostgreSQL + PostGIS** (`postgis` and `pg_trgm` extensions)
- Access to the private `passyunk_automation` repository (`passyunk-private.key` + `ssh-config`) for building the container or installing locally

## Configuration

All secrets and database connection settings are unified under environment variables (auto-loaded from `.env` if present). See [.env.example](.env.example) for all available variables.

## Running the API (Docker / EKS)

Build the multi-stage Python 3.14 image (the private SSH key is used only in the builder stage and is never present in the runtime image):

```bash
docker build -t ais:latest .
```

Run against an RDS (or local) engine database:

```bash
export ENGINE_DB_HOST='ais-engine-dev.cfuoybzycpox.us-east-1.rds.amazonaws.com'
export ENGINE_DB_PASS='<password>'

docker run -itd --network host --name ais -p 8080:8080 \
  -e ENGINE_DB_HOST="$ENGINE_DB_HOST" \
  -e ENGINE_DB_PASS="$ENGINE_DB_PASS" \
  ais:latest

curl "http://localhost:8080/search/1234%20market"
```

Or using Docker Compose:

```bash
docker compose up --build -d
```

## Local Development

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements-engine.txt
pip install -e .
cp .env.example .env  # fill in your values

gunicorn -c gunicorn.conf.py ais.api:app
```

## Building the Engine Database

The engine build pipeline is managed via the `ais engine` CLI:

```bash
# List all pipeline stages and steps
ais engine list

# Run the full build into local PostgreSQL
ais engine build

# Resume from a specific step or run a single stage/step
ais engine build --from make_address_summary
ais engine build --stage summaries
ais engine build --only make_service_area_summary
```

To run the full build, test, dump, and restore to the inactive RDS instance (or `dev` RDS) on the build server:

```bash
# Restore to dev RDS
./scripts/build_and_restore_rds.sh --dev

# Restore to inactive blue/green RDS (without swapping)
./scripts/build_and_restore_rds.sh
```

## RDS Blue-Green Swap

Swapping the active RDS instance (`blue` <-> `green`) is decoupled from the build script and does not touch ECS or ALB DNS. It validates RDS availability and row counts, then updates AWS SSM Parameter Store (and optionally a Route53 DB CNAME):

```bash
# Check active/inactive RDS status
python3 scripts/rds_blue_green.py status

# Dry-run swap
python3 scripts/rds_blue_green.py swap --dry-run

# Execute swap
python3 scripts/rds_blue_green.py swap
```

You can also trigger the swap manually via the **RDS Blue-Green Swap** GitHub Actions workflow (`.github/workflows/rds-blue-green-swap.yml`).

## Testing

```bash
# Unit tests (no DB required)
pytest ais/tests/api/test_paginator.py -v

# API integration tests (requires ENGINE_DB_HOST and ENGINE_DB_PASS)
pytest ais/tests/api -v

# Engine comparison tests (compares ENGINE_TO_TEST against ENGINE_TO_COMPARE)
ENGINE_TO_TEST=localhost ENGINE_TO_COMPARE=$BLUE_RDS_HOST pytest ais/tests/engine -v
```
