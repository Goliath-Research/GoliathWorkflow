# DomainProgram Language Reference (v2)

Canonical **full language** specification for DomainProgram IR: typed variables, worker-delegated assign, and control flow that matches the database workflow engine.

> **Operator summary:** keep using [`domain-program-language.md`](domain-program-language.md) for day-to-day methylation pipelines (FOREACH + planner). This v2 document is the complete construct catalog and the home for **assign / WHILE / SWITCH / REPEAT** and typed scope variables.

| Artifact | Schema / location |
|----------|-------------------|
| DomainProgram IR | `schemas/domain/domain_program.schema.json` |
| Variable schemas (MVP) | `schemas/vars/*.schema.json` + program `variables` / `WorkflowDefinitionSpec.variable_schemas` |
| Compiled engine graph | `schemas/workflow/workflow_definition.schema.json` |
| Action catalog | `schemas/actions/catalog.json` (seed); **DB** `wf.workflow_action` is operational SoT |

Compiler: `workflow_engine/domain/compiler.py` → `WorkflowDefinitionSpec`.

---

## Layer model

```text
DomainProgram IR  ⊂  engine graph (SEQUENCE / FOREACH / IF / SWITCH / WHILE / REPEAT / ACTION / PARALLEL)
       │
       ▼ compile
WorkflowDefinitionSpec (+ variable_schemas side-car)
       │
       ▼ deploy / local run
DB scheduler + scope          workers = computational leaves
(claim → input_json → submit → output_json → variable_output_binding)
```

| Layer | Responsibility |
|-------|----------------|
| **DomainProgram** | Authoring IR: control flow, action names, typed `variables`, `assign` sugar |
| **Compiler** | Lowers to engine nodes; assign → `ACTION` + output binding; never evaluates RHS |
| **DB / local engine** | Schedules nodes, manages scope, applies bindings; **no** expression evaluator |
| **Workers** | Validate input/output against catalog JSON Schema; perform compute |

### Completeness claim

DomainProgram is **domain-orchestration complete** and **TC-capable** via `WHILE` + typed `assign` + catalog workers (workers supply the computational power). It is **not** a place to implement methylation science in-graph: science stays in catalog actions (`pipeline.*`, `validation.*`, `sample.*`). Prefer FOREACH + planner for MC/stability programs.

---

## Design rules (locked)

| Rule | Meaning |
|------|---------|
| Assign semantics | Sugar over catalog **ACTION** + `variable_output_binding`; engine never evaluates RHS |
| New engine node? | **No** — reuse `ACTION` |
| Typing | Program `variables` map name → JSON Schema (`schemaRef` or inline `schema`); assign targets must be declared |
| Scope write | Assign writes **current scope only**; compiler rejects same-name assign under `parallel: true` / parallel FOREACH ancestors |
| Compute surface | Typed catalog family `workflow.const_*`, `workflow.json_path_*`, `workflow.fs_stat` (no arbitrary eval) |
| Config boundary | Assign must **not** mutate `resolvedConfig` / `actionConfig`; orchestration/data values only |
| Methylation programs | Keep FOREACH + planner; assign is for generic / state-machine workflows |

---

## Construct catalog

### `do` / `action`

```json
{
  "do": "pipeline.centroid",
  "with": {
    "chromosome": { "ref": "chromosome" },
    "context": { "ref": "context" }
  },
  "out": { "qcPass": "$.guardrails.overall_pass" },
  "node_key": "centroid_g1"
}
```

Aliases: `action` ≡ `do`. Optional `with` / `in`, `out` (var → JSON path into `output_json`), `node_key`.

### `for` / `foreach`

```json
{
  "for": {
    "in": { "ref": "project.comparisons" },
    "as": "comparison",
    "index": "comparisonIndex",
    "parallel": true
  },
  "do": [ { "do": "pipeline.detector", "with": { "comparison": { "ref": "comparison.label" } } } ]
}
```

### `parallel` and sequence

```json
{ "parallel": [ { "do": "pipeline.centroid", "with": { "group": "A" } }, { "do": "pipeline.centroid", "with": { "group": "B" } } ] }
```

A JSON array of steps under a parent is a `SEQUENCE`.

### `if` / `then` / `else`

```json
{ "if": "${qcPass}", "then": [ { "do": "sample.archive_sample" } ], "else": [ { "do": "sample.mark_failed" } ] }
```

Condition is a scope variable (truthiness). Strip `${…}` the same way as WHILE.

### `switch` / `cases` / `default`

```json
{
  "switch": "${gateCode}",
  "cases": {
    "0": [ { "do": "workflow.const_string", "with": { "value": "ok" } } ],
    "1": [ { "do": "workflow.const_string", "with": { "value": "retry" } } ]
  },
  "default": [ { "do": "workflow.const_string", "with": { "value": "unknown" } } ]
}
```

Case keys are **integers** (engine `SWITCH`). Alternate: `{ "switch": { "ref": "prior_node_key" } }` for result-code switching by node key (engine `switch_ref_node_key`).

### `while` / `body`

```json
{
  "while": "${hasMore}",
  "do": [
    { "do": "workflow.json_path_bool", "with": { "documentPath": "${var.pagePath}", "jsonPath": "$.hasMore" }, "out": { "hasMore": "$.value" } }
  ]
}
```

Alias: `body` for the loop steps.

### `repeat` / `count` / `body`

```json
{ "repeat": 3, "do": [ { "do": "workflow.const_int", "with": { "value": 1 } } ] }
```

Or `{ "repeat": { "count": 3 }, "body": [...] }`. MVP: **literal int only**.

### `variables` registry

```json
{
  "variables": {
    "primaryAnalyte": "cfdna",
    "hasMore": { "schemaRef": "schemas/vars/bool.schema.json", "description": "Pagination gate" },
    "pageIndex": { "schema": { "type": "integer", "minimum": 0 } }
  }
}
```

- **Legacy seeds** (scalars/lists) → instance `context_json` (unchanged).
- **Declarations** (`schemaRef` or `schema`) → typed assign targets; copied to `WorkflowDefinitionSpec.variable_schemas` (no separate DB table in MVP).

### `assign`

```json
{
  "assign": "hasMore",
  "using": "workflow.const_bool",
  "with": { "value": true },
  "fromPath": "$.value"
}
```

Compiles to `ACTION` + `out: { "hasMore": "$.value" }`. Target **must** be a declared variable. Optional `do` alias for `using`. Default `fromPath` is `$.value`.

MVP plug check: for known `workflow.*` actions, `schemaRef` on the target must **exactly** match the action’s expected var schema path (no full JSON Schema subsumption).

---

## Template namespaces

| Form | Meaning |
|------|---------|
| `${var.name}` | Scope variable (bindings, FOREACH item fields, assign targets) |
| `${ctx.*}` | Instance context (engine-specific; prefer `var` in programs) |
| `{ "ref": "project.comparisons" }` | Collection binding from study manifest |
| `{ "ref": "iteration.runDir" }` | Nested FOREACH item field |

FOREACH with `parallel: true` opens a child scope per item; assign writes that child scope only.

---

## Result codes, bindings, CAAS

| Code | Meaning |
|------|---------|
| `< 0` | Hard failure |
| `0` | Success / false |
| `1` | True / remediation |
| `2..N` | SWITCH cases |

Output bindings map `output_json` paths into scope (`out` / assign / catalog `domain_effects.scope_bindings`).

**CAAS / idempotency:** pure `workflow.const_*` and `workflow.json_path_*` may enable signature skip. `workflow.fs_stat` includes `mtimeUtc` — treat as non-replay-safe (idempotency off).

---

## Typed compute actions (MVP)

| Action | Input | Output `$.value` |
|--------|-------|------------------|
| `workflow.const_bool` | `{ "value": bool }` | bool |
| `workflow.const_int` | `{ "value": int }` | int |
| `workflow.const_string` | `{ "value": str }` | string |
| `workflow.const_path` | `{ "value": str }` | path string |
| `workflow.json_path_bool` | `{ "documentPath", "jsonPath" }` | bool |
| `workflow.json_path_int` | `{ "documentPath", "jsonPath" }` | int |
| `workflow.json_path_string` | `{ "documentPath", "jsonPath" }` | string |
| `workflow.fs_stat` | `{ "path" }` | bool (`exists`); also `exists`, `size`, `mtimeUtc` |

Capability family: `workflow.*` (per-action capabilities such as `workflow.const-bool`). Execution: `in_process`. Operational catalog SoT: database after seed from git `schemas/actions/catalog.json`.

---

## Anti-patterns

1. **Parallel shared assign** — writing the same var under `parallel: true` / parallel FOREACH (compiler error).
2. **Config mutation** — assigning into `resolvedConfig` / `actionConfig` (forbidden by contract; use profile/site/instance overlays).
3. **Science-in-assign** — implementing DMP/gene/MC logic via const/json_path loops instead of catalog science actions.
4. **Undeclared assign target** — assign without `schemaRef`/`schema` declaration.
5. **Arbitrary eval** — there is no `workflow.eval` / Python sandbox.

---

## Use cases

### 1. Const + IF

```json
{
  "programVersion": 2,
  "name": "ConstIfGate",
  "projectPath": "/work/projects/example/configs/project.json",
  "variables": {
    "runHeavy": { "schemaRef": "schemas/vars/bool.schema.json" }
  },
  "body": [
    {
      "assign": "runHeavy",
      "using": "workflow.const_bool",
      "with": { "value": true }
    },
    {
      "if": "${runHeavy}",
      "then": [ { "do": "context.resolve_project", "with": {} } ],
      "else": []
    }
  ]
}
```

### 2. Pagination / WHILE

See fixture `workflow_engine/domain/fixtures/assign_while_pagination.program.json`: seed `hasMore`, loop while true, refresh from JSON page file via `workflow.json_path_bool`.

### 3. Map–reduce

See fixture `workflow_engine/domain/fixtures/assign_map_reduce.program.json`: FOREACH over paths (sequential), `workflow.fs_stat` per path, reduce existence into a summary string via `workflow.const_string` / `workflow.json_path_string` after the loop.

### 4. QC state machine (generic)

```json
{
  "switch": "${gateCode}",
  "cases": {
    "0": [ { "assign": "label", "using": "workflow.const_string", "with": { "value": "pass" } } ],
    "1": [ { "assign": "label", "using": "workflow.const_string", "with": { "value": "remediate" } } ]
  },
  "default": [ { "assign": "label", "using": "workflow.const_string", "with": { "value": "fail" } } ]
}
```

Not a full SamplePrep rewrite — pattern only. Production SamplePrep uses a **hybrid**: typed `variables` for QC gates (`qcPass`, `remediateAlignment`, `extractionQcPass`) with catalog `scope_bindings` writing those names, while **FOREACH samples + IF** remains the control flow. Explicit program `out` under `parallel: true` is avoided when the same gate is written again on QC retry (compiler parallel-assign rule). See `workflow_engine/domain/fixtures/sample_prep.program.json`.

### 5. Typed parameter bus

Declare a path variable; assign once; pass `${var.artifactPath}` into two different catalog actions’ `with` fields.

### 6. Contrast: methylation MC without assign

Programs such as `mc_stability.program.json` / `h_pca_good` style remain **FOREACH + `validation.plan_iterations` + bindings**. That pattern is preferred for cohort science: collections come from the study manifest and planner, not from assign loops. **Do not** rewrite MC DomainPrograms to use typed assign.

---

## Related

- Operator summary: [`domain-program-language.md`](domain-program-language.md)
- Compiler internals: [`../implementation/domain-program-compiler.md`](../implementation/domain-program-compiler.md)
- Engine: [`../implementation/workflow-engine.md`](../implementation/workflow-engine.md)
- Plan: [`../plans/typed-assign-domain-program.plan.md`](../plans/typed-assign-domain-program.plan.md)
