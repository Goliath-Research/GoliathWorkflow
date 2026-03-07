# MethylCentroid Implementation (MethylUtils)

This document describes how MethylCentroid is implemented on top of **MethylUtils**: the builder, data types, I/O, and how the methylcentroid package uses them. **Only the ECDF distribution is supported**; Normal, Beta, Beta-Binomial, and Beta-Mixture have been removed.

## Architecture Overview

- **MethylUtils** (package `methyl_utils`) provides the core centroid **building** and **data types**.
- **MethylCentroid** (package `methyl_centroid`) provides the **user-facing API**, batch processing, CLI, and project/config resolution; it calls MethylUtils for actual centroid construction and uses MethylUtils types throughout.

```
User / CLI
    → methyl_centroid.MethylCentroid (config, chrom/ctx, samples)
        → methyl_utils.core.centroid_builder.MethylCentroidBuilder
            → add_sample(path) per sample
            → finalize() → MethylCentroid
        → methyl_utils.core.io.save_to_h5 / load_from_h5
```

## MethylUtils Components

### 1. MethylCentroidBuilder (`methyl_utils.core.centroid_builder`)

The **single** way to build extended centroids:

- **Streaming**: Processes one sample at a time via `add_sample(sample_path)`.
- **Position alignment**: Maintains a sorted union of positions; new positions are merged and accumulators updated (GPU or CPU).
- **Accumulators**: N, Sx, Sx2, mC_sum, uC_sum, and **bin_edges** / **bin_counts** (binned histogram for ECDF). Number of bins is set by `binned_stats_bins` (default 20 in MethylCentroid).
- **GPU**: Uses CuPy when `use_gpu=True` and available.
- **Finalize**: `finalize()` applies `min_coverage` filter and returns **MethylCentroid** with core columns and binned_stats (bin_edges, bin_counts).

**Constructor** (simplified):

```python
from methyl_utils.core.centroid_builder import MethylCentroidBuilder

builder = MethylCentroidBuilder(
    min_coverage=4,
    use_gpu=True,
    chunk_size=100_000_000,
    metadata=None,
    binned_stats_bins=20,
)
builder.add_sample("/path/to/sample/dir")  # or path to {chrom}-{ctx}.h5
# ... more add_sample() ...
centroid = builder.finalize()  # MethylCentroid
```

### 2. Convenience function: `build_centroid`

```python
from methyl_utils.core.centroid_builder import build_centroid

centroid = build_centroid(
    sample_paths=["/path/s1", "/path/s2"],
    min_coverage=4,
    use_gpu=True,
    metadata={"chrom": "1", "ctx": "CG"},
    binned_stats_bins=20,
)
```

### 3. Data types (`methyl_utils.core.methyl_frame`)

- **MethylSample**: Single sample (pos, mC, uC, tnc). Loaded from per-sample HDF5.
- **MethylCentroid**: The only centroid type. Fields: pos, tnc, N, Sx, Sx2, Sm, Su, Sc2, Swx2. Required **binned_stats** (bin_edges, bin_counts) for ECDF. Beta parameters (alpha, beta) are derived via method-of-moments from N, Sx, Sx2 when needed; **comparison and overlap use ECDF only**.

The centroid data class in MethylUtils is **MethylCentroid** (single type).

### 4. I/O (`methyl_utils.core.io`)

- **load_from_h5(path)**: Returns `MethylSample` or `MethylCentroid` depending on presence of full centroid schema (N, Sx, Sx2, Sm, Su, Sc2, Swx2). Binned stats required for centroids.
- **save_to_h5**: Persists centroid/sample to HDF5; writes only the current schema (no log sums or Beta-Binomial columns).

### 5. How the methylcentroid package uses MethylUtils

- **Build**: Instantiates `MethylCentroidBuilder(min_coverage, use_gpu, binned_stats_bins=20)`, calls `add_sample(path)` for each sample, then `finalize()`. Applies optional `min_samples` filter on the result.
- **Incremental add/remove**: Uses `MethylCentroid.add_sample(sample)` and `.remove_sample(sample)` for in-memory updates.
- **Saving**: Writes the finalized MethylCentroid to `output_dir` as `{chrom}-{ctx}.h5` with binned_stats when bins > 0.
- **Distribution**: Only **ECDF** is used for comparison and overlap (MethylCentroidPair, MethylDetector).

## Summary

| Layer | Component | Role |
|-------|-----------|------|
| MethylUtils | MethylCentroidBuilder | Streaming, GPU; finalize → MethylCentroid with binned_stats |
| MethylUtils | MethylCentroid | Single centroid type; N, Sx, Sx2, Sm, Su, Sc2, Swx2, binned_stats; ECDF only for comparison |
| MethylUtils | load_from_h5 / save_to_h5 | Load/save samples and centroids |
| MethylCentroid package | MethylCentroid (class) | Config, chrom/ctx, batch, CLI; delegates to MethylCentroidBuilder |

For theoretical background (ECDF, sufficient statistics), see **MethylCentroid_Theoretical_Foundation.md**.
