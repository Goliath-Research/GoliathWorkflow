# Workflow Engine Delphi Implementation

This document describes how the Delphi runtime in `workflow_engine/src` executes workflows backed by the `wf` SQL schema, and provides a workflow tree example that exercises all major control-flow branches.

## Runtime architecture

- `WfEngine.Scheduler.pas` (`TWorkflowEngine`) is the orchestration entrypoint.
- `WfEngine.ControlFlow.pas` (`TWorkflowControlFlow`) performs node activation and parent continuation.
- `WfEngine.Scope.pas` (`TWorkflowScope`) manages scoped variables, defaults, conditions, and output bindings.
- `WfEngine.JsonResolver.pas` (`TWorkflowJsonResolver`) resolves `${...}` placeholders in templates and input bindings.
- `WfEngine.Repository.pas` (`TWorkflowRepository`) persists and reads graph/runtime state from SQL (`wf` schema).
- `WfEngine.WorkerApiAdapter.pas` (`TWorkflowWorkerApi`) bridges worker stored procedures and optional in-engine submit path.
- `WfEngine.ServiceLoop.pas` (`TWorkflowEngineHostedService`) wraps connection lifecycle and polling loop for service hosting.

## End-to-end lifecycle

1. `StartInstance()` loads graph (`workflow_node` + `workflow_edge`) and validates `root_node_id`.
2. Instance status changes to `RUNNING`; instance scope (`scope_node_execution_id = 0`) is seeded from `workflow_instance.context_json`.
3. `ActivateNode()` recursively expands the tree:
   - `ACTION` creates `node_execution` with `READY` status and resolved `input_json`.
   - Composite nodes create `RUNNING` execution rows and dispatch children according to type.
4. Workers claim `READY` actions through `wf.sp_worker_request_task`, execute work, then submit.
5. `OnActionCompleted()` stores result/output, updates scope variables via output bindings, and continues the parent composite.
6. Root completion sets instance to `COMPLETED`; any unrecoverable branch failure sets instance to `FAILED`.

## Control-flow semantics

- **Sequence (`ntSequence`)**: executes children by `child_order`; stops on first failed child.
- **Parallel (`ntParallel`)**: fans out all children; completes only when all are terminal and none failed.
- **If (`ntIf`)**: condition resolves to integer (`0` false, non-zero true) and selects `THEN` or `ELSE`.
- **Switch (`ntSwitch`)**: matches integer value against `CASE`; falls back to `DEFAULT`.
- **Repeat (`ntRepeat`)**: inserts `loop_state`, executes `BODY` until `repeat_target_count`.
- **While (`ntWhile`)**: evaluates condition before each iteration; exits when condition becomes `0`.

## Scope and data resolution

### Scope hierarchy

- Instance scope root id is `0` (`WF_INSTANCE_SCOPE_EXECUTION_ID`).
- Each composite opens a new scope execution id.
- Variable lookup climbs parent scopes until instance scope.
- Parallel branches copy parent scope into branch-local scope and write outputs independently.

### Placeholder tokens

Supported `${...}` families:

- `ctx.*` (execution context), e.g. `${ctx.iterationNo}`
- `var.*` (scope variables), e.g. `${var.sampleId}`
- `ctx.task.<node_key>.resultCode`
- `ctx.task.<node_key>.output.<jsonPath>`

Unsupported expression syntax (operators/functions) throws `EWfJson` with engine error `ENGINE_ERROR_UNSUPPORTED_EXPR`.

## Workflow tree example (exercises implementation)

The following tree intentionally covers `SEQUENCE`, `PARALLEL`, `IF`, `SWITCH`, `REPEAT`, `WHILE`, and `ACTION` behavior:

```text
RootSeq [SEQUENCE]
├─ LoadInput [ACTION]
├─ BranchPar [PARALLEL]
│  ├─ GateIf [IF: condition_var=shouldRunQc]
│  │  ├─ QcTask [ACTION]                (THEN)
│  │  └─ SkipQc [ACTION]                (ELSE)
│  └─ ModeSwitch [SWITCH: switch_var=mode]
│     ├─ NormalizeA [ACTION]            (CASE 1)
│     ├─ NormalizeB [ACTION]            (CASE 2)
│     └─ NormalizeDefault [ACTION]      (DEFAULT)
├─ RetryRepeat [REPEAT: repeat_count=3]
│  └─ AlignChunk [ACTION]               (BODY)
├─ PollWhile [WHILE: condition_var=hasMorePages]
│  └─ FetchPage [ACTION]                (BODY)
└─ Publish [ACTION]
```

### Why this tree is useful

- **Branching correctness**: validates IF and SWITCH selection and missing-branch safeguards.
- **Join behavior**: validates parallel fan-out/fan-in completion logic.
- **Loop state**: validates repeat loop persistence and while iterative progression.
- **Scope writes/reads**: output bindings from branch actions can feed later conditions/switches.
- **Context fields**: actions receive `ctx.iterationNo`, `ctx.sequenceIndex`, and `ctx.parallelIndex` where applicable.

### SQL seed for this tree

Use `sql/workflow_tree_seed_example.sql` to create this exact workflow in `wf` schema.

- Seeded workflow definition name: `DelphiTreeFlow`
- Prerequisite migration: `sql/wf_scope_variables.sql`
- Suggested instance context:
  - `{"sampleId":"S-001","mode":2,"shouldRunQc":1,"hasMorePages":1}`
- Deterministic worker result codes to reproduce walkthrough:
  - `load_input=1`, `fetch_page=1 then 0`, all others `=1`
- To run the full flow with worker claim/submit simulation, use:
  - `sql/workflow_tree_run_example.sql` (set `@wid` and `@tok` first)

## Example execution walk-through

Assume:

- `shouldRunQc = 1`
- `mode = 2`
- `hasMorePages` starts as `1`, then becomes `0` after two `FetchPage` outputs

Expected high-level progression:

1. `LoadInput` becomes `READY`, completes, and writes initial variables.
2. `BranchPar` creates two concurrent branches:
   - `GateIf` activates `QcTask`.
   - `ModeSwitch` activates `NormalizeB`.
3. `BranchPar` completes after both branch actions are terminal and successful.
4. `RetryRepeat` runs `AlignChunk` exactly 3 iterations (`loop_state.current_iteration` advances 1 -> 3).
5. `PollWhile` runs `FetchPage` twice, then condition evaluates to `0` and loop exits.
6. `Publish` executes; root sequence completes; instance transitions to `COMPLETED`.

## Failure conventions

- Worker submit with `result_code < 0` marks the action `FAILED` and fails the instance.
- Missing structural branches (IF/ELSE, SWITCH/DEFAULT, missing BODY) are engine failures with explicit `ENGINE_ERROR_*` codes.
- JSON/template/context resolution failures raise `EWfJson` and fail the relevant activation path.

## Hosting and operations

- Console host: `WfEngineSrv.dpr`
  - `/run [pollms=1000] [maxinstances=50]`
  - `/startinstance version=<id> [context={}]`
- Required environment variable: `METHYLPIPELINE_DB` (UniDAC connection string).

