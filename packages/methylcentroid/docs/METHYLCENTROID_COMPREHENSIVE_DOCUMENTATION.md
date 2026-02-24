# MethylCentroid Comprehensive Documentation

## Contents
1. Overview
2. Data Model
3. Centroid Computation
4. Sufficient Statistics and Distributions
5. Configuration
6. CLI Usage
7. GPU and Memory Management
8. Output Files
9. Examples
10. Troubleshooting

---

## 1. Overview

MethylCentroid computes representative methylation profiles (centroids) from
sample cohorts. A centroid stores per-position methylation statistics in a
compact HDF5 file for downstream analysis (DMP detection, classification, and
validation).

Key goals:
- memory-efficient aggregation,
- optional GPU acceleration,
- incremental updates (add/remove samples),
- extended statistics for distribution-aware comparisons.

## 2. Data Model

Each centroid position stores:
- **pos**: genomic coordinate
- **mC / uC**: averaged methylated / unmethylated counts
- **N**: number of contributing samples
- **Sx, Sx2**: sums of methylation fractions and squares
- **log_x_sum, log_1_minus_x_sum**: log-sum statistics

Extended centroids may also include (when built with extended stats):
- **sum_cov, sum_cov2, sum_mC, sum_uC, sum_mC2, sum_uC2**
- **Sx3, Sx4**
- **count_zero, count_one**

See **MethylCentroid_Theoretical_Foundation.md** and **METHYLCENTROID_IMPLEMENTATION.md** for theory and implementation.

## 3. Centroid Computation

For N samples at position i:

```
Centroid_i = (1/N) × Σ(methylation_level_ij)
```

MethylCentroid builds the centroid via streaming sample updates, accumulating
the sufficient statistics listed above. Optional chunked processing is used
for large genomes (e.g., CHH).

### Implementation (MethylUtils)

Centroid construction is implemented in **MethylUtils**: **MethylCentroidBuilder** (streaming, GPU), **build_centroid()**, **MethylExtendedCentroid** / **MethylBetaBinomialCentroid**, and **load_from_h5** / **save_to_h5**. See **METHYLCENTROID_IMPLEMENTATION.md** for full details.

## 4. Sufficient Statistics and Distributions

The centroid stores sufficient statistics for:
- **Normal** (mean/variance via Sx, Sx2)
- **Beta** (MLE via log-sums)
- **Beta-Binomial** (coverage-aware overdispersion)
- **Beta Mixture** (optional binned stats or masked refinement)

Full derivations and formulas are documented in:

📄 **`docs/METHYLCENTROID_DISTRIBUTIONS.tex`**

## 5. Configuration

### JSON Configuration Format

```json
{
  "laboratory": "UCSF",
  "disease": "Breast Cancer",
  "group": "Tumor",
  "batch": "2024-01",
  "chrom": "1",
  "ctx": "CG",
  "output_dir": "./centroids",
  "add_samples": [
    "/data/samples/sample1",
    "/data/samples/sample2"
  ],
  "min_coverage": 4,
  "use_gpu": true,
  "verbose": true
}
```

### Parameters

- **chrom** (str): Chromosome identifier (e.g., '1', 'X', 'MT')
- **ctx** (str): Methylation context ('CG', 'CHG', 'CHH')
- **output_dir** (str): Directory to save centroid files
- **samples** (List[str], optional): Current samples in centroid (for updates)
- **add_samples** (List[str], optional): New samples to add
- **remove_samples** (List[str], optional): Samples to remove
- **min_coverage** (int, default=4): Minimum $mC + uC$ for position inclusion
- **use_gpu** (bool, default=True): Enable GPU acceleration when available
- **verbose** (bool, default=True): Enable verbose logging
- **laboratory/disease/group/batch**: Metadata fields saved with centroid

## 6. CLI Usage

```bash
# Single config
python -m methyl_centroid.cli --config config.json

# Batch config
python -m methyl_centroid.cli --batch-config batch_config.json

# Force CPU
python -m methyl_centroid.cli --config config.json --no-gpu
```

## 7. GPU and Memory Management

MethylCentroid uses a memory-aware chunked pipeline for large contexts:
- CPU mode: minimizes peak RAM via chunked processing.
- GPU mode: uses CuPy when available; can be disabled via `use_gpu=false`.

For CHH, consider:
- higher `min_coverage`,
- CPU mode (`use_gpu=false`) if GPU memory is shared or constrained.

## 8. Output Files

### Primary Outputs

1. **`{chrom}-{ctx}.h5`**: HDF5 centroid with per-position statistics
2. **`{chrom}-{ctx}_config.json`**: Updated configuration + metadata

### Optional Binned Stats

When `enable_binned_stats=True`, a `binned_stats` group is saved in HDF5 for
mixture refinement (bin edges + per-position counts).

## 9. Examples

### Basic Centroid

```python
from methyl_centroid import MethylCentroid

mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids',
    add_samples=['sample1', 'sample2'],
    min_coverage=4
)
mc.build_centroid()
```

### Incremental Update

```python
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids',
    samples=['sample1', 'sample2'],
    add_samples=['sample3']
)
mc.build_centroid()
```

### Binned Stats (optional)

```python
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids',
    add_samples=['sample1', 'sample2'],
    enable_binned_stats=True,
    binned_stats_bins=32
)
mc.build_centroid()
```

## 10. Troubleshooting

- **GPU used unexpectedly**: set `use_gpu=false` in config or pass `--no-gpu`.
- **Large CHH memory use**: increase `min_coverage` or run CPU mode.
- **Missing sample files**: verify `{chrom}-{ctx}.h5` exists for each sample path.
<!-- LEGACY CONTENT REMOVED (outlier detection docs removed)

1. [Overview](#overview)
2. [Mathematical Theory](#mathematical-theory)
3. [Core Concepts](#core-concepts)
4. [Centroid Calculation Algorithm](#centroid-calculation-algorithm)
5. [Outlier Detection Methods](#outlier-detection-methods)
6. [API Reference](#api-reference)
7. [Configuration](#configuration)
8. [Advanced Features](#advanced-features)
9. [Usage Examples](#usage-examples)
10. [Troubleshooting](#troubleshooting)
11. [Integration with MethylPipeline](#integration-with-methylpipeline)
12. [Performance](#performance)
13. [License](#license)

---

## Overview

**MethylCentroid** is a high-performance Python package for calculating representative methylation profiles (centroids) from genomic data, with advanced outlier detection and GPU acceleration capabilities.

### What is a Methylation Centroid?

A **methylation centroid** is a statistical summary that represents the average methylation pattern across a group of samples. Think of it as the "representative profile" for a cohort:

- **Input**: Multiple methylation samples (e.g., 35 healthy individuals)
- **Output**: A single centroid that captures the group's typical methylation pattern
- **Purpose**: Enable comparisons between groups, quality control, and downstream classification

### MethylSample: Unified Data Structure

MethylCentroid uses `MethylSample` (from MethylUtils) as a unified container that supports three data types:

1. **Basic Sample**: Individual methylation sample with `pos`, `mC`, `uC`, `tnc` fields
2. **Basic Centroid**: Aggregated sample with additional `N` (sample count), `Sx`, `Sx2` (sufficient statistics for mean/variance)
3. **Extended Centroid**: Basic centroid plus `log_x_sum`, `log_1_minus_x_sum` (sufficient statistics for Beta distribution MLE)

This unified design allows MethylCentroid to:
- Process individual samples during centroid calculation
- Accumulate statistics (Sx, Sx2, log sums) incrementally
- Extract Beta distribution parameters (α, β) from extended centroids for probabilistic outlier detection
- Maintain backward compatibility with existing HDF5 files

### Key Features

- **Robust Outlier Detection**: Automatically identifies and removes aberrant samples using multiple statistical methods
- **GPU Acceleration**: 10-50x speedup for large datasets using NVIDIA GPUs
- **Multi-Metric Consensus**: Uses multiple distance metrics for reliable outlier identification
- **Memory Efficient**: Smart caching and chunked processing for large genomic datasets
- **Incremental Operations**: Add/remove samples without recalculating entire centroids
- **Quality Assurance**: Comprehensive validation and convergence guarantees

---

## Mathematical Theory

### Data Representation

Each methylation sample contains data for genomic positions with:

- **$mC_i$**: Count of methylated cytosines at position $i$
- **$uC_i$**: Count of unmethylated cytosines at position $i$
- **$x_i$**: Methylation level where $x_i = \frac{mC_i}{mC_i + uC_i}$, bounded in [0, 1]
- **$pos_i$**: Genomic coordinate of position $i$

### Centroid Calculation

MethylCentroid uses **extended centroid** calculation for statistical rigor:

#### Extended Centroid (Recommended)

For $N$ samples at position $i$:

$$
\text{Centroid}_i = \frac{1}{N} \sum_{j=1}^{N} x_{ij}
$$

This approach:
- **Accumulates methylation levels**: $S_x = \sum x_{ij}$ and $S_{x^2} = \sum x_{ij}^2$
- **Properly handles varying coverage**: Each sample contributes equally regardless of depth
- **Enables variance estimation**: $\sigma^2 = \frac{S_{x^2}}{N} - \left(\frac{S_x}{N}\right)^2$

#### Why Not Basic Averaging?

The naive approach of averaging raw counts fails when samples have different coverage:

$$
\text{Basic (WRONG)} = \frac{\sum mC_i}{\sum mC_i + \sum uC_i}
$$

This incorrectly weights samples with higher coverage, biasing the centroid.

### Position Alignment

MethylCentroid uses **MethylUtils' PositionAligner** to handle samples with different genomic positions:

**Algorithm**:
1. Union all positions across samples: $P = \bigcup_{j=1}^{N} P_j$
2. For each position $p \in P$, accumulate values from samples that have data at $p$
3. Calculate centroid using only samples with coverage at each position

**Complexity**: $O(N \log M)$ where $N$ = samples, $M$ = average positions per sample

---

## Core Concepts

### 1. Centroid vs Sample

| Aspect | Sample | Centroid |
|--------|--------|----------|
| **Represents** | Single individual | Group average |
| **Contains** | Raw methylation counts | Accumulated statistics |
| **Fields** | pos, mC, uC, tnc | pos, mC, uC, tnc, N, Sx, Sx2 |
| **Purpose** | Individual data | Group comparison |

### 2. Outlier Detection Philosophy

MethylCentroid identifies samples that deviate significantly from the group using:

- **Information-theoretic distances**: Measure how "different" a sample is from the centroid
- **Statistical significance testing**: Use p-values to quantify deviation
- **Multi-metric consensus**: Require agreement across multiple distance measures
- **Iterative refinement**: Remove outliers one at a time, recalculating centroid each iteration

### 3. Distance Metrics

Five complementary metrics measure sample-centroid divergence:

#### Jeffreys Divergence

Symmetrized Kullback-Leibler divergence:

$$
D_{\text{Jeffreys}}(x, c) = \sum_i x_i \log\frac{x_i}{c_i} + c_i \log\frac{c_i}{x_i}
$$

**Properties**:
- Information-theoretic measure
- Symmetric
- Sensitive to probability differences
- **Use when**: Emphasizing information content differences

#### Jensen-Shannon Divergence

Bounded, symmetric information divergence:

$$
D_{\text{JS}}(x, c) = \frac{1}{2}\left[D_{\text{KL}}(x \| m) + D_{\text{KL}}(c \| m)\right]
$$

where $m = \frac{x + c}{2}$

**Properties**:
- Bounded: $0 \leq D_{\text{JS}} \leq \log(2)$
- Square root is a proper metric
- Less sensitive to extreme values than KL divergence
- **Use when**: Need bounded, interpretable distances

#### Weighted Jensen-Shannon Divergence

Entropy-weighted version emphasizing high-certainty positions:

$$
D_{\text{WJS}}(x, c) = \sum_i w_i \cdot D_{\text{JS}, i}(x_i, c_i)
$$

where $w_i = \frac{1}{H(c_i) + \epsilon}$ and $H(c_i) = -c_i \log c_i - (1-c_i)\log(1-c_i)$

**Properties**:
- Emphasizes positions with low entropy (high certainty)
- Down-weights ambiguous positions (methylation ≈ 0.5)
- **Use when**: Focusing on biologically informative positions

#### Hellinger Distance

Square-root based metric:

$$
D_{\text{Hellinger}}(x, c) = \sqrt{\sum_i \left(\sqrt{x_i} - \sqrt{c_i}\right)^2}
$$

**Properties**:
- Robust to extreme values
- Proper metric (satisfies triangle inequality)
- Bounded: $0 \leq D_{\text{Hellinger}} \leq \sqrt{2}$
- **Use when**: Need robustness to outliers

#### Wasserstein Distance

Optimal transport distance:

$$
W_p(X, Y) = \left(\inf_{\gamma \in \Gamma(X,Y)} \int \|x - y\|^p d\gamma(x,y)\right)^{1/p}
$$

**Properties**:
- Accounts for both positional and methylation differences
- Geometrically meaningful
- Proper metric
- **Use when**: Spatial relationships matter

### 4. Statistical Distribution Modeling

MethylCentroid adaptively selects between Normal and Beta distributions using AIC:

#### Beta Distribution (Preferred for Bounded Metrics)

For distances bounded in [0, 1]:

$$
f(x; \alpha, \beta) = \frac{x^{\alpha-1}(1-x)^{\beta-1}}{B(\alpha, \beta)}
$$

**Parameter Estimation** (Method of Moments):

$$
\hat{\alpha} = \frac{\mu^2(1-\mu)}{\sigma^2} - \mu, \quad \hat{\beta} = \frac{\hat{\alpha}(1-\mu)}{\mu}
$$

**P-value Calculation**:

$$
p\text{-value} = 1 - F_{\text{Beta}}(d_{\text{observed}}; \hat{\alpha}, \hat{\beta})
$$

#### Normal Distribution (Fallback for Unbounded Metrics)

$$
f(x; \mu, \sigma) = \frac{1}{\sigma\sqrt{2\pi}} \exp\left(-\frac{(x-\mu)^2}{2\sigma^2}\right)
$$

**P-value Calculation**:

$$
p\text{-value} = 1 - \Phi\left(\frac{d_{\text{observed}} - \hat{\mu}}{\hat{\sigma}}\right)
$$

---

## Centroid Calculation Algorithm

### High-Level Workflow

```
1. Position Alignment
   ├─ Load all samples
   ├─ Find union of genomic positions
   └─ Create accumulator arrays

2. Accumulation
   ├─ For each sample:
   │  ├─ Calculate methylation levels
   │  ├─ Align to union positions
   │  └─ Update accumulators (Sx, Sx2, N)
   └─ Apply minimum coverage filter

3. Finalization
   ├─ Calculate centroid methylation: x = Sx / N
   ├─ Convert to counts: mC, uC from x and coverage
   └─ Save to HDF5 with metadata
```

### Detailed Algorithm

#### Step 1: Position Alignment

```python
from methyl_utils import PositionAligner

aligner = PositionAligner()

for sample_path in sample_paths:
    sample = MethylSample.load_from_h5(sample_path)
    aligner.add_sample(sample)

# Get aligned positions and accumulators
positions = aligner.get_positions()
Sx = aligner.get_Sx_accumulator()
Sx2 = aligner.get_Sx2_accumulator()
N = aligner.get_N_accumulator()
```

#### Step 2: Coverage Filtering

```python
# Apply minimum coverage threshold
coverage_mask = N >= min_coverage

filtered_positions = positions[coverage_mask]
filtered_Sx = Sx[coverage_mask]
filtered_Sx2 = Sx2[coverage_mask]
filtered_N = N[coverage_mask]
```

#### Step 3: Centroid Calculation

```python
# Calculate centroid methylation levels
centroid_methylation = filtered_Sx / filtered_N

# Calculate variance for quality metrics
centroid_variance = (filtered_Sx2 / filtered_N) - centroid_methylation**2

# Convert to methylated/unmethylated counts
# Using average coverage per position
avg_coverage = 10  # or from data
centroid_mC = centroid_methylation * avg_coverage
centroid_uC = (1 - centroid_methylation) * avg_coverage
```

#### Step 4: Save Centroid

```python
from methyl_utils import save_centroid_to_h5

save_centroid_to_h5(
    output_path,
    positions=filtered_positions,
    mC=centroid_mC,
    uC=centroid_uC,
    N=filtered_N,
    Sx=filtered_Sx,
    Sx2=filtered_Sx2,
    metadata={
        'samples': sample_paths,
        'min_coverage': min_coverage,
        'chromosome': chrom,
        'context': ctx
    }
)
```

---

## Outlier Detection Methods

MethylCentroid implements three outlier detection strategies, automatically selected based on sample size:

### 1. Probabilistic Beta Classifier (≥20 samples)

**When to Use**: Large cohorts where statistical modeling is reliable

**Algorithm**:
```
1. Calculate distances for all samples
2. Fit Beta distribution to distance values
3. Compute outlier probability for each sample
4. Select sample with highest outlier probability
5. Check if p-value < α (significance threshold)
```

**Advantages**:
- Most statistically rigorous
- Properly models bounded distance distributions
- Provides calibrated probabilities

**Implementation**:
```python
from methyl_utils import ProbabilisticBetaClassifier

classifier = ProbabilisticBetaClassifier()
classifier.fit_from_distances(distances)
outlier_probs = classifier.predict_outlier_probabilities(distances)
```

### 2. Multi-Metric Consensus (5-19 samples)

**When to Use**: Medium-sized cohorts where consensus improves reliability

**Algorithm**:
```
For each distance metric m:
    1. Calculate distances: d_m(sample, centroid)
    2. Fit statistical distribution to d_m values
    3. Calculate p-value for each sample

Consensus Decision:
    If |{m : p_m(sample) < α}| ≥ min_metrics_agree:
        Mark sample as outlier
    
    Remove most significant outlier (lowest p-value)
```

**Advantages**:
- Robust to metric-specific artifacts
- Reduces false positives
- Complementary information from different metrics

**Configuration**:
```python
config = MethylCentroidConfig(
    distance_metrics=[
        DistanceMetric.JENSEN_SHANNON,
        DistanceMetric.WASSERSTEIN,
        DistanceMetric.HELLINGER
    ],
    min_metrics_agree=2,  # Require 2/3 metrics to agree
    α=0.05
)
```

### 3. Single-Metric Detection (3-4 samples)

**When to Use**: Small cohorts where multi-metric consensus is unreliable

**Algorithm**:
```
1. Use single distance metric (default: Jensen-Shannon)
2. Calculate distances for all samples
3. Fit Normal distribution to distances
4. Identify most extreme outlier (highest z-score)
5. Check if p-value < α
```

**Advantages**:
- Simpler, more interpretable
- Works with minimal samples
- Lower computational cost

### Iterative Outlier Removal

All methods use iterative refinement:

```
Iteration 1:
    Calculate centroid from all N samples
    Detect outlier → Remove sample with p < α
    
Iteration 2:
    Recalculate centroid from remaining N-1 samples
    Detect outlier → Remove if p < α
    
...

Stop when:
    - No outlier detected (all p-values > α)
    - Maximum iterations reached
    - Minimum samples reached
```

**Convergence Guarantee**: The algorithm always terminates due to:
1. Finite sample count
2. Bounded distance metrics
3. Monotonic removal (never re-add samples)

---

## API Reference

### MethylCentroid Class

Main class for centroid calculation and outlier detection.

#### Constructor

```python
MethylCentroid(
    chrom: str,
    ctx: str,
    output_dir: str,
    samples: List[str] = None,
    add_samples: List[str] = None,
    remove_samples: List[str] = None,
    outliers: List[str] = None,
    min_coverage: int = 4,
    min_samples: int = 3,
    verbose: bool = True,
    laboratory: str = None,
    disease: str = None,
    group: str = None,
    batch: str = None
)
```

**Parameters**:

- **chrom** (str): Chromosome identifier (e.g., '1', 'X', 'MT')
- **ctx** (str): Methylation context ('CG', 'CHG', or 'CHH')
- **output_dir** (str): Directory to save centroid files
- **samples** (List[str], optional): Current samples in centroid (for updates)
- **add_samples** (List[str], optional): New samples to add
- **remove_samples** (List[str], optional): Samples to remove
- **outliers** (List[str], optional): Previously identified outliers
- **min_coverage** (int, default=4): Minimum $mC + uC$ for position inclusion
- **min_samples** (int, default=3): Minimum number of samples for position inclusion in centroid
- **use_gpu** (bool, default=True): Enable GPU acceleration when available
- **verbose** (bool, default=True): Enable verbose logging
- **laboratory** (str, optional): Lab identifier for metadata
- **disease** (str, optional): Disease/condition for metadata
- **group** (str, optional): Sample group identifier for metadata
- **batch** (str, optional): Batch identifier for metadata

#### Methods

##### build_centroid()

Build centroid from samples with automatic outlier detection.

```python
results = mc.build_centroid()
```

**Returns**: `OutlierRemovalResults` containing:
- `iterations`: List of outlier removal details
- `final_centroid_path`: Path to saved centroid file
- `total_samples_removed`: Count of removed outliers

##### update_centroid()

Incrementally update existing centroid.

```python
mc.update_centroid(
    add_samples=['new_sample1', 'new_sample2'],
    remove_samples=['old_sample1']
)
```

**Parameters**:
- **add_samples** (List[str]): Samples to add
- **remove_samples** (List[str]): Samples to remove

**Returns**: Updated `OutlierRemovalResults`

##### save_centroid()

Save current centroid to HDF5 file.

```python
mc.save_centroid(output_path, metadata={})
```

**Parameters**:
- **output_path** (str): Path to save HDF5 file
- **metadata** (dict): Additional metadata to include

### MethylCentroidConfig Class

Pydantic model for configuration validation.

```python
from methyl_centroid import MethylCentroidConfig, DistanceMetric

config = MethylCentroidConfig(
    laboratory="UCSF",
    disease="Breast Cancer",
    group="Tumor",
    batch="2024-01",
    chrom="1",
    ctx="CG",
    output_dir="./centroids",
    add_samples=sample_paths,
    distance_metrics=[
        DistanceMetric.JENSEN_SHANNON,
        DistanceMetric.WASSERSTEIN
    ],
    min_metrics_agree=2,
    α=0.05,
    min_coverage=4
)
```

#### Field Validation

- **ctx**: Must be 'CG', 'CHG', or 'CHH'
- **α**: Must be in (0, 1]
- **min_coverage**: Must be ≥ 1
- **min_metrics_agree**: Must be ≥ 0

### OutlierDetectorFactory

Factory for creating appropriate outlier detectors.

```python
from methyl_centroid.outlier_detection import OutlierDetectorFactory

detector = OutlierDetectorFactory.create_detector(
    num_samples=25,
    distance_metrics=[DistanceMetric.JENSEN_SHANNON],
    config={'alpha': 0.05}
)
```

---

## Configuration

### JSON Configuration Format

```json
{
  "laboratory": "UCSF",
  "disease": "Breast Cancer",
  "group": "Tumor",
  "batch": "2024-01",
  "chrom": "1",
  "ctx": "CG",
  "output_dir": "./centroids",
  "use_gpu": true,
  "add_samples": [
    "/data/samples/sample1",
    "/data/samples/sample2"
  ],
  "min_coverage": 4,
  "max_iterations": 10,
  "max_iterations_percentage": 0.1,
  "α": 0.05,
  "min_samples": 3,
  "distance_metrics": [
    "jensen_shannon",
    "wasserstein"
  ],
  "min_metrics_agree": 2,
  "verbose": true
}
```

### Loading Configuration

```python
from methyl_centroid import MethylCentroidConfig

config = MethylCentroidConfig.from_file('config.json')
mc = MethylCentroid(**config.model_dump())
```

### Common Configuration Patterns

#### Conservative Outlier Detection

```python
config = MethylCentroidConfig(
    α=0.01,  # Stricter threshold
    min_metrics_agree=3,  # Require 3+ metrics
    distance_metrics=[
        DistanceMetric.JENSEN_SHANNON,
        DistanceMetric.WASSERSTEIN,
        DistanceMetric.HELLINGER,
        DistanceMetric.JEFFREYS
    ]
)
```

#### Aggressive Outlier Detection

```python
config = MethylCentroidConfig(
    α=0.10,  # More lenient threshold
    min_metrics_agree=1,  # Single metric sufficient
    max_iterations_percentage=0.20  # Remove up to 20% of samples
)
```

#### High-Coverage Quality Control

```python
config = MethylCentroidConfig(
    min_coverage=10,  # Higher coverage requirement
    α=0.05,
    distance_metrics=[DistanceMetric.WEIGHTED_JENSEN_SHANNON]  # Emphasize high-certainty positions
)
```

---

## Advanced Features

### 1. GPU Acceleration

MethylCentroid automatically detects and uses NVIDIA GPUs when available.

#### Automatic GPU Detection

```python
from methyl_utils import is_gpu_available

if is_gpu_available():
    print("GPU acceleration enabled")
    # GPU operations happen automatically
else:
    print("Using CPU fallback")
```

#### Performance Gains

| Operation | CPU Time | GPU Time | Speedup |
|-----------|----------|----------|---------|
| Position Intersection | 50ms | 1ms | 50x |
| Distance Calculation | 200ms | 10ms | 20x |
| Centroid Accumulation | 100ms | 2ms | 50x |
| **Total Pipeline** | **500ms** | **28ms** | **18x** |

#### GPU Memory Management

MethylCentroid uses MethylUtils' memory manager for efficient GPU utilization:

```python
from methyl_utils import get_memory_manager

mem_mgr = get_memory_manager()
stats = mem_mgr.get_memory_usage()

print(f"GPU Memory: {stats['gpu_used_gb']:.1f} / {stats['gpu_total_gb']:.1f} GB")
```

### 2. Smart Sample Caching

Automatic LRU cache with memory management:

```python
from methyl_centroid.core import SmartSampleCache

cache = SmartSampleCache(
    memory_manager=mem_mgr,
    max_memory_gb=50  # Use up to 50GB for caching
)

# Cache automatically loads and evicts samples
sample = cache.get(sample_path, loader_func=load_sample)

# Check cache statistics
stats = cache.get_stats()
print(f"Cached samples: {stats['cached_samples']}")
print(f"Memory usage: {stats['memory_usage_mb']:.1f} MB")
```

### 3. Incremental Centroid Updates

Add or remove samples without full recalculation:

```python
# Initial centroid
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='centroids',
    add_samples=['sample1', 'sample2', 'sample3']
)
results = mc.build_centroid()

# Later: add new samples
mc_updated = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='centroids',
    samples=['sample1', 'sample2', 'sample3'],  # Current samples
    add_samples=['sample4', 'sample5'],  # New samples
    outliers=results.outliers  # Previously removed outliers
)
results_updated = mc.build_centroid()
```

### 4. Batch Processing

Process multiple chromosome/context combinations:

```python
from methyl_centroid import MethylCentroid

chromosomes = ['1', '2', '3', 'X']
contexts = ['CG', 'CHG', 'CHH']

for chrom in chromosomes:
    for ctx in contexts:
        mc = MethylCentroid(
            chrom=chrom,
            ctx=ctx,
            output_dir=f'centroids/chr{chrom}',
            add_samples=sample_paths,
            min_coverage=4
        )
        results = mc.build_centroid()
        print(f"Completed {chrom}-{ctx}: {results.total_samples_removed} outliers removed")
```

### 5. Custom Distance Metrics

Extend with custom distance metrics:

```python
from methyl_centroid import DistanceMetric
from methyl_utils import register_distance_metric

# Register custom metric
@register_distance_metric('custom_metric')
def custom_distance(sample_methylation, centroid_methylation, weights=None):
    """Custom distance calculation"""
    diff = np.abs(sample_methylation - centroid_methylation)
    if weights is not None:
        diff *= weights
    return np.mean(diff)

# Use in configuration
config = MethylCentroidConfig(
    distance_metrics=['custom_metric'],
    # ... other parameters
)
```

### 6. Performance Profiling

Built-in performance monitoring:

```python
from methyl_utils import get_performance_profiler, start_performance_monitoring

# Start monitoring
monitor = start_performance_monitoring(interval=1.0)

# Build centroid
mc = MethylCentroid(...)
results = mc.build_centroid()

# Get profiling results
profiler = get_performance_profiler()
report = profiler.get_report()

print(f"Total time: {report['total_time']:.2f}s")
print(f"Peak memory: {report['peak_memory_gb']:.2f} GB")
print(f"GPU utilization: {report['gpu_utilization_percent']:.1f}%")
```

---

## Usage Examples

### Example 1: Basic Centroid Creation

```python
from methyl_centroid import MethylCentroid

# Create centroid from samples
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./output/centroids',
    add_samples=[
        '/data/samples/sample1',
        '/data/samples/sample2',
        '/data/samples/sample3'
    ],
    min_coverage=4,
    α=0.05
)

results = mc.build_centroid()

print(f"Centroid saved to: {results.final_centroid_path}")
print(f"Outliers removed: {results.total_samples_removed}")

for iteration in results.iterations:
    print(f"  Iteration {iteration.iteration}: {iteration.outlier_path} (p={iteration.p_value:.6f})")
```

### Example 2: Multi-Metric Consensus

```python
from methyl_centroid import MethylCentroid, MethylCentroidConfig, DistanceMetric

config = MethylCentroidConfig(
    laboratory="UCSF",
    disease="Breast Cancer",
    group="Tumor",
    batch="2024-01",
    chrom='1',
    ctx='CG',
    output_dir='./centroids',
    add_samples=sample_paths,
    distance_metrics=[
        DistanceMetric.JENSEN_SHANNON,
        DistanceMetric.WASSERSTEIN,
        DistanceMetric.HELLINGER
    ],
    min_metrics_agree=2,  # Require 2/3 metrics to agree
    α=0.05
)

mc = MethylCentroid(**config.model_dump())
results = mc.build_centroid()
```

### Example 3: Incremental Updates

```python
# Initial centroid
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='centroids',
    add_samples=['sample1', 'sample2', 'sample3'],
    laboratory="UCSF",
    disease="Breast Cancer",
    group="Tumor",
    batch="2024-01"
)
initial_results = mc.build_centroid()

# Add new samples later
mc_updated = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='centroids',
    samples=['sample1', 'sample2', 'sample3'],  # Current samples (after outlier removal)
    add_samples=['sample4', 'sample5'],  # New samples to add
    outliers=initial_results.outliers,  # Re-include for fair evaluation
    laboratory="UCSF",
    disease="Breast Cancer",
    group="Tumor",
    batch="2024-01"
)
updated_results = mc_updated.build_centroid()
```

### Example 4: Using Configuration Files

```python
from methyl_centroid import MethylCentroidConfig, MethylCentroid

# Load configuration from JSON
config = MethylCentroidConfig.from_file('config.json')

# Create centroid
mc = MethylCentroid(**config.model_dump())
results = mc.build_centroid()

# Save updated configuration
updated_config = MethylCentroidConfig(
    **config.model_dump(),
    samples=results.remaining_samples,
    outliers=results.outliers
)
updated_config.to_file('config_updated.json')
```

### Example 5: Batch Processing with Progress Tracking

```python
from methyl_centroid import MethylCentroid
from tqdm import tqdm

chromosomes = [str(i) for i in range(1, 23)] + ['X', 'Y']
contexts = ['CG', 'CHG', 'CHH']

results_summary = []

for chrom in tqdm(chromosomes, desc="Chromosomes"):
    for ctx in tqdm(contexts, desc=f"Chr {chrom} contexts", leave=False):
        try:
            mc = MethylCentroid(
                chrom=chrom,
                ctx=ctx,
                output_dir=f'centroids/chr{chrom}',
                add_samples=sample_paths,
                min_coverage=4,
                α=0.05,
                verbose=False  # Reduce output for batch processing
            )
            results = mc.build_centroid()
            
            results_summary.append({
                'chrom': chrom,
                'ctx': ctx,
                'outliers_removed': results.total_samples_removed,
                'centroid_path': results.final_centroid_path
            })
        except Exception as e:
            print(f"Error processing {chrom}-{ctx}: {e}")
            continue

# Save summary
import pandas as pd
df = pd.DataFrame(results_summary)
df.to_csv('batch_processing_summary.csv', index=False)
print(df)
```

### Example 6: Custom Outlier Detection Thresholds

```python
from methyl_centroid import MethylCentroid

# Conservative (strict) outlier detection
mc_conservative = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='centroids',
    add_samples=sample_paths,
    α=0.01,  # Stricter threshold
    min_metrics_agree=3,  # More metrics must agree
    max_iterations=5  # Limit removals
)

# Aggressive (lenient) outlier detection
mc_aggressive = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='centroids',
    add_samples=sample_paths,
    α=0.10,  # More lenient threshold
    min_metrics_agree=1,  # Single metric sufficient
    max_iterations_percentage=0.20  # Remove up to 20% of samples
)
```

---

## Troubleshooting

### Common Issues and Solutions

#### 1. GPU Not Detected

**Problem**: GPU available but not being used

**Solutions**:
```bash
# Check CUDA installation
nvidia-smi

# Install CuPy matching CUDA version
pip install cupy-cuda11x  # Replace 11x with your CUDA version

# Verify GPU detection
python -c "from methyl_utils import is_gpu_available; print(is_gpu_available())"
```

#### 2. Out of Memory Errors

**Problem**: Process crashes with memory errors

**Solutions**:
```python
# Reduce cache size
cache = SmartSampleCache(max_memory_gb=20)  # Smaller cache

# Increase minimum coverage (reduces position count)
mc = MethylCentroid(..., min_coverage=10)

# Process samples in smaller batches
batch_size = 10
for i in range(0, len(samples), batch_size):
    batch_samples = samples[i:i+batch_size]
    mc = MethylCentroid(..., add_samples=batch_samples)
    mc.build_centroid()
```

#### 3. No Outliers Detected

**Problem**: Expected outliers but none detected

**Diagnosis**:
```python
# Check distance distributions
from methyl_utils import auto_compute_distance
import matplotlib.pyplot as plt

distances = []
for sample_path in sample_paths:
    dist = auto_compute_distance(sample, centroid, metric='jensen_shannon')
    distances.append(dist)

plt.hist(distances, bins=20)
plt.xlabel('Jensen-Shannon Distance')
plt.ylabel('Frequency')
plt.title('Distance Distribution')
plt.show()
```

**Solutions**:
```python
# Increase significance threshold
mc = MethylCentroid(..., α=0.10)

# Use single metric instead of consensus
mc = MethylCentroid(
    ...,
    distance_metrics=[DistanceMetric.JENSEN_SHANNON],
    min_metrics_agree=1
)
```

#### 4. Too Many Outliers Detected

**Problem**: Removing too many samples

**Solutions**:
```python
# Decrease significance threshold
mc = MethylCentroid(..., α=0.01)

# Increase consensus requirement
mc = MethylCentroid(..., min_metrics_agree=3)

# Limit maximum removals
mc = MethylCentroid(
    ...,
    max_iterations=3,
    max_iterations_percentage=0.10  # Maximum 10% of samples
)
```

#### 5. Slow Performance

**Problem**: Centroid calculation takes too long

**Solutions**:
```python
# Enable GPU acceleration (if available)
from methyl_utils import is_gpu_available
print(f"GPU available: {is_gpu_available()}")

# Reduce distance metrics
mc = MethylCentroid(
    ...,
    distance_metrics=[DistanceMetric.JENSEN_SHANNON]  # Single metric
)

# Disable verbose output
mc = MethylCentroid(..., verbose=False)

# Use chunked processing for large datasets
from methyl_utils import ChunkedGenomicProcessor
processor = ChunkedGenomicProcessor(chunk_size=1000000)
```

#### 6. HDF5 File Corruption

**Problem**: Cannot read centroid files

**Solutions**:
```python
import h5py

# Check file integrity
try:
    with h5py.File(centroid_path, 'r') as f:
        print(f"Keys: {list(f.keys())}")
        print(f"Metadata: {dict(f.attrs)}")
except Exception as e:
    print(f"File corrupted: {e}")
    # Re-generate centroid

# Verify file format
from methyl_utils import MethylSample
sample = MethylSample.load_from_h5(centroid_path)
print(f"Positions: {len(sample.pos)}")
print(f"Methylation range: [{sample.mC.min()}, {sample.mC.max()}]")
```

### Debugging Tips

#### Enable Detailed Logging

```python
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

mc = MethylCentroid(..., verbose=True)
```

#### Check Intermediate Results

```python
# Save intermediate centroids
for iteration in range(max_iterations):
    mc.build_centroid()
    mc.save_centroid(f'centroid_iter_{iteration}.h5')
```

#### Profile Performance

```python
from methyl_utils import start_performance_monitoring, get_performance_profiler

monitor = start_performance_monitoring()
mc.build_centroid()
profiler = get_performance_profiler()

print(profiler.get_report())
```

---

## Integration with MethylPipeline

MethylCentroid is a core component of the MethylPipeline ecosystem:

### Pipeline Workflow

```
1. MethylCentroid
   ├─ Create centroids for Group A
   ├─ Create centroids for Group B
   └─ Remove outliers from both groups

2. MethylModeler
   ├─ Compare Centroid A vs Centroid B
   ├─ Identify DMPs (Differentially Methylated Positions)
   └─ Train classifier on DMPs

3. MethylClassifier
   ├─ Load trained classifier
   ├─ Classify new samples
   └─ Report probabilities and predictions
```

### Example: Complete Pipeline

```python
from methyl_centroid import MethylCentroid
from methyl_modeler import MethylModeler
from methyl_classifier import MethylClassifier

# Step 1: Create centroids
centroid_healthy = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='centroids',
    add_samples=healthy_samples,
    group='Healthy'
).build_centroid()

centroid_cancer = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='centroids',
    add_samples=cancer_samples,
    group='Cancer'
).build_centroid()

# Step 2: Detect DMPs
detector = MethylModeler(
    centroid1_path=centroid_healthy.final_centroid_path,
    centroid2_path=centroid_cancer.final_centroid_path,
    output_dir='dmps'
)
dmp_results = detector.find_dmps()

# Step 3: Classify new samples
classifier = MethylClassifier(
    model_path=dmp_results.classifier_path
)
prediction = classifier.predict(new_sample_path)
print(f"Prediction: {prediction.class_name} (probability: {prediction.probability:.3f})")
```

### Data Flow

```
MethylCentroid Output:
  ├─ centroid.h5 (HDF5 file)
  ├─ metadata (samples, outliers, statistics)
  └─ quality metrics

MethylModeler Input:
  ├─ centroid1.h5
  └─ centroid2.h5

MethylModeler Output:
  ├─ dmps.csv (Differentially Methylated Positions)
  ├─ classifier.pkl (Trained model)
  └─ validation_report.json

MethylClassifier Input:
  └─ classifier.pkl

MethylClassifier Output:
  ├─ predictions (class, probability)
  └─ confidence scores
```

---

## Performance

### Computational Complexity

| Operation | Time Complexity | Space Complexity |
|-----------|----------------|------------------|
| Position Alignment | O(N log M) | O(P) |
| Centroid Calculation | O(N × P) | O(P) |
| Distance Calculation | O(N × P × K) | O(N × K) |
| Outlier Detection | O(I × N × P × K) | O(N × K) |

Where:
- N = number of samples
- P = number of genomic positions
- M = average positions per sample
- K = number of distance metrics
- I = outlier removal iterations

### Benchmarks

#### Dataset Characteristics

- **Small**: 5 samples, 1M positions, CG context
- **Medium**: 25 samples, 10M positions, CG context
- **Large**: 100 samples, 28M positions, CG+CHG+CHH contexts

#### Performance Results (CPU)

| Dataset | Position Alignment | Centroid Calc | Outlier Detection | Total Time |
|---------|-------------------|---------------|-------------------|------------|
| Small | 2s | 5s | 10s | 17s |
| Medium | 15s | 30s | 120s | 165s |
| Large | 120s | 300s | 900s | 1320s |

#### Performance Results (GPU)

| Dataset | Position Alignment | Centroid Calc | Outlier Detection | Total Time | Speedup |
|---------|-------------------|---------------|-------------------|------------|---------|
| Small | 0.1s | 0.3s | 0.8s | 1.2s | **14x** |
| Medium | 0.5s | 2s | 8s | 10.5s | **16x** |
| Large | 5s | 15s | 60s | 80s | **17x** |

### Memory Usage

#### Typical Memory Requirements

| Dataset Size | Samples | Positions | CPU Memory | GPU Memory |
|--------------|---------|-----------|------------|------------|
| Small | 5 | 1M | 500 MB | 200 MB |
| Medium | 25 | 10M | 5 GB | 2 GB |
| Large | 100 | 28M | 40 GB | 12 GB |

#### Memory Optimization Strategies

1. **Smart Caching**: LRU eviction keeps memory usage bounded
2. **Chunked Processing**: Process large datasets in chunks
3. **GPU Memory Pooling**: Reuse GPU allocations across operations
4. **Sparse Accumulation**: Only allocate for observed positions

---

## License

MethylCentroid is licensed under the MIT License.

```
MIT License

Copyright (c) 2024 MethylPipeline Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Citation

If you use MethylCentroid in your research, please cite:

```bibtex
@software{methylcentroid2024,
  title={MethylCentroid: High-Performance Methylation Centroid Calculation with Advanced Outlier Detection},
  author={MethylPipeline Contributors},
  year={2024},
  url={https://github.com/yourusername/MethylPipeline}
}
```

---

## Support and Contributing

### Getting Help

- **Documentation**: https://methylpipeline.readthedocs.io
- **Issues**: https://github.com/yourusername/MethylPipeline/issues
- **Discussions**: https://github.com/yourusername/MethylPipeline/discussions

### Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](../../CONTRIBUTING.md) for guidelines.

### Development Setup

```bash
# Clone repository
git clone https://github.com/yourusername/MethylPipeline.git
cd MethylPipeline/packages/methylcentroid

# Install in development mode
poetry install

# Run tests
poetry run pytest

# Build documentation
cd docs
make html
```

---

## Appendix: Mathematical Derivations

### A. Centroid Variance Calculation

For a centroid with accumulated statistics:

$$
\text{Var}(x) = E[x^2] - (E[x])^2
$$

Given:
- $S_x = \sum x_i$
- $S_{x^2} = \sum x_i^2$
- $N$ = sample count

We calculate:

$$
\mu = \frac{S_x}{N}, \quad \sigma^2 = \frac{S_{x^2}}{N} - \mu^2
$$

### B. Beta Distribution MLE

Maximum likelihood estimation for Beta parameters:

Given observations $x_1, \ldots, x_n$:

$$
\mathcal{L}(\alpha, \beta) = \prod_{i=1}^n \frac{x_i^{\alpha-1}(1-x_i)^{\beta-1}}{B(\alpha, \beta)}
$$

Log-likelihood:

$$
\ell(\alpha, \beta) = (\alpha-1)\sum\log x_i + (\beta-1)\sum\log(1-x_i) - n\log B(\alpha, \beta)
$$

Optimization via numerical methods (scipy.optimize) to find $\hat{\alpha}, \hat{\beta}$.

### C. General Simes Formula

For combining p-values from multiple tests:

Given p-values $p_1, \ldots, p_k$ sorted in ascending order:

$$
p_{\text{Simes}} = \min_{i=1,\ldots,k} \frac{k \cdot p_i}{i}
$$

**Application in MethylCentroid**:

When `min_metrics_agree=0`, use General Simes to combine p-values across metrics:

```python
sorted_pvals = np.sort(p_values)
k = len(sorted_pvals)
simes_pval = min(k * sorted_pvals[i] / (i+1) for i in range(k))
```

### D. Information-Theoretic Distance Bounds

**Pinsker's Inequality**:

$$
D_{\text{TV}}(P, Q) \leq \sqrt{\frac{1}{2} D_{\text{KL}}(P \| Q)}
$$

Where $D_{\text{TV}}$ is total variation distance.

**Jensen-Shannon Bound**:

$$
0 \leq D_{\text{JS}}(P, Q) \leq \log 2 \approx 0.693
$$

**Hellinger Bound**:

$$
0 \leq D_{\text{Hellinger}}(P, Q) \leq \sqrt{2}
$$

---

*End of MethylCentroid Comprehensive Documentation*

**Last Updated**: October 2024  
**Version**: 2.0.0

-->

