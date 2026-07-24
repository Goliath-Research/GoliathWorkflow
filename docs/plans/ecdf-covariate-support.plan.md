---
name: ECDF Covariate Support
overview: Add optional covariate support to the ECDF backend by stacking first-stage ECDF predictions with covariates in a second-stage logistic model (reusing the shared covariate preprocessor), and enable that path for raw_dmp, raw_gene, and aggregated ECDF modes when `covariates_path` is set.

> **Status: Implemented.** First-stage ECDF remains methylation-only; optional second-stage fuses probs ± covariates ± observed_hybrid.

azure_devops:
  type: Feature
  title: "ECDF optional covariates (second-stage stacker)"
  work_item_id: null
  epic_id: 413
todos:
  - id: typed-second-stage-params
    content: Add Pydantic-typed covariate (+ existing) params to ecdf_second_stage API
    status: completed
  - id: stack-covariates
    content: Concat fit_covariates onto ECDF probs (+ optional observed_hybrid); persist preprocessor/metadata
    status: completed
  - id: trainer-gate-all-modes
    content: Run second stage for raw_dmp/raw_gene/aggregated when ecdf_second_stage_enabled (covariates_path coerces enabled=true)
    status: completed
  - id: profiles-docs-schema
    content: Wire ecdf covariates in research/cell_deconv profiles; update USAGE/theory; export schema if needed
    status: completed
  - id: tests
    content: Cover covariates-only stacker, raw_gene trainer gate, and strict join failure
    status: completed
---

# ECDF optional covariates (second-stage stacker)

## Decision

Use **ECDF predictions + covariates → second-stage model**, not early-concat into the Bayesian/histogram ECDF feature matrix.

## Implementation summary

- [`ecdf_second_stage.py`](../../packages/methylvalidation/methyl_validation/ecdf_second_stage.py): `EcdfSecondStageParams` + stack of probs / optional observed_hybrid / covariates
- [`trainer_api.py`](../../packages/methylvalidation/methyl_validation/trainer_api.py): gate on `ecdf_second_stage_enabled` (setting `covariates_path` coerces the flag true at config validate) for raw_dmp, raw_gene, and aggregated paths
- Profiles: `samd_research`, `samd_pivotal`, `samd_holdout_enrichment`, `mc_dmp_gene_fc`, `cell_deconv`
- Docs: USAGE, IMPLEMENTATION, theory ch.15
