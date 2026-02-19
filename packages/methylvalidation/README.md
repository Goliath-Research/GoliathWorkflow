# MethylValidation

Monte Carlo validation runner for MethylPipeline. Performs repeated stratified train/validation splits, runs the pipeline (MethylCentroid → MethylDetector → MethylClassifier → MethylValidator) per iteration with the training set, validates on the holdout set, and aggregates MethylValidator metrics into empirical distributions.

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

- `output_base/run_0001/`, `run_0002/`, ... — per-iteration project, train/val CSVs, and pipeline outputs (centroid, detection, classifier, validator).
- `output_base/all_metrics.csv` — one row per successful iteration with all scalar metrics.
- `output_base/metrics_summary.json` — empirical distribution summary (mean, std, min, max, percentiles) per metric.

## Dependencies

Requires the MethylPipeline CLI tools to be installed and on `PATH`: `methyl-centroid`, `methyl-detector`, `methyl-classifier`, `methyl-validator`.
