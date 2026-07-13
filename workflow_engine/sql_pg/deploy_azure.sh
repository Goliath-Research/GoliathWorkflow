#!/usr/bin/env bash
# Deploy MethylPipeline wf schema to Azure Database for PostgreSQL.
#
# Prerequisites:
#   - psql (PostgreSQL client 15+)
#   - Your client IP allowed in Azure PG firewall (or run from Azure VM / Cloud Shell)
#   - Login granted CONNECT on database postgres (default Azure DB)
#
# Native PostgreSQL auth (dba):
#   export PGHOST=epimethyl.postgres.database.azure.com
#   export PGPORT=5432
#   export PGDATABASE=postgres
#   export PGUSER=dba
#   export PGPASSWORD='...'
#   ./deploy_azure.sh
#
# Microsoft Entra ID auth:
#   export PGHOST=epimethyl.postgres.database.azure.com
#   export PGPORT=5432
#   export PGDATABASE=postgres
#   export PGUSER='you@epimethyl.com'
#   export PGPASSWORD="$(az account get-access-token --resource https://ossrdbms-aad.database.windows.net --query accessToken --output tsv)"
#   ./deploy_azure.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export PGHOST="${PGHOST:-epimethyl.postgres.database.azure.com}"
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-postgres}}"
export PGSSLMODE="${PGSSLMODE:-require}"

if [[ -z "${PGUSER:-}" ]]; then
  PGUSER="${POSTGRES_USER:-dba}"
  export PGUSER
fi

if [[ -z "${PGPASSWORD:-}" ]]; then
  if [[ -n "${POSTGRES_PASSWORD:-}" ]]; then
    export PGPASSWORD="$POSTGRES_PASSWORD"
  elif command -v az >/dev/null 2>&1; then
    echo "PGPASSWORD not set; fetching Entra token via az cli..."
    export PGPASSWORD
    PGPASSWORD="$(az account get-access-token --resource https://ossrdbms-aad.database.windows.net --query accessToken --output tsv)"
  else
    echo "Set PGPASSWORD (native auth) or install az cli for Entra auth." >&2
    exit 1
  fi
fi

SCRIPTS=(
  00_schema.sql
  03_engine_core.sql
  05_runtime_parity.sql
  06_scope_writepath_parity.sql
  07_scope_encoding_parity.sql
  08_foreach_support.sql
  01_worker_api.sql
  02_repository_api.sql
  wf_apply_validation_plan.sql
  wf_hyperparameter_set.sql
  04_admin.sql
  wf_action_schema.sql
  wf_repo_upsert_workflow_action.sql
  wf_action_dispatch_metadata.sql
  wf_repo_create_workflow_graph.sql
  wf_sql_collection_bindings.sql
  portal_resource_profile.sql
  portal_workflow_api.sql
  wf_drop_platform_sample_storage.sql
  cfg_schema.sql
  cfg_registry_tables.sql
  cfg_wf_relationships.sql
  cfg_repo_api.sql
  cfg_portal_api.sql
)

echo "Target: host=$PGHOST db=$PGDATABASE user=$PGUSER sslmode=$PGSSLMODE"

echo "Preflight..."
psql -q -v ON_ERROR_STOP=1 -c "SELECT current_user, current_database(), version();"

for name in "${SCRIPTS[@]}"; do
  path="$SCRIPT_DIR/$name"
  if [[ ! -f "$path" ]]; then
    echo "Missing script: $path" >&2
    exit 1
  fi
  echo "Applying $name ..."
  psql -q -v ON_ERROR_STOP=1 -f "$path"
done

echo "Contract check..."
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  echo "python3 not found; skipping contract check" >&2
else
  "$PYTHON_BIN" "$REPO_ROOT/workflow_engine/contract/validate_contract.py"
fi

echo "Deployed wf objects on $PGHOST/$PGDATABASE"
