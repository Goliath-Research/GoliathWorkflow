---
name: per-chromosome stable dmp selection
overview: Refactor stability panel construction to select DMPs per chromosome (then union), using detector effect-size-based ranking with a single global selection method/parameters in validation config.
todos:
  - id: extend-dmp-aggregation-with-effect-size
    content: Store per-DMP effect-size aggregates alongside frequency/count in stability computation.
    status: pending
  - id: implement-per-chromosome-selector
    content: Add chromosome-grouped selection engine with top_percentage, above_elbow, and stabilization_rate methods.
    status: pending
  - id: add-global-selection-config
    content: Introduce validation config fields for stability selection method and parameters with backward-compatible defaults.
    status: pending
  - id: wire-cli-and-summary
    content: Pass new config through CLI into run_stability_analysis and include method/per-chrom stats in stability_summary.json.
    status: pending
  - id: add-tests-and-docs
    content: Create synthetic tests for method behavior and union output, then update usage/implementation docs.
    status: pending
isProject: false
---

# Per-Chromosome Stable DMP Selection Plan

## Goal
Replace current pooled/global stable DMP trimming with **per-chromosome selection**. Each chromosome gets its own selected subset, and the final panel is the union across chromosomes.

## Targeted Design
- Selection scope changes from global table-wide to chromosome-local.
- Ranking uses detector **effect_size** (from discovery exports), not only frequency/count.
- One global selection method for all chromosomes, configured in validation settings.

## Implementation Steps

- Update stability data model and aggregation in [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py):
  - Extend DMP stability computation to retain per-DMP effect-size aggregates across runs (e.g., mean/max effect_size) while still computing frequency/count.
  - Add a chromosome-aware selector that groups by `chromosome` and applies one chosen method per group.
  - Produce final selected panel as union of selected rows from each chromosome.

- Implement three per-chromosome selection methods in [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py):
  - `top_percentage`: keep top X% by effect-size ranking per chromosome.
  - `above_elbow`: detect elbow on per-chromosome effect-size curve and keep rows above threshold.
  - `stabilization_rate`: keep most important rows until marginal improvement/importance rate drops below configured limit.

- Add global selection config fields in [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/config.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/config.py):
  - `stability_selection_method` (enum: `top_percentage`, `above_elbow`, `stabilization_rate`).
  - Method-specific parameters (e.g., `stability_top_percentage`, `stability_stabilization_rate_limit`, optional minimum per chromosome).
  - Keep backward compatibility: if unset, preserve current behavior via sensible default mapping.

- Wire config through CLI flow in [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/cli.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/cli.py):
  - Pass new selection method/params into `run_stability_analysis(...)`.
  - Ensure existing `stability_dmp_freq` filtering remains available and compatible.

- Update outputs and reporting in [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py):
  - Keep `stable_dmps_production.csv` as final union panel.
  - Add summary metadata in `stability_summary.json` for:
    - selected method + parameters
    - per-chromosome selected counts
    - total union size.
  - Optionally write a helper table (e.g., per-chromosome selection stats) if useful for traceability.

- Add/extend tests under [`/home/ubuntu/MethylPipeline/packages/methylvalidation/tests`](/home/ubuntu/MethylPipeline/packages/methylvalidation/tests):
  - Verify per-chromosome selection behavior (not pooled).
  - Verify each method selects expected rows on synthetic data.
  - Verify final union panel composition and backward compatibility path.

- Update docs:
  - [`/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md`](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md)
  - [`/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/IMPLEMENTATION.md`](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/IMPLEMENTATION.md)
  - Document method semantics, parameters, and examples.

## Verification
- Focused pytest for stability/config/CLI wiring in `packages/methylvalidation/tests`.
- Short 1-iteration smoke and multi-iteration synthetic smoke to confirm:
  - per-chromosome selection is applied,
  - final panel is chromosome-union,
  - summary reports method and per-chromosome counts.