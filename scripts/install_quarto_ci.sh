#!/usr/bin/env bash
# Install Quarto for CI agents (Ubuntu amd64). Idempotent.
set -euo pipefail

if command -v quarto >/dev/null 2>&1; then
  quarto --version
  exit 0
fi

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) DEB=quarto-linux-amd64.deb ;;
  aarch64|arm64) DEB=quarto-linux-arm64.deb ;;
  *)
    echo "ERROR: unsupported arch for Quarto CI install: $ARCH" >&2
    exit 1
    ;;
esac

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
# GitHub /releases/latest/download/ requires the exact versioned asset name (404 otherwise).
# Quarto's redirect always resolves to the current release .deb for this arch.
curl -fsSL "https://quarto.org/download/latest/${DEB}" -o quarto.deb
sudo dpkg -i quarto.deb
quarto --version
