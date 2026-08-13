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
# Options:
#   --skip-schema          Skip DDL deploy (schema already applied)
#   --skip-seed            Skip action catalog + JSON schema seed
#   --skip-workflows       Skip deploy_workflow_definitions.sh
#   --schema-only          Deploy DDL only
#   --register-worker      Register wf.cluster/worker after seed (direct DB)
#   --worker-key NAME      external_worker_key (default: hostname)
#   --cluster KEY          cluster_key (default: epimethyl)
#   --with-cluster-security  Azure SQL/PG: apply cluster IP-binding columns
#   --verify               Read-only health check (schema artifacts, catalog drift, optional gateway ping)
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
WITH_CLUSTER_SECURITY=0
VERIFY_ONLY=0
WORKER_KEY="${WORKER_KEY:-$(hostname -s 2>/dev/null || echo worker-1)}"
CLUSTER_KEY="${CLUSTER_KEY:-epimethyl}"
WORKER_ENV_FILE="${WORKER_ENV_FILE:-/work/epimethyl/env/worker.env}"

usage() {
  sed -n '2,34p' "$0"
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
    --use-gateway-only)
      echo "Note: --use-gateway-only removed; catalog seed/deploy use direct DB" >&2
      shift
      ;;
    --with-cluster-security) WITH_CLUSTER_SECURITY=1; shift ;;
    --verify) VERIFY_ONLY=1; SKIP_SCHEMA=1; SKIP_SEED=1; SKIP_WORKFLOWS=1; shift ;;
    --worker-env) WORKER_ENV_FILE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
[[ -x "$PYTHON_BIN" ]] || PYTHON_BIN=python3

if [[ "$VERIFY_ONLY" -eq 1 ]]; then
  echo "==> Bootstrap verify (read-only) ..."
  fail=0
  cd "$REPO_ROOT"
  # shellcheck disable=SC1091
  if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
    source "$REPO_ROOT/.venv/bin/activate"
  fi
  if ! methyl-export-action-catalog --check; then fail=1; fi
  if ! methyl-export-domain-schemas --check; then fail=1; fi
  if [[ -f "$REPO_ROOT/schemas/actions/catalog.json" ]]; then
    n="$(python3 -c 'import json; print(len(json.load(open("schemas/actions/catalog.json"))["actions"]))' 2>/dev/null || echo 0)"
    echo "Catalog actions on disk: $n"
  fi
  if [[ -f /work/epimethyl/env/workflow_versions.json ]]; then
    echo "OK: workflow_versions.json present"
  else
    echo "WARN: /work/epimethyl/env/workflow_versions.json missing (run deploy_workflow_definitions.sh)"
  fi
  if curl -fsS -o /dev/null "${API_BASE%/}/health" 2>/dev/null || curl -fsS -o /dev/null "$API_BASE" 2>/dev/null; then
    echo "OK: gateway reachable at $API_BASE"
  else
    echo "WARN: gateway not reachable at $API_BASE (start methyl-gateway for live check)"
  fi
  bash "$SCRIPT_DIR/verify_work_layout.sh" || fail=1
  if [[ $fail -ne 0 ]]; then
    echo "Bootstrap verify failed." >&2
    exit 1
  fi
  echo "Bootstrap verify passed."
  exit 0
fi

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

if [[ "$SKIP_SEED" -eq 0 ]]; then
  echo "==> Exporting task schemas and action catalog ..."
  methyl-export-task-schemas
  methyl-export-action-catalog
  python scripts/check_task_input_config_boundary.py

  echo "==> Seeding wf.workflow_action + task JSON schemas (direct DB) ..."
  "$PYTHON_BIN" "$REPO_ROOT/workflow_engine/sql_mssql/seed_action_catalog.py" --regenerate-catalog --use-db
fi

# Configuration registry: import FS → cfg store → materialize onto /work (never secrets)
SKIP_CFG="${SKIP_CFG:-0}"
if [[ "$SKIP_CFG" -eq 0 ]]; then
  echo "==> Importing profiles/programs into cfg store and materializing onto /work ..."
  CFG_STORE="${METHYL_CFG_STORE:-/work/epimethyl/cfg-store}"
  WORK_ROOT="${METHYL_WORK_ROOT:-/work}"
  export PYTHONPATH="${REPO_ROOT}/workflow_engine:${PYTHONPATH:-}"
  "$PYTHON_BIN" -m cfg.cli --store-dir "$CFG_STORE" import-fs \
    --repo-root "$REPO_ROOT" \
    --work-root "$WORK_ROOT" || echo "WARN: methyl-cfg import-fs failed (non-fatal)"
  "$PYTHON_BIN" -m cfg.cli --store-dir "$CFG_STORE" link-site-assets \
    --site default --deploy-db \
    || echo "WARN: methyl-cfg link-site-assets failed (non-fatal; cfg.site_reference_asset stays empty)"
  "$PYTHON_BIN" -m cfg.cli --store-dir "$CFG_STORE" sync-actions \
    --repo-root "$REPO_ROOT" --from-json || echo "WARN: methyl-cfg sync-actions failed (non-fatal)"
  "$PYTHON_BIN" -m cfg.cli --store-dir "$CFG_STORE" materialize \
    --work-root "$WORK_ROOT" || echo "WARN: methyl-cfg materialize failed (non-fatal)"
fi

if [[ "$SKIP_WORKFLOWS" -eq 0 ]]; then
  echo "==> Deploying DomainProgram workflows (direct DB) ..."
  bash "$SCRIPT_DIR/deploy_workflow_definitions.sh"
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

Next:
  # Start worker-only gateway (optional for claim/submit)
  methyl-gateway

  # Register a worker if not done above
  bash scripts/register_worker.sh --cluster ${CLUSTER_KEY} --key ${WORKER_KEY}

EOF
