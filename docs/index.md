# MethylPipeline Documentation

This page maps the documentation system for the monorepo and identifies canonical sources for each audience and task.

## Start Here

- Repository landing page: [`../README.md`](../README.md)
- **Documentation audit (coverage + staleness):** [`DOCUMENTATION_AUDIT.md`](DOCUMENTATION_AUDIT.md)
- **Architecture review (workflow-first):** [`architecture_review.md`](architecture_review.md)
- **DomainProgram language:** [`domain_program_language.md`](domain_program_language.md)
- Environment setup: [`DEPLOYMENT.md`](DEPLOYMENT.md)
- Operational runbook (stage-by-stage): [`user-manual/index.qmd`](user-manual/index.qmd)
- Theory and reference: [`theory/README.md`](theory/README.md)
- **Production deployment:** [`deployment/production_runbook.md`](deployment/production_runbook.md)
- Code-backed configuration matrix: [`config_parameter_matrix.md`](config_parameter_matrix.md)

## Canonical Sources By Purpose

- **Run sample prep (FASTQ → HDF5):**
  - [`user-manual/03-sample-prep-and-qc.qmd`](user-manual/03-sample-prep-and-qc.qmd)
  - [`workflow_engine/sql/SamplePrepFlow.md`](../workflow_engine/sql/SamplePrepFlow.md)
- **Run the analysis pipeline (stability → model):**
  - [`user-manual/index.qmd`](user-manual/index.qmd)
- **Deploy database, gateway, workers:**
  - [`user-manual/14-deployment-and-distributed-workflow.qmd`](user-manual/14-deployment-and-distributed-workflow.qmd)
  - [`deployment/production_runbook.md`](deployment/production_runbook.md)
  - [`workers/WORKER_PROTOCOL.md`](../workers/WORKER_PROTOCOL.md)
  - [`contracts/openapi.yaml`](../contracts/openapi.yaml)
- **Author workflows in JSON:**
  - [`domain_program_language.md`](domain_program_language.md)
- **Understand statistical/method details:**
  - [`theory/index.qmd`](theory/index.qmd)
- **Package-specific CLI/API behavior:**
  - `packages/*/README.md`
  - `packages/*/docs/USAGE.md`
- **Implementation internals:**
  - `packages/*/docs/IMPLEMENTATION.md`
- **Parameter and schema traceability:**
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

1. [`user-manual/index.qmd`](user-manual/index.qmd) — operators
2. [`theory/README.md`](theory/README.md) — methods
3. [`domain_program_language.md`](domain_program_language.md) — workflow authors
4. [`deployment/production_runbook.md`](deployment/production_runbook.md) — production deploy
5. Relevant package docs under `packages/*/docs/`

## Notes On Documentation Ownership

- Theory book and user manual intentionally overlap, but should not diverge in defaults/CLI semantics.
- Package docs should hold package-specific operational details; cross-package workflows should live in user manual/theory workflow chapters.
- Repo vs `/work` layout: user manual ch.02 and [`.cursor/rules/work-config-paths.mdc`](../.cursor/rules/work-config-paths.mdc).
