# Buffy gene Tier-A cross-VM runbook

This runbook executes the Buffy gene+covariates study from a clean output tree, then confirms content-addressed action reuse and runs BA-first Tier-A slices. It uses only repository DomainPrograms and the study files under `/work/projects/prostate-cancer/configs/`.

## Prerequisites

- The repository is checked out at `/home/ubuntu/MethylPipeline` and `.venv` is installed.
- `/work/samples`, `/work/genomes`, `/work/site`, and the prostate-cancer project are mounted at the same paths.
- These study files are present:
  - `project_Buffy_ecdf_gene_covariates.json`
  - `context_Buffy_ecdf_gene_covariates.json`
  - `grid_Buffy_ecdf_gene_covariates_tier_a.json`
  - `weights_Buffy_ecdf_gene_covariates_ba.json`
- `/work/projects/prostate-cancer/Buffy_ecdf_gene_covariates` does not exist before the baseline run. Do not copy artifacts from another study tree.

Run the workflow dry-run before consuming compute:

```bash
cd /home/ubuntu/MethylPipeline
source .venv/bin/activate
methyl-workflow-run \
  --program workflow_engine/domain/fixtures/mc_stability.program.json \
  --context-file /work/projects/prostate-cancer/configs/context_Buffy_ecdf_gene_covariates.json \
  --parallel-workers 1 --dry-run -v
```

## Baseline sequence

Start stability in a detached terminal. The log is outside the not-yet-created study directory so shell redirection cannot fail.

```bash
tmux new-session -d -s buffy-gene-mc 'bash -lc "
  cd /home/ubuntu/MethylPipeline && source .venv/bin/activate &&
  methyl-workflow-run \
    --program workflow_engine/domain/fixtures/mc_stability.program.json \
    --context-file /work/projects/prostate-cancer/configs/context_Buffy_ecdf_gene_covariates.json \
    --parallel-workers 1 -v \
    > /work/projects/prostate-cancer/Buffy_ecdf_gene_covariates.mc_stability.log 2>&1
"'
tmux attach -t buffy-gene-mc
```

Continue only after `stability/stability_summary.json` exists and `freeze_readiness.json` reports `go` or `go_with_risks`.

```bash
tmux new-session -d -s buffy-gene-freeze 'bash -lc "
  cd /home/ubuntu/MethylPipeline && source .venv/bin/activate &&
  methyl-workflow-run \
    --program workflow_engine/domain/fixtures/validation_freeze.program.json \
    --context-file /work/projects/prostate-cancer/configs/context_Buffy_ecdf_gene_covariates.json \
    --parallel-workers 1 -v \
    > /work/projects/prostate-cancer/Buffy_ecdf_gene_covariates.freeze.log 2>&1
"'
```

After freeze succeeds, run strict model-MC and then final post-model validation:

```bash
tmux new-session -d -s buffy-gene-model-mc 'bash -lc "
  cd /home/ubuntu/MethylPipeline && source .venv/bin/activate &&
  methyl-workflow-run \
    --program workflow_engine/domain/fixtures/validation_model_mc.program.json \
    --context-file /work/projects/prostate-cancer/configs/context_Buffy_ecdf_gene_covariates.json \
    --parallel-workers 1 -v \
    > /work/projects/prostate-cancer/Buffy_ecdf_gene_covariates.model_mc.log 2>&1
"'

tmux new-session -d -s buffy-gene-model 'bash -lc "
  cd /home/ubuntu/MethylPipeline && source .venv/bin/activate &&
  methyl-workflow-run \
    --program workflow_engine/domain/fixtures/validation_model.program.json \
    --context-file /work/projects/prostate-cancer/configs/context_Buffy_ecdf_gene_covariates.json \
    --parallel-workers 1 -v \
    > /work/projects/prostate-cancer/Buffy_ecdf_gene_covariates.model.log 2>&1
"'
```

Start `buffy-gene-model` only after `buffy-gene-model-mc` exits successfully. The final phase is the only phase that evaluates `locked_test`.

Do not use `/tmp` DomainPrograms, hand-written summaries, or `requireArtifactReuse: false`. Fix a reproducible incompatibility in code instead of modifying artifacts.

## Idempotency replay

Record baseline duration, then rerun the identical stability command without `--force-rerun`:

```bash
/usr/bin/time -o /work/projects/prostate-cancer/Buffy_ecdf_gene_covariates.replay.time \
  -f 'elapsed=%e' \
  bash -lc 'cd /home/ubuntu/MethylPipeline && source .venv/bin/activate &&
    methyl-workflow-run \
      --program workflow_engine/domain/fixtures/mc_stability.program.json \
      --context-file /work/projects/prostate-cancer/configs/context_Buffy_ecdf_gene_covariates.json \
      --parallel-workers 1 -v' \
  > /work/projects/prostate-cancer/Buffy_ecdf_gene_covariates.replay.log 2>&1
```

The replay log must show signature-based skips or CAAS reuse for unchanged actions. Preserve the baseline and replay timings as the wall-clock evidence; do not delete `.action_results`.

## BA-first Tier-A search (gene FeatureCuts only)

Do **not** run freeze, model-MC, or locked_test during search. Score mean gene-FC BA from
`run_*/gene_stability/gene_featurecuts_metrics.json` (aggregated automatically when
`metrics_summary.json` is absent). ECDF + covariates come only after a winner.

Slice 1 raises `stability_gene_featurecuts_max_dmps` (site 1000 was too restrictive):

| Axis | Values |
|------|--------|
| `stability_gene_featurecuts_max_dmps` | 20000, 100000 |
| `gene_featurecuts_target_ba` | 0.90, 0.95 |
| `n_iterations` | 10 (full) |

Base config (portable paths, uncapped default cleared by grid cells):

```text
/work/projects/prostate-cancer/experiments/Buffy_ecdf_gene_covariates_tier_a/base_mc_config.json
```

```bash
cd /home/ubuntu/MethylPipeline
source .venv/bin/activate
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
