#!/usr/bin/env bash
# Pre-render Mermaid sources in docs/diagrams/src/ to SVG + PNG in docs/diagrams/out/.
# PNG uses native SVG text (htmlLabels: false) so labels survive LaTeX/PDF embeds.
#
# Freshness uses content hashes (out/<name>.mmd.sha256), not filesystem mtimes —
# Azure/CI checkouts often make src/ appear newer than out/ and false-fail -nt checks.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/docs/diagrams/src"
OUT="${ROOT}/docs/diagrams/out"
DIAGRAM_PKG="${ROOT}/docs/diagrams"
MMDC="${DIAGRAM_PKG}/node_modules/.bin/mmdc"
MERMAID_CONFIG="${DIAGRAM_PKG}/mermaid-config.json"
CHECK_ONLY=false

usage() {
  echo "Usage: $0 [--check]" >&2
  echo "  Renders *.mmd to matching *.svg and *.png under docs/diagrams/out/." >&2
  echo "  --check  Exit 1 if any output is missing, hash-mismatched, or a placeholder." >&2
}

mmd_sha256() {
  # Portable content hash of the Mermaid source (no filename in digest).
  sha256sum "$1" | awk '{print $1}'
}

write_source_hash() {
  local mmd="$1"
  local base="$2"
  mmd_sha256 "$mmd" >"$OUT/${base}.mmd.sha256"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) CHECK_ONLY=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

mkdir -p "$OUT"

resolve_chromium() {
  if [[ -n "${PUPPETEER_EXECUTABLE_PATH:-}" ]]; then
    return 0
  fi
  local candidate
  for candidate in \
    chromium-browser chromium google-chrome \
    /usr/bin/chromium-browser /usr/bin/chromium \
    /snap/bin/chromium; do
    if command -v "$candidate" >/dev/null 2>&1; then
      export PUPPETEER_EXECUTABLE_PATH
      PUPPETEER_EXECUTABLE_PATH="$(command -v "$candidate")"
      return 0
    fi
    if [[ -x "$candidate" ]]; then
      export PUPPETEER_EXECUTABLE_PATH="$candidate"
      return 0
    fi
  done
  echo "ERROR: no Chromium/Chrome found. Install chromium-browser or set PUPPETEER_EXECUTABLE_PATH." >&2
  exit 1
}

ensure_mmdc() {
  if [[ -x "$MMDC" ]]; then
    return 0
  fi
  if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm not found. Install Node.js or run: cd docs/diagrams && npm ci" >&2
    exit 1
  fi
  echo "Installing pinned @mermaid-js/mermaid-cli under docs/diagrams/ ..."
  if [[ -f "${DIAGRAM_PKG}/package-lock.json" ]]; then
    (cd "$DIAGRAM_PKG" && npm ci --no-audit --no-fund)
  else
    (cd "$DIAGRAM_PKG" && npm install --no-audit --no-fund)
  fi
  if [[ ! -x "$MMDC" ]]; then
    echo "ERROR: mmdc not found at $MMDC after npm install" >&2
    exit 1
  fi
}

is_placeholder_svg() {
  local svg="$1"
  [[ ! -f "$svg" ]] && return 1
  grep -q 'placeholder SVG' "$svg" 2>/dev/null
}

stale=0
shopt -s nullglob
for mmd in "$SRC"/*.mmd; do
  base="$(basename "$mmd" .mmd)"
  svg="$OUT/${base}.svg"
  png="$OUT/${base}.png"
  hash_file="$OUT/${base}.mmd.sha256"
  if $CHECK_ONLY; then
    actual="$(mmd_sha256 "$mmd")"
    expected=""
    [[ -f "$hash_file" ]] && expected="$(tr -d '[:space:]' <"$hash_file")"
    for artifact in "$svg" "$png"; do
      if [[ ! -f "$artifact" ]]; then
        echo "STALE: $artifact (regenerate with scripts/render_diagrams.sh)" >&2
        stale=1
      fi
    done
    if [[ -z "$expected" || "$expected" != "$actual" ]]; then
      echo "STALE: $hash_file (source hash mismatch; regenerate with scripts/render_diagrams.sh)" >&2
      stale=1
    fi
    if [[ -f "$svg" ]] && is_placeholder_svg "$svg"; then
      echo "PLACEHOLDER: $svg (regenerate with scripts/render_diagrams.sh)" >&2
      stale=1
    fi
    continue
  fi
  ensure_mmdc
  resolve_chromium
  if [[ ! -f "$MERMAID_CONFIG" ]]; then
    echo "ERROR: missing Mermaid config at $MERMAID_CONFIG" >&2
    exit 1
  fi
  echo "Rendering $mmd -> $svg + $png (PUPPETEER_EXECUTABLE_PATH=${PUPPETEER_EXECUTABLE_PATH:-unset})"
  "$MMDC" -i "$mmd" -o "$svg" -b transparent -c "$MERMAID_CONFIG"
  "$MMDC" -i "$mmd" -o "$png" -b transparent -c "$MERMAID_CONFIG" -s 2
  if is_placeholder_svg "$svg"; then
    echo "ERROR: render produced placeholder-like output for $svg" >&2
    exit 1
  fi
  write_source_hash "$mmd" "$base"
done

if $CHECK_ONLY && [[ $stale -ne 0 ]]; then
  exit 1
fi

if ! $CHECK_ONLY; then
  echo "Diagram render complete: $OUT"
fi
