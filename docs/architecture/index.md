# Architecture

Consolidated system design for MethylPipeline: configuration layers, distributed runtime, orchestration paths, and pipeline stages.

| Document | Topic |
|----------|-------|
| [Component boundaries](component-boundaries.md) | Gateway vs DB vs admin CLI vs MCP vs pipeline knowledge |
| [Layer model](layer-model.md) | manifest → profile → program → instance → worker |
| [Distributed runtime](distributed-runtime.md) | portal, DB, gateway, workers, shared storage |
| [Orchestration paths](orchestration-paths.md) | local, gateway, legacy CLI matrix |
| [Pipeline stages](pipeline-stages.md) | sample prep through validation stage DAG |
| [Hyperparameter sets & CAAS](../usage/17-content-addressed-action-store.qmd) | Experiment with the same workflow under varied config; idempotent cross-instance reuse ([deep dive](../../workflow_engine/docs/pipeline_architecture.md#hyperparameter-sets-and-caas)) |
| [Documentation audit (2026-07)](documentation-audit-2026-07.md) | Staleness findings + Quarto validation + remediation checklist |

**Interactive hub:** [methylpipeline-architecture canvas](../canvas/methylpipeline-architecture.canvas.tsx) (local vs gateway, config layers, DB contract)

**Documentation hub:** [methylpipeline-docs canvas](../canvas/methylpipeline-docs.canvas.tsx) — [all canvases](../canvas/README.md)

**Implementation detail:** [Implementation guide](../implementation/index.md). **Operator runbooks:** [Usage manual](../usage/index.qmd).

## Quick audience routing

- **Config author** → [layer-model.md](layer-model.md)
- **DevOps / cluster** → [distributed-runtime.md](distributed-runtime.md) + [Usage ch.14](../usage/14-deployment-and-distributed-workflow.qmd)
- **Workflow author** → [orchestration-paths.md](orchestration-paths.md) + [Usage ch.04 orchestration](../usage/04-orchestration-workflow-run.qmd) + [DomainProgram reference](../reference/domain-program-language.md)
- **Experimentation / result versioning** → [Usage ch.17](../usage/17-content-addressed-action-store.qmd) + [pipeline architecture — hyperparameter sets](../../workflow_engine/docs/pipeline_architecture.md#hyperparameter-sets-and-caas)
