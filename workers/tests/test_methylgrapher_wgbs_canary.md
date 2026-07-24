# WGBS pangenome canary (vs linear fq2bam_meth)

Gate production promotion of `buffy_wgbs_pangenome_gene_fc` (`alignmentMode=pangenome_wgbs`)
on an explicit real-sample canary. Do **not** replace the linear path until thresholds pass.

## Inputs

- Same sample FASTQs run through:
  1. `alignmentMode=linear` → `sample.parabricks_fq2bam` + `sample.methyl_extract`
  2. `alignmentMode=pangenome_wgbs` → `sample.methylgrapher_wgbs_align` + `sample.methylgrapher_wgbs_extract`
- Site pins: stock `pangenome` + BS `pangenome_wgbs` (`d9-bs/1.70`) via `METHYL_SITE_CONFIG`
- Image: `METHYL_METHYLGRAPHER_IMAGE` (64K ARM64 smoke via `workers/docker/methylgrapher/smoke_64k.sh`)

## Compare

| Metric | Artifact | Acceptance (operator-set) |
|--------|----------|---------------------------|
| Mapping rate | alignment QC JSON | within agreed delta of linear |
| Duplication rate | `{sample}.deduplicate_metrics.txt` / QC | within agreed delta |
| CpG sites called | `{chrom}-CG.h5` counts | ≥ agreed fraction of linear |
| Mean coverage / beta | H5 summaries | within agreed delta |
| Read-level tiles | `*.patterns.h5` | non-empty when `read_level.enabled` |
| informME inputs | patterns + contexts | loadable by `pipeline.info_measures` |

## Procedure

```bash
source .venv/bin/activate
# 1) 64K image smoke
bash workers/docker/methylgrapher/smoke_64k.sh "$METHYL_METHYLGRAPHER_IMAGE"
# 2) Run both SamplePrep modes on the canary sample (operator study configs)
# 3) Diff QC JSON + H5 counts; record decision under the study output_base
```

Promotion requires documented pass against the operator thresholds above; stock Giraffe
(`alignmentMode=pangenome`) remains available but is **not** a silent fallback when BS
assets are missing.
