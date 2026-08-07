# MojoFq2bamMeth MVP parity matrix (vs Clara fq2bam_meth)

Capability remains `sample.parabricks_fq2bam` / `parabricks.fq2bam`. Switch with `actionConfig.parabricks.engine`.

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

## Explicitly out of MVP scope

- Full CollectMultipleMetrics / every Picard table Clara emits
- BQSR / BaseRecalibrator
- Bit-identical BAM vs Clara

## Concordance gates

See [`docs/plans/mojo-fq2bam-concordance-gates.md`](../plans/mojo-fq2bam-concordance-gates.md). Rollback: `engine=parabricks`.
