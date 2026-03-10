# MethylCentroid Theoretical Foundation

## Goal

`MethylCentroid` summarizes a cohort of methylation samples without storing the
full sample-by-position matrix. The centroid stores per-position sufficient
statistics plus an empirical histogram so downstream comparison can stay
ECDF-based.

## Per-sample Quantities

For sample `j` at genomic position `i`:

- `mC_ij`: methylated count
- `uC_ij`: unmethylated count
- `c_ij = mC_ij + uC_ij`: coverage
- `x_ij = mC_ij / c_ij`: methylation fraction in `[0, 1]` when coverage is nonzero

Only samples with coverage at a position contribute to that position's centroid
statistics.

## Stored Sufficient Statistics

For each genomic position, the centroid stores:

- `N`: number of contributing samples
- `Sx = sum(x_ij)`
- `Sx2 = sum(x_ij^2)`
- `Sm = sum(mC_ij)`
- `Su = sum(uC_ij)`
- `Sc2 = sum(c_ij^2)`
- `Swx2 = sum(c_ij * x_ij^2)`

These are enough to derive:

- mean methylation: `mean = Sx / N`
- sample variance of methylation fractions:
  `(Sx2 - Sx^2 / N) / max(N - 1, 1)`
- average counts and several downstream derived summaries

They also preserve enough information for downstream heterogeneity-style
statistics, which is why `Sc2` and `Swx2` remain part of the persisted centroid
schema.

`alpha` and `beta` can still be derived from the stored statistics when a
downstream consumer wants those moments, but they are not the runtime
comparison mode anymore.

## ECDF Histogram

Each centroid must also store a per-position histogram over methylation
fractions:

- `bins`: number of histogram bins
- `bin_counts`: shape `(n_positions, bins)`
- `bin_edges`: reconstructed in memory as uniform edges on `[0, 1]`

`binned_stats_bins` is mandatory and must be `>= 1`. The supported default is
`20`.

The histogram is the empirical distribution used by:

- `MethylCentroidPair`
- `MethylDetector`
- downstream overlap and effect-size calculations

## Why ECDF Only

The current contract intentionally removes runtime switching among Normal, Beta,
Beta-Binomial, and Beta-Mixture comparison modes.

The ECDF-only design has a few benefits:

- It preserves the observed cohort shape instead of forcing a parametric fit.
- It works for skewed, multimodal, or otherwise irregular methylation
  distributions.
- It keeps the build-time and compare-time contracts aligned around one data
  model: sufficient statistics plus empirical histograms.

## Cohort Update Semantics

At the runner level, cohort updates are resolved as:

```text
effective_samples = samples - remove_samples + add_samples
```

That resolved cohort is what gets built and persisted. The final active cohort
is written to:

- HDF5 metadata field `samples_used`
- sidecar config field `samples`

This is the contract used by `MethylValidation` when it emits per-run cohort
deltas.

## Summary

`MethylCentroid` is built around:

- compact sufficient statistics
- required ECDF histogram data
- deterministic cohort updates
- one downstream comparison mode: ECDF
