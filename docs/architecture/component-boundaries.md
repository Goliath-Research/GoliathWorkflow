# Component boundaries

MethylPipeline separates **orchestration infrastructure** (database workflow engine, agnostic gateway, workers) from **pipeline knowledge** (actions, programs, profiles, studies). This document states the intended ownership of each layer.

## Database (`wf` + `portal` schemas)

The database owns:

| Responsibility | Mechanism |
|----------------|-----------|
| **Workflow engine** | Generic DAG/FOREACH control flow, scope variables, task leasing, instance state |
| **RBAC** | Entra roles, worker tokens, portal principals |
| **Portal UI render** | `portal.sp_*` procs, resource profiles, workflow builder |
| **Instance creation & configuration** | `workflow_instance.context_json` → scope at start; SQL resolves `${var.*}` into task `input_json` |
| **Monitoring & dashboards** | Instance/node execution status, portal views |
| **Execution scope identity + CAAS ledger** | `wf.execution_scope` (`set_key`, opaque `config_json`), nullable `workflow_instance.execution_scope_id`, `wf.execution_scope_action_entry` (`action_name`, `run_key`, `content_key`); no pipeline semantics in columns. The "hyperparameter" meaning lives in `cfg` (`cfg.hyperparameter_search_run` / `cfg.hyperparameter_trial`) |

The database does **not** encode methylation semantics. Action names, capabilities, and JSON schemas are **data rows** seeded from git; the engine never branches on pipeline meaning in SQL.

**Config resolution at instance time:** Portal middle-tier or `methyl-study-start` calls `finalize_instance_context()` before `create_workflow_instance`, baking `resolvedConfig__<action_config_key>` scope variables. The SQL read-path binds these into action input templates — workers receive fully-resolved payloads without gateway enrichment.

## REST gateway (`methyl-gateway`)

The gateway is a **stateless REST passthrough** between compute workers and the database:

| Allowed | Forbidden |
|---------|-----------|
| Worker auth, claim, submit, heartbeat, fail | Reading `schemas/actions/catalog.json` |
| Health check | Catalog seed, workflow deploy, study lifecycle |
| | `materialize_action_input` / config merge at claim |
| | DomainProgram compile, validation/sample-prep planners |

**Identity:**

- **Worker** — `POST /v1/workers/*` with `worker_id` + `worker_token`

EpiPortal **never** calls the gateway; it uses Azure SQL `portal.sp_*` directly.

## Operator tooling (domain-aware, outside gateway)

| Tool | Role |
|------|------|
| **Portal SQL** (`portal.sp_*`) | Production create/start/monitor for EpiPortal |
| **`methyl-study-start` (Admin CLI)** | Compile/plan/start via `rest.db_client` (MSSQL or PostgreSQL) — Cursor developer mode + CI |
| **`workflow_engine/ops`** | Shared helpers used by Admin CLI and deploy/seed scripts |
| **`scripts/deploy_workflow_definitions.sh`** | Compile + deploy workflow specs via direct DB |
| **`seed_action_catalog.py`** | Upsert action catalog + dispatch metadata into `wf.workflow_action` |
| **`methyl-workflow-run`** | Local in-process runs (no database) |
| **Cursor MCP** | Interactive SQL inspect/edit in development |

The Admin CLI does **not** go through the REST gateway. It opens the same backend-agnostic DB connection workers' gateway uses (`open_gateway_db` / `BACKEND_DB`), runs domain Python (compile/plan/enrich), then writes through `rest.db_client`.

## Compute workers

Workers poll the gateway (or future equivalent transport), execute tasks, and submit results. They:

- Authenticate with worker credentials only
- Consume `input_json` including `resolvedConfig` as produced by the DB engine
- Never connect to SQL directly
- Never use MCP

**Process-pack dispatch** (methyl-specific, outside the engine) uses a catalog-driven
[action provider registry](action-provider-registry.md): CLI subclasses register by
`action_name`, in-process handlers live under `methyl_worker.handlers`, and compiler
template extras come from catalog `domain_effects`. Optional worker-local `Depends`
([`depends.py`](../../workers/methyl_worker/depends.py)) injects `TaskRuntimeContext` /
logger / path helpers into in-process handlers only — not into the SQL engine, gateway,
or DomainProgram compiler.

## MCP servers (development only)

Cursor MCP servers (`user-azure-sql-dev`, PostgreSQL MCP) are **operator/dev tooling**:

- Inspection, parity checks, surgical SQL during development
- **Not** part of worker runtime, gateway data plane, or production automation

Bulk catalog seed and workflow deploy use direct-DB scripts — not MCP and not the gateway.

See also [worker-transport-decision.md](worker-transport-decision.md).

## Pipeline knowledge (git + `/work`)

| Artifact | Location | Validated by |
|----------|----------|--------------|
| Action catalog | `workers/methyl_worker/action_catalog.py` → `schemas/actions/catalog.json` | CI export check |
| Task I/O schemas | `schemas/tasks/*.schema.json` | JSON Schema |
| DomainPrograms | `workflow_engine/domain/**/*.program.json` | `domain_program.schema.json` |
| Profiles | `workflow_engine/domain/profiles/*.profile.json` | `profile.schema.json` |
| Study manifests | `/work/projects/<study>/configs/project_*.json` | `project_config.schema.json` |
| Site manifest | `/work/site/methyl_site.json` | `site_manifest.schema.json` |

## Related docs

- [Layer model](layer-model.md) — four-layer config precedence
- [Distributed runtime](distributed-runtime.md) — portal / gateway / worker topology
- [Orchestration paths](orchestration-paths.md) — local vs distributed entry points
- [Action provider registry](action-provider-registry.md) — process pack vs engine; registry over DI
- [portal_study_lifecycle.md](../../workflow_engine/docs/portal_study_lifecycle.md) — portal staged starts
- Plan: [agnostic-gateway-and-boundaries.plan.md](../plans/agnostic-gateway-and-boundaries.plan.md)
- Plan: [action-provider-registry.plan.md](../plans/action-provider-registry.plan.md)
