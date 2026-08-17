# Workflow Engine — Implementation

Internal map for `workflow_engine/`: gateway, database client, scheduler, and DomainProgram integration.

## Entry points

| CLI / service | Module area |
|---------------|-------------|
| `methyl-workflow-run` | `workflow_engine/local/` |
| `methyl-gateway` | `workflow_engine/rest/` |
| `methyl-export-task-schemas` | schema export from Pydantic models |
| `methyl-export-action-catalog` | action catalog for DB + editor |

## Gateway (`workflow_engine/rest/`)

- Uvicorn app exposing `/v1/*` per [`contracts/openapi.yaml`](../../contracts/openapi.yaml)
- Repository layer wraps SQL/PostgreSQL stored procedures
- Stateless — all workflow state in DB

## Database client

- Dual backend: Azure SQL (`workflow_engine/sql_mssql/`) and PostgreSQL (`workflow_engine/sql_pg/`)
- JSON-native params via `wf_json_native_params.sql`
- FOREACH / PARALLEL scope encoding: `wf_sql_foreach_support.sql`, `wf_sql_scope_encoding_parity.sql`

## Local engine (`workflow_engine/local/`)

- Executes compiled graphs without worker poll loop
- Same action catalog dispatch as workers
- Used for CI checks and developer iteration

## Domain layer (`workflow_engine/domain/`)

- `compiler.py` — DomainProgram → deploy spec
- `profiles/` — reusable actionConfig packs
- `fixtures/` — SamplePrep and reference programs
- `checks/` — study-specific program variants

## Diagrams

- Architecture deep dive: [`pipeline_architecture.md`](pipeline_architecture.md) (inline Mermaid)
- Shared assets: [`docs/diagrams/`](../../docs/diagrams/)

## Related docs

- [Implementation guide (docs)](../../docs/implementation/index.md)
- [Architecture](../../docs/architecture/index.md)
- [Delphi runtime notes](../delphi/WORKFLOW_ENGINE_DELPHI.md)
