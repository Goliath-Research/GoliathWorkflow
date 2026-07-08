#!/usr/bin/env bash
# Copy versioned canvases from docs/canvas/ into Cursor's IDE-managed canvases folder.
#
# Usage (from repo root):
#   bash scripts/sync_cursor_canvases.sh
#
# Optional:
#   CURSOR_CANVASES_DIR=~/.cursor/projects/<slug>/canvases bash scripts/sync_cursor_canvases.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC="$REPO_ROOT/docs/canvas"

if [[ ! -d "$SRC" ]]; then
  echo "Missing canvas source: $SRC" >&2
  exit 1
fi

discover_cursor_canvases_dir() {
  local repo_name
  repo_name="$(basename "$REPO_ROOT")"
  local projects_root="${HOME}/.cursor/projects"
  if [[ ! -d "$projects_root" ]]; then
    return 1
  fi
  local candidate
  for candidate in "$projects_root"/*/canvases; do
    [[ -d "$candidate" ]] || continue
    local slug
    slug="$(basename "$(dirname "$candidate")")"
    if [[ "$slug" == *"$repo_name"* ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

DEST="${CURSOR_CANVASES_DIR:-}"
if [[ -z "$DEST" ]]; then
  DEST="$(discover_cursor_canvases_dir || true)"
fi

if [[ -z "$DEST" ]]; then
  cat >&2 <<EOF
Could not find Cursor canvases directory for repo '$REPO_ROOT'.

Set CURSOR_CANVASES_DIR explicitly, for example:
  CURSOR_CANVASES_DIR="\$HOME/.cursor/projects/<workspace-slug>/canvases" \\
    bash scripts/sync_cursor_canvases.sh

Or open this repo once in Cursor so ~/.cursor/projects/<slug>/canvases exists, then re-run.
EOF
  exit 1
fi

mkdir -p "$DEST"

shopt -s nullglob
copied=0
for path in "$SRC"/*.canvas.tsx "$SRC"/*.canvas.data.json; do
  [[ -f "$path" ]] || continue
  cp -f "$path" "$DEST/"
  echo "Synced $(basename "$path") -> $DEST/"
  copied=$((copied + 1))
done

if [[ -f "$SRC/tsconfig.json" ]]; then
  cp -f "$SRC/tsconfig.json" "$DEST/"
  echo "Synced tsconfig.json -> $DEST/"
fi

if [[ "$copied" -eq 0 ]]; then
  echo "No canvas files found under $SRC" >&2
  exit 1
fi

echo "Done. $copied canvas file(s) in $DEST"
