# MethylPipeline Documentation

This page maps the documentation system for the monorepo and identifies canonical sources for each audience and task.

## Start Here

- Repository landing page: [`../README.md`](../README.md)
- **Architecture review (workflow-first)**: [`architecture_review.md`](architecture_review.md)
- **DomainProgram language**: [`domain_program_language.md`](domain_program_language.md)
- Environment setup: [`DEPLOYMENT.md`](DEPLOYMENT.md)
- Operational runbook (stage-by-stage): [`user-manual/index.qmd`](user-manual/index.qmd)
- Theory and reference: [`theory/README.md`](theory/README.md)
- Code-backed configuration matrix: [`config_parameter_matrix.md`](config_parameter_matrix.md)

## Canonical Sources By Purpose

- **Run the pipeline**:
  - [`user-manual/index.qmd`](user-manual/index.qmd)
- **Understand statistical/method details**:
  - [`theory/index.qmd`](theory/index.qmd)
- **Package-specific CLI/API behavior**:
  - `packages/*/README.md`
  - `packages/*/docs/USAGE.md`
- **Implementation internals**:
  - `packages/*/docs/IMPLEMENTATION.md`
- **Parameter and schema traceability**:
  - [`config_parameter_matrix.md`](config_parameter_matrix.md)

## Current Workflow Contract

- `methyl-validation --stability`
  - Per-iteration MC path: `methyl-centroid` -> `methyl-detector`
  - Followed by stability aggregation (optional adaptive stop via `stability_early_stop_*`).
- `methyl-validation --freeze`
  - Production path: `methyl-centroid` -> `methyl-detector` (fixed panel) -> `methyl-mapper` -> `methyl-enricher`
  - Optional `methyl-disease-progression` if enabled in project config.
  - Freeze may also prepare mapper annotation cache artifacts for observed-hybrid mapped-family model builds.
- `methyl-validation --model` / model-selection flow
  - Final model build/selection after freeze artifacts are ready.
  - `ecdf` backend includes aggregated observed-hybrid OvR mode when configured (`ecdf_aggregated_*` + `feature_family_set`).

Biological gate (recommended before final model promotion):

- `methyl-validation biological-readiness <project_root>`

## Reading Order

1. [`user-manual/index.qmd`](user-manual/index.qmd)
2. [`theory/README.md`](theory/README.md)
3. Relevant package docs under `packages/*/docs/`

## Notes On Documentation Ownership

- Theory book and user manual intentionally overlap, but should not diverge in defaults/CLI semantics.
- Package docs should hold package-specific operational details; cross-package workflows should live in user manual/theory workflow chapters.
