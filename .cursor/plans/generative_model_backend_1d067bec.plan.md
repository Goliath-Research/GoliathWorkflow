---
name: Generative model backend
overview: Add a first-class hybrid generative backend for `methyl-validation --model` that uses detector-derived DMP features/weights (via bundle artifacts), supports binary and multiclass prediction, and integrates with existing predictor outputs/metrics while keeping ECDF/tabular options available.
todos:
  - id: gen-config-cli
    content: Add generative_hybrid backend options to MonteCarloConfig and methyl-validation CLI overrides
    status: completed
  - id: gen-backend-core
    content: Implement methyl_validation/generative_backend.py for train/predict using bundle-derived features and detector weights
    status: completed
  - id: gen-artifacts
    content: Define and write generative artifact + metadata format under production classifiers directory
    status: completed
  - id: gen-orchestration
    content: Wire generative_hybrid branch into run_pipeline_for_model with standard step logs/timings
    status: completed
  - id: gen-multiclass-binary
    content: Implement and verify binary + multiclass label/probability handling with existing predictor cohort resolution
    status: completed
  - id: gen-covariates
    content: Integrate optional covariates sidecar into generative feature pipeline with strict ID join
    status: completed
  - id: gen-tests
    content: Add targeted tests for backend selection, strict config validation, metrics output, and artifact shape
    status: completed
  - id: gen-verify
    content: Run targeted pytest + lints across methylvalidation/methylpredictor/methylclassifier touched files
    status: completed
isProject: false
---

# Hybrid Generative Backend Plan

## Outcome

Implement a new `model_backend` option (full first-class rollout) that trains and serves a **hybrid generative model**:

- VAE-style encoder to latent `z`
- class-conditional density in latent space for likelihood-based scoring
- posterior class probabilities for binary and multiclass

The backend must consume MethylDetector outputs (DMP index + effect_size/weight) and not re-derive biology-aware weighting.

## Integration Points

- Model orchestration: [packages/methylvalidation/methyl_validation/pipeline_runner.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/pipeline_runner.py)
- Config + CLI wiring: [packages/methylvalidation/methyl_validation/config.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/config.py), [packages/methylvalidation/methyl_validation/cli.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/cli.py)
- Bundle artifacts: [packages/methylvalidation/methyl_validation/model_bundle.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/model_bundle.py)
- Existing tabular extraction path to reuse: [packages/methylvalidation/methyl_validation/tabular_backend.py](/home/ubuntu/MethylPipeline/packages/methylvalidation/methyl_validation/tabular_backend.py)
- Predictor/classifier compatibility contract: [packages/methylpredictor/methyl_predictor/core/predictor.py](/home/ubuntu/MethylPipeline/packages/methylpredictor/methyl_predictor/core/predictor.py), [packages/methylclassifier/methyl_classifier/core/classifier.py](/home/ubuntu/MethylPipeline/packages/methylclassifier/methyl_classifier/core/classifier.py)

## Architecture

```mermaid
flowchart LR
  det[MethylDetector DMP exports] --> bundle[ModelFeatureBundle H5+JSON]
  bundle --> feat[Feature extractor from sample H5]
  feat --> enc[Hybrid encoder VAE]
  enc --> latent[Latent z]
  latent --> classdens[Class conditional density]
  classdens --> proba[Posterior probabilities]
  proba --> pred[Predictions + metrics JSON/CSV]
```



## Implementation Steps

1. **Add backend config surface**
  - Extend `MonteCarloConfig.model_backend` choices to include `generative_hybrid`.
  - Add strict typed fields for generative hyperparameters (latent dim, KL weight, density type, epochs, batch size, seed, calibration toggle).
  - Add CLI overrides for those fields (same pattern as tabular flags).
2. **Create generative backend module**
  - Add `methyl_validation/generative_backend.py` with:
    - `train_generative_model(...)`
    - `predict_generative_model_from_project(...)`
  - Reuse bundle DMP index and sample extraction mechanics from tabular backend.
  - Implement weighted feature pipeline using detector `weight/effect_size` as input weighting (no re-estimation of biological weights).
3. **Model artifact format**
  - Save backend artifacts under production classifier dir, including:
    - model weights/state

n     - metadata JSON (class_names, n_classes, feature_order, latent config, bundle path, covariates info)

- Keep outputs aligned with predictor expectations: `predictions.csv` with `prediction` and `prob_class`*, plus `validation_metrics.json`.

1. **Orchestrate in `--model` flow**
  - Add `generative_hybrid` branch to `run_pipeline_for_model`:
    - `model-bundle`
    - `generative-train`
    - `generative-predictor`
  - Preserve existing timing/log writing behavior and `model_summary.json` compatibility.
2. **Binary + multiclass handling**
  - Ensure training labels come from `ProjectConfig.get_resolved_groups()` in order.
  - For prediction, support existing predictor cohort resolution (`test_group_paths` for K-class; binary control/disease lists) and compute metrics consistently.
3. **Covariates support (v1)**
  - Reuse current covariates sidecar flow (`.h5` preferred, `.csv` allowed).
  - Concatenate covariates into model input or latent conditioner with strict id join by sample basename / configured id column.
4. **Validation + strictness tests**
  - Add tests for:
    - backend selection and artifact generation
    - binary and multiclass probability output shape
    - strict config validation failures
    - covariate join behavior
  - Keep/extend targeted package tests and lint checks.

## Compatibility Rules

- Do not change ECDF behavior when `model_backend=ecdf`.
- Do not change tabular behavior when `model_backend=tabular_sklearn`.
- Keep `validator_metrics` compatibility by writing expected scalar fields in `validation_metrics.json`.
- Keep HDF5 plugin ordering (`import hdf5plugin` before `import h5py`) wherever generative artifact I/O touches H5 with plugin compression.

