# Admin CLI — `methyl-study-start`

> **Canonical** operator/CI entry for compile, plan, and start workflow instances.  
> **Not** exposed on the worker-only REST gateway (`/v1/workers/*`).

## Role

| Concern | Tool |
|---------|------|
| Worker claim/submit | `methyl-gateway` + `methyl-worker` |
| Compile DomainProgram → `WorkflowDefinitionSpec` | `methyl-study-start compile` |
| Deploy graph to DB | `scripts/deploy_workflow_definitions.sh` or portal |
| Start SamplePrep / validation instance | `methyl-study-start sample-prep-start` / `validation-start` |
| Plan MC iterations context | `methyl-study-start plan-iterations` |

Implementation: [`workflow_engine/admin/study_start.py`](../../workflow_engine/admin/study_start.py) → [`workflow_engine/ops/`](../../workflow_engine/ops/) → [`workflow_engine/rest/db_client.py`](../../workflow_engine/rest/db_client.py).

## Backend selection

Set database env before any subcommand (same as gateway):

| Backend | Variables |
|---------|-----------|
| PostgreSQL | `BACKEND_DB=postgres`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` |
| Azure SQL | `BACKEND_DB=mssql`, `AZURE_SQL_SERVER`, `AZURE_SQL_DB`, `AZURE_SQL_USER`, `AZURE_SQL_PASSWORD` |

Optional override: `METHYLPIPELINE_DB` (full DSN). Schema: `WF_SCHEMA` (default `wf`).

Templates: [`deploy/env/gateway.postgres.env.example`](../../deploy/env/gateway.postgres.env.example), [`deploy/env/gateway.mssql.env.example`](../../deploy/env/gateway.mssql.env.example).

```bash
set -a && source /work/goliath/env/gateway.env && set +a
source /work/goliath/venv-aarch64/bin/activate   # or repo .venv
```

## Subcommands

### `compile`

Compile a `*.program.json` to raw `WorkflowDefinitionSpec` JSON (stdout or `-o`).

```bash
methyl-study-start compile \
  workflow_engine/domain/fixtures/study_validation_lifecycle.program.json \
  --project-path /work/projects/prostate-cancer/configs/project_Healthy_vs_PCa1-5-CG.json \
  -o /tmp/lifecycle_spec.json
```

### `validation-start`

Plan validation context, optionally compile+deploy program, create instance, start.

```bash
methyl-study-start validation-start - <<'JSON'
{
  "projectPath": "/work/projects/prostate-cancer/configs/project_Healthy_vs_PCa1-5-CG.json",
  "pipelineProfile": "mc_gene_fc",
  "program_path": "workflow_engine/domain/fixtures/study_validation_lifecycle.program.json"
}
JSON
```

Or reuse deployed version: `"workflow_version_id": 42`.

**Output:** JSON with `workflow_instance_id`, `workflow_version_id`, enriched `context_json` keys.

### `sample-prep-start`

Start SamplePrep pipeline instance.

```bash
methyl-study-start sample-prep-start /work/projects/my-study/configs/sample_prep_request.json
```

### `plan-iterations`

Merge planner output into instance `context_json` (optional DB persist).

```bash
methyl-study-start plan-iterations planner_payload.json \
  --workflow-instance-id 1001
```

## Permissions

Requires DB roles that can call workflow repository procedures (`wf_repo_create_workflow_graph`, `sp_start_workflow_instance`, etc.). Bootstrap: [`scripts/bootstrap_distributed_workers.sh`](../../scripts/bootstrap_distributed_workers.sh).

## Separation from gateway

| Surface | Routes / commands |
|---------|-------------------|
| **Workers** | `POST /v1/workers/claim`, `POST /v1/workers/submit`, health |
| **Admin CLI** | `methyl-study-start *` (direct DB) |
| **Portal (future)** | `portal.sp_*` T-SQL procedures |

OpenAPI: [`contracts/openapi.yaml`](../../contracts/openapi.yaml) documents worker paths only.

## SaMD study creation helpers

| Command | Role |
|---------|------|
| `methyl-study-init` | Scaffold `/work/projects/<study-id>/` + slim `project_*.json` with `validation_partitions` |
| `methyl-study-validate-manifest` | Refuse empty required holdouts for `samd_holdout_enrichment` / `samd_pivotal`; block pre-pivotal clinical claims |

Operator SOP: [`../usage/18-samd-study-lifecycle.md`](../usage/18-samd-study-lifecycle.md). Presets: `scripts/workflow_presets.sh list` (`samd_*`).

Example validation-start context for enrichment:

```json
{
  "projectPath": "/work/projects/my-disease/configs/project_Healthy_vs_Disease.json",
  "pipelineProfile": "samd_holdout_enrichment"
}
```

## Related

- [DomainProgram language](domain-program-language.md)
- [Workflow engine](../implementation/workflow-engine.md)
- [Operator journey](../deployment/operator-journey.md)
- [Component boundaries](../architecture/component-boundaries.md)
- [SaMD study lifecycle](../usage/18-samd-study-lifecycle.md)
