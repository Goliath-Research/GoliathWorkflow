# MethylSample Class Hierarchy Documentation

## Overview

The MethylUtils library provides a hierarchical class structure for representing different types of methylation data. The hierarchy separates individual samples from aggregated centroids, with increasing levels of statistical sophistication.

## Important Notes

### Context Property Changes

Due to a property name collision in MethylFrame, the metadata context property has been renamed from `context` to `context_metadata`. This affects:

- **DataFrame context column**: `sample.context` returns a pandas Series with decoded context values ('CG', 'CHG', 'CHH') for filtering
- **Metadata context**: `sample.context_metadata` provides access to the context stored in metadata

**Migration Guide**:
- Replace `sample.context = "CG"` with `sample.context_metadata = "CG"`
- Replace `ctx = sample.context` (metadata access) with `ctx = sample.context_metadata`
- DataFrame filtering like `sample[sample.context == "CG"]` continues to work unchanged

## Class Hierarchy

```
MethylSample (base class)
├── Core methylation data (pos, mC, uC, tnc)
├── Basic sample operations
└── Metadata management

MethylExtendedCentroid (inherits from MethylFrame; single centroid type)
├── Adds sample count and accumulators (N, Sx, Sx2)
├── Optional binned_stats (in memory: bin_edges, bin_counts) for ECDF; H5 stores only methylation_data.attrs["bins"] and methylation_data["bin_counts"]
├── Beta parameters via Method of Moments (MoM) from N, Sx, Sx2
└── Centroid aggregation (add_sample / remove_sample)
```

## 1. MethylSample (Base Class)

**Purpose**: Represents individual methylation samples with basic methylation data.

### Fields (Members)

| Field | Type | Description |
|-------|------|-------------|
| `pos` | `np.ndarray` (uint32) | Genomic positions |
| `mC` | `np.ndarray` (uint32) | Methylated cytosine counts |
| `uC` | `np.ndarray` (uint32) | Unmethylated cytosine counts |
| `tnc` | `np.ndarray` (uint8) | Trinucleotide context + strand info (packed byte) |
| `_metadata` | `Optional[Dict[str, Any]]` | Internal metadata storage |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `sample_type` | `str` | Returns `"sample"` |
| `is_centroid` | `bool` | Returns `False` |
| `is_extended_centroid` | `bool` | Returns `False` |
| `laboratory` | `Optional[str]` | Laboratory name from metadata (read/write) |
| `disease` | `Optional[str]` | Disease type from metadata (read/write) |
| `group` | `Optional[str]` | Group identifier from metadata (read/write) |
| `batch` | `Optional[str]` | Batch identifier from metadata (read/write) |
| `chromosome` | `Optional[str]` | Chromosome from metadata (read/write) |
| `context` | `pd.Series` | DataFrame column with decoded context ('CG', 'CHG', 'CHH') (read-only) |
| `context_metadata` | `Optional[str]` | Methylation context from metadata (read/write) |
| `metadata` | `Optional[Dict[str, Any]]` | Full metadata dictionary (read/write) |
| `samples` | `List[str]` | List of sample identifiers (inherited) |
| `group_name` | `str` | Combined group identifier |
| `position_count` | `int` | Number of genomic positions |
| `memory_usage_mb` | `float` | Memory usage in megabytes |
| `bytes_per_position` | `float` | Bytes per genomic position |

### Methods

#### Data Access Methods
- `get_methylation_levels() -> np.ndarray` - Get methylation levels (mC/(mC+uC))
- `get_coverage() -> np.ndarray` - Get total coverage (mC+uC)
- `get_sample_count() -> Optional[np.ndarray]` - Get sample counts (returns None for base class)
- `median_coverage(*, max_positions=100_000, seed=None) -> float` - Median coverage across positions; uses a random subset when `len(self) > max_positions` for speed (e.g. 80M+ positions). For cohort-level outlier detection.
- `mean_coverage() -> float` - Mean coverage across positions (single-pass O(n)).

#### Resource Management
- `close(free_gpu_pool: bool = False) -> None` - Release references and free memory. Call when done with the sample (e.g. after extraction or when evicting from cache). Idempotent; do not use the instance after calling.

#### Statistical Methods
- `methylation_stats() -> dict` - Basic methylation statistics
- `coverage_stats() -> dict` - Coverage statistics

#### File I/O Methods
- `save_to_h5(file_path, compressed=True, metadata=None) -> Path` - Save to HDF5
- `load_from_h5(file_path, positions=None, debug=False) -> MethylSample` - Load from HDF5
- `load_multiple_chromosomes(pattern) -> Dict[str, MethylSample]` - Load multiple chromosomes

#### Data Manipulation Methods
- `create_aligned_sample(mask) -> MethylSample` - Create aligned sample from boolean mask
- `apply_mask(mask) -> MethylSample` - Apply boolean mask to data
- `create_position_mask(positions) -> np.ndarray` - Create position-based mask
- `merge_contexts() -> MethylSample` - Merge different methylation contexts
- `cap_coverage_binomial(n_cap, *, seed=None) -> MethylSample` - Cap per-CpG coverage by binomial thinning (in-place). For positions with coverage > n_cap, reduces mC/uC by random thinning (p = n_cap/n; mC' ~ Bin(mC,p), uC' ~ Bin(uC,p)) so methylation proportion stays unbiased. Returns self for chaining. Use to correct outlier counts (e.g. after flagging with `compute_coverage_outlier_flags`).
- `median_coverage(*, max_positions=100_000, seed=None) -> float` - Median coverage across positions; uses a random sample of positions when n > max_positions (robust to outliers, cheap).
- `coverage_iqr_n_cap(*, max_positions=100_000, iqr_multiplier=1.5, seed=None) -> (median, upper_fence, n_cap)` - From the same random sample of positions: median, upper fence Q3 + iqr_multiplier*IQR, and n_cap = ceil(upper_fence). Use n_cap as the outlier limit (only positions with coverage above the fence are capped). When IQR=0, n_cap is set from median so we do not cap everything.

#### Utility Methods
- `to_numpy(extended=False) -> np.ndarray` - Convert to numpy structured array
- `to_dataframe() -> pd.DataFrame` - Convert to pandas DataFrame
- `list_datasets(file_path) -> List[str]` - List HDF5 datasets

#### Factory Methods
- `from_sample_data(pos, mC, uC, tnc) -> MethylSample` - Create from basic data
- `from_centroid_data(centroid_data, metadata=None) -> MethylSample` - Auto-detect and create appropriate type

#### Coverage outlier detection (module-level)
- `compute_coverage_outlier_flags(samples, *, method="robust_z", threshold=3.5, max_positions=100_000, seed=None) -> List[bool]` (from `methyl_utils.core.methyl_frame` or `methyl_utils`) — Flags samples with outlying coverage using robust z-score (median, MAD) or IQR. Optionally run this, then cap only flagged samples in place: `for i, s in enumerate(samples): if flags[i]: s.cap_coverage_binomial(n_cap=35, seed=0)`.
- `estimate_n_cap_from_sample_path(path, *, max_positions=100_000, iqr_multiplier=1.5, seed=None) -> int` (from `methyl_utils.core.io` or `methyl_utils`) — Estimate n_cap from one sample file using IQR on a random subset of positions: upper fence = Q3 + 1.5*IQR; positions with coverage above that (e.g. re-sequencing duplicates) are outliers. Returns n_cap = ceil(upper_fence) for use with cap_coverage_binomial. `estimate_n_cap_from_sample_path_with_log` returns (median, upper_fence, n_cap) for logging.

## 2. MethylExtendedCentroid

**Purpose**: Single centroid type: aggregated counts (N, mC, uC) and statistical accumulators (Sx, Sx2) for mean/variance and optional binned ECDF (bin_edges, bin_counts). Beta parameters are computed via Method of Moments (MoM).

### Fields (Members)

*Inherits pos, mC, uC, tnc from MethylFrame; required centroid fields:*

| Field | Type | Description |
|-------|------|-------------|
| `N` | `np.ndarray` (uint32) | Sample counts per position |
| `Sx` | `np.ndarray` (float32) | Sum of methylation levels |
| `Sx2` | `np.ndarray` (float32) | Sum of squared methylation levels |
| `binned_stats` | `Optional[dict]` | If present: `bin_edges`, `bin_counts` for ECDF. In H5, only `methylation_data.attrs["bins"]` and `methylation_data["bin_counts"]` are stored; edges are derived. Basic sample has no bins. |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `sample_type` | `str` | Returns `"extended_centroid"` |
| `is_centroid` | `bool` | Returns `True` |
| `alpha` | `np.ndarray` | Beta alpha (MoM from N, Sx, Sx2) |
| `beta` | `np.ndarray` | Beta beta (MoM) |
| `mean` | `np.ndarray` | Expected methylation level |
| `variance` | `np.ndarray` | Methylation level variance |
| `tau` | `np.ndarray` | Total concentration (alpha + beta) |

### Methods

- `get_sample_count() -> np.ndarray` - Returns N array
- `add_sample(sample)` / `remove_sample(sample)` - Update N, mC, uC, Sx, Sx2 (and binned_counts when binned_stats set)
- `get_beta_parameters() -> Tuple[np.ndarray, np.ndarray]` - Get (alpha, beta)
- Statistical comparison: `prob_belongs`, `z_score`, `p_value`, `statistical_test`

## Usage Examples

### Creating Individual Samples
```python
from methyl_utils import MethylSample
import numpy as np

sample = MethylSample(
    pos=np.array([100, 200, 300], dtype=np.uint32),
    mC=np.array([10, 20, 30], dtype=np.uint32),
    uC=np.array([5, 15, 25], dtype=np.uint32),
    tnc=np.array([1, 2, 3], dtype=np.uint8),
    _metadata={'batch': 'batch1', 'disease': 'healthy'}
)

print(f"Sample type: {sample.sample_type}")  # "sample"
print(f"Methylation levels: {sample.get_methylation_levels()}")  # [0.67, 0.57, 0.55]
```

### Creating Centroids (MethylExtendedCentroid)
```python
from methyl_utils import MethylExtendedCentroid
import pandas as pd

df = pd.DataFrame({
    'pos': [100, 200, 300],
    'mC': [50, 100, 150],
    'uC': [25, 75, 125],
    'tnc': [1, 2, 3],
    'N': [5, 5, 5],
    'Sx': np.array([3.0, 5.0, 7.0], dtype=np.float32),
    'Sx2': np.array([10.0, 25.0, 49.0], dtype=np.float32),
})
centroid = MethylExtendedCentroid(df, metadata={'context': 'CG'})

print(centroid.sample_type)   # "extended_centroid"
print(centroid.alpha[0])      # Beta (MoM)
print(centroid.mean[0])
```

### Auto-Detection on Load

When loading from HDF5, if N, Sx, and Sx2 are present, the loader returns `MethylExtendedCentroid`; otherwise `MethylSample`.

## Inheritance and Polymorphism

- **MethylSample**: base for single-sample data (pos, mC, uC, tnc).
- **MethylExtendedCentroid**: single centroid type (adds N, Sx, Sx2; optional binned_stats); `is_centroid` is True.

## Data Type Validation

- **MethylSample**: Validates pos, mC, uC, tnc (uint32, uint32, uint32, uint8).
- **MethylExtendedCentroid**: Additionally requires N (uint32), Sx (float32), Sx2 (float32).

All arrays must have matching lengths and proper data types or initialization will raise `AssertionError`.

## Memory and Performance

- Uses `@dataclass(slots=True)` for memory efficiency
- Arrays use appropriate NumPy dtypes to minimize memory usage
- Statistical properties are cached on first access
- Supports GPU acceleration for computational methods (where available)

## File Format Compatibility

All classes support HDF5 serialization with automatic type detection on loading:

- Individual samples save/load basic methylation data
- Centroids save/load with sample count information
- Extended centroids include N, Sx, Sx2 and optional binned_stats for ECDF-based analysis (only ECDF is supported)

The `load_from_h5()` method automatically detects the data type and returns the appropriate class instance.
