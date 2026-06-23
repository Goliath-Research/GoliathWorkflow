# SQL Server Workflow Engine scripts

Delphi runtime implementation notes and control-flow walkthrough: [`WORKFLOW_ENGINE_DELPHI.md`](WORKFLOW_ENGINE_DELPHI.md)

**Azure SQL / bundled engine (`wf` schema):** use [`MethylPipeline_202604291041.sql`](MethylPipeline_202604291041.sql) as the single deploy script. It defines clusters, registered workers (`wf.worker`), bearer tokens (`wf.worker_token`), native `JSON` payload columns, and worker procedures that require `@worker_id BIGINT` (from `wf.worker.id`) plus `@worker_token`.

---

Run scripts **in this order** on a database (SQL Server 2017+ recommended for `JSON_*` functions) — legacy **dbo** layout:

1. [`workflow_definition.sql`](workflow_definition.sql) — definitions (workflows, nodes, edges, templates/bindings).
2. [`workflow_runtime.sql`](workflow_runtime.sql) — instances, executions, leases, loop state.
3. [`workflow_constraints_indexes.sql`](workflow_constraints_indexes.sql) — extra indexes/constraints.
4. [`workflow_worker_api.sql`](workflow_worker_api.sql) — functions + stored procedures (`sp_worker_request_task`, `sp_worker_submit_result`, engine activation).
5. [`workflow_seed_examples.sql`](workflow_seed_examples.sql) — optional demo workflow (`DemoFlow`).
6. [`workflow_tree_seed_example.sql`](workflow_tree_seed_example.sql) — optional tree workflow (`DelphiTreeFlow`) matching Delphi runtime walkthrough.
7. [`workflow_tree_run_example.sql`](workflow_tree_run_example.sql) — optional end-to-end claim/submit simulation loop for `DelphiTreeFlow`.
8. [`wf_scope_readpath.sql`](wf_scope_readpath.sql) — scope variable read-path helpers (`wf_get_scope_variable_json/int`).
8a. [`wf_instance_extension.sql`](wf_instance_extension.sql) — generic optional instance extension storage (json/jsonb).
8b. [`wf_json_column_alignment.sql`](wf_json_column_alignment.sql) — migrate scope/context JSON columns to native types.
8c. [`wf_drop_monte_carlo_tables.sql`](wf_drop_monte_carlo_tables.sql) — remove deprecated `wf.monte_carlo_*` tables.
9. [`wf_sql_branch_parity.sql`](wf_sql_branch_parity.sql) — SQL IF/SWITCH/WHILE variable-branch parity (`condition_var`/`switch_var`) with Delphi runtime behavior.
10. [`workflow_methylvalidation_seed.sql`](workflow_methylvalidation_seed.sql) — **deprecated** MethylValidationFlow (use ValidationPipeline).
10a. [`wf_validation_pipeline_seed.sql`](wf_validation_pipeline_seed.sql) — **ValidationPipeline** (FOREACH over `iterations[]`).
11. [`wf_sql_runtime_parity.sql`](wf_sql_runtime_parity.sql) — SQL-only parity for scope init from context and `${var.*}` resolution.
12. [`wf_sql_scope_writepath_parity.sql`](wf_sql_scope_writepath_parity.sql) — SQL write-path parity: `wf_apply_output_bindings`, `wf_open_scope`, scope copy for PARALLEL children.
13. [`wf_sp_delete_workflow_def.sql`](wf_sp_delete_workflow_def.sql) — `sp_delete_workflow_def`: remove a workflow definition (and instances) so seed scripts can be re-run.
14. [`wf_sql_foreach_support.sql`](wf_sql_foreach_support.sql) — **FOREACH** control-flow node, parallel mode, `${var.name[n]}`, `${ctx.item}`.
14a. [`wf_sql_scope_encoding_parity.sql`](wf_sql_scope_encoding_parity.sql) — canonical JSON-value encoding (`wf_json_encode_scalar/openjson`); fixes integer-as-string write-path inconsistency. Deploy immediately after `wf_sql_foreach_support.sql`.
15. [`wf_repository_api.sql`](wf_repository_api.sql) — middle-tier repository wrappers (dual-database contract).
15a. [`wf_json_native_params.sql`](wf_json_native_params.sql) — native `json` params for engine/worker submit (deploy before worker contract refresh).
15b. [`wf_workflow_edge_index_fixup.sql`](wf_workflow_edge_index_fixup.sql) — drop `UQ_we_parent_child_order` (required before programmatic IF workflow deploy).
15c. [`wf_cluster_security_columns.sql`](wf_cluster_security_columns.sql) — cluster `allowed_source_cidrs`, `entra_client_id`, and `arc_resource_id` for gateway tiered auth.
15d. [`wf_cluster_arc_resource_id.sql`](wf_cluster_arc_resource_id.sql) — idempotent add of `arc_resource_id` when upgrading older deployments.
15e. [`wf_platform_sample_storage.sql`](wf_platform_sample_storage.sql) — platform long-term sample object storage (myQNAPcloud / S3-compatible).
16. [`wf_worker_api_contract.sql`](wf_worker_api_contract.sql) — worker submit result-set contract alignment.
17. [`wf_data_driven_pipeline_seed.sql`](wf_data_driven_pipeline_seed.sql) — **DataDrivenPipeline** (generic; instance `context_json` drives fan-out).
17a. [`wf_sample_prep_pipeline_seed.sql`](wf_sample_prep_pipeline_seed.sql) — **SamplePrepPipeline** (per-sample FASTQ → HDF5 upstream).
17b. [`wf_action_schema.sql`](wf_action_schema.sql) — `workflow_action_schema` table + repo procs for action I/O JSON Schemas.
16. [`wf_pca_two_group_seed.sql`](wf_pca_two_group_seed.sql) — **deprecated** static PCaTwoGroupFlow.
17. [`wf_pca_ovr_seed.sql`](wf_pca_ovr_seed.sql) — **deprecated** static PCaOvrFlow.
18. [`wf_pca_two_group_run_example.sql`](wf_pca_two_group_run_example.sql) — optional simulation for legacy seed.

See also: [CAPABILITY_CHECK.md](CAPABILITY_CHECK.md), [sql/DataDrivenPipeline.md](sql/DataDrivenPipeline.md), [sql/SamplePrepFlow.md](sql/SamplePrepFlow.md), [docs/pipeline_architecture.md](docs/pipeline_architecture.md) (Quarto HTML/PDF: [docs/pipeline_architecture.qmd](docs/pipeline_architecture.qmd)), [contract/db_objects.md](contract/db_objects.md), [contract/sample_prep_capabilities.md](contract/sample_prep_capabilities.md), [sql_pg/README.md](sql_pg/README.md), [../contracts/openapi.yaml](../contracts/openapi.yaml), [../workers/WORKER_PROTOCOL.md](../workers/WORKER_PROTOCOL.md), [sql/wf_foreach_design.md](sql/wf_foreach_design.md), [sql/instance_context_examples/pca_ovr.json](sql/instance_context_examples/pca_ovr.json), [sql/instance_context_examples/sample_prep_plasma.json](sql/instance_context_examples/sample_prep_plasma.json).

To redeploy from scratch, drop runtime tables before re-running `workflow_definition.sql` if `workflow_instance` exists (it references `workflow_version`). Example:

```sql
DROP TABLE IF EXISTS dbo.execution_context;
DROP TABLE IF EXISTS dbo.task_lease;
DROP TABLE IF EXISTS dbo.loop_state;
DROP TABLE IF EXISTS dbo.instance_cursor;
DROP TABLE IF EXISTS dbo.node_execution;
DROP TABLE IF EXISTS dbo.workflow_instance;
-- then run scripts 1–5 again
```

## Worker API (summary)

### `wf` schema (`MethylPipeline_*.sql`)

| Procedure | Purpose |
|-----------|---------|
| `wf.sp_start_workflow_instance @workflow_instance_id` | Move instance to `RUNNING` and expand the workflow graph from `root_node_id`. |
| `wf.sp_worker_request_task @worker_id BIGINT, @worker_token NVARCHAR(4000), @capability, @max_lease_seconds` | Authenticates registered worker; atomically claims one `READY` action row (returns 0 or 1 row). |
| `wf.sp_worker_submit_result @node_execution_id, @worker_id BIGINT, @worker_token, @result_code, @output_json NVARCHAR(MAX), ... OUTPUT` | Validates lease + token; advances control flow. Use `@result_code < 0` to fail the instance. Payload must be valid JSON text (stored in `json` columns via explicit cast). |
| `wf.sp_worker_heartbeat` / `wf.sp_worker_fail_task` | Lease renewal and explicit failure (same `@worker_id` / `@worker_token`). |
| `wf.sp_delete_workflow_def @workflow_name` or `@workflow_def_id` | Remove a workflow definition (optional instance purge) so seed scripts can be re-run. |

Tokens are verified against `HASHBYTES('SHA2_256', @worker_token)` rows in `wf.worker_token` (portal must register workers and issue secrets before polling).

### Legacy dbo scripts (`workflow_worker_api.sql`)

| Procedure | Purpose |
|-----------|---------|
| `sp_start_workflow_instance @workflow_instance_id` | Move instance to `RUNNING` and expand the workflow graph from `root_node_id`. |
| `sp_worker_request_task @worker_id, @capability, @max_lease_seconds` | Atomically claims one `READY` action row (returns 0 or 1 row). |
| `sp_worker_submit_result @node_execution_id, @worker_id, @result_code, @output_json, ... OUTPUT` | Applies completion; advances control flow. Use `@result_code < 0` to fail the instance. |
| `sp_worker_heartbeat` / `sp_worker_fail_task` | Lease renewal and explicit failure. |

## Placeholders

Templates use `${...}` tokens only. Supported references include `ctx.iterationNo`, `ctx.sequenceIndex`, `ctx.parallelIndex`, `ctx.parent.resultCode`, and `ctx.task.<node_key>.resultCode` / `ctx.task.<node_key>.output.<path>`.

## REST middle-tier

OpenAPI contract: [`../contracts/openapi.yaml`](../contracts/openapi.yaml)

Install the production gateway package:

```bash
source .venv/bin/activate
pip install -e workflow_engine/
```

Python REST worker (poll/submit): [`../workers/WORKER_PROTOCOL.md`](../workers/WORKER_PROTOCOL.md) — install with `pip install -e workers/`, run `methyl-worker`.

| Implementation | Command | Backend |
|----------------|---------|---------|
| **Python (production)** | `methyl-gateway` via systemd on a dedicated Linux VM; dev: `python workflow_engine/rest/gateway.py` | Azure SQL (`BACKEND_DB=mssql`) or PostgreSQL (`BACKEND_DB=postgres`) via psycopg/pyodbc |
| Delphi (frozen reference / Windows) | `WfEngineSrv` / `MethylWfGateway` — manual Win64 build only; see [`DELPHI_GATEWAY_STATUS.md`](DELPHI_GATEWAY_STATUS.md) | UniDAC → Azure SQL or PostgreSQL (`BACKEND_DB`) |

PostgreSQL parity scripts (`sql_pg/05`–`07`) port runtime resolver, scope write-path, and JSON encoding from the T-SQL parity scripts. FOREACH (`wf_sql_foreach_support.sql`) remains MSSQL-only for now.

Parity harness: `python workflow_engine/tests/parity/run_parity.py` (requires `psql` + Postgres 17).

### Action payload schemas

After deploying `wf_action_schema.sql`:

```bash
source .venv/bin/activate
methyl-export-task-schemas              # writes schemas/tasks/*.schema.json
methyl-export-task-schemas --check      # CI drift gate
python workflow_engine/sql/seed_action_schemas.py
```

Gateway routes: `GET /v1/actions`, `GET /v1/actions/{action_name}/schema?direction=input|output` ([`contracts/openapi.yaml`](../contracts/openapi.yaml)). The Config Editor fetches these when `[Gateway] Enabled=true` in its INI file.
