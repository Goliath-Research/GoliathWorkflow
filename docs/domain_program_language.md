# DomainProgram Language Reference

Authoring format for MethylPipeline workflows. Schema: `schemas/domain/domain_program.schema.json`.  
Compiler: `workflow_engine/domain/compiler.py` → `WorkflowDefinitionSpec`.

## Constructs

| IR | Engine node | Semantics |
|----|-------------|-----------|
| `do` / `action` | `ACTION` | Run catalog action; `with` supplies parameters |
| `for` / `foreach` | `FOREACH` | Iterate collection; `parallel: true` fans out |
| `parallel: [...]` | `PARALLEL` | Run children concurrently |
| sequence of steps | `SEQUENCE` | Ordered execution |
| `if` / `then` / `else` | `IF` | Branch on scope variable truthiness |
| `switch` | `SWITCH` | Integer case selection |
| `while` | `WHILE` | Loop while condition var truthy |
| `repeat` | `REPEAT` | Fixed iteration count |

## Conditions (IF)

Conditions reference scope variables set by prior ACTION output bindings or instance `context_json`:

```json
{ "if": "${qcPass}", "then": [...], "else": [...] }
```

Example: `sample.methyl_qc` binds `qcPass` from `$.guardrails.overall_pass` (see `schemas/actions/catalog.json`).

## Action parameters

```json
{
  "do": "pipeline.detector",
  "with": {
    "chromosome": { "ref": "chromosome" },
    "stepOverride": { "detection_mode": "discovery_only" }
  }
}
```

Literal strings in `with` (e.g. `"mode": "full"`) are preserved; use `{ "ref": "..." }` for scope references.

## Instance context

Minimal validation instance:

```json
{ "projectPath": "/work/study/configs/project.json" }
```

Sample prep adds `samples[]`, `isCfdna`, storage profiles — see `workflow_engine/sql/instance_context_examples/`.

## Local execution

```bash
methyl-workflow-run --program path/to/program.json --context-file context.json --stub-external
methyl-validation run-workflow --program path/to/program.json --context-file context.json
```

## Collection bindings

Compiler emits bindings for `project.*` references. Engine resolves `projectPath` → inline `project` JSON → `chromosomes`, `comparisons`, etc. before FOREACH runs.
