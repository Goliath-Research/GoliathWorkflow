MethylClusterDP - Dirichlet-Process Clustering for Homogeneous Centroids
========================================================================

Overview
--------
This module clusters methylation samples into homogeneous centroids using a Dirichlet-Process (DP) mixture with Beta/Beta-Binomial emissions. It builds on the functional centroid API in `methyl_utils.MethylSample` (`add_sample`, `remove_sample`, `create_centroid_from_samples`) and supports GPU acceleration when available.

Key Features
------------
- Collapsed-Gibbs sampler with functional centroid updates (no in-place mutation)
- Emissions:
  - Beta-Binomial for low coverage (n ≤ n_switch)
  - Beta PDF for high coverage (n > n_switch)
- Per-chromosome workflow (handled by your orchestration layer)
- Outputs:
  - Single CSV with columns: `sample_path, centroid_idx` (1-based)
  - One HDF5 file per centroid: `centroid-{idx}.h5`, idx starting at 1

CLI Usage
---------
```
python -m methyl_cluster.cli.main \
  --samples-file /path/to/samples.txt \
  --output-dir /path/to/output \
  --alpha-dp 1.0 --a0 1.0 --b0 1.0 \
  --n-switch 20 --max-sweeps 50 --seed 42
```

Where `samples.txt` contains one HDF5 sample path per line.

Programmatic Usage
------------------
```python
from pathlib import Path
from methyl_utils.methyl_sample import MethylSample
from methyl_cluster.methyl_cluster_dp import MethylClusterDP, DPConfig

paths = [Path("s1.h5"), Path("s2.h5"), Path("s3.h5")]
samples = [MethylSample.load_from_h5(p) for p in paths]

cfg = DPConfig(alpha_dp=1.0, a0=1.0, b0=1.0, n_switch=20, use_gpu=True, max_sweeps=50, seed=42)
dp = MethylClusterDP(cfg).fit(samples, init="random")

# Assignments (0-based in memory; export as 1-based)
assign = dp.predict(samples)
centroids = dp.centroids
```

Notes
-----
- Clustering is performed per chromosome; run the module for each chromosome/context set as needed.
- The DP concentration `alpha_dp` controls the propensity to create new clusters.
- The `n_switch` threshold controls when to treat observations as counts (Beta-Binomial) vs. proportions (Beta).

# MethylCluster

MethylCluster is a Python package for clustering methylation samples using HDBSCAN with precomputed distance matrices. It integrates with MethylUtils for GPU-accelerated distance computations.

## Installation

```bash
pip install -e packages/methylcluster
```

## Quick Start

```python
from methyl_cluster import MethylCluster, MethylClusterConfig, ClusterMetric
from methyl_utils.core.methyl_frame import MethylSample

# Load samples
samples = [MethylSample.load_from_h5(p) for p in paths]

# Configure and run
config = MethylClusterConfig(
    samples=paths,
    chrom="1",
    ctx="CG",
    metric=ClusterMetric.JENSEN_SHANNON,
    output_dir="results"
)

clusterer = MethylCluster(config)
results = clusterer.run()
```

## Features

- HDBSCAN clustering with precomputed distances
- GPU-accelerated distance metrics (Jensen-Shannon, Hellinger, etc.)
- Automatic caching of distance matrices
- Comprehensive visualizations (dendrogram, t-SNE, heatmap)

For full documentation, see [METHYLCLUSTER_COMPREHENSIVE_DOCUMENTATION.md](docs/METHYLCLUSTER_COMPREHENSIVE_DOCUMENTATION.md)
