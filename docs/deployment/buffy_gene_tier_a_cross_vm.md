# Buffy gene Tier-A cross-VM runbook

This runbook runs the Buffy gene+covariates Tier-A experiment from study JSON under
`/work/projects/prostate-cancer/`, using a **promoted MethylPipeline release** (worker
venv + runtime-bundle). It does **not** change `wf` / `cfg` database schemas, the action
catalog, gateway contracts, or worker task models.

## Architecture boundary (release-stable ops)

| Layer | Role for this experiment |
|-------|--------------------------|
| `wf` / `cfg` schemas, gateway, action catalog | **Untouched** |
| Study / experiment JSON on `/work` | **Operator surface** — grids, weights, context, `base_mc_config` |
| Promoted worker packages (`methylvalidation`, `methylgeneselect`) | Generic platform capability (null cap clearing; gene-FC BA objective fallback) — must be **in the release**, not forked per study |
| Repo checkout / `.venv` | Only a temporary fallback until a release includes those package fixes |

**Do:** tune via `/work/.../configs/*.json` and `/work/.../experiments/...`; run CLIs from the release PATH.

**Do not:** edit Python for Buffy-specific logic, invent study-only profiles, or migrate DB schemas for Tier-A grids.

Platform gaps that belong in the next promote (already in git; not disease-specific):

1. Study/MC explicit `null` clears site `gene_selection.max_dmps` (gene-select).
2. Stability-only search scores mean BA from `run_*/gene_stability/gene_featurecuts_metrics.json` when `metrics_summary.json` is absent.

Until that promote lands, prefer **explicit large** `stability_gene_featurecuts_max_dmps` in the grid (slice 1 already uses `20000` / `100000`). Gene-FC BA ranking requires a venv that has the objective fallback (release after promote, or repo `.venv` as interim).

## Prerequisites

- Release at `/work/goliath/current` with `runtime-bundle` and worker PATH from
  `/work/goliath/current/env/worker.env` (typically `/work/goliath/venv-aarch64`).
- `/work/samples`, `/work/genomes`, `/work/site`, and the prostate-cancer project are mounted.
- These study files are present under `/work/projects/prostate-cancer/configs/`:
  - `project_Buffy_ecdf_gene_covariates.json`
  - `context_Buffy_ecdf_gene_covariates.json`
  - `grid_Buffy_ecdf_gene_covariates_tier_a.json`
  - `weights_Buffy_ecdf_gene_covariates_ba.json`
- `/work/projects/prostate-cancer/Buffy_ecdf_gene_covariates` does not exist before the baseline run. Do not copy artifacts from another study tree.

Activate the release environment (preferred):

```bash
set -a
source /work/goliath/current/env/worker.env
set +a
# Ensure methyl-* resolve from the release venv first
export PATH=/work/goliath/venv-aarch64/bin:$PATH
```

Dry-run before consuming compute (programs from **runtime-bundle**, not a git checkout):

```bash
methyl-workflow-run \
  --program /work/goliath/current/runtime-bundle/domain/fixtures/mc_stability.program.json \
  --context-file /work/projects/prostate-cancer/configs/context_Buffy_ecdf_gene_covariates.json \
  --parallel-workers 1 --dry-run -v
```

## Clean baseline before Tier-A

Do **not** start Tier-A until `Buffy_ecdf_gene_covariates` completes a **config-driven** baseline through `post_model_validation` (no mid-run NFS patches for `test_groups.json` / `val_*.csv`). See [`docs/plans/buffy-clean-pipeline.plan.md`](../plans/buffy-clean-pipeline.plan.md). Preferred driver on this host (repo `.venv` until release includes the holdout-eval fixes):

```bash
START_FROM=freeze bash /work/projects/prostate-cancer/configs/run_Buffy_ecdf_gene_covariates_baseline.sh
```

## Baseline sequence

Start stability in a detached terminal. The log is outside the not-yet-created study directory so shell redirection cannot fail.

```bash
tmux new-session -d -s buffy-gene-mc 'bash -lc "
  set -a && source /work/goliath/current/env/worker.env && set +a &&
  export PATH=/work/goliath/venv-aarch64/bin:\$PATH &&
  methyl-workflow-run \
    --program /work/goliath/current/runtime-bundle/domain/fixtures/mc_stability.program.json \
    --context-file /work/projects/prostate-cancer/configs/context_Buffy_ecdf_gene_covariates.json \
    --parallel-workers 1 -v \
    > /work/projects/prostate-cancer/Buffy_ecdf_gene_covariates.mc_stability.log 2>&1
"'
tmux attach -t buffy-gene-mc
```

Continue only after `stability/stability_summary.json` exists and `freeze_readiness.json` reports `go` or `go_with_risks`.

```bash
tmux new-session -d -s buffy-gene-freeze 'bash -lc "
  set -a && source /work/goliath/current/env/worker.env && set +a &&
  export PATH=/work/goliath/venv-aarch64/bin:\$PATH &&
  methyl-workflow-run \
    --program /work/goliath/current/runtime-bundle/domain/fixtures/validation_freeze.program.json \
    --context-file /work/projects/prostate-cancer/configs/context_Buffy_ecdf_gene_covariates.json \
    --parallel-workers 1 -v \
    > /work/projects/prostate-cancer/Buffy_ecdf_gene_covariates.freeze.log 2>&1
"'
```

After freeze succeeds, run strict model-MC and then final post-model validation:

```bash
tmux new-session -d -s buffy-gene-model-mc 'bash -lc "
  set -a && source /work/goliath/current/env/worker.env && set +a &&
  export PATH=/work/goliath/venv-aarch64/bin:\$PATH &&
  methyl-workflow-run \
    --program /work/goliath/current/runtime-bundle/domain/fixtures/validation_model_mc.program.json \
    --context-file /work/projects/prostate-cancer/configs/context_Buffy_ecdf_gene_covariates.json \
    --parallel-workers 1 -v \
    > /work/projects/prostate-cancer/Buffy_ecdf_gene_covariates.model_mc.log 2>&1
"'

tmux new-session -d -s buffy-gene-model 'bash -lc "
  set -a && source /work/goliath/current/env/worker.env && set +a &&
  export PATH=/work/goliath/venv-aarch64/bin:\$PATH &&
  methyl-workflow-run \
    --program /work/goliath/current/runtime-bundle/domain/fixtures/validation_model.program.json \
    --context-file /work/projects/prostate-cancer/configs/context_Buffy_ecdf_gene_covariates.json \
    --parallel-workers 1 -v \
    > /work/projects/prostate-cancer/Buffy_ecdf_gene_covariates.model.log 2>&1
"'
```

Start `buffy-gene-model` only after `buffy-gene-model-mc` exits successfully. The final phase is the only phase that evaluates `locked_test`.

Do not use `/tmp` DomainPrograms, hand-written summaries, or `requireArtifactReuse: false`. Fix a reproducible incompatibility in a **promoted** package release instead of modifying artifacts.

## Idempotency replay

Record baseline duration, then rerun the identical stability command without `--force-rerun`:

```bash
/usr/bin/time -o /work/projects/prostate-cancer/Buffy_ecdf_gene_covariates.replay.time \
  -f 'elapsed=%e' \
  bash -lc 'set -a && source /work/goliath/current/env/worker.env && set +a &&
    export PATH=/work/goliath/venv-aarch64/bin:$PATH &&
    methyl-workflow-run \
      --program /work/goliath/current/runtime-bundle/domain/fixtures/mc_stability.program.json \
      --context-file /work/projects/prostate-cancer/configs/context_Buffy_ecdf_gene_covariates.json \
      --parallel-workers 1 -v' \
  > /work/projects/prostate-cancer/Buffy_ecdf_gene_covariates.replay.log 2>&1
```

The replay log must show signature-based skips or CAAS reuse for unchanged actions. Preserve the baseline and replay timings as the wall-clock evidence; do not delete `.action_results`.

## BA-first Tier-A search (gene FeatureCuts only)

Do **not** run freeze, model-MC, or locked_test during search. Score mean gene-FC BA from
`run_*/gene_stability/gene_featurecuts_metrics.json` (aggregated automatically when
`metrics_summary.json` is absent — requires a release that includes that objective fallback).
ECDF + covariates come only after a winner.

Slice 1 raises `stability_gene_featurecuts_max_dmps` (site 1000 was too restrictive):

| Axis | Values |
|------|--------|
| `stability_gene_featurecuts_max_dmps` | 20000, 100000 |
| `gene_featurecuts_target_ba` | 0.90, 0.95 |
| `n_iterations` | 10 (full) |

Base config (portable paths; grid cells set explicit raised caps):

```text
/work/projects/prostate-cancer/experiments/Buffy_ecdf_gene_covariates_tier_a/base_mc_config.json
```

```bash
# Uses release venv when it has gene-FC BA scoring; else falls back to repo .venv (pre-promote)
GRID_FILE=/work/projects/prostate-cancer/configs/grid_Buffy_ecdf_gene_covariates_tier_a.json
BASE_CONFIG=/work/projects/prostate-cancer/experiments/Buffy_ecdf_gene_covariates_tier_a/base_mc_config.json
WEIGHTS=/work/projects/prostate-cancer/configs/weights_Buffy_ecdf_gene_covariates_ba.json
WORK_DIR=/work/projects/prostate-cancer/experiments/Buffy_ecdf_gene_covariates_tier_a/max_dmps_by_target_ba
GRID="$(
  python -c 'import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps(d["slices"][0]["grid"]))' "$GRID_FILE"
)"

# Dry-run materializes trial_*/mc_config.json
methyl-hyperparam-search \
  --config "$BASE_CONFIG" \
  --work-dir "$WORK_DIR" \
  --grid "$GRID" \
  --weights-json "$WEIGHTS" \
  --dry-run

# Full 10-iter stability for all 4 trials (~1 day wall-clock)
tmux new-session -d -s buffy-tier-a-slice1 \
  /work/projects/prostate-cancer/experiments/Buffy_ecdf_gene_covariates_tier_a/run_slice1_search.sh
# Log: .../max_dmps_by_target_ba.search.log
```

After slice 1, inspect `search_summary.json` and per-trial `n_dmp_loci_for_features` (must be ≫ 1000).
If mean gene-FC BA is still below ~0.90, run slice 2 (`min_genes_by_recurrence`) with the winning
`max_dmps`/`target_ba` fixed in the base config. If a slice would exceed ~12 full trials, drop that
slice to `n_iterations=5` then confirm the top two at 10-iter.

Only then freeze → model-MC (ECDF + covariates) → post-model on `locked_test` for the winning config.
