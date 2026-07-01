# Analyte-driven pipeline profiles

Set **`regulatory.primary_analyte`** once in the study manifest (`cfdna`, `buffy_coat`, or `combined`). The resolver merges analyte-specific defaults into profile/site `actionConfig` via `merge_step_config` in `packages/methylutils/methyl_utils/analyte_profiles.py` (explicit profile or site keys always win).

Opt out: `"auto_apply_analyte_profile": false` under `regulatory`.

## What each analyte enables

| Step | `cfdna` | `buffy_coat` |
|------|---------|--------------|
| `alignment_qc` | cfDNA fragmentomics + **alignment guardrails** + bisulfite QC | **alignment guardrails** + bisulfite QC (no cfDNA fragmentomics profile) |
| `fragmentomics` | `methyl-fragmentomics` enabled (WPS + end motifs) | disabled |
| `enricher` | `library_preset: cancer-core`; CIS-BP **gene_sets + motif_scan + annotate** | CIS-BP **gene_sets** only |
| `validation` | `enforce_training_analyte_match: true` | `false` |

`combined` / unknown analytes: bisulfite QC defaults only.

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
