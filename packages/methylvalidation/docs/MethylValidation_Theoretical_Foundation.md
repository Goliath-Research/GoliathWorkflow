# MethylValidation Theoretical Foundation

**Related documentation:** [METHYLVALIDATION_IMPLEMENTATION](METHYLVALIDATION_IMPLEMENTATION.md), [USAGE](USAGE.md), [MethylPredictor Theoretical Foundation](../../methylpredictor/docs/MethylPredictor_Theoretical_Foundation.md).

## Goal

MethylValidation estimates the **sampling distribution** of validation metrics (balanced accuracy, sensitivity, specificity, F1, etc.) by running the full MethylPipeline many times with different stratified train/validation splits (Monte Carlo). The current implementation is **binary-only** (one control cohort and one disease cohort per run). It does not define a new probabilistic model for the metrics themselves; those are standard classification metrics computed by **MethylPredictor** (see [MethylPredictor documentation](../../methylpredictor/docs/MethylPredictor_Theoretical_Foundation.md)). The "distribution" MethylValidation provides is the **empirical distribution** over iterations: with enough iterations, the summary (mean, std, percentiles) approximates the sampling distribution of each metric.

## Stratified train/validation split

For two groups — **control** (e.g. healthy) and **disease** — MethylValidation splits each group independently using the same **train_fraction** (e.g. 0.8). The training set is used for MethylCentroid → MethylDetector → MethylClassifier; the validation set is held out and used only by **methyl-predictor**. This ensures:

- Both train and validation contain both classes (stratified).
- Each iteration gets a different random split (with optional fixed seed for reproducibility).
- Validation metrics are computed on unseen samples, so they reflect generalization.

## Per iteration

1. **Split**: Stratified split of control and disease samples into train and validation.
2. **Project**: Generate a run-specific project JSON and train/val CSVs (train samples only for pipeline; val samples only for predictor).
3. **Pipeline**: Run methyl-centroid → methyl-detector → methyl-classifier (on train data).
4. **Validation**: Run methyl-predictor with the validation set (control and disease holdout).
5. **Collect**: Read `validation_metrics.json` from the predictor output; record scalar metrics (accuracy, balanced_accuracy, sensitivity, specificity, F1, etc.) and step timings (duration per step, n_train_samples, n_val_samples).

After **N** iterations, all collected metrics are aggregated into:

- **all_metrics.csv** — one row per successful iteration (raw sample of the metric values).
- **metrics_summary.json** — per-metric empirical distribution: mean, std, min, max, count, and percentiles (p5, p25, p50, p75, p95). This is the **probability distribution summary** of the quality metrics.

With a sufficiently large N, the summary describes the approximate sampling distribution of each metric (e.g. "balanced accuracy under random train/val splits").

## Processing and storage

- **Step timings**: Each run records `duration_seconds` per pipeline step and `n_train_samples`, `n_val_samples`. These allow extrapolation: e.g. mean time per step and scaling by sample size to estimate "time for M total samples and K iterations." An optional **resource_summary.json** summarizes mean duration per step and mean total time per iteration for quick estimation.
- **Storage**: Total storage is approximately (size of one run directory) × number of iterations, plus the small aggregate files (all_metrics.csv, metrics_summary.json). Storage per run can be measured once (e.g. `du -s run_0001`) and multiplied by N; or recorded per iteration if the runner is extended to do so.

## Summary

| Aspect | Role |
|--------|------|
| **Inputs** | Sample lists (healthy_csv, disease_csv), train_fraction, n_iterations, base_project, output_base |
| **Outputs** | all_metrics.csv (raw metrics per iteration), metrics_summary.json (empirical distribution per metric), step_timings.csv (and optional resource_summary.json) |
| **Metric distribution** | metrics_summary.json + all_metrics.csv — empirical distribution of BA, sensitivity, specificity, F1, etc. |
| **Processing estimation** | step_timings.csv (and resource_summary.json) — duration per step, n_train/n_val; scale to other sample counts and iterations |
| **Storage estimation** | Measure one run directory; total ≈ (size per run) × n_iterations |

For implementation details (split, project generation, pipeline runner, aggregation), see [METHYLVALIDATION_IMPLEMENTATION.md](METHYLVALIDATION_IMPLEMENTATION.md). For setup and usage (Docker, venv, config, interpreting outputs), see [USAGE.md](USAGE.md).
