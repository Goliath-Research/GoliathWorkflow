---
name: stability detector parameter extraction
overview: Add minimal detector/filter parameter extraction from per-run `results-*.json` into stability outputs, so stable DMP decisions are traceable to the detection settings and funnel sizes used in each iteration.
todos:
  - id: extract-results-json-per-run
    content: Implement run-level loader/extractor for minimal fields from detections/**/results-*.json.
    status: pending
  - id: add-detector-parameters-to-summary
    content: Wire extracted detector parameter data into stability_summary.json as per_run + aggregates.
    status: pending
  - id: cover-with-tests
    content: Add/extend tests for extraction logic, summary integration, and missing-results fallback behavior.
    status: pending
  - id: document-summary-fields
    content: Update methylvalidation usage/implementation docs with new detector_parameters section in stability_summary.json.
    status: pending
  - id: verify-with-focused-runs
    content: Run focused tests and a short stability smoke check to confirm output schema and values.
    status: pending
isProject: false
---

# Stability Detector Parameter Extraction Plan

## Scope
Extend stability analysis to extract and summarize minimal detector parameters and funnel-size totals from `detections/**/results-*.json` for each Monte Carlo run, and include this in `stability_summary.json`.

## Implementation Steps

- Update stability data collection in [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py):
  - Add a helper to discover and load `results-*.json` files under each `run_*` detection subtree.
  - Extract the selected minimal fields per run/chromosome result:
    - `n_dmps_exported`
    - `total_statistical_dmps`
    - `total_biological_dmps`
    - `config.effect_size_coverage`
    - `config.delta_mean_reduction`
    - `config.classifier_dmp_selection`
    - `config.dynamic_dmp_cutoff_enabled`
  - Aggregate these per run (multi-chromosome safe):
    - keep config-like fields only when consistent across chromosomes in that run
    - summarize counts as mean/min/max across chromosome result files and include `n_result_files`.

- Extend `run_stability_analysis(...)` in [`/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py`](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/stability.py):
  - Compute detector-parameter extraction for all analyzed runs.
  - Add a new `detector_parameters` section to `stability_summary.json` only (no new CSV files), containing:
    - `per_run`: list of extracted run records
    - `aggregates`: compact summary stats over numeric fields and categorical value distributions.

- Keep stability behavior unchanged for DMP counting:
  - `dmp_frequency.csv` and `stable_dmps_production.csv` remain as-is.
  - Existing BA-based gating remains as-is.

- Add/adjust tests under [`/home/ubuntu/MethylPipeline/packages/methylvalidation/tests`](/home/ubuntu/MethylPipeline/packages/methylvalidation/tests):
  - New test for extraction from synthetic `results-*.json` trees (single and multi-chromosome cases).
  - New test that `run_stability_analysis` writes the new `detector_parameters` block in `stability_summary.json`.
  - Verify graceful handling when no results files exist for some runs.

- Update docs to describe the new summary content:
  - [`/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md`](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md)
  - [`/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/IMPLEMENTATION.md`](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/IMPLEMENTATION.md)

## Verification
- Run focused tests for `methylvalidation` stability modules.
- Execute a short MC stability smoke (1 iteration) and confirm `stability/stability_summary.json` includes:
  - `detector_parameters.per_run`
  - `detector_parameters.aggregates`
  - expected minimal extracted fields from detector `results-*.json`.