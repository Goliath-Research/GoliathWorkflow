#!/usr/bin/env bash
# Pre-render Mermaid sources in docs/diagrams/src/ to SVG in docs/diagrams/out/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/docs/diagrams/src"
OUT="${ROOT}/docs/diagrams/out"
DIAGRAM_PKG="${ROOT}/docs/diagrams"
MMDC="${DIAGRAM_PKG}/node_modules/.bin/mmdc"
CHECK_ONLY=false

usage() {
  echo "Usage: $0 [--check]" >&2
  echo "  Renders *.mmd to matching *.svg under docs/diagrams/out/." >&2
  echo "  --check  Exit 1 if any output is missing, older than its source, or a placeholder." >&2
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
  if $CHECK_ONLY; then
    if [[ ! -f "$svg" ]] || [[ "$mmd" -nt "$svg" ]]; then
      echo "STALE: $svg (regenerate with scripts/render_diagrams.sh)" >&2
      stale=1
    elif is_placeholder_svg "$svg"; then
      echo "PLACEHOLDER: $svg (regenerate with scripts/render_diagrams.sh)" >&2
      stale=1
    fi
    continue
  fi
  ensure_mmdc
  resolve_chromium
  echo "Rendering $mmd -> $svg (PUPPETEER_EXECUTABLE_PATH=${PUPPETEER_EXECUTABLE_PATH:-unset})"
  "$MMDC" -i "$mmd" -o "$svg" -b transparent
  if is_placeholder_svg "$svg"; then
    echo "ERROR: render produced placeholder-like output for $svg" >&2
    exit 1
  fi
done

if $CHECK_ONLY && [[ $stale -ne 0 ]]; then
  exit 1
fi

if ! $CHECK_ONLY; then
  echo "Diagram render complete: $OUT"
fi
