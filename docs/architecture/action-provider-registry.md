# Action provider registry (process pack vs engine)

## Decision

MethylPipeline keeps the **Workflow Engine process-agnostic** and hardens the
**process pack** (methyl worker + action catalog) with an explicit **action
provider registry**. We do **not** adopt request-scoped dependency injection
(e.g. `fast_depends`) as the primary mechanism for action-agnosticism.

| Layer | Knows about | Extension style |
|-------|-------------|-----------------|
| Engine (SQL / local scheduler / compiler) | Node types, scope, `${var.*}` templates | Opaque `ACTION` nodes |
| Action catalog | `action_name`, capability, I/O schemas, `domain_effects` | Static `ACTION_CATALOG` + export/seed |
| CLI providers | Specialized `CliAction` / collectors | `register_cli_provider(action_name, …)` |
| In-process handlers | Domain packages | Catalog `in_process_handler` name → `handlers` package |
| Instance config | Merged `actionConfig` | Baked `resolvedConfig` / `resolvedConfig__*` |

## Why not DI for the engine

`fast_depends` (and similar) inject typed dependencies into callables. The
engine’s contract is already opaque: `action_name` + JSON `input_json`. Config
injection is instance-time baking (`finalize_instance_context`), not handler
signature wiring. Putting a DI container in the gateway, SQL engine, or
DomainProgram compiler would couple orchestration to process-pack types.

## Registry mechanics

1. **CLI actions** — modules under `workers/methyl_worker/actions/` call
   `register_cli_provider(...)`. `build_action_from_catalog` looks up the
   provider (or falls back to generic `CliAction`). No `if action_name == …`
   switch in the dispatcher.
2. **In-process actions** — catalog `in_process_handler` names resolve on the
   `methyl_worker.handlers` package (`handlers/sample_prep.py`,
   `handlers/validation.py`, …).
3. **Compiler templates** — catalog `domain_effects.template_defaults` and
   `template_group_side_defaults` drive `_action_template` in
   `workflow_engine/domain/compiler.py` without methylation-specific branches.
4. **Capability probing** — `resolve_worker_capabilities()` derives auto-detect
   rows from `ACTION_CATALOG` (CLI on PATH, Parabricks, extractor, always-on
   in-process).

## Adding a new process action

1. Add Pydantic task I/O models and an `ACTION_CATALOG` entry.
2. For CLI: implement/register a provider (or use generic `CliAction` + `argv_map`).
3. For in-process: add `_handle_*` in the appropriate `handlers/` module and set
   `in_process_handler`.
4. Export: `methyl-export-action-catalog` / task schema export; seed DB.
5. Optional: template rules on `domain_effects` if the compiler must bind scope
   vars beyond `with` / `context_vars`.

Keep the catalog **explicit** (CI drift check). Do not rely on silent setuptools
entry-point discovery as the sole registration path.

## Related

- [Component boundaries](component-boundaries.md)
- Plan: [action-provider-registry.plan.md](../plans/action-provider-registry.plan.md)
- Universal Action Input Contract: `.cursor/rules/python-typed-io.mdc`
