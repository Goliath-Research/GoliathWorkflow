# Documentation Toolchain Decision

**Date:** 2026-08-10 (supersedes 2026-06-26 Quarto decision)  
**Status:** Adopted — Markdown-first MkDocs Material

## Summary

| Pillar | Format | Build |
|--------|--------|-------|
| **All site docs** | Plain Markdown (`.md`) | `mkdocs build` → portable `site/` |
| **Theory math** | `$…$` / `$$…$$` + MathJax | Rendered in the **MkDocs site**; PDF via Playwright print |
| **Diagrams** | Fenced ` ```mermaid ` (dynamic JS) | Native in Material; GitHub-native too |
| **PDF** | Playwright print of built HTML (HTTP + Mermaid flattened out of closed shadow DOM, scale-to-fit ≤ ~½ page) | `make docs-pdf` → `site-pdf/MethylPipeline-Documentation.pdf` |
| **Static diagram PNGs** (optional) | `docs/diagrams/src/*.mmd` → `docs/diagrams/out/*` via `scripts/render_diagrams.sh` | Marp / offline only — not preferred for the MkDocs PDF path |
| **Customer pack** | Nav subset | `mkdocs build -f mkdocs.customer.yml` |
| **Cursor canvases** | `.canvas.tsx` in `docs/canvas/` | IDE hubs; site links to [`canvas/README.md`](../canvas/README.md) (sync + open in Cursor) |
| **Marp decks** | `docs/presentations/` | Optional pre-rendered PNG from `docs/diagrams/out/` |

**Decision:** Prefer **plain Markdown + Mermaid + MathJax** over Quarto books. This is a **quality-preserving** replacement, not a simplification:

| Quarto capability | Markdown-first equivalent |
|-------------------|---------------------------|
| LaTeX math (`$…$` / `$$…$$`, numbered eqs) | Same delimiters via **MathJax** (`pymdownx.arithmatex`); stable anchors with `<div id="eq-…">` |
| Mermaid diagrams in HTML | Fenced ` ```mermaid ` (Material + GitHub render the same source) |
| Mermaid in PDF | **Playwright** prints the live HTML after flattening Mermaid out of closed shadow DOM (`scripts/render_docs_pdf.py`) — vector-quality diagrams, not PNG embeds |
| Callouts | MkDocs admonitions (`!!! warning` / `!!! note`) |
| Section IDs `{#sec-…}` | Python-Markdown `attr_list` (already enabled) |

Quarto was kept previously only for theory equations; that forced Mermaid pre-render (SVG/PNG) for PDF. MkDocs Material restores **dynamic Mermaid** while keeping the original LaTeX.

**Preview caveat:** Cursor / VS Code Markdown preview does **not** load MathJax or Mermaid from `mkdocs.yml`. Raw `$…$` there is expected. Use `make docs-serve` (or `mkdocs serve`) to see typeset equations.

## Why this replaces Quarto Option A

| Criterion | MkDocs Material (current) | Quarto books (retired) |
|-----------|---------------------------|------------------------|
| Display math (HTML) | MathJax / KaTeX | Excellent |
| Mermaid in HTML | Native, dynamic | Often pre-rendered for PDF parity |
| Mermaid in PDF | Playwright prints the live HTML page | Required `mmdc` PNG embeds |
| Single corpus | One `.md` tree + one nav | Split books + plain-MD pillars |
| Portable website | `site/` on any static host | Per-book `_book/` |
| Contributor friction | Markdown everyone already writes | `.qmd` + Quarto + TeX |

## Equations without Quarto

The fence is **authoring syntax** (raw on purpose). The paragraph after it is the **live MathJax render** — only in the MkDocs site, not in the IDE preview.

````markdown
Inline: threshold $\alpha$.

Block with anchor:

<div id="eq-effect-size" markdown="1">

$$
e_i = |\Delta\mu_i| \cdot w_i
$$

</div>
````

**Live render (MkDocs + MathJax):**

Inline: threshold $\alpha$.

<div id="eq-effect-size" markdown="1">

$$
e_i = |\Delta\mu_i| \cdot w_i
$$

</div>

Cross-page: [Eq. centroid-moments](../theory/chapters/01-methylutils.md#eq-centroid-moments) (theory chapter, also MathJax).

## Diagram pipeline

| Output | Mechanism |
|--------|-----------|
| MkDocs HTML | Fenced Mermaid (JS) |
| GitHub | Fenced Mermaid |
| PDF | Playwright snapshot of HTML (Mermaid already drawn) |
| Marp / offline | Optional `docs/diagrams/src/*.mmd` → `out/*` via `scripts/render_diagrams.sh` |

Workflow diagrams must not use TikZ as a parallel source.

## Local and hosted site

```bash
source .venv/bin/activate
pip install -r docs-requirements.txt
mkdocs serve                 # dynamic local preview — MathJax + Mermaid
mkdocs build --strict        # writes ./site/
mkdocs build -f mkdocs.customer.yml
```

Copy or sync `site/` to GitHub Pages, Azure Static Web Apps, Blob static website, or an internal `/work` share. No special runtime beyond a static file server.

## CI expectations

On docs changes:

1. `mkdocs build --strict`
2. `bash scripts/check_doc_links.sh`
3. `bash scripts/check_doc_freshness.sh`
4. `python scripts/check_windows_paths.py`
5. Optional: `bash scripts/render_diagrams.sh --check` when shared Marp diagram sources change
6. Release: `bash scripts/build_docs_pdf.sh` (Playwright HTML→PDF; Mermaid scale-to-fit in `scripts/render_docs_pdf.py`)

## Related

- Contributor guide: [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
- Diagram sources: [`../diagrams/src/`](../diagrams/src/)
- Audit registry: [`../DOCUMENTATION_AUDIT.md`](../DOCUMENTATION_AUDIT.md)
- Alignment engines: [`../usage/alignment-engines.md`](../usage/alignment-engines.md)
