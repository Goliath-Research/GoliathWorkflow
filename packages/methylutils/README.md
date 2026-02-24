# MethylUtils

MethylUtils is a Python package for methylation data analysis, providing efficient data structures and statistical methods for genomic methylation analysis.

## Key Features

- Efficient MethylSample class for samples and centroids
- GPU-accelerated distance metrics
- Statistical tests for Beta distributions
- Centroid comparison and DMP detection
- Bayesian classification (Beta/BMM, multi-class)

## Installation

```bash
pip install -e packages/methylutils
```

## Quick Start

```python
from methyl_utils.core.methyl_frame import MethylSample, MethylExtendedCentroid

# Create sample
sample = MethylSample(
    pos=np.array([100, 200]),
    mC=np.array([10, 20]),
    uC=np.array([5, 15]),
    tnc=np.array([1, 2])
)

# Create centroid
centroid = MethylExtendedCentroid.from_sample_data(
    pos=np.array([100, 200]),
    mC=np.array([50, 100]),
    uC=np.array([25, 75]),
    tnc=np.array([1, 2]),
    N=np.array([5, 5]),
    Sx=np.array([2.5, 5.0]),
    Sx2=np.array([1.25, 5.0]),
    log_x_sum=np.array([0.5, 1.0]),
    log_1_minus_x_sum=np.array([-0.5, -1.0])
)

# Add sample to centroid
updated_centroid = centroid.add_sample(sample)
```

## Documentation

- **[Usage Guide (Docker and venv)](docs/USAGE.md)** — Setup with Docker or a local virtual environment; install order for dependent packages.
- [Theoretical Foundation](docs/MethylUtils_Theoretical_Foundation.md) — Role of MethylUtils, project config, sample/centroid model, Beta and metrics.
- [Implementation](docs/METHYLUTILS_IMPLEMENTATION.md) — Package layout and how downstream packages use MethylUtils.
- [Comprehensive Documentation](docs/METHYLUTILS_COMPREHENSIVE_DOCUMENTATION.md) — Full math, distance formulas, data structures, and API details.
