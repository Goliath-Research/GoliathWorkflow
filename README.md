# MethylPipeline

Unified genomics pipeline for methylation analysis, optimized for NVIDIA GPU acceleration.

## Overview

MethylPipeline is a comprehensive monorepo containing all components required for methylation-based genomic analysis. The pipeline is designed to run on NVIDIA GH200 GPUs with 96GB RAM and leverages CUDA, RAPIDS, CuPy, and other GPU-accelerated libraries for high-performance computation.

## Architecture

The pipeline consists of 8 integrated Python packages:

- **methylutils** - Core utilities: logging, GPU management, HDF5 file handling, genomic sample classes (MethylSample), and GPU-optimized mathematical/statistical functions
- **methylcentroid** - Centroid generation for sample clustering
- **methyldetector** - DMP (Differentially Methylated Position) detection with effect size calculations
- **methylcluster** - Sample clustering using Jensen-Shannon or Hellinger distance with HDBSCAN
- **methylmapper** - DMP-to-gene mapping with Azure SQL integration
- **methyltrainer** - Machine learning model training for classification
- **methylclassifier** - Sample classification using trained models
- **methylenricher** - Gene enrichment analysis

## System Requirements

### Hardware
- NVIDIA GPU GH200 with 96GB RAM (or compatible CUDA-enabled GPU)
- 16+ vCPU
- Shared storage for multi-VM deployments

### Software
- Docker with GPU support (nvidia-docker2)
- NVIDIA Driver 525.60.13+
- CUDA 12.8+

## Quick Start

### Development Environment

1. **Clone the repository:**
   ```bash
   cd /home/ubuntu
   git clone <repository-url> MethylPipeline
   cd MethylPipeline
   ```

2. **Set up development environment:**
   ```bash
   bash scripts/setup_dev.sh
   ```

3. **Attach to container:**
   ```bash
   docker exec -it methylpipeline bash
   ```

4. **Test installation:**
   ```bash
   python -c "from methyl_utils import get_logger; print('✓ MethylUtils OK')"
   ```

### Production Deployment

1. **Build production container:**
   ```bash
   bash scripts/setup_prod.sh
   ```

2. **Attach to production container:**
   ```bash
   docker exec -it methylpipeline-prod bash
   ```

## Container Management

Use the convenience script to manage containers:

```bash
# Development container
./scripts/run_container.sh dev start    # Start dev container
./scripts/run_container.sh dev stop     # Stop dev container
./scripts/run_container.sh dev shell    # Open bash shell
./scripts/run_container.sh dev logs     # View logs

# Production container
./scripts/run_container.sh prod start   # Start prod container
./scripts/run_container.sh prod stop    # Stop prod container
```

## Project Structure

```
MethylPipeline/
├── packages/           # Python packages
│   ├── methylutils/
│   ├── methylcentroid/
│   ├── methyldetector/
│   ├── methylcluster/
│   ├── methylmapper/
│   ├── methyltrainer/
│   ├── methylclassifier/
│   └── methylenricher/
├── docker/            # Container configuration
│   ├── Dockerfile
│   ├── Dockerfile.production
│   ├── docker-compose.yml
│   └── docker-compose.production.yml
├── scripts/           # Setup and utility scripts
│   ├── setup_dev.sh
│   ├── setup_prod.sh
│   ├── install_all.sh
│   └── run_container.sh
└── docs/             # Documentation
    ├── DEVELOPMENT.md
    ├── PRODUCTION.md
    └── ARCHITECTURE.md
```

## Development Workflow

1. **Make changes** to any package in `packages/`
2. **Changes are immediately reflected** in the container (editable install)
3. **Run tests** within the container
4. **Commit changes** to version control

See [DEVELOPMENT.md](docs/DEVELOPMENT.md) for detailed development guidelines.

## Production Deployment

Production containers have all packages installed as regular (non-editable) packages with pinned versions for reproducibility.

See [PRODUCTION.md](docs/PRODUCTION.md) for production deployment guidelines.

## Documentation

- [Development Guide](docs/DEVELOPMENT.md) - Development workflow, testing, contributing
- [Production Guide](docs/PRODUCTION.md) - Production deployment and operations
- [Architecture](docs/ARCHITECTURE.md) - System architecture and dependencies

## Testing

Run tests from within the container:

```bash
# Test all packages
pytest packages/

# Test specific package
pytest packages/methylutils/tests/

# Test with GPU
pytest -m gpu packages/
```

## License

MIT License

## Support

For issues and questions, please open an issue on the repository.

