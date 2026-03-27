# MethylValidation Usage Guide

## Overview

MethylValidation orchestrates repeated train/validation splits, **methyl-centroid + methyl-detector** per iteration, aggregation of **detector** (or **predictor** when using `--predictor-only`) metrics, then optional **--freeze** (mapper/enricher) and **--model** (classifier→predictor). It supports two primary workflows:

1. **Model Creation** (`--stability` + `--freeze` + `--model`) — Identify stable DMPs across many random splits, extract pathways, and then build a final production model on all data.
2. **Model Use for Prediction** (`--predictor-only`) — Evaluate a frozen production model on random holdouts without retraining.

Both workflows are controlled by the project configuration file. See the full Quarto documentation at `docs/theory/` for theoretical background and the complete configuration reference.

---

## Two Workflows

### Workflow 1: Model Creation

**Purpose:** Build a robust, production-ready classifier by identifying consistently recurring DMPs across random data partitions.

**Steps:**

```bash
# Step 1: Monte Carlo + stability (n_iterations: centroid + detector per split)
methyl-validation --project configs/my_project.json --stability

# Step 2: Production freeze (full pipeline on all data up to mapper/enricher)
methyl-validation --project configs/my_project.json --freeze

# Step 3: Production model (after reviewing pathways, train the classifier and validate)
methyl-validation --project configs/my_project.json --model
```

**Why this workflow?**

- Monte Carlo splits refit centroids and detection on training fractions; **balanced_accuracy** in `all_metrics.csv` comes from **MethylDetector** validation (mean over `result*.json`) unless you use **`--predictor-only`** with a frozen model.
- Stability analysis identifies DMPs that recur in ≥ `stability_dmp_freq` fraction of runs.
- The freeze step prepares the final data using only the stable positions (`fixed_dmp_panel`), bypassing re-discovery, and extracting the valid pathway families (genes).
- The model step builds the final model from the verified DMPs and predicts on the test set.

**Output:** `monte_carlo_runs/production/classifiers/multiclass-classifier.pkl` is the final production model (created after `--model`).

### Workflow 2: Model Use for Prediction

**Purpose:** Measure the performance distribution of the frozen production model on held-out samples.

**Prerequisites:** Workflow 1 must have been completed (`production/project.json` must exist).

```bash
methyl-validation --project configs/my_project.json --predictor-only
```

**Why this workflow?**

- Much faster (only `methyl-predictor` runs per iteration).
- Provides the empirical distribution of the frozen model's balanced accuracy.
- Uses the same stratified splitting logic as Workflow 1 for consistency.

---

## CLI Flags

| Flag | Description |
|------|-------------|
| `--project PATH` | Path to the project JSON (preferred; reads `step_config.validation` from the project). |
| `--config PATH` | Path to a standalone Monte Carlo config JSON (alternative to `--project`). |
| `--stability` | Run stability analysis after the MC loop (Workflow 1, Step 1). |
| `--freeze` | Run production freeze using the stable DMP panel, up to enricher (Workflow 1, Step 2). |
| `--model` | Run production model builder after freeze (Workflow 1, Step 3). |
| `--predictor-only` | Run only `methyl-predictor` per iteration using the frozen model (Workflow 2). |
| `--skip-enricher` | Skip the enricher inside MC iterations even when `run_mapper_and_enricher: true`. |
| `--iterations N` | Override `n_iterations` from config. |
| `--seed S` | Override `seed` from config. |
| `--output-base DIR` | Override `output_base` from config. |

---

## Setup

### Option 1: Virtual environment (recommended for development)

```bash
cd /path/to/MethylPipeline
source .venv/bin/activate
methyl-validation --project configs/my_project.json --stability
```

### Option 2: Docker container

```bash
cd /path/to/MethylPipeline/docker
docker compose up -d
docker exec -w /workspace methylpipeline \
  methyl-validation --project /workspace/configs/my_project.json --stability
```

Paths in the config must be valid **inside** the container.

---

## Project Config: `step_config.validation`

Rather than a separate Monte Carlo config file, embed the validation settings directly in the project file. Only MC-specific fields are needed here; `samples_base_path`, `output_base`, and the cohort structure are inherited from the top-level project fields.

```json
"step_config": {
  "validation": {
    "train_fraction": 0.8,
    "n_iterations": 50,
    "seed": 42,
    "run_stability": true,
    "stability_dmp_freq": 0.7,
    "stability_min_balanced_accuracy": null,
    "abort_on_step_failure": false
  }
}
```

All `step_config.validation` fields are documented in the configuration reference (see `docs/theory/chapters/13-configuration-reference.qmd` or the Quarto book at `docs/theory/`).

---

## Outputs

All outputs are under `output_base/project_name/monte_carlo_runs/`:

| File / Directory | Description |
|-----------------|-------------|
| `run_000N/` | Per-iteration directory: `project.json`, train/val CSVs, pipeline outputs, `logs/`, `predictors/validation_metrics.json`. |
| `all_metrics.csv` | One row per successful iteration: `iteration`, `run_id`, `accuracy`, `balanced_accuracy`, `macro_f1`, `n_samples`, `n_classes`, etc. |
| `metrics_summary.json` | Per-metric empirical distribution: `mean`, `std`, `min`, `max`, `count`, `p5`, `p25`, `p50`, `p75`, `p95`. |
| `step_timings.csv` | Per step per run: `step_name`, `duration_seconds`, `return_code`, `run_id`, `n_train_samples`, `n_val_samples`. |
| `resource_summary.json` | Mean/std duration per step and range of train/val sizes. |
| `stability/stable_dmps_production.csv` | Stable DMP panel (created by `--stability`). |
| `stability/stability_summary.json` | Stability run summary: `n_runs_analyzed`, `stable_dmps_at_threshold`, `min_frequency`. |
| `production/project.json` | Frozen production project with `fixed_dmp_panel` in `step_config.detection`. |
| `production/classifiers/multiclass-classifier.pkl` | **Final production model.** |
| `production/production_summary.json` | Production freeze summary. |

---

## Three Key Diagnostics

### 1. Low DMP coverage (`dmps_used_fraction_median` < 0.5)

**Cause:** `min_sample_coverage` in `step_config.detection` > centroid `min_coverage` in `step_config.centroid.base_config`.

**Fix:**
```json
"centroid": { "base_config": { "min_coverage": 4 } },
"detection": { "min_coverage": 4, "min_sample_coverage": 4 }
```

### 2. Class imbalance (majority class recall ≈ 1.0, others ≈ 0)

**Cause:** Imbalanced cohort (e.g. 2–4× more healthy than disease samples).

**Fix:**
```json
"detection": {
  "multiclass_train_learned_head": true,
  "multiclass_learned_class_weight": "balanced"
}
```

### 3. sklearn version mismatch (`InconsistentVersionWarning`)

**Cause:** Model was trained with a different sklearn version than the one currently installed.

**Fix:** Re-run `--freeze`. The new model PKL will record `sklearn_version` in its metadata.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `command not found: methyl-validation` | Activate the venv: `source .venv/bin/activate` |
| `Monte Carlo config needs at least two cohorts` | Use `--project` not `--config` when passing a project file |
| `step_config.validation not found` | Add the `validation` block to your project's `step_config` |
| `FileNotFoundError: fixed_dmp_panel not found` | Run `--stability` before `--freeze` |
| `Blind predictor: blind mode rejected` | Remove `blind` from `step_config.predictor` |
| Stability panel is empty | Lower `stability_dmp_freq` or increase `n_iterations` |

---

## Related Documentation

- **Theory and algorithms:** `docs/theory/` (Quarto book)
- **Two workflows in depth:** `docs/theory/chapters/12-two-workflows.qmd`
- **Full configuration reference:** `docs/theory/chapters/13-configuration-reference.qmd`
- **User guide:** `docs/theory/chapters/14-user-guide.qmd`
- **Implementation notes:** `packages/methylvalidation/docs/IMPLEMENTATION.md`
