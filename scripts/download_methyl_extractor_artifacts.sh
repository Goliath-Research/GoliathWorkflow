#!/bin/bash
# Download MethylExtractor tarballs from Azure Artifacts Universal Packages into a release directory.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/download_methyl_extractor_artifacts.sh [options]

Options:
  --release-dir PATH     Target release directory (default: /work/epimethyl/releases/<version>)
  --version VER          Universal Package version (SemVer, e.g. 2026.6.1; required)
  --organization URL     Azure DevOps org (default: https://dev.azure.com/EpiMethyl)
  --project NAME         Project name (default: Development)
  --feed NAME            Artifacts feed (default: methyl-extractor)
  --arch KEY             Download one arch only (aarch64 or amd64); default both
  -h, --help             Show this help

Requires: az CLI with azure-devops extension; az devops login (PAT with Packaging read).

Example:
  scripts/download_methyl_extractor_artifacts.sh \
    --version 2026.6.1 \
    --release-dir /work/epimethyl/releases/2026.6.1
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=detect_platform.sh
source "$SCRIPT_DIR/detect_platform.sh"

RELEASE_DIR=""
VERSION=""
ORG="${AZURE_DEVOPS_ORG:-https://dev.azure.com/EpiMethyl}"
PROJECT="${AZURE_DEVOPS_PROJECT:-Development}"
FEED="${METHYL_EXTRACTOR_FEED:-methyl-extractor}"
ARCH_FILTER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release-dir) RELEASE_DIR="${2:-}"; shift 2 ;;
    --version) VERSION="${2:-}"; shift 2 ;;
    --organization) ORG="${2:-}"; shift 2 ;;
    --project) PROJECT="${2:-}"; shift 2 ;;
    --feed) FEED="${2:-}"; shift 2 ;;
    --arch) ARCH_FILTER="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

info() { echo "[INFO] $*"; }
die() { echo "[ERROR] $*" >&2; exit 1; }

[[ -n "$VERSION" ]] || die "--version is required"
VERSION="$(normalize_release_version "$VERSION")"
require_release_version "$VERSION" "--version" || exit 1

RELEASE_DIR="${RELEASE_DIR:-/work/epimethyl/releases/$VERSION}"
mkdir -p "$RELEASE_DIR"

download_one() {
  local arch_key="$1"
  local pkg_name="methyl-extractor-linux-${arch_key}"
  local staging="$RELEASE_DIR/.dl-${arch_key}"
  local tarball="$RELEASE_DIR/${pkg_name}.tar.gz"

  info "Downloading $pkg_name @ $VERSION"
  rm -rf "$staging"
  mkdir -p "$staging"
  az artifacts universal download \
    --organization "$ORG" \
    --project "$PROJECT" \
    --scope project \
    --feed "$FEED" \
    --name "$pkg_name" \
    --version "$VERSION" \
    --path "$staging"
  cp "$staging/${pkg_name}.tar.gz" "$tarball"
  info "Wrote $tarball ($(sha256sum "$tarball" | awk '{print $1}'))"
}

for arch in aarch64 amd64; do
  [[ -n "$ARCH_FILTER" && "$ARCH_FILTER" != "$arch" ]] && continue
  download_one "$arch"
done

info "Download complete: $RELEASE_DIR"
info "Update manifest.json artifacts.*.sha256 then run promote_release.sh"
