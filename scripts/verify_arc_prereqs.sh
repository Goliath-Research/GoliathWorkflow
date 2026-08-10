#!/bin/bash
# Verify Azure Arc Connected Machine agent is installed and Connected.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/verify_arc_prereqs.sh

Exits 0 when azcmagent reports Connected status and ARC_RESOURCE_ID is present
in /etc/methyl/arc.env (or METHYL_ARC_ENV). Exits 1 otherwise.
EOF
}

ARC_ENV="${METHYL_ARC_ENV:-/etc/methyl/arc.env}"

if ! command -v azcmagent >/dev/null 2>&1; then
  echo "azcmagent not installed; run scripts/install_arc_agent.sh" >&2
  exit 1
fi

status="$(azcmagent show -j 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null || true)"
if [[ "$status" != "Connected" ]]; then
  echo "Arc agent not Connected (status=${status:-unknown})" >&2
  exit 1
fi

if [[ ! -f "$ARC_ENV" ]]; then
  echo "Arc Connected but missing $ARC_ENV (run install_arc_agent.sh post-connect hook)" >&2
  exit 1
fi
if [[ ! -r "$ARC_ENV" ]]; then
  echo "Arc Connected but cannot read $ARC_ENV (chmod 644; written as root-only?)" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$ARC_ENV"
if [[ -z "${ARC_RESOURCE_ID:-}" ]]; then
  echo "Arc Connected but ARC_RESOURCE_ID unset in $ARC_ENV" >&2
  exit 1
fi

echo "Arc agent Connected; ARC_RESOURCE_ID=$ARC_RESOURCE_ID"
exit 0
