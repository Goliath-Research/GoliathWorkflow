# MethylValidation Usage Guide

## Overview

MethylValidation runs Monte Carlo validation: repeated stratified train/validation splits, full pipeline (MethylCentroid → MethylDetector → MethylClassifier → MethylPredictor) per iteration, and aggregation of validation metrics and step timings. It targets **multiclass** pipelines (flat **`groups`** template, **K ≥ 2** cohorts, **multiclass-classifier.pkl**) and still supports **legacy binary** runs (control/disease template, two cohorts). It provides the **empirical distribution** of quality metrics (balanced accuracy, sensitivity, specificity, F1, macro/weighted F1, etc.) and data to **estimate processing time and storage**. **Blind-only** predictor configs are rejected (use **methyl-predictor** alone for blind runs).

There are **two ways** to run MethylValidation:

1. **Docker container** — Run inside the MethylPipeline image; all CLIs (methyl-centroid, methyl-detector, methyl-classifier, methyl-predictor) must be on PATH in the container.
2. **Local host with virtual environment** — Create a venv, install the pipeline packages and MethylValidation, activate, and run on the host.

Use one or the other; the CLI is the same once the environment is set.

---

## Setup 1: Docker container

Use this when you want a single, reproducible environment.

**Prerequisites:** Docker; for GPU, NVIDIA Container Toolkit.

**1. Start the container**

From the MethylPipeline repo:

```bash
cd /path/to/MethylPipeline/docker
docker compose up -d
```

(Use the same container name as in your compose file; below assumes `methylpipeline` and repo mounted at `/workspace`.)

**2. Run MethylValidation**

Paths in your config must be valid **inside** the container (e.g. `/workspace/...`). From the host:

```bash
docker exec -w /workspace methylpipeline methyl-validation --config /workspace/path/to/monte_carlo_config.json
```

Override options (e.g. fewer iterations for a test run):

```bash
docker exec -w /workspace methylpipeline methyl-validation --config /workspace/config.json --iterations 5 --output-base /workspace/out
```

**Note:** The container must have `methyl-centroid`, `methyl-detector`, `methyl-classifier`, and `methyl-predictor` on PATH (they are typically installed in the same MethylPipeline image).

---

## Setup 2: Local host with virtual environment

Use this when you run on the host and want to activate a virtual environment.

**Prerequisites:** Python 3.10+. The pipeline CLIs must be available after installation.

**1. Create a virtual environment** (from the **MethylPipeline repository root**; canonical name is `.venv`)

```bash
cd /path/to/MethylPipeline
python3.12 -m venv .venv
```

**2. Activate the virtual environment**

```bash
source .venv/bin/activate
```

On Windows: `.venv\Scripts\activate`. After activation, the prompt usually shows `(.venv)`.

**3. Install dependencies**

MethylValidation depends on MethylUtils and MethylPredictor; the pipeline steps require MethylCentroid, MethylDetector, MethylClassifier, and MethylPredictor. Install in order:

```bash
cd /path/to/MethylPipeline
pip install -e packages/methylutils
pip install -e packages/methylcentroid
pip install -e packages/methyldetector
pip install -e packages/methylclassifier
pip install -e packages/methylpredictor
pip install -e packages/methylvalidation
```

**4. Run MethylValidation**

With the virtual environment **activated**:

```bash
methyl-validation --config monte_carlo_config.json
methyl-validation --config monte_carlo_config.json --iterations 20 --seed 42 --output-base ./my_runs
```

Paths in the config are on the **host**; you do not use the container.

---

## Config

Create a JSON config with the following fields:

| Field | Description |
|-------|-------------|
| `samples_base_path` | Base directory for resolving sample names from CSVs (same idea as project `samples_base_path`). |
| `cohorts` | **Preferred (multiclass):** ordered list `[{ "label": "<matches groups[i].label>", "csv": "<path>" }, ...]` with **K ≥ 2** entries. |
| `healthy_csv` / `disease_csv` | **Legacy (binary):** two CSVs for control and disease. If omitted, you must supply `cohorts` (at least two entries). |
| `train_fraction` | Fraction of samples used for training per cohort (e.g. `0.8`). |
| `n_iterations` | Number of Monte Carlo iterations (e.g. 50–200). |
| `seed` | Optional RNG seed for reproducibility. |
| `base_project` | Template project JSON. **Multiclass:** flat top-level `groups` (length **K**); must match `cohorts` count and label order. **Binary:** control/disease + comparisons (exactly **two** MC cohorts). |
| `output_base` | Root directory for all runs. Runs are created under `output_base/project_name/monte_carlo_runs/run_0001`, etc. |
| `path_remap` | Optional path remap dict (or reuse from base_project). |
| `abort_on_step_failure` | If `true`, abort all iterations when a pipeline step fails; if `false`, skip the iteration and continue. |

**Layout selection:** If `base_project` defines **`groups`** (length ≥ 2), the run uses the **multiclass** path (`infer_monte_carlo_layout`); `cohorts` length must equal `len(groups)`. If the project uses **nested disease `stages`** (and/or multiple control groups) so that **`get_resolved_groups()`** returns **K ≥ 3** leaves in a fixed order, the layout may be **`hierarchical_multiclass`**: each iteration patches **`controls.groups`** / **`diseases.groups`** with train/val CSVs per resolved leaf, keeps **stratified splits per cohort**, and runs the multiclass pipeline with **`per_cancer_group=true`**. `cohorts[].label` must match that resolved order. Otherwise the **binary** path is used when the template is control/disease only and the MC config defines exactly two cohorts (via `healthy_csv`/`disease_csv` or two `cohorts` entries).

The base template for multiclass must train a single **multiclass-classifier.pkl** under the project `classifiers/` directory (same contract as MethylPredictor). **Do not** set `step_config.predictor.blind` for MC configs — startup will error.

CSV format: single column or header `sample` / `path` / `sample_path` with sample folder names (resolved with `samples_base_path`).

**Example (legacy binary: healthy vs disease):**

```json
{
  "samples_base_path": "/data/samples",
  "healthy_csv": "configs/healthy.csv",
  "disease_csv": "configs/disease.csv",
  "train_fraction": 0.8,
  "n_iterations": 50,
  "seed": 42,
  "base_project": "configs/project_healthy_vs_disease.json",
  "output_base": "/work/monte_carlo_runs",
  "abort_on_step_failure": false
}
```

**Example (multiclass: three cohorts, labels must match `groups` in base_project):**

```json
{
  "samples_base_path": "/data/samples",
  "cohorts": [
    { "label": "healthy", "csv": "configs/healthy.csv" },
    { "label": "pca1", "csv": "configs/pca1.csv" },
    { "label": "pca2", "csv": "configs/pca2.csv" }
  ],
  "train_fraction": 0.8,
  "n_iterations": 20,
  "base_project": "configs/project_multiclass_flat_groups.json",
  "output_base": "/work/mc_out",
  "abort_on_step_failure": false
}
```

---

## Outputs

All outputs under **`output_base/project_name/monte_carlo_runs/`**:

| File or directory | Description |
|-------------------|-------------|
| **all_metrics.csv** | One row per successful iteration: `iteration`, `run_id`, `run_dir`, plus scalar metrics (accuracy, balanced_accuracy, sensitivity, specificity, macro_precision, macro_recall, macro_f1, weighted_f1, precision_binary, recall_binary, f1_binary, n_samples, n_classes). |
| **metrics_summary.json** | Per-metric empirical distribution: `mean`, `std`, `min`, `max`, `count`, and percentiles `p5`, `p25`, `p50`, `p75`, `p95`. This is the **probability distribution summary** of the quality metrics. |
| **step_timings.csv** | Per step per run: `step_name`, `duration_seconds`, `return_code`, `run_id`, `run_dir`, `n_train_samples`, `n_val_samples`. |
| **resource_summary.json** | (If generated) Mean and std of duration per step, mean total time per iteration, and min/max/mean of `n_train_samples` and `n_val_samples`. |
| **run_0001/**, **run_0002/**, ... | Per-iteration directory: `project.json`, train/val artifacts (binary: four CSVs; multiclass: `train_<label>.csv` + `val_test_groups.json`), pipeline outputs, `logs/`, per-run `step_timings.csv`. Multiclass predictor output: `run_*/predictors/validation_metrics.json`. |

---

## Quality metrics distribution

The **probability distribution** of the validation metrics (balanced accuracy, sensitivity, specificity, F1, etc.) is provided by:

- **metrics_summary.json** — For each metric, the summary gives the empirical distribution over iterations: mean, standard deviation, min, max, and percentiles (p5, p25, p50, p75, p95). With enough iterations, this approximates the sampling distribution of that metric under random train/val splits.
- **all_metrics.csv** — The raw sample (one row per iteration). Use it for custom analysis (e.g. histograms, other percentiles, correlation between metrics).

Metrics included (from MethylPredictor) include: **accuracy**, **balanced_accuracy**, **sensitivity**, **specificity**, **macro_precision**, **macro_recall**, **macro_f1**, **weighted_f1**, **precision_binary**, **recall_binary**, **f1_binary**, **n_samples**, **n_classes**. For definitions, see [MethylPredictor USAGE](../../methylpredictor/docs/USAGE.md#accuracy-metrics-reported).

---

## Estimating processing and storage

### Processing time

- **step_timings.csv** — Each row has `step_name`, `duration_seconds`, `n_train_samples`, `n_val_samples`. To estimate run time for a different total sample size **M** and **K** iterations:
  1. Compute mean (or median) `duration_seconds` per `step_name` (e.g. in Python or R).
  2. Optionally regress duration on `n_train_samples + n_val_samples` to scale to M (e.g. if duration is roughly linear in sample count, scale proportionally).
  3. Sum mean duration over the four steps to get mean time per iteration; multiply by K for total estimated time.
- **resource_summary.json** — If present, it provides mean duration per step and mean total time per iteration directly, plus the range of train/val sample sizes, so you can estimate without parsing step_timings.csv.

### Storage

Storage is **not** recorded automatically. To estimate:

1. Measure one run directory after a completed run, e.g.:
   ```bash
   du -s output_base/project_name/monte_carlo_runs/run_0001
   ```
2. Total storage ≈ (size per run) × number of iterations + size of `all_metrics.csv`, `metrics_summary.json`, and `step_timings.csv` (usually negligible).

---

## Troubleshooting

- **Missing CLIs:** MethylValidation calls `methyl-centroid`, `methyl-detector`, `methyl-classifier`, `methyl-predictor` via subprocess. If one is not found, the step fails. Ensure all are installed and on PATH (Docker: use the full image; venv: install all pipeline packages).
- **Path errors in Docker:** Paths in the config must be valid inside the container (e.g. `/workspace/...`). Mount the repo and data so container paths match.
- **Path errors on host:** With venv, paths are on the host; ensure `samples_base_path`, CSV paths, `base_project`, and `output_base` are correct.
- **abort_on_step_failure:** If `true`, the first pipeline failure stops everything. Set to `false` to skip failed iterations and continue (failed runs are not included in all_metrics.csv).
- **Too few samples for split:** Stratified split requires at least one train and one validation sample per cohort. If you have very few samples, increase sample count or reduce `train_fraction` carefully.
- **Blind predictor:** `methyl-validation` exits if `step_config.predictor` uses blind-only mode; remove `blind` from the base project for MC or use labeled holdouts.
- **Multiclass layout errors:** `groups` length must match `cohorts` length; labels must match in order. Binary templates require exactly two cohorts.

---

## Related documentation

- [MethylValidation Theoretical Foundation](MethylValidation_Theoretical_Foundation.md) — Goal, stratified split, empirical metric distribution, processing/storage.
- [METHYLVALIDATION_IMPLEMENTATION](METHYLVALIDATION_IMPLEMENTATION.md) — Modules, data flow, MethylUtils usage.
- [MethylPredictor USAGE](../../methylpredictor/docs/USAGE.md) — Metric definitions (BA, sensitivity, specificity, F1, etc.).
