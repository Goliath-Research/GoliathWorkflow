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

echo "Rendering presentation decks with Marp..."
for f in "$PRESENTATIONS_DIR"/*.md; do
    [ "$(basename "$f")" = "README.md" ] && continue
    marp --no-stdin "$f" --html --output "${f%.md}.html"
done

echo "Injecting Mermaid runtime into generated HTML..."
ROOT_DIR="$ROOT_DIR" python3 - <<'PY'
from pathlib import Path
import os

root = Path(os.environ["ROOT_DIR"])
presentations = root / "docs" / "presentations"

inject = """<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
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

for html in presentations.glob("*.html"):
    raw = html.read_text(encoding="utf-8")
    if "cdn.jsdelivr.net/npm/mermaid@" in raw:
        continue
    if "</body>" in raw:
        raw = raw.replace("</body>", f"{inject}\n</body>")
        html.write_text(raw, encoding="utf-8")
PY

echo "Done. HTML decks are in: $PRESENTATIONS_DIR"
