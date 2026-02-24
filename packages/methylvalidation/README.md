# MethylValidation

Monte Carlo validation runner for MethylPipeline. Performs repeated stratified train/validation splits, runs the pipeline (MethylCentroid → MethylDetector → MethylClassifier → MethylPredictor) per iteration with the training set, validates on the holdout set, and aggregates validation metrics into **empirical distributions** (balanced accuracy, sensitivity, specificity, F1, etc.). It also records step timings (duration, n_train/n_val samples) so you can **estimate processing time and storage** for a given number of samples and iterations.

## Documentation

- **[Usage Guide (Docker and venv)](docs/USAGE.md)** — Setup, config, outputs, quality metrics distribution, and estimating processing and storage.
- [Theoretical Foundation](docs/MethylValidation_Theoretical_Foundation.md) — Goal, stratified split, empirical metric distribution.
- [Implementation](docs/METHYLVALIDATION_IMPLEMENTATION.md) — Modules, data flow, MethylUtils usage.

## Config

Create a JSON config with:

| Field | Description |
|-------|-------------|
| `samples_base_path` | Base directory for resolving sample names from CSVs. |
| `healthy_csv` | Path to CSV listing healthy samples (one column, e.g. `sample`). |
| `disease_csv` | Path to CSV listing diseased samples (same format). |
| `train_fraction` | Fraction of samples used for training (e.g. `0.8`); same fraction for both classes. |
| `n_iterations` | Number of Monte Carlo iterations (e.g. 50–200). |
| `seed` | Optional RNG seed for reproducibility. |
| `base_project` | Path to an existing project JSON used as template. |
| `output_base` | Root directory for all runs (e.g. `./monte_carlo_runs`). |
| `path_remap` | Optional path remap dict (or reuse from base_project). |
| `abort_on_step_failure` | If true, abort when a pipeline step fails; otherwise skip the iteration. |

CSV format: same as the rest of the pipeline — single column or header `sample` / `path` with sample folder names (resolved with `samples_base_path`).

## Usage

```bash
methyl-validation --config monte_carlo_config.json
methyl-validation --config monte_carlo_config.json --iterations 20 --seed 42 --output-base ./my_runs
```

## Outputs

Outputs are under `output_base/project_name/monte_carlo_runs/`:

- `run_0001/`, `run_0002/`, ... — per-iteration project, train/val CSVs, and pipeline outputs (centroid, detection, classifier, predictor).
- `all_metrics.csv` — one row per successful iteration with all scalar metrics.
- `metrics_summary.json` — empirical distribution (mean, std, min, max, percentiles) per metric — the **probability distribution** of BA, sensitivity, specificity, F1, etc.
- `step_timings.csv` — per step per run: duration, n_train_samples, n_val_samples (for processing estimation).
- `resource_summary.json` — (if generated) mean duration per step and per iteration for quick run-time estimation.

## Dependencies

Requires the MethylPipeline CLI tools to be installed and on `PATH`: `methyl-centroid`, `methyl-detector`, `methyl-classifier`, `methyl-predictor`.
