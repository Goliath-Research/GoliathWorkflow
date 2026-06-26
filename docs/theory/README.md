# MethylPipeline Theory Book

This directory contains the canonical mathematical and statistical reference for MethylPipeline.

The source of truth is the code. This book is written from the implemented behavior of the packages under `packages/`, not from older design notes or aspirational API narratives. When the code and the older markdown docs disagree, the code wins.

## What This Book Covers

- shared notation and data structures,
- the ECDF-centered centroid, detector, classifier, predictor, and validation stack,
- downstream packages such as mapping, enrichment, and alignment QC,
- explicit caveats for approximations, heuristics, legacy remnants, and external-service-backed steps.

## Build Requirements

### HTML

- Install [Quarto](https://quarto.org/docs/download/).

### PDF

- Install Quarto.
- Install a TeX engine. The simplest supported path is:

```bash
quarto install tinytex
```

Quarto can also render with an existing TeX installation such as TeX Live or MiKTeX.

## Build Commands

From the repository root on Linux or macOS:

```bash
quarto preview docs/theory
quarto render docs/theory --to html
quarto render docs/theory --to pdf
```

From PowerShell on Windows 11:

```powershell
quarto preview .\docs\theory
quarto render .\docs\theory --to html
quarto render .\docs\theory --to pdf
```

To render both formats in one pass:

```bash
quarto render docs/theory
```

Rendered output is written to `docs/theory/_book/`.

## Authoring Rules

- Treat `packages/*` code as canonical.
- Prefer primary references in `references.bib`.
- Use `[@citation-key]` for citations and `@eq-...`, `@tbl-...`, `@sec-...` for cross-references.
- Do not upgrade heuristics into theory. Label them explicitly.
- If a method depends on an external service or stored procedure, document the dependency and the reproducibility limits.

## Relationship To Package Docs

The Quarto book is the canonical theory reference. Package-local `docs/THEORY.md` files should stay concise and point back to the corresponding Quarto chapter instead of becoming competing sources.

For workflow-first operations, command runbooks, and stage checklists, use the separate user manual at `docs/usage/`.

## Migration Note: Clustering Docs Retirement

`MethylCluster` is no longer part of the active MethylPipeline workflow documentation and has been removed from this book.

For the practical interpretation layer that previously mixed with clustering narratives, use:

- `chapters/12-two-workflows.qmd` for stage-level pipeline operations (`--stability`, `--freeze`, `--model`),
- `chapters/07-methylmapper.qmd` for DMP-to-gene aggregation and scoring,
- `chapters/08-methylenricher.qmd` for pathway/module interpretation.
