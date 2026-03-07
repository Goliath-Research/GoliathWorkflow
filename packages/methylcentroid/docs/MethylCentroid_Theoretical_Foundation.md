# MethylCentroid Theoretical Foundation

## Overview

MethylCentroid summarizes per-position methylation across a cohort of samples using **sufficient statistics** and a **per-position binned histogram (ECDF)**. The pipeline supports **only the empirical distribution (ECDF)** for downstream comparison and overlap. This design avoids storage of full sample matrices and supports streaming updates and GPU-friendly aggregation.

## Notation

For a genomic position, let the sample index be \(i = 1, \ldots, N\). Let \(mC_i\) and \(uC_i\) be methylated and unmethylated counts. Define:

- **Coverage**: \(n_i = mC_i + uC_i\)
- **Methylation fraction**: \(x_i = mC_i / n_i \in [0, 1]\)

The centroid stores aggregated statistics and a binned histogram at each position.

## Centroid Definition

The centroid mean at position \(i\) is:

$$\mu_i = \frac{1}{N} \sum_{j=1}^{N} x_{ij}$$

The centroid stores **sufficient statistics** and **binned counts** so that the empirical CDF (ECDF) can be used for comparison and overlap without retaining the full sample matrix.

## Statistics Stored

### Core (always present)

| Symbol | Name in code | Definition |
|--------|----------------|------------|
| \(N\) | `N` | \(\sum_i 1\) (number of samples) |
| \(S_x\) | `Sx` | \(\sum_i x_i\) |
| \(S_{x^2}\) | `Sx2` | \(\sum_i x_i^2\) |

Plus position, counts, and context: `pos`, `mC`, `uC`, `tnc` (aggregated appropriately).

### Binned stats (ECDF)

When `binned_stats_bins` > 0 (default 20), the centroid stores per-position histograms:

| Name in code | Definition |
|--------------|------------|
| `bin_edges` | Global edges, e.g. \([0, 0.05, 0.1, \ldots, 1]\) (length `n_bins + 1`) |
| `bin_counts` | Per-position counts per bin (shape `(n_positions, n_bins)`) |

These define an empirical CDF at bin edges. **Spline interpolation** (e.g. PCHIP) is used so that \(F(x)\) and the PDF \(F'(x)\) are defined for any \(x \in [0,1]\).

---

## Supported Distribution: ECDF Only

The pipeline supports **only the empirical distribution (ECDF)** for:

- **Mean**: \(\hat{\mu} = S_x / N\)
- **Variance**: sample variance \((S_{x^2} - S_x^2/N) / \max(N-1, 1)\)
- **Overlap**: between two centroids, overlap is derived from the ECDFs (e.g. \(1 - \mathrm{KS}\) where KS is the Kolmogorov–Smirnov statistic on the interpolated CDFs)
- **Log-probability**: \(\log P(x \mid \text{centroid}) = \log F'(x)\) from the spline derivative
- **P-value**: approximate (e.g. two-sample KS or chi-square on binned counts)

Centroids must be built with `binned_stats_bins` > 0 (default 20) so that binned stats are present. In memory the centroid has `bin_edges` and `bin_counts`; in HDF5 only `methylation_data.attrs["bins"]` and `methylation_data["bin_counts"]` are stored (bin edges are derived as uniform in [0,1]). MethylCentroidPair and MethylDetector use ECDF only; Normal, Beta, Beta-Binomial, and Beta-Mixture distribution options have been removed.

---

## Why Sufficient Statistics + Binned Histogram?

- **Memory**: Storage scales with number of positions and bins, not positions × samples.
- **Streaming**: New samples update aggregates and bin counts without reloading previous samples.
- **GPU**: Vectorized accumulation maps well to GPU kernels (MethylCentroidBuilder).
- **Data-driven**: ECDF uses the actual distribution of the data; no parametric assumption.

## Summary

| What | Stored / used |
|------|----------------|
| Mean, variance | \(N\), \(S_x\), \(S_{x^2}\) |
| ECDF (only supported view) | `bin_edges`, `bin_counts`; spline-interpolated CDF/PDF |

## References

- **Implementation**: MethylUtils `MethylCentroidBuilder`, `MethylCentroid` (data class); comparison via `MethylCentroidPair` using **ECDF only**. Build centroids with `binned_stats_bins` (default 20).
