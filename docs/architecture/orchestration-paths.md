# Orchestration Paths

**Default for new work:** `methyl-workflow-run` with a DomainProgram and pipeline profile. The monolithic `methyl-validation` stage flags are **legacy**.

| Path | Entry | Status |
|------|-------|--------|
| **Workflow (canonical)** | `methyl-workflow-run` | **Preferred** — local, CI, and production workers |
| Workflow (CLI alias) | `methyl-validation run-workflow` | Same engine; prefer `methyl-workflow-run` for clarity |
| Distributed workflow | `methyl-gateway` + `methyl-worker` | Production cluster (gateway = DB passthrough) |
| Worker task input | `resolvedConfig` + optional `resolvedProject` | Baked at instance start; CLIs receive `--resolved-config` |
| Study lifecycle (admin) | `methyl-study-start` / portal SQL | Compile/plan/start via DB client — not gateway |
| Monolithic CLI | `methyl-validation --stability/--freeze/--model` | **Legacy** (`--legacy-orchestration`) — transitional scripts only |
| File queue | `methyl-validation plan-runs` / `run-task` | **Legacy** distributed MC — migrate to gateway workers when possible |
| Direct package CLIs | `methyl-centroid`, `methyl-detector`, … | Single-step debugging |

## Canonical workflow programs

| Program | Purpose |
|---------|---------|
| `workflow_engine/domain/fixtures/sample_prep.program.json` | Per-sample QC, remediation, extract, archive |
| `workflow_engine/domain/checks/pca1_5_cg/configs/pca1_5_mc_stability*.program.json` | MC stability |
| `workflow_engine/domain/fixtures/study_validation_lifecycle.program.json` | Full study lifecycle |

Deploy compiled specs: `bash scripts/deploy_workflow_definitions.sh`

## Local vs distributed

- **Local:** `LocalWorkflowEngine` executes compiled graphs in-process — same DomainPrograms as production.
- **Distributed:** workers claim `node_execution` rows via the agnostic gateway; scope variables (including `resolvedConfig__*`) drive template binding in SQL. Instance context is finalized by portal or `methyl-study-start` before create — not at task claim in the gateway.

Deprecated SQL seeds (`workflow_methylvalidation_seed.sql`, `wf_pca_*`, `wf_sample_prep_pipeline_seed.sql`) — use DomainProgram compile + deploy instead.

**Usage:** [ch.14 deployment](../usage/14-deployment-and-distributed-workflow.qmd). **Implementation:** [workers-and-gateway.md](../implementation/workers-and-gateway.md).
