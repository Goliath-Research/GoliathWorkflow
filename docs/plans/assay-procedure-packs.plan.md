---
name: Assay procedure packs
overview: "Add a third packaging layer—assay procedure packs—between the methylation process pack and disease/trait application packs, so buffy coat (pangenome + informME + deconv + gene FeatureCuts), cfDNA WGBS, and EM-Seq targeted deep become one-click operator presets without encoding disease logic in Python."
azure_devops:
  type: Feature
  title: "Assay procedure packs for methylation analytes"
  work_item_id: null
  epic_id: 413
todos:
  - id: taxonomy-docs
    content: Document assay procedure pack layer (ch.24 + regulatory roadmap + ANALYTE_PROFILES) with buffy/cfDNA/EM-Seq mapping
    status: completed
    work_item_id: null
  - id: procedure-json-resolver
    content: Add profiles/procedures/*.procedure.json + pipelineProcedure merge/validate against primary_analyte
    status: completed
    work_item_id: null
  - id: ship-buffy-cfdna
    content: Ship buffy_wgbs_pangenome_gene_fc and cfdna_wgbs_plasma procedures + CI smokes; linear buffy as alternate
    status: completed
    work_item_id: null
  - id: emseq-seam
    content: "libraryProtocol emseq_targeted + BED/depth SamplePrep fork + cfdna_emseq_targeted procedure"
    status: completed
    work_item_id: null
  - id: retarget-app-packs
    content: Point Alzheimer/plant (and future oncology) application packs at procedure ids instead of re-specifying science knobs
    status: completed
    work_item_id: null
---

# Assay procedure packs for methylation analytes

> **Status: Implemented** (2026-07). Shipped `pipelineProcedure` overlays under
> [`workflow_engine/domain/profiles/procedures/`](../../workflow_engine/domain/profiles/procedures/),
> resolver merge in `pipeline_profiles` / `enrich_instance_context`, EM-Seq SamplePrep
> + panel BAM filter seam, and Alzheimer/plant overlays retargeted to procedure ids.
> Operator guide: [Usage ch.24](../usage/24-methylation-application-packs.qmd).

## Recommendation (short answer)

**Yes — predefine these as named assay procedure packs**, not as new process packs and not as disease application packs.

| Layer | Owns | Operator picks |
|-------|------|----------------|
| **Process pack** | Omics modality (methylation WGBS actions/programs) | `regulatory.primary_modality: methylation` |
| **Assay procedure pack** | Library protocol + SamplePrep + science defaults | e.g. `buffy_wgbs_pangenome_gene_fc` |
| **Application pack** | Indication/trait overlay | e.g. Alzheimer, PCa |
| **Study manifest** | This cohort’s samples and comparisons | `project_*.json` |

## Shipped procedures

| Id | Analyte | Notes |
|----|---------|-------|
| `buffy_wgbs_pangenome_gene_fc` | `buffy_coat` | Default buffy research |
| `buffy_wgbs_linear_gene_fc` | `buffy_coat` | Linear baseline |
| `cfdna_wgbs_plasma` | `cfdna` | No deconv lifecycle |
| `cfdna_emseq_targeted` | `cfdna` | Panel BED + `min_cov` |
| `plant_wgbs_gene_fc` | `plant_tissue` | Plant lifecycle |

## Resolution order

`instance → procedure → profile/mode → analyte → site`

## Key artifacts

- Procedures: `workflow_engine/domain/profiles/procedures/*.procedure.json`
- Schema: `schemas/config/procedure.schema.json`
- Programs: `study_validation_lifecycle_no_deconv.program.json`, `sample_prep_emseq.program.json`
- Tests: `workflow_engine/tests/test_pipeline_procedures.py`
