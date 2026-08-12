# Workflow Engine Capability Check (SQL-only, PCa3-oriented)

This document maps the workflow "language" (tree control flow, remote worker tasks, variables/scopes, loop indices, assignments) to **`wf`** schema objects in [sql_mssql/MethylPipeline.sql](sql_mssql/MethylPipeline.sql) and notes gaps for running a project like `project_PCa3.json`.

**Runtime target:** pure T-SQL stored procedures (no Delphi `WfEngineSrv`).

---

## 1. Supported today (SQL)

### 1.1 Tree control flow

| Concept | Schema object | Notes |
|---------|---------------|-------|
| Workflow definition | `wf.workflow_def`, `wf.workflow_version` | Versioned; `root_node_id` points at tree root |
| Node kinds | `wf.workflow_node.node_type` | CHECK: `ACTION`, `SEQUENCE`, `PARALLEL`, `IF`, `SWITCH`, `REPEAT`, `WHILE`, **`FOREACH`** |
| Parent/child + order | `wf.workflow_edge` | `child_order`, `branch_kind` (`SEQUENCE`, `PARALLEL`, `THEN`, `ELSE`, `CASE`, `DEFAULT`, `BODY`) |
| Instance run | `wf.workflow_instance` | `status`, `context_json`, timestamps |
| Per-node runtime | `wf.node_execution` | `status`, `input_json`, `output_json`, `result_code`, parent/iteration |

**Activation / continuation:** `wf.wf_engine_activate`, `wf.wf_sequence_continue`, `wf.wf_parallel_continue`, `wf.wf_repeat_continue`, `wf.wf_while_continue`, `wf.wf_engine_on_composite_complete`, `wf.wf_engine_on_action_complete`.

Branch parity (scope variables for IF/SWITCH/WHILE): [sql_mssql/wf_sql_branch_parity.sql](sql_mssql/wf_sql_branch_parity.sql).

### 1.2 Remote worker tasks

| Concept | Schema object |
|---------|---------------|
| Action catalog | `wf.workflow_action` (`action_name`, `capability`, `payload_schema_ref`) |
| Action I/O types | `wf.workflow_action.input_type_id` / `output_type_id` → `wf.data_type` (+ fields); legacy `wf.workflow_action_schema` read-compat only |
| Input template | `wf.workflow_input_template.template_json` with `${...}` placeholders |
| Input bindings | `wf.workflow_input_binding` (`target_json_path`, `source_expr`) |
| Worker poll/claim | `wf.sp_worker_request_task` → `node_execution` WHERE `status = READY` |
| Worker complete | `wf.sp_worker_submit_result` → `wf.wf_engine_on_action_complete` |
| Lease | `wf.task_lease` |

Placeholder resolution (read-path): `wf.wf_resolve_token`, `wf.wf_resolve_placeholders`, `wf.wf_build_input_json_for_action` ([sql_mssql/wf_sql_runtime_parity.sql](sql_mssql/wf_sql_runtime_parity.sql)).

Supported token families:

- `${ctx.iterationNo}`, `${ctx.sequenceIndex}`, `${ctx.parallelIndex}`, `${ctx.parent.resultCode}`
- `${ctx.task.<node_key>.resultCode}`, `${ctx.task.<node_key>.output.<path>}`
- `${var.<name>}` (scope walk via `wf.wf_get_scope_variable_json`)
- `${var.<array>[n]}` (indexed element from JSON array scope value)
- `${ctx.item}` / `${ctx.index}` (current FOREACH element and zero-based index)

### 1.3 Variables and scopes (read-path)

| Concept | Schema object |
|---------|---------------|
| Global variables | `wf.scope_variable` at `scope_node_execution_id = 0` |
| Instance bootstrap | `workflow_instance.context_json` → `wf.wf_init_instance_scope_from_context` |
| Scope-local vars | Same table; `scope_node_execution_id` = composite `node_execution.id` |
| Scope defaults (definition) | `wf.node_scope_default` (`var_name`, `default_expr`) |
| Output → variable (definition) | `wf.variable_output_binding` (`source_kind`: `result_code` \| `output_path`) |

Scope read walk: [sql_mssql/wf_scope_readpath.sql](sql_mssql/wf_scope_readpath.sql) (`wf.wf_get_scope_variable_json` / `_int`).

### 1.4 Loop index

| Concept | Mechanism |
|---------|-----------|
| REPEAT / WHILE iteration | `${ctx.iterationNo}` in `wf.execution_context` (seeded by `wf.wf_seed_execution_context`) |
| Fixed-count loop | `wf.workflow_node.repeat_count` + `wf.loop_state` |

---

## 2. Gaps closed by this milestone

| Gap | Fix |
|-----|-----|
| Output bindings not applied on task complete | [sql_mssql/wf_sql_scope_writepath_parity.sql](sql_mssql/wf_sql_scope_writepath_parity.sql): `wf.wf_apply_output_bindings` called from `wf.wf_engine_on_action_complete` |
| Scope defaults not applied when composite opens | Same script: `wf.wf_open_scope` called from `wf.wf_engine_activate` for composite nodes |
| ACTION under PARALLEL needs isolated scope copy | Same script: scope copy on ACTION activation when parent is `PARALLEL` |

Deploy **after** `wf_sql_runtime_parity.sql` and `wf_sql_branch_parity.sql`.

---

## 3. Remaining gaps (scale-up)

| Gap | Impact |
|-----|--------|
| ~~No `FOREACH` node type~~ | **Implemented** — [`wf_sql_foreach_support.sql`](sql_mssql/wf_sql_foreach_support.sql); generic workflow [`wf_data_driven_pipeline_seed.sql`](sql_mssql/wf_data_driven_pipeline_seed.sql) |
| ~~No array indexing in placeholders~~ | **Implemented** — `${var.name[n]}` in `wf_resolve_token` |
| No expression language in `${...}` | No `(`, `+`, spaces in tokens; object fields use FOREACH flatten or indexed arrays |
| `payload_schema_ref` is external only | Worker validates JSON shape; DB does not enforce JSON Schema |
| Detector has no `--chromosome` CLI flag | **Mitigated** — worker `DetectorCliAction` maps per-chromosome scope into `--step-override` JSON; `comparison` → `--group` |

See [sql_mssql/wf_foreach_design.md](sql_mssql/wf_foreach_design.md) for the proposed `FOREACH` enhancement (milestone 3 — data-driven full project without node explosion).

---

## 4. PCa3 pipeline mapping (high level)

### Milestone 0: Sample prep (upstream)

| Step | Worker capability | Workflow |
|------|-------------------|----------|
| Download FASTQs | `sample.download-fastq` | **SamplePrepPipeline** |
| Parabricks fq2bam | `parabricks.fq2bam` | **SamplePrepPipeline** |
| Delete FASTQs | `sample.delete-fastqs` | **SamplePrepPipeline** |
| Trim FASTQ (fastp) | `sample.trim-fastq` | **SamplePrepPipeline** (alignment remediation) |
| Alignment QC | `methyl-qc` | **SamplePrepPipeline** |
| cfDNA fragmentomics | `methyl-fragmentomics` | **SamplePrepPipeline** (cfDNA only) |
| Methyl extraction | `methyl-extract` | **SamplePrepPipeline** |
| Extraction QC | `methyl-extraction-qc` | **SamplePrepPipeline** |
| Archive HDF5 | `sample.upload-h5` | **SamplePrepPipeline** |
| Delete BAM | `sample.delete-bam` | **SamplePrepPipeline** |
| QC failed marker | `sample.mark-failed` | **SamplePrepPipeline** (optional) |

Operator guide: [sql_mssql/SamplePrepFlow.md](sql_mssql/SamplePrepFlow.md). Contract: [contract/sample_prep_capabilities.md](contract/sample_prep_capabilities.md). **Deploy workflow:** `scripts/deploy_workflow_definitions.sh` (DomainProgram fixture).

### Milestone 1–2: Analysis (downstream)

| Pipeline step | Worker capability | Milestone |
|---------------|-------------------|-----------|
| Centroid per group | `methyl-centroid` | 1 + 2 |
| Detection per comparison | `methyl-detector` | 1 + 2 |
| Mapper (all comparisons) | `methyl-mapper` | **2** ([PCaOvrFlow](sql_mssql/PCaOvrFlow.md)) |
| Enricher | `methyl-enricher` | **2** |
| Disease progression | `methyl-disease-progression` | **2** |
| MC validation loop | **ValidationPipeline** + planner | [wf_validation_pipeline_seed.sql](sql_mssql/wf_validation_pipeline_seed.sql) |
| Study validation lifecycle | **StudyValidationLifecycle** | `validation.plan_iterations` → stability → freeze → mapper/enricher/progression → `validation.model_mc` → `validation.select_best_model` → `validation.post_model_validation` |
| Portal staged start | `methyl-study-start validation-start` or `portal.sp_create_and_start_instance` | [docs/portal_study_lifecycle.md](docs/portal_study_lifecycle.md) |
| Methyl extract chrom mapping | Derived from `project.chromosomes` | `step_config.methyl_extract.contig_naming` / inline `chrom_mapping` object |
| Compiler scope bindings | `iterations`, `fixedDmpPanel`, `selectedBackend` | From `action_catalog` `domain_effects.scope_bindings` → `variable_output_binding` |

**Milestone 1:** `PCaTwoGroupFlow` — one control vs one disease, 24 chromosomes.  
**Milestone 2:** `PCaOvrFlow` — `control_vs_each_disease` (PCa_Low ∥ PCa_High), then mapper → enricher → progression.

---

## 5. Deployment order (workflow engine scripts)

1. `MethylPipeline.sql` (or base `wf` schema)
2. `wf_scope_variables.sql`
3. `wf_scope_readpath.sql`
4. `wf_json_column_alignment.sql` (migrate legacy JSON columns to native `json`)
5. `wf_instance_extension.sql`
6. `wf_drop_monte_carlo_tables.sql` (remove deprecated `wf.monte_carlo_*`)
6a. `wf_apply_validation_plan.sql` — merge planner `context_json` onto workflow instances
7. `wf_sql_runtime_parity.sql`
8. `wf_sql_branch_parity.sql`
9. **`wf_sql_scope_writepath_parity.sql`** (write-path parity)
10. **`wf_sql_foreach_support.sql`** (FOREACH node + indexed placeholders)
11. **`wf_sp_delete_workflow_def.sql`** (delete/rebuild definitions)
12. **`wf_validation_pipeline_seed.sql`** — **ValidationPipeline** (FOREACH iterations)
13. **DomainProgram deploy** — `scripts/deploy_workflow_definitions.sh` compiles [`domain/fixtures/sample_prep.program.json`](domain/fixtures/sample_prep.program.json) → **SamplePrepPipeline** (per-sample FASTQ → HDF5, two QC gates)

14. **`wf_sample_prep_pipeline_seed.sql`** — **deprecated** legacy SQL Server seed; use DomainProgram deploy above
14. **`wf_data_driven_pipeline_seed.sql`** — generic DataDrivenPipeline (preferred)
15. `wf_pca_two_group_seed.sql` / `wf_pca_ovr_seed.sql` — **deprecated** static generators
16. `workflow_methylvalidation_seed.sql` — **deprecated** MethylValidationFlow
17. `wf_pca_two_group_run_example.sql` (validation, optional)

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

## 6. Action payload schemas (REST + editor)

| Surface | Mechanism |
|---------|-----------|
| Storage | `wf.workflow_action_schema` (`input` / `output`, JSON Schema draft 2020-12) |
| Export | `methyl-export-task-schemas` from `workers/methyl_worker/task_models.py` |
| Gateway | `GET /v1/actions`, `GET /v1/actions/{name}/schema?direction=` |
| Config Editor | `RemoteSchemaCatalog` when `[Gateway] Enabled=true` |
| Enforcement | Workers only (`validate_task_input` / `validate_task_output`; error code `4001`) |

`payload_schema_ref` on `wf.workflow_action` mirrors the seeded input schema `schema_id`.
