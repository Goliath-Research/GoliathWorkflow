# Orchestration Paths

| Path | Entry | Status |
|------|-------|--------|
| **Workflow (canonical)** | `methyl-workflow-run`, `methyl-validation run-workflow` | Preferred |
| Distributed workflow | `methyl-gateway` + `methyl-worker` | Production cluster (gateway = DB passthrough) |
| Study lifecycle (admin) | `methyl-study-start` | Compile/plan/start — not gateway domain routes |
| Monolithic CLI | `methyl-validation --stability/--freeze/--model` | Legacy (`--legacy-orchestration`) |
| File queue | `methyl-validation plan-runs` / `run-task` | Legacy distributed MC |
| Direct package CLIs | `methyl-centroid`, `methyl-detector`, … | Single-step debugging |

## Canonical workflow programs

| Program | Purpose |
|---------|---------|
| `workflow_engine/domain/fixtures/sample_prep.program.json` | Per-sample QC, remediation, extract, archive |
| `workflow_engine/domain/checks/pca1_5_cg/configs/pca1_5_mc_stability*.program.json` | MC stability |
| `workflow_engine/domain/checks/pca1_5_cg/configs/study_validation_lifecycle.program.json` | Full study lifecycle |

Deploy compiled specs: `bash scripts/deploy_workflow_definitions.sh`

## Local vs distributed

- **Local:** `LocalWorkflowEngine` executes compiled graphs in-process — same DomainPrograms as production.
- **Distributed:** workers claim `node_execution` rows via the agnostic gateway; scope variables (including `resolvedConfig__*`) drive template binding in SQL. Instance context is finalized by portal or `methyl-study-start` before create — not at task claim in the gateway.

Deprecated SQL seeds (`workflow_methylvalidation_seed.sql`, `wf_pca_*`, `wf_sample_prep_pipeline_seed.sql`) — use DomainProgram compile + deploy instead.

**Usage:** [ch.14 deployment](../usage/14-deployment-and-distributed-workflow.qmd). **Implementation:** [workers-and-gateway.md](../implementation/workers-and-gateway.md).
