# MethylPipeline Workspace

Multi-project workspace for methylation analysis tools.

## Quick Start

```bash
# Set up environment (required for all operations)
source setup_env.sh

# Verify setup
python packages/methylcentroid/methyl_centroid/path_utils.py
```

See `ENV_SETUP.md` for complete documentation.

## Projects

- **methylutils** - Core methylation analysis utilities
- **methylcentroid** - Centroid calculation and outlier detection

## Documentation

- `ENV_SETUP.md` - Environment setup and METHYLPIPELINE variable
- `METADATA_UPDATES.md` - Recent metadata support additions

## Host Conda (CUDA 13.0)

For CUDA 13.0 systems (DGX Spark), use:

```bash
./scripts/setup_host_conda.sh
```

### Poetry + Conda

Use conda for dependencies and install packages with `pip -e ... --no-deps`.
If you use Poetry, keep its virtualenvs enabled so it does not modify the conda env.
