#!/usr/bin/env bash
# Privileged-host database bootstrap: schema (optional) + Python entity populate.
#
# GPU workers must not run this script. It applies dual-dialect DDL via
# workflow_engine/sql_{mssql,pg}/deploy_azure.sh, then seeds process packs,
# analytes, the action catalog, enrichment presets, and DomainProgram graphs.
#
# Usage:
#   # PostgreSQL (canonical DB name: goliath)
#   export BACKEND_DB=postgres
#   export PGHOST=... PGDATABASE=goliath PGUSER=dba PGPASSWORD='...' PGSSLMODE=require
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
#   --skip-seed            Skip Python entity populate
#   --skip-workflows       Skip deploy_workflow_definitions.sh
#   --schema-only          Deploy DDL only
#   --with-cluster-security  Azure SQL/PG: apply cluster IP-binding columns
#   --verify               Read-only catalog/schema-script check (no DDL/seed)
#   -h, --help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SKIP_SCHEMA=0
SKIP_SEED=0
SKIP_WORKFLOWS=0
SCHEMA_ONLY=0
WITH_CLUSTER_SECURITY=0
VERIFY_ONLY=0

usage() {
  sed -n '2,32p' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-schema) SKIP_SCHEMA=1; shift ;;
    --skip-seed) SKIP_SEED=1; shift ;;
    --skip-workflows) SKIP_WORKFLOWS=1; shift ;;
    --schema-only) SCHEMA_ONLY=1; SKIP_SEED=1; SKIP_WORKFLOWS=1; shift ;;
    --register-worker|--worker-key|--cluster|--worker-env|--api-base)
      echo "Worker register/enroll is not part of database bootstrap." >&2
      echo "Use methyl-worker enroll on GPU VMs after the gateway is up." >&2
      exit 2
      ;;
    --use-gateway-only)
      echo "Note: --use-gateway-only removed; catalog seed/deploy use direct DB" >&2
      shift
      ;;
    --with-cluster-security) WITH_CLUSTER_SECURITY=1; shift ;;
    --verify) VERIFY_ONLY=1; SKIP_SCHEMA=1; SKIP_SEED=1; SKIP_WORKFLOWS=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
[[ -x "$PYTHON_BIN" ]] || PYTHON_BIN=python3

if [[ "$VERIFY_ONLY" -eq 1 ]]; then
  echo "==> Database bootstrap verify (read-only) ..."
  fail=0
  cd "$REPO_ROOT"
  # shellcheck disable=SC1091
  if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
    source "$REPO_ROOT/.venv/bin/activate"
  fi
  if ! methyl-export-action-catalog --check; then fail=1; fi
  if ! methyl-export-domain-schemas --check; then fail=1; fi
  if ! "$PYTHON_BIN" "$SCRIPT_DIR/check_sql_deploy_twins.py"; then fail=1; fi
  if [[ -f "$REPO_ROOT/schemas/actions/catalog.json" ]]; then
    n="$(python3 -c 'import json; print(len(json.load(open("schemas/actions/catalog.json"))["actions"]))' 2>/dev/null || echo 0)"
    echo "Catalog actions on disk: $n"
  fi
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
if [[ "$BACKEND" == "postgres" ]]; then
  export POSTGRES_DB="${POSTGRES_DB:-${PGDATABASE:-goliath}}"
  export PGDATABASE="${PGDATABASE:-$POSTGRES_DB}"
fi

if [[ "$SKIP_SCHEMA" -eq 0 ]]; then
  echo "==> Deploying schema (${BACKEND}) ..."
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

  echo "==> Seeding wf.workflow_action + wf.data_type ..."
  "$PYTHON_BIN" "$REPO_ROOT/workflow_engine/sql_mssql/seed_action_catalog.py" --regenerate-catalog --use-db

  echo "==> Syncing cfg process packs / analytes / profiles ..."
  SYNC_BACKEND="$BACKEND"
  [[ "$SYNC_BACKEND" == "mssql" ]] || SYNC_BACKEND=postgres
  "$PYTHON_BIN" "$REPO_ROOT/scripts/sync_cfg_profiles_and_action_catalog.py" \
    --backend "$SYNC_BACKEND" --skip-seed

  echo "==> Process-pack catalog SQL + row sync ..."
  bash "$SCRIPT_DIR/deploy_process_pack_catalog.sh" --backend "$SYNC_BACKEND" --sync

  echo "==> Enrichment library presets ..."
  export PYTHONPATH="${REPO_ROOT}/workflow_engine:${PYTHONPATH:-}"
  CFG_STORE="${METHYL_CFG_STORE:-$REPO_ROOT/.cfg-store}"
  mkdir -p "$CFG_STORE"
  "$PYTHON_BIN" -m cfg.cli --store-dir "$CFG_STORE" sync-library-presets \
    --repo-root "$REPO_ROOT"
fi

if [[ "$SKIP_WORKFLOWS" -eq 0 ]]; then
  echo "==> Deploying DomainProgram workflows (direct DB) ..."
  bash "$SCRIPT_DIR/deploy_workflow_definitions.sh"
fi

cat <<EOF

Database bootstrap complete (privileged host).

Next:
  1. Deploy the gateway VM (scripts/provision_gateway_node.sh) — no /work required
  2. Portal-preregister each GPU public IP
  3. First GPU worker: scripts/provision_worker_node.sh (seeds /work, then enrolls)
  4. Later GPUs: same script (enroll first, VM-local only)

EOF
