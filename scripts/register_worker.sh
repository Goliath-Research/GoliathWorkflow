#!/bin/bash
# Register a workflow worker (wf.cluster + wf.worker + wf.worker_token).

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/register_worker.sh [options]

DEV/bootstrap: upserts wf.worker via direct DB env.
Production: set WORKER_API_BASE (and omit AZURE_SQL_*/POSTGRES_*); script calls
gateway POST /v1/workers/enroll. Prefer: methyl-worker enroll --api-base … --cluster … --key …

Options:
  --key NAME           external_worker_key (default: hostname)
  --cluster KEY        cluster_key (default: goliath)
  --capability NAME    Repeatable capability (omit for auto-detect on this VM)
  --omnibus            Register wildcard '*' capability (legacy omnibus worker)
  --allowed-cidr CIDR  Repeatable cluster source CIDR (Tier C public workers; DB path only)
  --entra-client-id ID Optional Entra application (client) id for cluster
  --arc-resource-id ID Azure Arc resource id (default: /etc/methyl/arc.env)
  --require-arc          Fail if Arc agent is not Connected
  --env-file PATH      Credential file (default: /etc/methyl/worker-token)
  --token TOKEN        Use fixed token (DB path only; default: random hex)
  --dry-run            Print plan only
  -h, --help           Show this help

Direct DB (dev): BACKEND_DB / AZURE_SQL_* or POSTGRES_*.
Gateway enroll (prod): WORKER_API_BASE or METHYL_API_BASE; portal must preregister this VM's public IP.
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
    --arc-resource-id) ARGS+=(--arc-resource-id "${2:-}"); shift 2 ;;
    --require-arc) ARGS+=(--require-arc); shift ;;
    --env-file) ARGS+=(--env-file "${2:-}"); shift 2 ;;
    --token) ARGS+=(--token "${2:-}"); shift 2 ;;
    --dry-run) ARGS+=(--dry-run); shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

exec "$PYTHON_BIN" "$SCRIPT_DIR/register_worker.py" "${ARGS[@]}"
