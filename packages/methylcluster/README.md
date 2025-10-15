# MethylCluster

## Overview

HDBSCAN clustering for methylation samples with GPU-accelerated distance metrics.

## Features

- GPU-Accelerated: Uses MethylUtils GPU-accelerated distance metrics for fast computation
- Multiple Metrics: Supports Jensen-Shannon and Hellinger distance metrics
- Distance Matrix Caching: Cache computed distance matrices for reuse
- Rich Visualizations: Generate heatmaps, cluster trees, and MDS projections
- Flexible Configuration: JSON-based configuration for reproducible analyses
- Container-Ready: Designed to run in the methylpipeline Docker container

## Installation

```bash
poetry install
```

## Usage

### Command Line

```bash
python -m methylcluster.cli --config config.json
```

### Python API

```python
from methylcluster import MethylCluster, MethylClusterConfig

config = MethylClusterConfig.from_file("config.json")
cluster = MethylCluster(config)
results = cluster.run()
```

## Configuration

See example config.json in the original content.

## Output

cluster_results.json, distance_matrix.npz, visualizations (HTML/PNG).

## Integration

Use for clustering samples in MethylPipeline workflow.

## Troubleshooting

- GPU issues: Check MethylUtils configuration
- Memory errors: Reduce sample count or use CPU

## License

MIT License - see LICENSE file for details.

