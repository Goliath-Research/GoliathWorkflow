#!/bin/bash
# Install and connect Azure Arc agent (azcmagent) for worker VM governance.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/install_arc_agent.sh [options]

Requires root (sudo). Connects this VM to Azure Arc; writes /etc/methyl/arc.env.

Options:
  --subscription-id ID
  --resource-group NAME
  --tenant-id ID
  --location REGION          Azure region for Arc resource (default: westus2)
  --machine-name NAME        Arc machine name (default: hostname -s)
  --tags KEY=VALUE,...       Comma-separated tags
  --proxy-url URL            HTTPS proxy for agent
  --service-principal        Use AZURE_CLIENT_ID + AZURE_CLIENT_SECRET env
  --with-ama                 Install Azure Monitor Agent extension (requires az CLI)
  --dry-run
  -h, --help

Env: AZURE_CLIENT_ID, AZURE_CLIENT_SECRET (service principal onboarding)
EOF
}

SUBSCRIPTION_ID="${AZ_SUBSCRIPTION_ID:-}"
RESOURCE_GROUP="${AZ_RESOURCE_GROUP:-}"
TENANT_ID="${AZURE_TENANT_ID:-}"
LOCATION="${AZ_ARC_LOCATION:-westus2}"
MACHINE_NAME="$(hostname -s 2>/dev/null || hostname)"
TAGS=""
PROXY_URL=""
USE_SP=0
WITH_AMA=0
DRY_RUN=0
ARC_ENV="/etc/methyl/arc.env"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --subscription-id) SUBSCRIPTION_ID="${2:-}"; shift 2 ;;
    --resource-group) RESOURCE_GROUP="${2:-}"; shift 2 ;;
    --tenant-id) TENANT_ID="${2:-}"; shift 2 ;;
    --location) LOCATION="${2:-}"; shift 2 ;;
    --machine-name) MACHINE_NAME="${2:-}"; shift 2 ;;
    --tags) TAGS="${2:-}"; shift 2 ;;
    --proxy-url) PROXY_URL="${2:-}"; shift 2 ;;
    --service-principal) USE_SP=1; shift ;;
    --with-ama) WITH_AMA=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DRY-RUN] $*"
  else
    "$@"
  fi
}

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0 ..." >&2
  exit 1
fi

if command -v azcmagent >/dev/null 2>&1; then
  status="$(azcmagent show -j 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)"
  if [[ "$status" == "Connected" && -f "$ARC_ENV" ]]; then
    echo "Arc agent already Connected; skipping install"
    exit 0
  fi
fi

[[ -n "$SUBSCRIPTION_ID" && -n "$RESOURCE_GROUP" && -n "$TENANT_ID" ]] || {
  echo "Set --subscription-id, --resource-group, --tenant-id" >&2
  exit 1
}

if ! command -v azcmagent >/dev/null 2>&1; then
  echo "Installing azcmagent ..."
  if [[ -f /etc/debian_version ]]; then
    run curl -sSL https://aka.ms/azcmagent -o /tmp/install_linux_azcmagent.sh
    run bash /tmp/install_linux_azcmagent.sh
  else
    echo "Unsupported OS; install azcmagent manually: https://learn.microsoft.com/azure/azure-arc/servers/agent-overview" >&2
    exit 1
  fi
fi

# azcmagent requires --correlation-id to be a GUID (not an arbitrary string).
if command -v uuidgen >/dev/null 2>&1; then
  CORRELATION_ID="$(uuidgen)"
else
  CORRELATION_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
fi

connect_args=(
  --resource-group "$RESOURCE_GROUP"
  --tenant-id "$TENANT_ID"
  --location "$LOCATION"
  --subscription-id "$SUBSCRIPTION_ID"
  --resource-name "$MACHINE_NAME"
  --correlation-id "$CORRELATION_ID"
)

if [[ -n "$TAGS" ]]; then
  connect_args+=(--tags "$TAGS")
fi

if [[ -n "$PROXY_URL" ]]; then
  connect_args+=(--proxy-url "$PROXY_URL")
fi

if [[ "$USE_SP" -eq 1 ]]; then
  [[ -n "${AZURE_CLIENT_ID:-}" && -n "${AZURE_CLIENT_SECRET:-}" ]] || {
    echo "Set AZURE_CLIENT_ID and AZURE_CLIENT_SECRET for --service-principal" >&2
    exit 1
  }
  run azcmagent connect "${connect_args[@]}" \
    --service-principal-id "$AZURE_CLIENT_ID" \
    --service-principal-secret "$AZURE_CLIENT_SECRET"
else
  run azcmagent connect "${connect_args[@]}"
fi

# Prefer azcmagent (always present post-connect); fall back to az CLI.
resource_id=""
machine_name_resolved="$MACHINE_NAME"
resource_group_resolved="$RESOURCE_GROUP"
if command -v azcmagent >/dev/null 2>&1; then
  eval "$(azcmagent show -j 2>/dev/null | python3 -c '
import json, sys, shlex
d = json.load(sys.stdin)
rid = d.get("resourceId") or ""
name = d.get("resourceName") or ""
rg = d.get("resourceGroup") or ""
print("resource_id=" + shlex.quote(rid))
print("machine_name_resolved=" + shlex.quote(name or "'"$MACHINE_NAME"'"))
print("resource_group_resolved=" + shlex.quote(rg or "'"$RESOURCE_GROUP"'"))
' 2>/dev/null || true)"
fi
if [[ -z "$resource_id" ]] && command -v az >/dev/null 2>&1; then
  resource_id="$(az connectedmachine show \
    --name "$MACHINE_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --subscription "$SUBSCRIPTION_ID" \
    --query id -o tsv 2>/dev/null || true)"
fi

run mkdir -p /etc/methyl
if [[ "$DRY_RUN" -eq 0 ]]; then
  cat >"$ARC_ENV" <<EOF
# Written by scripts/install_arc_agent.sh
ARC_MACHINE_NAME=$machine_name_resolved
ARC_RESOURCE_GROUP=$resource_group_resolved
ARC_SUBSCRIPTION_ID=$SUBSCRIPTION_ID
ARC_RESOURCE_ID=${resource_id:-}
EOF
  # Not a secret (resource ids only); must be readable by verify_arc_prereqs as non-root.
  chmod 644 "$ARC_ENV"
fi

echo "Arc onboarding complete; wrote $ARC_ENV"

if [[ "$WITH_AMA" -eq 1 && -n "$resource_id" ]] && command -v az >/dev/null 2>&1; then
  echo "Installing Azure Monitor Agent extension ..."
  run az connectedmachine extension create \
    --machine-name "$MACHINE_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --name AzureMonitorLinuxAgent \
    --publisher Microsoft.Azure.Monitor \
    --type AzureMonitorLinuxAgent \
    --location "$LOCATION" || true
fi

run bash "$(dirname "$0")/verify_arc_prereqs.sh"
