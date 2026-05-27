#!/usr/bin/env bash
# Render all presentation markdown decks to HTML via Marp.

set -euo pipefail

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
PRESENTATIONS_DIR="$ROOT_DIR/docs/presentations"

if ! command -v marp >/dev/null 2>&1; then
    echo "Error: marp is not available on PATH."
    echo "Try: export PATH=\"\$(npm config get prefix)/bin:\$PATH\""
    exit 1
fi

echo "Rendering presentation decks with Marp..."
for f in "$PRESENTATIONS_DIR"/*.md; do
    [ "$(basename "$f")" = "README.md" ] && continue
    # Use the bare template to avoid iframe/presenter features that break under file:// origins.
    marp --no-stdin --template bare "$f" --html --output "${f%.md}.html"
done

echo "Done. HTML decks are in: $PRESENTATIONS_DIR"
