# MethylCluster Comprehensive Documentation

## Overview

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

## Detailed Usage

### Configuration

MethylClusterConfig provides extensive options:

```python
config = MethylClusterConfig(
    samples=["path/to/sample1", "path/to/sample2"],
    chrom="1",
    ctx="CG",
    metric=ClusterMetric.HELLINGER,
    min_cluster_size=5,
    output_dir="results",
    use_gpu=True,
    cache_distance_matrix=True
)
```

### Running Clustering

```python
clusterer = MethylCluster(config)
results = clusterer.run()
```

Results include:

- n_clusters
- n_noise
- cluster_assignments
- labels
- sample_paths

### Centroid-Based Clustering

For centroid method:

```python
config = MethylClusterConfig(
    # ... other params
    clustering_method=ClusteringMethod.CENTROID,
    force_k=3  # Optional
)
```

## Architecture

### Core Components

- **MethylCluster**: Main clustering class
- **DistanceMatrixComputer**: Computes pairwise distances
- **ClusterVisualizer**: Generates plots

### Data Flow

1. Load MethylSample from HDF5
2. Compute distances
3. Cluster with HDBSCAN
4. Save results and visualizations

## Advanced Topics

### Custom Metrics

Extend ClusterMetric enum for new metrics.

### GPU Acceleration

Automatically uses GPU if available via MethylUtils.

## Troubleshooting

- Ensure MethylUtils is installed
- Check GPU availability
- Verify HDF5 files format

