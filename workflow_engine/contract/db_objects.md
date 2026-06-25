# MethylPipeline DB Object Contract

Canonical contract for middle-tier-to-database access. Both **Azure SQL (T-SQL)** and **PostgreSQL (PL/pgSQL)** must implement every object listed in [`db_objects.yaml`](db_objects.yaml) with identical semantics.

## Schema

All workflow-engine objects live in schema **`wf`**. Domain/portal objects may use `dbo`, `Meta`, `RBAC`, `portal`, etc. (Azure SQL only until ported). **Do not add process-specific config tables to `wf`** — use `portal.resource_profile` or pass fully materialized JSON in `context_json`.

## Portability conventions

### Identity columns

| Azure SQL | PostgreSQL |
|-----------|------------|
| `BIGINT IDENTITY(1,1)` | `BIGINT GENERATED ALWAYS AS IDENTITY` |
| `OUTPUT INSERTED.id` | `RETURNING id` into result set |

Repository and worker procs that insert rows **return the new id as a single-column result set** named `id`.

### Timestamps

| Azure SQL | PostgreSQL |
|-----------|------------|
| `SYSUTCDATETIME()` | `(now() AT TIME ZONE 'utc')` or `now()` with `timestamptz` |
| `DATETIME2(7)` | `timestamptz` |

### JSON

| Azure SQL | PostgreSQL |
|-----------|------------|
| `json` | `jsonb` |
| `OPENJSON` / `FOR JSON` | `jsonb_each`, `jsonb_array_elements`, `jsonb_path_query` |
| `JSON_VALUE` / `JSON_QUERY` | PG17+ standard `JSON_VALUE` / `JSON_QUERY` where applicable |

**Policy:** JSON **storage** columns use native `json` (MSSQL) / `jsonb` (PostgreSQL) only — never `NVARCHAR(MAX)` or plain `text` for payload columns. Procs may use string variables at the wire boundary; writes cast to native JSON types.

### Procedure results (not OUTPUT parameters)

Legacy T-SQL uses `@accepted BIT OUTPUT` on `sp_worker_submit_result`. The contract uses a **single-row result set** instead:

| Column | Type | Description |
|--------|------|-------------|
| `accepted` | boolean | Task accepted |
| `instance_status` | varchar(32) | Instance status after submit |
| `next_ready_count` | int | Count of READY tasks remaining |

Both dialects implement `wf.sp_worker_submit_result` returning this row. T-SQL may retain OUTPUT params for backward compatibility but middle-tier reads the result set.

### Worker authentication

Token verification: `SHA2_256` hash of bearer token compared to `wf.worker_token.token_hash`.

- Azure SQL: `HASHBYTES('SHA2_256', @worker_token)`
- PostgreSQL: `encode(digest(@worker_token, 'sha256'), 'hex')` (pgcrypto)

### Error codes

Engine errors use integer codes documented in worker API scripts (e.g. `10001` missing binding, `50001` no root node).

## Object categories

### 1. Worker API (required for remote execution)

| Object | Kind | Purpose |
|--------|------|---------|
| `wf.wf_worker_authenticate` | procedure | Validate worker id + token |
| `wf.sp_worker_request_task` | procedure | Claim one READY action; returns task row or empty |
| `wf.sp_worker_submit_result` | procedure | Complete action; returns ack row |
| `wf.sp_worker_heartbeat` | procedure | Extend lease; returns `rows_updated` |
| `wf.sp_worker_fail_task` | procedure | Fail task and instance |
| `wf.sp_start_workflow_instance` | procedure | Start instance and activate root |

### 2. Repository API (middle-tier persistence)

Dialect-neutral wrappers used by the REST gateway — see `db_objects.yaml` `repository` section.

| Object | Purpose |
|--------|---------|
| `wf.wf_repo_upsert_action_schema` | Upsert input/output JSON Schema for a workflow action |
| `wf.wf_repo_get_action_schema` | Fetch one schema document by action name + direction |
| `wf.wf_repo_list_actions` | List actions with schema availability flags |
| `wf.wf_repo_upsert_workflow_action` | Upsert `wf.workflow_action` row from action catalog |
| `wf.wf_repo_create_workflow_graph` | Create workflow def/version/nodes/edges from JSON spec |
| `wf.wf_repo_get_workflow_instance` | Fetch instance id, version, and status by instance id |
| `wf.wf_repo_create_workflow_instance` | Insert instance row; returns `id` |

Action schemas are generated from worker Pydantic models (`methyl-export-task-schemas` → `schemas/tasks/`) and seeded via [`../sql/seed_action_catalog.py`](../sql/seed_action_catalog.py) using the **admin gateway** (`POST /v1/admin/catalog/seed`) or direct DB in dev. Runtime validation is enforced in workers; portal graph create rejects unknown actions in SQL.

### 2a. Portal repository API (EpiPortal — database only)

Deploy [`../sql/portal_workflow_api.sql`](../sql/portal_workflow_api.sql) (Azure SQL) or [`../sql_pg/portal_workflow_api.sql`](../sql_pg/portal_workflow_api.sql) (PostgreSQL). The portal **never** calls the REST gateway.

| Object | Purpose |
|--------|---------|
| `portal.sp_list_workflow_actions` | Action picker for workflow builder |
| `portal.sp_get_action_schema` | Schema-driven parameter forms |
| `portal.sp_list_workflow_definitions` | List defs (filter `source` = `portal` or `system`) |
| `portal.sp_create_workflow_graph` | Create portal-owned workflow graph; validates actions exist |
| `portal.sp_create_and_start_instance` | Create instance + `sp_start_workflow_instance` |
| `portal.sp_get_instance_tasks` | Monitor node executions for results panel |

Portal principals must not execute `wf.wf_repo_upsert_workflow_action` or admin delete procs. Catalog seed and system pipeline deploy use the **admin gateway** (`/v1/admin/*`) from CI/release automation.

### 3. Engine runtime (SQL-only activation path)

Used when middle-tier delegates graph expansion to SQL (`wf_engine_activate` path):

| Object | Purpose |
|--------|---------|
| `wf.wf_engine_activate` | Expand node into executions |
| `wf.wf_engine_on_action_complete` | Apply result and continue parent |
| `wf.wf_engine_continue_parent` | Parent composite continuation |
| `wf.wf_resolve_token` | Resolve `${...}` placeholder |
| `wf.wf_init_instance_scope_from_context` | Seed scope from `context_json` |
| `wf.wf_set_scope_variable` | Write scope variable |
| `wf.wf_get_scope_variable_json` | Read scope variable |
| `wf.wf_get_scope_variable_int` | Read scope variable as int |

Control-flow helpers: `wf_sequence_continue`, `wf_parallel_continue`, `wf_repeat_continue`, `wf_while_continue`, FOREACH procs.

### 4. Admin

| Object | Purpose |
|--------|---------|
| `wf.sp_delete_workflow_def` | Remove definition (+ optional instances) |

### 5. Domain (optional, Azure SQL today)

| Object | Purpose |
|--------|---------|
| `dbo.spMapDMP2Genes` | Map DMPs to genes (methyl-mapper) |

### 6. Workflow action catalog (SamplePrepPipeline)

Registered by DomainProgram deploy ([`sample_prep.program.json`](../domain/fixtures/sample_prep.program.json) via `scripts/deploy_workflow_definitions.sh`). Legacy SQL seed: [`../sql/deprecated/wf_sample_prep_pipeline_seed.sql`](../sql/deprecated/wf_sample_prep_pipeline_seed.sql). Full I/O contract: [`sample_prep_capabilities.md`](sample_prep_capabilities.md).

| action_name | capability |
|-------------|------------|
| `sample.download_fastq` | `sample.download-fastq` |
| `sample.parabricks_fq2bam` | `parabricks.fq2bam` |
| `sample.delete_fastqs` | `sample.delete-fastqs` |
| `sample.methyl_qc` | `methyl-qc` |
| `sample.fragmentomics` | `methyl-fragmentomics` |
| `sample.methyl_extract` | `methyl-extract` |
| `sample.delete_bam` | `sample.delete-bam` |
| `sample.qc_failed` | `sample.mark-failed` |

DataDrivenPipeline actions (`pipeline.centroid`, `pipeline.detector`, …) are registered in [`../sql/wf_data_driven_pipeline_seed.sql`](../sql/wf_data_driven_pipeline_seed.sql).

## Deployment order

### Azure SQL

See [`../README.md`](../README.md).

### PostgreSQL

See [`../sql_pg/README.md`](../sql_pg/README.md).

## Contract validation

Run from repo root:

```bash
python workflow_engine/contract/validate_contract.py
```

Fails if an object in `db_objects.yaml` is missing from either `sql/` or `sql_pg/` deploy scripts.
