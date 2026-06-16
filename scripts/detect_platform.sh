#!/bin/bash
# Detect host architecture and load platform_matrix.env defaults.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MATRIX_FILE="${PLATFORM_MATRIX_FILE:-$SCRIPT_DIR/platform_matrix.env}"

detect_uname_arch() {
  uname -m
}

# Map uname -m to matrix key (aarch64 | amd64)
platform_arch_key() {
  local uname_arch="${1:-$(detect_uname_arch)}"
  case "$uname_arch" in
    aarch64|arm64) echo "aarch64" ;;
    x86_64|amd64) echo "amd64" ;;
    *) echo "unknown" ;;
  esac
}

# Source platform_matrix.env and resolve PARABRICKS_IMAGE for current host.
resolve_parabricks_image() {
  local arch_key
  arch_key="$(platform_arch_key)"
  if [[ -f "$MATRIX_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$MATRIX_FILE"
  fi
  local var="PARABRICKS_IMAGE_${arch_key}"
  echo "${!var:-}"
}

resolve_methyl_extractor_subdir() {
  local uname_arch="${1:-$(detect_uname_arch)}"
  if [[ -f "$MATRIX_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$MATRIX_FILE"
  fi
  case "$uname_arch" in
    aarch64|arm64) echo "${METHYL_EXTRACTOR_ARCH_aarch64:-arm64}" ;;
    x86_64|amd64) echo "${METHYL_EXTRACTOR_ARCH_x86_64:-x64}" ;;
    *) return 1 ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "uname: $(detect_uname_arch)"
  echo "arch_key: $(platform_arch_key)"
  echo "parabricks_image: $(resolve_parabricks_image)"
  echo "methyl_extractor_subdir: $(resolve_methyl_extractor_subdir)"
fi
