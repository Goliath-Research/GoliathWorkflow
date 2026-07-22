#!/usr/bin/env bash
# Render all presentation markdown decks to HTML and PDF via Marp.
# Mermaid fences are post-processed so diagrams render in HTML and PDF.

set -euo pipefail

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
PRESENTATIONS_DIR="$ROOT_DIR/docs/presentations"
EMBED_JS="$ROOT_DIR/scripts/embed_marp_mermaid.mjs"

if ! command -v marp >/dev/null 2>&1; then
    echo "Error: marp is not available on PATH."
    echo "Try: export PATH=\"\$(npm config get prefix)/bin:\$PATH\""
    exit 1
fi

if ! command -v node >/dev/null 2>&1; then
    echo "Error: node is required to embed Mermaid into Marp HTML."
    exit 1
fi

echo "Rendering presentation decks with Marp (HTML + Mermaid + PDF)..."
for f in "$PRESENTATIONS_DIR"/*.md; do
    [ "$(basename "$f")" = "README.md" ] && continue
    base="${f%.md}"
    # Use the bare template to avoid iframe/presenter features that break under file:// origins.
    marp --no-stdin --template bare "$f" --html --output "${base}.html"
    node "$EMBED_JS" "${base}.html" --pdf "${base}.pdf"
done

echo "Done. HTML and PDF decks are in: $PRESENTATIONS_DIR"
