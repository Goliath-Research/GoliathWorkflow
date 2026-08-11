# MojoFq2bamMeth MVP parity matrix (vs Clara fq2bam_meth)

Capability remains `sample.parabricks_fq2bam` / `parabricks.fq2bam`. Switch with **explicit** `actionConfig.parabricks.engine` (`parabricks` = Clara, `mojo` = MojoFq2bamMeth) — never an automatic consequence of `pangenome_wgbs` Mojo failure. See [`mojo-multi-gpu-dual-align.md`](../architecture/mojo-multi-gpu-dual-align.md).

## Downstream consumers (must match)

| Artifact / field | Used by | Clara | Mojo MVP |
|------------------|---------|-------|----------|
| `{sampleId}.bam` (+ index) | `methyl_extract`, remediation | Yes | Yes (BWA-MEM C2T/G2A) |
| `{sampleId}.json` Parabricks shape | `wgbs_parabricks_qc` | Yes | Yes (shaped subset) |
| `{sampleId}.qc-metrics/` + `.tar` | `methyl_qc` packaging | Yes | Yes |
| `quality_yield.*` | PF / Q30 guardrails | Full | Synthetic from flagstat + defaults |
| `mean_quality_by_cycle.mean_quality` | cycle / post-20 quality | Full | Flat Q36 proxy array |
| `gc_bias_summary.at/gc_dropout` | GC guardrails | Full | Neutral defaults (1.0) |
| `insert_size_metrics.median_insert_size` | insert guardrail | Full | Default 200 until Picard CollectInsertSize |
| `pre_adapter_summaries` Deamination / OxoG | bisulfite proxy | Full | Conservative Deamination=5, OxoG=40 |
| `alignment_summary.mapped_rate` | optional | Often | From `samtools flagstat` |
| `{sampleId}.deduplicate_metrics.txt` | Picard-style | Yes | Optional / empty MVP |
| GPU sort/write | Clara `--gpusort` | Yes | N/A (samtools sort) |

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
