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
8. [`wf_monte_carlo_support.sql`](wf_monte_carlo_support.sql) — Monte Carlo plan/run metadata tables for Delphi middle-tier orchestration.
9. [`wf_sql_branch_parity.sql`](wf_sql_branch_parity.sql) — SQL IF/SWITCH/WHILE variable-branch parity (`condition_var`/`switch_var`) with Delphi runtime behavior.
10. [`workflow_methylvalidation_seed.sql`](workflow_methylvalidation_seed.sql) — explicit MethylValidation workflow seed (MC centroid/detector loop + post-loop centroid/detector/mapper/enricher/disease progression).
11. [`wf_sql_runtime_parity.sql`](wf_sql_runtime_parity.sql) — SQL-only parity for scope init from context, `${var.*}` resolution, and `mc.taskConfig` payload injection.
12. [`wf_sql_scope_writepath_parity.sql`](wf_sql_scope_writepath_parity.sql) — SQL write-path parity: `wf_apply_output_bindings`, `wf_open_scope`, scope copy for PARALLEL children.
13. [`wf_pca_two_group_seed.sql`](wf_pca_two_group_seed.sql) — PCaTwoGroupFlow: per-chromosome centroid+detection fan-out (milestone 1).
14. [`wf_pca_two_group_run_example.sql`](wf_pca_two_group_run_example.sql) — End-to-end worker simulation + assertions for PCaTwoGroupFlow.

See also: [CAPABILITY_CHECK.md](CAPABILITY_CHECK.md), [sql/wf_worker_contracts_pca_two_group.md](sql/wf_worker_contracts_pca_two_group.md), [sql/wf_foreach_design.md](sql/wf_foreach_design.md).

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
