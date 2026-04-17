# MethylValidation Usage Guide

## Overview

MethylValidation orchestrates repeated train/validation splits, **methyl-centroid + methyl-detector** per iteration, backend model training/evaluation loops, and production freeze/model build. It supports the staged workflow below:

1. **Stability discovery** (`--stability`) — Identify stable DMPs across many random splits.
2. **Production freeze** (`--freeze`) — Build fixed-panel biological outputs on all data.
3. **Model-selection Monte Carlo** (`--model-mc`) — Full retrain+test MC per backend with isolated backend outputs.
4. **Final model training** (`--select-best-model`) — Select best backend from model-MC summaries and train final production model on all data.
5. **On-demand evaluation/prediction** (`--post-model-validation` / `--predictor-only`) — Optional frozen-model descriptive holdouts or direct prediction use.

Both workflows are controlled by the project configuration file. See the full Quarto documentation at `docs/theory/` for theoretical background and the complete configuration reference.
For production migration policy, see [`ROLLOUT.md`](ROLLOUT.md).

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

# Step 3: Full model-selection MC retraining loop
methyl-validation --project configs/my_project.json --model-mc --model-mc-all

# Step 4: Select best backend and train final production model on all data
methyl-validation --project configs/my_project.json --select-best-model --model-mc-all
```

**Why this workflow?**

- Monte Carlo splits refit centroids and detection on training fractions; **balanced_accuracy** in `all_metrics.csv` comes from **MethylDetector** validation (mean over `result*.json`) unless you use **`--predictor-only`** with a frozen model.
- Stability analysis identifies DMPs that recur in ≥ `stability_dmp_freq` fraction of runs.
- The freeze step prepares the final data using only the stable positions (`fixed_dmp_panel`), bypassing re-discovery, and extracting the valid pathway families (genes).
- The model-MC step retrains each backend on each split and produces backend-specific metric distributions.
- Final model training uses the selected best backend on all production data.
- Every MC output root now writes `baseline_manifest.json` with split policy, seed policy, cohort sample digests, and metric schema version for reproducibility locking.

**Output:** `monte_carlo_runs/production/classifiers/multiclass-classifier.pkl` is the final production model (created after `--model`).

### Workflow mental model

```mermaid
flowchart TB
  subgraph mcStage [Workflow 1 Stage A Stability]
    mcIter["MC iterations"]
    mcC[methyl-centroid]
    mcD[methyl-detector]
    mcS["stability aggregation"]
    mcIter --> mcC --> mcD --> mcS
  end

  mcS --> freezeStageStart["Workflow 1 Stage B --freeze"]
  freezeStageStart --> frC[methyl-centroid]
  frC --> frD["methyl-detector fixed panel"] --> frM[methyl-mapper] --> frE[methyl-enricher] --> frP["optional methyl-disease-progression"]

  frP --> modelStageStart["Workflow 1 Stage C --model"]
  modelStageStart --> mdC[methyl-classifier] --> mdP["methyl-predictor (production validation pass)"]

  mdP --> wf2Start["Workflow 2 --post-model-validation"]
  wf2Start --> wf2Iter["MC holdouts"] --> wf2Pred["frozen backend evaluation per iteration"] --> wf2Ba["all metrics distributions + Plotly KDE/ECDF"]

  wf2Start --> wf2Lite["Optional --predictor-only (ECDF-only lightweight path)"]

  mdP --> newSamplePred["Predict new samples with the frozen model"]
```

### Workflow 2: Optional Frozen-Model Evaluation

**Purpose:** Measure descriptive frozen-model performance distributions after final model build (no retraining).

**Prerequisites:** Workflow 1 must have been completed (`production/project.json` must exist).

```bash
methyl-validation --project configs/my_project.json --post-model-validation
```

**Why this workflow?**

- Uses frozen artifacts only (no retraining).
- Supports all model backends.
- Provides empirical distributions for multiple metrics (`balanced_accuracy`, `sensitivity`, `specificity`, `macro_f1`, etc.).
- Includes proper-score diagnostics when probabilities are available (`nll`, `brier_score`, `ece`) in `validation_metrics.json` and MC aggregates.
- Exports `metrics_distributions_plotly.html` with KDE and ECDF for each metric.
- Uses the same stratified splitting logic as Workflow 1 for consistency.

### Accuracy confirmation vs blind inference

Use this order to keep model-quality evidence valid:

1. Train/evaluate with labeled splits (for example 80% train, 20% test) and Monte Carlo iterations.
2. Select the best backend by labeled metrics (`balanced_accuracy` default).
3. Retrain final production model on all available labeled data (`--select-best-model` -> final production build).
4. Use blind cohorts only after that final build for real-world inference.

Blind predictions are intentionally not used to claim accuracy because they do not include ground-truth labels.

### Recommended backend-selection defaults (PCa)

For prostate cancer stage workflows similar to `Healthy_vs_PCa1-4-CG`, use:

- `--selection-metric balanced_accuracy`
- `--selection-stat median`

Why:

- `balanced_accuracy` is robust to class imbalance across stages/cohorts.
- `median` (p50) is less sensitive to outlier runs than `mean`, so backend ranking is usually more stable in Monte Carlo experiments.

Example:

```bash
methyl-validation --project /work/prostate-cancer/configs/project_Healthy_vs_PCa1-4-CG.json \
  --select-best-model --model-mc-all \
  --selection-metric balanced_accuracy --selection-stat median
```

When to change defaults:

- Use `--selection-stat mean` if you explicitly want to reward occasional high-performing runs and accept higher variance.
- Use `--selection-metric macro_f1` when your primary objective is balanced precision/recall behavior across all classes rather than rank-balanced accuracy.

---

## CLI Flags

### Which steps run (CLI package mapping)

| Mode / Flag | Main steps that run |
|---|---|
| Monte Carlo loop (`methyl-validation` default, optional `--stability`) | Per iteration: `methyl-centroid` + `methyl-detector` |
| `--stability` | Uses the same Monte Carlo loop above, then runs stability aggregation over discovery DMP outputs (`run_stability_analysis`) |
| `--freeze` | `methyl-centroid` + `methyl-detector` (fixed panel) + `methyl-mapper` + `methyl-enricher` + optional `methyl-disease-progression` |
| `--model` (`model_backend="ecdf"`) | `methyl-classifier` + `methyl-predictor` on frozen `production/project.json` |
| `--model` (`model_backend="tabular_sklearn"` / `"generative_hybrid"`) | In-process backend flow: model bundle -> train -> predict (consumes freeze outputs; does not re-run `methyl-detector`) |
| `--model-mc` | Full MC retraining per split: centroid -> detector -> backend train/predict; writes isolated results under `model_mc/<backend>/`. With `--model-mc-all`, centroid+detector runs are built once and reused by all backends. |
| `--post-model-validation` | MC holdout evaluation on frozen production artifacts (no retraining): `ecdf` uses predictor-only runs, tabular/generative use frozen model inference |
| `--predictor-only` | Monte Carlo iterations where each iteration runs only `methyl-predictor` with frozen artifacts |

| Flag | Description | Main subprocesses / backend path |
|------|-------------|----------------------------------|
| `--project PATH` | Path to the project JSON (preferred; reads `step_config.validation` from the project). | Controls whichever path you select (`--stability`, `--freeze`, `--model-mc`, `--select-best-model`, `--model`, `--post-model-validation`, or `--predictor-only`). |
| `--config PATH` | Path to a standalone Monte Carlo config JSON (alternative to `--project`). | Same as above, but from MC config file mode. |
| `--stability` | Run stability analysis after the MC loop (Workflow 1, Step 1). | MC loop (`methyl-centroid` + `methyl-detector`) then in-process stability aggregation. |
| `--stability-featurecuts` | Enable detector FeatureCuts during MC (`classifier_dmp_selection=featurecuts_validation`) and compute stability from classifier-panel DMP exports. | Detector step override per run + classifier-panel stability aggregation. |
| `--stability-target-ba BA` | In FeatureCuts mode, target balanced accuracy used to pick minimum top-k DMPs by effect size. | Detector FeatureCuts target-BA selection (`target_balanced_accuracy`). |
| `--stability-min-selected-dmps N` | In FeatureCuts mode, enforce minimum selected DMP count per run. | Detector lower bound (`min_selected_dmps`) after FeatureCuts selection. |
| `--skip-centroid` | Reuse existing per-run centroids and run detector only (no centroid recomputation). Useful when tuning `step_config.detection` hyperparameters on the same MC splits. | MC loop runs detector-only using existing `run_XXXX/project.json` and centroid artifacts. |
| `--resume [RUN]` | Resume interrupted MC runs for `--stability` / default MC mode. Without `RUN`, repeats the last existing run and continues to `n_iterations`; with `RUN` (1-based), restarts from that run. | MC loop resume control (run directories `run_0001`, `run_0002`, ...). |
| `--freeze` | Run production freeze using the stable DMP panel, up to enricher (Workflow 1, Step 2). If `step_config.progression.enabled=true`, this also runs `methyl-disease-progression` after enricher. | `methyl-centroid` -> `methyl-detector` (fixed panel) -> `methyl-mapper` -> `methyl-enricher` (+ optional progression). |
| `--model` | Run production model builder after freeze (Workflow 1, Step 3). | `ecdf`: `methyl-classifier` -> `methyl-predictor`; other backends: bundle -> train -> predict. |
| `--model-mc` | Run full backend MC retraining+evaluation loop for model selection. | Per iteration: centroid -> detector -> backend train -> backend predict. |
| `--model-mc-all` | With `--model-mc`, run all supported backends with isolated outputs while reusing one shared MC run set. | Creates `model_mc/shared/run_XXXX` plus `model_mc/ecdf`, `model_mc/tabular_sklearn`, `model_mc/generative_hybrid`. |
| `--select-best-model` | Rank backend model-MC summaries and train final production model on all data. | Reads `model_mc/*/metrics_summary.json`, picks best by `--selection-metric`/`--selection-stat`, then runs production model build. |
| `--rollout-compare` + `--baseline-summary` + `--candidate-summary` | Compare dual-run summaries and emit promote/hold recommendation JSON using rollout thresholds from `step_config.validation`. | In-process comparison (no training/inference run). |
| `--selection-metric METRIC` | Metric for backend ranking in `--select-best-model`. | Default: `balanced_accuracy`. |
| `--selection-stat {mean,median}` | Statistic for backend ranking in `--select-best-model`. | Default: `median` (p50). |
| `--post-model-validation` | Run descriptive MC holdout evaluation with frozen production artifacts (no retraining). | `ecdf`: predictor-only evaluation; tabular/generative: in-process frozen model predict. Outputs to `monte_carlo_runs/post_model_validation/`. |
| `--model-backend` / `--post-model-backend` | Override backend used by `--model`, `--model-mc`, or `--post-model-validation`. If omitted, backend is read from `step_config.validation.model_backend`. | `ecdf` \| `tabular_sklearn` \| `generative_hybrid` |
| `--predictor-only` | Run only `methyl-predictor` per iteration using the frozen model (Workflow 2). | Monte Carlo iterations, predictor only. |
| `--skip-enricher` | Skip the enricher inside MC iterations even when `run_mapper_and_enricher: true`. | Also short-circuits enricher (and therefore progression) in `--freeze`. |
| `--iterations N` | Override `n_iterations` from config. | Affects MC loop count (`--stability` and `--predictor-only`). |
| `--seed S` | Override `seed` from config. | Affects MC split reproducibility. |
| `--output-base DIR` | Override `output_base` from config. | Affects all output roots. |

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

### Stability + freeze controls (operationally important)

Common fields for production staging:

- `run_stability`: enable stability aggregation after MC iterations.
- `stability_dmp_freq`: recurrence threshold for stable DMP selection.
- `stability_min_balanced_accuracy`: optional run-quality gate; only qualifying runs contribute to stability counts.
- `stability_gene_freq`: recurrence threshold for stable genes (when enricher outputs are available).
- `stability_featurecuts_enabled`: force detector FeatureCuts policy in MC (`classifier_dmp_selection=featurecuts_validation`).
- `stability_target_balanced_accuracy` / `stability_min_selected_dmps`: optional FeatureCuts constraints used in MC detector overrides.
- `stability_dual_cutoff_enabled`: enable dual strict/relaxed post-MC panels using `combined_score = effect_size * sqrt(frequency)`.
- `stability_relaxed_cutoff_mode`: relaxed cutoff rule: `elbow_log_score` (tail elbow) or `strict_multiplier`.
- `stability_relaxed_multiplier`: multiplier used when `stability_relaxed_cutoff_mode = strict_multiplier`.
- `stability_score_eps`: epsilon used in `log(score + eps)` elbow detection.
- `stability_tiers_enabled`: emit three tiered panel directories from one stability pass.
- `stability_tier_core_freq`: core threshold (default `0.85`).
- `stability_tier_extended_freq`: extended threshold (default `0.80`).
- `stability_tier_exploratory_freq`: exploratory threshold (default `0.70`).
- `stability_default_freeze_tier`: which tier aliases root `stable_dmps_production.csv` for `--freeze` (default `extended`).
- `freeze_stable_dmp_csv`: optional override for freeze input panel path (default: `monte_carlo_runs/stability/stable_dmps_production.csv`).
- `production_output_dir`: optional freeze/model output root (default: `monte_carlo_runs/production`).

`--freeze` fails fast if the stable panel path is missing, so run `--stability` first or set `freeze_stable_dmp_csv`.

### Strict stability profile example

Use this profile when you want conservative run filtering and classifier-panel-aligned stability:

```json
"validation": {
  "n_iterations": 30,
  "run_stability": true,
  "stability_dmp_freq": 0.6,
  "stability_min_balanced_accuracy": 0.9,
  "stability_gene_freq": 0.5,
  "stability_featurecuts_enabled": true,
  "stability_target_balanced_accuracy": 0.95,
  "stability_min_selected_dmps": 1000
}
```

This keeps runtime fixed while enforcing high per-run detector quality and explicit classifier-panel constraints.

### Covariate contract for `tabular_sklearn` / `generative_hybrid`

Covariates are backend-specific and are **not** used by the ECDF Bayesian path.

- **Join key:** `covariate_id_column` must match sample folder basename (for example `S123` from `/path/to/S123`).
- **Input formats:** `.csv` / `.tsv` or `.h5`/`.hdf5` sidecar (`sample_id`, `values`, optional `columns`).
- **Column roles:** inferred by default, or fixed via `covariate_numeric_columns`, `covariate_ordinal_columns`, and `covariate_categorical_columns`.
- **Numeric preprocessing:** impute via `covariate_missing_numeric_strategy` (`mean`, `median`, `zero`) then optional z-score (`covariate_standardize_numeric`).
- **Ordinal preprocessing:** mapped to ordered numeric codes (single feature per column) using `covariate_ordinal_maps`; if omitted, known label sets like `low/medium/high` are auto-mapped; unknown/missing values use `covariate_ordinal_unknown_value`.
- **Categorical preprocessing:** one-hot with frozen vocab and `__UNKNOWN__` bucket at inference.
- **Strictness:** `covariates_strict_join` (tabular) and `generative_covariates_strict` (generative) enforce one-to-one sample id coverage.

Example (`step_config.validation`) using all covariate types:

```json
"validation": {
  "model_backend": "generative_hybrid",
  "covariates_path": "/data/covariates.csv",
  "covariate_id_column": "sample_id",
  "covariate_numeric_columns": ["age", "bmi", "visceral_fat_pct"],
  "covariate_ordinal_columns": ["risk_band"],
  "covariate_ordinal_maps": {
    "risk_band": {
      "low": 1,
      "medium": 2,
      "high": 3
    }
  },
  "covariate_ordinal_unknown_value": 0,
  "covariate_categorical_columns": ["ethnicity", "center"],
  "covariate_missing_numeric_strategy": "median",
  "covariate_standardize_numeric": true
}
```

### Disease-feature controls for `observed_hybrid`

When `step_config.validation.feature_mode` is `observed_hybrid`, you can explicitly control which disease-aware feature families are included:

- `observed_feature_include_dmp` (default `true`): DMP-derived global/quantile and disease-comparison summaries
- `observed_feature_include_dmr` (default `true`): DMR/region aggregates
- `observed_feature_include_gene` (default `true`): gene-level aggregates
- `observed_feature_include_chromosome` (default `true`): chromosome-level summaries
- `observed_feature_dmr_window_bp` (default `100000`): fallback region window size when explicit DMR labels are absent
- `observed_feature_max_dmrs` / `observed_feature_max_genes` (default `32`): cap the number of top-weighted regions/genes retained in schema

These options are used by all three model backends in model-build flows:

- `ecdf` second-stage refinement (`ecdf-second-stage`)
- `tabular_sklearn`
- `generative_hybrid`

`methyl-validation` enforces train/predict schema parity via stored feature names + fill values in backend metadata.

### Tabular method configs (`tabular_sklearn`)

`step_config.validation` now supports canonical nested method configs for tabular backends:

- `tabular_methods`: ordered list of one or more entries
- each entry uses a `method` discriminator and method-specific `params`
- supported `method` values: `random_forest`, `hist_gradient_boosting`, `logistic_regression`
- when multiple methods are provided, the run evaluates all in order and promotes the top method to canonical tabular artifacts

Method selection controls:

- `tabular_method_selection_metric` (default `balanced_accuracy`)
- `tabular_method_selection_stat` (default `mean`, stored as ranking metadata label)

Canonical nested JSON example:

```json
"validation": {
  "model_backend": "tabular_sklearn",
  "tabular_methods": [
    {"method": "random_forest", "params": {"n_estimators": 500, "min_samples_leaf": 2, "class_weight": "balanced_subsample"}},
    {"method": "logistic_regression", "params": {"max_iter": 2000, "class_weight": "balanced", "c": 1.0}}
  ],
  "tabular_method_selection_metric": "balanced_accuracy",
  "tabular_method_selection_stat": "mean"
}
```

Backward compatibility:

- legacy `tabular_model_type` still works unchanged
- CLI shorthand `--tabular-model-type` maps to a single-entry `tabular_methods` list
- optional `--tabular-methods-json` allows direct nested list overrides from CLI

### Optional: `step_config.progression`

`methyl-validation` reads progression settings from `step_config.progression` in the project JSON when running `--freeze`:

```json
"step_config": {
  "progression": {
    "enabled": true,
    "ordered_comparison_labels": ["pca_pca1", "pca_pca2", "pca_pca3", "pca_pca4"],
    "strict_missing": false,
    "report_md": true
  }
}
```

- `enabled`: run `methyl-disease-progression` after `methyl-enricher` in freeze.
- `ordered_comparison_labels`: explicit stage order (optional; defaults to project comparison order).
- `strict_missing`: fail progression if any expected stage file is missing.
- `report_md`: emit `progression/report.md` in addition to CSV/JSON outputs.

### Canonical vs legacy config keys

Prefer these canonical keys in project files:

- `step_config.predictor` (legacy alias `step_config.validator` is deprecated)
- `step_config.enricher.input_file` / `step_config.enricher.output_dir` (legacy `input` / `outdir` are deprecated)
- `step_config.detection.ecdf_grid_size` (legacy aliases `ecdf_overlap_grid_size`, `ecdf_ks_grid_size` are deprecated)

### Rollout comparison thresholds

`--rollout-compare` uses thresholds from `step_config.validation`:

- `rollout_balanced_accuracy_drop_max`
- `rollout_macro_f1_drop_max`
- `rollout_nll_improvement_min_frac`
- `rollout_brier_improvement_min_frac`
- `rollout_ece_improvement_min_frac`

If not set, package defaults in `MonteCarloConfig` are used.

---

## Outputs

All outputs are under `output_base/project_name/monte_carlo_runs/`:

| File / Directory | Description |
|-----------------|-------------|
| `run_000N/` | Per-iteration directory: `project.json`, train/val CSVs, pipeline outputs, `logs/` (binary centroid runs write `methyl-centroid-group1.log` and `methyl-centroid-group2.log`), `predictors/validation_metrics.json`. |
| `all_metrics.csv` | One row per successful iteration: `iteration`, `run_id`, `accuracy`, `balanced_accuracy`, `macro_f1`, `n_samples`, `n_classes`, etc. When **validation_metrics.json** uses train/holdout mode, extra columns may include **`evaluation_semantics`**, **`training_balanced_accuracy`**, **`holdout_balanced_accuracy`**, and other **`training_*` / `holdout_*`** scalars. |
| `metrics_summary.json` | Per-metric empirical distribution: `mean`, `std`, `min`, `max`, `count`, `p5`, `p25`, `p50`, `p75`, `p95`. |
| `step_timings.csv` | Per step per run: `step_name`, `duration_seconds`, `return_code`, `run_id`, `n_train_samples`, `n_val_samples`, optional `n_processed_samples` for centroid rows. Binary MC runs include separate `methyl-centroid-group1` and `methyl-centroid-group2` rows. |
| `resource_summary.json` | Mean/std duration per step and range summaries for train/val sizes; includes `n_processed_samples` when present. |
| `stability/stable_dmps_production.csv` | Stable DMP panel (created by `--stability`). |
| `stability/stable_dmps_strict.csv` | Strict dual-cutoff panel (high-confidence subset for modeling) when `stability_dual_cutoff_enabled=true`. |
| `stability/stable_dmps_relaxed.csv` | Relaxed dual-cutoff panel (broader biology set for mapping/enrichment) when `stability_dual_cutoff_enabled=true`. |
| `stability/stable_dmps_scored.csv` | Frequency-filtered DMPs ranked by `combined_score = effect_size * sqrt(frequency)`. |
| `stability/stable_dmps_score_diagnostics.json` / `.csv` | Strict/relaxed cutoff diagnostics (indices, thresholds, retained counts, cutoff mode). |
| `stability/tier_core/`, `stability/tier_extended/`, `stability/tier_exploratory/` | Tiered dual-cutoff outputs when `stability_tiers_enabled=true`; each folder contains strict/relaxed/scored panels plus diagnostics and a tier-local `stable_dmps_production.csv`. |
| `stability/stable_dmps_production.csv` (tiered mode) | Root alias copied from `stability_default_freeze_tier` (default: `tier_extended`) so `--freeze` works without extra path overrides. |
| `stability/dmp_frequency_by_chromosome.html` | Combined Plotly chart with one series per chromosome (both `all` and `selected` traces): X = DMP frequency across runs (%), Y = DMP count. |
| `stability/dmp_frequency_chr_<chrom>.html` | Per-chromosome Plotly chart files, each showing `all` vs `selected` DMP count distributions over frequency (%). |
| `stability/stability_summary.json` | Stability run summary for DMP/gene frequency plus detector parameter extraction. Includes `detector_parameters.per_run` and `detector_parameters.aggregates` built from `detections/**/results-*.json` (minimal fields: exported/statistical/biological DMP totals, `effect_size_coverage`, `delta_mean_reduction`, `classifier_dmp_selection`, `dynamic_dmp_cutoff_enabled`). |
| `production/project.json` | Frozen production project with `fixed_dmp_panel` in `step_config.detection`. |
| `model_mc/shared/run_000N/` | Shared per-iteration artifacts (split projects + centroid/detector outputs) reused by all backends in `--model-mc --model-mc-all`. |
| `model_mc/<backend>/run_000N/` | Per-iteration backend model outputs (predictor/model artifacts and logs) produced from shared runs. |
| `model_mc/<backend>/all_metrics.csv` | One row per successful model-MC iteration for that backend. |
| `model_mc/<backend>/metrics_summary.json` | Per-backend empirical distribution summary. |
| `model_mc/<backend>/run_000N/predictors/feature_family_ablation.json` | Feature-family ablation scaffold with current balanced accuracy and recommended matrix (`baseline`, `+DMP`, `+DMR`, `+gene`, `all`). |
| `model_mc/backend_ranking.csv` | Cross-backend ranking by `--selection-metric` and `--selection-stat`. |
| `production/selected_backend.json` | Selected backend metadata and ranking used for final all-data training. |
| `post_model_validation/run_000N/` | Per-iteration post-model holdout evaluation outputs and logs. |
| `post_model_validation/all_metrics.csv` | One row per successful post-model iteration with scalar metrics. |
| `post_model_validation/metrics_summary.json` | Empirical distribution summary of post-model metrics. |
| `post_model_validation/metrics_distributions_plotly.html` | Plotly chart with KDE and ECDF for all numeric metrics. |
| `production/progression/` | Disease progression synthesis outputs (`genes_long.csv`, `pathways_long.csv`, `modules_long.csv`, `entities_progression_labels.csv`, `summary.json`, optional `report.md`). |
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
