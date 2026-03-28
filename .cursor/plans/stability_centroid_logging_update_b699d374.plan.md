---
name: stability centroid logging update
overview: Update Monte Carlo stability execution so each centroid group run is logged/timed independently, and centroid timing rows report actual processed samples from centroid outputs. Also suppress the optional missing-BA warning in MethylValidation.
todos:
  - id: split-centroid-steps
    content: Refactor stability pipeline runner to execute/log/time centroid group1 and group2 as separate tracked steps.
    status: completed
  - id: derive-processed-sample-count
    content: Add centroid output inspection to populate per-centroid-step n_processed_samples from metadata samples_used length.
    status: completed
  - id: wire-aggregation-and-warning-policy
    content: Update CLI timing aggregation and suppress optional missing-BA warning output while preserving metric collection.
    status: completed
  - id: schema-and-summary-compat
    content: Ensure validator metrics CSV/resource summary supports new n_processed_samples field without regressions.
    status: completed
  - id: docs-and-smoke-verify
    content: Update methylvalidation docs and run a short smoke validation to confirm logs/timings/fields behavior.
    status: completed
isProject: false
---

# Stability Logging and Timing Update Plan

## Scope

Implement the new stability-mode behavior in MethylValidation so each iteration treats control and disease centroid builds as two distinct tracked executions, with per-execution logs and timing rows that include true processed sample counts.

## Targeted Changes

- Update pipeline orchestration in `[/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/pipeline_runner.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/pipeline_runner.py)`:
  - Split centroid execution into two explicit sub-steps (`group1`, `group2`) instead of one combined timing/log entry.
  - Emit two log files per iteration for centroid runs (one per group).
  - Return two timing rows for centroid runs, each with its own duration.
  - Add centroid artifact inspection to compute `n_processed_samples` from centroid metadata (`samples_used` length), so timing rows reflect actual loaded samples rather than requested split size.
- Update MC aggregation in `[/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/cli.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/cli.py)`:
  - Preserve per-step timing rows from pipeline runner (including centroid group rows) and carry forward run metadata.
  - Stop emitting the current missing-BA warning for iterations with no scalar BA payload (keep iteration recording behavior unchanged).
- Extend timing/resource schema handling in `[/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/validator_metrics.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/validator_metrics.py)`:
  - Ensure `write_step_timings_csv` and resource summarization gracefully include/propagate `n_processed_samples` (without breaking existing `n_train_samples` / `n_val_samples` outputs).
- Update docs to match new outputs:
  - `[/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/USAGE.md)`
  - `[/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/IMPLEMENTATION.md](/home/ubuntu/MethylPipeline/packages/methylvalidation/docs/IMPLEMENTATION.md)`
  - Document that centroid now produces per-group logs/timings and that processed sample counts come from centroid outputs (`samples_used`) rather than requested split counts.

## Verification

- Run focused tests/lint for `methylvalidation` modules changed.
- Execute a short Monte Carlo smoke run (e.g., 1 iteration) and verify:
  - Two centroid log files exist per run.
  - `step_timings.csv` contains two centroid rows per run with durations.
  - Centroid rows include `n_processed_samples` derived from produced centroid files.
  - Missing BA warning no longer appears, while run aggregation still completes.

