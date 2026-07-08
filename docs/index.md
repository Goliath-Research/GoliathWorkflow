# MethylPipeline Documentation

Navigation hub for the three documentation pillars (Theory, Usage, Implementation) plus cross-cutting reference, architecture, deployment, and regulatory/product-control docs.

**Interactive hub:** [methylpipeline-docs canvas](canvas/methylpipeline-docs.canvas.tsx) — [canvas index](canvas/README.md)

## Start here by role

| Role | Start |
|------|-------|
| **Operator** — run a study end-to-end | [Usage manual](usage/index.qmd) Part II (ch.05–09) |
| **Statistician** — methods and assumptions | [Theory book](theory/index.qmd) — e.g. ch.03 DMP detection |
| **Developer** — engine, workers, compiler | [Implementation guide](implementation/index.md) |
| **Workflow author** — DomainPrograms | [DomainProgram language](reference/domain-program-language.md) + [Architecture: layer model](architecture/layer-model.md) |
| **DevOps** — DB, gateway, workers | [Usage ch.14](usage/14-deployment-and-distributed-workflow.qmd) + [Deployment runbook](deployment/production_runbook.md) |
| **Regulatory / quality** — product controls, evidence, change management | [Regulatory and product controls](regulatory/README.md) |

## Five navigation lenses

### By audience

See table above. Package maintainers: [implementation/packages/](implementation/packages/index.md).

### By pipeline stage

[Architecture: pipeline stages](architecture/pipeline-stages.md) ↔ [Usage ch.03–09](usage/index.qmd)

### By system layer

[Architecture: layer model](architecture/layer-model.md) — manifest → profile → program → instance → worker

### By package

[Package implementation index](implementation/packages/index.md) + `packages/*/docs/{THEORY,IMPLEMENTATION,USAGE}.md`

### By execution mode

[Architecture: orchestration paths](architecture/orchestration-paths.md) — **`methyl-workflow-run` (canonical)** vs legacy `methyl-validation`

## Three pillars

| Pillar | Location | Owns |
|--------|----------|------|
| **Theory** | [`theory/`](theory/index.qmd) | Math, statistics, assumptions, citations |
| **Usage** | [`usage/`](usage/index.qmd) | Commands, artifacts, troubleshooting, deploy |
| **Implementation** | [`implementation/`](implementation/index.md) | Engine, workers, compiler, code paths |

## Cross-cutting

| Area | Location |
|------|----------|
| Architecture | [`architecture/`](architecture/index.md) |
| Reference lookup | [`reference/`](reference/documentation-toolchain.md) |
| Deployment | [`deployment/`](deployment/production_runbook.md) |
| Regulatory / product controls | [`regulatory/`](regulatory/README.md) |
| Plans | [`plans/`](plans/README.md) |
| Cursor canvases | [`canvas/`](canvas/README.md) — versioned `.canvas.tsx`; run `scripts/sync_cursor_canvases.sh` after clone |
| Audit registry | [`DOCUMENTATION_AUDIT.md`](DOCUMENTATION_AUDIT.md) |

## Canonical workflow (DomainProgram-first)

```bash
methyl-workflow-run \
  --program workflow_engine/domain/checks/pca1_5_cg/configs/study_validation_lifecycle.program.json \
  --context '{"projectPath": "/work/<disease>/configs/project_*.json"}'
```

Legacy monolithic path (`methyl-validation --stability/--freeze/--model`) is **transitional only** — see [Usage ch.04 orchestration](usage/04-orchestration-workflow-run.qmd).

## Repository layout

- **Repo:** profiles, DomainPrograms, schemas, docs
- **`/work/<disease>/`:** study manifests, sample CSVs, run artifacts — see [work-config-paths rule](../.cursor/rules/work-config-paths.mdc)

## Related

- [`README.md`](../README.md) — repository landing
- [`DEPLOYMENT.md`](DEPLOYMENT.md) — dev environment setup
