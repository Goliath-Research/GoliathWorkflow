# MethylCentroid Implementation (MethylUtils)

This document describes how MethylCentroid is implemented on top of **MethylUtils**: the builder, data types, I/O, and how the methylcentroid package uses them.

## Architecture Overview

- **MethylUtils** (package `methyl_utils`) provides the core centroid **building** and **data types**.
- **MethylCentroid** (package `methyl_centroid`) provides the **user-facing API**, batch processing, CLI, and project/config resolution; it calls MethylUtils for actual centroid construction and uses MethylUtils types throughout.

```
User / CLI
    → methyl_centroid.MethylCentroid (config, chrom/ctx, samples)
        → methyl_utils.core.centroid_builder.MethylCentroidBuilder
            → add_sample(path) per sample
            → finalize() → MethylExtendedCentroid or MethylBetaBinomialCentroid
        → methyl_utils.core.io.save_to_h5 / load_from_h5
```

## MethylUtils Components

### 1. MethylCentroidBuilder (`methyl_utils.core.centroid_builder`)

The **single** way to build extended centroids in the pipeline:

- **Streaming**: Processes one sample at a time via `add_sample(sample_path)`; no need to load all samples into memory.
- **Position alignment**: Maintains a sorted union of positions; new positions are merged and accumulators updated (GPU or CPU).
- **Accumulators**: Keeps running sums for `N`, `Sx`, `Sx2`, `log_x_sum`, `log_1_minus_x_sum`, and optionally extended stats (`sum_cov`, `sum_mC`, `sum_uC`, `Sx3`, `Sx4`, `count_zero`, `count_one`).
- **GPU**: Uses CuPy when `use_gpu=True` and available; otherwise NumPy. All accumulation is vectorized.
- **Finalize**: `finalize()` applies `min_coverage` filter and returns:
  - **MethylBetaBinomialCentroid** when `store_extended_stats=True` (default): includes count columns for Beta-Binomial and overlap.
  - **MethylExtendedCentroid** when `store_extended_stats=False`: only base sufficient stats (N, Sx, Sx2, log sums).

**Constructor** (simplified):

```python
from methyl_utils.core.centroid_builder import MethylCentroidBuilder

builder = MethylCentroidBuilder(
    min_coverage=4,
    use_gpu=True,
    chunk_size=100_000_000,
    metadata=None,
    store_extended_stats=True,
)
builder.add_sample("/path/to/sample/dir")  # or path to {chrom}-{ctx}.h5
# ... more add_sample() ...
centroid = builder.finalize()  # MethylExtendedCentroid | MethylBetaBinomialCentroid
```

### 2. Convenience function: `build_centroid`

```python
from methyl_utils.core.centroid_builder import build_centroid

centroid = build_centroid(
    sample_paths=["/path/s1", "/path/s2"],
    min_coverage=4,
    use_gpu=True,
    metadata={"chrom": "1", "ctx": "CG"},
    store_extended_stats=True,
)
```

Creates a `MethylCentroidBuilder`, adds all paths, and returns `finalize()`.

### 3. Data types (`methyl_utils.core.methyl_frame`)

- **MethylSample**: Single sample (pos, mC, uC, tnc). Loaded from per-sample HDF5.
- **MethylBasicCentroid**: pos, mC, uC, tnc, N (no Sx/Sx2/log sums). Legacy/simple centroid.
- **MethylExtendedCentroid**: Extends MethylBasicCentroid with **required** fields:
  - N, Sx, Sx2, log_x_sum, log_1_minus_x_sum  
  No count columns (sum_cov, sum_mC, etc.). Supports `.alpha`, `.beta` (Beta MLE from log sums).
- **MethylBetaBinomialCentroid**: Subclass of MethylExtendedCentroid with **required** count columns (sum_cov, sum_mC, sum_uC, sum_cov2, sum_mC2, sum_uC2, Sx3, Sx4, count_zero, count_one). Used when `store_extended_stats=True` in the builder. Supports Beta-Binomial views and `overlap(other)` (e.g. Bhattacharyya).

**Type alias**: `MethylCentroid` in MethylUtils is an alias for `MethylExtendedCentroid` (both basic and Beta-Binomial centroids are instances of MethylExtendedCentroid).

### 4. I/O (`methyl_utils.core.io`)

- **load_from_h5(path)**: Returns `MethylSample`, `MethylBasicCentroid`, `MethylExtendedCentroid`, or `MethylBetaBinomialCentroid` depending on which datasets/attributes are present (e.g. if all Beta-Binomial count columns exist → MethylBetaBinomialCentroid).
- **save_to_h5**: Persists centroid/sample to HDF5; used by methylcentroid package when writing `{chrom}-{ctx}.h5`.

### 5. How the methylcentroid package uses MethylUtils

- **Initial centroid (first sample)** or **CHH streaming path**: Instantiates `MethylCentroidBuilder(min_coverage, use_gpu, store_extended_stats=True)`, calls `add_sample(path)` for each sample, then `finalize()`. Applies optional `min_samples` filter on the result.
- **Incremental add/remove**: For in-memory updates after the first build, uses `MethylExtendedCentroid.add_sample(sample)` and `.remove_sample(sample)` (samples are MethylSample instances loaded via `load_from_h5`).
- **Saving**: Writes the finalized centroid (MethylExtendedCentroid or MethylBetaBinomialCentroid) to `output_dir` as `{chrom}-{ctx}.h5` and saves config/metadata to `{chrom}-{ctx}_config.json`.
- **Dependencies**: Uses MethylUtils for `MethylSample`, `MethylExtendedCentroid`, `MethylCentroidBuilder`, `load_from_h5`, GPU/memory helpers (`is_gpu_available`, `get_memory_manager`), logging (`get_logger`), and optional chunked processing.

## Summary

| Layer | Component | Role |
|-------|-----------|------|
| MethylUtils | MethylCentroidBuilder | Streaming, GPU-capable accumulation; finalize → MethylExtendedCentroid or MethylBetaBinomialCentroid |
| MethylUtils | build_centroid() | One-shot build from list of paths |
| MethylUtils | MethylExtendedCentroid / MethylBetaBinomialCentroid | In-memory centroid type; Beta MLE (alpha, beta); optional count columns for Beta-Binomial |
| MethylUtils | load_from_h5 / save_to_h5 | Load/save samples and centroids |
| MethylCentroid package | MethylCentroid (class) | Config, chrom/ctx, batch, CLI; delegates building to MethylCentroidBuilder and in-memory updates to MethylExtendedCentroid.add_sample/remove_sample |

For theoretical background (distributions and sufficient statistics), see **MethylCentroid_Theoretical_Foundation.md** and **METHYLCENTROID_DISTRIBUTIONS.tex**.
