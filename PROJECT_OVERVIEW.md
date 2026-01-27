# MethylPipeline Project Overview

## 🎯 Project Summary

MethylPipeline is a unified monorepo for genome-scale methylation analysis, optimized for NVIDIA GPU acceleration. It consolidates 7 Python packages, Docker configurations, and comprehensive tooling into a single, well-organized structure.

## 📦 Package Ecosystem

### Core Package (Foundation)
```
methylutils
└── Provides: Logging, GPU management, HDF5 I/O, MethylSample class, 
    GPU-optimized stats & math
```

### Analysis & QC Packages
```
methylcentroid         methylcluster         methylmodeler
└── Centroid          └── QC & clustering   └── DMP detection +
    generation            (HDBSCAN/EM)         model packaging
```

### Interpretation & Reporting
```
methylclassifier       methylmapper          methylenricher
└── Sample             └── Gene mapping +    └── Functional
    classification         disease context       enrichment (ORA)
```

## 🏗️ Architecture

### Directory Structure
```
MethylPipeline/
│
├── 📦 packages/              # All Python packages
│   ├── methylutils/         # Core utilities & GPU helpers
│   ├── methylcentroid/      # Centroid generation
│   ├── methylcluster/       # QC & clustering
│   ├── methylmodeler/       # DMP detection + packaging
│   ├── methylclassifier/    # Classification CLI/API
│   ├── methylmapper/        # Gene mapping & disease context
│   └── methylenricher/      # Functional enrichment
│
├── 🐋 docker/               # Container configs
│   ├── Dockerfile           # Development
│   ├── Dockerfile.production
│   ├── docker-compose.yml
│   └── docker-compose.production.yml
│
├── 🔧 scripts/              # Automation
│   ├── install_all.sh       # Install packages
│   ├── setup_dev.sh         # Dev setup
│   ├── setup_prod.sh        # Prod setup
│   ├── run_container.sh     # Container mgmt
│   └── verify_setup.sh      # Verification
│
└── 📚 docs/                 # Documentation
    ├── DEVELOPMENT.md       # Dev workflow
    ├── PRODUCTION.md        # Ops guide
    ├── ARCHITECTURE.md      # System design
    └── README.md            # Doc index
```

## 🔄 Workflow

### Development Workflow
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

### Production Deployment
```
┌─────────────────────────────────────────────────────────┐
│ 1. Build Production Container                          │
│    bash scripts/setup_prod.sh                           │
│    └── Packages baked into image                       │
├─────────────────────────────────────────────────────────┤
│ 2. Deploy                                               │
│    Container runs with packages at:                     │
│    /opt/methylpipeline/lib/python3.10/site-packages    │
├─────────────────────────────────────────────────────────┤
│ 3. Monitor                                              │
│    Health checks, logs, GPU monitoring                  │
└─────────────────────────────────────────────────────────┘
```

## 💻 Technology Stack

### GPU Computing
- **CUDA**: 12.8+
- **CuPy**: GPU-accelerated NumPy
- **RAPIDS cuDF**: GPU DataFrames
- **Hardware**: NVIDIA GH200 (96GB)

### Python Ecosystem
- **Python**: 3.10
- **NumPy/SciPy**: Scientific computing
- **Pandas**: Data manipulation
- **h5py**: HDF5 support
- **PyTorch**: Neural networks

### Infrastructure
- **Docker**: Containerization
- **Ubuntu**: 22.04
- **Virtual Env**: Isolated Python environment

## 📊 Data Flow

```
Raw Samples (HDF5)
        ↓
  MethylUtils (I/O, GPU)
        ↓
  MethylCentroid (group reps)
        ↓
  MethylCluster (QC/outliers)
        ↓
  MethylModeler (DMPs + models)
        ↓
  MethylClassifier (inference)
        ↓
  MethylMapper (gene mapping + disease enrichment)
        ↓
  MethylEnricher (functional analysis on MethylMapper outputs)
```

## 🚀 Quick Start Commands

### Initial Setup
```bash
cd /home/ubuntu/MethylPipeline
bash scripts/setup_dev.sh
```

### Daily Usage
```bash
# Start container
./scripts/run_container.sh dev start

# Open shell
docker exec -it methylpipeline bash

# Inside container
python -c "from methyl_utils import get_logger"
pytest /workspace/packages/methylutils/tests/
```

### Container Management
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
| GPU | NVIDIA GH200 (96GB) or compatible |
| CPU | 16+ vCPU |
| RAM | 128GB+ recommended |
| Storage | NVMe SSD |
| OS | Ubuntu 22.04 |
| CUDA | 12.8+ |
| Docker | With nvidia-docker2 |

## 🔐 Key Features

### ✅ Development Features
- **Editable installs** - Changes immediately reflected
- **Volume mounts** - Edit on host, run in container
- **Hot reload** - No rebuild needed for code changes
- **Full tooling** - pytest, black, mypy, flake8

### ✅ Production Features
- **Immutable containers** - Packages baked in
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
| QUICK_REFERENCE.md | Command cheatsheet | Everyone |
| MIGRATION_GUIDE.md | Transition guide | Existing users |
| docs/DEVELOPMENT.md | Dev workflow | Developers |
| docs/PRODUCTION.md | Ops guide | DevOps/SRE |
| docs/ARCHITECTURE.md | System design | Architects |
| CHANGELOG.md | Version history | Everyone |
| SETUP_COMPLETE.md | Setup verification | Setup team |

## 🎓 Learning Path

### For New Developers
1. Read [README.md](README.md)
2. Run [scripts/setup_dev.sh](scripts/setup_dev.sh)
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
- **Clear history**: Changelog maintained

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
- ✅ All 7 packages recognized
- ✅ Docker builds successfully
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
4. Check container logs

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
5. **🔧 Developer-Friendly**: Editable installs, hot reload
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
2. 🚀 **Build container**: `bash scripts/setup_dev.sh`
3. 🧪 **Test**: `docker exec methylpipeline pytest /workspace/packages/`
4. 📖 **Read docs**: Start with `docs/DEVELOPMENT.md`
5. 💻 **Start coding**: Edit files in `packages/`

---

**Status**: ✅ Setup Complete  
**Version**: 1.0.0  
**Last Updated**: 2025-10-13  

For detailed information, see individual documentation files or run:
```bash
cat /home/ubuntu/MethylPipeline/QUICK_REFERENCE.md
```

