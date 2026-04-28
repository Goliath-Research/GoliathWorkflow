# SQL Server Workflow Engine scripts

Run scripts **in this order** on a database (SQL Server 2017+ recommended for `JSON_*` functions):

1. [`workflow_definition.sql`](workflow_definition.sql) — definitions (workflows, nodes, edges, templates/bindings).
2. [`workflow_runtime.sql`](workflow_runtime.sql) — instances, executions, leases, loop state.
3. [`workflow_constraints_indexes.sql`](workflow_constraints_indexes.sql) — extra indexes/constraints.
4. [`workflow_worker_api.sql`](workflow_worker_api.sql) — functions + stored procedures (`sp_worker_request_task`, `sp_worker_submit_result`, engine activation).
5. [`workflow_seed_examples.sql`](workflow_seed_examples.sql) — optional demo workflow (`DemoFlow`).

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

| Procedure | Purpose |
|-----------|---------|
| `sp_start_workflow_instance @workflow_instance_id` | Move instance to `RUNNING` and expand the workflow graph from `root_node_id`. |
| `sp_worker_request_task @worker_id, @capability, @max_lease_seconds` | Atomically claims one `READY` action row (returns 0 or 1 row). |
| `sp_worker_submit_result @node_execution_id, @worker_id, @result_code, @output_json, ... OUTPUT` | Applies completion; advances control flow. Use `@result_code < 0` to fail the instance. |
| `sp_worker_heartbeat` / `sp_worker_fail_task` | Lease renewal and explicit failure. |

## Placeholders

Templates use `${...}` tokens only. Supported references include `ctx.iterationNo`, `ctx.sequenceIndex`, `ctx.parallelIndex`, `ctx.parent.resultCode`, and `ctx.task.<node_key>.resultCode` / `ctx.task.<node_key>.output.<path>`.
