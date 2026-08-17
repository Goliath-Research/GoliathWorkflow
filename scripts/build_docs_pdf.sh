#!/usr/bin/env bash
# Render the MkDocs site to PDF via Playwright (preserves Mermaid + MathJax).
# Produces site-pdf/MethylPipeline-Documentation.pdf
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r docs-requirements.txt
python -m playwright install chromium >/dev/null

rm -rf site site-pdf
mkdocs build --strict
mkdir -p site-pdf

python scripts/render_docs_pdf.py

echo "PDF outputs in site-pdf/:"
find site-pdf -name '*.pdf' | head -20
