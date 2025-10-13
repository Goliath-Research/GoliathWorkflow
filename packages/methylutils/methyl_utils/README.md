# Methyl Utils

A shared utilities package for methyl-related applications including GPU detection, logging, and other common functionality used across MethylCentroid, MethylDetector, MethylCluster, and other applications.

## Features

- **NVIDIA GPU Detection**: Uses pynvml as the primary detection method (NVIDIA's official NVML Python bindings)
- **CuPy Integration**: Automatic CuPy availability detection and testing
- **RAPIDS Support**: Detection of cuDF and cupyx.scipy modules
- **Memory Management**: GPU memory monitoring and cleanup utilities
- **Performance Comparison**: CPU vs GPU implementation comparison tools
- **Consistent Logging**: Standardized logging across all applications

## Installation

### Basic Installation
```bash
pip install -e .
```

### With GPU Support
```bash
pip install -e .[gpu]
```

### With RAPIDS Support
```bash
pip install -e .[rapids]
```

## Quick Start

```python
from methyl_utils.gpu_detection import print_gpu_status, is_gpu_available, get_cupy
from methyl_utils.logging_utils import setup_logging

# Check GPU status
print_gpu_status()

# Use GPU if available
if is_gpu_available():
    cp = get_cupy()
    # Use CuPy for GPU operations
    gpu_array = cp.array([1, 2, 3, 4, 5])
else:
    import numpy as np
    # Fallback to NumPy
    cpu_array = np.array([1, 2, 3, 4, 5])

# Setup logging
setup_logging(verbose=True)
```

## API Reference

### GPU Detection

- `is_gpu_available()`: Check if GPU is available and functional
- `is_cupy_available()`: Check if CuPy can be imported
- `is_cudf_available()`: Check if cuDF is available
- `get_cupy()`: Get CuPy module if available
- `get_gpu_state()`: Get complete GPU state information
- `print_gpu_status()`: Print detailed GPU status

### Memory Management

- `cleanup_gpu_memory()`: Clean up GPU memory
- `get_memory_info()`: Get current GPU memory usage
- `get_gpu_memory_gb()`: Get total GPU memory in GB

### Utilities

- `create_gpu_array(array)`: Create GPU array if possible
- `to_cpu_array(array)`: Convert array to CPU
- `compare_implementations(cpu_func, gpu_func, *args, **kwargs)`: Compare CPU vs GPU performance

### Logging

- `setup_logging(verbose=False, log_file=None)`: Configure application logging
- `setup_module_logging(module_name, verbose=False)`: Setup module-level logging
- `get_logger(name, verbose=False)`: Get configured logger

## Usage in Applications

### MethylCentroid
```python
from methyl_utils.gpu_detection import is_gpu_available, get_cupy

class MethylCentroid:
    def __init__(self):
        self.gpu_available = is_gpu_available()
        self.cp = get_cupy() if self.gpu_available else None
```

### PositionAligner
```python
from methyl_utils.gpu_detection import is_gpu_available, get_cupy

class PositionAligner:
    def __init__(self, use_gpu=True):
        self.gpu_available = use_gpu and is_gpu_available()
        self.cp = get_cupy() if self.gpu_available else None
```

## Benefits

1. **Single Source of Truth**: One place to manage GPU detection logic
2. **Consistency**: Same GPU detection behavior across all applications
3. **Maintainability**: Easy to update GPU detection for all applications
4. **Testability**: Centralized testing of GPU functionality
5. **Reusability**: Can be used by future applications

## Requirements

- Python >= 3.8
- NumPy >= 1.20.0
- pynvml >= 11.0.0 (for NVIDIA GPU detection)

### Optional
- CuPy (for GPU operations)
- cuDF (for RAPIDS DataFrame operations)
- cupyx.scipy (for GPU-accelerated scientific computing)
