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

## If the first launch failed with strict reuse

Primary `monte_carlo_runs/run_*` is discovery-only and is **not** compatible with
the freeze/production detection contract (`fixed_dmp_panel`). Model-MC must reuse
`model_mc/shared` from the archived freeze-panel shared runs, then rebuild ECDF only.

The driver script now links `model_mc/shared` → `model_mc.pre_alr_stacker.bak/shared`
automatically (**symlink**, not `cp -a` — NFS rejects permission preservation and can leave mode-`700` partial trees).
automatically. Relaunch:

```bash
tmux kill-session -t hpca-extval10-model 2>/dev/null || true
tmux new-session -d -s hpca-extval10-model \
  'bash /work/projects/prostate-cancer/configs/run_H_PCa_good_ecdf_covariates_extval10_model.sh'
tmux attach -t hpca-extval10-model
```

Expect log lines like `Kept existing compatible shared artifacts` / `Reusing existing model-mc shared runs`, then `Running model-mc backend=ecdf`.

## Success checks

1. New `monte_carlo_runs/model_mc/ecdf/metrics_summary.json` exists.
2. Per-run second-stage / dataset manifests show **logit class-1 + 5 Neu-referenced
   ALR coordinates** (not 8 standardized raw fractions).
3. `validation_model` completes; locked_test scoring only in that stage.
4. Do not start Tier-A search against the same trial dirs on both VMs.

## Relaunch after ALR / epsilon fix (2026-07-21)

Earlier gene-train runs still skipped second-stage because shared/`mc_config` had
overlapping numeric + composition columns, and `MonteCarloConfig` did not expose
`ecdf_second_stage_probability_epsilon` via runtime getattr.

**On the H_PCa VM (`192-222-51-118`):**

```bash
# 1) stop the old session
tmux kill-session -t hpca-extval10-model 2>/dev/null || true
pkill -f 'run_H_PCa_good_ecdf_covariates_extval10_model.sh' 2>/dev/null || true
pkill -f 'methyl-workflow-run.*context_H_PCa_good_ecdf_covariates' 2>/dev/null || true

# 2) apply platform getattr fix into this host's checkout
bash /work/projects/prostate-cancer/configs/patches/apply_ecdf_epsilon_getattr_fix.sh

# 3) relaunch
tmux new-session -d -s hpca-extval10-model \
  'bash /work/projects/prostate-cancer/configs/run_H_PCa_good_ecdf_covariates_extval10_model.sh'
tmux attach -t hpca-extval10-model
```

`ecdf-second-stage.log` must not report a missing-epsilon skip.
