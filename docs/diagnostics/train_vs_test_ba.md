# Train balanced accuracy near 100% vs test ~0.5

This note summarizes how the pipeline builds labels and features, and why a **constant prediction** (e.g. always class 0 / `centroid1`) yields **balanced accuracy 0.5** on a balanced binary test set.

## What “train BA” often measures

Training-time checks frequently classify **group centroids** (or mean profiles) at the DMP panel. Those summaries are built to separate the two cohorts, so **accuracy on centroids can be very high** even when **individual** holdout samples barely separate.

## Label alignment (binary Monte Carlo)

1. **`generate_run_project`** ([`project_gen.py`](../../packages/methylvalidation/methyl_validation/project_gen.py)) flattens the template `controls` / `diseases` into **one training CSV per side** and rewrites `comparisons` using [`_first_control_and_disease_labels`](../../packages/methylvalidation/methyl_validation/project_gen.py):
   - Control label = **first control group’s `label`** (e.g. `all` in [`project_Healthy_vs_PCa1-5-CG.json`](../../workflow_engine/domain/checks/pca1_5_cg/configs/project_Healthy_vs_PCa1-5-CG.json)).
   - Disease label = **first disease parent group’s `label`** (e.g. `pca`), not the staged leaf `pca_pca1`, because the MC project **replaces** nested `stages` with a single flat disease group.

2. After this rewrite, **`get_comparisons()`** and **`get_resolved_groups()`** agree: e.g. `all` vs `pca`, with outputs under `detections/all/pca/`, `classifiers/all/pca/`, etc.

3. **Predictor expected classes** for binary runs come from **control paths first (0), then disease paths (1)** ([`_build_samples_and_expected`](../../packages/methylpredictor/methyl_predictor/core/predictor.py)). MC **`_patch_step_config_predictor_binary_holdouts`** (internal helper name) points merged **`actionConfig.predictor`** at **validation CSVs** (`val_control.csv`, `val_disease.csv`) in the same order, so **0 = control, 1 = disease** matches the classifier’s **centroid1 vs centroid2** ordering **as long as** training used the same comparison.

4. **CLI override** `--test-control` / `--test-disease` merges into `test_group_paths` with explicit `class_index` 0 and 1 ([`project_resolver.py`](../../packages/methylpredictor/methyl_predictor/project_resolver.py)).

## CG-only H5 layout

When the model’s `model_contexts == ['CG']`, [`classify_samples_from_list`](../../packages/methylclassifier/methyl_classifier/cli/main.py) loads **only** `{chrom}-CG.h5` per sample directory (no CHG/CHH merge). Missing or misnamed files reduce usable DMPs; the predictions CSV still reports **`dmps_used`**, **`dmps_total`**, and **`dmp_coverage_pct`**.

## Template vs MC disease label (`pca` vs `pca_pca1`)

The **slim** template may use staged disease leaves (`pca_pca1`) for the **full** pipeline, while **binary MC** uses flattened labels (`pca`). Paths and pickles for a given run are **internally consistent** for that run’s `project.json`. If you compare artifacts across **different** project shapes, compare **directory names** (`all/pca` vs `all/pca_pca1`) and **`actionConfig.classifier.save_classifier_path`** / predictor `model_path`.

## `actionConfig.classifier` vs constant test predictions

[`project_Healthy_vs_PCa1-5-CG.json`](../../workflow_engine/domain/checks/pca1_5_cg/configs/project_Healthy_vs_PCa1-5-CG.json) sets `ovr_binary_pickles_from_comparisons: false` and **`weight_method: linear_fitted`** for multi-chromosome fusion. If every sample gets **similar** `prob_class0` / `prob_class1` and **always** predicts class 0, investigate:

- Per-chromosome / fused logits (`methyl-predictor` / classifier **`--debug`**).
- Whether **fitted chromosome weights** collapse signal toward one expert.
- **Cohort / batch effects** (individuals overlapping while centroids still separate).

## Predictor guardrails

[`run_prediction`](../../packages/methylpredictor/methyl_predictor/core/predictor.py) warns when fewer than `n_classes` distinct predictions appear on a labeled run, and writes **`sample_dmp_coverage`** summaries into `validation_metrics.json` when the predictions CSV contains DMP coverage columns.
