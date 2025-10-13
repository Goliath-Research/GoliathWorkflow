# Changelog

All notable changes to the MethylPipeline project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-10-13

### Added
- Initial monorepo structure consolidating all MethylPipeline packages
- 7 integrated packages:
  - methylutils - Core utilities and GPU support
  - methylcentroid - Centroid generation
  - methyldetector - DMP detection
  - methylmapper - DMP-to-gene mapping
  - methyltrainer - Model training
  - methylclassifier - Sample classification
  - methylenricher - Gene enrichment analysis
- Docker development and production configurations
- Unified installation scripts
- Comprehensive documentation (DEVELOPMENT, PRODUCTION, ARCHITECTURE)
- Migration guide from multi-repo structure
- Container management scripts
- Workspace configuration (pyproject.toml)
- Centralized .gitignore

### Changed
- Migrated from multi-directory structure to monorepo
- Container name: `epimethyl` → `methylpipeline`
- Package paths: `/home/ubuntu/MethylUtils` → `/workspace/packages/methylutils`
- Updated PYTHONPATH for new structure
- Docker Compose syntax: `docker-compose` → `docker compose`

### Infrastructure
- Base image: nvidia/cuda:12.8.0-devel-ubuntu22.04
- Python: 3.10 in virtual environment
- GPU support: NVIDIA GH200 with 96GB RAM
- CUDA: 12.8+
- CuPy: 12.x with CUDA support
- RAPIDS: cuDF for GPU DataFrames

## [Unreleased]

### Planned
- CI/CD integration (GitHub Actions)
- Automated testing pipeline
- Performance benchmarks
- Multi-GPU support
- Distributed computing (Dask)
- Web interface (Flask/FastAPI)
- Cloud deployment configurations
- Package versioning automation

---

## Version History

### Version 1.0.0 - Initial Monorepo Release
First unified release of the MethylPipeline system. This version consolidates all previously separate packages into a single monorepo with improved tooling and documentation.

**Migration**: See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for instructions on migrating from the old multi-repo structure.

---

## How to Update This Changelog

When making changes:

1. Add entries under `[Unreleased]` section
2. Use categories: Added, Changed, Deprecated, Removed, Fixed, Security
3. Before release, move entries from Unreleased to new version section
4. Include date and version number
5. Link to migration guides or breaking change documentation

Example:
```markdown
## [1.1.0] - 2025-11-01

### Added
- New feature X

### Changed
- Modified behavior Y

### Fixed
- Bug Z
```

