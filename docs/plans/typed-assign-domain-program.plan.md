---
name: Typed Assign DomainProgram Language
overview: Extend DomainProgram toward a typed, worker-delegated assign model (ACTION + scope binding + JSON Schema variable registry), expose WHILE/SWITCH/REPEAT in the compiler to match the DB engine, and publish a complete language reference with worked generic use cases—without rewriting existing methylation FOREACH pipelines.
> **Status: COMPLETED** — language v2 + MVP runtime (IR/compiler/catalog/fixtures/tests).

todos:
  - id: lang-doc-v2
    content: Write docs/reference/domain-program-language-v2.md; promote plan; link from index
    status: completed
  - id: ir-schema
    content: Add VariableDecl/AssignStep/SwitchStep/WhileStep/RepeatStep; export schema; variable_schemas on WorkflowDefinitionSpec
    status: completed
  - id: compiler-control-assign
    content: Extend compiler for assign/switch/while/repeat; parallel-assign rejection; honor ActionStep.out; unit tests
    status: completed
  - id: compute-actions
    content: Add typed workflow.* catalog entries, task models, handlers
    status: completed
  - id: fixtures-tests
    content: Add assign_while_pagination and assign_map_reduce fixtures; smoke tests
    status: completed
  - id: docs-align
    content: Update domain-program-compiler.md, workflow-engine.md, plans/README; clarify operator summary vs v2
    status: completed
---

# Typed Assign DomainProgram Language

> **Delivery scope:** language reference document + MVP runtime (IR/compiler/catalog/local engine tests). No new SQL `NodeType`. Variable schemas live in program/`WorkflowDefinitionSpec` JSON for MVP (not a separate DB table). Existing MC/stability programs stay unchanged.

## Design decisions (locked)

| Decision | Choice |
|----------|--------|
| Assign semantics | Sugar over catalog **ACTION** + `variable_output_binding`; engine never evaluates RHS |
| New engine node? | **No** — reuse `ACTION` |
| Typing | Program `variables` map name → JSON Schema (`schemaRef` or inline); assign targets must be declared |
| Scope write rule | Assign writes **current scope only**; compiler rejects same-name assign under `parallel: true` / parallel FOREACH ancestors |
| Compute surface | Typed catalog family: `workflow.const_bool\|int\|string\|path`, `workflow.json_path_bool\|int\|string`, `workflow.fs_stat` |
| Control-flow gap | Compiler emits **SWITCH**, **WHILE**, **REPEAT** (engine already supports them) |
| Config boundary | Assign must not mutate `resolvedConfig` / `actionConfig`; orchestration/data values only |
| Methylation programs | Keep FOREACH + planner; assign is for generic / state-machine workflows |
| Catalog SoT | Git catalog is seed/authoring; **DB** `wf.workflow_action` is operational SoT after seed |

## Implementation notes

- Language reference: [`docs/reference/domain-program-language-v2.md`](../reference/domain-program-language-v2.md)
- IR: `packages/methyldomain/methyl_domain/program.py`
- Compiler: `workflow_engine/domain/compiler.py`
- Compute actions: `workers/methyl_worker/task_models/workflow_compute_models.py`, `handlers/workflow_compute.py`
- Fixtures: `workflow_engine/domain/fixtures/assign_*.program.json`

## Out of scope

- Rewriting SamplePrep / MC DomainPrograms to use assign
- SQL expression evaluator or ASSIGN node type
- Arbitrary `workflow.eval` / Python sandbox
- Parent-scope accumulators under parallel FOREACH
- Mutating `resolvedConfig` via assign
- Full JSON Schema subsumption engine
