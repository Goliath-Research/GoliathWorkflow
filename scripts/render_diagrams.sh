#!/usr/bin/env bash
# Pre-render Mermaid sources in docs/diagrams/src/ to SVG in docs/diagrams/out/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/docs/diagrams/src"
OUT="${ROOT}/docs/diagrams/out"
CHECK_ONLY=false

usage() {
  echo "Usage: $0 [--check]" >&2
  echo "  Renders *.mmd to matching *.svg under docs/diagrams/out/." >&2
  echo "  --check  Exit 1 if any output is missing or older than its source." >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) CHECK_ONLY=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

mkdir -p "$OUT"

if ! command -v mmdc >/dev/null 2>&1; then
  if command -v npx >/dev/null 2>&1; then
    MMDC=(npx --yes @mermaid-js/mermaid-cli)
  else
    echo "ERROR: mmdc not found. Install: npm install -g @mermaid-js/mermaid-cli" >&2
    exit 1
  fi
else
  MMDC=(mmdc)
fi

stale=0
shopt -s nullglob
for mmd in "$SRC"/*.mmd; do
  base="$(basename "$mmd" .mmd)"
  svg="$OUT/${base}.svg"
  if $CHECK_ONLY; then
    if [[ ! -f "$svg" ]] || [[ "$mmd" -nt "$svg" ]]; then
      echo "STALE: $svg (regenerate with scripts/render_diagrams.sh)" >&2
      stale=1
    fi
    continue
  fi
  echo "Rendering $mmd -> $svg"
  "${MMDC[@]}" -i "$mmd" -o "$svg" -b transparent
done

if $CHECK_ONLY && [[ $stale -ne 0 ]]; then
  exit 1
fi

echo "Diagram render complete: $OUT"
