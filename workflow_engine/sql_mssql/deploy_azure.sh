#!/usr/bin/env bash
# Deploy MethylPipeline wf schema parity scripts to Azure SQL.
#
# Prerequisites:
#   - sqlcmd (SQL Server command-line tools)
#   - Base wf schema already deployed (MethylPipeline.sql or MethylPipelineDB_Script.sql)
#   - AZURE_SQL_* env vars set (or METHYLPIPELINE_DB ODBC connection string)
#
# Usage:
#   export AZURE_SQL_SERVER=your-server.database.windows.net
#   export AZURE_SQL_DB=MethylPipeline
#   export AZURE_SQL_USER=sql-admin
#   export AZURE_SQL_PASSWORD='...'
#   ./workflow_engine/sql_mssql/deploy_azure.sh
#
# Optional:
#   export SQLCMD_TRUST_SERVER_CERTIFICATE=1   # dev / private endpoints
#   ./workflow_engine/sql_mssql/deploy_azure.sh --with-cluster-security

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

WITH_CLUSTER_SECURITY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-cluster-security) WITH_CLUSTER_SECURITY=1; shift ;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if ! command -v sqlcmd >/dev/null 2>&1; then
  echo "sqlcmd not found. Install mssql-tools18 or mssql-tools." >&2
  exit 1
fi

SERVER="${AZURE_SQL_SERVER:-}"
DATABASE="${AZURE_SQL_DB:-MethylPipeline}"
USER="${AZURE_SQL_USER:-}"
PASSWORD="${AZURE_SQL_PASSWORD:-}"

if [[ -z "$SERVER" || -z "$USER" || -z "$PASSWORD" ]]; then
  echo "Set AZURE_SQL_SERVER, AZURE_SQL_USER, AZURE_SQL_PASSWORD (and optionally AZURE_SQL_DB)." >&2
  exit 1
fi

SQLCMD_ARGS=(
  -S "$SERVER"
  -d "$DATABASE"
  -U "$USER"
  -P "$PASSWORD"
  -b
  -V 16
)

if [[ "${SQLCMD_TRUST_SERVER_CERTIFICATE:-0}" == "1" ]]; then
  SQLCMD_ARGS+=(-C)
fi

run_sql() {
  local path="$1"
  echo "Applying $(basename "$path") ..."
  sqlcmd "${SQLCMD_ARGS[@]}" -i "$path"
}

SCRIPTS=(
  wf_scope_readpath.sql
  wf_instance_extension.sql
  wf_json_column_alignment.sql
  wf_drop_monte_carlo_tables.sql
  wf_sql_branch_parity.sql
  wf_sql_runtime_parity.sql
  wf_sql_scope_writepath_parity.sql
  wf_sp_delete_workflow_def.sql
  wf_sql_foreach_support.sql
  wf_sql_scope_encoding_parity.sql
  wf_repository_api.sql
  wf_json_native_params.sql
  wf_workflow_edge_index_fixup.sql
  wf_worker_api_contract.sql
  wf_worker_enrollment.sql
  portal_worker_enrollment_api.sql
  wf_action_schema.sql
  wf_repo_upsert_workflow_action.sql
  wf_action_dispatch_metadata.sql
  wf_repo_create_workflow_graph.sql
  wf_apply_validation_plan.sql
  wf_hyperparameter_set.sql
  wf_sql_collection_bindings.sql
  portal_workflow_api.sql
  wf_drop_platform_sample_storage.sql
  cfg_schema.sql
  cfg_registry_tables.sql
  cfg_json_column_alignment.sql
  cfg_wf_relationships.sql
  cfg_repo_api.sql
  portal_resource_profile.sql
  cfg_portal_api.sql
)

echo "Target: server=$SERVER database=$DATABASE user=$USER"

for name in "${SCRIPTS[@]}"; do
  path="$SCRIPT_DIR/$name"
  if [[ ! -f "$path" ]]; then
    echo "Missing script: $path" >&2
    exit 1
  fi
  run_sql "$path"
done

if [[ "$WITH_CLUSTER_SECURITY" -eq 1 ]]; then
  run_sql "$SCRIPT_DIR/wf_cluster_security_columns.sql"
  if [[ -f "$SCRIPT_DIR/wf_cluster_arc_resource_id.sql" ]]; then
    run_sql "$SCRIPT_DIR/wf_cluster_arc_resource_id.sql"
  fi
fi

PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
if [[ -x "$PYTHON_BIN" ]]; then
  echo "Contract check..."
  "$PYTHON_BIN" "$REPO_ROOT/workflow_engine/contract/validate_contract.py"
fi

echo "Deployed wf parity objects on $SERVER/$DATABASE"
echo "Next: source .venv/bin/activate && bash scripts/bootstrap_distributed_workers.sh --skip-schema"
