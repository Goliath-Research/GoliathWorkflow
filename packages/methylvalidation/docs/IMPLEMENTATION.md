# MethylValidation Implementation

**Related documentation:** [THEORY.md](THEORY.md), [Usage (Docker and venv)](USAGE.md), [MethylPredictor USAGE](../../methylpredictor/docs/USAGE.md), and the canonical theory book at [../../../docs/theory/README.md](../../../docs/theory/README.md).

This document describes how MethylValidation is implemented: it orchestrates stratified splits, per-iteration project generation, subprocess pipeline runs, and aggregation of MethylPredictor metrics and step timings.

## Configuration Philosophy: Single Source of Truth

Project configurations should follow a **single source of truth** principle:

- **Global level**: Define `controls`, `diseases`, `samples_base_path`, etc.
- **Step-specific sections**: Only override settings that are different for that step
- **Avoid duplication**: Do not repeat global data structures in step configs

### Example of Clean Structure:

```json
{
  "project_name": "Healthy_vs_PCa1-4-CG",
  "samples_base_path": "/work/prostate-cancer/samples",
  "controls": { ... },           // Define once
  "diseases": { ... },           // Define once
  "step_config": {
    "centroid": { ... },
    "detection": { ... },
    "predictor": {
      "debug": false,
      "panel": { ... }           // Only step-specific overrides
    },
    "validation": { ... }        // MC-specific settings
  }
}
```

### 1. Model Creation (Monte Carlo + Stability + Freeze)

- Run with `--stability` to evaluate many random splits
- Run with `--freeze` to create final production model
- Uses `step_config.validation` settings from the project

### 2. Model Use for Prediction (Predictor-only)

- Uses same splits as Model Creation but only runs predictor
- Evaluates the frozen production model

**Command examples:**
```bash
# Model Creation
methyl-validation --project configs/project_Healthy_vs_PCa1-4-CG.json --stability
methyl-validation --project configs/project_Healthy_vs_PCa1-4-CG.json --freeze

# Model Use for Prediction  
methyl-validation --project configs/project_Healthy_vs_PCa1-4-CG.json --predictor-only
```

---

## Architecture overview

MethylValidation orchestrates stratified splits, project generation, and pipeline execution via subprocess calls. It supports both workflows described above.

The main components are:

1. **Config & Layout**: Loads `MonteCarloConfig`, rejects blind predictors, and infers binary vs multiclass layout.
2. **Data Splitting**: `stratified_split*` functions create train/validation splits.
3. **Project Generation**: Creates per-run `project.json` files with appropriate sample paths.
4. **Pipeline Execution**: Uses `pipeline_runner.py` to run the appropriate steps.
5. **Aggregation**: Collects metrics and timings from all runs.

The `--freeze` path uses `run_pipeline_for_production()` which runs: centroid → detector(with `fixed_dmp_panel`) → mapper → enricher; when `step_config.progression.enabled=true`, it then runs `methyl-disease-progression`.

```mermaid
flowchart LR
  Config[MonteCarloConfig]
  Layout[infer_monte_carlo_layout]
  Split[stratified_split / stratified_split_multiclass]
  GenB[generate_run_project]
  GenM[generate_run_project_multiclass]
  RunB[run_pipeline_for_iteration]
  RunM[run_pipeline_for_iteration_multiclass]
  Freeze[freeze_production_model]
  ProdRun[run_pipeline_for_production]
  Centroid[methyl-centroid]
  Detector[methyl-detector\n(fixed_dmp_panel)]
  Classifier[methyl-classifier]
  Predictor[methyl-predictor]
  Metrics[validation_metrics.json]
  Aggregate[validator_metrics]

  Config --> Layout
  Layout --> Split
  Split --> GenB
  Split --> GenM
  GenB --> RunB
  GenM --> RunM
  RunB --> Centroid
  RunM --> Centroid
  Centroid --> Detector
  Detector --> Classifier
  Classifier --> Predictor
  Predictor --> Metrics
  Metrics --> Aggregate
  Config --> Freeze
  Freeze --> ProdRun
  ProdRun --> Centroid
  Centroid --> Detector
```

## MethylUtils usage

MethylValidation uses **MethylUtils** only for project loading:

- **load_project(base_project)** — To read `project_name` and project structure so that run directories are created under `output_base/project_name/monte_carlo_runs/run_0001`, etc.
- **load_project(project_path)** — Per run (binary), to resolve the predictor output directory from comparisons (`run_dir/predictors/<control>/<disease>`). Multiclass flat runs use `run_dir/predictors` directly.

Sample path resolution is done locally in MethylValidation ([split.py](../methyl_validation/split.py): `load_and_resolve_sample_paths`). Iteration metrics are produced by **MethylDetector** (balanced accuracy in `result*.json`) during the default MC loop, or by **MethylPredictor** when using **`--predictor-only`** or after **`--model`**; MethylValidation aggregates via `iteration_scalar_metrics_from_run_dir`.

## Modules

| Module | Role |
|--------|------|
| **config.py** | `MonteCarloConfig` — `cohorts` (preferred) or legacy `healthy_csv`/`disease_csv`, plus train_fraction, n_iterations, seed, base_project, output_base, path_remap, abort_on_step_failure. |
| **predictor_policy.py** | `assert_monte_carlo_predictor_allowed` — reject `predictor.blind` / `test_blind_paths` for MC. |
| **split.py** | `load_and_resolve_sample_paths`; `stratified_split` (binary); `stratified_split_multiclass` (per-label train/val). |
| **project_gen.py** | `infer_monte_carlo_layout` (rejects 2 cohorts when project resolves to >2 leaves); `generate_run_project` (binary CSV names unchanged); `generate_run_project_multiclass` / `generate_run_project_hierarchical_multiclass` (`training_<label>.csv`, `testing_<label>.csv`, `val_test_groups.json`). Each run’s `project.json` rewrites `step_config.predictor` to the holdout CSVs: **flat** MC also sets `test_group_paths`; **hierarchical** MC only updates nested `controls`/`diseases` (keeps template parent labels, e.g. `prostate_cancer` vs top-level `pca`). MethylPredictor zips predictor list expansion with resolved centroid labels when `test_group_paths` is absent. |
| **pipeline_runner.py** | `run_pipeline_for_iteration` / `run_pipeline_for_iteration_multiclass`: **methyl-centroid → methyl-detector** only. `run_pipeline_for_production`: freeze (centroid→detector→mapper→enricher) and optional `methyl-disease-progression` from `step_config.progression`. `run_pipeline_for_model`: classifier→predictor. `run_predictor_only_*`: predictor-only. |
| **validator_metrics.py** | `iteration_scalar_metrics_from_run_dir`: predictor `validation_metrics.json` if present, else mean detector `balanced_accuracy` from `detections/**/result*.json`. |

## Data flow (CLI)

1. Load config; `assert_monte_carlo_predictor_allowed`; `infer_monte_carlo_layout(base_project, len(cohorts))`.
2. Resolve `project_name`; create `output_base/project_name/monte_carlo_runs/`.
3. Resolve all cohort sample paths from CSVs.
4. For each iteration:
   - **Binary:** `stratified_split` → `generate_run_project` → `run_pipeline_for_iteration` (centroid group1/group2 overrides).
   - **Multiclass:** `stratified_split_multiclass` → `generate_run_project_multiclass` → `run_pipeline_for_iteration_multiclass` (centroid + detector only).
   - Read metrics via `iteration_scalar_metrics_from_run_dir(run_dir)` (predictor JSON if present, else detector `result*.json`).
5. Aggregate → `all_metrics.csv`, `metrics_summary.json`, `step_timings.csv`, optional `resource_summary.json`.

**MethylPredictor:** flat-group projects with **multiclass-classifier.pkl** resolve via `resolve_predictor_config` (shared `_build_multiclass_predictor_config`). The CLI applies `--test-groups` in both single-config and per-comparison multiclass runs (`_apply_test_groups_json_to_config`).

**After a frozen production build:** `--model` runs **methyl-classifier** then **methyl-predictor** (`run_pipeline_for_model`). **`--predictor-only`** still runs holdout **methyl-predictor** iterations using `frozen_project_path` (same stratified splits as MC); it expects predictor `validation_metrics.json` per run.

**Disease progression synthesis:** when `step_config.progression.enabled` is set, freeze invokes `methyl-disease-progression --project <production/project.json>` after enricher. The progression tool reads comparison outputs (`mapper/<control>/<disease>/all-gene_name-combined.csv`, `enricher/<control>/<disease>/enrichment_merged.csv`, optional `modules_ranked.csv`) and writes long tables + summary under `<project_root>/progression`.

## Output files

| File | Description |
|------|-------------|
| **all_metrics.csv** | One row per successful iteration: iteration, run_id, run_dir, accuracy, balanced_accuracy, sensitivity, specificity, macro_f1, etc. |
| **metrics_summary.json** | Per-metric empirical distribution: mean, std, min, max, count, percentiles (p5, p25, p50, p75, p95). |
| **step_timings.csv** | Per step per run: step_name, duration_seconds, return_code, run_id, run_dir, n_train_samples, n_val_samples. |
| **resource_summary.json** | (Optional) Mean/std duration per step, mean total time per iteration, min/max/mean n_train_samples and n_val_samples. |

For setup (Docker, venv), config reference, and how to use these outputs for metric distributions and processing/storage estimation, see [USAGE.md](USAGE.md).
