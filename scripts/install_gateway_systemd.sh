#!/bin/bash
# Install methyl-gateway systemd unit on this VM.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/install_gateway_systemd.sh [options]

Options:
  --root PATH           Epimethyl root (default: /work/epimethyl)
  --arch KEY            aarch64 or amd64 (default: detect)
  --runtime PATH        Path to runtime-bundle (default: <root>/current/runtime-bundle)
  --no-start            Install/enable only; do not start
  -h, --help
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=detect_platform.sh
source "$SCRIPT_DIR/detect_platform.sh"

ROOT="${EPIMETHYL_ROOT:-/work/epimethyl}"
ARCH=""
RUNTIME=""
NO_START=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="${2:-}"; shift 2 ;;
    --arch) ARCH="${2:-}"; shift 2 ;;
    --runtime) RUNTIME="${2:-}"; shift 2 ;;
    --no-start) NO_START=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0 ..." >&2
  exit 1
fi

ARCH="${ARCH:-$(platform_arch_key "$(detect_uname_arch)")}"
VENV="$ROOT/venv-${ARCH}"
RUNTIME="${RUNTIME:-$(readlink -f "$ROOT/current/runtime-bundle" 2>/dev/null || echo "$SCRIPT_DIR/..")}"
DEPLOY="$RUNTIME/deploy/systemd"
[[ -d "$DEPLOY" ]] || DEPLOY="$SCRIPT_DIR/../deploy/systemd"

SRC="$DEPLOY/methyl-gateway.service"
[[ -f "$SRC" ]] || { echo "Missing $SRC" >&2; exit 1; }

sed -e "s|__EPIMETHYL_ROOT__|$ROOT|g" \
    -e "s|__EPIMETHYL_VENV__|$VENV|g" \
    "$SRC" >"/etc/systemd/system/methyl-gateway.service"

systemctl daemon-reload
systemctl enable methyl-gateway.service
[[ "$NO_START" -eq 0 ]] && systemctl restart methyl-gateway.service
systemctl status methyl-gateway.service --no-pager -l | head -15
