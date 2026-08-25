# MojoFq2bamMeth MVP parity matrix (vs Clara fq2bam_meth)

Capability remains `sample.parabricks_fq2bam` / `parabricks.fq2bam`. Switch with **explicit** `actionConfig.parabricks.engine` (`parabricks` = Clara, `mojo` = MojoFq2bamMeth) — never an automatic consequence of `pangenome_wgbs` Mojo failure. See [`mojo-multi-gpu-dual-align.md`](../architecture/mojo-multi-gpu-dual-align.md).

**Production default (linear `engine=mojo`):** FM-index (`METHYLGRAPHER_LINEAR_ENGINE=fm`) on Clara's `${REF}.bwameth.c2t` BWA index, native BGZF BAM, GPU sort + markdup. The frozen k-mer path (`engine=parity`) is a science fallback, not the operator default. Engine contract: sibling mojo-align [`fq2bam-meth/docs/LINEAR_ENGINES.md`](https://dev.azure.com/EpiMethyl/Development/_git/mojo-align?path=/fq2bam-meth/docs/LINEAR_ENGINES.md). QC metrics remain `metrics_source: samtools+placeholders` until Picard enrichment — placeholders are not Clara-equivalent hard fails (see [sample-prep-tooling.md](../architecture/sample-prep-tooling.md)).

## Downstream consumers (must match)

| Artifact / field | Used by | Clara | Mojo (FM default) |
|------------------|---------|-------|-------------------|
| `{sampleId}.bam` (+ index) | `methyl_extract`, remediation | Yes | Yes — FM-index C2T/G2A on `${REF}.bwameth.c2t` |
| `{sampleId}.json` Parabricks shape | `wgbs_parabricks_qc` | Yes | Yes (shaped subset; placeholders where Picard is absent) |
| `{sampleId}.qc-metrics/` + `.tar` | `methyl_qc` packaging | Yes | Yes (packaging present; tables may be placeholder) |
| `quality_yield.*` | PF / Q30 guardrails | Full | Synthetic from flagstat + defaults |
| `mean_quality_by_cycle.mean_quality` | cycle / post-20 quality | Full | Flat Q36 proxy array |
| `gc_bias_summary.at/gc_dropout` | GC guardrails | Full | Neutral defaults (1.0) |
| `insert_size_metrics.median_insert_size` | insert guardrail | Full | Default 200 until Picard CollectInsertSize |
| `pre_adapter_summaries` Deamination / OxoG | bisulfite proxy | Full | Conservative Deamination=5, OxoG=40 |
| `alignment_summary.mapped_rate` | optional | Often | From `samtools flagstat` |
| `{sampleId}.deduplicate_metrics.txt` | Picard-style | Yes | GPU markdup counts; Picard-column file until enrichment |
| GPU sort / markdup | Clara `--gpusort` | Yes | Yes (native GPU sort + markdup; `samtools index` only) |

## GATK 4 / Picard consumer bar (in scope for cutover)

Clara advertises GATK 4 support. Mojo BAMs must be acceptable to the same
downstream tools — not bit-identical, but metric-close:

| Check | Tool | Pass |
|-------|------|------|
| `ValidateSamFile` SUMMARY | GATK4 / Picard | Mojo exit 0 (or no worse than Clara) |
| `PCT_PF_READS_ALIGNED` | CollectAlignmentSummaryMetrics | \|Δ\| ≤ 0.02 vs Clara |
| Insert size median / SD | CollectInsertSizeMetrics | within cohort guardrails |
| Mapped / proper-pair rates | `samtools flagstat` | \|Δ\| ≤ 0.02 / 0.05 |
| Coordinate sort + `@RG` | BAM header | required |
| Duplicate marking | `samtools markdup` (or Picard) | required for QC path |

Harness: `mojo-align/fq2bam-meth/scripts/compare_gatk_picard_metrics.py`
(`GATK_JAR` / `PICARD_JAR` or `gatk` on PATH).

## Still deferred (post map-rate parity)

- Full `CollectMultipleMetrics --gen-all-metrics` tar parity with every Clara table
- BQSR / BaseRecalibrator table bit-match
- Bit-identical BAM vs Clara

## Concordance gates

See [`docs/plans/mojo-fq2bam-concordance-gates.md`](../plans/mojo-fq2bam-concordance-gates.md). Rollback: `engine=parabricks`.

## Comparison arms (originals retained)

Before/after bakeoffs keep Clara `fq2bam_meth` selectable forever (`align.linear.parabricks`). Mojo is preferred science, not a deletion of Clara. Layout + report helpers: [`docs/architecture/sample-prep-tooling.md`](../architecture/sample-prep-tooling.md), plan [`comparison-arms-bakeoff.plan.md`](../plans/comparison-arms-bakeoff.plan.md).

| Gate (2026-08-15) | Status |
|-------------------|--------|
| Clara vs Mojo linear wall (GH200 subset) | **PENDING** operator |
| Linear BAM concordance scripts | Available (`parity_linear_parabricks_vs_mojo.sh`) |
| Production site default flip to Mojo-only | **Not done** (by design) |