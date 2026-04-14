---
name: Observed-only Hybrid Features
overview: Design and integrate an observed-only hybrid feature layer (no methylation imputation) for tabular and generative backends, and add ECDF second-stage scoring support using the same constrained feature set.
todos:
  - id: feature-builder
    content: Create shared observed-only hybrid feature builder with schema + reliability outputs.
    status: pending
  - id: tabular-wireup
    content: Integrate observed-only hybrid features into tabular train/predict paths with metadata parity.
    status: pending
  - id: generative-wireup
    content: Integrate observed-only hybrid features into generative train/predict paths with metadata parity.
    status: pending
  - id: config-and-routing
    content: Add config knobs and pass-through routing for feature mode and thresholds.
    status: pending
  - id: ecdf-second-stage
    content: Add optional ECDF second-stage scorer using observed-only hybrid features and expose outputs safely.
    status: pending
  - id: validation
    content: Run unit/integration validation and compare holdout behavior against current baseline.
    status: pending
isProject: false
---

# Observed-only Hybrid Feature Plan

## Outcome
Add a shared feature-builder that computes biologically constrained, observed-only features (no `0.5` methylation fill) and use it across:
- `tabular_sklearn` training/prediction
- `generative_hybrid` training/prediction
- optional ECDF second-stage scorer for binary decision refinement

## Scope and constraints
- Use only DMPs present in each sample for feature statistics.
- Keep hybrid feature dimensionality moderate (target ~30-80 columns).
- Preserve reliability features so models can learn evidence quality, not just signal magnitude.
- Keep existing backends runnable; add feature mode as an explicit path/flag with backward-compatible default.

## Implementation steps
- Add a new shared module (suggested: [packages/methylvalidation/methyl_validation/observed_feature_builder.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/observed_feature_builder.py)) that:
  - builds per-sample observed-only deltas against reference means
  - computes global features (weighted signed/abs shift + quantiles)
  - computes constrained gene/region block features
  - computes reliability features (`obs_fraction`, `obs_weight_fraction`, counts)
  - outputs a dense feature table + metadata schema
- Wire tabular backend in [packages/methylvalidation/methyl_validation/tabular_backend.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/tabular_backend.py):
  - replace direct raw DMP matrix training path with the observed-only feature table when enabled
  - persist feature schema/ordering in `tabular-model-metadata.json`
  - use same builder in prediction to guarantee train/infer parity
- Wire generative backend in [packages/methylvalidation/methyl_validation/generative_backend.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/generative_backend.py):
  - train latent model on observed-only hybrid features (plus optional covariates)
  - reuse identical feature schema at prediction
- Add config controls in [packages/methylvalidation/methyl_validation/config.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/config.py):
  - feature mode toggle (raw vs observed-hybrid)
  - hybrid feature knobs (top genes/regions, quantiles, min support thresholds)
  - minimum evidence threshold behavior (`indeterminate`/reject on low observed support)
- Add backend-step pass-through in [packages/methylvalidation/methyl_validation/trainer_api.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/trainer_api.py) so tabular/generative runners receive the new feature settings.
- Add ECDF second-stage scorer hook:
  - read ECDF `predictions.csv` probabilities and observed-only hybrid features
  - train lightweight calibrator/refiner (binary) and persist artifact under production classifiers
  - integrate into predictor output as an optional extra decision column (without replacing base ECDF outputs by default)

## Validation plan
- Unit-level:
  - deterministic feature schema generation across runs
  - observed-only behavior (no methylation imputation path for hybrid builder)
  - train/infer schema parity checks
- Integration-level:
  - run `--model --model-backend tabular_sklearn` and `generative_hybrid` with observed-hybrid mode
  - confirm produced metadata includes feature schema and reliability stats
  - verify metrics and prediction files are generated without shape mismatch
- Performance checks:
  - compare holdout metrics vs current raw-DMP baseline
  - inspect feature importance/contribution concentration on constrained gene/region block

## Key touchpoints
- [packages/methylvalidation/methyl_validation/tabular_backend.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/tabular_backend.py)
- [packages/methylvalidation/methyl_validation/generative_backend.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/generative_backend.py)
- [packages/methylvalidation/methyl_validation/trainer_api.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/trainer_api.py)
- [packages/methylvalidation/methyl_validation/config.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/config.py)
- [packages/methylpredictor/methyl_predictor/core/predictor.py](/home/ubuntu/MethylPipeline/packages/methylpredictor/methyl_predictor/core/predictor.py) (for optional second-stage ECDF decision columns)