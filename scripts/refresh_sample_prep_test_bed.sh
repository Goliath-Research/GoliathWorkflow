#!/usr/bin/env bash
# Refresh SamplePrep test bed against Azure SQL (or PostgreSQL via BACKEND_DB).
#
# Requires the same DB env as the REST gateway (see docs/deployment/production_runbook.md).
#
# Usage:
#   source /work/epimethyl/env/gateway.env   # or export AZURE_SQL_* manually
#   bash scripts/refresh_sample_prep_test_bed.sh
#
# Options:
#   --api-base URL     Gateway for workflow deploy (default: WORKER_API_BASE)
#   --skip-deploy      Only reseed action catalog (no workflow POST)
#   --skip-seed        Only deploy workflow definitions

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

API_BASE="${WORKER_API_BASE:-http://localhost:8080/v1}"
SKIP_DEPLOY=0
SKIP_SEED=0
GATEWAY_ONLY=0

usage() {
  cat <<'EOF'
Usage: scripts/refresh_sample_prep_test_bed.sh [options]

Refreshes action catalog + SamplePrep workflow definition for gateway testing.

Prefer admin gateway (no direct DB creds on operator host):
  export WORKER_API_BASE=http://localhost:8080/v1
  export GATEWAY_ADMIN_BEARER_TOKEN=<entra-jwt>
  bash scripts/refresh_sample_prep_test_bed.sh --use-gateway-only

Env (direct DB seed fallback):
  AZURE_SQL_SERVER, AZURE_SQL_DB, AZURE_SQL_USER, AZURE_SQL_PASSWORD
  BACKEND_DB=mssql

Env (PostgreSQL):
  BACKEND_DB=postgres
  POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

Options:
  --api-base URL     REST gateway base (default: WORKER_API_BASE)
  --skip-deploy      Skip deploy_workflow_definitions.sh
  --skip-seed        Skip seed_action_catalog.py
  --use-gateway-only Require admin gateway token; skip direct DB env check
  -h, --help         Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-base) API_BASE="${2:-}"; shift 2 ;;
    --skip-deploy) SKIP_DEPLOY=1; shift ;;
    --skip-seed) SKIP_SEED=1; shift ;;
    --use-gateway-only) GATEWAY_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
[[ -x "$PYTHON_BIN" ]] || PYTHON_BIN=python3

source "$REPO_ROOT/.venv/bin/activate"

BACKEND="${BACKEND_DB:-mssql}"
if [[ "$GATEWAY_ONLY" -eq 0 && "$SKIP_SEED" -eq 0 ]]; then
  if [[ -n "${GATEWAY_ADMIN_BEARER_TOKEN:-}" || -n "${GATEWAY_ENTRA_BEARER_TOKEN:-}" ]]; then
    GATEWAY_ONLY=1
  fi
fi

if [[ "$GATEWAY_ONLY" -eq 0 && "$SKIP_SEED" -eq 0 ]]; then
  if [[ "$BACKEND" == "mssql" || "$BACKEND" == "sql" ]]; then
    if [[ -z "${AZURE_SQL_SERVER:-}" || -z "${AZURE_SQL_DB:-}" ]]; then
      echo "Azure SQL env required for direct DB seed, or set GATEWAY_ADMIN_BEARER_TOKEN" >&2
      exit 1
    fi
    echo "Using Azure SQL backend: ${AZURE_SQL_SERVER}/${AZURE_SQL_DB}"
  else
    echo "Using PostgreSQL backend (BACKEND_DB=${BACKEND})"
  fi
else
  echo "Using admin gateway for catalog seed/deploy"
fi

echo "Exporting task schemas and action catalog..."
methyl-export-task-schemas
methyl-export-action-catalog

if [[ "$SKIP_SEED" -eq 0 ]]; then
  echo "Seeding wf.workflow_action + schemas..."
  SEED_ARGS=()
  if [[ -n "${GATEWAY_ADMIN_BEARER_TOKEN:-}" || -n "${GATEWAY_ENTRA_BEARER_TOKEN:-}" ]]; then
    SEED_ARGS+=(--use-gateway)
  fi
  "$PYTHON_BIN" "$REPO_ROOT/workflow_engine/sql_mssql/seed_action_catalog.py" "${SEED_ARGS[@]}"
fi

if [[ "$SKIP_DEPLOY" -eq 0 ]]; then
  echo "Deploying workflow definitions to ${API_BASE} ..."
  bash "$SCRIPT_DIR/deploy_workflow_definitions.sh" --api-base "$API_BASE"
fi

echo "SamplePrep test bed refresh complete."
