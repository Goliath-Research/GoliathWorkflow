# MethylSample Class Hierarchy Documentation

## Overview

The MethylUtils library provides a hierarchical class structure for representing different types of methylation data. The hierarchy separates individual samples from aggregated centroids, with increasing levels of statistical sophistication.

## Class Hierarchy

```
MethylSample (base class)
├── Core methylation data (pos, mC, uC, tnc)
├── Basic sample operations
└── Metadata management

MethylBasicCentroid (inherits from MethylSample)
├── Adds sample count aggregation (N)
├── Centroid aggregation methods
└── Basic centroid operations

MethylCentroid (inherits from MethylBasicCentroid)
├── Adds statistical accumulators (Sx, Sx2, log_x_sum, log_1_minus_x_sum)
├── Beta distribution parameter estimation
└── Advanced statistical analysis methods
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
| `context` | `Optional[str]` | Methylation context from metadata (read/write) |
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

#### Utility Methods
- `to_numpy(extended=False) -> np.ndarray` - Convert to numpy structured array
- `to_dataframe() -> pd.DataFrame` - Convert to pandas DataFrame
- `list_datasets(file_path) -> List[str]` - List HDF5 datasets

#### Factory Methods
- `from_sample_data(pos, mC, uC, tnc) -> MethylSample` - Create from basic data
- `from_centroid_data(centroid_data, metadata=None) -> MethylSample` - Auto-detect and create appropriate type

## 2. MethylBasicCentroid

**Purpose**: Represents basic centroids aggregated from multiple samples.

### Fields (Members)

*Inherits all fields from MethylSample, plus:*

| Field | Type | Description |
|-------|------|-------------|
| `N` | `np.ndarray` (uint32) | Sample counts per position |
| `_metadata` | `Optional[Dict[str, Any]]` | Internal metadata storage (overridden for dataclass ordering) |

### Properties

*Overrides these properties from MethylSample:*

| Property | Type | Description |
|----------|------|-------------|
| `sample_type` | `str` | Returns `"basic_centroid"` |
| `is_centroid` | `bool` | Returns `True` |
| `is_extended_centroid` | `bool` | Returns `False` |

*Inherits all other properties from MethylSample.*

### Methods

*Inherits all methods from MethylSample, plus:*

#### Centroid-Specific Methods
- `get_sample_count() -> Optional[np.ndarray]` - Returns sample counts (N array)
- `add_sample(sample) -> MethylBasicCentroid` - Add sample to centroid
- `remove_sample(sample) -> MethylBasicCentroid` - Remove sample from centroid

#### Statistical Comparison Methods
- `prob_belongs(sample, use_gpu=True) -> float` - Probability sample belongs to centroid
- `z_score(sample, use_gpu=True) -> float` - Z-score distance to centroid
- `p_value(sample, use_gpu=True) -> float` - Statistical significance of difference
- `statistical_test(sample, use_gpu=True) -> Tuple[float, float]` - Combined statistical test

#### Factory Methods
- `create_from_samples(samples, use_gpu=True) -> MethylBasicCentroid` - Create from multiple samples
- `create_centroid_from_samples(samples, use_gpu=True) -> MethylCentroid` - Create extended centroid from samples

## 3. MethylCentroid

**Purpose**: Represents extended centroids with full statistical accumulators for Beta distribution analysis.

### Fields (Members)

*Inherits all fields from MethylBasicCentroid, plus:*

| Field | Type | Description |
|--------|------|-------------|
| `Sx` | `np.ndarray` (float32) | Sum of methylation levels |
| `Sx2` | `np.ndarray` (float32) | Sum of squared methylation levels |
| `log_x_sum` | `np.ndarray` (float32) | Sum of log(methylation_level) for Beta MLE |
| `log_1_minus_x_sum` | `np.ndarray` (float32) | Sum of log(1-methylation_level) for Beta MLE |
| `_metadata` | `Optional[Dict[str, Any]]` | Internal metadata storage (overridden for dataclass ordering) |
| `_cached_alpha` | `Optional[np.ndarray]` | Cached Beta distribution alpha parameter |
| `_cached_beta` | `Optional[np.ndarray]` | Cached Beta distribution beta parameter |
| `_cached_mean` | `Optional[np.ndarray]` | Cached expected methylation level |
| `_cached_variance` | `Optional[np.ndarray]` | Cached methylation level variance |
| `_cached_tau` | `Optional[np.ndarray]` | Cached total concentration (alpha + beta) |

### Properties

*Overrides these properties from MethylBasicCentroid:*

| Property | Type | Description |
|----------|------|-------------|
| `sample_type` | `str` | Returns `"extended_centroid"` |
| `is_extended_centroid` | `bool` | Returns `True` |

*Adds these new statistical properties:*

| Property | Type | Description |
|----------|------|-------------|
| `alpha` | `np.ndarray` | Beta distribution alpha parameter (computed on demand) |
| `beta` | `np.ndarray` | Beta distribution beta parameter (computed on demand) |
| `mean` | `np.ndarray` | Expected methylation level with adaptive estimation |
| `variance` | `np.ndarray` | Methylation level variance |
| `tau` | `np.ndarray` | Total concentration parameter (alpha + beta) |
| `precision` | `np.ndarray` | Precision of methylation estimates |

### Methods

*Inherits all methods from MethylBasicCentroid, plus:*

#### Advanced Statistical Methods
- `get_beta_parameters() -> Tuple[np.ndarray, np.ndarray]` - Get (alpha, beta) parameters
- `clear_statistical_cache()` - Clear cached statistical computations

#### Internal Statistical Methods
- `_compute_beta_parameters() -> Tuple[np.ndarray, np.ndarray]` - Compute Beta parameters using MLE
- `_estimate_beta_params_bounded_extended(n, log_x_sum, log_1mx_sum) -> Tuple[np.ndarray, np.ndarray]` - Bounded MLE estimation

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

### Creating Basic Centroids
```python
from methyl_utils import MethylBasicCentroid

centroid = MethylBasicCentroid(
    pos=np.array([100, 200, 300], dtype=np.uint32),
    mC=np.array([50, 100, 150], dtype=np.uint32),
    uC=np.array([25, 75, 125], dtype=np.uint32),
    tnc=np.array([1, 2, 3], dtype=np.uint8),
    N=np.array([5, 5, 5], dtype=np.uint32),  # 5 samples aggregated
    _metadata={'group': 'control'}
)

print(f"Sample type: {centroid.sample_type}")  # "basic_centroid"
print(f"Is centroid: {centroid.is_centroid}")  # True
print(f"Sample counts: {centroid.get_sample_count()}")  # [5, 5, 5]
```

### Creating Extended Centroids with Statistics
```python
from methyl_utils import MethylCentroid

extended = MethylCentroid(
    pos=np.array([100, 200, 300], dtype=np.uint32),
    mC=np.array([50, 100, 150], dtype=np.uint32),
    uC=np.array([25, 75, 125], dtype=np.uint32),
    tnc=np.array([1, 2, 3], dtype=np.uint8),
    N=np.array([10, 10, 10], dtype=np.uint32),
    Sx=np.array([3.0, 5.0, 7.0], dtype=np.float32),      # Sum of methylation levels
    Sx2=np.array([10.0, 25.0, 49.0], dtype=np.float32),   # Sum of squared levels
    log_x_sum=np.array([0.1, 0.2, 0.3], dtype=np.float32), # Log sums for Beta MLE
    log_1_minus_x_sum=np.array([-0.1, -0.2, -0.3], dtype=np.float32),
    _metadata={'chromosome': 'chr1', 'context': 'CG'}
)

print(f"Sample type: {extended.sample_type}")  # "extended_centroid"
print(f"Alpha parameter: {extended.alpha[0]:.3f}")  # Beta distribution parameters
print(f"Beta parameter: {extended.beta[0]:.3f}")
print(f"Mean methylation: {extended.mean[0]:.3f}")  # Adaptive mean estimation
print(f"Variance: {extended.variance[0]:.3f}")       # Statistical variance
```

### Auto-Detection Factory Method
```python
from methyl_utils import MethylSample

# Dictionary with extended centroid data
centroid_data = {
    'pos': np.array([100, 200]),
    'mC': np.array([50, 100]),
    'uC': np.array([25, 75]),
    'tnc': np.array([1, 2]),
    'N': np.array([10, 10]),
    'Sx': np.array([3.0, 5.0]),
    'Sx2': np.array([10.0, 25.0]),
    'log_x_sum': np.array([0.1, 0.2]),
    'log_1_minus_x_sum': np.array([-0.1, -0.2])
}

# Automatically creates the correct type
obj = MethylSample.from_centroid_data(centroid_data)
print(f"Auto-detected type: {obj.sample_type}")  # "extended_centroid"
print(f"Is instance of MethylCentroid: {isinstance(obj, MethylCentroid)}")  # True
```

## Inheritance and Polymorphism

The hierarchy supports proper inheritance and polymorphism:

```python
# All classes are MethylSample instances
assert isinstance(sample, MethylSample)      # True
assert isinstance(centroid, MethylSample)    # True
assert isinstance(extended, MethylSample)    # True

# Centroids are also MethylBasicCentroid instances
assert isinstance(centroid, MethylBasicCentroid)  # True
assert isinstance(extended, MethylBasicCentroid)  # True

# Extended centroids have additional capabilities
assert extended.is_extended_centroid  # True
assert hasattr(extended, 'alpha')     # True
assert hasattr(extended, 'beta')      # True
```

## Data Type Validation

All classes perform automatic data type validation:

- **MethylSample**: Validates core arrays (pos: uint32, mC: uint32, uC: uint32, tnc: uint8)
- **MethylBasicCentroid**: Validates N array (uint32) in addition to base validation
- **MethylCentroid**: Validates extended arrays (Sx: float32, Sx2: float32, log_x_sum: float32, log_1_minus_x_sum: float32)

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
- Extended centroids include statistical accumulators for Beta distribution analysis

The `load_from_h5()` method automatically detects the data type and returns the appropriate class instance.
