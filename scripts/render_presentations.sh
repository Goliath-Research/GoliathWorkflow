#!/usr/bin/env bash
# Render all presentation markdown decks to HTML and enable Mermaid diagrams.

set -euo pipefail

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
PRESENTATIONS_DIR="$ROOT_DIR/docs/presentations"

if ! command -v marp >/dev/null 2>&1; then
    echo "Error: marp is not available on PATH."
    echo "Try: export PATH=\"\$(npm config get prefix)/bin:\$PATH\""
    exit 1
fi

NPM_ROOT="$(npm root -g)"
MERMAID_BUNDLE="$NPM_ROOT/mermaid/dist/mermaid.min.js"
if [ ! -f "$MERMAID_BUNDLE" ]; then
    echo "Mermaid bundle not found in current npm global path."
    echo "Attempting to install mermaid globally..."
    npm install -g mermaid >/dev/null
    NPM_ROOT="$(npm root -g)"
    MERMAID_BUNDLE="$NPM_ROOT/mermaid/dist/mermaid.min.js"
fi
if [ ! -f "$MERMAID_BUNDLE" ]; then
    echo "Error: Mermaid bundle not found at $MERMAID_BUNDLE"
    echo "Install with: npm install -g mermaid"
    exit 1
fi

echo "Rendering presentation decks with Marp..."
for f in "$PRESENTATIONS_DIR"/*.md; do
    [ "$(basename "$f")" = "README.md" ] && continue
    marp --no-stdin "$f" --html --output "${f%.md}.html"
done

echo "Injecting Mermaid runtime into generated HTML..."
ROOT_DIR="$ROOT_DIR" MERMAID_BUNDLE="$MERMAID_BUNDLE" python3 - <<'PY'
from pathlib import Path
import os

root = Path(os.environ["ROOT_DIR"])
presentations = root / "docs" / "presentations"
mermaid_bundle = Path(os.environ["MERMAID_BUNDLE"]).read_text(encoding="utf-8")

inject = (
    "<script>\n"
    + mermaid_bundle
    + "\n</script>\n"
    + """<script>
(function () {
  if (!window.mermaid) return;
  mermaid.initialize({ startOnLoad: false, securityLevel: "loose" });
  const blocks = document.querySelectorAll("pre code.language-mermaid");
  blocks.forEach((code) => {
    const pre = code.closest("pre");
    if (!pre) return;
    const div = document.createElement("div");
    div.className = "mermaid";
    div.textContent = code.textContent;
    pre.replaceWith(div);
  });
  mermaid.run({ querySelector: ".mermaid" });
})();
</script>
"""
)

for html in presentations.glob("*.html"):
    raw = html.read_text(encoding="utf-8")
    if "mermaid.initialize({ startOnLoad: false, securityLevel: \"loose\" });" in raw:
        continue
    if "</body>" in raw:
        raw = raw.replace("</body>", f"{inject}\n</body>")
        html.write_text(raw, encoding="utf-8")
PY

echo "Done. HTML decks are in: $PRESENTATIONS_DIR"
