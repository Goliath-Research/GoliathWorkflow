# Workflow Engine

The workflow engine schedules DomainProgram graphs either **in-process** (`LocalWorkflowEngine`) or via a **database-backed** engine with remote workers.

## Components

| Path | Role |
|------|------|
| `workflow_engine/local/` | In-process graph executor; `methyl-workflow-run` entry |
| `workflow_engine/rest/` | `methyl-gateway` — stateless HTTP → stored procedures |
| `workflow_engine/sql/` | Azure SQL deploy scripts, SamplePrep/DataDriven docs |
| `workflow_engine/sql_pg/` | PostgreSQL parity |
| `workflow_engine/domain/` | DomainProgram compiler, profiles, fixtures, checks |

## Local execution

```bash
methyl-workflow-run \
  --program workflow_engine/domain/checks/pca1_5_cg/configs/study_validation_lifecycle.program.json \
  --context-file workflow_engine/domain/profiles/staged_ovr_mc.profile.json \
  --context '{"projectPath": "/work/projects/prostate-cancer/configs/project_Healthy_vs_PCa1-5-CG.json"}'
```

`LocalWorkflowEngine` materializes the same compiled graph as production without DB leases.

## Database engine

Deploy order and object list: [`workflow_engine/README.md`](../../workflow_engine/README.md).

Key concepts:

- `workflow_def` / `workflow_version` — compiled graph storage
- `workflow_instance` + `context_json` — per-run bindings
- `node_execution` + `scope_variable` — scheduling and `${var.*}` resolution
- `task_lease` — worker claim semantics

## Related

- [Architecture: distributed runtime](../architecture/distributed-runtime.md)
- [Pipeline architecture (full)](../../workflow_engine/docs/pipeline_architecture.md)
- [IMPLEMENTATION.md](../../workflow_engine/docs/IMPLEMENTATION.md)
