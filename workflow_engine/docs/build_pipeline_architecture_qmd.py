#!/usr/bin/env python3
"""Generate pipeline_architecture.qmd from pipeline_architecture.md (dual HTML/PDF diagrams)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MD = ROOT / "pipeline_architecture.md"
QMD = ROOT / "pipeline_architecture.qmd"

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
  pdf:
    documentclass: scrartcl
    pdf-engine: lualatex
    colorlinks: true
    geometry:
      - margin=1in
    include-in-header:
      text: |
        \\usepackage{tikz}
        \\usetikzlibrary{arrows.meta,positioning,fit,backgrounds,calc,shapes.geometric,shapes.multipart}
execute:
  enabled: false
---

"""

# Compact TikZ figures for PDF (vector quality; mirrors Mermaid in the Markdown source).
TIKZ: dict[str, str] = {
    "presentation-map": r"""
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
  scale=0.78, every node/.style={transform shape},
  box/.style={draw, rounded corners=2pt, align=center, font=\scriptsize, minimum height=0.55cm, text width=2.1cm},
  store/.style={box, cylinder, shape border rotate=90, aspect=0.25, fill=gray!12},
  arr/.style={-{Latex[length=1.6mm]}, thick},
  darr/.style={arr, dashed}
]
\node[box, fill=blue!8] (editor) {Config editor\\Web};
\node[box, fill=blue!8, right=0.9cm of editor] (run) {Start run\\REST};
\node[box, fill=green!8, below=1.1cm of editor] (def) {DataDriven\\Pipeline};
\node[box, fill=green!8, right=0.5cm of def] (inst) {instance\\context\_json};
\node[box, fill=green!8, right=0.5cm of inst] (exec) {node\_exec\\scope\_var};
\node[box, fill=orange!10, below=1.1cm of def] (rest) {REST\\:8080};
\node[box, fill=orange!10, right=0.6cm of rest] (engine) {Engine\\procs};
\node[box, fill=purple!8, below=1.0cm of rest] (w1) {centroid};
\node[box, fill=purple!8, right=0.35cm of w1] (w2) {detector};
\node[box, fill=purple!8, right=0.35cm of w2] (w3) {mapper\ldots};
\node[store, right=2.2cm of exec] (stor) {Shared\\storage /work};
\draw[arr] (editor)--(run); \draw[arr] (run)--(inst);
\draw[arr] (def)--(inst); \draw[arr] (inst)--(exec);
\draw[arr] (rest)--(engine); \draw[arr] (engine)--(exec);
\draw[arr] (w1)--(rest); \draw[arr] (w2)--(rest); \draw[arr] (w3)--(rest);
\draw[arr] (w1)--(stor); \draw[arr] (w2)--(stor); \draw[arr] (w3)--(stor);
\draw[darr] (exec)--node[above, font=\tiny]{paths}(stor);
\node[font=\footnotesize\bfseries, above=0.15cm of editor] {Portal};
\node[font=\footnotesize\bfseries, above=0.15cm of def] {Database};
\node[font=\footnotesize\bfseries, above=0.15cm of rest] {Middle-tier};
\node[font=\footnotesize\bfseries, above=0.15cm of w2] {Workers};
\end{tikzpicture}
\caption{Four-layer architecture: portal, database, middle-tier, and cluster workers.}
\end{figure}
""",
    "cohort-hierarchy": r"""
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
  scale=0.85, every node/.style={transform shape},
  box/.style={draw, rounded corners=2pt, align=center, font=\scriptsize, text width=2.4cm, minimum height=0.5cm},
  arr/.style={-{Latex[length=1.6mm]}, thick}
]
\node[box, fill=gray!10] (root) {ProjectConfig};
\node[box, below=0.45cm of root] (meta) {metadata, paths};
\node[box, below left=0.55cm and 0.2cm of meta] (ctrl) {control side};
\node[box, below right=0.55cm and 0.2cm of meta] (dis) {disease side};
\node[box, below=0.45cm of meta] (cmp) {comparisons};
\node[box, left=0.15cm of cmp] (chr) {chromosomes};
\node[box, right=0.15cm of cmp] (sc) {step\_config};
\node[box, below=0.45cm of ctrl] (g1) {groups[]};
\node[box, below=0.45cm of dis] (g2) {groups[]};
\node[box, below=0.45cm of g2] (st) {stages[]};
\draw[arr] (root)--(meta); \draw[arr] (meta)--(ctrl); \draw[arr] (meta)--(dis);
\draw[arr] (meta)--(cmp); \draw[arr] (meta)--(chr); \draw[arr] (meta)--(sc);
\draw[arr] (ctrl)--(g1); \draw[arr] (dis)--(g2); \draw[arr] (g2)--(st);
\end{tikzpicture}
\caption{Project configuration JSON hierarchy.}
\end{figure}
""",
    "schema-tree": r"""
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
  scale=0.82, every node/.style={transform shape},
  box/.style={draw, rounded corners=2pt, align=center, font=\scriptsize, text width=2.2cm},
  arr/.style={-{Latex[length=1.6mm]}, thick}
]
\node[box, fill=gray!10] (pcs) {project\_config.schema};
\node[box, right=0.55cm of pcs] (cds) {\$defs\\ControlDiseaseSide};
\node[box, above=0.4cm of cds] (gc) {\$defs\\GroupConfig};
\node[box, below=0.4cm of cds] (cs) {\$defs\\ComparisonSpec};
\node[box, right=0.55cm of cds] (sc) {step\_config};
\node[box, above=0.35cm of sc] (cent) {centroid.schema};
\node[box, below=0.15cm of sc] (det) {detection.schema};
\node[box, below=0.55cm of sc] (map) {mapper.schema};
\draw[arr] (pcs)--(cds); \draw[arr] (pcs)--(gc); \draw[arr] (pcs)--(cs);
\draw[arr] (pcs)--(sc); \draw[arr] (sc)--(cent); \draw[arr] (sc)--(det); \draw[arr] (sc)--(map);
\end{tikzpicture}
\caption{JSON Schema reference tree (excerpt).}
\end{figure}
""",
    "portal-editor": r"""
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
  scale=0.82, every node/.style={transform shape},
  box/.style={draw, rounded corners=2pt, align=center, font=\scriptsize, text width=1.9cm},
  arr/.style={-{Latex[length=1.6mm]}, thick}
]
\node[box] (user) {Portal user};
\node[box, right=0.7cm of user] (web) {Editor Web\\:8077};
\node[box, below=0.8cm of web] (json) {project.json};
\node[box, above=0.7cm of web] (schemas) {*.schema.json};
\node[box, left=0.7cm of schemas] (loader) {Schema\\loader};
\node[box, right=0.7cm of schemas] (grid) {Property\\grid};
\draw[arr] (user)--node[above, font=\tiny]{upload}(web);
\draw[arr] (schemas)--(loader); \draw[arr] (loader)--(grid); \draw[arr] (grid)--(json);
\draw[arr] (json)--node[below, font=\tiny]{download}(user);
\end{tikzpicture}
\caption{Schema-driven portal config editor flow.}
\end{figure}
""",
    "er-diagram": r"""
\begin{figure}[htbp]
\centering
\small
\begin{tabular}{@{}ll@{}}
\textbf{workflow\_def} & 1--* \textbf{workflow\_version} \\
\textbf{workflow\_version} & 1--* \textbf{workflow\_node}, 1--* \textbf{workflow\_instance} \\
\textbf{workflow\_node} & *--* \textbf{workflow\_edge}; 0..1 \textbf{workflow\_input\_template} \\
\textbf{workflow\_instance} & 1--* \textbf{node\_execution} \\
\textbf{node\_execution} & 0..1 \textbf{task\_lease}; scope via \textbf{scope\_variable} \\
\textbf{cluster} & 1--* \textbf{worker} $\to$ \textbf{worker\_token} \\
\end{tabular}
\caption{Workflow database entity relationships (simplified).}
\end{figure}
""",
    "scope-hierarchy": r"""
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
  scale=0.88, every node/.style={transform shape},
  box/.style={draw, rounded corners=2pt, align=center, font=\scriptsize, text width=2.5cm},
  arr/.style={-{Latex[length=1.6mm]}, thick},
  darr/.style={arr, dashed}
]
\node[box] (ctx) {context\_json};
\node[box, below=0.5cm of ctx] (root) {scope id = 0};
\node[box, below=0.5cm of root] (fecp) {FOREACH scope};
\node[box, below=0.5cm of fecp] (seq) {SEQUENCE scope};
\node[box, below=0.5cm of seq] (act) {ACTION scope};
\draw[arr] (ctx)--(root); \draw[arr] (root)--(fecp); \draw[arr] (fecp)--(seq); \draw[arr] (seq)--(act);
\draw[arr, looseness=4] (act) to[bend left=35] node[right, font=\tiny]{output bind.}(act);
\draw[darr] (act) to[bend right=25] node[left, font=\tiny]{parent walk}(seq);
\end{tikzpicture}
\caption{Scoped variable hierarchy along the execution tree.}
\end{figure}
""",
    "worker-conditions": r"""
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
  scale=0.85, every node/.style={transform shape},
  box/.style={draw, rounded corners=2pt, align=center, font=\scriptsize, text width=2.0cm},
  arr/.style={-{Latex[length=1.6mm]}, thick}
]
\node[box, fill=orange!10] (e) {Engine};
\node[box, fill=purple!8, right=1.2cm of e] (w) {Worker ACTION};
\node[box, fill=green!8, below=0.9cm of e] (s) {scope\_variable};
\node[box, fill=orange!10, right=1.2cm of s] (cf) {IF / SWITCH / WHILE};
\draw[arr] (e)--node[above, font=\tiny]{input\_json}(w);
\draw[arr] (w)--node[right, font=\tiny]{submit}(e);
\draw[arr] (e)--node[left, font=\tiny]{bindings}(s);
\draw[arr] (s)--(cf); \draw[arr] (cf)--node[above, font=\tiny]{branch}(e);
\end{tikzpicture}
\caption{Worker-driven conditions: ACTION output updates scope, then control flow branches.}
\end{figure}
""",
    "methylvalidation-flow": r"""
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
  scale=0.82, every node/.style={transform shape},
  box/.style={draw, rounded corners=2pt, align=center, font=\scriptsize, text width=2.0cm},
  arr/.style={-{Latex[length=1.6mm]}, thick}
]
\node[box] (root) {SEQUENCE root};
\node[box, below left=0.6cm and 0.1cm of root] (feat) {REPEAT MC feature};
\node[box, below right=0.6cm and 0.1cm of root] (fin) {SEQUENCE final};
\node[box, below=0.5cm of feat] (fc) {centroid};
\node[box, right=0.4cm of fc] (fd) {detector};
\node[box, below=0.5cm of fin] (map) {mapper $\to$ enricher $\to$ prog.};
\draw[arr] (root)--(feat); \draw[arr] (root)--(fin);
\draw[arr] (feat)--(fc); \draw[arr] (feat)--(fd); \draw[arr] (fin)--(map);
\end{tikzpicture}
\caption{MethylValidationFlow: Monte Carlo feature loop then final full-sample pipeline.}
\end{figure}
""",
    "data-driven-pipeline": r"""
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
  scale=0.75, every node/.style={transform shape},
  box/.style={draw, rounded corners=2pt, align=center, font=\tiny, text width=1.85cm},
  arr/.style={-{Latex[length=1.4mm]}, thick}
]
\node[box] (root) {SEQUENCE root};
\node[box, below left=0.55cm of root] (fecp) {FOREACH comparisons};
\node[box, below right=0.55cm of root] (post) {post pipeline};
\node[box, below=0.45cm of fecp] (fechr) {FOREACH chromosomes};
\node[box, below=0.45cm of fechr] (seq) {one chromosome};
\node[box, below left=0.4cm of seq] (par) {PARALLEL centroids};
\node[box, below right=0.4cm of seq] (det) {detect};
\draw[arr] (root)--(fecp); \draw[arr] (root)--(post);
\draw[arr] (fecp)--(fechr); \draw[arr] (fechr)--(seq);
\draw[arr] (seq)--(par); \draw[arr] (seq)--(det);
\end{tikzpicture}
\caption{DataDrivenPipeline workflow tree (static nodes, data-driven fan-out).}
\end{figure}
""",
    "worker-protocol": r"""
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
  scale=0.85, every node/.style={transform shape},
  box/.style={draw, rounded corners=2pt, align=center, font=\scriptsize, text width=1.8cm},
  arr/.style={-{Latex[length=1.6mm]}, thick}
]
\node[box, fill=purple!8] (w) {Worker};
\node[box, fill=orange!10, right=1.0cm of w] (mt) {REST API};
\node[box, fill=green!8, right=1.0cm of mt] (db) {Database};
\draw[arr] (w)--node[above, font=\tiny]{request task}(mt);
\draw[arr] (mt)--node[above, font=\tiny]{sp\_worker\_request}(db);
\draw[arr] (db)--node[below, font=\tiny]{input\_json}(mt);
\draw[arr] (mt)--node[below, font=\tiny]{has\_task}(w);
\draw[arr] (w)--node[above, font=\tiny]{submit result}(mt);
\draw[arr] (mt)--node[above, font=\tiny]{on\_action\_complete}(db);
\end{tikzpicture}
\caption{Worker poll / submit protocol via stateless middle-tier.}
\end{figure}
""",
    "cluster-storage": r"""
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
  scale=0.78, every node/.style={transform shape},
  box/.style={draw, rounded corners=2pt, align=center, font=\scriptsize, text width=1.7cm},
  store/.style={box, fill=gray!12, text width=2.4cm},
  arr/.style={-{Latex[length=1.6mm]}, thick}
]
\node[box] (n1) {centroid worker};
\node[box, right=0.3cm of n1] (n2) {detector worker};
\node[box, right=0.3cm of n2] (n3) {mapper worker};
\node[store, below=1.0cm of n2] (stor) {Shared /work\\centroids, detections, mapper};
\node[box, fill=orange!10, above=0.9cm of n2] (mt) {Middle-tier};
\node[box, fill=green!8, left=1.2cm of mt] (db) {Database};
\draw[arr] (n1)--(stor); \draw[arr] (n2)--(stor); \draw[arr] (n3)--(stor);
\draw[arr] (n1)--(mt); \draw[arr] (n2)--(mt); \draw[arr] (n3)--(mt);
\draw[arr] (mt)--(db);
\end{tikzpicture}
\caption{Cluster workers share NFS/Azure Files storage; coordination via database only.}
\end{figure}
""",
}

FIGURE_ORDER = [
    "presentation-map",
    "cohort-hierarchy",
    "schema-tree",
    "portal-editor",
    "er-diagram",
    "scope-hierarchy",
    "worker-conditions",
    "methylvalidation-flow",
    "data-driven-pipeline",
    "worker-protocol",
    "cluster-storage",
]


def wrap_mermaid(mermaid: str, fig_id: str) -> str:
    tikz = TIKZ[fig_id]
    return f"""::: {{.content-visible when-format="html"}}
```mermaid
{mermaid.strip()}
```
:::

::: {{.content-visible when-format="pdf"}}
```{{=latex}}
{tikz.strip()}
```
:::

"""


def main() -> None:
    text = MD.read_text(encoding="utf-8")
    # Drop duplicate top-level title; YAML supplies title.
    text = re.sub(r"^# Configurable Methylation Pipeline — Architecture\s*\n+", "", text, count=1)

    parts = re.split(r"```mermaid\n", text)
    out = [YAML + parts[0]]
    for i, chunk in enumerate(parts[1:], start=0):
        mermaid_body, rest = chunk.split("```\n", 1)
        fig_id = FIGURE_ORDER[i]
        out.append(wrap_mermaid(mermaid_body, fig_id))
        out.append(rest)

    rendering = """
## Rendering this document

This Quarto source is generated from [`pipeline_architecture.md`](pipeline_architecture.md). Edit the Markdown, then regenerate:

```bash
python workflow_engine/docs/build_pipeline_architecture_qmd.py
quarto render workflow_engine/docs/pipeline_architecture.qmd --to html
quarto render workflow_engine/docs/pipeline_architecture.qmd --to pdf
```

- **HTML** uses interactive Mermaid diagrams.
- **PDF** uses TikZ vector figures (same approach as [`docs/MethylPipeline-overview.qmd`](../../docs/MethylPipeline-overview.qmd)).
- PDF requires a TeX installation (`quarto install tinytex` or TeX Live with `lualatex`).

"""
    body = "".join(out)
    if "## Rendering this document" not in body:
        body = body.rstrip() + "\n\n---\n" + rendering

    QMD.write_text(body, encoding="utf-8")
    print(f"Wrote {QMD} ({len(FIGURE_ORDER)} diagram pairs)")


if __name__ == "__main__":
    main()
