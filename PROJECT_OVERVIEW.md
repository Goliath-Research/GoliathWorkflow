# MethylPipeline Project Overview

## 🎯 Project Summary

MethylPipeline is a unified monorepo for genome-scale methylation analysis, optimized for NVIDIA GPU acceleration. It consolidates 10 Python packages, optional Docker configurations, and host setup tooling into a single, well-organized structure.

## 📦 Package Ecosystem

### Core Package (Foundation)
```
methylutils
└── Provides: Logging, GPU management, HDF5 I/O, MethylSample class, 
    GPU-optimized stats & math
```

### Analysis & QC Packages
```
methylcentroid         methylcluster         methyldetector
└── Centroid          └── QC & clustering   └── DMP detection +
    generation            (HDBSCAN/EM)         model creation
```

### Data Quality Utilities
```
methylalignmentqc
└── Parse Parabricks QC metrics to JSON/columnar outputs
```

### Interpretation & Reporting
```
methylclassifier       methylmapper          methylenricher
└── Sample             └── Gene mapping +    └── Functional
    classification         disease context       enrichment (ORA)
    (Beta/BMM, multi-class)

methylpredictor        methylvalidation
└── Classification      └── Validation workflows
    metrics on test sets    (Monte Carlo, stratified splits)
```

## 🏗️ Architecture

### Directory Structure
```
MethylPipeline/
│
├── 📦 packages/              # All Python packages
│   ├── methylutils/         # Core utilities & GPU helpers
│   ├── methylcentroid/      # Centroid generation (+ explorer)
│   ├── methylcluster/       # QC & clustering
│   ├── methyldetector/      # DMP detection + model creation (+ explorer)
│   ├── methylclassifier/    # Classification CLI/API
│   ├── methylmapper/        # Gene mapping & disease context
│   ├── methylenricher/      # Functional enrichment
│   ├── methylalignmentqc/   # Alignment QC parsing
│   ├── methylpredictor/     # Classification metrics
│   └── methylvalidation/    # Validation workflows
│
├── 🐋 docker/               # Container configs
│   ├── Dockerfile           # Development
│   ├── Dockerfile.production
│   ├── docker-compose.yml
│   └── docker-compose.production.yml
│
├── 🔧 scripts/              # Automation
│   ├── install_all.sh       # Install packages
│   ├── setup_dev.sh         # Dev setup (Docker)
│   ├── setup_host.sh        # Host setup (non-Docker)
│   ├── setup_prod.sh        # Prod setup (Docker)
│   ├── run_container.sh     # Container mgmt
│   └── verify_setup.sh      # Verification
│
├── requirements-pipeline.txt # Pipeline-level Python deps
├── requirements-gpu.txt      # GPU/CUDA deps (CUDA 13.x)
│
└── 📚 docs/                 # Documentation
    ├── DEVELOPMENT.md       # Dev workflow
    ├── PRODUCTION.md        # Ops guide
    ├── ARCHITECTURE.md      # System design
    └── README.md            # Doc index
```

## 🔄 Workflow

### Development Workflow (Host / Non-Docker)
```
┌─────────────────────────────────────────────────────────┐
│ 1. Setup                                                │
│    bash scripts/setup_host.sh --system-deps --gpu       │
│    └── Installs system + pipeline deps + packages       │
├─────────────────────────────────────────────────────────┤
│ 2. Development                                          │
│    Edit files → packages/*/                             │
│    └── Editable installs reflect changes locally       │
├─────────────────────────────────────────────────────────┤
│ 3. Testing                                              │
│    pytest packages/                                     │
├─────────────────────────────────────────────────────────┤
│ 4. Commit                                               │
│    git add . && git commit -m "..."                     │
└─────────────────────────────────────────────────────────┘
```

Note: On Ubuntu 24.04+ where `python3.10` packages are unavailable, `setup_host.sh` installs the default `python3` packages and uses the system Python (3.10+).

### Development Workflow (Docker, Optional)
```
┌─────────────────────────────────────────────────────────┐
│ 1. Setup                                                │
│    bash scripts/setup_dev.sh                            │
│    └── Builds container, installs packages             │
├─────────────────────────────────────────────────────────┤
│ 2. Development                                          │
│    Edit files → packages/*/  (on host)                  │
│    └── Changes immediately reflected in container      │
├─────────────────────────────────────────────────────────┤
│ 3. Testing                                              │
│    docker exec methylpipeline bash                      │
│    pytest /workspace/packages/                          │
├─────────────────────────────────────────────────────────┤
│ 4. Commit                                               │
│    git add . && git commit -m "..."                     │
└─────────────────────────────────────────────────────────┘
```

### Production Deployment (Host or Docker)
```
┌─────────────────────────────────────────────────────────┐
│ 1. Host Setup                                           │
│    bash scripts/setup_host.sh --system-deps --gpu       │
│    └── Packages installed into virtualenv               │
├─────────────────────────────────────────────────────────┤
│ 2. Docker Setup (optional)                              │
│    bash scripts/setup_prod.sh                           │
│    └── Packages baked into image                        │
├─────────────────────────────────────────────────────────┤
│ 3. Monitor                                              │
│    Health checks, logs, GPU monitoring                  │
└─────────────────────────────────────────────────────────┘
```

## 💻 Technology Stack

### GPU Computing
- **CUDA**: 13.x
- **CuPy**: GPU-accelerated NumPy
- **RAPIDS cuDF**: GPU DataFrames
- **Hardware**: NVIDIA DGX Spark / GH200 / A100-class GPUs

### Python Ecosystem
- **Python**: 3.10+
- **NumPy/SciPy**: Scientific computing
- **Pandas**: Data manipulation
- **h5py**: HDF5 support
- **PyTorch**: Neural networks

### Infrastructure
- **Host**: Ubuntu 22.04+ with venv + pip
- **Docker**: Optional containerization
- **Python**: 3.10+ environments

## 📊 Data Flow

```
Raw Samples (HDF5)
        ↓
  MethylAlignmentQC (optional QC parsing)
        ↓
  MethylUtils (I/O, GPU)
        ↓
  MethylCentroid (group reps)
        ↓
  MethylCluster (QC/outliers)
        ↓
  MethylDetector (DMPs + models)
        ↓
  MethylClassifier (inference, Beta/BMM multi-class)
        ↓
  MethylMapper (gene mapping + disease enrichment)
        ↓
  MethylEnricher (functional analysis on MethylMapper outputs)
```

## 🚀 Quick Start Commands

### Initial Setup (Host)
```bash
cd /path/to/MethylPipeline
bash scripts/setup_host.sh --system-deps --gpu
```

### Initial Setup (Docker, Optional)
```bash
cd /path/to/MethylPipeline
bash scripts/setup_dev.sh
```

### Daily Usage (Host)
```bash
python -c "from methyl_utils import get_logger"
pytest packages/methylutils/tests/
```

### Container Management (Optional)
```bash
./scripts/run_container.sh dev start     # Start
./scripts/run_container.sh dev stop      # Stop
./scripts/run_container.sh dev restart   # Restart
./scripts/run_container.sh dev logs      # View logs
./scripts/run_container.sh dev shell     # Open shell
```

## 📈 System Requirements

| Component | Requirement |
|-----------|-------------|
| GPU | NVIDIA GPU (A100/H100/GH200/DGX Spark) or compatible |
| CPU | 16+ vCPU |
| RAM | 128GB+ recommended |
| Storage | NVMe SSD |
| OS | Ubuntu 22.04+ |
| CUDA | 13.x (for GPU acceleration) |
| Python | 3.10+ |
| Docker | Optional (for containerized deployment) |

## 🔐 Key Features

### ✅ Development Features
- **Editable installs** - Changes immediately reflected
- **Host-first setup** - Install without containers
- **Container option** - Use Docker when needed
- **Full tooling** - pytest, black, mypy, flake8

### ✅ Production Features
- **Host or container** - Run directly or in Docker
- **Immutable containers** - Packages baked in (optional)
- **Health checks** - Automated monitoring
- **Version pinning** - Reproducible builds
- **Restart policies** - High availability
- **Resource limits** - Controlled usage

### ✅ GPU Features
- **Automatic detection** - CPU/GPU fallback
- **Memory management** - Chunked processing
- **Monitoring tools** - GPU utilization tracking
- **Optimization** - Memory pools, caching

## 📖 Documentation Map

| Document | Purpose | Audience |
|----------|---------|----------|
| README.md | Quick start & overview | Everyone |
| PROJECT_OVERVIEW.md | Repo summary | Everyone |
| QUICK_REFERENCE.md | Command cheatsheet | Everyone |
| QUICK_REFERENCE_CONTEXTS.md | Config/context cheatsheet | Everyone |
| ENV_SETUP.md | Environment setup | Developers |
| docs/DEVELOPMENT.md | Dev workflow | Developers |
| docs/PRODUCTION.md | Ops guide | DevOps/SRE |
| docs/ARCHITECTURE.md | System design | Architects |
| docs/MAINTENANCE.md | Maintenance tasks | DevOps/SRE |
| SETUP_COMPLETE.md | Setup verification | Setup team |

## 🎓 Learning Path

### For New Developers
1. Read [README.md](README.md)
2. Run [scripts/setup_host.sh](scripts/setup_host.sh) (or Docker setup)
3. Read [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
4. Explore package code in `packages/`
5. Run tests: `pytest packages/methylutils/tests/`

### For Operations Team
1. Read [README.md](README.md)
2. Read [docs/PRODUCTION.md](docs/PRODUCTION.md)
3. Run [scripts/setup_prod.sh](scripts/setup_prod.sh)
4. Configure monitoring
5. Review [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

### For System Architects
1. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
2. Review package dependencies
3. Study GPU optimization patterns
4. Plan scaling strategy
5. Design CI/CD pipeline

## 🔄 Version Control Strategy

### Repository Structure
- **Monorepo**: All packages in one repository
- **Unified versioning**: Single version number
- **Atomic commits**: Changes across packages in one commit
- **Clear history**: Documented in git history

### Branch Strategy (Recommended)
```
main (production)
  ↑
develop (integration)
  ↑
feature/* (development)
```

## 🎯 Success Metrics

### Setup Validation
- ✅ All 8 packages recognized
- ✅ Host setup completes successfully
- ✅ Docker builds successfully (if used)
- ✅ All imports work
- ✅ Tests pass
- ✅ GPU accessible

### Performance Targets
- GPU utilization: >70%
- Processing speed: 10K+ samples/hour
- Memory efficiency: <80% GPU memory
- Startup time: <60 seconds

## 🆘 Getting Help

### Self-Service Resources
1. Check [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
2. Review [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#troubleshooting)
3. Run `scripts/verify_setup.sh`
4. Check container logs (if using Docker)

### Support Channels
- Documentation: `docs/`
- Issue tracker: Repository issues
- Logs: `docker compose logs`
- Team: Contact development team

## 🎉 What Makes This Special

1. **🎯 Unified**: All components in one place
2. **⚡ GPU-Optimized**: Leverages NVIDIA acceleration
3. **📦 Production-Ready**: Dev and prod configs
4. **📚 Well-Documented**: Comprehensive guides
5. **🔧 Developer-Friendly**: Editable installs, host-first
6. **🚀 Easy Deployment**: Single command setup
7. **🔐 Secure**: Non-root containers, isolation
8. **📊 Scalable**: Designed for growth

## 📅 Project Timeline

- **Phase 1** (Complete): Monorepo structure created
- **Phase 2** (Current): Development workflow established
- **Phase 3** (2 months): Production deployment
- **Phase 4** (Future): CI/CD, scaling, enhancements

## 🎓 Next Steps

1. ✅ **Verify setup**: `bash scripts/verify_setup.sh`
2. 🚀 **Install (host)**: `bash scripts/setup_host.sh --system-deps --gpu`
3. 🧪 **Test**: `pytest packages/`
4. 📖 **Read docs**: Start with `docs/DEVELOPMENT.md`
5. 💻 **Start coding**: Edit files in `packages/`

---

**Status**: ✅ Setup Complete  
**Version**: 1.0.0  
**Last Updated**: 2026-01-28  

For detailed information, see individual documentation files or run:
```bash
cat QUICK_REFERENCE.md
```

