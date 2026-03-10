# MethylUtils Theoretical Foundation

## Role

`MethylUtils` is the shared mathematical layer for centroid comparison, ECDF overlap, significance testing, and the canonical biological `effect_size`.

## Canonical statistical and biological pipeline

For centroid-to-centroid DMP analysis, MethylUtils now exposes four core pieces:

1. Histogram-derived Mann-Whitney U testing from centroid `bin_counts`.
2. Storey q-value correction.
3. Continuous ECDF overlap from centroid `binned_stats`.
4. The canonical biological score:

   `effect_size = |delta_mean| * (1 - overlap) * exp(-lambda_var * (sqrt(variance1) + sqrt(variance2)))`

## Continuous ECDF overlap

Centroids store binned methylation values. `ECDFView` reconstructs a continuous ECDF over `[0, 1]` with PCHIP interpolation and derives a PDF by differentiating that spline.

Overlap is defined as:

`overlap = integral_0^1 min(f1(x), f2(x)) dx`

This is different from the previous KS-style `1 - D` interpretation. The new overlap directly measures shared support between the two methylation distributions.

## Variance penalty

The reliability term is:

`exp(-lambda_var * (sqrt(variance1) + sqrt(variance2)))`

This keeps the two-group variances separate and penalizes diffuse loci symmetrically without assuming equal variance. These variances are part of the biological reliability term only; the significance test itself remains non-parametric.

## Practical implication

`MethylDetector` and `MethylDetectorExplorer` both delegate their final overlap/effect-size computation to these shared MethylUtils helpers so the score definition is consistent across the pipeline.
