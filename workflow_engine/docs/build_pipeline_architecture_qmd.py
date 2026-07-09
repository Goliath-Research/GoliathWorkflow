#!/usr/bin/env python3
"""Generate pipeline_architecture.qmd from pipeline_architecture.md (Mermaid + pre-rendered SVG for PDF)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
MD = ROOT / "pipeline_architecture.md"
QMD = ROOT / "pipeline_architecture.qmd"
DIAGRAMS_OUT = REPO / "docs" / "diagrams" / "out"

YAML = """---
title: "Configurable Methylation Pipeline — Architecture"
subtitle: "Portal, workflow database, middle-tier, workers, and scoped variables"
date: last-modified
toc: true
number-sections: true
format:
  html:
    theme: cosmo
    code-overflow: wrap
    include-after-body:
      text: |
        <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
        <script>
        document.addEventListener("DOMContentLoaded", async function () {
          if (typeof mermaid === "undefined") return;
          mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "loose" });
          var i = 0;
          for (const el of document.querySelectorAll("pre.mermaid")) {
            const code = el.querySelector("code");
            let text = (code ? code.textContent : el.textContent) || "";
            try {
              const out = await mermaid.render("mmd-" + (++i), text.trim());
              el.outerHTML = out.svg;
            } catch (err) {
              console.error("Mermaid render failed:", err);
            }
          }
        });
        </script>
  pdf:
    documentclass: scrartcl
    pdf-engine: lualatex
    colorlinks: true
    geometry:
      - margin=1in
    include-in-header:
      text: |
        \\usepackage{adjustbox}
        \\usepackage{booktabs}
        \\usepackage{graphicx}
execute:
  enabled: false
---

"""

# Map mermaid block order in pipeline_architecture.md to pre-rendered SVG assets.
# Regenerate SVGs: bash scripts/render_diagrams.sh
FIGURE_ORDER: list[tuple[str, str]] = [
    ("presentation-map", "distributed-runtime"),
    ("sample-prep-pipeline", "sample-prep-pipeline"),
    ("cohort-hierarchy", "cohort-hierarchy"),
    ("schema-tree", "schema-tree"),
    ("action-schemas", "action-schemas"),
    ("portal-editor", "portal-editor"),
    ("domain-program-compile", "domain-program-compile"),
    ("er-diagram", "er-diagram"),
    ("caas-er-diagram", "er-diagram"),
    ("scope-hierarchy", "scope-hierarchy"),
    ("worker-conditions", "worker-conditions"),
    ("methylvalidation-flow", "methylvalidation-flow"),
    ("data-driven-pipeline", "data-driven-pipeline"),
    ("worker-protocol", "worker-protocol"),
    ("cluster-storage", "cluster-storage"),
]


def wrap_mermaid(mermaid: str, fig_id: str, svg_name: str) -> str:
    svg_path = DIAGRAMS_OUT / f"{svg_name}.svg"
    pdf_block = ""
    if svg_path.is_file():
        rel = Path("../../../docs/diagrams/out") / f"{svg_name}.svg"
        pdf_block = f"""::: {{.content-visible when-format="pdf"}}
![{fig_id}]({rel.as_posix()}){{width=100%}}
:::
"""
    else:
        pdf_block = f"""::: {{.content-visible when-format="pdf"}}
*PDF figure `{svg_name}.svg` missing — run `bash scripts/render_diagrams.sh`.*
:::
"""
    return f"""::: {{.content-visible when-format="html"}}
```mermaid
{mermaid.strip()}
```
:::

{pdf_block}
"""


def main() -> None:
    text = MD.read_text(encoding="utf-8")
    text = re.sub(r"^# Configurable Methylation Pipeline — Architecture\s*\n+", "", text, count=1)

    n_mermaid = len(re.findall(r"```mermaid\n", text))
    if n_mermaid != len(FIGURE_ORDER):
        raise SystemExit(
            f"Mermaid block count ({n_mermaid}) != FIGURE_ORDER ({len(FIGURE_ORDER)}); "
            "update build_pipeline_architecture_qmd.py"
        )

    parts = re.split(r"```mermaid\n", text)
    out = [YAML + parts[0]]
    for i, chunk in enumerate(parts[1:], start=0):
        mermaid_body, rest = chunk.split("```\n", 1)
        fig_id, svg_name = FIGURE_ORDER[i]
        out.append(wrap_mermaid(mermaid_body, fig_id, svg_name))
        out.append(rest)

    rendering = """
## Rendering this document

Edit [`pipeline_architecture.md`](pipeline_architecture.md), regenerate the Quarto source, then render locally:

```bash
python workflow_engine/docs/build_pipeline_architecture_qmd.py
bash scripts/render_diagrams.sh

# HTML — use preview (recommended); Mermaid needs HTTP + JavaScript
quarto preview workflow_engine/docs/pipeline_architecture.qmd

# Or use the helper script from the repo root:
bash workflow_engine/docs/render-pipeline-architecture.sh preview

# PDF — pre-rendered SVG figures from docs/diagrams/out/ (requires TeX / lualatex)
quarto render workflow_engine/docs/pipeline_architecture.qmd --to pdf
```

**HTML:** Open the URL that `quarto preview` prints. Do **not** open `pipeline_architecture.html` directly from disk — Mermaid will not run.

**PDF:** Uses pre-rendered SVG assets (see [`docs/reference/documentation-toolchain.md`](../../docs/reference/documentation-toolchain.md)). Install TeX if needed: `quarto install tinytex`.

"""
    body = "".join(out)
    if "## Rendering this document" not in body:
        body = body.rstrip() + "\n\n---\n" + rendering

    QMD.write_text(body, encoding="utf-8")
    print(f"Wrote {QMD} ({len(FIGURE_ORDER)} diagram blocks, PDF via pre-rendered SVG)")


if __name__ == "__main__":
    main()
