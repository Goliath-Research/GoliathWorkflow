# Development Guide

This guide covers the development workflow for MethylPipeline.

## Setting Up Development Environment

### Prerequisites

- Docker with GPU support (nvidia-docker2)
- NVIDIA Driver 525.60.13+
- CUDA 12.8+
- Git

### Initial Setup

1. **Clone the repository:**
   ```bash
   cd /home/ubuntu
   git clone <repository-url> MethylPipeline
   cd MethylPipeline
   ```

2. **Build and start development container:**
   ```bash
   bash scripts/setup_dev.sh
   ```

   This script will:
   - Build the Docker container with all dependencies
   - Start the container
   - Install all packages in editable mode (`pip install -e .`)

3. **Attach to the container:**
   ```bash
   docker exec -it methylpipeline bash
   ```

## Development Workflow

### Making Changes

All packages are mounted as volumes and installed in editable mode, so changes to Python files are immediately reflected in the container.

1. **Edit files** on the host machine in `packages/<package-name>/`
2. **Test changes** inside the container
3. **Commit** when ready

### Package Structure

Each package follows this structure:

```
packages/methylutils/
├── methyl_utils/          # Source code
│   ├── __init__.py
│   ├── module1.py
│   └── module2.py
├── tests/                 # Tests
│   ├── test_module1.py
│   └── test_module2.py
├── setup.py              # Package configuration
├── requirements.txt      # Dependencies
└── README.md            # Package documentation
```

### Testing

#### Run All Tests

```bash
# Inside container
pytest packages/
```

#### Run Tests for Specific Package

```bash
pytest packages/methylutils/tests/
```

#### Run Tests with Coverage

```bash
pytest --cov=packages/ --cov-report=html packages/
```

#### Run GPU Tests

```bash
pytest -m gpu packages/
```

#### Run Tests in Parallel

```bash
pytest -n auto packages/
```

### Code Quality

#### Format Code

```bash
# Inside container
black packages/
```

#### Check Code Style

```bash
flake8 packages/
```

#### Type Checking

```bash
mypy packages/methylutils/
```

## Package Dependencies

### Installation Order

Packages must be installed in this order due to dependencies:

1. **methylutils** (core, no dependencies)
2. **methylcentroid** (depends on methylutils)
3. **methyldetector** (depends on methylutils)
4. **methylmapper** (depends on methylutils)
5. **methyltrainer** (depends on methylutils)
6. **methylclassifier** (depends on methylutils, methyltrainer)
7. **methylenricher** (depends on methylutils)

The `install_all.sh` script handles this automatically.

### Adding New Dependencies

1. Add to package's `requirements.txt`
2. Add to package's `setup.py` in `install_requires`
3. If it's a system library, add to `docker/Dockerfile`
4. Rebuild container: `docker compose -f docker/docker-compose.yml build`

## Common Development Tasks

### Add New Package

1. Create package directory: `mkdir packages/newpackage`
2. Add `setup.py`, `requirements.txt`, `README.md`
3. Create source directory: `mkdir packages/newpackage/newpackage`
4. Add `__init__.py` and source files
5. Update `scripts/install_all.sh` to include new package
6. Update `docker/docker-compose.yml` PYTHONPATH

### Debugging in Container

```bash
# Attach with bash
docker exec -it methylpipeline bash

# Run Python with debugging
python -m pdb script.py

# Install ipdb for better debugging
pip install ipdb
```

### View Container Logs

```bash
cd docker/
docker compose logs -f
```

### Restart Container

```bash
./scripts/run_container.sh dev restart
```

### Rebuild Container

```bash
cd docker/
docker compose build
docker compose up -d
```

## GPU Development

### Check GPU Availability

```bash
# Inside container
python -c "import cupy; print(cupy.cuda.runtime.getDeviceCount())"
```

### Monitor GPU Usage

```bash
# Inside container
watch -n 1 nvidia-smi
```

### GPU Memory Management

MethylUtils provides GPU management utilities:

```python
from methyl_utils.gpu_utils import check_gpu_memory, clear_gpu_memory

# Check available memory
memory_info = check_gpu_memory()
print(f"Free: {memory_info['free_mb']} MB")

# Clear GPU cache
clear_gpu_memory()
```

## Troubleshooting

### Container Won't Start

```bash
# Check Docker logs
docker compose -f docker/docker-compose.yml logs

# Check GPU access
nvidia-smi
```

### Import Errors

```bash
# Reinstall packages
docker exec methylpipeline bash /workspace/scripts/install_all.sh

# Check PYTHONPATH
docker exec methylpipeline bash -c "echo \$PYTHONPATH"
```

### GPU Errors

```bash
# Check CUDA version
nvidia-smi

# Check CuPy installation
docker exec methylpipeline python -c "import cupy; print(cupy.__version__)"
```

### Permission Errors

```bash
# Fix ownership (run on host)
sudo chown -R ubuntu:ubuntu /home/ubuntu/MethylPipeline
```

## Best Practices

1. **Always test** before committing
2. **Write tests** for new functionality
3. **Update documentation** when adding features
4. **Use type hints** where appropriate
5. **Follow PEP 8** style guidelines
6. **Keep commits atomic** and well-described
7. **Handle GPU memory** carefully (use context managers)
8. **Profile GPU code** before optimization

## Resources

- [CUDA Programming Guide](https://docs.nvidia.com/cuda/)
- [CuPy Documentation](https://docs.cupy.dev/)
- [RAPIDS Documentation](https://docs.rapids.ai/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)

