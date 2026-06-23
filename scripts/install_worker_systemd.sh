#!/bin/bash
# Install methyl-worker systemd unit on this VM (local daemon, shared /work env).
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/install_worker_systemd.sh [options]

Options:
  --root PATH           Epimethyl root (default: /work/epimethyl)
  --arch KEY            aarch64 or amd64 (default: detect)
  --capability NAME     Install methyl-worker@NAME.service instead of omnibus
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
CAPABILITY=""
RUNTIME=""
NO_START=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="${2:-}"; shift 2 ;;
    --arch) ARCH="${2:-}"; shift 2 ;;
    --capability) CAPABILITY="${2:-}"; shift 2 ;;
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

WORKER_BIN="$VENV/bin/methyl-worker"
[[ -x "$WORKER_BIN" ]] || WORKER_BIN="$ROOT/venv/bin/methyl-worker"

PATH_LINE="$VENV/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

if [[ -n "$CAPABILITY" ]]; then
  UNIT="methyl-worker@${CAPABILITY}.service"
  SRC="$DEPLOY/methyl-worker@.service"
  [[ -f "$SRC" ]] || { echo "Missing $SRC" >&2; exit 1; }
  sed -e "s|venv-aarch64|$VENV|g" \
      -e "s|/work/epimethyl|$ROOT|g" \
      -e "s|PATH=/work/epimethyl/venv-aarch64/bin:|PATH=$PATH_LINE|" \
      "$SRC" >"/etc/systemd/system/methyl-worker@.service"
  systemctl daemon-reload
  systemctl enable "$UNIT"
  [[ "$NO_START" -eq 0 ]] && systemctl restart "$UNIT"
  systemctl status "$UNIT" --no-pager -l | head -15
  exit 0
fi

SRC="$DEPLOY/methyl-worker.service"
[[ -f "$SRC" ]] || { echo "Missing $SRC" >&2; exit 1; }

TMP="$(mktemp)"
sed -e "s|venv-aarch64|$VENV|g" \
    -e "s|/work/epimethyl|$ROOT|g" \
    -e "s|ExecStart=/work/epimethyl/venv-aarch64/bin/methyl-worker|ExecStart=$WORKER_BIN|" \
    -e "s|PATH=/work/epimethyl/venv-aarch64/bin:|PATH=$PATH_LINE|" \
    "$SRC" >"$TMP"
cp "$TMP" /etc/systemd/system/methyl-worker.service
rm -f "$TMP"

systemctl daemon-reload
systemctl enable methyl-worker.service
[[ "$NO_START" -eq 0 ]] && systemctl restart methyl-worker.service
systemctl status methyl-worker.service --no-pager -l | head -15
