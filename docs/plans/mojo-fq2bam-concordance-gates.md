# MojoFq2bamMeth concordance gates (vs Clara)

| Gate | How | Pass |
|------|-----|------|
| Flagstat mapped-rate | Same sample, Clara vs Mojo | \|Δ\| ≤ 0.02 |
| MethylExtract CpG | Top-N CpG β / coverage Spearman | ≥ 0.95 |
| Wall time | Same SKU class (NVIDIA or AMD) | Mojo ≤ Clara × 1.25 (or absolute SLA) |
| QC overall_pass | `methyl-qc` on Mojo metrics JSON | Pass with site thresholds |
| AMD + NVIDIA | Both green on same sample | Required before fleet cutover |

## Runner

```bash
source .venv/bin/activate
# After both arms produce sampleDir_linear_clara/ and sampleDir_linear_mojo/
python scripts/compare_mojo_fq2bam_vs_clara.py \
  --clara-dir /work/samples/SAMPLE/linear_clara \
  --mojo-dir /work/samples/SAMPLE/linear_mojo \
  --sample-id SAMPLE
```

Rollback: `actionConfig.parabricks.engine=parabricks`.
