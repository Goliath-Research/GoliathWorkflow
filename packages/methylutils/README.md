# MethylUtils

## Overview

A comprehensive Python package for statistical analysis of methylation data with GPU acceleration support. It provides high-performance implementations of various statistical distance metrics for Beta distributions commonly used in methylation analysis.

## Features

- Automatic GPU Acceleration: Optimized for NVIDIA GH200 with 96GB memory
- Factory Pattern Architecture: Extensible metric computation system
- Memory Efficient: In-place operations and optimized memory usage
- Type Safe: Full type hints and comprehensive validation
- Modular Design: Clean separation of concerns across focused modules

## Installation

Install with GPU support (recommended):

```bash
poetry install --with gpu
```

Basic installation:

```bash
poetry install
```

## Usage

### Command Line

```bash
methylutils --help
```

### Python API

```python
import numpy as np
from methyl_utils import auto_compute_distance

# Sample Beta distribution parameters
a1, b1 = np.array([2.0, 5.0]), np.array([3.0, 2.0])
a2, b2 = np.array([4.0, 3.0]), np.array([2.0, 4.0])

# Compute Jensen-Shannon distance
result = auto_compute_distance(a1, b1, a2, b2, metric="jensen_shannon")
print(f"JSD: {result}")
```

See more examples in the original content.

## Configuration

Configuration is handled via Python imports and function parameters.

## Output

Functions return numerical results or data structures like numpy arrays.

## Integration

MethylUtils is the core utility package used by all other packages in MethylPipeline for logging, GPU management, and statistical computations.

## Troubleshooting

- GPU not detected: Ensure CuPy is installed and GPU drivers are up to date.
- Import errors: Check if all dependencies are installed via Poetry.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.