# Documentation Toolchain Decision

**Date:** 2026-06-26  
**Status:** Adopted for MethylPipeline documentation IA revision

## Summary

| Pillar | Format | Build |
|--------|--------|-------|
| **Theory** | Quarto (`.qmd`) | `quarto render docs/theory` — math, bib, cross-refs |
| **Usage** | Quarto (`.qmd`) | `quarto render docs/usage` — operator runbooks |
| **Implementation** | Plain Markdown | GitHub-native; fenced Mermaid |
| **Architecture** | Plain Markdown | GitHub-native; pre-rendered SVG for PDF exports |
| **Cursor canvases** | `.canvas.tsx` in `docs/canvas/` | Interactive IDE hubs; sync via `scripts/sync_cursor_canvases.sh` |
| **Reference** | Plain Markdown / optional Quarto | Lookup tables, schemas, language spec |

**Decision:** **Option A — Quarto + `@mermaid-js/mermaid-cli` pre-render** for theory and usage books. Plain Markdown for implementation and architecture pillars. **Retire dual TikZ maintenance** for workflow diagrams.

**Validated 2026-07:** Theory book requires Quarto (LaTeX math, bibliography, cross-refs). Usage book reviewed — stays Quarto for multi-part PDF/HTML assembly despite no display math. CI smoke and doc freshness guards added in the docs refresh plan.

## Evaluation criteria (benchmark: theory ch.03 + three workflow diagrams)

| Criterion | Weight | Quarto + mmdc (A) | MyST + Sphinx (B) | MkDocs Material (C) | Dual TikZ (D, status quo) |
|-----------|--------|-------------------|-------------------|---------------------|---------------------------|
| Display math (HTML + PDF) | High | Excellent (LaTeX) | Excellent | Weak PDF | Excellent |
| Bibliography / `@citation` | High | Existing `references.bib` | Migration cost | Plugin-dependent | Existing |
| Equation cross-refs | High | `@eq-`, `@sec-` in place | Comparable | Limited | In place |
| Mermaid → PDF fidelity | High | Pre-rendered PNG (`htmlLabels: false` SVG + 2× PNG via `mmdc`) | Extension-dependent | Poor | TikZ duplicate (painful) |
| Mermaid → HTML / GitHub | High | Native + CDN | Good | Built-in | HTML only without TikZ |
| CI complexity | Medium | Quarto + TeX + Node for mmdc | Higher migration | Lower | Quarto + TeX + manual TikZ |
| Contributor friction | Medium | `.qmd` + one diagram source | New toolchain | Split from theory book | Two diagram languages |
| Canvas alignment | Medium | Shared `.mmd` sources | Same possible | Same possible | Divergent TikZ |

### Benchmark artifacts

1. **Math chapter:** `docs/theory/chapters/03-methyldetector.qmd` — KS tests, q-values, taxonomy labels, code traceability.
2. **Diagrams:** `docs/diagrams/src/layer-model.mmd`, `distributed-runtime.mmd`, `pipeline-stages.mmd`.

**Scoring:** Option A wins on math investment preservation, cross-ref continuity, and single diagram source. Option B would require full theory book migration with no proportional gain. Option C is unsuitable for publication-quality theory PDF. Option D is rejected — dual maintenance already blocks scale.

## Diagram pipeline

```
docs/diagrams/src/*.mmd     # canonical Mermaid source
docs/diagrams/out/*.svg     # committed pre-rendered assets (GitHub / HTML; native SVG text)
docs/diagrams/out/*.png     # committed pre-rendered assets (Quarto PDF — reliable label rasterization)
docs/diagrams/mermaid-config.json  # htmlLabels: false so SVG text survives non-HTML viewers
scripts/render_diagrams.sh  # mmdc wrapper (--check for CI)
```

| Output | Mechanism |
|--------|-----------|
| GitHub / plain `.md` | Fenced ` ```mermaid ` blocks (native GitHub) |
| Quarto HTML | `![caption](../diagrams/out/fig.png)` or `.svg` |
| Quarto PDF | `![caption](../diagrams/out/fig.png)` — **PNG embeds** (SVG can rasterize labels poorly in LuaLaTeX) |
| Canvas | SDK DAG layout mirroring same topology; links to `.mmd` sources |
| Marp | Embed pre-rendered PNG/SVG from `out/` |

### Tooling

Dependencies are pinned in [`docs/diagrams/package.json`](../diagrams/package.json). The render script installs them on first use (`npm ci` in that directory).

```bash
# One-time (or let render_diagrams.sh install automatically)
cd docs/diagrams && npm ci

# Regenerate all shared diagrams (uses system Chromium on ARM via PUPPETEER_EXECUTABLE_PATH)
bash scripts/render_diagrams.sh

# CI freshness check (missing, stale, or placeholder SVGs fail)
bash scripts/render_diagrams.sh --check
```

**ARM / aarch64 dev hosts:** `@mermaid-js/mermaid-cli` bundles Puppeteer; on ARM it may download the wrong Chrome arch when invoked via ephemeral `npx`. The repo pins a local install under `docs/diagrams/node_modules/` and `render_diagrams.sh` sets `PUPPETEER_EXECUTABLE_PATH` to system `chromium` / `chromium-browser` when unset. Install Chromium (`apt install chromium-browser`, or `/snap/bin/chromium`).

**CI:** PR pipeline installs `chromium-browser`, runs `npm ci` in `docs/diagrams/`, then `render_diagrams.sh --check`. Commit regenerated SVG **and** PNG whenever `.mmd` sources change. PDF builds must not depend on live Mermaid JS or SVG `foreignObject` labels.

### TikZ policy

TikZ remains allowed only for **non-flowchart** theory figures where Mermaid is a poor fit (dense mathematical diagrams). **Workflow and architecture diagrams must not use TikZ as a parallel source.**

## Quarto book configuration

- **Theory:** title `MethylPipeline Theory`; Parts I–II only (math + config semantics + workflow theory); no CLI runbook chapters.
- **Usage:** title `MethylPipeline Usage Manual`; renamed from `docs/usage/`; cross-links to theory and implementation.
- PDF header: remove `\usepackage{tikz}` from usage book where diagrams use pre-rendered assets.

## CI expectations

On docs changes:

1. `bash scripts/render_diagrams.sh --check`
2. `bash scripts/check_doc_links.sh`
3. `python scripts/check_windows_paths.py`
4. `quarto render docs/theory docs/usage --to html` (PDF optional on release)

## Related

- Diagram sources: [`../diagrams/src/`](../diagrams/src/)
- Architecture consolidation: [`../architecture/`](../architecture/)
- Audit registry: [`../DOCUMENTATION_AUDIT.md`](../DOCUMENTATION_AUDIT.md)
