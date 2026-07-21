# H_PCa good ECDF extval10 — other-VM model rerun

Operator runbook for **`H_PCa_good_ecdf_covariates_extval10`** after the ALR
composition-groups migration. Stability and freeze stay; only model-MC and
post-model are re-run. Companion plan:
[`docs/plans/ecdf-studies-cross-vm.plan.md`](../plans/ecdf-studies-cross-vm.plan.md).

## Prerequisites (already done on shared NFS)

- Context migrated:
  `/work/projects/prostate-cancer/configs/context_H_PCa_good_ecdf_covariates.json`
  (`covariate_composition_groups` only; no overlapping `covariate_numeric_columns`).
- Old stacker archived:
  `…/monte_carlo_runs/model_mc.pre_alr_stacker.bak`
  (live `model_mc/` must **not** exist before launch).
- Driver script:
  `/work/projects/prostate-cancer/configs/run_H_PCa_good_ecdf_covariates_extval10_model.sh`
- `validation_model_mc.program.json` present under
  `/work/epimethyl/current/runtime-bundle/domain/fixtures/`
  (copied from the repo fixture if the release bundle lacked it).

## Environment on the other VM

Prefer the **repo `.venv`** for `methyl-workflow-run` if the release
`venv-aarch64` fails with `No module named 'compiler'` (observed on
`192-222-50-58`). Keep `METHYL_PROFILE_DIR` pointed at the runtime-bundle profiles.

```bash
export METHYL_PROFILE_DIR=/work/epimethyl/current/runtime-bundle/domain/profiles
cd /home/ubuntu/MethylPipeline   # or this host's checkout
source .venv/bin/activate
```

## Dry-run

```bash
DRY_RUN=1 bash /work/projects/prostate-cancer/configs/run_H_PCa_good_ecdf_covariates_extval10_model.sh
```

Confirm resolved ECDF params include `covariate_composition_groups` and
`requireArtifactReuse` is present on the model-MC action.

## Launch (tmux)

Do **not** run this on the Buffy VM while Buffy baseline is burning the GPU;
start on the dedicated other VM only.

```bash
tmux new-session -d -s hpca-extval10-model \
  'bash /work/projects/prostate-cancer/configs/run_H_PCa_good_ecdf_covariates_extval10_model.sh'
tmux attach -t hpca-extval10-model
```

Logs:

- `/work/projects/prostate-cancer/H_PCa_good_ecdf_covariates_extval10.model_mc.log`
- `/work/projects/prostate-cancer/H_PCa_good_ecdf_covariates_extval10.model.log`

## If strict reuse fails (missing classifier PKLs)

Discovery-only MC may lack `classifier-*.pkl`. If model-MC aborts on
`requireArtifactReuse`, temporarily run with a local program copy that sets
`requireArtifactReuse: false`, and/or set `actionConfig.detection.export_classifier: true`
in the context for a one-shot relaunch. Prefer fixing reuse inputs over leaving
reuse disabled permanently.

## Success checks

1. New `monte_carlo_runs/model_mc/ecdf/metrics_summary.json` exists.
2. Per-run second-stage / dataset manifests show **logit class-1 + 5 Neu-referenced
   ALR coordinates** (not 8 standardized raw fractions).
3. `validation_model` completes; locked_test scoring only in that stage.
4. Do not start Tier-A search against the same trial dirs on both VMs.
