# MethylCentroid

## Overview

A high-performance Python package for calculating methylation centroids from genomic data with GPU acceleration support, advanced outlier detection algorithms, and modular SOLID principles-based architecture.

## Features

- Modular Architecture: Clean, SOLID principles-based design with focused modules
- High-Performance Processing: Optimized for large genomic datasets with parallel processing
- GPU Acceleration: Automatic NVIDIA GPU detection and acceleration (10-50x speedup)
- Advanced Outlier Detection: Multiple algorithms including probabilistic Beta classification for ≥20 samples
- Incremental Operations: Add/remove samples from existing centroids without full recalculation
- Flexible Input: Support for multiple chromosome/context combinations (CG, CHG, CHH)
- MethylUtils Integration: Leverages shared utilities for logging, performance profiling, and GPU management
- Memory Optimization: Intelligent caching, dynamic chunking, and memory-aware processing
- Command-Line Interface: Easy-to-use CLI for batch processing

## Installation

```bash
poetry install
```

## Usage

### Command Line

```bash
python -m methylcentroid.centroid_cli --config config.json
```

### Python API

```python
from methylcentroid.methyl_centroid import MethylCentroid

mc = MethylCentroid(
    add_samples=["path/to/sample1", "path/to/sample2"],
    chrom="1",
    ctx="CG",
    output_dir="output",
    min_coverage=4
)

results = mc.build_centroid()
```

## Configuration

See example config.json in the original content.

## Output

Centroids saved as HDF5 files with positions, mC, uC, etc.

## Integration

Used in MethylPipeline for generating centroids before DMP detection in MethylDetector.

## Troubleshooting

- Container not running: docker start epimethyl
- GPU issues: Check MethylUtils GPU detection

## License

This project is licensed under the MIT License - see the LICENSE file for details.