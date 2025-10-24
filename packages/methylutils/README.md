# MethylUtils

**Core utility library for the MethylPipeline ecosystem**

## Overview

MethylUtils is the foundational library providing shared utilities, GPU acceleration, statistical functions, and core data structures for all MethylPipeline packages. It implements high-performance distance metrics, Beta distribution analytics, memory management, and the core classification engine.

### What is MethylUtils?

MethylUtils serves as the backbone of MethylPipeline, offering:

- **Core Data Structures**: `MethylSample`, `PositionAligner`, `MethylCentroidPair`
- **Statistical Engine**: 7 distance metrics, FDR correction (Storey's q-value), Beta analytics
- **GPU Acceleration**: Automatic detection, 20-50x speedup with NVIDIA GPUs
- **Memory Management**: LRU caching, memory-mapped I/O, chunked processing
- **Classification Core**: `ProbabilisticBetaClassifier` for Bayesian classification

## Key Features

- ✨ **Automatic GPU Acceleration**: Seamless CuPy integration with CPU fallback
- 📊 **7 Distance Metrics**: Jensen-Shannon, Hellinger, Wasserstein, Jeffreys, Bhattacharyya, KL, Weighted JS
- 🧮 **Statistical Rigor**: Storey's q-value FDR correction, Beta distribution analytics
- 🏗️ **Factory Pattern**: Extensible metric computation system
- 💾 **Memory Efficient**: LRU caching, memory-mapped HDF5, intelligent chunking
- 🔬 **Type Safe**: Full type hints, Pydantic validation
- 🎯 **Modular Design**: Clean separation across focused modules

## Installation

```bash
# Install with GPU support (recommended)
pip install -e ".[gpu]"

# Basic installation (CPU-only)
pip install -e .
```

## Quick Start

### Basic Distance Computation

```python
import numpy as np
from methyl_utils import auto_compute_distance

# Beta distribution parameters for two methylation samples
alpha1 = np.array([2.0, 5.0, 3.0])
beta1 = np.array([3.0, 2.0, 4.0])
alpha2 = np.array([4.0, 3.0, 2.0])
beta2 = np.array([2.0, 4.0, 5.0])

# Compute Jensen-Shannon distance (automatically uses GPU if available)
distance = auto_compute_distance(alpha1, beta1, alpha2, beta2, metric="jensen_shannon")
print(f"Jensen-Shannon Distance: {distance:.4f}")
```

### Working with MethylSample

```python
from methyl_utils import MethylSample

# Load sample from HDF5
sample = MethylSample.load_from_h5('/data/sample1/chr1-CG.h5')

print(f"Sample has {len(sample.pos)} positions")
print(f"Chromosome: {sample.chrom}, Context: {sample.ctx}")

# Access methylation data
positions = sample.pos  # Genomic positions
x_values = sample.x    # Methylation levels
n_values = sample.N    # Coverage
```

### Comparing Two Centroids

```python
from methyl_utils import MethylCentroidPair

# Compare two centroids statistically
pair = MethylCentroidPair(
    centroid1_path='/centroids/healthy.h5',
    centroid2_path='/centroids/cancer.h5',
    fdr_threshold=0.01,
    use_gpu=True
)

# Detect differentially methylated positions
dmps = pair.detect_dmps()
print(f"Found {len(dmps)} DMPs with FDR < 0.01")
```

### GPU Acceleration

```python
from methyl_utils import is_gpu_available, cleanup_gpu_memory

if is_gpu_available():
    print("GPU acceleration enabled!")
    # ... perform GPU-accelerated operations ...
    cleanup_gpu_memory()  # Clean up after intensive operations
else:
    print("Running on CPU")
```

### Bayesian Classification

```python
from methyl_utils import ProbabilisticBetaClassifier

# Create classifier with Beta parameters for each class
classifier = ProbabilisticBetaClassifier(
    positions=[100, 200, 300],
    alpha_class1=[5.0, 10.0, 3.0],
    beta_class1=[2.0, 1.0, 4.0],
    alpha_class2=[2.0, 3.0, 8.0],
    beta_class2=[5.0, 4.0, 1.0],
    class1_name='Healthy',
    class2_name='Cancer'
)

# Classify a sample
sample = MethylSample.load_from_h5('/data/test_sample/chr1-CG.h5')
result = classifier.predict(sample)

print(f"Predicted: {result['predicted_class']}")
print(f"Probabilities: {result['posterior_probs']}")
```

## Core Components

### 1. Data Structures

- **`MethylSample`**: Methylation data representation with HDF5 I/O
- **`PositionAligner`**: Aligns samples to common genomic positions
- **`MethylCentroidPair`**: Statistical comparison of two centroids with FDR correction

### 2. Distance Metrics

| Metric | Use Case | Properties |
|--------|----------|------------|
| Jensen-Shannon | General purpose (default) | Bounded [0, log2], symmetric |
| Hellinger | Geometric distance | Proper metric, bounded [0, 1] |
| Wasserstein | Distribution topology | Optimal transport |
| Jeffreys | Symmetric divergence | Unbounded |
| Bhattacharyya | Distribution overlap | Bounded [0, 1] |
| KL Divergence | Information theory | Asymmetric, unbounded |
| Weighted JS | Entropy-weighted | Downweights uncertain positions |

### 3. Statistical Functions

- **FDR Correction**: Storey's q-value method (recommended for genomics)
- **Beta Analytics**: Parameter estimation, likelihood ratios, confidence intervals
- **Effect Sizes**: Delta mean, Cohen's d, Bhattacharyya coefficient

### 4. GPU Utilities

- Automatic GPU detection and initialization
- Seamless CPU/GPU array conversion
- Memory management and cleanup
- Performance profiling

### 5. Classification

- **`ProbabilisticBetaClassifier`**: Bayesian classification with exact Beta likelihoods
- Equal priors (0.5, 0.5) for unbiased predictions
- Log-likelihood ratio computation
- Posterior probability calculation

## Documentation

📚 **[Comprehensive Documentation](docs/METHYLUTILS_COMPREHENSIVE_DOCUMENTATION.md)** - Complete guide covering:
- Mathematical theory and algorithms
- Detailed API reference for all modules
- Advanced features (GPU acceleration, memory management, performance)
- Usage examples and best practices
- Integration with other MethylPipeline packages

## Architecture

MethylUtils is organized into focused modules:

```
methyl_utils/
├── Core Analysis
│   ├── metrics_core.py          # Distance metric implementations
│   ├── metrics_factory.py       # Factory pattern for metrics
│   ├── statistical_tests.py     # FDR correction, hypothesis testing
│   └── genomic_utils.py         # Genomic coordinate utilities
├── Performance
│   ├── memory_manager.py        # LRU caching, memory management
│   ├── chunked_processor.py     # Chunked processing for large datasets
│   └── performance_profiler.py  # Performance monitoring
├── Infrastructure
│   ├── gpu_detection.py         # GPU availability detection
│   ├── gpu_utils.py             # GPU array management
│   ├── logging_utils.py         # Consistent logging
│   └── metric_validations.py   # Input validation
├── Integrated Components
│   ├── methyl_sample.py         # MethylSample data structure
│   ├── position_aligner.py      # Position alignment
│   ├── methyl_centroid_pair.py  # Centroid comparison
│   └── probabilistic_beta_classifier.py  # Bayesian classifier
└── beta_analytics.py            # Beta distribution functions
```

## Integration with MethylPipeline

MethylUtils is used by **all** MethylPipeline packages:

- **MethylCentroid**: Uses `PositionAligner`, distance metrics, GPU utilities
- **MethylCluster**: Uses distance metrics, `MethylSample`, GPU acceleration
- **MethylDetector**: Uses `MethylCentroidPair`, FDR correction, `ProbabilisticBetaClassifier`
- **MethylTrainer**: Uses `MethylCentroidPair`, `ProbabilisticBetaClassifier`
- **MethylClassifier**: Uses `ProbabilisticBetaClassifier` for predictions

## Performance

### GPU Acceleration Benchmarks

| Operation | CPU Time | GPU Time | Speedup |
|-----------|----------|----------|---------|
| Jensen-Shannon (1M positions) | 5.2s | 0.15s | 35x |
| Hellinger (1M positions) | 4.8s | 0.12s | 40x |
| Wasserstein (1M positions) | 12.5s | 0.6s | 21x |
| FDR Correction (100K tests) | 2.1s | 0.1s | 21x |

### Memory Efficiency

- LRU caching reduces redundant computations
- Memory-mapped HDF5 for large files
- Chunked processing prevents memory overflow
- GPU memory management prevents leaks

## Examples

### Example 1: Compute All Distance Metrics

```python
from methyl_utils import auto_compute_distance
import numpy as np

alpha1, beta1 = np.array([5.0, 10.0]), np.array([2.0, 1.0])
alpha2, beta2 = np.array([2.0, 3.0]), np.array([5.0, 4.0])

metrics = ['jensen_shannon', 'hellinger', 'wasserstein', 'jeffreys', 'bhattacharyya']

for metric in metrics:
    distance = auto_compute_distance(alpha1, beta1, alpha2, beta2, metric=metric)
    print(f"{metric:20s}: {distance:.6f}")
```

### Example 2: Position Alignment

```python
from methyl_utils import PositionAligner, MethylSample

# Create aligner
aligner = PositionAligner(max_samples=100, use_gpu=False)
aligner.set_min_coverage(4)

# Add samples
sample1 = MethylSample.load_from_h5('/data/sample1/chr1-CG.h5')
sample2 = MethylSample.load_from_h5('/data/sample2/chr1-CG.h5')

aligner.add_sample(sample1, sample_id=0)
aligner.add_sample(sample2, sample_id=1)

# Get aligned centroid
centroid = aligner.get_centroid()
print(f"Aligned centroid has {len(centroid.pos)} positions")
```

### Example 3: FDR Correction with Storey's Method

```python
from methyl_utils.methyl_centroid_pair import MethylCentroidPair

# Create centroid pair
pair = MethylCentroidPair(
    centroid1_path='/centroids/healthy.h5',
    centroid2_path='/centroids/cancer.h5',
    fdr_threshold=0.01,
    use_gpu=True
)

# Detect DMPs with Storey's q-value FDR correction
dmps = pair.detect_dmps()

# Access q-values
for pos, qval in zip(dmps['pos'][:10], dmps['fdr_qvalue'][:10]):
    print(f"Position {pos}: q-value = {qval:.6f}")
```

## Troubleshooting

### GPU Not Detected

**Problem**: GPU not being used despite being available

**Solutions**:
```bash
# Check CUDA installation
nvidia-smi

# Install CuPy for your CUDA version
pip install cupy-cuda11x  # For CUDA 11.x

# Verify GPU detection
python -c "from methyl_utils import is_gpu_available; print(is_gpu_available())"
```

### Memory Issues

**Problem**: Out of memory errors

**Solutions**:
```python
# Clean up GPU memory
from methyl_utils import cleanup_gpu_memory
cleanup_gpu_memory()

# Use chunked processing
from methyl_utils import ChunkedProcessor
processor = ChunkedProcessor(chunk_size=10000)

# Disable GPU if needed
use_gpu = False
```

### Import Errors

**Problem**: Cannot import MethylUtils

**Solutions**:
```bash
# Ensure package is installed
pip list | grep methyl

# Install in development mode
cd packages/methylutils
pip install -e .

# Check Python path
python -c "import sys; print('\n'.join(sys.path))"
```

## API Reference

### Core Functions

```python
# Distance computation
auto_compute_distance(a1, b1, a2, b2, metric, use_gpu=True) -> float

# GPU utilities
is_gpu_available() -> bool
cleanup_gpu_memory() -> None

# Beta analytics
estimate_beta_params(x, N) -> Tuple[np.ndarray, np.ndarray]
beta_log_pdf(x, alpha, beta) -> np.ndarray
```

### Classes

- `MethylSample`: Methylation data representation
- `PositionAligner`: Position alignment for multiple samples
- `MethylCentroidPair`: Statistical comparison with FDR
- `ProbabilisticBetaClassifier`: Bayesian classification
- `MetricsFactory`: Factory for distance metric computation

See [Comprehensive Documentation](docs/METHYLUTILS_COMPREHENSIVE_DOCUMENTATION.md) for complete API details.

## Contributing

MethylUtils is the core library - changes here affect all packages. Please ensure:

1. All tests pass: `pytest tests/`
2. Type checking: `mypy methyl_utils/`
3. Code formatting: `black methyl_utils/`
4. Documentation updated

## License

MIT License - see [LICENSE](../../LICENSE) file for details.

## Citation

```bibtex
@software{methylutils2024,
  title={MethylUtils: Core Utilities for Methylation Analysis},
  author={MethylPipeline Contributors},
  year={2024},
  url={https://github.com/yourusername/MethylPipeline}
}
```

---

For more information, see the [MethylPipeline Documentation](../../docs/METHYLPIPELINE_COMPREHENSIVE_DOCUMENTATION.md).
