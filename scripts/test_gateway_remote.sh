#!/bin/bash
# Smoke-test the production gateway via SSH (localhost on VM) and optional public HTTP.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SSH_HOST="${GATEWAY_SSH:-ubuntu@48.216.240.121}"
PUBLIC_HOST="${GATEWAY_PUBLIC:-48.216.240.121}"
KEY="${GATEWAY_SSH_KEY:-$REPO_ROOT/deploy/gateway_key.pem}"
PUBLIC_PORT="${GATEWAY_PORT:-443}"
LOCAL_PORT="${GATEWAY_LOCAL_PORT:-8080}"

usage() {
  cat <<EOF
Usage: scripts/test_gateway_remote.sh [options]

Options:
  --ssh-only       Skip public HTTP probe from this machine
  --public-only    Skip SSH (curl public /v1/health only)
  --deploy         Also run deploy_workflow_definitions.sh on the gateway VM
  -h, --help       Show this help

Env: GATEWAY_SSH, GATEWAY_PUBLIC, GATEWAY_SSH_KEY, GATEWAY_PORT (public HTTPS), GATEWAY_LOCAL_PORT (loopback)
EOF
}

SSH_ONLY=0
PUBLIC_ONLY=0
RUN_DEPLOY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ssh-only) SSH_ONLY=1; shift ;;
    --public-only) PUBLIC_ONLY=1; shift ;;
    --deploy) RUN_DEPLOY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

test_public() {
  echo "=== public HTTPS ${PUBLIC_HOST}:${PUBLIC_PORT} ==="
  if curl -sS -m 10 -k "https://${PUBLIC_HOST}:${PUBLIC_PORT}/v1/health"; then
    echo
  else
    echo "(public endpoint unreachable from this machine — NSG may restrict source IP)" >&2
    return 1
  fi
}

test_ssh() {
  [[ -f "$KEY" ]] || { echo "Missing SSH key: $KEY" >&2; exit 1; }
  chmod 600 "$KEY"

  echo "=== SSH ${SSH_HOST} ==="
  ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new \
    "$SSH_HOST" bash -s -- "$LOCAL_PORT" "$RUN_DEPLOY" <<'REMOTE'
set -euo pipefail
API_PORT="$1"
RUN_DEPLOY="$2"
BASE="http://127.0.0.1:${API_PORT}/v1"

echo "--- hostname ---"
hostname

echo "--- methyl-gateway ---"
systemctl is-active methyl-gateway
systemctl status methyl-gateway --no-pager -l | head -15

echo "--- health ---"
curl -sS "${BASE}/health"
echo

echo "--- actions (first 3 names) ---"
curl -sS "${BASE}/actions" | python3 -c '
import json, sys
data = json.load(sys.stdin)
items = data if isinstance(data, list) else data.get("actions", [])
names = [x.get("name", x) if isinstance(x, dict) else str(x) for x in items[:3]]
print(f"count={len(items)} sample={names}")
'

if [[ "$RUN_DEPLOY" == "1" ]]; then
  echo "--- deploy workflow definitions ---"
  set -a
  # shellcheck disable=SC1091
  source /work/goliath/env/gateway.env
  set +a
  cd /work/goliath/repos/MethylPipeline
  ./scripts/deploy_workflow_definitions.sh
  cat /work/goliath/env/workflow_versions.json
fi
REMOTE
}

fail=0
if [[ "$PUBLIC_ONLY" -eq 1 ]]; then
  test_public || fail=1
elif [[ "$SSH_ONLY" -eq 1 ]]; then
  test_ssh || fail=1
else
  test_public || true
  echo
  test_ssh || fail=1
fi

exit "$fail"
