---
name: Buffy clean pipeline
overview: Land three platform fixes so freeze→model emits holdout eval artifacts from config (no NFS surgery), lock Buffy context to the best uncapped gene-FC + ALR second-stage contract, then resume from completed stability through post_model_validation on this VM only.

> **Status: IN PROGRESS.** Platform fixes landed; Buffy resume from freeze on this VM.

azure_devops:
  type: Feature
  title: "Buffy clean stability→model pipeline"
  work_item_id: null
  epic_id: 413
todos:
  - id: fix-readiness-ready
    content: Map freeze-readiness verdict.overall → ready; surface reasons
    status: completed
    work_item_id: null
  - id: emit-holdout-eval-artifacts
    content: Freeze writes test_groups + test/val CSVs to CAAS parent, production/, mc_root
    status: completed
    work_item_id: null
  - id: post-model-fallback
    content: post_model_validation derives cohorts from holdout_manifest if CSVs missing
    status: completed
    work_item_id: null
  - id: buffy-context-second-stage
    content: Set ecdf_second_stage_enabled=true in Buffy context/project
    status: completed
    work_item_id: null
  - id: promote-plan-docs
    content: Write docs/plans/buffy-clean-pipeline.plan.md + README row
    status: completed
    work_item_id: null
  - id: launch-buffy-freeze
    content: tmux START_FROM=freeze through model; verify second-stage + post_model COMPLETED
    status: in_progress
    work_item_id: null
---

# Buffy clean stability→model pipeline

## Goal

Confirm **Buffy_ecdf_gene_covariates** works end-to-end on this VM (`192-222-50-58`) as a **config-driven** pipeline: stability → freeze → model_mc → model (including `post_model_validation`). No mid-run NFS patches. Tier-A only after this baseline.

## Locked science parameters (source of truth)

Keep / set in [`/work/projects/prostate-cancer/configs/context_Buffy_ecdf_gene_covariates.json`](/work/projects/prostate-cancer/configs/context_Buffy_ecdf_gene_covariates.json) + matching project:

- Profile `mc_gene_fc`; `max_dmps=100000`, `max_genes=200`; gene-FC target BA `0.95`; `stability_gene_freq=0.3`
- ECDF `raw_gene` + cell-fraction covariates; **composition-groups only** (ALR vs `Neu`)
- **`ecdf_second_stage_enabled=true`** (logit + ALR stacker)
- Holdout: `locked_test`, exclude from training, seed `42`, `n_iterations=10`

**Reuse** existing uncapped MC (10/10 runs). Do **not** wipe `monte_carlo_runs/run_*` / `stability/`.

## Platform fixes

1. **Freeze readiness `ready` mapping** — [`workers/methyl_worker/handlers/validation.py`](../../workers/methyl_worker/handlers/validation.py): map `verdict.overall ∈ {go, go_with_risks}` → `ready=True`; surface `reasons`.
2. **Holdout eval sidecars** — [`holdout_eval.write_holdout_eval_artifacts`](../../packages/methylvalidation/methyl_validation/holdout_eval.py) + wire into [`prepare_freeze_project`](../../packages/methylvalidation/methyl_validation/stability.py) (DomainProgram path) and monolithic freeze; [`eval_split_resolver`](../../packages/methylvalidation/methyl_validation/eval_split_resolver.py) checks logical `production/` parent before CAAS resolve.
3. **Post-model cohort fallback** — derive `val_*.csv` from `holdout_manifest` + `locked_test` when missing.

## Execution

```bash
START_FROM=freeze bash /work/projects/prostate-cancer/configs/run_Buffy_ecdf_gene_covariates_baseline.sh
```

Driver uses repo `.venv` + runtime-bundle programs. Logs: `Buffy_ecdf_gene_covariates.{freeze,model_mc,model}.log`.

## Success criteria

- Freeze emits `holdout_manifest.json`, `test_groups.json`, and binary cohort CSVs under production/ + `monte_carlo_runs/`
- `model_mc` second-stage metadata shows logit + ALR composition features
- `model` / `post_model_validation` COMPLETED without hand-written study artifacts

## Out of scope

- H_PCa / other VM; Tier-A search; re-running uncapped `mc_stability`; release `venv-aarch64` compiler fix
