---
name: Agnostic Gateway And Boundaries
overview: Strip all pipeline knowledge out of the REST gateway so it is a pure worker-to-database passthrough, moving config resolution to instance-configuration time (DB-served) and domain compile/lifecycle to admin tooling; then document the architectural boundaries (agnostic gateway, dev-only MCP, DB-owned engine/RBAC/portal/instances).
azure_devops:
  type: Feature
  title: "Agnostic gateway and documented boundaries"
  work_item_id: 551
  epic_id: 413
todos:
  - id: resolve-at-config
    content: Emit generic resolvedConfig scope binding in compiler and compute resolvedConfigByKey at instance creation so the DB serves fully-resolved input_json; verify SQL object-valued scope ref parity
    status: completed
    work_item_id: 552
  - id: gateway-claim-clean
    content: Remove materialize_claimed_task_input from worker_request_task in db_client.py (return DB claim verbatim) and drop it from __all__
    status: completed
    work_item_id: 553
  - id: gateway-catalog-clean
    content: Remove catalog loading and _merge_action_catalog from gateway.py; serve /v1/actions from DB rows, persisting execution_mode/cli_tool/etc into wf.workflow_action via seed
    status: completed
    work_item_id: 554
  - id: move-lifecycle-out
    content: Delete domain compile/lifecycle routes from gateway.py and relocate study/sample-prep/compile logic into an admin-tier CLI that calls generic gateway/DB endpoints
    status: completed
    work_item_id: 555
  - id: repoint-callers
    content: Update CI/smoke/scripts/docs that call /v1/studies/* or /v1/admin/workflows/compile to use the new admin CLI
    status: completed
    work_item_id: 556
  - id: docs-boundaries
    content: Add component-boundaries doc (agnostic gateway, dev-only MCP, DB-owned engine/RBAC/portal/instances) and update index, orchestration-paths, layer-model, pipeline_architecture.qmd, AGENTS.md, config-not-code rule
    status: completed
    work_item_id: 557
  - id: promote-plan
    content: Promote plan to docs/plans/agnostic-gateway-and-boundaries.plan.md and update docs/plans/README.md
    status: completed
    work_item_id: 558
  - id: verify
    content: Run gateway/worker/domain pytest suites, contract parity, and an end-to-end DB-backed claim confirming resolvedConfig is present with no gateway enrichment
    status: completed
    work_item_id: 559
---

# Agnostic Gateway and Documented Boundaries

> **Status: completed** (2026-07-03)

## Goal

Make the REST gateway a pure passthrough between workers and the database (no pipeline knowledge), and record the intended boundaries in canonical docs. `resolvedConfig` is resolved once at **instance creation/configuration** (baked into instance scope, served by the DB); domain **compile/lifecycle** moved to **`methyl-study-start`** admin CLI.

## Deliverables

| Area | Change |
|------|--------|
| Compiler | `resolvedConfig` template binding `${var.resolvedConfig__<key>}` |
| Instance config | `finalize_instance_context()` bakes scope vars before DB create |
| Gateway | Worker/admin passthrough only; no catalog file reads, no claim-time merge |
| DB | `wf.workflow_action` dispatch columns; `wf_action_dispatch_metadata.sql` |
| Admin CLI | `methyl-study-start` (compile, validation-start, sample-prep-start, plan-iterations) |
| Docs | [component-boundaries.md](../architecture/component-boundaries.md) |

## Architecture

See [component-boundaries.md](../architecture/component-boundaries.md) for the canonical boundary diagram and ownership table.

## Out of scope (follow-up)

- DB-side `wf.wf_apply_validation_plan` hardcoded `'methylvalidation.plan'` extension key
