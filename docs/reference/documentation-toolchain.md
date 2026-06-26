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
| **Reference** | Plain Markdown / optional Quarto | Lookup tables, schemas, language spec |

**Decision:** **Option A — Quarto + `@mermaid-js/mermaid-cli` pre-render** for theory and usage books. Plain Markdown for implementation and architecture pillars. **Retire dual TikZ maintenance** for workflow diagrams.

## Evaluation criteria (benchmark: theory ch.03 + three workflow diagrams)

| Criterion | Weight | Quarto + mmdc (A) | MyST + Sphinx (B) | MkDocs Material (C) | Dual TikZ (D, status quo) |
|-----------|--------|-------------------|-------------------|---------------------|---------------------------|
| Display math (HTML + PDF) | High | Excellent (LaTeX) | Excellent | Weak PDF | Excellent |
| Bibliography / `@citation` | High | Existing `references.bib` | Migration cost | Plugin-dependent | Existing |
| Equation cross-refs | High | `@eq-`, `@sec-` in place | Comparable | Limited | In place |
| Mermaid → PDF fidelity | High | Pre-rendered SVG via `mmdc` | Extension-dependent | Poor | TikZ duplicate (painful) |
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
docs/diagrams/out/*.svg     # committed pre-rendered assets
scripts/render_diagrams.sh  # mmdc wrapper (--check for CI)
```

| Output | Mechanism |
|--------|-----------|
| GitHub / plain `.md` | Fenced ` ```mermaid ` blocks (native GitHub) |
| Quarto HTML | Live Mermaid JS (Quarto 1.4+ or CDN hook) |
| Quarto PDF | `![caption](../diagrams/out/fig.svg)` or `\includegraphics` — **no inline TikZ for workflow figures** |
| Canvas | SDK DAG layout mirroring same topology; links to `.mmd` sources |
| Marp | Embed pre-rendered PNG/SVG from `out/` |

### Tooling

```bash
# Global install (preferred on dev machines)
npm install -g @mermaid-js/mermaid-cli

# Or one-shot via npx (used when mmdc not on PATH)
npx --yes @mermaid-js/mermaid-cli -i docs/diagrams/src/layer-model.mmd -o docs/diagrams/out/layer-model.svg

# Regenerate all shared diagrams
bash scripts/render_diagrams.sh

# CI freshness check
bash scripts/render_diagrams.sh --check
```

If Node/`mmdc` is unavailable (e.g. ARM hosts where Puppeteer/Chrome fails), run `render_diagrams.sh` on an x86_64 CI agent or dev machine and commit the resulting SVGs. **Placeholder SVGs** may be checked in temporarily; CI `--check` still verifies freshness when sources change. PDF builds must not depend on live Mermaid JS.

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
