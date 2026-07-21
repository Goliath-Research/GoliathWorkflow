# Analyte-driven pipeline profiles

> **Modality vs analyte.** `regulatory.primary_modality` (`methylation` | `rnaseq`) selects the **omics process pack** and is distinct from `regulatory.primary_analyte` (the DNA-methylation sample matrix: `cfdna`, `buffy_coat`, `combined`). Modality defaults to `methylation` when unset. The RNA-Seq pack uses its own programs (`sample_prep_rnaseq`, `rnaseq_study_lifecycle`), profile (`rnaseq_research`), and actions (`sample.parabricks_rna_fq2bam` / `sample.kallisto` / `sample.rna_qc` / `sample.register_expression` / `pipeline.rna_de_select`); the analyte packs below apply to the methylation modality only. See [RNA-Seq process pack](usage/20-rnaseq-process-pack.qmd).

> **Disease packs.** A disease pack is a study configuration on the methylation modality (cohorts + partitions + a disease overlay), not new code. Example: the [Alzheimer cfDNA pack](usage/21-alzheimer-cfdna-pack.qmd) — staged Control -> MCI -> AD on `primary_analyte: cfdna` with `mapper.disease_term` = Alzheimer's disease and the `neuro-core` enrichment preset.

Set **`regulatory.primary_analyte`** once in the study manifest (`cfdna`, `buffy_coat`, or `combined`). The resolver merges analyte-specific defaults into profile/site `actionConfig` via `merge_step_config` in `packages/methylutils/methyl_utils/analyte_profiles.py` (explicit profile or site keys always win).

Opt out: `"auto_apply_analyte_profile": false` under `regulatory`.

## What each analyte enables

| Step | `cfdna` | `buffy_coat` | `tissue` |
|------|---------|--------------|----------|
| `alignment_qc` | cfDNA fragmentomics + **alignment guardrails** + bisulfite QC | **alignment guardrails** + bisulfite QC (no cfDNA fragmentomics profile) | bisulfite QC defaults (no analyte pack) |
| `fragmentomics` | `methyl-fragmentomics` enabled (WPS + end motifs) | disabled | disabled |
| `cell_deconvolution` | Houseman 6 Ω, or HiTIMED plasma tree (`tumor_fraction` + immune) | Houseman 6 Ω, or HiTIMED immune subtree (no tumor) | HiTIMED full tumor/immune/stromal tree (flat Houseman stays blood-oriented) |
| `enricher` | `library_preset: cancer-core`; CIS-BP **gene_sets + motif_scan + annotate** | CIS-BP **gene_sets** only | defaults unless profile overrides |
| `validation` | `enforce_training_analyte_match: true` | `false` | not set by analyte pack |

`combined` / unknown analytes: bisulfite QC defaults only.

**`cell_deconvolution` note.** The method switch and analyte-driven HiTIMED tree roots are **not** applied by the analyte profile merge today; set `method` (`houseman` | `hitimed`) under profile `actionConfig.cell_deconvolution`. HiTIMED reads its tree from the `analyte` field, which defaults to `regulatory.primary_analyte`. There is no dedicated `tissue` entry in `analyte_profiles.py`, so tissue prep/enricher steps use `combined`/unknown defaults unless a profile overrides them. See [Theory ch.07a MethylDeconv](theory/chapters/07a-methyldeconv.qmd).

Background research on analyte tradeoffs: [docs/research/](../research/README.md).

## CIS-BP multi-mode (cfDNA)

When the profile sets `cisbp_modes` under `actionConfig.enricher`, the enricher runs modes in order and merges separate libraries:

- `CIS-BP` — gene_sets (1A)
- `CIS-BP-motif` — motif_scan at DMP loci (1C)
- `CIS-BP-annotate` — CIS-BP metadata on ChEA/TRRUST hits (1B; requires TF libraries from `cancer-core`)

## Plasma retrain

Profiles set guards and defaults; they do **not** train a classifier. For cfDNA production models, still run MC/freeze on plasma cohorts with `model_training_analyte: cfdna`. See [PLASMA_RETRAIN_PATH.md](../packages/methylvalidation/docs/PLASMA_RETRAIN_PATH.md).

## Minimal cfDNA study example

Study manifest (cohorts + regulatory only):

```json
{
  "project_name": "Plasma_cfDNA_CG",
  "output_base": "/work/projects/prostate-cancer",
  "samples_base_path": "/work/samples",
  "chromosomes": ["1", "21", "22"],
  "contexts": ["CG"],
  "comparisons": "control_vs_each_disease",
  "regulatory": {
    "primary_analyte": "cfdna",
    "stage": "feasibility"
  },
  "controls": {
    "label": "healthy",
    "groups": [{ "label": "all", "sample_paths": ["data/healthy_p.csv"] }]
  },
  "diseases": {
    "label": "cancer",
    "groups": [{ "label": "pca", "sample_paths": ["data/pca_p.csv"] }]
  }
}
```

Tool parameters (fragmentomics, enricher CIS-BP modes, validation guards) live in profile `actionConfig` — see [`mc_gene_fc.profile.json`](../workflow_engine/domain/profiles/mc_gene_fc.profile.json) or a study-specific overlay, and site defaults in `/work/site/methyl_site.json`.

Example: [`tools/methyl-config-editor/configs/project_Plasma_cfDNA_CG.example.json`](../tools/methyl-config-editor/configs/project_Plasma_cfDNA_CG.example.json).
