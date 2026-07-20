---
name: HiTIMED theory docs
overview: Document Houseman and HiTIMED cell deconvolution in the architecture end-to-end workflow, add a Theory chapter for the math and analyte trees, and extend Theory workflow coverage with a per-analyte action inventory for cfDNA, buffy_coat, and tissue.

> **Status: IMPLEMENTED.** Documentation-only: end-to-end workflow section 5 now describes the `method: houseman | hitimed` switch and analyte trees; Theory adds [`docs/theory/chapters/07a-methyldeconv.qmd`](../theory/chapters/07a-methyldeconv.qmd) (`@sec-methyldeconv`) plus a post-freeze covariate stage and per-analyte action matrix in [`docs/theory/chapters/12-two-workflows.qmd`](../theory/chapters/12-two-workflows.qmd). Companion implementation plan: [`hitimed-hierarchical-deconvolution.plan.md`](hitimed-hierarchical-deconvolution.plan.md).

azure_devops:
  type: Feature
  title: "HiTIMED + analyte actions in Theory and end-to-end docs"
  work_item_id: null
  epic_id: 413
todos:
  - id: e2e-hitimed
    content: Update end-to-end-workflow.md section 5 for Houseman + HiTIMED method switch and analyte trees
    status: completed
    work_item_id: null
  - id: theory-deconv-chapter
    content: Add docs/theory/chapters/07a-methyldeconv.qmd and wire _quarto.yml / index / README
    status: completed
    work_item_id: null
  - id: theory-analyte-actions
    content: Expand ch.12 two-workflows with post-freeze covariates + per-analyte action matrix (cfdna, buffy_coat, tissue)
    status: completed
    work_item_id: null
  - id: limitations-analyte-sync
    content: Limitations caveat for external atlases; sync ANALYTE_PROFILES.md for tissue + cell_deconvolution
    status: completed
    work_item_id: null
  - id: promote-plan
    content: Promote plan to docs/plans/hitimed-theory-docs.plan.md and README mapping row
    status: completed
    work_item_id: null
---

# HiTIMED + analyte actions in Theory and e2e

## Goal

Bring documentation in line with the shipped `pipeline.cell_deconvolution` method switch (`houseman` | `hitimed`) and make Theory the place that explains both methods **and** which actions participate for each analyte (`cfdna`, `buffy_coat`, `tissue`).

No package/code changes; docs + Quarto book wiring only. The implementation is tracked separately in [`hitimed-hierarchical-deconvolution.plan.md`](hitimed-hierarchical-deconvolution.plan.md).

## 1. Architecture: end-to-end workflow

Updated [`docs/architecture/end-to-end-workflow.md`](../architecture/end-to-end-workflow.md) section 5:

- `pipeline.cell_deconvolution` is now described as method-selectable: `houseman` (flat IDOL 6-cell) vs `hitimed` (hierarchical, reuses `houseman_qp` per node).
- The section 5.1 diagram shows the method switch, and an analyte table maps `buffy_coat`/`cfdna`/`tissue` to their tree roots and leaf columns.
- Same CSV contract (`{output_base}/cell_fractions/cell_fractions.csv`), plus `cell_fractions.manifest.json` recording `method`/`analyte`/`tree_root`.
- Cross-links to the Theory chapter and [`hitimed-hierarchical-deconvolution.plan.md`](hitimed-hierarchical-deconvolution.plan.md).

## 2. Theory Part I: methyldeconv chapter

Added [`docs/theory/chapters/07a-methyldeconv.qmd`](../theory/chapters/07a-methyldeconv.qmd) (`@sec-methyldeconv`), after mapper and before enricher. Covers the Houseman constrained-projection QP, marker extraction, the HiTIMED path-product tree, analyte-driven roots, config knobs, and category/reference-basis caveats. Wired into [`_quarto.yml`](../theory/_quarto.yml), both package-map tables in [`index.qmd`](../theory/index.qmd), and [`README.md`](../theory/README.md). Added a reference-basis caveat and deprecation-snapshot row in [`10-limitations-and-open-questions.qmd`](../theory/chapters/10-limitations-and-open-questions.qmd).

## 3. Theory Part II: analyte action inventory

Expanded [`docs/theory/chapters/12-two-workflows.qmd`](../theory/chapters/12-two-workflows.qmd) with a post-freeze covariate stage (`@sec-post-freeze-covariates`) and a per-analyte action matrix (`@sec-analyte-actions`) covering `cfdna`, `buffy_coat`, and `tissue`, including the two caveats (no `tissue` analyte pack in `analyte_profiles.py`; flat Houseman is blood-oriented so tissue composition needs HiTIMED).

## 4. Supporting operator docs

Synced [`docs/ANALYTE_PROFILES.md`](../ANALYTE_PROFILES.md): added a `tissue` column, a `cell_deconvolution` row, and a note that the method switch / HiTIMED tree are set via profile `actionConfig.cell_deconvolution` (not the analyte profile merge).

## Out of scope

- Implementing a `tissue` entry in `analyte_profiles.py` or changing deconvolution code
- Provisioning/committing full cfDNA/tissue hierarchy basis JSONs
- Regenerating config schemas (unchanged)
