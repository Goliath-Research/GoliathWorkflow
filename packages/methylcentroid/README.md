# MethylCentroid

## Overview

**MethylCentroid** is a high-performance Python package for calculating representative methylation profiles (centroids) from genomic data. It provides robust outlier detection, GPU acceleration, and seamless integration with the MethylPipeline ecosystem for epigenetic research and clinical applications.

A **methylation centroid** represents the average methylation pattern across a group of samples, enabling:
- **Group Comparisons**: Compare healthy vs. disease cohorts
- **Quality Control**: Identify and remove aberrant samples
- **Downstream Analysis**: Generate centroids for DMP detection and classification

## Key Features

- **🔬 Robust Outlier Detection**: Three adaptive algorithms (Probabilistic Beta Classifier, Multi-Metric Consensus, Single-Metric) automatically selected based on sample size
- **⚡ GPU Acceleration**: 10-50x speedup for large datasets using NVIDIA GPUs with automatic CPU fallback
- **📊 Multi-Metric Consensus**: Combines 5 distance metrics (Jeffreys, Jensen-Shannon, Weighted JS, Hellinger, Wasserstein) for reliable outlier identification
- **🧠 Smart Memory Management**: LRU caching and intelligent memory allocation for large genomic datasets
- **🔄 Incremental Operations**: Add/remove samples without full recalculation
- **📦 MethylUtils Integration**: Leverages optimized computational infrastructure for distance calculations, GPU management, and performance profiling
- **🎯 Statistical Rigor**: Beta/Normal distribution modeling with AIC-based selection and proper variance estimation
- **⚙️ Modular Architecture**: Clean, SOLID principles-based design with focused, maintainable modules

## How It Works

### Mathematical Foundation

MethylCentroid uses **extended centroid calculation** for statistical accuracy:

For N samples at genomic position i:

```
Centroid_i = (1/N) × Σ(methylation_level_ij)
```

This approach:
1. **Accumulates methylation levels**: Σx and Σx² for each position
2. **Handles varying coverage**: Each sample contributes equally regardless of sequencing depth
3. **Enables variance estimation**: σ² = (Σx²/N) - (Σx/N)²

### Outlier Detection Strategy

MethylCentroid uses a **multi-metric consensus** approach:

**Step 1: Distance Calculation**
- Compute multiple information-theoretic distances between each sample and the centroid
- Available metrics: Jeffreys, Jensen-Shannon, Weighted JS, Hellinger, Wasserstein

**Step 2: Statistical Modeling**
- Fit Beta or Normal distribution to distance values (selected via AIC)
- Calculate p-values for each sample under the fitted distribution

**Step 3: Consensus Decision**
- Require agreement across multiple metrics (configurable threshold)
- Remove most significant outlier (lowest p-value < α)
- Recalculate centroid and iterate until convergence

**Adaptive Algorithm Selection**:
- **≥20 samples**: Probabilistic Beta Classifier (most rigorous)
- **5-19 samples**: Multi-Metric Consensus (robust)
- **3-4 samples**: Single-Metric Detection (simple, interpretable)

### Why Probabilistic Methods?

Unlike simple distance-based thresholding:
- **Statistically principled**: Uses proper hypothesis testing with p-values
- **Robust to sample size**: Adapts to dataset characteristics
- **Reduces false positives**: Multi-metric consensus prevents spurious detections
- **Quantifies uncertainty**: Provides confidence scores for outlier assignments

## Installation

```bash
# Using Poetry (recommended)
cd packages/methylcentroid
poetry install

# Or using pip
pip install -e .
```

### Optional Dependencies

- **GPU Support**: `pip install cupy-cuda11x` (replace 11x with your CUDA version)
- **Visualization**: `pip install plotly matplotlib`

## Usage

### Basic Example

```python
from methyl_centroid import MethylCentroid

# Create centroid from samples with automatic outlier detection
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids',
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

### Multi-Metric Consensus

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
    α=0.05,
    min_coverage=4
)

mc = MethylCentroid(**config.model_dump())
results = mc.build_centroid()
```

### Incremental Updates

```python
# Initial centroid creation
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='centroids',
    add_samples=['sample1', 'sample2', 'sample3']
)
initial_results = mc.build_centroid()

# Later: add new samples
mc_updated = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='centroids',
    samples=['sample1', 'sample2', 'sample3'],  # Current samples (after outlier removal)
    add_samples=['sample4', 'sample5'],  # New samples to add
    outliers=initial_results.outliers  # Re-include for fair evaluation
)
updated_results = mc_updated.build_centroid()
```

### Command Line Interface

```bash
# Using configuration file
python -m methylcentroid.centroid_cli --config config.json

# Direct parameters
python -m methylcentroid.centroid_cli \
    --chrom 1 \
    --ctx CG \
    --output-dir ./centroids \
    --samples sample1 sample2 sample3 \
    --min-coverage 4 \
    --alpha 0.05
```

## Configuration

### JSON Configuration Example

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
  "max_iterations": 10,
  "α": 0.05,
  "distance_metrics": ["jensen_shannon", "wasserstein"],
  "min_metrics_agree": 2
}
```

### Key Parameters

- **chrom**: Chromosome identifier (e.g., '1', 'X', 'MT')
- **ctx**: Methylation context ('CG', 'CHG', 'CHH')
- **min_coverage**: Minimum mC + uC for position inclusion (default: 4)
- **α (alpha)**: Significance level for outlier detection (default: 0.05)
- **distance_metrics**: List of metrics for outlier detection
- **min_metrics_agree**: Number of metrics that must agree (0 = use General Simes formula)
- **max_iterations**: Maximum outlier removal iterations (default: 10)

## Documentation

📚 **[Comprehensive Documentation](docs/METHYLCENTROID_COMPREHENSIVE_DOCUMENTATION.md)**

Detailed documentation covering:
- **Mathematical Theory**: Beta distributions, information-theoretic distances, statistical modeling
- **Algorithm Details**: Position alignment, centroid calculation, outlier detection methods
- **API Reference**: Complete class and method documentation
- **Advanced Features**: GPU acceleration, smart caching, batch processing
- **Usage Examples**: Common patterns and use cases
- **Troubleshooting**: Solutions to common issues
- **Performance**: Benchmarks and optimization strategies

## Output

### Centroid HDF5 File Structure

```
centroid.h5
├── methylation_data/
│   ├── pos          # uint32: Genomic positions
│   ├── mC           # uint32: Methylated cytosine counts (averaged)
│   ├── uC           # uint32: Unmethylated cytosine counts (averaged)
│   ├── tnc          # uint8: Trinucleotide context
│   ├── N            # uint32: Number of samples at each position
│   ├── Sx           # float32: Sum of methylation levels
│   └── Sx2          # float32: Sum of squared methylation levels
└── metadata (attributes)
    ├── laboratory
    ├── disease
    ├── group
    ├── batch
    ├── samples_used
    ├── outliers_removed
    └── statistics
```

### Outlier Removal Results

```python
class OutlierRemovalResults:
    iterations: List[OutlierIterationInfo]  # Details for each iteration
    final_centroid_path: str                 # Path to saved centroid
    total_samples_removed: int               # Count of outliers removed
```

## Model Training

Centroids created by MethylCentroid are used by **MethylModeler** for:

1. **DMP Detection**: Compare two centroids to find differentially methylated positions
2. **Classifier Training**: Use DMPs to train Bayesian classifiers
3. **Validation**: Assess classifier performance using centroid samples

**Example Pipeline**:

```python
from methyl_centroid import MethylCentroid
from methyl_modeler import MethylModeler

# Create centroids
centroid_healthy = MethylCentroid(..., group='Healthy').build_centroid()
centroid_cancer = MethylCentroid(..., group='Cancer').build_centroid()

# Detect DMPs and train classifier
detector = MethylModeler(
    centroid1_path=centroid_healthy.final_centroid_path,
    centroid2_path=centroid_cancer.final_centroid_path
)
dmp_results = detector.find_dmps()
```

## Advanced Features

### 1. GPU Acceleration

Automatic GPU detection and 10-50x speedup:

```python
from methyl_utils import is_gpu_available

if is_gpu_available():
    print("GPU acceleration enabled")
    # MethylCentroid automatically uses GPU
else:
    print("Using CPU fallback")
```

### 2. Smart Sample Caching

LRU cache with automatic memory management:

```python
from methyl_centroid.core import SmartSampleCache

cache = SmartSampleCache(max_memory_gb=50)
stats = cache.get_stats()
print(f"Cached samples: {stats['cached_samples']}")
print(f"Memory usage: {stats['memory_usage_mb']:.1f} MB")
```

### 3. Custom Distance Metrics

Extend with your own metrics:

```python
from methyl_utils import register_distance_metric

@register_distance_metric('custom_metric')
def custom_distance(sample_methylation, centroid_methylation, weights=None):
    diff = np.abs(sample_methylation - centroid_methylation)
    if weights is not None:
        diff *= weights
    return np.mean(diff)
```

### 4. Batch Processing

Process multiple chromosome/context combinations:

```python
chromosomes = [str(i) for i in range(1, 23)] + ['X', 'Y']
contexts = ['CG', 'CHG', 'CHH']

for chrom in chromosomes:
    for ctx in contexts:
        mc = MethylCentroid(chrom=chrom, ctx=ctx, ...)
        results = mc.build_centroid()
```

## Integration with MethylPipeline

MethylCentroid is a core component of the MethylPipeline workflow:

```
1. MethylCentroid
   ├─ Create centroids for Group A (e.g., Healthy)
   ├─ Create centroids for Group B (e.g., Cancer)
   └─ Remove outliers from both groups

2. MethylModeler
   ├─ Compare Centroid A vs Centroid B
   ├─ Identify DMPs (Differentially Methylated Positions)
   └─ Train Bayesian classifier on DMPs

3. MethylClassifier
   ├─ Load trained classifier
   ├─ Classify new samples
   └─ Report probabilities and predictions
```

## API Reference

### MethylCentroid Class

Main class for centroid calculation and outlier detection.

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
    max_iterations: int = 10,
    max_iterations_percentage: float = 0.1,
    α: float = 0.05,
    min_samples: int = 3,
    distance_metrics: List[DistanceMetric] = None,
    min_metrics_agree: int = 1,
    verbose: bool = True,
    laboratory: str = None,
    disease: str = None,
    group: str = None,
    batch: str = None
)
```

**Methods**:
- `build_centroid()`: Build centroid with automatic outlier detection
- `update_centroid()`: Incrementally update existing centroid
- `save_centroid()`: Save centroid to HDF5 file

### MethylCentroidConfig Class

Pydantic model for configuration validation.

```python
from methyl_centroid import MethylCentroidConfig

config = MethylCentroidConfig.from_file('config.json')
mc = MethylCentroid(**config.model_dump())
```

## Troubleshooting

### GPU Not Detected

```bash
# Check CUDA installation
nvidia-smi

# Install matching CuPy version
pip install cupy-cuda11x  # Replace with your CUDA version

# Verify GPU detection
python -c "from methyl_utils import is_gpu_available; print(is_gpu_available())"
```

### Out of Memory

```python
# Reduce cache size
mc = MethylCentroid(..., cache_size_gb=20)

# Increase minimum coverage (reduces positions)
mc = MethylCentroid(..., min_coverage=10)

# Process in smaller batches
```

### No Outliers Detected

```python
# Increase significance threshold
mc = MethylCentroid(..., α=0.10)

# Use single metric
mc = MethylCentroid(
    ...,
    distance_metrics=[DistanceMetric.JENSEN_SHANNON],
    min_metrics_agree=1
)
```

### Too Many Outliers

```python
# Decrease significance threshold
mc = MethylCentroid(..., α=0.01)

# Increase consensus requirement
mc = MethylCentroid(..., min_metrics_agree=3)

# Limit maximum removals
mc = MethylCentroid(..., max_iterations=3, max_iterations_percentage=0.10)
```

## Performance

### Benchmarks

| Dataset | Samples | Positions | CPU Time | GPU Time | Speedup |
|---------|---------|-----------|----------|----------|---------|
| Small | 5 | 1M | 17s | 1.2s | 14x |
| Medium | 25 | 10M | 165s | 10.5s | 16x |
| Large | 100 | 28M | 1320s | 80s | 17x |

### Memory Requirements

| Dataset | Samples | Positions | CPU Memory | GPU Memory |
|---------|---------|-----------|------------|------------|
| Small | 5 | 1M | 500 MB | 200 MB |
| Medium | 25 | 10M | 5 GB | 2 GB |
| Large | 100 | 28M | 40 GB | 12 GB |

## License

This project is licensed under the MIT License - see the LICENSE file for details.

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

## Support

- **Documentation**: [Comprehensive Guide](docs/METHYLCENTROID_COMPREHENSIVE_DOCUMENTATION.md)
- **Theoretical Foundation**: [MethylCentroid Theory](docs/MethylCentroid_Theoretical_Foundation.md)
- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions

## Contributing

Contributions are welcome! Please see the main MethylPipeline CONTRIBUTING.md for guidelines.