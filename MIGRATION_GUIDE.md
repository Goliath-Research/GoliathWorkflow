# Migration Guide: Multi-Repo to Monorepo

This guide helps you transition from the old multi-directory structure to the new MethylPipeline monorepo.

## Overview of Changes

### Old Structure
```
/home/ubuntu/
├── MethylUtils/
├── MethylDetector/
├── MethylCentroid/
├── MethylMapper/
├── MethylTrainer/
├── MethylClassifier/
├── MethylEnricher/
└── Work/cuda/  (Docker config)
```

### New Structure
```
/home/ubuntu/MethylPipeline/
├── packages/
│   ├── methylutils/
│   ├── methyldetector/
│   ├── methylcentroid/
│   ├── methylmapper/
│   ├── methyltrainer/
│   ├── methylclassifier/
│   └── methylenricher/
├── docker/
├── scripts/
└── docs/
```

## Migration Steps

### 1. Verify Current Setup

Before migrating, verify your current environment:

```bash
# Check existing containers
docker ps -a | grep -E "(epimethyl|methylpipeline)"

# List existing packages
ls -d /home/ubuntu/Methyl*

# Check current docker config
ls /home/ubuntu/Work/cuda/
```

### 2. Stop Existing Containers

```bash
# Stop old container (if running)
cd /home/ubuntu/Work/cuda
docker compose down
```

### 3. Update Your Workflow

#### Old Workflow (Multi-Repo)
```bash
# Old: Attach to container
docker exec -it epimethyl bash

# Old: Packages at /home/ubuntu/MethylUtils, etc.
cd /home/ubuntu/MethylUtils
```

#### New Workflow (Monorepo)
```bash
# New: Attach to container
docker exec -it methylpipeline bash

# New: Packages at /workspace/packages/
cd /workspace/packages/methylutils
```

### 4. Update Your Scripts

If you have scripts that reference old paths, update them:

```bash
# Old paths
/home/ubuntu/MethylUtils
/home/ubuntu/MethylDetector

# New paths
/workspace/packages/methylutils
/workspace/packages/methyldetector
```

### 5. Update Import Statements

Import statements remain the same (no changes needed):

```python
# These work in both old and new structure
from methyl_utils import get_logger
from methyldetector import MethylDetector
from methylclassifier import MethylClassifier
```

### 6. Update Configuration Files

If you have configuration files with hardcoded paths:

```yaml
# Old
data_path: /home/ubuntu/MethylUtils/data

# New (in container)
data_path: /workspace/packages/methylutils/data

# Best practice: Use relative paths or environment variables
data_path: ${METHYL_UTILS_PATH}/data
```

## Environment Variables

### Old Environment Variables
```bash
PYTHONPATH=/home/ubuntu/MethylUtils:/home/ubuntu/MethylDetector:...
METHYL_UTILS_PATH=/home/ubuntu/MethylUtils
```

### New Environment Variables
```bash
PYTHONPATH=/workspace/packages/methylutils:/workspace/packages/methyldetector:...
METHYL_UTILS_PATH=/workspace/packages/methylutils
```

These are set automatically in the container.

## Working with Both Structures

During transition, you may need to work with both structures:

### Option 1: Keep Old Structure (Backward Compatibility)

The new monorepo exists alongside the old structure:

```bash
/home/ubuntu/
├── MethylUtils/           # Old (still works)
├── MethylDetector/        # Old (still works)
├── ...
└── MethylPipeline/        # New (recommended)
```

Both can coexist. The new container uses `/home/ubuntu/MethylPipeline`.

### Option 2: Create Symbolic Links

For compatibility with existing scripts:

```bash
# Create symlinks from old locations to new
ln -s /home/ubuntu/MethylPipeline/packages/methylutils /home/ubuntu/MethylUtils
ln -s /home/ubuntu/MethylPipeline/packages/methyldetector /home/ubuntu/MethylDetector
# ... and so on
```

## Container Migration

### Old Container Commands
```bash
cd /home/ubuntu/Work/cuda
docker compose build
docker compose up -d
docker exec -it epimethyl bash
```

### New Container Commands
```bash
cd /home/ubuntu/MethylPipeline
bash scripts/setup_dev.sh
docker exec -it methylpipeline bash
```

## Testing After Migration

Verify everything works:

```bash
# 1. Build and start container
cd /home/ubuntu/MethylPipeline
bash scripts/setup_dev.sh

# 2. Attach to container
docker exec -it methylpipeline bash

# 3. Test imports
python -c "from methyl_utils import get_logger; print('✓ MethylUtils')"
python -c "from methyldetector import MethylDetector; print('✓ MethylDetector')"
python -c "from methylclassifier import MethylClassifier; print('✓ MethylClassifier')"

# 4. Run existing test scripts
pytest /workspace/packages/methylutils/tests/
```

## Common Issues and Solutions

### Issue: Import Errors

**Problem**: `ModuleNotFoundError: No module named 'methyl_utils'`

**Solution**: Ensure packages are installed in container:
```bash
docker exec methylpipeline bash /workspace/scripts/install_all.sh
```

### Issue: File Not Found

**Problem**: Scripts can't find files at old paths

**Solution**: Update paths in scripts or use symbolic links:
```bash
ln -s /home/ubuntu/MethylPipeline/packages/methylutils /home/ubuntu/MethylUtils
```

### Issue: Container Name Conflict

**Problem**: `Container name 'methylpipeline' already in use`

**Solution**: Stop and remove old container:
```bash
docker stop methylpipeline
docker rm methylpipeline
```

### Issue: GPU Not Available

**Problem**: `CUDA not available` in new container

**Solution**: Verify nvidia-docker is working:
```bash
docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi
```

## Rollback Procedure

If you need to revert to the old structure:

```bash
# 1. Stop new container
cd /home/ubuntu/MethylPipeline/docker
docker compose down

# 2. Start old container
cd /home/ubuntu/Work/cuda
docker compose up -d

# 3. Attach to old container
docker exec -it epimethyl bash
```

## Gradual Migration Strategy

Recommended approach for large teams:

### Phase 1: Parallel Operation (Week 1-2)
- Set up new monorepo alongside old structure
- Test new setup thoroughly
- Update documentation

### Phase 2: Transition (Week 3-4)
- Migrate development workflows to monorepo
- Update CI/CD pipelines
- Create symbolic links for compatibility

### Phase 3: Consolidation (Week 5+)
- Remove old containers
- Clean up old directory structure (optional)
- Remove symbolic links

## Benefits of New Structure

1. **Unified Codebase**: All packages in one repository
2. **Consistent Tooling**: Shared scripts and configuration
3. **Easier Deployment**: Single container setup
4. **Better Documentation**: Centralized docs
5. **Simplified Dependencies**: Clear package hierarchy
6. **Version Control**: Easier to track changes across packages
7. **Production Ready**: Separate dev and prod configurations

## Need Help?

If you encounter issues during migration:
1. Check the [Troubleshooting](docs/DEVELOPMENT.md#troubleshooting) section
2. Review container logs: `docker compose logs`
3. Open an issue on the repository
4. Contact the development team

## Checklist

- [ ] Current setup verified and documented
- [ ] Old containers stopped
- [ ] New monorepo set up
- [ ] Development container built and tested
- [ ] All packages import correctly
- [ ] Scripts updated with new paths
- [ ] Configuration files updated
- [ ] Team members notified
- [ ] Documentation reviewed
- [ ] Backup of old structure created (if needed)

