# MethylPipeline Architecture Review

Date: 2026-06-24  
Status: canonical reference for workflow-first migration

## Executive summary

MethylPipeline evolved from per-package CLIs with Pydantic JSON configs, through a monolithic `project.json` + `step_config` orchestration layer (`pipeline_runner.py`), to a **DomainProgram** workflow language executed by a database workflow engine and remote workers. The local **`methyl-workflow-run`** engine now executes the same compiled graphs in-process.

**Target:** DomainProgram JSON defines pipeline architecture (actions, control flow, per-action parameters). `project.json` is a **study manifest** (cohorts, paths, chromosomes)—not a hard-coded pipeline blueprint.

## Layer map

| Layer | Artifact | Role |
|-------|----------|------|
| Study manifest | `project.json` / `ProjectConfig` | Cohorts, sample paths, chromosomes, `output_base` |
| Workflow IR | `*.program.json` / `DomainProgram` | `for`, `if`, `parallel`, `do` — pipeline structure |
| Deploy spec | `WorkflowDefinitionSpec` / `compiled_workflow.json` | Nodes, edges, templates, bindings for engine |
| Instance | `context_json` | `projectPath`, `samples[]`, `isCfdna`, … |
| Execution | Action catalog + `methyl_worker.handlers` | CLI / in-process dispatch |
| Orchestration | DB engine + gateway **or** `LocalWorkflowEngine` | Graph scheduling |

## Orchestration path matrix

| Path | Entry | Status |
|------|-------|--------|
| **Workflow (canonical)** | `methyl-workflow-run`, `methyl-validation run-workflow` | Preferred |
| Distributed workflow | `methyl-gateway` + `methyl-worker` | Production cluster |
| Monolithic CLI | `methyl-validation --stability/--freeze/--model` | Legacy (`--legacy-orchestration`) |
| File queue | `methyl-validation plan-runs` / `run-task` | Legacy distributed MC |
| Direct package CLIs | `methyl-centroid`, `methyl-detector`, … | Supported for single steps |

## Canonical workflow programs

| Program | Purpose |
|---------|---------|
| `workflow_engine/domain/fixtures/sample_prep.program.json` | Per-sample QC, remediation, extract, archive |
| `workflow_engine/domain/checks/pca1_5_cg/configs/pca1_5_mc_stability*.program.json` | MC stability |
| `workflow_engine/domain/checks/pca1_5_cg/configs/study_validation_lifecycle.program.json` | Full study lifecycle |

Deploy compiled specs: `scripts/deploy_workflow_definitions.sh`

## Deprecated SQL seeds

Marked deprecated in `workflow_engine/README.md`: `workflow_methylvalidation_seed.sql`, `wf_pca_*`, `wf_sample_prep_pipeline_seed.sql`. Use DomainProgram compile + deploy.

## project.json slim-down

**Keep:** `control`/`disease`, `comparisons`, `chromosomes`, `contexts`, `output_base`, `path_remap`  
**Move to programs:** stage ordering, conditional algorithm branches, per-action `stepOverride`  
**Deprecate:** `step_config.validation.run_mapper_and_enricher`, `skip_enricher`, `step_config.validator` alias

Parameter precedence: program `with` > `step_config` > analyte profile defaults.

## Purge register

### Tier A (removed)

- `packages/methylutils/comparison.py`
- `packages/methylutils/methyl_utils/centroid_pair.py`
- `packages/methylutils/methyl_utils/modeling/`
- `packages/methylcluster/methyl_cluster/methyl_cluster_dp.py`
- `packages/methylutils/methyl_utils/health_discovery.py`

### Tier B (after program parity)

- `pipeline_runner.py` orchestration loops
- `methylcluster` package
- Legacy SQL workflow seeds
- Azure SQL `DMPMapper` non-`--project` path

### Tier C (documentation)

- `docs/Next Steps.md`, `docs/theory/DOCUMENTATION_PLAN.md` — archived
- User manual orchestration chapters → DomainProgram + `methyl-workflow-run`

## Related docs

- [DomainProgram language](domain_program_language.md)
- [Pipeline architecture](../workflow_engine/docs/pipeline_architecture.md)
- [Config parameter matrix](config_parameter_matrix.md)
- [Code-first discovery report](code_first_discovery_report.md)
