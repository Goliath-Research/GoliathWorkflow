---
name: Buffy gene Tier-A
overview: Author a fresh Buffy gene+covariates study (mc_gene_fc, discovery loci, locked_test) with a BA-focused Tier-A grid and a clean, portable VM run sequence—no reuse of the existing Buffy MC tree and no manual artifact surgery.

> **Status: IMPLEMENTED.** The project, context, Tier-A slices, BA weights, and cross-VM runbook are ready; the full experiment remains an operator-run validation on the target VM.

azure_devops:
  type: Feature
  title: "Buffy gene Tier-A"
  work_item_id: null
  epic_id: 413
todos:
  - id: buffy-project-holdout
    content: Author project_Buffy_ecdf_gene_covariates.json with stratified ~10% locked_test + development_train (seed 42)
    status: completed
    work_item_id: null
  - id: buffy-gene-context
    content: Author context_Buffy_ecdf_gene_covariates.json (mc_gene_fc, discovery loci, no biomarker, ECDF raw_gene + ALR covariates, holdout exclude)
    status: completed
    work_item_id: null
  - id: buffy-tier-a-grid
    content: Author grid_Buffy_ecdf_gene_covariates_tier_a.json (BA-first gene FC × gene_freq 2D slices) + search command notes
    status: completed
    work_item_id: null
  - id: buffy-plan-docs
    content: Promote plan to docs/plans/buffy-ecdf-gene-tier-a.plan.md and update docs/plans/README.md
    status: completed
    work_item_id: null
  - id: buffy-vm-runbook
    content: "Document clean tmux sequence: mc_stability → freeze → model_mc → model; Tier-A pilot after baseline"
    status: completed
    work_item_id: null
---

# Buffy gene+covariates Tier-A cross-VM project

Topology **1B** uses one `mc_gene_fc` arm. Holdout **2A** creates a fresh study tree with a stratified 10% `locked_test`. Tier-A candidates are ranked primarily by balanced accuracy.

## Artifacts

| Artifact | Path |
|---|---|
| Study manifest | `/work/projects/prostate-cancer/configs/project_Buffy_ecdf_gene_covariates.json` |
| Context | `/work/projects/prostate-cancer/configs/context_Buffy_ecdf_gene_covariates.json` |
| Tier-A grid | `/work/projects/prostate-cancer/configs/grid_Buffy_ecdf_gene_covariates_tier_a.json` |
| BA weights | `/work/projects/prostate-cancer/configs/weights_Buffy_ecdf_gene_covariates_ba.json` |
| Output root | `/work/projects/prostate-cancer/Buffy_ecdf_gene_covariates` |
| Operator runbook | [`docs/deployment/buffy_gene_tier_a_cross_vm.md`](../deployment/buffy_gene_tier_a_cross_vm.md) |

The existing Buffy configurations and MC tree remain historical and are not overwritten.

## Study contract

- The study reuses the Buffy good-cohort CSVs and cell-fraction covariates.
- `stratified_holdout_by_fraction(..., fraction=0.10, seed=42)` produced 9 healthy and 13 PCa locked samples; the other 205 samples are explicit `development_train`.
- The context uses `mc_gene_fc`, gene FeatureCuts, and discovery loci without a DMP FeatureCuts or biomarker-filter stage.
- `stability_gene_featurecuts_max_dmps` and `stability_min_balanced_accuracy` remain unset.
- ECDF uses `raw_gene` features and ALR-transformed CD8T, CD4T, NK, Bcell, Mono, and Neu covariates.
- MC excludes `locked_test`; only final post-model validation may score it.

## Tier-A surface

The first slice searches `gene_featurecuts_min_genes × stability_gene_freq`; the second searches `gene_featurecuts_max_genes × stability_gene_freq`. Both keep `gene_featurecuts_target_ba=0.95`, holdout controls, and ten MC iterations fixed.

Trials use isolated `trial_NNNN/out` roots. Model-MC must complete before BA ranking because stability-only trials do not emit the required `metrics_summary.json`. The BA objective has weight 1.0; stable-gene reward is deliberately small at 0.05.

## Clean execution

Follow the operator runbook for:

1. baseline `mc_stability`;
2. `validation_freeze`;
3. strict `validation_model_mc`;
4. final `validation_model` against locked test;
5. identical-context replay to record action reuse and wall-clock behavior;
6. the first Tier-A slice, followed by the second only if needed.

Only repository fixtures under `workflow_engine/domain/fixtures/` are allowed. Do not use temporary resume programs, hand-written production summaries, or disabled artifact-reuse checks.

## Success criteria

- The fresh study tree has a non-empty locked test that is absent from all MC training splits.
- Each gene FeatureCuts run receives uncapped discovery DMPs.
- Stability emits a gene panel, summary, and acceptable freeze readiness.
- Model-MC emits per-iteration test metrics and final validation scores locked test.
- `search_summary.json` ranks a completed 2D slice using the BA-dominant objective.
- An identical workflow replay records content-addressed/signature skips and lower wall-clock work for unchanged actions.
