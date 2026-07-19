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

## BA-first Tier-A pilot

The baseline creates:

```text
/work/projects/prostate-cancer/Buffy_ecdf_gene_covariates/monte_carlo_runs/queue/mc_config.json
```

Extract one 2D slice from the grid and generate isolated trial configs:

```bash
cd /home/ubuntu/MethylPipeline
source .venv/bin/activate
GRID_FILE=/work/projects/prostate-cancer/configs/grid_Buffy_ecdf_gene_covariates_tier_a.json
BASE_CONFIG=/work/projects/prostate-cancer/Buffy_ecdf_gene_covariates/monte_carlo_runs/queue/mc_config.json
WEIGHTS=/work/projects/prostate-cancer/configs/weights_Buffy_ecdf_gene_covariates_ba.json
WORK_DIR=/work/projects/prostate-cancer/experiments/Buffy_ecdf_gene_covariates_tier_a/min_genes_by_recurrence
GRID="$(
  python -c 'import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps(d["slices"][0]["grid"]))' "$GRID_FILE"
)"
methyl-hyperparam-search \
  --config "$BASE_CONFIG" \
  --work-dir "$WORK_DIR" \
  --grid "$GRID" \
  --weights-json "$WEIGHTS" \
  --dry-run
```

For every generated `trial_*/mc_config.json`, run stability, freeze, and ECDF model-MC in order:

```bash
for cfg in "$WORK_DIR"/trial_*/mc_config.json; do
  methyl-validation --config "$cfg" --stability
  methyl-validation --config "$cfg" --freeze
  methyl-validation --config "$cfg" --model-mc --model-mc-all
done
```

Do not run post-model validation for search candidates: that would tune against `locked_test`. After model-MC has created each trial's `model_mc/ecdf/metrics_summary.json`, rerun the search command without `--dry-run`; the stability step resumes its existing trial tree and `search_summary.json` ranks candidates with the BA-dominant weights.

```bash
methyl-hyperparam-search \
  --config "$BASE_CONFIG" \
  --work-dir "$WORK_DIR" \
  --grid "$GRID" \
  --weights-json "$WEIGHTS"
```

Run the second slice only after choosing the minimum-gene neighborhood; change `["slices"][0]` to `["slices"][1]` and use a distinct `max_genes_by_recurrence` work directory. Confirm the winning candidate with the canonical workflow in a fresh final study tree, then evaluate its locked test exactly once.
