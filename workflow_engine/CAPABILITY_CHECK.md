# Workflow Engine Capability Check (SQL-only, PCa3-oriented)

This document maps the workflow "language" (tree control flow, remote worker tasks, variables/scopes, loop indices, assignments) to **`wf`** schema objects in [sql/MethylPipeline.sql](sql/MethylPipeline.sql) and notes gaps for running a project like `project_PCa3.json`.

**Runtime target:** pure T-SQL stored procedures (no Delphi `WfEngineSrv`).

---

## 1. Supported today (SQL)

### 1.1 Tree control flow

| Concept | Schema object | Notes |
|---------|---------------|-------|
| Workflow definition | `wf.workflow_def`, `wf.workflow_version` | Versioned; `root_node_id` points at tree root |
| Node kinds | `wf.workflow_node.node_type` | CHECK: `ACTION`, `SEQUENCE`, `PARALLEL`, `IF`, `SWITCH`, `REPEAT`, `WHILE` (~line 197) |
| Parent/child + order | `wf.workflow_edge` | `child_order`, `branch_kind` (`SEQUENCE`, `PARALLEL`, `THEN`, `ELSE`, `CASE`, `DEFAULT`, `BODY`) |
| Instance run | `wf.workflow_instance` | `status`, `context_json`, timestamps |
| Per-node runtime | `wf.node_execution` | `status`, `input_json`, `output_json`, `result_code`, parent/iteration |

**Activation / continuation:** `wf.wf_engine_activate`, `wf.wf_sequence_continue`, `wf.wf_parallel_continue`, `wf.wf_repeat_continue`, `wf.wf_while_continue`, `wf.wf_engine_on_composite_complete`, `wf.wf_engine_on_action_complete`.

Branch parity (scope variables for IF/SWITCH/WHILE): [sql/wf_sql_branch_parity.sql](sql/wf_sql_branch_parity.sql).

### 1.2 Remote worker tasks

| Concept | Schema object |
|---------|---------------|
| Action catalog | `wf.workflow_action` (`action_name`, `capability`, `payload_schema_ref`) |
| Input template | `wf.workflow_input_template.template_json` with `${...}` placeholders |
| Input bindings | `wf.workflow_input_binding` (`target_json_path`, `source_expr`) |
| Worker poll/claim | `wf.sp_worker_request_task` → `node_execution` WHERE `status = READY` |
| Worker complete | `wf.sp_worker_submit_result` → `wf.wf_engine_on_action_complete` |
| Lease | `wf.task_lease` |

Placeholder resolution (read-path): `wf.wf_resolve_token`, `wf.wf_resolve_placeholders`, `wf.wf_build_input_json_for_action` ([sql/wf_sql_runtime_parity.sql](sql/wf_sql_runtime_parity.sql)).

Supported token families:

- `${ctx.iterationNo}`, `${ctx.sequenceIndex}`, `${ctx.parallelIndex}`, `${ctx.parent.resultCode}`
- `${ctx.task.<node_key>.resultCode}`, `${ctx.task.<node_key>.output.<path>}`
- `${var.<name>}` (scope walk via `wf.wf_get_scope_variable_json`)

### 1.3 Variables and scopes (read-path)

| Concept | Schema object |
|---------|---------------|
| Global variables | `wf.scope_variable` at `scope_node_execution_id = 0` |
| Instance bootstrap | `workflow_instance.context_json` → `wf.wf_init_instance_scope_from_context` |
| Scope-local vars | Same table; `scope_node_execution_id` = composite `node_execution.id` |
| Scope defaults (definition) | `wf.node_scope_default` (`var_name`, `default_expr`) |
| Output → variable (definition) | `wf.variable_output_binding` (`source_kind`: `result_code` \| `output_path`) |

Scope read walk: [sql/wf_monte_carlo_support.sql](sql/wf_monte_carlo_support.sql) (`wf.wf_get_scope_variable_json` / `_int`).

### 1.4 Loop index

| Concept | Mechanism |
|---------|-----------|
| REPEAT / WHILE iteration | `${ctx.iterationNo}` in `wf.execution_context` (seeded by `wf.wf_seed_execution_context`) |
| Fixed-count loop | `wf.workflow_node.repeat_count` + `wf.loop_state` |

---

## 2. Gaps closed by this milestone

| Gap | Fix |
|-----|-----|
| Output bindings not applied on task complete | [sql/wf_sql_scope_writepath_parity.sql](sql/wf_sql_scope_writepath_parity.sql): `wf.wf_apply_output_bindings` called from `wf.wf_engine_on_action_complete` |
| Scope defaults not applied when composite opens | Same script: `wf.wf_open_scope` called from `wf.wf_engine_activate` for composite nodes |
| ACTION under PARALLEL needs isolated scope copy | Same script: scope copy on ACTION activation when parent is `PARALLEL` |

Deploy **after** `wf_sql_runtime_parity.sql` and `wf_sql_branch_parity.sql`.

---

## 3. Remaining gaps (scale-up)

| Gap | Impact on PCa3 |
|-----|------------------|
| No `FOREACH` node type | Per-chromosome fan-out requires **static** node generation at seed time (see [sql/wf_pca_two_group_seed.sql](sql/wf_pca_two_group_seed.sql)) |
| No array indexing in placeholders (`var.list[idx]`) | Cannot select i-th chromosome from a JSON array in templates |
| No expression language in `${...}` | No `(`, `+`, spaces in tokens |
| `payload_schema_ref` is external only | Worker validates JSON shape; DB does not enforce JSON Schema |
| Detector has no `--chromosome` CLI flag | Single-chromosome worker runs need `step-override` with `"chromosome": ["N"]` |

See [sql/wf_foreach_design.md](sql/wf_foreach_design.md) for the proposed `FOREACH` enhancement.

---

## 4. PCa3 pipeline mapping (high level)

| Pipeline step | Worker capability | Milestone 1 |
|---------------|-------------------|-------------|
| Centroid per group | `methyl-centroid` | `pca.centroid` ACTION per (group, chromosome) |
| Detection per comparison | `methyl-detector` | `pca.detector` ACTION per chromosome (after both centroids) |
| Mapper / enricher / model | various | Out of scope for milestone 1; see [workflow_methylvalidation_seed.sql](sql/workflow_methylvalidation_seed.sql) |

**Milestone 1 workflow:** `PCaTwoGroupFlow` — one control vs one disease group, 24 chromosomes, parallel by chromosome. See [sql/wf_worker_contracts_pca_two_group.md](sql/wf_worker_contracts_pca_two_group.md).

---

## 5. Deployment order (workflow engine scripts)

1. `MethylPipeline.sql` (or base `wf` schema)
2. `wf_scope_variables.sql`
3. `wf_monte_carlo_support.sql`
4. `wf_sql_runtime_parity.sql`
5. `wf_sql_branch_parity.sql`
6. **`wf_sql_scope_writepath_parity.sql`** (write-path parity)
7. `wf_pca_two_group_seed.sql`
8. `wf_pca_two_group_run_example.sql` (validation)

---

## 6. Engine error codes (reference)

| Code | Meaning |
|------|---------|
| 10001 | Missing placeholder / scope / context |
| 10002 | Unsupported placeholder expression |
| 10003 | Missing IF branch |
| 10004 | Missing SWITCH case |
| 10005 | Missing REPEAT body |
| 10006 | Missing WHILE body |
| 10007 | Missing loop_state for REPEAT |
| 10008 | Invalid JSON after template resolution |

Negative `result_code` from workers → instance `FAILED`.
