#!/bin/bash
# Register a workflow worker (wf.cluster + wf.worker + wf.worker_token).

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/register_worker.sh [options]

Options:
  --key NAME           external_worker_key (default: hostname)
  --cluster KEY        cluster_key (default: epimethyl)
  --capability NAME    Repeatable capability filter (omit for omnibus worker)
  --allowed-cidr CIDR  Repeatable cluster source CIDR (Tier C public workers)
  --entra-client-id ID Optional Entra application (client) id for cluster
  --env-file PATH      Append WORKER_ID and WORKER_TOKEN (default: /work/epimethyl/env/worker.env)
  --token TOKEN        Use fixed token (default: random hex)
  --dry-run            Print plan only
  -h, --help           Show this help

Uses BACKEND_DB / connection env (see deploy/env/gateway.*.env.example).
PostgreSQL: PGHOST, PGUSER, PGPASSWORD, PGDATABASE.
Azure SQL: AZURE_SQL_SERVER, AZURE_SQL_DB, AZURE_SQL_USER, AZURE_SQL_PASSWORD.
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
fi

ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --key) ARGS+=(--key "${2:-}"); shift 2 ;;
    --cluster) ARGS+=(--cluster "${2:-}"); shift 2 ;;
    --capability) ARGS+=(--capability "${2:-}"); shift 2 ;;
    --allowed-cidr) ARGS+=(--allowed-cidr "${2:-}"); shift 2 ;;
    --entra-client-id) ARGS+=(--entra-client-id "${2:-}"); shift 2 ;;
    --env-file) ARGS+=(--env-file "${2:-}"); shift 2 ;;
    --token) ARGS+=(--token "${2:-}"); shift 2 ;;
    --dry-run) ARGS+=(--dry-run); shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

exec "$PYTHON_BIN" "$SCRIPT_DIR/register_worker.py" "${ARGS[@]}"
