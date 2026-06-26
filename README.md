# MethylPipeline Monorepo

MethylPipeline is a multi-package Python monorepo for methylation analysis workflows, from cohort centroid construction through DMP discovery, biological interpretation, and model validation/deployment.

## Primary workflow (DomainProgram-first)

Studies are orchestrated with **DomainProgram JSON** and the workflow engine:

```bash
source .venv/bin/activate
methyl-workflow-run \
  --program workflow_engine/domain/checks/pca1_5_cg/configs/study_validation_lifecycle.program.json \
  --context '{"projectPath": "/work/<disease>/configs/project_*.json"}'
```

- **Programs and profiles** live in this repository (`workflow_engine/domain/`).
- **Study manifests and artifacts** live on shared storage (`/work/<disease>/`).

Legacy monolithic CLI (`methyl-validation --stability/--freeze/--model`) is still supported; see [Usage manual](docs/usage/index.qmd).

## What This Repository Includes

- Core statistical path: `methylcentroid`, `methyldetector`, `methylclassifier`, `methylpredictor`, `methylvalidation`
- Biological interpretation: `methylmapper`, `methylenricher`, `methyldiseaseprogression`
- QC and shared infrastructure: `methylalignmentqc`, `methylutils`
- Workflow engine: `workflow_engine/`, `workers/`, `methyl-gateway`

## Documentation map

| Audience | Start here |
|----------|------------|
| Everyone | [`docs/index.md`](docs/index.md) — five navigation lenses |
| Operators | [`docs/usage/index.qmd`](docs/usage/index.qmd) |
| Statisticians | [`docs/theory/index.qmd`](docs/theory/index.qmd) |
| Developers | [`docs/implementation/index.md`](docs/implementation/index.md) |
| System design | [`docs/architecture/index.md`](docs/architecture/index.md) |
| Workflow authors | [`docs/reference/domain-program-language.md`](docs/reference/domain-program-language.md) |

- Documentation audit: [`docs/DOCUMENTATION_AUDIT.md`](docs/DOCUMENTATION_AUDIT.md)
- Environment setup: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- Production deployment: [`docs/deployment/production_runbook.md`](docs/deployment/production_runbook.md)

## Quick Start (Host / `.venv`)

```bash
cd /home/ubuntu/MethylPipeline
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e packages/methylutils
```

Install additional packages as needed, then:

```bash
methyl-workflow-run --help
methyl-validation --help
```

## Notes

- Commands and tests must run in the local `.venv`.
- Package docs: `packages/*/docs/{THEORY,IMPLEMENTATION,USAGE}.md` — theory stubs link to the theory book.
