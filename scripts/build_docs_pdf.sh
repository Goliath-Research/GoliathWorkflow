#!/usr/bin/env bash
# Render the MkDocs site to PDF via Playwright (preserves Mermaid + MathJax).
# Produces site-pdf/MethylPipeline-Documentation.pdf from the already-built HTML.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r docs-requirements.txt
python -m playwright install chromium >/dev/null

rm -rf docs/theory/.quarto docs/usage/.quarto
rm -rf site site-pdf
mkdocs build --strict
mkdir -p site-pdf

python - <<'PY'
"""Print key site pages to a single aggregated PDF using Playwright."""
from pathlib import Path

from playwright.sync_api import sync_playwright

root = Path("site").resolve()
out_dir = Path("site-pdf")
out_pdf = out_dir / "MethylPipeline-Documentation.pdf"

# Landing + pillar indexes first, then deep pages in nav order (capped for CI time).
preferred = [
    "index.html",
    "overview/methylpipeline-platform-overview/index.html",
    "theory/index.html",
    "usage/index.html",
    "usage/alignment-engines/index.html",
    "usage/03-sample-prep-and-qc/index.html",
    "usage/18-samd-study-lifecycle/index.html",
    "architecture/layer-model/index.html",
    "architecture/end-to-end-workflow/index.html",
    "deployment/operator-journey/index.html",
    "regulatory/index.html",
    "regulatory/change-management-plan/index.html",
    "reference/documentation-toolchain/index.html",
    "CONTRIBUTING/index.html",
]

pages = []
for rel in preferred:
    path = root / rel
    if path.is_file():
        pages.append(path)

# Fill remaining HTML pages (stable order) up to a soft cap.
cap = 40
for path in sorted(root.rglob("index.html")):
    if path in pages:
        continue
    # Skip search / 404
    if "404" in path.parts:
        continue
    pages.append(path)
    if len(pages) >= cap:
        break

if not pages:
    raise SystemExit("No HTML pages found under site/")

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context()
    pdf_bytes = []
    for i, path in enumerate(pages):
        page = context.new_page()
        page.goto(path.as_uri(), wait_until="networkidle")
        # Allow MathJax + Mermaid to finish
        page.wait_for_timeout(800)
        pdf_bytes.append(
            page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
            )
        )
        page.close()
        print(f"rendered {i+1}/{len(pages)} {path.relative_to(root)}")
    browser.close()

# Concatenate with pypdf if available; else keep first page set as multi-file.
try:
    from pypdf import PdfWriter, PdfReader
    import io

    writer = PdfWriter()
    for blob in pdf_bytes:
        reader = PdfReader(io.BytesIO(blob))
        for page in reader.pages:
            writer.add_page(page)
    with out_pdf.open("wb") as fh:
        writer.write(fh)
    print(f"wrote {out_pdf} ({len(writer.pages)} pages)")
except Exception as exc:  # noqa: BLE001
    # Fallback: write individual PDFs
    print(f"pypdf merge unavailable ({exc}); writing per-page PDFs")
    for i, blob in enumerate(pdf_bytes):
        (out_dir / f"page-{i:03d}.pdf").write_bytes(blob)
    out_pdf.write_bytes(pdf_bytes[0])
    print(f"wrote {out_pdf} (first page only) + page-*.pdf")
PY

echo "PDF outputs in site-pdf/:"
find site-pdf -name '*.pdf' | head -20
