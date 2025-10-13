# Methyl Utils Installation Guide

## Installation Options

### Option 1: Install in Development Mode (Recommended)

```bash
# From the methyl_utils directory
cd /path/to/methyl_utils
pip install -e .

# Or from any location
pip install -e /path/to/methyl_utils
```

### Option 2: Install from Shared Location

```bash
# If methyl_utils is in a shared location accessible by all applications
pip install -e /workspace/shared_packages/methyl_utils
```

### Option 3: Add to PYTHONPATH

```bash
# Add to your environment or container
export PYTHONPATH="/path/to/methyl_utils:$PYTHONPATH"

# Or add to each application's environment
export PYTHONPATH="/workspace/shared_packages/methyl_utils:$PYTHONPATH"
```

## Usage in Applications

Once installed, use in any methyl-related application:

```python
# GPU detection
from methyl_utils.gpu_detection import is_gpu_available, print_gpu_status, get_cupy

# Logging utilities
from methyl_utils.logging_utils import setup_logging, get_logger

# Check GPU status
print_gpu_status()

# Setup logging
setup_logging(verbose=True)
```

## Dependencies

### Required
- Python >= 3.8
- numpy >= 1.20.0
- nvidia-ml-py >= 12.535.0

### Optional (for GPU support)
- cupy-cuda11x >= 10.0.0
- cudf-cu11 >= 22.0.0 (for RAPIDS support)

## Installation with GPU Support

```bash
# Install with GPU support
pip install -e .[gpu]

# Install with RAPIDS support
pip install -e .[rapids]
```

## Verification

```python
# Test installation
from methyl_utils.gpu_detection import print_gpu_status
print_gpu_status()
```
