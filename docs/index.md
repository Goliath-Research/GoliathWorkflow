# MethylPipeline Documentation

Markdown-first documentation site (Material for MkDocs) covering Theory, Usage, Implementation, plus architecture, deployment, reference, and regulatory/product-control docs.

**Build / preview:** see [Contributing](CONTRIBUTING.md) — `make docs-serve` or `mkdocs build --strict` → portable `site/`.

**Quick platform overview:** [Platform Overview](overview/methylpipeline-platform-overview.md) · [companion canvas](canvas/README.md#methylpipeline-platform-overview)

**Interactive hub:** [docs canvas](canvas/README.md#methylpipeline-docs) — [canvas index](canvas/README.md) (open in Cursor after `bash scripts/sync_cursor_canvases.sh`)

## Start here by role

| Role | Start |
|------|-------|
| **Anyone new** — concise platform + SaMD fitness synthesis | [Platform Overview](overview/methylpipeline-platform-overview.md) |
| **Operator** — run a study end-to-end | [Usage](usage/index.md) staged chapters · [SaMD lifecycle](usage/18-samd-study-lifecycle.md) · [Alignment engines](usage/alignment-engines.md) |
| **Statistician** — methods and assumptions | [Theory](theory/index.md) — e.g. [DMP detection](theory/chapters/03-methyldetector.md) |
| **Developer** — engine, workers, compiler | [Implementation](implementation/index.md) · [Sample prep (native-Mojo)](implementation/sample-preparation-flow.md) · [Mojo multi-GPU Align](architecture/mojo-multi-gpu-dual-align.md) |
| **Workflow author** — DomainPrograms | [DomainProgram language](reference/domain-program-language.md) · [v2](reference/domain-program-language-v2.md) · [Layer model](architecture/layer-model.md) |
| **DevOps** — DB, gateway, workers | [Operator journey](deployment/operator-journey.md) · [Admin CLI](reference/admin-cli-methyl-study-start.md) · [Usage deployment](usage/14-deployment-and-distributed-workflow.md) |
| **Auditor** — traceability, evidence | [Traceability](reference/traceability-provenance.md) · [Regulatory](regulatory/README.md) |
| **Package maintainer** | [implementation/packages/](implementation/packages/index.md) |

## Five navigation lenses

### By audience

See table above. Regulatory / quality: [regulatory/README.md](regulatory/README.md). Customer subset site: `mkdocs.customer.yml`.

### By pipeline stage

[Pipeline stages](architecture/pipeline-stages.md) · **[End-to-end workflow (Mermaid)](architecture/end-to-end-workflow.md)** ↔ [Usage](usage/index.md)

### By system layer

[Layer model](architecture/layer-model.md) — manifest → profile → program → instance → worker

### By package

[Package implementation index](implementation/packages/index.md) + `packages/*/docs/{THEORY,IMPLEMENTATION,USAGE}.md`

### By execution mode

[Orchestration paths](architecture/orchestration-paths.md) — **`methyl-workflow-run` (canonical)** vs legacy `methyl-validation`

## Pillars

| Pillar | Location | Owns |
|--------|----------|------|
| **Theory** | [`theory/`](theory/index.md) | Math, statistics, assumptions (MathJax) |
| **Usage** | [`usage/`](usage/index.md) | Commands, artifacts, troubleshooting, deploy |
| **Implementation** | [`implementation/`](implementation/index.md) | Engine, workers, compiler, code paths |

## Cross-cutting

| Area | Location |
|------|----------|
| Architecture | [`architecture/`](architecture/index.md) |
| Platform overview | [`overview/methylpipeline-platform-overview.md`](overview/methylpipeline-platform-overview.md) |
| Reference | [`reference/documentation-toolchain.md`](reference/documentation-toolchain.md), [`configuration-reference.md`](reference/configuration-reference.md) |
| Deployment | [`deployment/operator-journey.md`](deployment/operator-journey.md) |
| Regulatory | [`regulatory/`](regulatory/README.md) |
| Plans (internal) | [`plans/`](plans/README.md) |
| Cursor canvases | [`canvas/`](canvas/README.md) |
| Audit registry | [`DOCUMENTATION_AUDIT.md`](DOCUMENTATION_AUDIT.md) |
| Contributing | [`CONTRIBUTING.md`](CONTRIBUTING.md) |

## Canonical workflow (DomainProgram-first)

```bash
methyl-workflow-run \
  --program workflow_engine/domain/fixtures/study_validation_lifecycle.program.json \
  --context '{"projectPath": "/work/<disease>/configs/project_*.json"}'
```

Legacy monolithic path (`methyl-validation --stability/--freeze/--model`) is **transitional only** — see [Usage orchestration](usage/04-orchestration-workflow-run.md).

## Related

- [`README.md`](../README.md) — repository landing
- [`DEPLOYMENT.md`](DEPLOYMENT.md) — dev environment setup
