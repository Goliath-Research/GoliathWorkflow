# MethylPipeline Architecture Review

Date: 2026-06-24  
Status: canonical reference for workflow-first migration

## Executive summary

MethylPipeline evolved from per-package CLIs with Pydantic JSON configs, through a monolithic `project.json` + `step_config` orchestration layer (`pipeline_runner.py`), to a **DomainProgram** workflow language executed by a database workflow engine and remote workers. The local **`methyl-workflow-run`** engine now executes the same compiled graphs in-process.

**Target:** DomainProgram JSON defines pipeline architecture (actions, control flow, per-action parameters). `project.json` is a **study manifest** (cohorts, paths, chromosomes, regulatory metadata)—not a hard-coded pipeline blueprint and **not** a tool-parameter store.

## Layer map

| Layer | Artifact | Role |
|-------|----------|------|
| Study manifest | `project.json` / `ProjectConfig` | Cohorts, sample paths, chromosomes, comparisons, stages, `regulatory`, `validation_partitions`, `progression_order` |
| Site manifest | `/work/site/methyl_site.json` | Genomes, GTF, caches, cluster defaults |
| Pipeline profile | `*.profile.json` | Reusable `actionConfig` packs + scope booleans (`runDmpSelection`, `runProgressionAnalysis`, …) |
| Workflow IR | `*.program.json` / `DomainProgram` | `for`, `if`, `parallel`, `do` — pipeline structure |
| Deploy spec | `WorkflowDefinitionSpec` / `compiled_workflow.json` | Nodes, edges, templates, bindings for engine |
| Instance | `context_json` | `projectPath`, `pipelineProfile`, `samples[]`, … |
| Task input | `resolvedConfig` (materialized) | Merged action parameters at worker claim time |
| Execution | Action catalog + `methyl_worker.handlers` | CLI / in-process dispatch |
| Orchestration | DB engine + gateway **or** `LocalWorkflowEngine` | Graph scheduling |

**Storage:** DomainPrograms, profiles, and schemas live in the **git repository** and are documented for users. Study manifests (`project_*.json`), sample CSVs, and run artifacts live on **`/work/<disease>/`** (shared storage). Do not copy `*.program.json` under `/work/.../configs/`.

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

## Study manifest slim-down (four-layer model)

**Keep in study manifest:** `controls`/`diseases`, staged `comparisons`, `chromosomes`, `contexts`, `output_base`, `path_remap`, `regulatory`, `validation_partitions`, `progression_order`, `progression_labels`

**Move to profiles (`actionConfig`):** detection, mapper, enricher, validation MC settings, classifier/predictor tuning, progression scoring options

**Move to site manifest:** genome FASTA, GTF, mapper home, shared cache paths

**Move to programs:** stage ordering, conditional algorithm branches, per-action `stepOverride`

**Removed:** `step_config` on study manifests (schema rejection + CI guard). Legacy files migrate via `scripts/migrate_project_config.py`.

Parameter precedence: instance override → program `with` / `stepOverride` → profile `actionConfig` → analyte defaults (`regulatory.primary_analyte`) → site manifest → package defaults.

See [`docs/plans/simplify-study-config.plan.md`](plans/simplify-study-config.plan.md) for phased rollout.

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
