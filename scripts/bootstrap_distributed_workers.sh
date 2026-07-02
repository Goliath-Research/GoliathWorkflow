#!/usr/bin/env bash
# Bootstrap distributed remote worker testing (PostgreSQL or Azure SQL).
#
# End-to-end: deploy wf schema (optional) → export action catalog → seed DB →
# deploy DomainProgram workflows → optionally register a worker.
#
# Usage:
#   # PostgreSQL
#   export BACKEND_DB=postgres
#   export PGHOST=... PGDATABASE=postgres PGUSER=dba PGPASSWORD='...' PGSSLMODE=require
#   bash scripts/bootstrap_distributed_workers.sh
#
#   # Azure SQL
#   export BACKEND_DB=mssql
#   export AZURE_SQL_SERVER=....database.windows.net
#   export AZURE_SQL_DB=MethylPipeline
#   export AZURE_SQL_USER=... AZURE_SQL_PASSWORD='...'
#   bash scripts/bootstrap_distributed_workers.sh
#
#   # Gateway-only seed/deploy (no direct DB creds on operator host)
#   export WORKER_API_BASE=https://gateway.example.com/v1
#   export GATEWAY_ADMIN_BEARER_TOKEN='...'
#   bash scripts/bootstrap_distributed_workers.sh --skip-schema --use-gateway-only
#
# Options:
#   --skip-schema          Skip DDL deploy (schema already applied)
#   --skip-seed            Skip action catalog + JSON schema seed
#   --skip-workflows       Skip deploy_workflow_definitions.sh
#   --schema-only          Deploy DDL only
#   --register-worker      Register wf.cluster/worker after seed (direct DB)
#   --worker-key NAME      external_worker_key (default: hostname)
#   --cluster KEY          cluster_key (default: epimethyl)
#   --api-base URL         Gateway for workflow deploy (default: WORKER_API_BASE)
#   --use-gateway-only     Seed catalog via admin gateway (requires bearer token)
#   --with-cluster-security  Azure SQL/PG: apply cluster IP-binding columns
#   -h, --help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

API_BASE="${WORKER_API_BASE:-http://localhost:8080/v1}"
SKIP_SCHEMA=0
SKIP_SEED=0
SKIP_WORKFLOWS=0
SCHEMA_ONLY=0
REGISTER_WORKER=0
GATEWAY_ONLY=0
WITH_CLUSTER_SECURITY=0
WORKER_KEY="${WORKER_KEY:-$(hostname -s 2>/dev/null || echo worker-1)}"
CLUSTER_KEY="${CLUSTER_KEY:-epimethyl}"
WORKER_ENV_FILE="${WORKER_ENV_FILE:-/work/epimethyl/env/worker.env}"

usage() {
  sed -n '2,40p' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-schema) SKIP_SCHEMA=1; shift ;;
    --skip-seed) SKIP_SEED=1; shift ;;
    --skip-workflows) SKIP_WORKFLOWS=1; shift ;;
    --schema-only) SCHEMA_ONLY=1; SKIP_SEED=1; SKIP_WORKFLOWS=1; shift ;;
    --register-worker) REGISTER_WORKER=1; shift ;;
    --worker-key) WORKER_KEY="${2:-}"; shift 2 ;;
    --cluster) CLUSTER_KEY="${2:-}"; shift 2 ;;
    --api-base) API_BASE="${2:-}"; shift 2 ;;
    --use-gateway-only) GATEWAY_ONLY=1; shift ;;
    --with-cluster-security) WITH_CLUSTER_SECURITY=1; shift ;;
    --worker-env) WORKER_ENV_FILE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
[[ -x "$PYTHON_BIN" ]] || PYTHON_BIN=python3

# shellcheck disable=SC1091
source "$REPO_ROOT/.venv/bin/activate"

BACKEND="${BACKEND_DB:-postgres}"
if [[ "$BACKEND" == "sql" ]]; then BACKEND=mssql; fi

if [[ "$SKIP_SCHEMA" -eq 0 ]]; then
  echo "==> Deploying wf schema (${BACKEND}) ..."
  if [[ "$BACKEND" == "mssql" ]]; then
    DEPLOY_ARGS=()
    [[ "$WITH_CLUSTER_SECURITY" -eq 1 ]] && DEPLOY_ARGS+=(--with-cluster-security)
    bash "$REPO_ROOT/workflow_engine/sql_mssql/deploy_azure.sh" "${DEPLOY_ARGS[@]}"
  else
    bash "$REPO_ROOT/workflow_engine/sql_pg/deploy_azure.sh"
    if [[ "$WITH_CLUSTER_SECURITY" -eq 1 && -f "$REPO_ROOT/workflow_engine/sql_pg/wf_cluster_security_columns.sql" ]]; then
      echo "Applying wf_cluster_security_columns.sql ..."
      psql -q -v ON_ERROR_STOP=1 -f "$REPO_ROOT/workflow_engine/sql_pg/wf_cluster_security_columns.sql"
    fi
  fi
fi

if [[ "$SCHEMA_ONLY" -eq 1 ]]; then
  echo "Schema deploy complete (--schema-only)."
  exit 0
fi

if [[ "$GATEWAY_ONLY" -eq 0 && "$SKIP_SEED" -eq 0 ]]; then
  if [[ -n "${GATEWAY_ADMIN_BEARER_TOKEN:-}" || -n "${GATEWAY_ENTRA_BEARER_TOKEN:-}" ]]; then
    GATEWAY_ONLY=1
  fi
fi

if [[ "$SKIP_SEED" -eq 0 ]]; then
  echo "==> Exporting task schemas and action catalog (33 actions) ..."
  methyl-export-task-schemas
  methyl-export-action-catalog
  python scripts/check_task_input_config_boundary.py

  echo "==> Seeding wf.workflow_action + task JSON schemas ..."
  SEED_ARGS=(--regenerate-catalog)
  if [[ "$GATEWAY_ONLY" -eq 1 ]]; then
    SEED_ARGS+=(--use-gateway)
  else
    SEED_ARGS+=(--use-db)
  fi
  "$PYTHON_BIN" "$REPO_ROOT/workflow_engine/sql_mssql/seed_action_catalog.py" "${SEED_ARGS[@]}"
fi

if [[ "$SKIP_WORKFLOWS" -eq 0 ]]; then
  echo "==> Deploying DomainProgram workflows to ${API_BASE} ..."
  bash "$SCRIPT_DIR/deploy_workflow_definitions.sh" --api-base "$API_BASE"
fi

if [[ "$REGISTER_WORKER" -eq 1 ]]; then
  echo "==> Registering worker cluster=${CLUSTER_KEY} key=${WORKER_KEY} ..."
  bash "$SCRIPT_DIR/register_worker.sh" \
    --cluster "$CLUSTER_KEY" \
    --key "$WORKER_KEY" \
    --env-file "$WORKER_ENV_FILE"
fi

cat <<EOF

Bootstrap complete.

Backend: ${BACKEND}
Gateway: ${API_BASE}

Next steps for distributed workers:
  1. Copy deploy/env/gateway.$(if [[ "$BACKEND" == mssql ]]; then echo mssql; else echo postgres; fi).env.example → /work/epimethyl/env/gateway.env
  2. Start gateway: methyl-gateway (see deploy/systemd/methyl-gateway.service)
  3. On each GPU worker:
       bash scripts/register_worker.sh --cluster ${CLUSTER_KEY} --key <hostname>
       bash scripts/install_worker_systemd.sh
  4. Smoke test:
       export WORKER_STUB_EXTERNAL=1   # optional dry-run
       bash scripts/smoke_sample_prep.sh --api-base ${API_BASE}

Workflow version map: /work/epimethyl/env/workflow_versions.json
Docs: docs/deployment/distributed-workers-bootstrap.md

EOF
