---
name: Per-Chromosome Selection Plan Update
overview: Update the per-chromosome stable DMP selection plan to include both combined and per-chromosome charts, with Y-axis showing DMP counts (not percentages) for both all candidates and final selected subsets.
todos: []
isProject: false
---

# Per-Chromosome Selection Plan Update

## Scope Update

In addition to per-chromosome selection and union-panel output, charting will now:

- generate **both** chart layouts:
  - one combined multi-series chart
  - one chart per chromosome
- use **Y-axis = DMP count** (absolute counts), not percent
- include **both populations**:
  - all DMPs per frequency
  - selected DMPs per frequency

## Plan Adjustments

- Update chart generation in `[/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py)`:
  - Build per-chromosome frequency distributions from candidate DMP table (all) and selected table.
  - Emit:
    - combined chart: e.g. `dmp_frequency_by_chromosome.html`
    - per-chromosome charts: e.g. `dmp_frequency_chr_<chrom>.html`
  - In each chart, include separate traces for `all` vs `selected` counts.
  - Keep elbow visualization aligned with selected method semantics (per chromosome).
- Update stability summary schema in `[/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py)`:
  - Add paths for combined chart and per-chromosome chart files.
  - Add per-chromosome count summaries for all-vs-selected so gene-mapping impact is explicit.
- Update tests in `[/home/ubuntu/MethylPipeline/packages/methylvalidation/tests](/home/ubuntu/MethylPipeline/packages/methylvalidation/tests)`:
  - Verify both chart types are created.
  - Verify Y-axis input data uses counts and includes both all/selected distributions.
  - Verify per-chromosome outputs remain consistent with final union selection.
- Update docs:
  - `[/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md)`
  - `[/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/IMPLEMENTATION.md](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/IMPLEMENTATION.md)`
  - Document chart file names, chart semantics, and count-based Y-axis interpretation.

## Verification

- Focused tests for stability selection + chart generation.
- Synthetic smoke run confirming:
  - combined multi-series chart exists
  - per-chromosome chart files exist
  - counts for all/selected are represented and consistent with selection outputs.

