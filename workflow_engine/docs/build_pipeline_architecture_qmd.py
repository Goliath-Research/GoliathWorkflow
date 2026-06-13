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
        \\usepackage{tikz}
        \\usetikzlibrary{arrows.meta,positioning,fit,backgrounds,calc,shapes.geometric}
execute:
  enabled: false
---

"""

# Shared TikZ styles (match docs/MethylPipeline-overview.qmd quality).
_TIKZ_STYLES = r"""
  node distance=0.65cm and 0.55cm,
  every node/.style={transform shape},
  base/.style={draw, rounded corners=3pt, align=center, font=\footnotesize, minimum height=0.72cm, text width=2.6cm},
  arr/.style={-{Latex[length=2mm]}, thick},
  darr/.style={arr, dashed}
"""


def _fig(tikz_body: str, caption: str) -> str:
    return rf"""
\begin{{figure}}[htbp]
\centering
\begin{{adjustbox}}{{max width=\linewidth,center}}
\begin{{tikzpicture}}[{_TIKZ_STYLES.strip()}]
{tikz_body.strip()}
\end{{tikzpicture}}
\end{{adjustbox}}
\caption{{{caption}}}
\end{{figure}}
"""


# TikZ figures for PDF (vector; mirrors Mermaid in pipeline_architecture.md).
TIKZ: dict[str, str] = {
    "presentation-map": _fig(
        r"""
\node[base, fill=blue!10] (editor) {Schema config editor\\(Web :8077)};
\node[base, fill=blue!10, right=0.55cm of editor] (runprep) {Start SamplePrep};
\node[base, fill=blue!10, right=0.55cm of runprep] (runddp) {Start DataDriven};
\node[draw, dashed, rounded corners=4pt, inner sep=0.35cm, fill=blue!6, fit=(editor)(runprep)(runddp), label={[font=\small\bfseries]above:Company Portal}] (portalbox) {};
\node[base, fill=green!10, below=1.35cm of runprep] (wfprep) {SamplePrepPipeline};
\node[base, fill=green!10, right=0.55cm of wfprep] (wfdef) {DataDrivenPipeline};
\node[base, fill=green!10, right=0.55cm of wfdef] (inst) {workflow\_instance\\context\_json};
\node[base, fill=green!10, right=0.55cm of inst] (nexec) {node\_execution\\scope\_variable};
\node[draw, dashed, rounded corners=4pt, inner sep=0.35cm, fill=green!6, fit=(wfprep)(wfdef)(inst)(nexec), label={[font=\small\bfseries]above:Backend Database}] (dbbox) {};
\node[base, fill=orange!12, below=1.35cm of wfprep] (rest) {WfEngine REST\\:8080};
\node[base, fill=orange!12, right=0.75cm of rest] (engine) {Engine procs\\T-SQL / PL/pgSQL};
\node[draw, dashed, rounded corners=4pt, inner sep=0.35cm, fill=orange!8, fit=(rest)(engine), label={[font=\small\bfseries]above:Middle-Tier}] (mtbox) {};
\node[base, fill=purple!10, below=1.25cm of rest] (w0) {download / Parabricks / QC / extract};
\node[base, fill=purple!10, right=0.4cm of w0] (w1) {methyl-centroid / detector};
\node[base, fill=purple!10, right=0.4cm of w1] (w3) {mapper / enricher / prog.};
\node[draw, dashed, rounded corners=4pt, inner sep=0.35cm, fill=purple!6, fit=(w0)(w1)(w3), label={[font=\small\bfseries]above:Remote Workers}] (wbox) {};
\node[base, fill=gray!12, right=1.6cm of inst] (stor) {Shared storage\\NFS / Azure Files\\/work/...};
\draw[arr] (editor)--(runprep); \draw[arr] (runprep)--(wfprep);
\draw[arr] (wfprep)--node[above, font=\scriptsize]{HDF5 ready}(runddp);
\draw[arr] (runddp)--(wfdef);
\draw[arr] (wfdef)--(inst); \draw[arr] (inst)--(nexec);
\draw[arr] (rest)--(engine); \draw[arr] (engine)--(nexec);
\draw[arr] (w0)--(rest); \draw[arr] (w1)--(rest); \draw[arr] (w3)--(rest);
\draw[arr] (w0)--(stor); \draw[arr] (w1)--(stor); \draw[arr] (w3)--(stor);
\draw[darr] (nexec)--node[above, font=\scriptsize]{input paths}(stor);
""",
        "Four-layer architecture: portal, database, middle-tier, and cluster workers.",
    ),
    "sample-prep-pipeline": _fig(
        r"""
\node[base] (dl) {download FASTQs};
\node[base, right=0.35cm of dl] (align) {Parabricks fq2bam};
\node[base, right=0.35cm of align] (delFq) {delete FASTQs};
\node[base, right=0.35cm of delFq] (qc) {methyl-qc};
\node[base, below=0.85cm of qc] (gate) {QC pass?};
\node[base, left=1.2cm of gate] (fail) {mark failed};
\node[base, right=1.2cm of gate] (cfdna) {cfDNA?};
\node[base, right=0.55cm of cfdna] (frag) {fragmentomics};
\node[base, below=0.85cm of gate] (ext) {MethylExtractor};
\node[base, right=0.55cm of ext] (delBam) {delete BAM};
\node[base, below=0.85cm of ext] (h5) {chrom-CG.h5};
\draw[arr] (dl)--(align)--(delFq)--(qc)--(gate);
\draw[arr] (gate)--node[left, font=\scriptsize]{no}(fail);
\draw[arr] (gate)--node[right, font=\scriptsize]{yes}(cfdna);
\draw[arr] (cfdna)--node[above, font=\scriptsize]{yes}(frag);
\draw[arr] (cfdna)--(ext); \draw[arr] (frag)--(ext);
\draw[arr] (ext)--(delBam)--(h5);
""",
        "SamplePrepPipeline per-sample step order (QC before fragmentomics; cfDNA branch).",
    ),
    "cohort-hierarchy": _fig(
        r"""
\node[base, fill=gray!10] (root) {ProjectConfig};
\node[base, below=of root] (meta) {Metadata and paths};
\node[base, below left=0.7cm and 0.3cm of meta] (ctrl) {control side};
\node[base, below right=0.7cm and 0.3cm of meta] (dis) {disease side};
\node[base, below=of meta] (cmp) {comparisons};
\node[base, left=0.5cm of cmp] (chr) {chromosomes};
\node[base, right=0.5cm of cmp] (sc) {step\_config};
\node[base, below=of ctrl] (g1) {groups[]};
\node[base, below=of dis] (g2) {groups[]};
\node[base, below=of g2] (st) {stages[] (optional)};
\draw[arr] (root)--(meta);
\draw[arr] (meta)--(ctrl); \draw[arr] (meta)--(dis);
\draw[arr] (meta)--(cmp); \draw[arr] (meta)--(chr); \draw[arr] (meta)--(sc);
\draw[arr] (ctrl)--(g1); \draw[arr] (dis)--(g2); \draw[arr] (g2)--(st);
""",
        "Project configuration JSON hierarchy.",
    ),
    "schema-tree": _fig(
        r"""
\node[base, fill=gray!10] (pcs) {project\_config.schema.json};
\node[base, right=1.0cm of pcs] (cds) {\$defs: ControlDiseaseSide};
\node[base, above=0.45cm of cds] (gc) {\$defs: GroupConfig};
\node[base, below=0.45cm of cds] (cs) {\$defs: ComparisonSpec};
\node[base, right=1.0cm of cds] (sc) {step\_config keys};
\node[base, above=0.35cm of sc] (cent) {centroid.schema};
\node[base] at (sc |- cs) (det) {detection.schema};
\node[base, below=0.35cm of sc] (map) {mapper.schema};
\draw[arr] (pcs)--(cds); \draw[arr] (pcs)--(gc); \draw[arr] (pcs)--(cs);
\draw[arr] (pcs)--(sc);
\draw[arr] (sc)--(cent); \draw[arr] (sc)--(det); \draw[arr] (sc)--(map);
""",
        "JSON Schema reference tree (excerpt).",
    ),
    "action-schemas": _fig(
        r"""
\node[base] (pm) {Pydantic task\\models};
\node[base, right=0.45cm of pm] (exp) {methyl-export-\\task-schemas};
\node[base, right=0.45cm of exp] (db) {wf.workflow\_\\action\_schema};
\node[base, right=0.45cm of db] (gw) {GET /v1/actions};
\node[base, below=0.75cm of gw] (ed) {Config Editor};
\node[base, left=0.75cm of ed] (wk) {Worker runtime};
\draw[arr] (pm)--(exp)--(db)--(gw);
\draw[arr] (gw)--(ed);
\draw[arr] (pm)--(wk);
""",
        "Action payload schemas: Pydantic models to database and runtime validation.",
    ),
    "portal-editor": _fig(
        r"""
\node[base] (user) {Portal user\\(browser)};
\node[base, right=1.0cm of user] (web) {MethylConfigEditorWeb\\:8077};
\node[base, above=0.75cm of web] (schemas) {schemas/config/*.schema.json};
\node[base, left=0.75cm of schemas] (loader) {JsonSchemaLoader};
\node[base, right=0.75cm of schemas] (grid) {Property grid /\\nested editors};
\node[base, below=0.85cm of web] (json) {project.json\\upload / download};
\draw[arr] (user)--node[above, font=\scriptsize]{upload}(web);
\draw[arr] (schemas)--(loader); \draw[arr] (loader)--(grid);
\draw[arr] (grid)--(json);
\draw[arr] (json)--node[below, font=\scriptsize]{download}(user);
""",
        "Schema-driven portal config editor flow.",
    ),
    "domain-program-compile": _fig(
        r"""
\node[base] (client) {Client\\DomainProgram};
\node[base, fill=green!10, right=1.1cm of client] (db) {Engine (DB)};
\node[base, fill=purple!10, right=1.1cm of db] (worker) {Worker};
\draw[arr] (client)--node[above, font=\scriptsize]{POST instance\\projectPath}(db);
\draw[arr, looseness=2.5] (db) to[bend left=35] node[above, font=\scriptsize]{init scope}(db);
\draw[arr, looseness=4] (db) to[bend left=55] node[above, font=\scriptsize]{resolve bindings}(db);
\draw[arr, looseness=5.5] (db) to[bend left=75] node[above, font=\scriptsize]{FOREACH / PARALLEL}(db);
\draw[arr] (worker)--node[below, font=\scriptsize]{request task}(db);
\draw[arr] (db)--node[below, font=\scriptsize]{concrete input\_json}(worker);
""",
        "DomainProgram compile and instance start: collection bindings then concrete worker tasks.",
    ),
    "er-diagram": r"""
\begin{figure}[htbp]
\centering
\small
\begin{tabular}{@{}>{\raggedright\arraybackslash}p{0.42\linewidth} p{0.5\linewidth}@{}}
\toprule
\textbf{Entity} & \textbf{Relationships} \\
\midrule
workflow\_def & 1--* workflow\_version \\
workflow\_version & 1--* workflow\_node; 1--* workflow\_instance \\
workflow\_node & *--* workflow\_edge; 0..1 input template \\
workflow\_instance & 1--* node\_execution \\
node\_execution & 0..1 task\_lease; scope via scope\_variable \\
cluster & 1--* worker $\rightarrow$ worker\_token \\
\bottomrule
\end{tabular}
\caption{Workflow database entity relationships (simplified).}
\end{figure}
""",
    "scope-hierarchy": _fig(
        r"""
\node[base] (ctx) {context\_json\\(instance start)};
\node[base, below=of ctx] (root) {scope id = 0\\global variables};
\node[base, below=of root] (fecp) {FOREACH scope\\item fields bound};
\node[base, below=of fecp] (seq) {SEQUENCE scope\\copied from parent};
\node[base, below=of seq] (act) {ACTION scope\\output bindings};
\draw[arr] (ctx)--node[right, font=\scriptsize]{init scope}(root);
\draw[arr] (root)--(fecp); \draw[arr] (fecp)--(seq); \draw[arr] (seq)--(act);
\draw[arr, looseness=5] (act) to[bend left=40] node[right, font=\scriptsize]{on submit}(act);
\draw[darr] (act) to[bend right=30] node[left, font=\scriptsize]{parent walk}(seq);
""",
        "Scoped variable hierarchy along the execution tree.",
    ),
    "worker-conditions": _fig(
        r"""
\node[base, fill=orange!12] (e) {Workflow engine};
\node[base, fill=purple!10, right=1.3cm of e] (w) {Worker ACTION\\(QC, rules, \ldots)};
\node[base, fill=green!10, below=1.0cm of e] (s) {scope\_variable\\shouldRunQc, mode, \ldots};
\node[base, fill=orange!12, right=1.3cm of s] (cf) {IF / SWITCH / WHILE};
\draw[arr] (e)--node[above, font=\scriptsize]{input\_json}(w);
\draw[arr] (w)--node[right, font=\scriptsize]{result + output\_json}(e);
\draw[arr] (e)--node[left, font=\scriptsize]{output bindings}(s);
\draw[arr] (s)--(cf);
\draw[arr] (cf)--node[above, font=\scriptsize]{activate branch}(e);
""",
        "Worker-driven conditions: ACTION output updates scope, then control flow branches.",
    ),
    "methylvalidation-flow": _fig(
        r"""
\node[base] (root) {SEQUENCE root};
\node[base, below left=0.75cm and 0.2cm of root] (fe) {FOREACH iterations};
\node[base, below right=0.75cm and 0.2cm of root] (fin) {SEQUENCE final};
\node[base, below=0.55cm of fe] (fseq) {centroid $\rightarrow$ detector\\${var.taskConfig}};
\node[base, below=0.55cm of fin] (fpost) {mapper $\rightarrow$ enricher $\rightarrow$ progression};
\draw[arr] (root)--(fe); \draw[arr] (root)--(fin);
\draw[arr] (fe)--(fseq); \draw[arr] (fin)--(fpost);
""",
        "ValidationPipeline: FOREACH planner iterations then final post steps.",
    ),
    "data-driven-pipeline": _fig(
        r"""
\node[base] (root) {SEQUENCE root};
\node[base, below left=0.8cm and 0.15cm of root] (fecp) {FOREACH comparisons\\(parallel)};
\node[base, below right=0.8cm and 0.15cm of root] (post) {SEQUENCE post\_pipeline\\mapper, enricher, progression};
\node[base, below=0.55cm of fecp] (seqcmp) {SEQUENCE one\_comparison};
\node[base, below=0.55cm of seqcmp] (fechr) {FOREACH chromosomes\\(parallel)};
\node[base, below=0.55cm of fechr] (seqchr) {SEQUENCE one\_chromosome};
\node[base, below left=0.55cm and 0.1cm of seqchr] (par) {PARALLEL\\centroid\_g1, centroid\_g2};
\node[base, below right=0.55cm and 0.1cm of seqchr] (det) {ACTION detect};
\draw[arr] (root)--(fecp); \draw[arr] (root)--(post);
\draw[arr] (fecp)--(seqcmp); \draw[arr] (seqcmp)--(fechr);
\draw[arr] (fechr)--(seqchr); \draw[arr] (seqchr)--(par); \draw[arr] (seqchr)--(det);
""",
        "DataDrivenPipeline workflow tree (static nodes, data-driven fan-out).",
    ),
    "worker-protocol": _fig(
        r"""
\node[base, fill=purple!10] (w) {Worker node};
\node[base, fill=orange!12, right=1.1cm of w] (mt) {Middle-tier REST};
\node[base, fill=green!10, right=1.1cm of mt] (db) {Database (wf)};
\draw[arr] (w)--node[above, font=\scriptsize]{POST /tasks/request}(mt);
\draw[arr] (mt)--node[above, font=\scriptsize]{sp\_worker\_request\_task}(db);
\draw[arr] (db)--node[below, font=\scriptsize]{input\_json + lease}(mt);
\draw[arr] (mt)--node[below, font=\scriptsize]{has\_task}(w);
\draw[arr] (w)--node[above, font=\scriptsize]{POST /tasks/\{id\}/submit}(mt);
\draw[arr] (mt)--node[above, font=\scriptsize]{wf\_engine\_on\_action\_complete}(db);
""",
        "Worker poll / submit protocol via stateless middle-tier.",
    ),
    "cluster-storage": _fig(
        r"""
\node[base] (n1) {methyl-centroid\\worker};
\node[base, right=0.35cm of n1] (n2) {methyl-detector\\worker};
\node[base, right=0.35cm of n2] (n3) {methyl-mapper\\worker};
\node[base, fill=gray!12, below=1.1cm of n2, text width=3.4cm] (stor) {Shared /work mount\\centroids, detections, mapper outputs};
\node[base, fill=orange!12, above=1.0cm of n2] (mt) {Middle-tier REST};
\node[base, fill=green!10, left=1.3cm of mt] (db) {Database};
\draw[arr] (n1)--(stor); \draw[arr] (n2)--(stor); \draw[arr] (n3)--(stor);
\draw[arr] (n1)--(mt); \draw[arr] (n2)--(mt); \draw[arr] (n3)--(mt);
\draw[arr] (mt)--(db);
""",
        "Cluster workers share NFS/Azure Files storage; coordination via database only.",
    ),
}

FIGURE_ORDER = [
    "presentation-map",
    "sample-prep-pipeline",
    "cohort-hierarchy",
    "schema-tree",
    "action-schemas",
    "portal-editor",
    "domain-program-compile",
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
    # Plain ```mermaid (not `{mermaid}` cells): PDF-safe; HTML runs Mermaid via include-after-body script.
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

    n_mermaid = len(re.findall(r"```mermaid\n", text))
    if n_mermaid != len(FIGURE_ORDER):
        raise SystemExit(
            f"Mermaid block count ({n_mermaid}) != FIGURE_ORDER ({len(FIGURE_ORDER)}); update build_pipeline_architecture_qmd.py"
        )

    parts = re.split(r"```mermaid\n", text)
    out = [YAML + parts[0]]
    for i, chunk in enumerate(parts[1:], start=0):
        mermaid_body, rest = chunk.split("```\n", 1)
        fig_id = FIGURE_ORDER[i]
        out.append(wrap_mermaid(mermaid_body, fig_id))
        out.append(rest)

    rendering = """
## Rendering this document

Edit [`pipeline_architecture.md`](pipeline_architecture.md), regenerate the Quarto source, then render locally:

```bash
python workflow_engine/docs/build_pipeline_architecture_qmd.py

# HTML — use preview (recommended); Mermaid needs HTTP + JavaScript
quarto preview workflow_engine/docs/pipeline_architecture.qmd

# Or use the helper script from the repo root:
bash workflow_engine/docs/render-pipeline-architecture.sh preview

# PDF — vector TikZ figures (requires TeX / lualatex)
quarto render workflow_engine/docs/pipeline_architecture.qmd --to pdf
# bash workflow_engine/docs/render-pipeline-architecture.sh pdf
```

**HTML:** Open the URL that `quarto preview` prints (typically `http://localhost:…`) in your normal browser. Do **not** open `pipeline_architecture.html` directly from disk (`file://`) or in the IDE Markdown/HTML preview — Mermaid will not run and you will see raw diagram source (`erDiagram`, `flowchart`, etc.).

**PDF:** Uses TikZ figures (same approach as [`docs/MethylPipeline-overview.qmd`](../../docs/MethylPipeline-overview.qmd)). Install TeX if needed: `quarto install tinytex`.

"""
    body = "".join(out)
    if "## Rendering this document" not in body:
        body = body.rstrip() + "\n\n---\n" + rendering

    QMD.write_text(body, encoding="utf-8")
    print(f"Wrote {QMD} ({len(FIGURE_ORDER)} diagram pairs)")


if __name__ == "__main__":
    main()
