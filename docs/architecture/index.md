# Architecture

Consolidated system design for MethylPipeline: configuration layers, distributed runtime, orchestration paths, and pipeline stages.

| Document | Topic |
|----------|-------|
| [Component boundaries](component-boundaries.md) | Gateway vs DB vs admin CLI vs MCP vs pipeline knowledge |
| [Action provider registry](action-provider-registry.md) | Process-pack registry vs engine; why not DI |
| [Layer model](layer-model.md) | manifest → profile → program → instance → worker |
| [Config registry](config-registry.md) | `cfg` SoT → materialize `/work`; storage endpoints/credentials |
| [Distributed runtime](distributed-runtime.md) | portal, DB, gateway, workers, shared storage |
| [Orchestration paths](orchestration-paths.md) | local, gateway, legacy CLI matrix |
| [Pipeline stages](pipeline-stages.md) | sample prep through validation stage DAG |
| [End-to-end workflow](end-to-end-workflow.md) | Ingest → SamplePrep (QC/trim/extract) → MC → DeConv/info measures → model → holdouts (Mermaid) |
| [Portal remote control](portal-remote-control.md) | UI→DB vs workers→gateway; multi-instance hyperparameter grids; `cfg` trials → wf `execution_scope` |
| [Execution scopes & CAAS](../usage/17-content-addressed-action-store.qmd) | Experiment with the same workflow under varied config; idempotent cross-instance reuse ([deep dive](../../workflow_engine/docs/pipeline_architecture.md#execution-scopes-and-caas)) |
| [Documentation audit (2026-07)](documentation-audit-2026-07.md) | Staleness findings + Quarto validation + remediation checklist |

**Interactive hub:** [methylpipeline-architecture canvas](../canvas/methylpipeline-architecture.canvas.tsx) (local vs gateway, config layers, DB contract)

**Platform overview:** [Platform Overview](../overview/methylpipeline-platform-overview.md) · [overview canvas](../canvas/methylpipeline-platform-overview.canvas.tsx)

**Documentation hub:** [methylpipeline-docs canvas](../canvas/methylpipeline-docs.canvas.tsx) — [all canvases](../canvas/README.md)

**Implementation detail:** [Implementation guide](../implementation/index.md). **Operator runbooks:** [Usage manual](../usage/index.qmd).

## Quick audience routing

- **Config author** → [layer-model.md](layer-model.md) + [config-registry.md](config-registry.md)
- **DevOps / cluster** → [production-platform.md](../deployment/production-platform.md) + [distributed-runtime.md](distributed-runtime.md) + [Usage ch.14](../usage/14-deployment-and-distributed-workflow.qmd) + [Usage ch.19](../usage/19-config-registry.qmd)
- **Workflow author** → [orchestration-paths.md](orchestration-paths.md) + [Usage ch.04 orchestration](../usage/04-orchestration-workflow-run.qmd) + [DomainProgram reference](../reference/domain-program-language.md) + [end-to-end workflow](end-to-end-workflow.md)
- **Experimentation / result versioning** → [Usage ch.17](../usage/17-content-addressed-action-store.qmd) + [pipeline architecture — execution scopes](../../workflow_engine/docs/pipeline_architecture.md#execution-scopes-and-caas) + [portal remote control](portal-remote-control.md)
