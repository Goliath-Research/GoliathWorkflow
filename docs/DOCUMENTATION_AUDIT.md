# MethylPipeline Documentation Audit

**Date:** 2026-06-25  
**Scope:** Theory, implementation, usage, deployment, workflow JSON language, SamplePrep QC.

This document is the canonical register of documentation coverage, canonical sources, stale items, and maintenance rules. It was produced as part of a repo-wide documentation remediation.

## Coverage matrix

| Area | Canonical source | Status | Notes |
|------|------------------|--------|-------|
| **Theory** | [`docs/theory/`](theory/) | Strong for core pipeline math | Ch.09 alignment QC + ch.09a extraction QC cover sample prep; ch.14 overlaps user manual |
| **Implementation** | `packages/*/docs/IMPLEMENTATION.md`, [`workflow_engine/docs/pipeline_architecture.md`](../workflow_engine/docs/pipeline_architecture.md) | Good per-package | Split CLIs documented in package READMEs; see [`config_parameter_matrix.md`](config_parameter_matrix.md) |
| **Usage (CLI/stages)** | [`docs/user-manual/`](user-manual/index.qmd) | Complete for prep→blind | Ch.03 sample prep; ch.04 package reference; ch.05–09 stages; ch.14 deployment |
| **Workflow JSON language** | [`domain_program_language.md`](domain_program_language.md) | Standalone reference | Schemas in `schemas/domain/`, `schemas/workflow/` |
| **SamplePrep + QC** | User manual ch.03, [`workflow_engine/sql/SamplePrepFlow.md`](../workflow_engine/sql/SamplePrepFlow.md) | Documented | Picard + Parabricks + extraction guardrails |
| **Deployment** | User manual ch.14, [`deployment/production_runbook.md`](deployment/production_runbook.md) | Dual-backend guide | PostgreSQL + Azure SQL; gateway + workers |
| **Schemas / contracts** | [`schemas/`](../schemas/), [`contracts/openapi.yaml`](../contracts/openapi.yaml), [`workers/WORKER_PROTOCOL.md`](../workers/WORKER_PROTOCOL.md) | Machine-readable | Regenerate via `methyl-export-task-schemas` |

## Canonical doc map (“read this for X”)

| Question | Start here |
|----------|------------|
| How do I set up the dev environment? | [`DEPLOYMENT.md`](DEPLOYMENT.md), user manual ch.01 |
| Where do project configs vs programs live? | User manual ch.02, [`.cursor/rules/work-config-paths.mdc`](../.cursor/rules/work-config-paths.mdc) |
| How does SamplePrep QC work? | User manual ch.03, theory ch.09 |
| How do I run stability/freeze/model? | User manual ch.05–07 |
| How do I author a workflow in JSON? | [`domain_program_language.md`](domain_program_language.md) |
| How do I deploy DB + gateway + workers? | User manual ch.14, [`deployment/production_runbook.md`](deployment/production_runbook.md) |
| What is the REST/worker protocol? | [`workers/WORKER_PROTOCOL.md`](../workers/WORKER_PROTOCOL.md), [`contracts/openapi.yaml`](../contracts/openapi.yaml) |
| What do config keys mean? | Theory ch.13, [`config_parameter_matrix.md`](config_parameter_matrix.md) |
| What is stale vs current? | This file |

## Repository vs `/work` ownership

| **Repository (versioned)** | **`/work/<study>/` (runtime)** |
|----------------------------|--------------------------------|
| `workflow_engine/domain/profiles/*.profile.json` | `configs/project_*.json` |
| `workflow_engine/domain/checks/*/configs/*.program.json` | Sample CSVs, outputs |
| `workflow_engine/domain/fixtures/*.program.json` | `monte_carlo_runs/`, `alignment_qc/` |
| `schemas/`, docs, theory | Per-study artifacts |

Rule: point `methyl-workflow-run --program` at **repo** DomainPrograms; point `--context` / `projectPath` at **`/work`** project JSON.

## Stale-item register

### P0 — fixed in this remediation

| Item | Location | Remediation |
|------|----------|-------------|
| Broken link to `wf_sample_prep_pipeline_seed.sql` (moved to `deprecated/`) | Contract docs, PCa flow docs | Redirect to DomainProgram + `deploy_workflow_definitions.sh` |
| FOREACH “MSSQL-only” claim | `workflow_engine/README.md` | Updated; PostgreSQL `08_foreach_support.sql` documented |
| User manual ch.14 reference before chapter existed | `user-manual/index.qmd` | Added ch.14 deployment chapter |
| Missing `deploy/env/gateway.*.env.example` | `production_runbook.md` | Added example env files |
| Theory `comparison.py` as active path | Theory ch.01, ch.10 | Marked removed/legacy |

### P1 — fixed or marked legacy

| Item | Location | Remediation |
|------|----------|-------------|
| `methylcluster` in analysis doc | `MethylPipeline-analysis.qmd` | Deprecation banner |
| `/home/ubuntu/Work/...` paths | Diagram pack, foreach design | Normalized to `/work/prostate-cancer/` |
| Legacy PCa SQL seed flows | `PCaOvrFlow.md`, `PCaTwoGroupFlow.md` | Deprecated banner + redirect |
| Completed plans without IMPLEMENTED | `production-gpu-worker-layout`, `devops-ci-cd-release` | Status line added |

### P2 — housekeeping (ongoing)

| Item | Action |
|------|--------|
| `pipeline_architecture.md` / `.qmd` / `.html` triplicate | Regenerate via `build_pipeline_architecture_qmd.py`; do not edit `.html` by hand |
| Committed `_book/` render trees | Regenerate after `.qmd` changes: `quarto render docs/user-manual --to pdf` |
| `code_first_discovery_report.md` | Historical snapshot only; do not treat as operator docs |
| `workflow_engine/sql/deprecated/*.sql` | Kept for archaeology; never deploy |

## Maintenance rules

1. **User manual** owns operator commands, stage handoffs, deployment checklists, and artifact gates.
2. **Theory book** owns statistical/method justification and full parameter reference (ch.13).
3. **Package `docs/USAGE.md`** owns CLI flags and package-local outputs; cross-package flows live in the user manual.
4. **DomainProgram language** changes update [`domain_program_language.md`](domain_program_language.md) and `schemas/domain/domain_program.schema.json`.
5. **Worker/task schema** changes run `methyl-export-task-schemas` and `methyl-export-action-catalog`.
6. **Do not duplicate** theory ch.14 and user manual — cross-link; if defaults diverge, fix user manual first.
7. **Regenerate** Quarto books after substantive `.qmd` edits.

## Related documents

- Architecture (workflow-first): [`architecture_review.md`](architecture_review.md)
- Doc index: [`index.md`](index.md)
- Implementation plans (historical): [`plans/README.md`](plans/README.md)
