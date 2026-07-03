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

The database does **not** encode methylation semantics. Action names, capabilities, and JSON schemas are **data rows** seeded from git; the engine never branches on pipeline meaning in SQL.

**Config resolution at instance time:** Admin tooling (portal, `methyl-study-start`) calls `finalize_instance_context()` before `create_workflow_instance`, baking `resolvedConfig__<action_config_key>` scope variables. The SQL read-path binds these into action input templates — workers receive fully-resolved payloads without gateway enrichment.

## REST gateway (`methyl-gateway`)

The gateway is a **stateless REST passthrough** between compute workers and the database:

| Allowed | Forbidden |
|---------|-----------|
| Worker auth, claim, submit, heartbeat, fail | Reading `schemas/actions/catalog.json` |
| Admin catalog seed (opaque JSON upserts) | `materialize_action_input` / config merge at claim |
| Deploy compiled `WorkflowDefinitionSpec` | DomainProgram compile, validation/sample-prep planners |
| Generic create/start/get instance (pre-built `context_json`) | Study-specific lifecycle routes |

**Identities:**

- **Worker** — `POST /v1/workers/*` with `worker_id` + `worker_token`
- **Admin / CI** — `POST /v1/admin/*` with Entra `WorkflowEngineAdmin` or bearer token

EpiPortal **never** calls the gateway; it uses Azure SQL `portal.sp_*` directly.

## Admin tooling (domain-aware, outside gateway)

| Tool | Role |
|------|------|
| **`methyl-study-start`** | Compile DomainPrograms, plan/enrich context, finalize resolvedConfig, create/start instances via DB |
| **`scripts/deploy_workflow_definitions.sh`** | POST compiled workflow specs to admin gateway |
| **`seed_action_catalog.py`** | Upsert action catalog + dispatch metadata into `wf.workflow_action` |
| **`methyl-workflow-run`** | Local in-process runs (no database) |

## Compute workers

Workers poll the gateway (or future equivalent transport), execute tasks, and submit results. They:

- Authenticate with worker credentials only
- Consume `input_json` including `resolvedConfig` as produced by the DB engine
- Never connect to SQL directly
- Never use MCP

## MCP servers (development only)

Cursor MCP servers (`user-azure-sql-dev`, PostgreSQL MCP) are **operator/dev tooling**:

- Inspection, parity checks, surgical SQL during development
- **Not** part of worker runtime, gateway data plane, or production automation

Bulk catalog seed and workflow deploy use scripts or the admin gateway API — not MCP.

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
- [portal_study_lifecycle.md](../../workflow_engine/docs/portal_study_lifecycle.md) — portal staged starts
- Plan: [agnostic-gateway-and-boundaries.plan.md](../plans/agnostic-gateway-and-boundaries.plan.md)
