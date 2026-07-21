# Alzheimer cfDNA application pack (example)

Instance of the [methylation application-pack pattern](../../../usage/24-methylation-application-packs.qmd)
(disease application). A **staged (Control -> MCI -> AD)** cfDNA DNA-methylation study
on the existing methylation SaMD control plane. It reuses the standard SamplePrep and
study-lifecycle DomainPrograms, the `samd_*` profile ladder, and the cfDNA analyte
profile. The pack is config + cohorts + partitions + a disease overlay — no new actions
or aligners.

See the operator guide: [Usage ch.21 Alzheimer cfDNA pack](../../../usage/21-alzheimer-cfdna-pack.qmd)
and the shared methylation workflow: [end-to-end workflow](../../../architecture/end-to-end-workflow.md).

## Files

| File | Role |
|------|------|
| `project_Healthy_vs_AD_Stages.json` | Study manifest: Control vs MCI vs AD stages, cfDNA analyte, `methylation` modality, progression labels, partitions (placeholder IDs) |
| `context_alzheimer_cfdna.json` | Disease overlay: `mapper.disease_term=Alzheimer's disease`, `enricher.library_preset=neuro-core`, progression, optional blood-immune covariates |
| `data/*.csv` | Cohort CSV stubs (replace placeholder IDs with real, patient-disjoint sample IDs) |

## Instantiate on /work

Studies live under `/work/projects/<study>/`. Scaffold with the CLI, then copy this
manifest/overlay in:

```bash
methyl-study-init \
  --study-id alzheimer-cfdna \
  --name Healthy_vs_AD_Stages \
  --analyte cfdna \
  --modality methylation \
  --stages 2 \
  --intended-use "Research-use cfDNA methylation classifier for Alzheimer detection." \
  --output-root /work/projects
# then rename the two disease stages to MCI / AD (see this manifest), fill data/*.csv,
# and assign patient-disjoint validation_partitions.
```

## Run the SaMD ladder

```bash
# Research
methyl-workflow-run \
  --program workflow_engine/domain/fixtures/study_validation_lifecycle.program.json \
  --context-file docs/examples/samd/alzheimer-cfdna/context_alzheimer_cfdna.json

# Enrichment (requires non-empty locked_test) -> switch pipelineProfile to samd_holdout_enrichment
# Pivotal (requires non-empty pivotal_validation) -> switch pipelineProfile to samd_pivotal
```

Enrichment uses the `neuro-core` library preset from the enrichment preset registry
(`methyl-cfg sync-library-presets`), not the oncology `cancer-core` default.
