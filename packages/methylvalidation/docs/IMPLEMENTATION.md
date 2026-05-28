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

- Run with `--stability` to evaluate many random splits and aggregate stable DMPs
- Run with `--freeze` to build production biological outputs from the stable panel
- Run with `--model-mc` to perform full backend-specific MC retrain+test loops for model selection
- Run with `--select-best-model` to select best backend and build final production model artifacts
- Uses `step_config.validation` settings from the project

### 2. Model Use for Prediction (Predictor-only)

- Uses same splits as Model Creation but only runs predictor
- Evaluates the frozen production model

**Command examples:**
```bash
# Model Creation
methyl-validation --project configs/project_Healthy_vs_PCa1-4-CG.json --stability
methyl-validation --project configs/project_Healthy_vs_PCa1-4-CG.json --freeze

# Model Selection Monte Carlo
methyl-validation --project configs/project_Healthy_vs_PCa1-4-CG.json --model-mc --model-mc-all

# Final model training (all data)
methyl-validation --project configs/project_Healthy_vs_PCa1-4-CG.json --select-best-model --model-mc-all

# Model Use for Prediction
methyl-validation --project configs/project_Healthy_vs_PCa1-4-CG.json --predictor-only
```

---

## Architecture overview

MethylValidation orchestrates stratified splits, project generation, and pipeline execution via subprocess calls. It supports both workflows described above.

### Package mapping by stage

- **MC loop (`methyl-validation` default, with optional `--stability`)**: per iteration runs `methyl-centroid` then `methyl-detector` (`run_pipeline_for_iteration`, `run_pipeline_for_iteration_multiclass`).
- **`--stability`**: after the MC loop, runs in-process stability aggregation (`run_stability_analysis`) over detector discovery outputs.
- **`--freeze`**: runs `run_pipeline_for_production`: `methyl-centroid` -> `methyl-detector` (fixed panel) -> `methyl-mapper` -> `methyl-enricher`, then optional `methyl-disease-progression`.
- **`--model-mc`**: full retrain+test MC for model selection. With `--model-mc-all`, MethylValidation first builds a shared iteration set (`model_mc/shared/run_XXXX`) for split + centroid + detector, then runs backend-specific train/predict stages under `model_mc/<backend>/run_XXXX`. When split source is reusable from primary MC runs, centroid/detector artifacts are linked into shared/backend run roots instead of recomputing.
- **`--model`**: runs `run_pipeline_for_model`. Backend comes from `step_config.validation.backend_profiles` (or validated CLI override). For `ecdf`, steps are `methyl-classifier` -> `methyl-predictor`. For `tabular_sklearn` and `generative_hybrid`, steps are in-process bundle -> train -> predict and do not re-run `methyl-detector`.
- **Aggregated ECDF observed-hybrid mode**: when `model_backend=ecdf` and observed-hybrid mapped features are active (`feature_family_set != dmp`), trainer API runs `ecdf-aggregated-train` -> `ecdf-aggregated-predictor` and intentionally skips `ecdf-second-stage`.
- **`--select-best-model`**: ranks backend model-MC summaries and runs final all-data production model build using selected backend.
- **`--post-model-validation`**: runs MC holdout evaluation against frozen production artifacts only (no retraining). `ecdf` dispatches predictor-only runs; `tabular_sklearn` and `generative_hybrid` dispatch frozen model inference via backend predictors.
- Legacy flat backend keys under `step_config.validation` are now rejected; migration is handled by `methyl-validation-migrate-backend-config`.
- **`--predictor-only`**: MC iterations that run only `methyl-predictor` using frozen artifacts.
- **`--rollout-compare`**: compares baseline/candidate `metrics_summary.json` and writes promotion/hold report using rollout thresholds in `MonteCarloConfig`.

ECDF/Bayesian remains DMP-only by design at the first stage. The optional ECDF second stage and the `observed_hybrid` path used by ECDF-aggregated/tabular/generative backends share a unified mapped-feature builder with explicit family toggles:

- `feature_family_set=dmp`: fixed DMP-family observed metrics (legacy behavior).
- `feature_family_set=gene`: dynamic one-feature-per-mapped-gene keys (`gene::<GENE>`).
- `feature_family_set=structural`: dynamic one-feature-per-mapped `(gene, feature_type)` keys (`struct::<GENE>::<FEATURE>`).
- combined families (`dmp+gene`, `dmp+structural`, `hybrid-all`) concatenate families in deterministic order.

For gene/structural keys, per-sample value uses signed weighted centered methylation over observed loci:

- `sum(sign(effect_size) * abs(effect_size) * (beta - 0.5)) / sum(abs(effect_size))`

Only mapped keys present in the stable DMP bundle are emitted (no synthetic all-feature expansion). All backends persist observed-feature schema/report/fill values, and prediction enforces strict parity via `verify_feature_schema` to prevent train/predict drift.

The main components are:

1. **Config & Layout**: Loads `MonteCarloConfig`, rejects blind predictors, and infers binary vs multiclass layout.
2. **Data Splitting**: `stratified_split*` functions create train/validation splits.
3. **Project Generation**: Creates per-run `project.json` files with appropriate sample paths.
4. **Pipeline Execution**: Uses `pipeline_runner.py` to run the appropriate steps.
5. **Aggregation**: Collects metrics and timings from all runs.

During stability MC runs, `stability_featurecuts_enabled` and related `stability_target_balanced_accuracy` / `stability_min_selected_dmps` settings are materialized per iteration as `detector_step_override.json` so detector selection policy is explicit and auditable in each `run_XXXX`.

The `--freeze` path uses `run_pipeline_for_production()` which runs: centroid → detector(with `fixed_dmp_panel`) → mapper → enricher; when `step_config.progression.enabled=true`, it then runs `methyl-disease-progression`.
During freeze, model-bundle preparation can materialize mapper annotation cache files under `production/model_bundle/` and wire `step_config.model_bundle.mapper_annotation_csv` for mapped-family feature builds.
Cache generation also supports configurable per-gene mapper attributes via `step_config.model_bundle.mapper_gene_columns` (or `step_config.mapper.mapper_gene_columns` fallback), defaulting to `["gene_score", "mean_effect_size", "gene_effect_compound", "gene_feature_effect_compound"]`; set `[]` to disable carrying extra per-gene columns.

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

Sample path resolution is done locally in MethylValidation ([split.py](../methyl_validation/split.py): `load_and_resolve_sample_paths`). Iteration metrics are produced by **MethylDetector** (balanced accuracy in `result*.json`) during the default MC loop, by backend predictors during `--model-mc`, or by frozen predictor paths during `--post-model-validation` / `--predictor-only`; MethylValidation aggregates via `iteration_scalar_metrics_from_run_dir`.

## Modules

| Module | Role |
|--------|------|
| **config.py** | `MonteCarloConfig` — `cohorts` (preferred) or legacy `healthy_csv`/`disease_csv`, plus train_fraction, n_iterations, seed, base_project, output_base, path_remap, abort_on_step_failure. |
| **predictor_policy.py** | `assert_monte_carlo_predictor_allowed` — reject `predictor.blind` / `test_blind_paths` for MC. |
| **split.py** | `load_and_resolve_sample_paths`; `stratified_split` (binary); `stratified_split_multiclass` (per-label train/val). |
| **project_gen.py** | `infer_monte_carlo_layout` (rejects 2 cohorts when project resolves to >2 leaves); `generate_run_project` (binary CSV names unchanged); `generate_run_project_multiclass` / `generate_run_project_hierarchical_multiclass` (`training_<label>.csv`, `testing_<label>.csv`, `val_test_groups.json`). Each run’s `project.json` rewrites `step_config.predictor` to the holdout CSVs: **flat** MC also sets `test_group_paths`; **hierarchical** MC only updates nested `controls`/`diseases` (keeps template parent labels, e.g. `prostate_cancer` vs top-level `pca`). MethylPredictor zips predictor list expansion with resolved centroid labels when `test_group_paths` is absent. |
| **pipeline_runner.py** | `run_pipeline_for_iteration` / `run_pipeline_for_iteration_multiclass`: centroid + detector only. In binary MC iterations, centroid executes as two tracked runs (`group1`, `group2`) with separate logs/timing rows and per-row `n_processed_samples` read from centroid metadata (`samples_used`). `run_pipeline_for_production`: freeze (centroid→detector→mapper→enricher) and optional `methyl-disease-progression` from `step_config.progression`. `run_pipeline_for_model`: classifier→predictor or backend bundle/train/predict. `run_predictor_only_*`: predictor-only. `run_post_model_validation_*`: frozen-artifact evaluation for post-model MC mode across all backends. |
| **trainer_api.py** | Backend step abstraction for `--model`. Builds backend-specific step lists (ECDF, aggregated ECDF observed-hybrid, tabular, generative) so orchestration can be extracted into a future `methylmodeltrainer` package without changing workflow CLI semantics. |
| **validator_metrics.py** | `iteration_scalar_metrics_from_run_dir`: predictor `validation_metrics.json` if present, else mean detector `balanced_accuracy` from `detections/**/result*.json`. Also exports aggregated Plotly KDE+ECDF chart (`metrics_distributions_plotly.html`) for post-model validation summaries. |

Config-contract audit and redundancy classification are tracked in [../../../docs/config_parameter_matrix.md](../../../docs/config_parameter_matrix.md). Use canonical keys (`predictor`, `input_file`, `output_dir`, `ecdf_grid_size`) in new project files; legacy aliases are compatibility-only.

## Data flow (CLI)

1. Load config; `assert_monte_carlo_predictor_allowed`; `infer_monte_carlo_layout(base_project, len(cohorts))`.
2. Resolve `project_name`; create `output_base/project_name/monte_carlo_runs/`.
3. Resolve all cohort sample paths from CSVs.
4. For each default/stability iteration:
   - **Binary:** `stratified_split` → `generate_run_project` → `run_pipeline_for_iteration` (centroid group1/group2 overrides).
   - **Multiclass:** `stratified_split_multiclass` → `generate_run_project_multiclass` → `run_pipeline_for_iteration_multiclass` (centroid + detector only).
   - Read metrics via `iteration_scalar_metrics_from_run_dir(run_dir)` (predictor JSON if present, else detector `result*.json`).
   - If `stability_early_stop_enabled=true` and stability mode is active, evaluate convergence at each checkpoint (`S_k` vs `S_(k-window)` by Jaccard + size delta) and stop when thresholds pass for `stability_convergence_patience` consecutive checkpoints.
5. Aggregate → `all_metrics.csv`, `metrics_summary.json`, `step_timings.csv`, optional `resource_summary.json`.
6. For `--model-mc`, run shared split+centroid+detector preparation once (for `--model-mc-all`), then run backend model stages under isolated backend roots and emit cross-backend ranking files (`backend_ranking.csv`, `backend_ranking.json`). Reused split runs can link primary centroid/detector artifacts into shared/backend roots.
7. For `--rollout-compare`, load baseline/candidate summaries, apply configured rollout thresholds, and emit `rollout_decision.json` (or `--rollout-report` path).

**MethylPredictor:** flat-group projects with **multiclass-classifier.pkl** resolve via `resolve_predictor_config` (shared `_build_multiclass_predictor_config`). The CLI applies `--test-groups` in both single-config and per-comparison multiclass runs (`_apply_test_groups_json_to_config`).

**After a frozen production build:** `--model-mc --model-mc-all` builds shared iteration artifacts under `monte_carlo_runs/model_mc/shared/` and evaluates each backend under `monte_carlo_runs/model_mc/<backend>/`. `--select-best-model` reads backend summaries, selects best backend by configured metric/statistic, and runs final all-data production model build. `--post-model-validation` remains a descriptive frozen-model MC path under `monte_carlo_runs/post_model_validation/`.

**Disease progression synthesis:** when `step_config.progression.enabled` is set, freeze invokes `methyl-disease-progression --project <production/project.json>` after enricher. The progression tool reads comparison outputs (`mapper/<control>/<disease>/all-gene_name-combined.csv`, `enricher/<control>/<disease>/enrichment_merged.csv`, optional `modules_ranked.csv`) and writes long tables + summary under `<project_root>/progression`.

## Output files

| File | Description |
|------|-------------|
| **all_metrics.csv** | One row per successful iteration: iteration, run_id, run_dir, accuracy, balanced_accuracy, sensitivity, specificity, macro_f1, etc. |
| **metrics_summary.json** | Per-metric empirical distribution: mean, std, min, max, count, percentiles (p5, p25, p50, p75, p95). |
| **step_timings.csv** | Per step per run: `step_name`, `duration_seconds`, `return_code`, `run_id`, `run_dir`, `n_train_samples`, `n_val_samples`, and optional `n_processed_samples` (centroid rows). Binary centroid runs emit `methyl-centroid-group1` and `methyl-centroid-group2` rows. |
| **resource_summary.json** | (Optional) Mean/std duration per step, mean total time per iteration, min/max/mean `n_train_samples`, `n_val_samples`, and `n_processed_samples` when present. |
| **model_mc/shared/run_XXXX/** | Shared per-iteration project + centroid/detector artifacts reused across backends when running `--model-mc --model-mc-all`. |
| **model_mc/shared/run_XXXX/centroids**, **model_mc/shared/run_XXXX/detections** | Symlinked from primary MC runs when split source is marked reusable; avoids duplicate detector execution. |
| **model_mc/<backend>/all_metrics.csv** | Per-backend model-stage MC metrics table produced from shared runs (or standalone backend runs when `--model-mc-all` is not used). |
| **model_mc/<backend>/metrics_summary.json** | Per-backend summary statistics used for backend ranking. |
| **model_mc/backend_ranking.csv** | Cross-backend ranking by configured metric/statistic. |
| **production/selected_backend.json** | Selected backend and ranking metadata for final all-data training decision. |
| **production/model_bundle/mapper_dmp_annotations.csv** | Mapper-derived annotation cache used by observed-hybrid mapped-family feature builders. |
| **production/classifiers/ecdf_aggregated_ovr.pkl**, **ecdf_aggregated_ovr.meta.json** | Aggregated ECDF OvR model artifacts for observed-hybrid ECDF backend mode. |
| **post_model_validation/metrics_distributions_plotly.html** | Plotly dashboard with KDE (density) and ECDF (cumulative) panels for each numeric metric. |
| **predictors/feature_family_ablation.json** | Ablation-oriented scaffold emitted for observed-hybrid paths (active families + recommended matrix for BA comparisons). |
| **classifiers/tabular_method_metrics.csv** | Per-method evaluation metrics for tabular multi-method sequence runs (ordered method index, selection metric score, rank). |
| **classifiers/tabular_method_ranking.json** | JSON ranking payload for tabular multi-method selection, including method params and selection rationale fields. |
| **stability/dmp_frequency_by_chromosome.html** | Combined Plotly stability chart with per-chromosome traces for both candidate (`all`) and final (`selected`) DMPs. X=frequency (% of runs), Y=DMP count. |
| **stability/dmp_frequency_chr_<chrom>.html** | Per-chromosome Plotly charts with `all` vs `selected` count curves over frequency (%). |
| **stability/stability_summary.json** | Stability summary now includes `detector_parameters` extracted from `detections/**/results-*.json`: per-run records plus aggregated numeric/categorical distributions for minimal detector/filter fields (`n_dmps_exported`, `total_statistical_dmps`, `total_biological_dmps`, `effect_size_coverage`, `delta_mean_reduction`, `classifier_dmp_selection`, `dynamic_dmp_cutoff_enabled`). When adaptive stop is enabled, `early_stopping` diagnostics are also recorded (`enabled`, `triggered`, stop iteration, and checkpoint history with Jaccard/size-delta stats). |

For setup (Docker, venv), config reference, and how to use these outputs for metric distributions and processing/storage estimation, see [USAGE.md](USAGE.md).
