# Architecture

Consolidated system design for MethylPipeline: configuration layers, distributed runtime, orchestration paths, and pipeline stages.

| Document | Topic |
|----------|-------|
| [Layer model](layer-model.md) | manifest → profile → program → instance → worker |
| [Distributed runtime](distributed-runtime.md) | portal, DB, gateway, workers, shared storage |
| [Orchestration paths](orchestration-paths.md) | local, gateway, legacy CLI matrix |
| [Pipeline stages](pipeline-stages.md) | sample prep through validation stage DAG |

**Interactive hub:** [methylpipeline-docs canvas](/home/ubuntu/.cursor/projects/home-ubuntu-MethylPipeline/canvases/methylpipeline-docs.canvas.tsx)

**Implementation detail:** [Implementation guide](../implementation/index.md). **Operator runbooks:** [Usage manual](../usage/index.qmd).

## Quick audience routing

- **Config author** → [layer-model.md](layer-model.md)
- **DevOps / cluster** → [distributed-runtime.md](distributed-runtime.md) + [Usage ch.14](../usage/14-deployment-and-distributed-workflow.qmd)
- **Workflow author** → [orchestration-paths.md](orchestration-paths.md) + [DomainProgram reference](../reference/domain-program-language.md)
