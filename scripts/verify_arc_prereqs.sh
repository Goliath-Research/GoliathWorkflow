#!/bin/bash
# Verify Azure Arc Connected Machine agent is installed and Connected.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/verify_arc_prereqs.sh

Exits 0 when azcmagent reports Connected status (or /etc/methyl/arc.env exists with ARC_RESOURCE_ID).
Exits 1 otherwise.
EOF
}

ARC_ENV="${METHYL_ARC_ENV:-/etc/methyl/arc.env}"

if [[ -f "$ARC_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$ARC_ENV"
  if [[ -n "${ARC_RESOURCE_ID:-}" ]]; then
    echo "Arc env present: ARC_RESOURCE_ID=$ARC_RESOURCE_ID"
    exit 0
  fi
fi

if ! command -v azcmagent >/dev/null 2>&1; then
  echo "azcmagent not installed; run scripts/install_arc_agent.sh" >&2
  exit 1
fi

status="$(azcmagent show -j 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null || true)"
if [[ "$status" == "Connected" ]]; then
  echo "Arc agent Connected"
  exit 0
fi

echo "Arc agent not Connected (status=${status:-unknown})" >&2
exit 1
