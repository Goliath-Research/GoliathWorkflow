---
name: RNA-Seq Process Pack
overview: "Add an end-to-end RNA-Seq (transcriptomics) process pack to MethylPipeline: new Parabricks quantification actions (rna_fq2bam and kallisto, selectable like linear/pangenome), a per-sample expression matrix + RNA QC, and downstream wiring of a samples-x-genes matrix into the existing Monte Carlo stability, tabular sklearn classifier, and covariate stacking, reusing the DomainProgram/scheduler/CAAS control plane rather than the methylation centroid/ECDF/Houseman science."
azure_devops:
  type: Feature
  title: "RNA-Seq transcriptomics process pack"
  work_item_id: null
  epic_id: 413
todos:
  - id: modality-refs
    content: Add primary_modality field + rna_reference site assets (schemas, pipeline_config getter, study_init --modality, download_rna_reference script)
    status: completed
    work_item_id: null
  - id: quant-actions
    content: Implement rna_fq2bam_runner and kallisto_runner (Docker pbrun), task models, handlers, capabilities
    status: completed
    work_item_id: null
  - id: rna-qc-express
    content: Add packages/rnaalignmentqc (sample.rna_qc) and packages/rnaexpress (sample.register_expression) + expression_matrix_ref domain schema
    status: completed
    work_item_id: null
  - id: downstream-model
    content: RNA cohort matrix loader (feature_mode rna_expression), pipeline.rna_de_select feature selector, wire tabular_sklearn + covariate stacking, reuse validation.stability
    status: completed
    work_item_id: null
  - id: programs-profiles
    content: Add sample_prep_rnaseq + rnaseq_study_lifecycle programs, rnaseq_research profile, quant_mode/useKallisto resolution in pipeline_profiles.py
    status: completed
    work_item_id: null
  - id: register-deploy-docs
    content: Register actions in action_catalog, regenerate task/config schemas, seed DB, add to deploy script, CI fixtures/tests, docs + promote plan to docs/plans
    status: completed
    work_item_id: null
---

# RNA-Seq Process Pack

> **Status: Implemented** (2026-07). RNA-Seq is a second omics modality alongside DNA methylation. Programs, actions, profiles, packages, schemas, and tests are in the repo; DB seeding (`seed_action_catalog.py`) and `methyl-cfg materialize` run per deployment.

## Goal
Add RNA-Seq as a second analyte modality alongside DNA methylation, reusing the disease-agnostic control plane (DomainProgram, typed actions, cfg/wf, scheduler, CAAS) and replacing only the methylation-specific science.

## Architecture: where RNA-Seq forks from methylation

```mermaid
flowchart TD
  dl[sample.download_fastq] --> mode{modality?}
  mode -->|methylation| meth[fq2bam_meth OR giraffe -> methyl_qc -> methyl_extract -> extraction_qc]
  mode -->|rnaseq| qm{quant_mode?}
  qm -->|star| rfb[sample.parabricks_rna_fq2bam]
  qm -->|kallisto| kal[sample.kallisto]
  rfb --> rqc[sample.rna_qc]
  kal --> rqc
  rqc --> reg[sample.register_expression]
  reg --> arch[archive/cleanup]
  arch --> mc[MC stability: DE feature-select -> tabular sklearn -> covariate stacking]
```

Reused as-is: Monte Carlo orchestration in `packages/methylvalidation`, `covariate_preprocessor` + `ecdf_second_stage` stacking, tabular sklearn, generic alignment metrics, DomainProgram/scheduler/CAAS/QC-gate pattern.
Not reused (methylation-only): `fq2bam_meth`/giraffe, `methyl_extract`, centroid/detector ECDF-on-beta, Houseman/HiTIMED (`packages/methyldeconv`), bisulfite/extraction QC, patterns/info-measures.

## Implemented components

### Phase 1 - Modality + reference assets
- `regulatory.primary_modality` (`methylation` | `rnaseq`) + `normalize_primary_modality` and `ProjectConfig.get_primary_modality()`.
- Site `rna_reference` block (STAR index, GTF, kallisto index, transcriptome FASTA, tx2gene) in `schemas/config/site_manifest.schema.json` + `site_grch38.example.json`; `resolve_rna_reference` + `site_slice_for_action` handling in `action_config_resolver.py`.
- `methyl-study-init --modality`; `scripts/download_rna_reference_grch38.sh`.

### Phase 2 - Alignment/quant actions
- `workers/methyl_worker/rna_fq2bam_runner.py` (`pbrun rna_fq2bam`, STAR gene counts) and `kallisto_runner.py` (`pbrun kallisto`).
- `task_models/rna_prep_models.py`, handlers in `handlers/rna_prep.py`, GPU capabilities `parabricks.rna_fq2bam` / `parabricks.kallisto`.

### Phase 3 - RNA QC + expression registration
- `packages/rnaalignmentqc` (`sample.rna_qc`), `packages/rnaexpress` (`sample.register_expression`), domain schemas `expression_matrix_ref.schema.json` + `rna_sample_ref.schema.json`.

### Phase 4 - Downstream
- `rna_express` cohort matrix loader (`load_expression_matrix`, log-CPM), DE gene selection + tabular classification action `pipeline.rna_de_select`, `feature_mode="rna_expression"` accepted by `MonteCarloConfig`; covariate stacking via `methyl_validation.covariate_preprocessor`.

### Phase 5 - Programs + profiles + config
- `workflow_engine/domain/fixtures/sample_prep_rnaseq.program.json`, `rnaseq_study_lifecycle.program.json`; `workflow_engine/domain/profiles/rnaseq_research.profile.json`.
- `quant_mode` (`star` | `kallisto`) → `useKallisto` resolution in `pipeline_profiles.py` (parallel to `alignment_mode`/`usePangenome`).

### Phase 6 - Registration / deploy / tests / docs
- Actions registered in `action_catalog.py`; `schemas/tasks/*` + `schemas/config/rna_*.schema.json` + `schemas/actions/catalog.json` regenerated.
- `scripts/deploy_workflow_definitions.sh` compiles the RNA programs when present.
- Tests: `workflow_engine/tests/test_rnaseq_sample_prep.py`, `packages/rnaexpress/tests`, `packages/rnaalignmentqc/tests`.

## Key decisions
- Two quantifiers selectable via `quant_mode` (star/kallisto), matching the linear/pangenome pattern.
- Modality is an explicit new field, not a reuse of `primary_analyte`.
- Downstream reuses MC orchestration + tabular sklearn + covariates; DE-based gene selection replaces centroid/ECDF; Houseman/HiTIMED and bisulfite QC are dropped for RNA.
