# MethylPipeline DB Object Contract

Canonical contract for middle-tier-to-database access. Both **Azure SQL (T-SQL)** and **PostgreSQL (PL/pgSQL)** must implement every object listed in [`db_objects.yaml`](db_objects.yaml) with identical semantics.

## Schema

All workflow-engine objects live in schema **`wf`**. Domain/portal objects may use `dbo`, `Meta`, `RBAC`, `portal`, etc. (Azure SQL only until ported).

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

Dialect-neutral wrappers used by `WfEngine.Repository` — see `db_objects.yaml` `repository` section.

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

Registered by [`../sql/wf_sample_prep_pipeline_seed.sql`](../sql/wf_sample_prep_pipeline_seed.sql). Full I/O contract: [`sample_prep_capabilities.md`](sample_prep_capabilities.md).

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
