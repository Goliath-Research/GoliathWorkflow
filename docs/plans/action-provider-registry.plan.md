---
name: Action provider registry
overview: Harden the process-pack boundary with a catalog-driven CLI action provider registry, catalog template rules, and worker-local Depends for in-process handlers — without adopting engine-wide fast_depends.
todos:
  - id: phase1-registry
    content: Catalog-driven CliAction/handler registry; remove build_action_from_catalog if/elif; split handlers modules
    status: completed
  - id: phase2-compiler
    content: Move centroid/detector template special-cases into catalog domain_effects / template metadata
    status: completed
  - id: docs
    content: Promote plan + update component-boundaries + ADR for registry over DI
    status: completed
  - id: phase3-optional-di
    content: "Worker-local Depends for TaskRuntimeContext / logger / path helpers in in-process handlers (not engine-wide fast_depends)"
    status: completed
---

> **Status: Implemented (Phase 1–3)**

# Action provider registry (Phase 1–3)

## Verdict

**Do not adopt `fast_depends` as the main path to action-agnosticism.** The Workflow Engine is already process-agnostic. Process-pack coupling is addressed with an explicit **action provider registry**, catalog-driven compiler template rules, and a **worker-local** `Depends` helper for in-process handlers only.

## Implemented

### Phase 1 — Action provider registry

- [`workers/methyl_worker/actions/registry.py`](../../workers/methyl_worker/actions/registry.py) — `register_cli_provider` / `build_cli_action`
- Specialized CLI modules self-register; [`build_action_from_catalog`](../../workers/methyl_worker/actions/base.py) has no `action_name` switch
- [`workers/methyl_worker/handlers/`](../../workers/methyl_worker/handlers/) package (`sample_prep`, `validation`, `context`, `stub`, `dispatch`)
- [`capabilities.py`](../../workers/methyl_worker/capabilities.py) derives auto-detect rows from `ACTION_CATALOG`

### Phase 2 — Catalog-driven compiler bindings

- `DomainEffects.template_defaults` / `template_group_side_defaults` on centroid/detector catalog entries
- [`compiler._apply_catalog_template_rules`](../../workflow_engine/domain/compiler.py) — no methylation-specific branches

### Phase 3 — Worker-local DI

- [`workers/methyl_worker/depends.py`](../../workers/methyl_worker/depends.py) — tiny `Depends` + providers (`get_runtime`, `get_logger`, `get_project_path`, `get_monte_carlo_runs_root`)
- `InProcessAction` invokes handlers via `call_in_process_handler`
- Context + validation handlers migrated to `Depends(...)` where they already needed runtime / MC paths
- **Not** used in SQL engine, gateway, or DomainProgram compiler

### Docs

- ADR: [`docs/architecture/action-provider-registry.md`](../architecture/action-provider-registry.md)
- Note in [`component-boundaries.md`](../architecture/component-boundaries.md)

## Explicitly out of scope

- Engine-wide DI containers / `fast_depends` in gateway or SQL
- Silent setuptools entry-point discovery as sole registration
