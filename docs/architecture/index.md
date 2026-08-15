# Architecture

Consolidated system design for MethylPipeline: configuration layers, distributed runtime, orchestration paths, and pipeline stages.

| Document | Topic |
|----------|-------|
| [Component boundaries](component-boundaries.md) | Gateway vs DB vs admin CLI vs MCP vs pipeline knowledge |
| [Action provider registry](action-provider-registry.md) | Process-pack registry vs engine; why not DI |
| [Layer model](layer-model.md) | manifest → profile → program → instance → worker |
| [Config registry](config-registry.md) | `cfg` SoT → materialize `/work`; storage endpoints/credentials |
| [Reference inventory (QNAP)](../deployment/reference-inventory-qnap.md) | Upload/provision map: `s3://epimethyl/genomes/` ↔ `/work/genomes/` |
| [Distributed runtime](distributed-runtime.md) | portal, DB, gateway, workers, shared storage |
| [Orchestration paths](orchestration-paths.md) | local, gateway, legacy CLI matrix |
| [Pipeline stages](pipeline-stages.md) | sample prep through validation stage DAG |
| [SamplePrep tooling](sample-prep-tooling.md) | mojo-align / MethylExtractor / Clara roles; alignment vs extraction QC |
| [End-to-end workflow — DNA methylation](end-to-end-workflow.md) | Ingest → SamplePrep (QC/trim/extract) → MC → DeConv/info measures → model → holdouts (Mermaid) |
| [Config propagation — methylation](config-propagation-methylation.md) | Bake → SamplePrep → MC snapshot → prepare_freeze path rebind → holdout; buffy vs cfDNA checklist |
| [End-to-end workflow — RNA-Seq](end-to-end-workflow-rnaseq.md) | Ingest → quantify (rna_fq2bam/kallisto) → RNA QC → expression.h5 → DE gene panel + tabular classification (Mermaid) |
| [End-to-end workflow — Proteomics](end-to-end-workflow-proteomics.md) | Ingest (GPU DIA-NN / panel) → proteomics QC → abundance.h5 → differential-abundance panel + tabular classification (Mermaid) |
| [Portal remote control](portal-remote-control.md) | UI→DB vs workers→gateway; multi-instance hyperparameter grids; `cfg` trials → wf `execution_scope` |
| [Portal information architecture](portal-ia.md) | EpiPortal nav hierarchy, RBAC floors, fleet Drain/Stop/Resume, affinity display, screen → `portal.sp_*` inventory |
| [Portal UI](portal-UI.md) | Pointer to portal-ia (Study catalog pickers, process packs) |
| [Execution scopes & CAAS](../usage/17-content-addressed-action-store.md) | Experiment with the same workflow under varied config; idempotent cross-instance reuse ([deep dive](../../workflow_engine/docs/pipeline_architecture.md#execution-scopes-and-caas)) |
| [Documentation audit (2026-07)](documentation-audit-2026-07.md) | Staleness findings + Quarto validation + remediation checklist |

**Interactive hub:** [architecture canvas](../canvas/README.md#methylpipeline-architecture) (local vs gateway, config layers, DB contract; open in Cursor after sync)

**Platform overview:** [Platform Overview](../overview/methylpipeline-platform-overview.md) · [overview canvas](../canvas/README.md#methylpipeline-platform-overview)

**Documentation hub:** [docs canvas](../canvas/README.md#methylpipeline-docs) — [all canvases](../canvas/README.md)

**Implementation detail:** [Implementation guide](../implementation/index.md). **Operator runbooks:** [Usage manual](../usage/index.md).

## Quick audience routing

- **Config author** → [layer-model.md](layer-model.md) + [config-registry.md](config-registry.md)
- **DevOps / cluster** → [production-platform.md](../deployment/production-platform.md) + [distributed-runtime.md](distributed-runtime.md) + [Usage ch.14](../usage/14-deployment-and-distributed-workflow.md) + [Usage ch.19](../usage/19-config-registry.md)
- **Workflow author** → [orchestration-paths.md](orchestration-paths.md) + [Usage ch.04 orchestration](../usage/04-orchestration-workflow-run.md) + [DomainProgram reference](../reference/domain-program-language.md) + [end-to-end workflow](end-to-end-workflow.md)
- **Experimentation / result versioning** → [Usage ch.17](../usage/17-content-addressed-action-store.md) + [pipeline architecture — execution scopes](../../workflow_engine/docs/pipeline_architecture.md#execution-scopes-and-caas) + [portal remote control](portal-remote-control.md)
- **EpiPortal UI / RBAC** → [portal-ia.md](portal-ia.md) ([portal-UI.md](portal-UI.md)) + [portal remote control](portal-remote-control.md) + [config-registry storage RBAC](config-registry.md)
