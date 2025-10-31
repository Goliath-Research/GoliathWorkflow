# MethylUtils: Comprehensive Documentation

## Table of Contents

1. [Overview](#overview)
2. [Mathematical Theory](#mathematical-theory)
3. [Core Concepts](#core-concepts)
4. [Module Organization](#module-organization)
5. [API Reference](#api-reference)
6. [Configuration](#configuration)
7. [Advanced Features](#advanced-features)
8. [Usage Examples](#usage-examples)
9. [Troubleshooting](#troubleshooting)
10. [Integration with MethylPipeline](#integration-with-methylpipeline)
11. [Performance](#performance)
12. [License](#license)

---

## Overview

**MethylUtils** is the foundational library for the entire MethylPipeline ecosystem. It provides high-performance computational infrastructure for methylation data analysis, optimized for genome-scale processing on NVIDIA GPUs.

### What is MethylUtils?

MethylUtils serves as the computational engine that powers all other packages in the MethylPipeline:

- **Shared Utilities**: Logging, GPU management, memory optimization
- **Core Data Structures**: `MethylSample`, position aligners, centroid pairs
- **Statistical Engine**: 7 distance metrics, FDR correction, Beta distribution operations
- **Performance Infrastructure**: GPU acceleration, chunked processing, profiling

### Key Features

- **Automatic GPU Acceleration**: 10-100x speedup on NVIDIA GH200 with automatic CPU fallback
- **Genome-Scale Processing**: Handles 3B+ positions efficiently with intelligent chunking
- **Advanced Statistics**: 7 information-theoretic distance metrics for Beta distributions
- **Memory Efficient**: Intelligent memory management, pooling, and memory-mapped I/O
- **Type Safe**: Full type hints and comprehensive validation
- **Factory Pattern**: Extensible metric computation system
- **Performance Monitoring**: Real-time profiling and bottleneck analysis
- **Container Ready**: Designed for Docker deployment with dependency fallbacks

---

## Mathematical Theory

### Beta Distribution Foundation

MethylUtils is built on the mathematical foundation that methylation levels follow **Beta distributions**:

$$
\text{Beta}(x; \alpha, \beta) = \frac{x^{\alpha-1}(1-x)^{\beta-1}}{B(\alpha, \beta)}
$$

where $B(\alpha, \beta)$ is the Beta function:

$$
B(\alpha, \beta) = \frac{\Gamma(\alpha)\Gamma(\beta)}{\Gamma(\alpha + \beta)}
$$

**Why Beta Distributions?**
- Methylation levels are bounded: $x \in [0, 1]$
- Beta distribution is the conjugate prior for Bernoulli trials
- Allows exact probabilistic inference
- Naturally handles uncertainty quantification

### Parameter Estimation

#### Method of Moments (MOM)

Given methylation levels $x_1, \ldots, x_n$:

$$
\bar{x} = \frac{1}{n}\sum_{i=1}^n x_i, \quad s^2 = \frac{1}{n-1}\sum_{i=1}^n (x_i - \bar{x})^2
$$

MOM estimators:

$$
\hat{\alpha} = \bar{x}\left(\frac{\bar{x}(1-\bar{x})}{s^2} - 1\right), \quad \hat{\beta} = (1-\bar{x})\left(\frac{\bar{x}(1-\bar{x})}{s^2} - 1\right)
$$

#### Maximum Likelihood Estimation (MLE)

Log-likelihood for Beta distribution:

$$
\ell(\alpha, \beta) = (\alpha-1)\sum_{i=1}^n \log x_i + (\beta-1)\sum_{i=1}^n \log(1-x_i) - n\log B(\alpha, \beta)
$$

Optimized numerically using `scipy.optimize` or GPU-accelerated solvers.

### Information-Theoretic Distances

MethylUtils implements 7 distance metrics for comparing Beta distributions:

#### 1. Jeffreys Divergence

Symmetrized Kullback-Leibler divergence:

$$
D_{\text{Jeffreys}}(\alpha_1, \beta_1, \alpha_2, \beta_2) = D_{\text{KL}}(P_1 \| P_2) + D_{\text{KL}}(P_2 \| P_1)
$$

where:

$$
D_{\text{KL}}(P_1 \| P_2) = \log\frac{B(\alpha_2, \beta_2)}{B(\alpha_1, \beta_1)} + (\alpha_1 - \alpha_2)[\psi(\alpha_1) - \psi(\alpha_1 + \beta_1)]
$$
$$
+ (\beta_1 - \beta_2)[\psi(\beta_1) - \psi(\alpha_1 + \beta_1)]
$$

$\psi$ is the digamma function.

**Properties**:
- Symmetric
- Information-theoretic measure
- Sensitive to distribution differences
- **Use when**: Emphasizing probability distribution divergence

#### 2. Jensen-Shannon Divergence

Bounded, symmetric measure:

$$
D_{\text{JS}}(P_1, P_2) = \frac{1}{2}D_{\text{KL}}(P_1 \| M) + \frac{1}{2}D_{\text{KL}}(P_2 \| M)
$$

where $M = \frac{1}{2}(P_1 + P_2)$ is the mixture distribution.

**Properties**:
- Bounded: $0 \leq D_{\text{JS}} \leq \log 2$
- Square root is a proper metric
- Less sensitive to extreme values
- **Use when**: Need bounded, interpretable distances

#### 3. Weighted Jensen-Shannon Divergence

Entropy-weighted version emphasizing high-certainty positions:

$$
D_{\text{WJS}}(P_1, P_2) = \sum_i w_i \cdot D_{\text{JS}, i}(P_1, P_2)
$$

where weights:

$$
w_i = \frac{1}{H(P_i) + \epsilon}, \quad H(P) = -\int P(x)\log P(x)\,dx
$$

**Properties**:
- Down-weights ambiguous positions (high entropy)
- Emphasizes informative positions
- **Use when**: Focusing on biologically certain regions

#### 4. Hellinger Distance

Square-root based metric:

$$
D_{\text{Hellinger}}(P_1, P_2) = \sqrt{1 - BC(P_1, P_2)}
$$

where $BC$ is the Bhattacharyya Coefficient:

$$
BC(\alpha_1, \beta_1, \alpha_2, \beta_2) = \frac{B\left(\frac{\alpha_1 + \alpha_2}{2}, \frac{\beta_1 + \beta_2}{2}\right)}{\sqrt{B(\alpha_1, \beta_1) \cdot B(\alpha_2, \beta_2)}}
$$

**Properties**:
- Proper metric (satisfies triangle inequality)
- Bounded: $0 \leq D_{\text{Hellinger}} \leq 1$
- Robust to outliers
- **Use when**: Need geometric interpretation

#### 5. Bhattacharyya Distance

Information-theoretic measure:

$$
D_{\text{Bhattacharyya}} = -\log BC(\alpha_1, \beta_1, \alpha_2, \beta_2)
$$

**Properties**:
- Related to Hellinger distance
- Natural logarithm scale
- **Use when**: Probabilistic error bounds needed

#### 6. Wasserstein Distance

Optimal transport distance:

$$
W_p(P_1, P_2) = \left(\int_0^1 |F_1^{-1}(u) - F_2^{-1}(u)|^p\,du\right)^{1/p}
$$

where $F_i^{-1}$ is the quantile function.

**Properties**:
- Proper metric
- Accounts for distribution shape
- Computationally expensive
- **Use when**: Distribution shape matters

#### 7. Total Variation Distance

Maximum probability mass difference:

$$
D_{\text{TV}}(P_1, P_2) = \frac{1}{2}\int |P_1(x) - P_2(x)|\,dx
$$

**Properties**:
- Bounded: $0 \leq D_{\text{TV}} \leq 1$
- Interpretable as probability difference
- **Use when**: Need intuitive interpretation

### Statistical Testing

#### Likelihood Ratio Test

For testing $H_0: \alpha_1 = \alpha_2, \beta_1 = \beta_2$:

$$
\Lambda = -2\log\frac{\mathcal{L}(H_0)}{\mathcal{L}(H_1)}
$$

Under $H_0$, $\Lambda \sim \chi^2_2$ (2 degrees of freedom).

P-value:

$$
p = P(\chi^2_2 \geq \Lambda) = 1 - F_{\chi^2_2}(\Lambda)
$$

#### FDR Correction: Storey's q-value Method

For $m$ hypotheses with p-values $p_1, \ldots, p_m$:

**Step 1: Estimate $\pi_0$ (proportion of true nulls)**

$$
\hat{\pi}_0(\lambda) = \frac{\#\{p_i > \lambda\}}{m(1-\lambda)}
$$

Typically use $\lambda = 0.5$ or optimize over a range.

**Step 2: Compute q-values**

Sort p-values: $p_{(1)} \leq p_{(2)} \leq \cdots \leq p_{(m)}$

$$
q_{(i)} = \min_{j \geq i} \left\{\hat{\pi}_0 \cdot \frac{m \cdot p_{(j)}}{j}\right\}
$$

**Advantage over Benjamini-Hochberg**:
- Adaptive: estimates $\pi_0$ from data
- More powerful when many true nulls exist
- Recommended for genomics data

---

## Core Concepts

### 1. MethylSample Data Structure

Central data structure representing methylation samples:

```python
@dataclass
class MethylSample:
    # Core data (always present)
    pos: np.ndarray      # uint32 - genomic positions
    mC: np.ndarray       # uint32 - methylated counts
    uC: np.ndarray       # uint32 - unmethylated counts
    tnc: np.ndarray      # uint8 - trinucleotide context + strand
    
    # Centroid data (optional)
    N: Optional[np.ndarray]    # uint32 - sample counts per position
    Sx: Optional[np.ndarray]   # float32 - sum of methylation levels
    Sx2: Optional[np.ndarray]  # float32 - sum of squared levels
    
    # Extended centroid (optional)
    log_x_sum: Optional[np.ndarray]           # float32 - log statistics
    log_1_minus_x_sum: Optional[np.ndarray]   # float32 - log statistics
```

**Key Methods**:
- `load_from_h5()`: Load from HDF5 file
- `save_to_h5()`: Save to HDF5 file
- `get_methylation_levels()`: Calculate methylation fractions
- `filter_by_coverage()`: Apply coverage threshold
- `align_to_positions()`: Align to reference positions

### 2. PositionAligner

Handles genomic position alignment across multiple samples:

**Algorithm**:
1. Union all positions: $P = \bigcup_{j=1}^{N} P_j$
2. Create accumulators for each position
3. For each sample, update accumulators at matching positions
4. Track sample count $N$ per position

**Complexity**: $O(N \log M)$ where $N$ = samples, $M$ = average positions

**GPU Acceleration**:
- Position intersection: 50x speedup
- Accumulator updates: 20x speedup
- Overall alignment: 30x speedup

### 3. MethylCentroidPair

Statistical comparison of two methylation centroids:

**Workflow**:
```
1. Load two centroids
2. Find common positions
3. Estimate Beta parameters (MLE)
4. Perform likelihood ratio tests
5. Apply FDR correction (Storey's method)
6. Compute effect sizes
7. Return DMPs with statistics
```

**Output Statistics**:
- p-values and q-values (FDR-corrected)
- Beta parameters ($\alpha_1, \beta_1, \alpha_2, \beta_2$)
- Mean methylation levels
- Delta mean (effect size)
- Bhattacharyya distance

### 4. ProbabilisticBetaClassifier

Bayesian classifier using Beta distributions:

**Classification Formula**:

$$
P(\text{Class } k | \mathbf{x}) = \frac{P(\mathbf{x} | \text{Class } k) \cdot P(\text{Class } k)}{\sum_j P(\mathbf{x} | \text{Class } j) \cdot P(\text{Class } j)}
$$

**Log-space Computation** (numerical stability):

$$
\log P(\text{Class } k | \mathbf{x}) = \log P(\text{Class } k) + \sum_{i=1}^{n} \log \text{Beta}(x_i; \alpha_{k,i}, \beta_{k,i})
$$

**Advanced Features**:
- Temperature scaling for calibration
- Platt scaling for posterior adjustment
- Missing data handling via availability masks
- Weighted DMPs for importance

---

## Module Organization

MethylUtils is organized into specialized modules following SOLID principles:

### Core Analysis Modules

#### metrics_core
Core metric computation functions:
- `compute_jeffreys_divergence()`
- `compute_jensen_shannon_divergence()`
- `compute_weighted_jensen_shannon()`
- `compute_hellinger_distance()`
- `compute_bhattacharyya_distance()`
- `compute_wasserstein_distance()`
- `compute_total_variation_distance()`

#### metrics_factory
Factory pattern for metric management:
```python
from methyl_utils import MetricFactory

factory = MetricFactory()
metric_func = factory.get_metric("jensen_shannon")
distance = metric_func(a1, b1, a2, b2)
```

#### statistical_tests
Statistical testing functions:
- `likelihood_ratio_test_beta()`: LRT for Beta distributions
- `beta_mle_estimation()`: MLE parameter estimation
- `beta_mom_estimation()`: Method of moments estimation
- `storey_qvalue()`: Storey's FDR correction
- `benjamini_hochberg()`: BH FDR correction

#### genomic_utils
Genomic utility functions:
- `group_by_gene()`: Group positions by gene
- `filter_by_region()`: Filter positions by genomic region
- `calculate_coverage()`: Coverage statistics

### Performance Optimization Modules

#### memory_manager
Advanced memory management:
```python
from methyl_utils import get_memory_manager

mem_mgr = get_memory_manager()
stats = mem_mgr.get_memory_usage()
mem_mgr.set_memory_limit_gb(80.0)
```

Features:
- Memory usage monitoring
- Automatic cleanup
- Memory pooling
- GPU memory management

#### chunked_processor
Intelligent chunking for large datasets:
```python
from methyl_utils import ChunkedGenomicProcessor

processor = ChunkedGenomicProcessor(chunk_size=1_000_000)
for chunk in processor.process_file(hdf5_file):
    process_chunk(chunk)
```

#### performance_profiler
Real-time performance monitoring:
```python
from methyl_utils import start_performance_monitoring, get_performance_profiler

monitor = start_performance_monitoring(interval=1.0)
# ... your code ...
profiler = get_performance_profiler()
report = profiler.get_report()
```

### Infrastructure Modules

#### gpu_detection
Comprehensive GPU detection and management:
```python
from methyl_utils import (
    is_gpu_available,
    get_gpu_memory_gb,
    get_gpu_device_count,
    print_gpu_status,
    cleanup_gpu_memory
)

if is_gpu_available():
    print(f"GPU Memory: {get_gpu_memory_gb():.1f} GB")
```

#### gpu_utils
GPU/CPU backend utilities:
- `create_gpu_array()`: Create GPU or CPU array
- `to_cpu_array()`: Transfer GPU to CPU
- `_prepare_arrays_for_backend()`: Automatic backend selection
- `_ensure_cpu_output()`: Ensure CPU output

#### logging_utils
Centralized logging configuration:
```python
from methyl_utils import get_logger, setup_logging

logger = get_logger(__name__)
setup_logging(level="INFO", log_file="analysis.log")
```

#### metric_validations
Input validation for all metrics:
- `validate_beta_parameters()`: Validate $\alpha, \beta > 0$
- `validate_methylation_data()`: Validate methylation levels $\in [0, 1]$
- `validate_sample_data()`: Comprehensive sample validation

---

## API Reference

### MethylSample Class

Main class for methylation data:

```python
class MethylSample:
    @classmethod
    def load_from_h5(cls, file_path: str) -> 'MethylSample':
        """Load sample from HDF5 file."""
    
    def save_to_h5(self, file_path: str, metadata: dict = None):
        """Save sample to HDF5 file with metadata."""
    
    def get_methylation_levels(self) -> np.ndarray:
        """Calculate methylation levels: mC / (mC + uC)."""
    
    def filter_by_coverage(self, min_coverage: int = 4) -> 'MethylSample':
        """Filter positions by minimum coverage."""
    
    def align_to_positions(self, positions: np.ndarray) -> 'MethylSample':
        """Align sample to reference positions."""
    
    @property
    def is_centroid(self) -> bool:
        """Check if this is a centroid (has N field)."""
    
    @property
    def is_extended_centroid(self) -> bool:
        """Check if this is an extended centroid (has log fields)."""
    
    @property
    def memory_usage_mb(self) -> float:
        """Calculate memory usage in MB."""
```

### PositionAligner Class

Position alignment across samples:

```python
class PositionAligner:
    def __init__(self, max_samples: int = 1000, use_gpu: bool = True):
        """Initialize position aligner."""
    
    def add_sample(self, sample: MethylSample):
        """Add a sample to the aligner."""
    
    def remove_sample(self, sample_index: int):
        """Remove a sample from the aligner."""
    
    def get_positions(self) -> np.ndarray:
        """Get union of all positions."""
    
    def get_accumulators(self) -> dict:
        """Get accumulator arrays (N, Sx, Sx2)."""
    
    def get_centroid(self, min_coverage: int = 1) -> MethylSample:
        """Calculate and return centroid."""
    
    @property
    def sample_count(self) -> int:
        """Number of samples in aligner."""
```

### MethylCentroidPair Class

Statistical comparison of centroids:

```python
class MethylCentroidPair:
    def __init__(
        self,
        centroid1: Union[str, MethylSample],
        centroid2: Union[str, MethylSample],
        alpha: float = 0.05,
        use_gpu: bool = True
    ):
        """Initialize centroid pair for comparison."""
    
    def find_dmps(
        self,
        min_delta_mean: float = 0.0,
        min_N_pct: float = 0.0
    ) -> pd.DataFrame:
        """Find differentially methylated positions."""
    
    def compute_statistics(self) -> pd.DataFrame:
        """Compute comprehensive statistics for all positions."""
    
    def get_dmp_count(self, q_threshold: float = 0.05) -> int:
        """Count DMPs at given q-value threshold."""
```

### ProbabilisticBetaClassifier Class

Bayesian classifier:

```python
class ProbabilisticBetaClassifier:
    def __init__(self, data: Dict[str, np.ndarray]):
        """Initialize with training data."""
    
    def predict_proba(
        self,
        X: np.ndarray,
        availability_mask: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """Predict posterior probabilities."""
    
    def predict(
        self,
        X: np.ndarray,
        availability_mask: Optional[np.ndarray] = None,
        threshold: float = 0.5
    ) -> np.ndarray:
        """Predict class labels."""
    
    def set_temperature(self, temperature: float = 1.0):
        """Set temperature for calibration."""
    
    def calibrate_platt(
        self,
        X_val: np.ndarray,
        y_val: np.ndarray
    ):
        """Calibrate probabilities using Platt scaling."""
```

### Distance Computation Functions

High-level distance computation:

```python
def auto_compute_distance(
    a1: np.ndarray,
    b1: np.ndarray,
    a2: np.ndarray,
    b2: np.ndarray,
    metric: str = "jensen_shannon",
    weights: Optional[np.ndarray] = None,
    use_gpu: bool = True
) -> np.ndarray:
    """
    Compute distance using specified metric.
    
    Args:
        a1, b1: Beta parameters for distribution 1
        a2, b2: Beta parameters for distribution 2
        metric: Distance metric to use
        weights: Optional weights for each position
        use_gpu: Whether to use GPU acceleration
    
    Returns:
        Array of distance values
    """
```

Available metrics:
- `"jeffreys"`
- `"jensen_shannon"`
- `"weighted_jensen_shannon"`
- `"hellinger"`
- `"bhattacharyya"`
- `"wasserstein"`
- `"total_variation"`

---

## Configuration

MethylUtils uses environment variables and function parameters for configuration:

### Environment Variables

```bash
# GPU Configuration
export CUDA_VISIBLE_DEVICES="0"          # GPU device ID
export CUPY_CACHE_DIR="/tmp/cupy_cache"  # CuPy cache directory

# Memory Configuration
export METHYLUTILS_MAX_MEMORY_GB="80"    # Maximum memory usage

# Logging Configuration
export METHYLUTILS_LOG_LEVEL="INFO"      # Log level (DEBUG, INFO, WARNING, ERROR)
export METHYLUTILS_LOG_FILE="methyl.log" # Log file path
```

### Function Parameters

Most functions accept configuration parameters:

```python
# GPU usage
result = auto_compute_distance(a1, b1, a2, b2, use_gpu=True)

# Memory limits
mem_mgr = get_memory_manager()
mem_mgr.set_memory_limit_gb(80.0)

# Chunk size
processor = ChunkedGenomicProcessor(chunk_size=1_000_000)

# Logging
logger = get_logger(__name__, level="DEBUG")
```

---

## Advanced Features

### 1. Automatic GPU Acceleration

MethylUtils automatically detects and uses GPU acceleration:

**Detection Logic**:
```python
if is_gpu_available():
    # Use CuPy for array operations
    # Use cupyx.scipy for special functions
    # GPU memory management
else:
    # Automatic CPU fallback
    # Use NumPy and SciPy
```

**Performance Gains**:
- Array operations: 50-100x
- Distance calculations: 20-50x
- Statistical tests: 10-30x

### 2. Memory-Mapped HDF5 Operations

Efficient I/O for large genomic files:

```python
sample = MethylSample.load_from_h5(
    file_path,
    use_memmap=True  # Memory-mapped mode
)

# Data loaded on-demand, not all in RAM
methylation = sample.get_methylation_levels()
```

### 3. Parallel Processing

Multi-threaded and multiprocessing support:

```python
from methyl_utils import parallel_process_samples
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=8) as executor:
    futures = [
        executor.submit(process_sample, sample_path)
        for sample_path in sample_paths
    ]
    results = [f.result() for f in futures]
```

### 4. Performance Profiling

Real-time performance monitoring:

```python
from methyl_utils import start_performance_monitoring, get_performance_profiler

# Start monitoring
monitor = start_performance_monitoring(interval=1.0)

# Your analysis code
for sample in samples:
    process_sample(sample)

# Get profiling report
profiler = get_performance_profiler()
report = profiler.get_report()

print(f"Total time: {report['total_time']:.2f}s")
print(f"Peak memory: {report['peak_memory_gb']:.2f} GB")
print(f"GPU utilization: {report['gpu_utilization_percent']:.1f}%")
```

### 5. Factory Pattern for Metrics

Extensible metric system:

```python
from methyl_utils import MetricFactory, register_metric

# Register custom metric
@register_metric('custom_distance')
def custom_distance(a1, b1, a2, b2, use_gpu=True):
    # Custom distance implementation
    return distance_values

# Use factory
factory = MetricFactory()
metric_func = factory.get_metric('custom_distance')
distance = metric_func(a1, b1, a2, b2)
```

### 6. GPU Memory Pooling

Efficient GPU memory reuse:

```python
from methyl_utils import get_cupy

cp = get_cupy()
if cp is not None:
    # Create memory pool
    mempool = cp.get_default_memory_pool()
    
    # Your GPU operations
    gpu_array = cp.array(data)
    result = gpu_operation(gpu_array)
    
    # Free memory
    mempool.free_all_blocks()
```

---

## Usage Examples

### Example 1: Basic Sample Loading and Analysis

```python
from methyl_utils import MethylSample

# Load sample from HDF5
sample = MethylSample.load_from_h5('/data/sample1/chr1-CG.h5')

print(f"Sample has {len(sample.pos)} positions")
print(f"Memory usage: {sample.memory_usage_mb:.1f} MB")

# Get methylation levels
methylation = sample.get_methylation_levels()
print(f"Mean methylation: {methylation.mean():.3f}")

# Filter by coverage
filtered = sample.filter_by_coverage(min_coverage=10)
print(f"After filtering: {len(filtered.pos)} positions")

# Save filtered sample
filtered.save_to_h5('/output/sample1_filtered.h5', 
                    metadata={'min_coverage': 10})
```

### Example 2: Distance Computation

```python
from methyl_utils import auto_compute_distance
import numpy as np

# Beta parameters from two centroids
alpha1 = np.array([5.0, 2.0, 8.0, 3.0])
beta1 = np.array([3.0, 6.0, 2.0, 5.0])
alpha2 = np.array([2.0, 8.0, 2.0, 7.0])
beta2 = np.array([6.0, 2.0, 6.0, 2.0])

# Compute Jensen-Shannon divergence
js_distance = auto_compute_distance(
    alpha1, beta1, alpha2, beta2,
    metric="jensen_shannon",
    use_gpu=True
)

print("Jensen-Shannon distances:", js_distance)

# Compute multiple metrics
for metric in ["jeffreys", "hellinger", "bhattacharyya"]:
    distance = auto_compute_distance(
        alpha1, beta1, alpha2, beta2,
        metric=metric,
        use_gpu=True
    )
    print(f"{metric}: {distance}")
```

### Example 3: Position Alignment

```python
from methyl_utils import PositionAligner, MethylSample

# Initialize aligner
aligner = PositionAligner(max_samples=100, use_gpu=True)

# Load and add samples
sample_paths = [
    '/data/sample1/chr1-CG.h5',
    '/data/sample2/chr1-CG.h5',
    '/data/sample3/chr1-CG.h5'
]

for path in sample_paths:
    sample = MethylSample.load_from_h5(path)
    aligner.add_sample(sample)

print(f"Aligned {aligner.sample_count} samples")
print(f"Total positions: {aligner.total_positions}")

# Get centroid
centroid = aligner.get_centroid(min_coverage=4)

# Save centroid
centroid.save_to_h5('/output/centroid.h5', 
                    metadata={'samples': sample_paths})
```

### Example 4: Centroid Comparison (DMP Detection)

```python
from methyl_utils import MethylCentroidPair

# Load and compare centroids
pair = MethylCentroidPair(
    centroid1='/data/healthy_centroid.h5',
    centroid2='/data/cancer_centroid.h5',
    alpha=0.05,
    use_gpu=True
)

# Find DMPs with filtering
dmps = pair.find_dmps(
    min_delta_mean=0.2,  # Minimum effect size
    min_N_pct=0.10       # Minimum coverage percentage
)

print(f"Found {len(dmps)} DMPs")
print(dmps.head())

# Statistics summary
print(f"Mean delta: {dmps['delta_mean'].abs().mean():.3f}")
print(f"Mean Bhattacharyya: {dmps['bhattacharyya'].mean():.3f}")

# Save DMPs
dmps.to_csv('/output/dmps.csv', index=False)
```

### Example 5: Classification with ProbabilisticBetaClassifier

```python
from methyl_utils import ProbabilisticBetaClassifier
import numpy as np

# Training data (from DMP detection)
training_data = {
    'positions': np.array([100, 200, 300, 400, 500]),
    'alpha1': np.array([5.0, 2.0, 8.0, 3.0, 6.0]),
    'beta1': np.array([3.0, 6.0, 2.0, 5.0, 4.0]),
    'alpha2': np.array([2.0, 8.0, 2.0, 7.0, 3.0]),
    'beta2': np.array([6.0, 2.0, 6.0, 2.0, 7.0]),
    'weights': np.array([0.9, 0.85, 0.92, 0.88, 0.90]),
    'directions': np.array([1, -1, 1, 1, -1])
}

# Initialize classifier
classifier = ProbabilisticBetaClassifier(training_data)

# New samples (5 DMPs, 3 samples)
new_samples = np.array([
    [0.75, 0.23, 0.89, 0.34, 0.21],  # Sample 1
    [0.12, 0.88, 0.15, 0.82, 0.90],  # Sample 2
    [0.65, 0.34, 0.78, 0.45, 0.32]   # Sample 3
])

# Predict probabilities
probs = classifier.predict_proba(new_samples)
print("Posterior probabilities:")
print(probs)

# Predict classes
predictions = classifier.predict(new_samples, threshold=0.5)
print("Predictions:", predictions)

# With missing data handling
availability_mask = np.array([
    [True, True, False, True, True],   # Sample 1: missing position 3
    [True, True, True, False, True],   # Sample 2: missing position 4
    [True, False, True, True, True]    # Sample 3: missing position 2
])

probs_masked = classifier.predict_proba(new_samples, availability_mask)
print("Probabilities (with missing data):")
print(probs_masked)
```

### Example 6: GPU Memory Management

```python
from methyl_utils import (
    is_gpu_available,
    get_gpu_memory_gb,
    cleanup_gpu_memory,
    get_memory_manager
)

if is_gpu_available():
    # Check initial GPU memory
    print(f"GPU Memory: {get_gpu_memory_gb():.1f} GB")
    
    # Set memory limit
    mem_mgr = get_memory_manager()
    mem_mgr.set_memory_limit_gb(80.0)
    
    # Your GPU operations
    # ...
    
    # Check memory usage
    stats = mem_mgr.get_memory_usage()
    print(f"Used: {stats['gpu_used_gb']:.1f} / {stats['gpu_total_gb']:.1f} GB")
    print(f"Utilization: {stats['gpu_utilization_percent']:.1f}%")
    
    # Cleanup when done
    cleanup_gpu_memory()
    print("GPU memory cleaned up")
```

### Example 7: Batch Processing with Chunking

```python
from methyl_utils import ChunkedGenomicProcessor, MethylSample

# Process large genomic file in chunks
processor = ChunkedGenomicProcessor(
    chunk_size=1_000_000,  # 1M positions per chunk
    max_memory_gb=50.0
)

sample_path = '/data/large_sample.h5'
results = []

with processor.process_file_chunked(sample_path) as chunks:
    for chunk_idx, chunk_data in enumerate(chunks):
        print(f"Processing chunk {chunk_idx + 1}...")
        
        # Process chunk
        chunk_result = analyze_chunk(chunk_data)
        results.append(chunk_result)

# Combine results
final_result = combine_chunk_results(results)
print(f"Processed {len(results)} chunks")
```

---

## Troubleshooting

### Common Issues and Solutions

#### 1. GPU Not Detected

**Problem**: GPU available but not being used

**Diagnosis**:
```python
from methyl_utils import (
    is_gpu_available,
    print_gpu_status,
    get_gpu_error_message
)

print_gpu_status()
if not is_gpu_available():
    print(f"Error: {get_gpu_error_message()}")
```

**Solutions**:
```bash
# Check CUDA installation
nvidia-smi

# Check CuPy installation
python -c "import cupy as cp; print(cp.__version__)"

# Install matching CuPy version
pip install cupy-cuda11x  # Replace with your CUDA version

# Set CUDA device
export CUDA_VISIBLE_DEVICES="0"
```

#### 2. Out of Memory Errors

**Problem**: Process crashes with memory errors

**Solutions**:
```python
# Reduce chunk size
processor = ChunkedGenomicProcessor(chunk_size=500_000)

# Set memory limit
mem_mgr = get_memory_manager()
mem_mgr.set_memory_limit_gb(50.0)

# Use memory-mapped I/O
sample = MethylSample.load_from_h5(path, use_memmap=True)

# Process in smaller batches
for batch in batched(samples, batch_size=10):
    process_batch(batch)
    cleanup_gpu_memory()
```

#### 3. Slow Performance

**Problem**: Processing slower than expected

**Diagnosis**:
```python
from methyl_utils import start_performance_monitoring, get_performance_profiler

monitor = start_performance_monitoring()
# ... your code ...
profiler = get_performance_profiler()
report = profiler.get_report()

# Check bottlenecks
print(f"I/O time: {report['io_time_percent']:.1f}%")
print(f"Compute time: {report['compute_time_percent']:.1f}%")
print(f"GPU utilization: {report['gpu_utilization_percent']:.1f}%")
```

**Solutions**:
```python
# Enable GPU acceleration
result = auto_compute_distance(a1, b1, a2, b2, use_gpu=True)

# Use parallel processing
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=8) as executor:
    results = list(executor.map(process_sample, samples))

# Optimize chunk size
processor = ChunkedGenomicProcessor(chunk_size=2_000_000)
```

#### 4. Import Errors

**Problem**: Cannot import MethylUtils modules

**Solutions**:
```bash
# Check installation
pip show methyl-utils

# Install in development mode
cd packages/methylutils
pip install -e .

# Check Python path
python -c "import sys; print('\n'.join(sys.path))"

# Add to PYTHONPATH
export PYTHONPATH="/path/to/MethylPipeline/packages/methylutils:$PYTHONPATH"
```

#### 5. HDF5 File Corruption

**Problem**: Cannot read HDF5 files

**Diagnosis**:
```python
import h5py

try:
    with h5py.File(file_path, 'r') as f:
        print(f"Keys: {list(f.keys())}")
        print(f"Attributes: {dict(f.attrs)}")
except Exception as e:
    print(f"File corrupted: {e}")
```

**Solutions**:
```python
# Validate file
from methyl_utils import MethylSample

try:
    sample = MethylSample.load_from_h5(file_path)
    print(f"Valid file: {len(sample.pos)} positions")
except Exception as e:
    print(f"Invalid file: {e}")
    # Re-generate file

# Check HDF5 compression
h5py.File(file_path, 'r')['methylation_data'].compression
```

#### 6. Numerical Instability

**Problem**: NaN or Inf values in results

**Solutions**:
```python
# Clip values to valid range
methylation = np.clip(methylation, 1e-6, 1-1e-6)

# Use log-space computation
log_likelihood = compute_log_likelihood(data)  # More stable

# Validate inputs
from methyl_utils import validate_beta_parameters
validate_beta_parameters(alpha, beta)  # Raises error if invalid
```

---

## Integration with MethylPipeline

MethylUtils serves as the foundation for all MethylPipeline packages:

### Dependency Graph

```
                    MethylUtils (Foundation)
                           |
        +------------------+------------------+
        |                  |                  |
  MethylCentroid    MethylModeler     MethylCluster
        |                  |                  |
        +--------+---------+                  |
                 |                            |
           MethylTrainer                      |
                 |                            |
                 +------------+---------------+
                              |
                        MethylClassifier
                              |
                        MethylEnricher
```

### Usage by Other Packages

#### MethylCentroid
```python
from methyl_utils import (
    PositionAligner,        # Position alignment
    MethylSample,           # Data structure
    auto_compute_distance,  # Outlier detection
    get_gpu_manager        # GPU acceleration
)
```

#### MethylModeler
```python
from methyl_utils import (
    MethylCentroidPair,     # DMP detection
    MethylSample,           # Load centroids
    ProbabilisticBetaClassifier  # Train classifier
)
```

#### MethylTrainer
```python
from methyl_utils import (
    MethylCentroidPair,     # Find DMPs
    ProbabilisticBetaClassifier,  # Create model
    beta_mle_estimation     # Parameter estimation
)
```

#### MethylClassifier
```python
from methyl_utils import (
    ProbabilisticBetaClassifier,  # Load and use model
    MethylSample            # Load sample data
)
```

#### MethylCluster
```python
from methyl_utils import (
    auto_compute_distance,  # Distance matrix
    MethylSample,           # Load samples
    get_gpu_manager        # GPU acceleration
)
```

### Shared Configuration

MethylUtils provides centralized configuration for the entire pipeline:

```python
# GPU settings (affects all packages)
from methyl_utils import get_gpu_manager
gpu_mgr = get_gpu_manager()
gpu_mgr.set_device(0)

# Logging (affects all packages)
from methyl_utils import setup_logging
setup_logging(level="INFO", log_file="pipeline.log")

# Memory management (affects all packages)
from methyl_utils import get_memory_manager
mem_mgr = get_memory_manager()
mem_mgr.set_memory_limit_gb(80.0)
```

---

## Performance

### Computational Complexity

| Operation | Time Complexity | Space Complexity | GPU Speedup |
|-----------|----------------|------------------|-------------|
| Load HDF5 Sample | O(P) | O(P) | 5x (I/O) |
| Position Alignment | O(N log M) | O(P) | 30x |
| Distance Calculation | O(P) | O(P) | 20-50x |
| Beta MLE Estimation | O(P × I) | O(P) | 10-30x |
| Likelihood Ratio Test | O(P) | O(P) | 15-40x |
| FDR Correction | O(P log P) | O(P) | 10x |

Where:
- P = number of genomic positions
- N = number of samples
- M = average positions per sample
- I = optimization iterations

### Benchmarks

#### Distance Calculations

Dataset: 10M positions, various metrics

| Metric | CPU Time | GPU Time | Speedup |
|--------|----------|----------|---------|
| Jeffreys | 2.5s | 0.05s | 50x |
| Jensen-Shannon | 2.2s | 0.08s | 28x |
| Weighted JS | 3.0s | 0.12s | 25x |
| Hellinger | 1.8s | 0.09s | 20x |
| Bhattacharyya | 1.5s | 0.06s | 25x |
| Wasserstein | 8.0s | 0.40s | 20x |

#### Position Alignment

| Samples | Positions | CPU Time | GPU Time | Speedup |
|---------|-----------|----------|----------|---------|
| 10 | 1M | 5s | 0.2s | 25x |
| 50 | 10M | 120s | 4s | 30x |
| 100 | 28M | 600s | 20s | 30x |

#### Beta MLE Estimation

| Positions | CPU Time | GPU Time | Speedup |
|-----------|----------|----------|---------|
| 1M | 8s | 0.3s | 27x |
| 10M | 80s | 3s | 27x |
| 28M | 220s | 8s | 28x |

### Memory Usage

#### Typical Memory Requirements

| Data Type | Size | CPU Memory | GPU Memory |
|-----------|------|------------|------------|
| Sample (1M pos) | Basic | 40 MB | 20 MB |
| Sample (10M pos) | Basic | 400 MB | 200 MB |
| Sample (28M pos) | Basic | 1.1 GB | 550 MB |
| Centroid (1M pos) | Extended | 60 MB | 30 MB |
| Centroid (10M pos) | Extended | 600 MB | 300 MB |
| Distance Matrix (100 samples) | - | 40 MB | 20 MB |

#### Memory Optimization Strategies

1. **Memory-mapped I/O**: Load data on-demand
2. **Chunked Processing**: Process in 1M position chunks
3. **GPU Memory Pooling**: Reuse GPU allocations
4. **Sparse Representation**: Only store observed positions
5. **Batch Processing**: Process samples in batches

---

## License

MethylUtils is licensed under the MIT License.

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

If you use MethylUtils in your research, please cite:

```bibtex
@software{methylutils2024,
  title={MethylUtils: High-Performance Computational Infrastructure for Methylation Data Analysis},
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
cd MethylPipeline/packages/methylutils

# Install in development mode
poetry install --with dev

# Run tests
poetry run pytest

# Run with GPU tests
poetry run pytest -m gpu

# Build documentation
cd docs
make html
```

---

*End of MethylUtils Comprehensive Documentation*

**Last Updated**: October 2024  
**Version**: 1.0.0

