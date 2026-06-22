#!/bin/bash
# Install nginx TLS reverse proxy for methyl-gateway on Ubuntu.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/setup_gateway_nginx.sh [options]

Options:
  --hostname NAME    TLS server_name (default: gateway hostname -f)
  --cert-dir PATH    Directory with fullchain.pem + privkey.pem
                     (default: /etc/ssl/methyl-gateway)
  --skip-nginx-install  Do not apt-install nginx
  -h, --help
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

HOSTNAME="${GATEWAY_HOSTNAME:-$(hostname -f 2>/dev/null || echo gateway.local)}"
CERT_DIR="${GATEWAY_CERT_DIR:-/etc/ssl/methyl-gateway}"
SKIP_INSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hostname) HOSTNAME="${2:-}"; shift 2 ;;
    --cert-dir) CERT_DIR="${2:-}"; shift 2 ;;
    --skip-nginx-install) SKIP_INSTALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ "$SKIP_INSTALL" -eq 0 ]]; then
  sudo apt-get update -qq
  sudo apt-get install -y nginx
fi

[[ -f "$CERT_DIR/fullchain.pem" && -f "$CERT_DIR/privkey.pem" ]] || {
  echo "Place TLS cert at $CERT_DIR/fullchain.pem and $CERT_DIR/privkey.pem" >&2
  echo "For internal CA or Let's Encrypt, see docs/deployment/production_runbook.md" >&2
  exit 1
}

TMP="$(mktemp)"
sed -e "s/GATEWAY_HOSTNAME/${HOSTNAME}/g" \
  "$REPO_ROOT/deploy/nginx/methyl-gateway.conf" >"$TMP"
sudo cp "$TMP" /etc/nginx/sites-available/methyl-gateway
rm -f "$TMP"

sudo ln -sf /etc/nginx/sites-available/methyl-gateway /etc/nginx/sites-enabled/methyl-gateway
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl reload nginx

echo "nginx TLS proxy enabled for https://${HOSTNAME}/v1"
echo "Ensure methyl-gateway binds 127.0.0.1:8080 (deploy/systemd/methyl-gateway.service)"
