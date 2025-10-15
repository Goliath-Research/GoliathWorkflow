# MethylCluster

HDBSCAN clustering for methylation samples with GPU-accelerated distance metrics.

## Overview

MethylCluster performs unsupervised clustering of methylation samples using HDBSCAN with precomputed distance matrices. It leverages GPU-accelerated distance metrics from MethylUtils (Jensen-Shannon and Hellinger distances) to efficiently cluster samples based on their methylation patterns.

## Features

- **GPU-Accelerated**: Uses MethylUtils GPU-accelerated distance metrics for fast computation
- **Multiple Metrics**: Supports Jensen-Shannon and Hellinger distance metrics
- **Distance Matrix Caching**: Cache computed distance matrices for reuse
- **Rich Visualizations**: Generate heatmaps, cluster trees, and MDS projections
- **Flexible Configuration**: JSON-based configuration for reproducible analyses
- **Container-Ready**: Designed to run in the methylpipeline Docker container

## Installation

### In Container

```bash
# Inside the methylpipeline container
cd /workspace/packages/methylcluster
pip install -e .
```

### Local Installation

```bash
cd /home/ubuntu/MethylPipeline/packages/methylcluster
pip install -e .
```

## Usage

### Command Line

```bash
# Using wrapper script (recommended)
./mc_cluster --config config.json --verbose

# Or directly
python -m methylcluster.cli --config config.json
```

### Python API

```python
from methylcluster import MethylCluster, MethylClusterConfig

# Load configuration
config = MethylClusterConfig.from_file("config.json")

# Run clustering
cluster = MethylCluster(config)
results = cluster.run()

# Access results
print(f"Found {results['n_clusters']} clusters")
print(f"Cluster assignments: {results['cluster_assignments']}")
```

## Configuration

Example configuration file:

```json
{
  "samples": [
    "/home/ubuntu/Work/samples/sample1",
    "/home/ubuntu/Work/samples/sample2",
    "/home/ubuntu/Work/samples/sample3"
  ],
  "chrom": "1",
  "ctx": "CG",
  "metric": "jensen_shannon",
  "min_cluster_size": 5,
  "min_samples": 5,
  "cluster_selection_epsilon": 0.0,
  "cluster_selection_method": "eom",
  "output_dir": "./clustering_results",
  "cache_distance_matrix": true,
  "use_gpu": true
}
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `samples` | List[str] | Required | Sample directory paths |
| `chrom` | str | Required | Chromosome identifier |
| `ctx` | str | Required | Context (CG, CHG, CHH) |
| `metric` | str | "jensen_shannon" | Distance metric |
| `min_cluster_size` | int | 5 | Minimum samples per cluster |
| `min_samples` | int | None | HDBSCAN min_samples (defaults to min_cluster_size) |
| `cluster_selection_epsilon` | float | 0.0 | Distance threshold for merging |
| `cluster_selection_method` | str | "eom" | Selection method (eom or leaf) |
| `output_dir` | str | Required | Output directory |
| `cache_distance_matrix` | bool | true | Cache distance matrix |
| `use_gpu` | bool | true | Use GPU acceleration |

## Output

MethylCluster generates:

1. **cluster_results.json**: Cluster assignments and statistics
2. **distance_matrix.npz**: Cached distance matrix (optional)
3. **distance_heatmap.html**: Interactive distance matrix heatmap
4. **cluster_tree.png**: HDBSCAN condensed tree plot
5. **mds_projection.html**: Interactive MDS projection colored by cluster
6. **cluster_statistics.html**: Cluster size bar chart

## Distance Metrics

### Jensen-Shannon Distance
- Symmetric, bounded [0,1] 
- Square root of Jensen-Shannon divergence
- Good for comparing probability distributions

### Hellinger Distance
- Symmetric, bounded [0,1]
- Measures similarity between probability distributions
- Robust to outliers

Both metrics are computed using Beta distribution parameters derived from mC/uC counts.

## Examples

See `examples/` directory for:
- `example_config.json`: Sample configuration file
- `clustering_example.py`: Python API usage example

## Requirements

- Python >= 3.10
- numpy >= 1.21.0
- scipy >= 1.7.0
- h5py >= 3.7.0
- hdbscan >= 0.8.33
- scikit-learn >= 1.0.0
- plotly >= 5.0.0
- matplotlib >= 3.5.0
- pydantic >= 2.0.0
- MethylUtils package

## License

MIT License - see LICENSE file for details.

## Citation

If you use MethylCluster in your research, please cite:

```bibtex
@software{methylcluster,
  title = {MethylCluster: HDBSCAN Clustering for Methylation Samples},
  author = {David Izada Rodriguez},
  year = {2024},
  url = {https://github.com/epimethyl/MethylPipeline}
}
```

## Support

For issues and questions:
- GitHub Issues: https://github.com/epimethyl/MethylPipeline/issues
- Email: dizada@epimethyl.com

