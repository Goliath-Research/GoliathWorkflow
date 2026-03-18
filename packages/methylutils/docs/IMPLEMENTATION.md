# MethylUtils Implementation

## Relevant modules for the ECDF effect-size pipeline

- `methyl_utils/statistical_tests.py`
  Owns the shared Mann-Whitney U test from centroid histograms, continuous ECDF overlap integration, canonical `effect_size` computation, and `lambda_var` optimization helper.
- `methyl_utils/core/distribution_views.py`
  Implements `ECDFView`, including PCHIP-based CDF/PDF evaluation and batched PDF sampling for overlap integration.
- `methyl_utils/methyl_centroid_pair.py`
  Loads and aligns centroids, computes per-position summary statistics, and delegates effect-size math to the shared helpers instead of maintaining a separate score formula.

## Shared contract

Downstream packages should treat the following as the canonical comparison flow:

1. Build or load centroids with `binned_stats`.
2. Run histogram-derived Mann-Whitney U testing on aligned centroid histograms.
3. Apply Storey q-value correction.
4. Compute continuous overlap only for the reduced set of positions that still matter.
5. Compute `effect_size` with the single canonical formula.

## Exported helper surface

The public `methyl_utils` package now exports:

- `mann_whitney_from_bin_counts()`
- `ecdf_overlap_integral()`
- `effect_size_from_components()`
- `ecdf_effect_size()`
- `optimize_lambda_var()`

These functions are the intended shared entry points for detector/explorer style analyses.
