# MethylDetector Theoretical Foundation

## Goal

`MethylDetector` identifies differential methylation with a staged pipeline that separates statistical significance from biological importance:

1. Welch-style unequal-variance mean-difference testing.
2. Storey q-value correction.
3. `delta_mean` reduction to keep continuous ECDF work tractable.
4. Continuous ECDF overlap and final `effect_size`.
5. Biological filtering on `delta_mean`, `overlap`, and `effect_size`.

## Statistical Stage

For each aligned position, MethylUtils computes a Welch-style test statistic and two-sided p-value using the per-group means, variances, and sample counts. Multiple testing is controlled with Storey q-values.

Positions with `q_value <= alpha` are the statistical DMP candidates.

## Biological Score

The pipeline uses one canonical biological score:

`effect_size = |delta_mean| * (1 - overlap) * exp(-lambda_var * (sqrt(variance1) + sqrt(variance2)))`

Where:

- `delta_mean = |mean1 - mean2|`
- `overlap = integral_0^1 min(f1(x), f2(x)) dx`
- `f1`, `f2` are the PCHIP-derived PDFs built from centroid `binned_stats`
- `lambda_var` controls how strongly diffuse within-group distributions are penalized

Interpretation:

- Larger `delta_mean` increases the score.
- Larger overlap decreases the score.
- Larger within-group variance decreases the score symmetrically in both groups.

## Why the reduction gate comes before overlap

The continuous overlap stage depends on `PchipInterpolator`, which is CPU-bound. At chromosome scale, evaluating every statistically significant position would be too expensive, so the detector applies a `delta_mean` reduction gate before any continuous overlap/effect-size calculation.

## Summary

| Component | Role |
|-----------|------|
| Statistical test | Welch-style unequal-variance mean-difference test |
| Multiple testing | Storey q-values |
| Reduction gate | `delta_mean_reduction` or `min_delta_mean` |
| Overlap | Continuous ECDF overlap from PCHIP-derived PDFs |
| Biological score | Canonical `effect_size` formula |
| Final biological filters | `min_delta_mean`, `max_overlap`, `min_effect_size`, optional `effect_size_quantile` |
