# Distributed queue workflow (MethylValidation)

This flow splits **discovery** Monte Carlo work into a **plan** phase (fast, metadata only on shared storage) and **worker** tasks (centroid + detector, or predictor-only) that a central queue can schedule across many machines. All workers must see the same output tree (e.g. NFS at `/work/...`).

## Storage layout (under `output_base / project_name / monte_carlo_runs /`)

| Path | Purpose |
|------|---------|
| `run_####/` | One MC iteration: `project.json`, train/val CSVs, logs, outputs |
| `queue/mc_config.json` | Snapshot of `MonteCarloConfig` for workers |
| `queue/plan_runs.json` | Machine-readable list of planned runs and `task_json` paths |
| `queue/tasks/run_####.json` | One task descriptor per run (for `run-task`) |
| `queue/queue_manifest.jsonl` | One JSON object per line: command + `expected_outputs` (from `export-queue`) |
| `queue/commands.sh` | Shell one-liner per task (no queue API) |
| `queue/queue_summary.json` | Counts and paths after export |
| `queue/claims/` | Optional file-based lease directory (reservation by workers) |
| `run_####/queue_task_status.json` | Worker completion record (from `run-task`) |
| `run_####/queue_local_step_timings.json` | Step timings for `aggregate-results` to merge into `step_timings.csv` |

## Workflow

1. **Plan** (one process, short): generate all run directories and task JSON, no heavy pipeline.
   ```bash
   methyl-validation plan-runs --config mc.json --overwrite
   # or: --project /work/.../project.json
   ```

2. **Export** (optional): build manifest for your queue broker.
   ```bash
   methyl-validation export-queue --config mc.json
   # or: --monte-carlo-runs /work/.../project_name/monte_carlo_runs
   ```

3. **Workers**: each job runs exactly one task (repeat until the queue is empty).
   ```bash
   methyl-validation run-task --task /work/.../monte_carlo_runs/queue/tasks/run_0001.json
   ```

4. **Aggregate** (after all tasks succeed, or to refresh metrics from a partial set):
   ```bash
   methyl-validation aggregate-results --config mc.json
   # add --stability to run the same DMP/gene stability pass as legacy --stability
   ```

5. **Legacy path unchanged**: a single process can still run the monolithic `methyl-validation` without subcommands (sequential MC loop).

## Example: `/work` project (e.g. prostate)

If your project file lives at `/home/ubuntu/Work/prostate-cancer/configs/project_Healthy_vs_PCa1-4-CG.json`, with `output_base` pointing at shared storage, `plan-runs` / `export-queue` resolve `monte_carlo_runs` the same way as the legacy CLI under `output_base / project_name / monte_carlo_runs`.

## Recovery

- Re-run a failed `run-task` for the same `--task` JSON; outputs are under the run directory.
- `queue_task_status.json` records `failed` vs `completed`.
- `aggregate-results` ignores runs with failed status (when `queue_task_status.json` is present) and includes runs with computable per-run metrics.

## Central server and workers

The queue manifest is **backend-agnostic** (JSON lines). A central service can hand each worker one manifest line; workers need the same venv, `methyl-*` CLIs, and R/W access to the shared `monte_carlo_runs` tree.

## Task schema

Task files use `task_schema_version: "1.0"` and the Pydantic model `DiscoveryRunTaskV1` in `methyl_validation.task_schema`. Extra fields are allowed for forward compatibility (`model_config = extra="allow"`).
