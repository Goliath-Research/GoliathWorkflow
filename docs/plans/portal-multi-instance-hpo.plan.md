---
name: Portal multi-instance HPO
overview: cfg-typed multi-instance hyperparameter search via portal SQL (UI to DB); wf opaque execution_scope for CAAS. Dual-backend DDL/procs in sql_mssql + sql_pg (deploy-wired). No portal OpenAPI; workers use Python methyl-gateway only; EpiPortal UI out of scope.

> **Status: IMPLEMENTED.** wf renamed to `execution_scope`; cfg search ledger + `portal.sp_*` (both backends); typed HPO models + JSON Schemas; shared expander/scorer in `workflow_engine/ops/hyperparam_grid.py` with `methyl-study-start hyperparam-grid-start|score`; docs in [portal-remote-control.md](../architecture/portal-remote-control.md).

azure_devops:
  type: Feature
  title: "Portal multi-instance hyperparameter grid"
  epic_id: 413
todos:
  - id: rename-wf-execution-scope
    content: Rename wf.hyperparameter_set to wf.execution_scope in sql_mssql + sql_pg (tables, FKs, procs) and wire deploy; Python alias hyperparamSetId to executionScopeId; docs
    status: completed
  - id: typed-hpo-schemas
    content: Pydantic models + export JSON Schemas for HyperparamGridSearch / TrialOverlay (cfg-facing); schemas/config
    status: completed
  - id: cfg-search-ledger
    content: cfg.hyperparameter_search_run/trial + portal.sp_* in sql_mssql + sql_pg (parity), deploy scripts; link trials to instance + execution_scope key
    status: completed
  - id: grid-expander
    content: "Shared expand path (portal middle-tier in-proc + methyl-study-start): validate schema, merge overlays, finalize, start N instances, cfg link + wf_apply_execution_scope"
    status: completed
  - id: score-promote
    content: Score completed trials via objective J (portal.sp_score / study-start); winner overlay export operator-gated
    status: completed
  - id: legacy-bridge-docs
    content: Document wf/cfg/portal + execution_scope rename + UI to DB vs workers to gateway; deprecate host methyl-hyperparam-search; portal-remote-control.md; usage ch.15
    status: completed
  - id: tests-promote-plan
    content: Tests for rename compat, schema validate/expand/score; promote docs/plans/portal-multi-instance-hpo.plan.md + README row
    status: completed
---

# Portal multi-instance hyperparameter grid

## Decision (locked)

**Option A — multi-instance grid.** The outer search is not a worker action. Each grid point is one `wf.workflow_instance`; workers only claim READY tasks with baked `resolvedConfig`.

- **EpiPortal UI screens:** out of scope. The UI connects **directly to the database** (`portal.sp_*`).
- **No portal search OpenAPI:** workers talk only to the Python `methyl-gateway` daemon. Any future worker REST is added to that daemon; this slice adds no gateway routes.

## Schema layering

| Schema | Owns | Does not know |
|--------|------|----------------|
| `wf` | Generic actions, graphs, instances, tasks; opaque `execution_scope` + CAAS ledger | Disease, study, "hyperparameter" |
| `cfg` | Sites, profiles, studies; typed hyperparameter search/trial entities; links cfg to wf and portal | Worker claim mechanics |
| `portal` | Clinical/project samples; UI-facing procs over cfg/wf | Engine graph internals |

## What shipped

### wf rename to `execution_scope`

- [`workflow_engine/sql_mssql/wf_execution_scope.sql`](../../workflow_engine/sql_mssql/wf_execution_scope.sql) and [`sql_pg/wf_execution_scope.sql`](../../workflow_engine/sql_pg/wf_execution_scope.sql): tables `wf.execution_scope`, `wf.execution_scope_action_entry`, column `workflow_instance.execution_scope_id`, procs `wf_apply_execution_scope` / `wf_repo_upsert_execution_scope_action_entry` / `wf_repo_get_execution_scope` / `wf_repo_list_execution_scope_action_entries`. Both files migrate the legacy `hyperparameter_set` objects in place.
- Context/task field `executionScopeId` (compiler + `finalize_instance_context`), with `hyperparamSetId` accepted as a one-release alias. Python helper renamed to [`rest/execution_scope.py`](../../workflow_engine/rest/execution_scope.py); [`rest/hyperparameter_set.py`](../../workflow_engine/rest/hyperparameter_set.py) is a thin compat shim.
- DB layer methods `apply_execution_scope` / `upsert_execution_scope_action_entry` (both backends), `db_objects.yaml`, deploy scripts, and compiled check fixtures regenerated.

### Typed HPO contracts

[`packages/methylvalidation/methyl_validation/hyperparam_models.py`](../../packages/methylvalidation/methyl_validation/hyperparam_models.py): `HyperparamGridSpec`, `HyperparamTrialOverlay`, `HyperparamSearchRequest`, `HyperparamSearchStatus` — exported to `schemas/config/hyperparam_*.schema.json`.

### cfg search ledger + portal procs

[`workflow_engine/sql_pg/cfg_hyperparameter_search.sql`](../../workflow_engine/sql_pg/cfg_hyperparameter_search.sql) (+ MSSQL parity): `cfg.hyperparameter_search_run`, `cfg.hyperparameter_trial` (trial to `workflow_instance_id` + `execution_scope_key`), and `portal.sp_start_hyperparam_grid` / `sp_add_hyperparam_trial` / `sp_score_hyperparam_trial` / `sp_get_hyperparam_search` / `sp_set_hyperparam_search_status`.

### Expander + scorer

[`workflow_engine/ops/hyperparam_grid.py`](../../workflow_engine/ops/hyperparam_grid.py): `expand_and_start_grid` (plan once, apply overlay, finalize, start N instances, register scope, record trials via `DbTrialLedger`), `score_grid`, and `winner_overlay` (operator-gated). CLI: `methyl-study-start hyperparam-grid-start` / `hyperparam-grid-score`.

### Docs + legacy

[`docs/architecture/portal-remote-control.md`](../architecture/portal-remote-control.md); usage ch.15 note; host `methyl-hyperparam-search` marked deprecated for production (dev/experimentation only).

## Out of scope

- EpiPortal React/UI screens.
- New OpenAPI/REST routes for search; a second HTTP host beside `methyl-gateway`.
- Moving the opaque scope ledger into cfg.
- Worker-hosted outer search; non-grid strategies (Random / Hyperband / Bayesian); auto-promote profiles.
