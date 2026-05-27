# MethylPipeline Monorepo

MethylPipeline is a multi-package Python monorepo for methylation analysis workflows, from cohort centroid construction through DMP discovery, biological interpretation, and model validation/deployment.

## What This Repository Includes

- Core statistical path:
  - `methylcentroid`
  - `methyldetector`
  - `methylclassifier`
  - `methylpredictor`
  - `methylvalidation` (workflow orchestrator)
- Biological interpretation:
  - `methylmapper`
  - `methylenricher`
  - `methyldiseaseprogression`
- QC and shared infrastructure:
  - `methylalignmentqc`
  - `methylutils`

## Canonical Documentation Map

- Start here for navigation and reading order:
  - [`docs/index.md`](docs/index.md)
- Environment setup and installation:
  - [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- Full theory/reference book (Quarto):
  - [`docs/theory/README.md`](docs/theory/README.md)
- Workflow-first operational manual (Quarto):
  - [`docs/user-manual/index.qmd`](docs/user-manual/index.qmd)
- Package-local usage and implementation docs:
  - `packages/*/README.md`
  - `packages/*/docs/{USAGE,IMPLEMENTATION,THEORY}.md`

## Primary Workflow Stages

1. `methyl-validation --stability`
   - Monte Carlo centroid+detector iterations
   - Stability aggregation and stable panel generation
   - Optional adaptive early stop via `stability_early_stop_*` convergence settings
2. `methyl-validation --freeze`
   - All-sample rerun with fixed panel
   - Mapper, Enricher, optional DiseaseProgression
   - Mapper annotation cache for observed-hybrid mapped-family model bundles
3. `methyl-validation --model` (or model-MC selection flow)
   - Final model build and predictor validation artifacts
   - Includes aggregated ECDF OvR mode for observed-hybrid `ecdf` backends

Recommended biological gate before final model promotion:

- `methyl-validation biological-readiness <project_root>`

## Quick Start (Host / `.venv`)

```bash
cd /home/ubuntu/MethylPipeline
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e packages/methylutils
```

Install additional packages as needed (or all pipeline packages for full workflows), then run:

```bash
methyl-validation --help
```

## Notes

- This repository expects commands/tests to run in the local `.venv`.
- Many docs overlap by design (theory vs runbook vs package docs); [`docs/index.md`](docs/index.md) identifies which document is the source of truth for each purpose.
