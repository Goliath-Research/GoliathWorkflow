# MethylPipeline Environment Setup

## Overview

The `METHYLPIPELINE` environment variable provides a consistent way to locate resources across all projects in the MethylPipeline workspace, eliminating the need for relative path gymnastics or guessing module locations.

## Quick Start

```bash
# Navigate to MethylPipeline root
cd /home/ubuntu/MethylPipeline

# Set up environment (run this in every new shell session)
source setup_env.sh
```

## What Gets Set Up

When you source `setup_env.sh`, the following happens:

1. **METHYLPIPELINE** - Points to the workspace root: `/home/ubuntu/MethylPipeline`
2. **PYTHONPATH** - Adds all package directories so they can be imported directly:
   - `${METHYLPIPELINE}/packages/methylutils`
   - `${METHYLPIPELINE}/packages/methylcentroid`

## Using METHYLPIPELINE in Your Code

### Option 1: Direct Environment Variable

```python
import os
from pathlib import Path

# Get the workspace root
methylpipeline_root = Path(os.environ['METHYLPIPELINE'])

# Access any project
methylutils_path = methylpipeline_root / "packages" / "methylutils"
methylcentroid_path = methylpipeline_root / "packages" / "methylcentroid"

# Access configs
config_path = methylpipeline_root / "packages" / "methylcentroid" / "configs" / "my_config.json"
```

### Option 2: Using path_utils Helper (Recommended)

```python
from methyl_centroid.path_utils import (
    get_methylpipeline_root,
    get_project_path,
    get_config_path,
    get_examples_path,
    get_data_path
)

# Get workspace root
root = get_methylpipeline_root()  # /home/ubuntu/MethylPipeline

# Get project paths
methylutils = get_project_path("methylutils")
methylcentroid = get_project_path("methylcentroid")

# Get config file
config = get_config_path("methylcentroid", "pb-cancer_batch_config.json")

# Get examples directory
examples = get_examples_path("methylcentroid")

# Get data directory
data = get_data_path("centroids/batch1")
```

## Project Structure

```
$METHYLPIPELINE/
├── setup_env.sh              # Environment setup script
├── packages/
│   ├── methylutils/          # MethylUtils package
│   │   └── methyl_utils/
│   └── methylcentroid/       # MethylCentroid package
│       └── methyl_centroid/
│           ├── configs/      # Configuration files
│           ├── examples/     # Example scripts
│           └── path_utils.py # Path utilities
├── data/                     # Shared data directory
└── docs/                     # Shared documentation
```

## Examples

### Running Example Scripts

All example scripts now use the METHYLPIPELINE environment variable:

```bash
# Set up environment first
source setup_env.sh

# Run examples
python packages/methylcentroid/methyl_centroid/examples/validate_config.py
python packages/methylcentroid/methyl_centroid/examples/example_metadata_access.py --demo
python packages/methylcentroid/methyl_centroid/examples/test_metadata.py /path/to/centroid.h5
```

### Writing New Scripts

When writing new scripts that need to locate MethylPipeline resources:

```python
#!/usr/bin/env python3
"""
My script that uses MethylPipeline resources.
"""

import os
import sys
from pathlib import Path

# Check environment
if 'METHYLPIPELINE' not in os.environ:
    print("Error: METHYLPIPELINE not set. Run: source setup_env.sh")
    sys.exit(1)

# Use the environment variable
from methyl_centroid.path_utils import get_config_path

config_file = get_config_path("methylcentroid", "my_config.json")
print(f"Loading config from: {config_file}")
```

## Benefits

✅ **No Path Guessing** - Always know where resources are  
✅ **Cross-Project** - Easy to reference resources across packages  
✅ **Portable** - Works regardless of installation location  
✅ **Clean Code** - No complex relative path calculations  
✅ **Consistent** - Same pattern across all projects  
✅ **Easy Testing** - Scripts can be run from any directory  

## Troubleshooting

### "METHYLPIPELINE not set" Error

```bash
# Make sure you sourced the script (not just executed it)
source setup_env.sh

# Verify it's set
echo $METHYLPIPELINE
```

### Need to Set Up Automatically?

Add to your `~/.bashrc` or `~/.bash_profile`:

```bash
# MethylPipeline environment
if [ -f ~/MethylPipeline/setup_env.sh ]; then
    source ~/MethylPipeline/setup_env.sh
fi
```

### Check Environment Status

```bash
# Quick check
echo $METHYLPIPELINE

# Detailed check
python -c "from methyl_centroid.path_utils import print_methylpipeline_info; print_methylpipeline_info()"
```

## For Developers

When creating new packages within MethylPipeline:

1. Add your package to `packages/`
2. Update `setup_env.sh` to include your package in PYTHONPATH
3. Use `path_utils` or `METHYLPIPELINE` env var to locate resources
4. Place examples in `packages/yourpackage/yourpackage/examples/`
5. Place configs in `packages/yourpackage/yourpackage/configs/`

## Summary

The `METHYLPIPELINE` environment variable creates a **single source of truth** for locating all workspace resources, making the codebase cleaner, more maintainable, and less error-prone.

## Host Conda Setup (CUDA 13.0 + RAPIDS 25.10)

For NVIDIA DGX Spark (CUDA 13.0), use the provided host setup script:

```bash
./scripts/setup_host_conda.sh
conda activate rapids-25.10
```

Then install packages without dependency resolution (use the conda env):

```bash
pip install -e packages/methylutils --no-deps
pip install -e packages/methylcentroid --no-deps
pip install -e packages/methyldetector --no-deps
pip install -e packages/methylmapper --no-deps
pip install -e packages/methylclassifier --no-deps
pip install -e packages/methylenricher --no-deps
pip install -e packages/methylcluster --no-deps
```

### Poetry + Conda (Recommended Behavior)

- Keep conda as the source of truth for dependencies.
- Avoid `poetry install` inside an active conda environment.
- If you do use Poetry, leave virtualenv creation enabled so it does not touch conda:

```bash
poetry config virtualenvs.create true
```

If you want a requirements file without installing, you can export:

```bash
poetry export -f requirements.txt -o requirements.txt --without-hashes
```

