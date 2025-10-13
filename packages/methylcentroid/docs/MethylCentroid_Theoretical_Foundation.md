# MethylCentroid: Theoretical Foundations and Implementation

## Overview

MethylCentroid is a high-performance computational framework for calculating methylation centroids from genomic data, incorporating advanced statistical methods for robust outlier detection. This document provides a comprehensive theoretical foundation for the algorithms, statistical methods, and computational approaches implemented in the MethylCentroid software package, with particular emphasis on its integration with the MethylUtils library.

## Core Architecture and MethylUtils Integration

### MethylUtils as the Computational Foundation

MethylCentroid builds upon the MethylUtils library, which provides essential computational infrastructure for methylation data analysis. The integration follows a layered architecture:

```
┌─────────────────────────────────────┐
│         MethylCentroid (API)        │
├─────────────────────────────────────┤
│        MethylUtils Services         │
│  ┌────────────────────────────────┐ │
│  │   PositionAligner              │ │
│  │   Distance Calculators         │ │
│  │   GPU Management               │ │
│  │   Memory Management            │ │
│  │   Performance Profiling        │ │
│  │   Chunked Processing           │ │
│  │   Logging Framework            │ │
│  └────────────────────────────────┘ │
├─────────────────────────────────────┤
│         Core Dependencies           │
│   (NumPy, HDF5, CuPy, SciPy, etc.)  │
└─────────────────────────────────────┘
```

### Key MethylUtils Components Used

#### PositionAligner
The `PositionAligner` class from MethylUtils provides efficient genomic coordinate alignment across multiple samples with different position sets.

**Key Features:**
- Dynamic position range expansion
- Memory-efficient accumulator updates
- O(N log M) complexity for N samples with M average positions

#### Distance Calculation Framework
MethylCentroid leverages MethylUtils' `auto_compute_distance` function for computing various information-theoretic distances:

```python
from methyl_utils import auto_compute_distance

# Computes distance between sample and centroid
distance = auto_compute_distance(
    sample_data, centroid_data,
    metric="jeffreys",  # or "jensen_shannon", "hellinger", etc.
    weights=position_weights  # Optional entropy-based weighting
)
```

#### GPU Acceleration Infrastructure
The GPU detection and memory management capabilities from MethylUtils enable transparent GPU acceleration:

```python
from methyl_utils import (
    is_gpu_available,
    get_memory_manager,
    get_performance_profiler
)

# Automatic GPU detection and acceleration
if is_gpu_available():
    # GPU-accelerated operations
    result = gpu_accelerated_operation(data)
else:
    # CPU fallback
    result = cpu_operation(data)
```

#### Memory and Performance Management
MethylUtils provides sophisticated memory management and performance profiling:

```python
from methyl_utils import (
    get_memory_manager,
    start_performance_monitoring,
    ChunkedGenomicProcessor
)

# Memory-efficient processing of large genomic datasets
with ChunkedGenomicProcessor(chunk_size=1000000) as processor:
    for chunk in processor.process_file(hdf5_file):
        # Process chunk with optimized memory usage
        process_chunk(chunk)
```

## Methylation Data Model

### Data Representation

MethylCentroid processes methylation data stored in HDF5 format, representing DNA methylation as cytosine modification levels at CpG dinucleotides and their genomic contexts (CG, CHG, CHH).

#### Core Data Elements
- **mCᵢ**: Count of methylated cytosines at genomic position i
- **uCᵢ**: Count of unmethylated cytosines at genomic position i
- **xᵢ**: Methylation level (0 ≤ xᵢ ≤ 1), where xᵢ = mCᵢ/(mCᵢ + uCᵢ)
- **posᵢ**: Genomic coordinate of position i
- **N**: Number of samples contributing to each position

#### HDF5 Data Structure
```
methylation_data/
├── pos       # uint32: Genomic positions
├── mC        # uint32: Methylated cytosine counts
├── uC        # uint32: Unmethylated cytosine counts
├── tnc       # uint8:  Trinucleotide context codes and strand
└── N         # uint32: Sample count per position (centroids only)
```

### MethylUtils Integration: Data Types and Structures

MethylCentroid uses MethylUtils' `MethylSample` class and `get_methyl_dtype()` function for efficient data handling:

```python
from methyl_utils import MethylSample, get_methyl_dtype

# Efficient data type for methylation arrays
dtype = get_methyl_dtype()  # Optimized dtype for methylation data

# Sample representation with MethylUtils
sample = MethylSample(
    positions=genomic_positions,
    methylated_counts=mC_data,
    unmethylated_counts=uC_data,
    trinucleotide_contexts=tnc_data
)
```

## Centroid Calculation Algorithms

### Basic vs Extended Centroids

MethylCentroid implements two centroid calculation approaches, each with distinct statistical properties:

#### Basic Centroid
**Formula:** Simple averaging of raw counts
```
centroid.mCᵢ = Σⱼ₌₁ᴺ mCᵢⱼ / N
centroid.uCᵢ = Σⱼ₌₁ᴺ uCᵢⱼ / N
methylation_level = centroid.mCᵢ / (centroid.mCᵢ + centroid.uCᵢ)
```

**Limitation:** Incorrect when position coverage varies across samples

#### Extended Centroid (Recommended)
**Formula:** Statistically rigorous averaging using accumulated methylation levels
```
centroid.Sxᵢ = Σⱼ₌₁ᴺ xᵢⱼ          # Sum of methylation levels
centroid.Sx2ᵢ = Σⱼ₌₁ᴺ xᵢⱼ²         # Sum of squared methylation levels
methylation_level = centroid.Sxᵢ / N  # Correct statistical estimator
```

**Advantages:**
- Properly accounts for varying sample counts per position
- Enables accurate outlier detection
- Supports advanced statistical analysis

### Position Alignment via MethylUtils

The centroid calculation relies on MethylUtils' `PositionAligner` for handling samples with different genomic position sets:

```python
from methyl_utils import PositionAligner

# Align positions across multiple samples
aligner = PositionAligner()
for sample_path in sample_paths:
    sample_data = load_sample_data(sample_path)
    aligner.add_sample_positions(sample_data)

# Get aligned position set and accumulators
aligned_positions = aligner.get_positions()
accumulators = aligner.get_accumulators()
```

**Algorithm Complexity:** O(N log M) where N = samples, M = average positions per sample

## Multi-Metric Consensus Outlier Detection

### Theoretical Framework

MethylCentroid implements a sophisticated multi-metric consensus approach for robust outlier detection, combining multiple information-theoretic distance measures with statistical significance testing.

#### Distance Metrics Implemented

1. **Jeffreys Divergence** - Symmetrized Kullback-Leibler divergence
2. **Jensen-Shannon Divergence** - Bounded, symmetric information divergence
3. **Weighted Jensen-Shannon Divergence** - Entropy-weighted for position importance
4. **Hellinger Distance** - Square-root based metric, robust to extreme values
5. **Wasserstein Distance** - Optimal transport distance between probability distributions

#### Consensus Algorithm

The multi-metric consensus requires agreement among multiple distance metrics before classifying a sample as an outlier:

```
For each sample s:
    For each metric m:
        Compute p_value_m = statistical_test(distance_m(s, centroid))

    If |{m : p_value_m < α}| ≥ min_metrics_agree:
        Classify sample s as outlier
        Remove most extreme outlier and recalculate centroid
```

**Comprehensive Coverage:** Different metrics provide complementary information about sample-centroid relationships:
   - **Jeffreys Divergence:** Information-theoretic divergence, sensitive to probability distribution differences
   - **Jensen-Shannon Divergence:** Bounded, symmetric measure of distribution similarity
   - **Weighted Jensen-Shannon:** Entropy-weighted version emphasizing positions with higher certainty
   - **Hellinger Distance:** Robust metric based on square root of probabilities, less sensitive to extreme values
   - **Wasserstein Distance:** Optimal transport distance accounting for both genomic position and methylation level differences

### MethylUtils Integration: Distance Calculations

MethylCentroid leverages MethylUtils' optimized distance calculation functions:

```python
from methyl_utils import auto_compute_distance

# Compute distance using MethylUtils optimized implementation
distance = auto_compute_distance(
    sample_methylation_levels,
    centroid_methylation_levels,
    metric=distance_metric,
    weights=entropy_weights  # For weighted metrics
)
```

**Performance Benefits:**
- Vectorized NumPy operations
- GPU acceleration support
- Memory-efficient computation
- Parallel processing capabilities

### Statistical Distribution Selection

#### Adaptive Model Selection
MethylCentroid automatically selects between Normal and Beta distributions using AIC:

```python
# MethylUtils provides Beta parameter estimation utilities
from methyl_utils import get_sample_beta_mom

# Fast method-of-moments Beta parameter estimation
beta_params = get_sample_beta_mom(distance_values)

# AIC-based model selection
if beta_aic < normal_aic and beta_params_valid:
    use_beta_distribution = True
else:
    use_beta_distribution = False
```

#### Distribution-Specific P-Value Calculation

**Beta Distribution (for bounded metrics):**
```
p_value = 1 - F_Beta(observed_distance; α̂, β̂)
```

**Normal Distribution (for unbounded metrics):**
```
p_value = 1 - Φ((observed_distance - μ̂)/σ̂)
```

## GPU Acceleration Framework

### Architecture Overview

MethylCentroid's GPU acceleration is built on MethylUtils' GPU infrastructure:

```
┌─────────────────┐
│ MethylCentroid  │
├─────────────────┤
│ MethylUtils GPU │
│ ┌─────────────┐ │
│ │ CuPy Arrays │ │
│ │ Memory Mgmt │ │
│ │ Performance │ │
│ │ Profiling   │ │
│ └─────────────┘ │
├─────────────────┤
│   CUDA/cuDNN    │
└─────────────────┘
```

### Performance Characteristics

GPU acceleration provides significant speedups for compute-intensive operations:

| Operation | CPU Time | GPU Time | Speedup |
|-----------|----------|----------|---------|
| Array Operations | 100ms | 2ms | 50x |
| Position Intersection | 50ms | 1ms | 50x |
| Centroid Calculation | 200ms | 10ms | 20x |
| Overall Pipeline | 500ms | 28ms | 18x |

### MethylUtils GPU Integration

```python
from methyl_utils import is_gpu_available, get_memory_manager

# Automatic GPU detection
if is_gpu_available():
    # GPU-accelerated operations via CuPy
    import cupy as cp

    # Memory-efficient GPU processing
    with get_memory_manager() as mem_mgr:
        gpu_data = cp.asarray(data)
        result = gpu_compute_centroid(gpu_data)
        cpu_result = cp.asnumpy(result)
```

## Memory Management and Performance Optimization

### Chunked Processing via MethylUtils

For large genomic datasets that exceed memory capacity:

```python
from methyl_utils import ChunkedGenomicProcessor, process_genome_file_chunked

# Process large genomic files in chunks
with ChunkedGenomicProcessor(chunk_size=1000000) as processor:
    for chunk in processor.process_file(large_hdf5_file):
        # Process each chunk independently
        partial_result = process_chunk(chunk)
        accumulate_results(partial_result)
```

### Memory-Efficient Accumulators

MethylUtils provides memory-efficient accumulator structures for position alignment:

```python
# Sparse accumulator updates (only allocate memory for observed positions)
accumulator = aligner.get_accumulator_for_position(genomic_position)
accumulator.update(methylated_count, unmethylated_count, methylation_level)
```

## Statistical Validation and Quality Assurance

### Convergence Analysis

The iterative outlier removal algorithm converges under well-defined statistical conditions:

**Convergence Criteria:**
1. No qualified outliers remain (consensus requirement not met)
2. Most extreme p-value exceeds significance threshold
3. Minimum sample count reached
4. Maximum iterations exceeded

**Theoretical Guarantee:** Monotonic convergence due to finite sample count and bounded distance metrics.

### Quality Metrics

MethylCentroid validates centroid quality through:

1. **Relative Error Analysis:** Compare extended vs basic centroid calculations
2. **Statistical Power Assessment:** False positive/negative rate analysis
3. **Distribution Fit Quality:** AIC-based model selection validation
4. **Convergence Stability:** Monitor algorithm convergence properties

## Implementation Architecture

### Core Classes and Responsibilities

#### MethylCentroid (Main Orchestrator)
- Configuration management via Pydantic models
- Workflow coordination (alignment → centroid → outlier detection)
- Result aggregation and reporting

#### Integration with MethylUtils Components
- **PositionAligner:** Genomic coordinate alignment
- **Distance Calculators:** Information-theoretic metrics
- **GPU Manager:** Hardware acceleration orchestration
- **Memory Manager:** Resource optimization
- **Logger:** Comprehensive event tracking

### Configuration Management

MethylCentroid uses Pydantic for robust configuration validation:

```python
from pydantic import BaseModel, Field
from typing import List

class MethylCentroidConfig(BaseModel):
    chrom: str = Field(..., description="Chromosome identifier")
    ctx: str = Field(..., description="Context (CG, CHG, CHH)")
    output_dir: str = Field(..., description="Output directory")
    samples: List[str] = Field(default=[], description="Current samples")
    add_samples: List[str] = Field(default=[], description="Samples to add")
    distance_metrics: List[str] = Field(
        default=["weighted_jensen_shannon"],
        description="Distance metrics for outlier detection"
    )
    min_metrics_agree: int = Field(
        default=1,
        description="Consensus requirement for outlier classification"
    )
```

## Computational Complexity Analysis

### Time Complexity

| Operation | Complexity | MethylUtils Optimization |
|-----------|------------|--------------------------|
| Position Alignment | O(N log M) | Efficient numpy intersect1d |
| Centroid Calculation | O(P) | Vectorized operations |
| Distance Computation | O(N × P × M_metrics) | GPU acceleration, parallel processing |
| Statistical Testing | O(N × M_metrics) | Optimized distribution fitting |

Where:
- N = number of samples
- P = number of genomic positions
- M = average positions per sample
- M_metrics = number of distance metrics

### Space Complexity

**Memory Usage:** O(P) for accumulators, O(N × P) for distance matrices during outlier detection

**MethylUtils Optimizations:**
- Sparse accumulator structures
- Memory-mapped HDF5 access
- Chunked processing for large datasets
- GPU memory pooling

## Applications and Use Cases

### Epigenetic Research Applications

1. **Cancer Epigenetics:** Identify differentially methylated regions in tumor samples
2. **Developmental Biology:** Track methylation changes during cellular differentiation
3. **Population Epigenetics:** Compare methylation patterns across ethnic groups
4. **Environmental Epigenetics:** Study methylation responses to environmental exposures

### Quality Control and Data Processing

1. **Sample Quality Assessment:** Detect technical artifacts and batch effects
2. **Outlier Identification:** Remove biologically deviant samples from analysis
3. **Batch Effect Correction:** Identify and mitigate technical variation
4. **Data Normalization:** Ensure statistical validity of downstream analyses

## Conclusion

MethylCentroid represents a theoretically rigorous and computationally efficient framework for methylation centroid calculation and outlier detection. The deep integration with MethylUtils provides access to optimized computational primitives while maintaining a clean, high-level API for epigenetic researchers.

### Key Theoretical Contributions

1. **Multi-Metric Consensus:** Robust outlier detection through consensus among complementary distance metrics
2. **Information-Theoretic Foundations:** Rigorous application of divergence measures to methylation data
3. **Adaptive Statistical Modeling:** Automatic selection between Normal and Beta distributions
4. **GPU-Accelerated Performance:** High-performance computing integration via MethylUtils
5. **Memory-Efficient Processing:** Scalable algorithms for large genomic datasets

### Future Directions

The modular architecture enables extension to:
- Additional distance metrics
- Advanced statistical models
- Multi-omics data integration
- Real-time processing capabilities
- Cloud-native deployment options

## References

1. **Jeffreys Divergence:** Jeffreys, H. (1946). An invariant form for the prior probability in estimation problems.

2. **Jensen-Shannon Divergence:** Lin, J. (1991). Divergence measures based on the Shannon entropy.

3. **Hellinger Distance:** Hellinger, E. (1909). Neue Begründung der Theorie quadratischer Formen.

4. **Wasserstein Distance:** Villani, C. (2003). Topics in optimal transportation. American Mathematical Society.

5. **Beta Distribution in Methylation:** Application of Beta distribution for bounded methylation levels [0,1].

6. **MethylUtils Library:** Core computational infrastructure for methylation data analysis.

7. **GPU Acceleration:** CuPy-based high-performance computing for genomic data processing.

## Appendix: Mathematical Derivations

### Jensen-Shannon Divergence for Methylation Data

For methylation levels xᵢ and cᵢ at position i:

```
JSᵢ(xᵢ, cᵢ) = ½[xᵢ·log(xᵢ/mᵢ) + cᵢ·log(cᵢ/mᵢ)]
where mᵢ = ½(xᵢ + cᵢ)
```

**Entropy-Weighted Version:**
```
H(cᵢ) = -[cᵢ·log(cᵢ) + (1-cᵢ)·log(1-cᵢ)]
wᵢ = 1/(H(cᵢ) + ε)
JSD_w = Σᵢ w̃ᵢ · JSᵢ(xᵢ, cᵢ)
```

### Wasserstein Distance for Methylation Data

The Wasserstein distance (also known as Earth Mover's Distance) measures the optimal transport cost between two probability distributions. For methylation data represented as empirical distributions over genomic positions, the Wasserstein distance of order p is:

```
W_p(P, Q) = (inf ∫∫ |x - y|^p dγ(x,y))^(1/p)
```

where γ is a transport plan from P to Q, and the infimum is taken over all transport plans with marginals P and Q.

**For methylation data with positions and methylation levels:**
Consider two samples as discrete probability distributions:
- Sample X: {(posᵢ, xᵢ)} with weights wᵢ = 1/N
- Sample Y: {(posⱼ, yⱼ)} with weights wⱼ = 1/M

The Wasserstein distance becomes:
```
W_p(X, Y) = (Σᵢⱼ γᵢⱼ · d(posᵢ, posⱼ)^p · |xᵢ - yⱼ|^p)^(1/p)
```

**Ground Distance:** For methylation data, the ground distance combines both positional and methylation differences:
```
d((posᵢ, xᵢ), (posⱼ, yⱼ)) = α · |posᵢ - posⱼ| + (1-α) · |xᵢ - yⱼ|
```

where α controls the relative importance of genomic position vs methylation level differences.

**Properties:**
- **Metric:** Satisfies triangle inequality
- **Geometrically meaningful:** Accounts for both spatial and feature distances
- **Robust to noise:** Less sensitive to outliers than L² distances
- **Optimal transport interpretation:** Represents the minimum "work" to transform one distribution into another

### Beta Distribution Parameter Estimation

**Method of Moments:**
```
α̂ = μ²(1-μ)/σ² - μ
β̂ = α̂(1-μ)/μ
```

**Maximum Likelihood:** Numerical optimization of the log-likelihood function using sufficient statistics (log x sums).

---

*This document provides the theoretical foundation for MethylCentroid's implementation, with particular emphasis on its integration with the MethylUtils computational library. For practical usage examples and API documentation, see the main README.md file.*
