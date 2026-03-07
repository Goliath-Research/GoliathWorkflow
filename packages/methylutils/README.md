# MethylUtils

MethylUtils is a Python package for methylation data analysis, providing efficient data structures and statistical methods for genomic methylation analysis.

## Key Features

- Efficient MethylSample class for samples and centroids; `close()` for memory cleanup
- GPU-accelerated distance metrics
- Statistical tests; centroid comparison uses ECDF only
- Centroid HDF5: `methylation_data` only (optional `bins` attr + `bin_counts` dataset)
- Centroid comparison and DMP detection; Bayesian classification (Beta/BMM, multi-class)
- **CLIs**: `methyl-utils`, `chrom-mapping`, `methyl-utils-deploy`

## Installation

```bash
pip install -e packages/methylutils
```

## Quick Start

```python
from methyl_utils.core.methyl_frame import MethylSample, MethylCentroid

# Create sample
sample = MethylSample(
    pos=np.array([100, 200]),
    mC=np.array([10, 20]),
    uC=np.array([5, 15]),
    tnc=np.array([1, 2])
)

# Create centroid (single type: pos, tnc, N, Sx, Sx2, Sm, Su, Sc2, Swx2 + binned_stats)
centroid = MethylCentroid.from_centroid_data({
    "pos": np.array([100, 200], dtype=np.uint32),
    "tnc": np.array([1, 2], dtype=np.uint8),
    "N": np.array([5, 5], dtype=np.uint32),
    "Sx": np.array([2.5, 5.0], dtype=np.float32),
    "Sx2": np.array([1.25, 5.0], dtype=np.float32),
    "Sm": np.array([50, 100], dtype=np.uint32),
    "Su": np.array([25, 75], dtype=np.uint32),
    "Sc2": np.array([5625, 30625], dtype=np.uint32),
    "Swx2": np.array([1.25, 5.0], dtype=np.float32),
})
# Properties: centroid.mean, centroid.variance (unweighted); centroid.weighted_mean, centroid.weighted_variance; centroid.coverage (Sm+Su)
# Add sample to centroid
updated_centroid = centroid.add_sample(sample)
```

## Documentation

- **[Usage Guide (Docker and venv)](docs/USAGE.md)** — Setup with Docker or a local virtual environment; install order for dependent packages.
- [Theoretical Foundation](docs/MethylUtils_Theoretical_Foundation.md) — Role of MethylUtils, project config, sample/centroid model, Beta and metrics.
- [Implementation](docs/METHYLUTILS_IMPLEMENTATION.md) — Package layout and how downstream packages use MethylUtils.
- [Comprehensive Documentation](docs/METHYLUTILS_COMPREHENSIVE_DOCUMENTATION.md) — Full math, distance formulas, data structures, and API details.
