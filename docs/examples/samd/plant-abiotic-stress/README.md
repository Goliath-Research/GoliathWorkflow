# Plant abiotic stress methylation pack (example)

A **binary Control vs Drought** *Arabidopsis thaliana* leaf WGBS methylation study on the
existing methylation control plane. It reuses the standard SamplePrep and the plant
study-lifecycle DomainProgram, the `samd_research` profile, and the new `plant_tissue`
analyte profile. The pack is config + cohorts + partitions + a trait overlay plus a
non-human site reference — no new actions or aligners.

Unlike a human disease pack, plants need a few platform unblockers that ship with this
pack: the `plant_tissue` analyte (plant-safe QC that treats CG/CHG/CHH as real biology,
no cfDNA fragmentomics), a linear TAIR10 site reference, a lifecycle program **without**
blood cell deconvolution, and the `plant-stress-core` enrichment preset.

See the operator guide: [Usage ch.23 Plant abiotic stress pack](../../../usage/23-plant-abiotic-stress-pack.qmd),
the analyte defaults in [ANALYTE_PROFILES](../../../ANALYTE_PROFILES.md), and the plant
epigenomics background in [Plant Research](../../../research/Plant%20Research.md).

## Files

| File | Role |
|------|------|
| `project_Control_vs_Drought.json` | Study manifest: Control vs Drought, `plant_tissue` analyte, `methylation` modality, CG/CHG/CHH contexts, Arabidopsis chromosomes 1-5, partitions (placeholder IDs) |
| `context_plant_abiotic_stress.json` | Trait overlay: `enricher.library_preset=plant-stress-core`, `organism=Arabidopsis_thaliana`, `string_species=3702`, `mapper.enrich_disease=false` (no human disease priors), progression off |
| `data/*.csv` | Cohort CSV stubs (replace placeholder IDs with real, plant-disjoint sample IDs) |

## Provision the TAIR10 reference (once per cluster)

Plants align linear only (no HPRC pangenome). Pin the genome + GTF in a site manifest and
provision the assets:

```bash
scripts/download_arabidopsis_tair10.sh
export METHYL_SITE_CONFIG=workflow_engine/domain/profiles/site_tair10.example.json
```

The site example (`site_tair10.example.json`) pins
`Arabidopsis_thaliana.TAIR10.dna.toplevel.fa` and `Arabidopsis_thaliana.TAIR10.58.gtf`
under `/work/genomes`.

## Instantiate on /work

Studies live under `/work/projects/<study>/`. Scaffold with the CLI, then copy this
manifest/overlay in:

```bash
methyl-study-init \
  --study-id plant-abiotic-stress \
  --name Control_vs_Drought \
  --analyte plant_tissue \
  --modality methylation \
  --binary \
  --intended-use "Research-use Arabidopsis drought methylation study." \
  --output-root /work/projects
# then fill data/*.csv and assign plant-disjoint validation_partitions.
```

## Run

```bash
methyl-workflow-run \
  --program workflow_engine/domain/fixtures/plant_stress_study_lifecycle.program.json \
  --context-file docs/examples/samd/plant-abiotic-stress/context_plant_abiotic_stress.json
```

Enrichment uses the `plant-stress-core` library preset from the enrichment preset
registry (`methyl-cfg sync-library-presets`), not the oncology `cancer-core` default.
Human-symbol Enrichr libraries do not map to Arabidopsis AGI locus IDs, so for true
Arabidopsis/crop term enrichment supply a custom plant GMT via
`actionConfig.enricher.libraries`; `plant-stress-core` (organism-general GO terms) is the
discovery default. Cell deconvolution is not run (blood-only bases); the plant lifecycle
program omits that node.

## Extending to other crops

Soybean, maize, or wheat reuse this pack by swapping the site reference pins (FASTA + GTF,
chromosome list, `string_species` taxon — e.g. 3847 soybean) and cohort CSVs. No code or
program changes are required.
