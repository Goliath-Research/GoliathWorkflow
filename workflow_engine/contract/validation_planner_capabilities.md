# Validation planner capabilities

Middle-tier / worker contract for Monte Carlo and stratified validation runs. The workflow **engine** does not plan iterations; an optional **planner** runs before `sp_start_workflow_instance` and merges output into `context_json`.

## Workflow definition

Use **`ValidationPipeline`** ([`wf_validation_pipeline_seed.sql`](../sql/wf_validation_pipeline_seed.sql)):

- `FOREACH` over `context_json.iterations[]` (sequential by default)
- Each iteration runs centroid → detector with `${var.taskConfig}` in templates
- After all iterations, `final_sequence` runs mapper → enricher → progression on `projectPath`

Example instance payload: [`validation_mc.json`](../sql/instance_context_examples/validation_mc.json).

## Capability (proposed)

| Field | Value |
|-------|-------|
| Capability id | `validation.plan-iterations` |
| Worker package | `packages/methylvalidation` (planner / project_gen) |
| Invoked by | Portal or middle-tier before instance start |

Phase 2: thin handler in `workers/methyl_worker/handlers.py` or dedicated `workers/validation_planner/` wrapping existing `methyl_validation` run-project generation.

## Input

JSON body (planner request):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `projectPath` | string | yes | Base project JSON path or resolved project root |
| `featureIterations` | int | no | Feature-stability MC count (default from `step_config.validation`) |
| `qualityIterations` | int | no | Post-model quality MC count |
| `seed` | int | no | RNG seed for reproducible splits |
| `trainFraction` | number | no | Stratified train fraction (e.g. `0.8`) |
| `layout` | string | no | `binary` or multiclass layout name |

The planner reads `project.json` / portal `validation.schema.json` (`validation_monte_carlo`) when overrides are omitted.

## Output

Merge into instance `context_json`:

```json
{
  "projectPath": "/work/.../Plasma_healthy_vs_PCa",
  "workerToolMapper": "MethylMapper",
  "workerToolEnricher": "MethylEnricher",
  "workerToolProgression": "MethylDiseaseProgression",
  "orderedComparisonLabels": ["healthy_vs_PCa"],
  "iterations": [
    {
      "runId": "feature_run_0001",
      "phase": "feature",
      "projectPath": "/work/.../monte_carlo_runs/run_0001",
      "taskConfig": {
        "runId": "feature_run_0001",
        "phase": "feature",
        "iteration": 1,
        "layout": "binary",
        "trainFraction": 0.8,
        "seed": 42
      }
    }
  ]
}
```

### `iterations[]` element shape

Each object is opaque to the engine except for fields referenced in workflow templates:

| Field | Type | Used by ValidationPipeline |
|-------|------|---------------------------|
| `runId` | string | `${var.runId}` |
| `phase` | string | `${var.phase}` |
| `projectPath` | string | `${var.projectPath}` (iteration-specific run project) |
| `taskConfig` | object | `${var.taskConfig}` embedded JSON in centroid/detector payloads |

FOREACH flattening copies object keys into scope (`wf_seed_foreach_iteration_scope`), so `${var.taskConfig}` resolves without engine injection.

Additional keys (e.g. `groups`, `comparisons`) are allowed for worker consumption.

## Optional audit persistence

Planners may persist the full plan for debugging:

```sql
EXEC wf.wf_repo_upsert_instance_extension
  @instance_id = @id,
  @extension_key = N'methylvalidation.plan',
  @data_json = @plan_json;  -- json / jsonb
```

Read back:

```sql
SELECT wf.wf_repo_get_instance_extension(@id, N'methylvalidation.plan');
```

This is **not required** for execution — only `context_json.iterations[]` drives the workflow.

## Portal integration

1. Call planner (`validation.plan-iterations`) with base project parameters.
2. Merge planner `iterations[]` (and any top-level keys) into `context_json`.
3. Create workflow instance bound to **`ValidationPipeline`** (not `MethylValidationFlow`).
4. `EXEC wf.sp_start_workflow_instance @workflow_instance_id`.

See also: [`packages/methylvalidation/docs/USAGE.md`](../../packages/methylvalidation/docs/USAGE.md), [`pipeline_architecture.md`](../docs/pipeline_architecture.md) §6 extension pattern.
