# Analyte-driven pipeline profiles

Set **`step_config.validation.regulatory.primary_analyte`** once (`cfdna`, `buffy_coat`, or `combined`). The pipeline fills missing step defaults from a profile via [`ProjectConfig.get_step_config`](../packages/methylutils/methyl_utils/pipeline_config.py) (deep setdefault: explicit JSON always wins).

Opt out: `"auto_apply_analyte_profile": false` under `regulatory`.

## What each analyte enables

| Step | `cfdna` | `buffy_coat` |
|------|---------|--------------|
| `alignment_qc` | cfDNA fragmentomics guardrails; bisulfite QC | bisulfite QC only (no cfDNA fragmentomics profile) |
| `fragmentomics` | `methyl-fragmentomics` enabled (WPS + end motifs) | disabled |
| `enricher` | `library_preset: cancer-core`; CIS-BP **gene_sets + motif_scan + annotate** | CIS-BP **gene_sets** only |
| `validation` | `enforce_training_analyte_match: true` | `false` |

`combined` / unknown analytes: bisulfite QC defaults only.

Background research on analyte tradeoffs: [docs/research/](../research/README.md).

## CIS-BP multi-mode (cfDNA)

When the profile sets `cisbp_modes`, the enricher runs modes in order and merges separate libraries:

- `CIS-BP` — gene_sets (1A)
- `CIS-BP-motif` — motif_scan at DMP loci (1C)
- `CIS-BP-annotate` — CIS-BP metadata on ChEA/TRRUST hits (1B; requires TF libraries from `cancer-core`)

## Plasma retrain

Profiles set guards and defaults; they do **not** train a classifier. For cfDNA production models, still run MC/freeze on plasma cohorts with `model_training_analyte: cfdna`. See [PLASMA_RETRAIN_PATH.md](../packages/methylvalidation/docs/PLASMA_RETRAIN_PATH.md).

## Minimal cfDNA project example

```json
{
  "step_config": {
    "alignment_qc": { "genome_fasta": "/ref/hg38.fa" },
    "mapper": { "gtf": "/ref/annotation.gtf" },
    "validation": {
      "regulatory": {
        "primary_analyte": "cfdna",
        "stage": "feasibility"
      }
    }
  }
}
```

See [`tools/methyl-config-editor/configs/project_Plasma_cfDNA_CG.example.json`](../tools/methyl-config-editor/configs/project_Plasma_cfDNA_CG.example.json).
