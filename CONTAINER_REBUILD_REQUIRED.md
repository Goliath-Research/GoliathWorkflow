# Container Rebuild Required

## Why?

The MethylPipeline packages have been standardized to use Python naming conventions with underscores (e.g., `methyl_detector`, `methyl_centroid`), and Poetry has been added to the Dockerfile for proper package management.

## Changes Made

1. **Package Naming**: All internal package folders now use underscores:
   - `methyl_utils` (was already correct)
   - `methyl_centroid` (renamed from `methylcentroid`)
   - `methyl_detector` (was already correct)
   - `methyl_classifier` (renamed from `methylclassifier`)
   - `methyl_cluster` (renamed from `methylcluster`)
   - `methyl_enricher` (renamed from `methylenricher`)
   - `methyl_mapper` (renamed from `methylmapper`)
   - `methyl_trainer` (renamed from `methyltrainer`)

2. **Poetry Added**: The Dockerfile now installs Poetry for proper dependency management

3. **Installation Script Updated**: `install_all.sh` now uses `poetry install` instead of `pip install`

## How to Rebuild

### Option 1: Rebuild the Container (Recommended)

```bash
# Stop the current container
cd /home/ubuntu/MethylPipeline/docker
docker compose down

# Rebuild with the updated Dockerfile
docker compose build

# Start the new container
docker compose up -d

# Verify it's running
docker ps | grep methylpipeline

# Install all packages
cd /home/ubuntu/MethylPipeline
./install.sh
```

### Option 2: Install Poetry in Running Container (Quick Fix)

If you don't want to rebuild right now:

```bash
# Install Poetry in the running container
docker exec methylpipeline bash -c "curl -sSL https://install.python-poetry.org | python3 - && ln -s /root/.local/bin/poetry /usr/local/bin/poetry && poetry config virtualenvs.create false"

# Then run the installation
cd /home/ubuntu/MethylPipeline
./install.sh
```

## After Installation

Test that the packages work:

```bash
# Test imports
docker exec methylpipeline python3 -c "from methyl_utils import get_logger; print('✓ MethylUtils OK')"
docker exec methylpipeline python3 -c "from methyl_detector import MethylDetector; print('✓ MethylDetector OK')"
docker exec methylpipeline python3 -c "from methyl_centroid import MethylCentroid; print('✓ MethylCentroid OK')"

# Test CLI wrappers
cd /home/ubuntu/MethylPipeline/packages/methyldetector
./md --help
```

## Summary of All Changes

- ✅ Removed unused config parameters (`apply_fdr_correction`, `fdr_method`, `apply_dmp_filtering`)
- ✅ Renamed all package folders to use underscores (Python standard)
- ✅ Updated all imports across packages
- ✅ Updated pyproject.toml files with `packages` field
- ✅ Added Poetry to Dockerfile
- ✅ Updated install_all.sh to use Poetry
- ✅ Created install.sh wrapper for easy installation
- ✅ Updated CLI wrappers (md, mc) to use new module names
- ✅ Cleared __pycache__ and .egg-info directories

All changes are complete and ready to use once the container is rebuilt!

