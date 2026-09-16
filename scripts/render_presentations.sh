#!/usr/bin/env bash
# Render all presentation markdown decks to HTML and PDF via Marp.
# Mermaid fences are post-processed so diagrams render in HTML and PDF.

set -euo pipefail

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
PRESENTATIONS_DIR="$ROOT_DIR/docs/presentations"
THEME_DIR="$PRESENTATIONS_DIR/themes"
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
    theme_args=()
    if [[ -f "$THEME_DIR/goliath-sales.css" ]]; then
        theme_args+=(--theme-set "$THEME_DIR/goliath-sales.css")
    fi

    # Sales decks (marp: true + custom theme) use bespoke for keyboard/progress/OSC.
    # Other decks keep bare for maximal file:// compatibility.
    template="bare"
    extra_args=()
    if grep -qE '^marp:\s*true' "$f"; then
        template="bespoke"
        extra_args+=(--bespoke.progress true --html)
    fi

    marp --no-stdin --template "$template" "${theme_args[@]}" "${extra_args[@]}" \
        "$f" --html --output "${base}.html"
    node "$EMBED_JS" "${base}.html" --pdf "${base}.pdf"
done

echo "Done. HTML and PDF decks are in: $PRESENTATIONS_DIR"
