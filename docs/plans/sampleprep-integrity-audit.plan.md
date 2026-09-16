---
name: SamplePrep integrity audit
overview: Audit SamplePrepPipeline end-to-end (DomainProgram graph, action catalog/schemas, procedure/site actionConfig, and live Azure wf/cfg/portal links), land a durable verify CLI so this stays green, and extend the existing scaffold path toward declare→schema→stub code generation.

> **Status: IMPLEMENTED.** Verify via `methyl-cfg verify-workflow` (and `--check-db` with gateway.env). Graph audit, methylgrapher bake fix, CI preflight hook, and scaffold extensions landed.

azure_devops:
  type: Feature
  title: "SamplePrepFlow integrity + action authoring"
  epic_id: 413
todos:
  - id: audit-graph
    content: Compile SamplePrepPipeline and audit IF/edges/orphans vs SamplePrepFlow.md
    status: completed
  - id: audit-catalog-config
    content: Run catalog/schema/boundary checks; map program actions to procedure/site actionConfig; document methylgrapher contract gap
    status: completed
  - id: audit-azure-db
    content: Compare live Azure wf/cfg/portal SamplePrep deploy + instance 59 resolvedConfig bake vs git
    status: completed
  - id: verify-cli
    content: Add methyl-cfg verify-workflow (graph + catalog + optional DB) and CI preflight hook
    status: completed
  - id: fix-bake
    content: Fix resolvedConfig bake so methylgrapher_wgbs image/engine/align_engine always land from site/procedure
    status: completed
  - id: scaffold-extend
    content: Extend methyl-cfg scaffold-action toward declare→schema→Pydantic/handler/catalog stubs
    status: completed
---

# SamplePrepFlow integrity + future action authoring

## Findings (Phase 1)

| Check | Result | Notes |
|-------|--------|-------|
| Graph IF/THEN/ELSE + orphans | **PASS** | Compiled 100 nodes / 99 edges; 0 orphan; all IF have THEN+ELSE |
| Catalog coverage | **PASS** | 14 SamplePrep actions all in `ACTION_CATALOG` |
| Parameter contract docs | **FIXED** | Added `sample.methylgrapher_wgbs_*` + giraffe to action-parameter-contract |
| methylgrapher bake | **FIXED** | `site_slice_for_action` merges genome+actionConfig; genome resolve keeps `align_engine`/`alignment_mode` |
| Azure `wf` SamplePrepPipeline | **PASS** | Active version; `methyl-cfg verify-workflow --check-db` clean (100 ACTION keys match) |
| Azure `wf.workflow_action` + schemas | **PASS** | All 14 SamplePrep actions present with schemas |
| `cfg.domain_program` | **WARN** | Store has other programs; SamplePrepPipeline not listed — still deployed via `deploy_workflow_definitions.sh`. Follow-up: `methyl-cfg import-fs` / `publish-program` |
| Instance 59 READY Aligns | **PASS (patched)** | `resolvedConfig.image` / `align_engine` present on READY tasks |
| Study project JSON | **PASS** | No `step_config`; cohorts/paths only |

## Tooling

- [`workflow_engine/domain/verify_workflow.py`](../../workflow_engine/domain/verify_workflow.py)
- `methyl-cfg verify-workflow` ([`workflow_engine/cfg/verify_workflow_cmd.py`](../../workflow_engine/cfg/verify_workflow_cmd.py))
- CI: [`scripts/ci_preflight.sh`](../../scripts/ci_preflight.sh) runs SamplePrep graph verify
- Scaffold: Pydantic + DomainProgram step snippets from [`workflow_engine/cfg/scaffold.py`](../../workflow_engine/cfg/scaffold.py)

## Operator commands

```bash
methyl-cfg verify-workflow
set -a; source /work/goliath/env/gateway.env; set +a
methyl-cfg verify-workflow --check-db
```
