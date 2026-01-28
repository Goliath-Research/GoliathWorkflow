# MethylPipeline

**Unified Genomics Pipeline for Comprehensive Methylation Analysis**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CUDA 13.0+](https://img.shields.io/badge/CUDA-13.0+-green.svg)](https://developer.nvidia.com/cuda-toolkit)

## Overview

MethylPipeline is a comprehensive, production-ready pipeline for methylation-based biomarker discovery and classification. It combines statistical rigor, Bayesian probabilistic methods, and GPU acceleration to provide a complete workflow from raw methylation samples to validated classifiers.

### Key Capabilities

- 🧬 **Centroid Generation**: Representative methylation profiles with outlier detection
- 📊 **DMP Detection**: Statistical identification of differentially methylated positions
- 🎯 **Bayesian Classification**: Probabilistic models with true posterior probabilities (Beta/BMM)
- 🔍 **Clustering**: Exploratory analysis, QC, and subtype discovery
- 🚀 **GPU Acceleration**: 10-50x speedup with NVIDIA GPUs
- 📦 **Production Ready**: Docker deployment, reproducible configurations
- 📚 **Comprehensive Documentation**: 6,000+ lines covering theory, algorithms, and examples

## Architecture

MethylPipeline now ships **7 packages** that share the MethylUtils foundation.

### Foundation

#### 1. **MethylUtils**
Core utilities, GPU detection, statistical functions, and data structures used everywhere.

**Key Components**:
- `MethylSample`, `PositionAligner`, `MethylCentroidPair`
- Probabilistic Beta classifier + multi-class Beta Mixture support
- Seven GPU-aware distance metrics (Jensen-Shannon, Hellinger, Wasserstein, etc.)
- Unified GPU/CPU memory management, logging, and profiling helpers

📚 [MethylUtils README](packages/methylutils/README.md) | [Comprehensive Guide](packages/methylutils/docs/METHYLUTILS_COMPREHENSIVE_DOCUMENTATION.md)

### Analysis & Quality Control

#### 2. **MethylCentroid** – Group Representatives
Creates extended centroids (Sx, Sx2, N) with adaptive outlier detection and GPU acceleration.

📚 [MethylCentroid README](packages/methylcentroid/README.md) | [Comprehensive Guide](packages/methylcentroid/docs/METHYLCENTROID_COMPREHENSIVE_DOCUMENTATION.md)

#### 3. **MethylCluster** – Exploratory Analysis
Multi-method clustering (HDBSCAN, Hierarchical, Centroid-based) with forced groups, soft assignments, and reusable distance matrices.

📚 [MethylCluster README](packages/methylcluster/README.md) | [Comprehensive Guide](packages/methylcluster/docs/METHYLCLUSTER_COMPREHENSIVE_DOCUMENTATION.md)

#### 4. **MethylModeler** – DMP Detection & Model Packaging
Detects Differentially Methylated Positions, applies biological filters, optimizes Balanced Accuracy, and exports classifier bundles for MethylClassifier.

📚 [MethylModeler README](packages/methylmodeler/README.md) | [Comprehensive Guide](packages/methylmodeler/docs/METHYLMODELER_COMPREHENSIVE_DOCUMENTATION.md)

### Interpretation & Reporting

#### 5. **MethylClassifier** – Sample Prediction
Loads packaged classifiers (single or multi-class), applies temperature scaling/Platt calibration, and scores samples with full posterior probabilities. Supports hybrid Beta/BMM likelihoods when BMM centroids are available.

📚 [MethylClassifier README](packages/methylclassifier/README.md) | [Comprehensive Guide](packages/methylclassifier/docs/METHYLCLASSIFIER_COMPREHENSIVE_DOCUMENTATION.md)

#### 6. **MethylMapper** – Gene Mapping & Disease Context
Maps optimized DMPs to genomic features using either the legacy Azure SQL workflow or the preferred bedtools-based mapper with Grok + Open Targets disease enrichment (optional DisGeNET).

📚 [MethylMapper README](packages/methylmapper/README.md) | [Quick Start](packages/methylmapper/QUICK_START.md)

#### 7. **MethylEnricher** – Functional Enrichment
Performs ORA/Enrichr-based enrichment across KEGG, Reactome, GO, MSigDB, and WikiPathways from MethylMapper gene lists (TXT/CSV).

📚 [MethylEnricher README](packages/methylenricher/README.md) | [Installation Notes](packages/methylenricher/INSTALLATION.md)

## Complete Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    1. Sample Preparation                    │
│  Collect raw methylation samples, store as HDF5 files       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              2. Centroid Generation (MethylCentroid)        │
│  Create representative centroids, remove outliers           │
│  Output: Centroid HDF5 files for each group                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│      3. Quality Control & Clustering (MethylCluster)        │
│  Detect batch effects/outliers, force expected groupings    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│      4. DMP Detection & Model Creation (MethylModeler)      │
│  Compare centroids, detect DMPs with FDR correction         │
│  Optimize Balanced Accuracy and package classifiers         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│           5. Classification (MethylClassifier)              │
│  Predict class for new samples with posterior probabilities │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│           6. Gene Mapping (MethylMapper)                    │
│  Map DMPs to genes/features, optional disease enrichment    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│        7. Functional Enrichment (MethylEnricher)            │
│  Perform ORA/Enrichr analysis on MethylMapper gene lists    │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Installation

#### Option 1: Docker (Recommended)

```bash
# Clone repository
git clone https://github.com/yourusername/MethylPipeline.git
cd MethylPipeline

# Build and start development container
./scripts/setup_dev.sh

# Or build production container
./scripts/setup_prod.sh

# Enter container
docker exec -it methylpipeline bash
```

#### Option 2: Host (Non-Docker)

```bash
# Clone repository
git clone https://github.com/yourusername/MethylPipeline.git
cd MethylPipeline

# Install on host (recommended for DGX / non-Docker)
bash scripts/setup_host.sh --system-deps --gpu
```

Notes:
- Omit `--gpu` for CPU-only installs.
- `requirements-pipeline.txt` contains shared Python deps.
- `requirements-gpu.txt` adds CUDA 12.x requirements.
- Add `--venv /path/to/venv` to control the virtualenv location.

### Basic Usage Example

```python
# 1. Create centroids
from methyl_centroid import MethylCentroid

healthy_centroid = MethylCentroid(
    add_samples=['/data/healthy1', '/data/healthy2', '/data/healthy3'],
    chrom='1',
    ctx='CG',
    centroid_output_path='/centroids/healthy'
).build_centroid()

cancer_centroid = MethylCentroid(
    add_samples=['/data/cancer1', '/data/cancer2'],
    chrom='1',
    ctx='CG',
    centroid_output_path='/centroids/cancer'
).build_centroid()

# 2. Detect DMPs and train classifier
from methyl_modeler import MethylModeler, MethylModelerConfig

config = MethylModelerConfig(
    chromosome="1",
    contexts=["CG"],
    centroid1_dir='/centroids/healthy',
    centroid2_dir='/centroids/cancer',
    output_dir='/output/modeler',
    target_balanced_accuracy=0.95
)

modeler = MethylModeler(config)
result = modeler.run()
print(f"Model trained with {result.total_biological_dmps} high-confidence DMPs")
print(f"Classifier saved to: {result.classifier_model_path}")

# 3. Classify new samples
from methyl_classifier import MethylClassifier

classifier = MethylClassifier('/output/modeler/classifier-1.pkl')

for sample in ['/data/test1', '/data/test2', '/data/test3']:
    result = classifier.predict(sample)
    print(f"{sample}: {result['predicted_class']} "
          f"(confidence: {result['confidence']:.3f})")
```

## Key Features

### Statistical Rigor

- **Storey's q-value FDR correction**: More powerful than Benjamini-Hochberg for genomics data
- **Balanced Accuracy**: Robust to class imbalance (e.g., 35 healthy vs 12 cancer samples)
- **Bayesian Probabilistic Models**: Exact Beta distribution likelihoods, not ML approximations
- **Multiple Distance Metrics**: Jensen-Shannon, Hellinger, Wasserstein, Jeffreys, Bhattacharyya

### GPU Acceleration

- **Automatic GPU Detection**: Seamless CPU fallback when GPU unavailable
- **20-50x Speedup**: NVIDIA CUDA acceleration via CuPy
- **Memory Efficient**: LRU caching, memory-mapped I/O, chunked processing
- **Multi-GPU Support**: Parallel processing across chromosomes

### Production Ready

- **Docker Deployment**: Reproducible containerized environments
- **JSON Configuration**: All parameters tracked for reproducibility
- **Model Packaging**: Complete metadata in `.pkl` files
- **Comprehensive Logging**: Detailed progress and diagnostics
- **Error Handling**: Graceful degradation and informative messages

## Documentation

### 📚 Comprehensive Documentation

Deep dives with algorithms, math, and advanced workflows:

- [MethylUtils Comprehensive Documentation](packages/methylutils/docs/METHYLUTILS_COMPREHENSIVE_DOCUMENTATION.md)
- [MethylCentroid Comprehensive Documentation](packages/methylcentroid/docs/METHYLCENTROID_COMPREHENSIVE_DOCUMENTATION.md)
- [MethylCluster Comprehensive Documentation](packages/methylcluster/docs/METHYLCLUSTER_COMPREHENSIVE_DOCUMENTATION.md)
- [MethylModeler Comprehensive Documentation](packages/methylmodeler/docs/METHYLMODELER_COMPREHENSIVE_DOCUMENTATION.md)
- [MethylClassifier Comprehensive Documentation](packages/methylclassifier/docs/METHYLCLASSIFIER_COMPREHENSIVE_DOCUMENTATION.md)
- [MethylPipeline Integration Documentation](docs/METHYLPIPELINE_COMPREHENSIVE_DOCUMENTATION.md)

### 📖 Package READMEs & Guides

- [MethylUtils README](packages/methylutils/README.md)
- [MethylCentroid README](packages/methylcentroid/README.md)
- [MethylCluster README](packages/methylcluster/README.md)
- [MethylModeler README](packages/methylmodeler/README.md)
- [MethylClassifier README](packages/methylclassifier/README.md)
- [MethylMapper README](packages/methylmapper/README.md) | [Bedtools Quick Start](packages/methylmapper/QUICK_START.md)
- [MethylEnricher README](packages/methylenricher/README.md)

### 🏗️ Architecture Documentation

- [Architecture Overview](docs/ARCHITECTURE.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [Production Deployment](docs/PRODUCTION.md)

## System Requirements

### Hardware Requirements

#### Minimum (CPU-only)
- **CPU**: 8 cores, 3.0 GHz+
- **RAM**: 32 GB
- **Storage**: 500 GB SSD
- **Time**: ~50 hours for genome-wide analysis

#### Recommended (GPU)
- **CPU**: 16 cores, 3.5 GHz+
- **RAM**: 64 GB
- **GPU**: NVIDIA GPU with 16 GB+ VRAM (V100, A100, GH200)
- **Storage**: 1 TB NVMe SSD
- **Time**: ~4 hours for genome-wide analysis

#### Production (Multi-GPU)
- **CPU**: 32+ cores
- **RAM**: 128 GB+
- **GPU**: 4x NVIDIA A100 (40 GB each) or 1x GH200 (96 GB)
- **Storage**: 2 TB NVMe SSD
- **Time**: ~1 hour for genome-wide analysis

### Software Requirements

- **OS**: Linux (Ubuntu 20.04+), macOS (CPU-only)
- **Python**: 3.10-3.12
- **CUDA**: 13.0+ (for GPU acceleration)
- **Docker**: 20.10+ (for containerized deployment)

## Performance Benchmarks

### GPU Acceleration

| Operation | CPU Time | GPU Time | Speedup |
|-----------|----------|----------|---------|
| Centroid (35 samples, Chr1) | 15 min | 2 min | 7.5x |
| Distance Matrix (100 samples) | 500s | 15s | 33x |
| DMP Detection (1M positions) | 45 min | 3 min | 15x |
| Binary Search (20 iterations) | 60 min | 5 min | 12x |
| Classification (100 samples) | 10 min | 1 min | 10x |

### Complete Pipeline (Chr1, CG context)

| Configuration | Time | Speedup |
|---------------|------|---------|
| CPU-only | 130 min | 1x |
| Single GPU | 11 min | 11.8x |
| Multi-GPU (4x) | 3 min | 43x |

## Examples

### Example 1: Complete Binary Classification

See [MethylPipeline Integration Documentation](docs/METHYLPIPELINE_COMPREHENSIVE_DOCUMENTATION.md#end-to-end-examples) for complete examples.

### Example 2: Multi-Chromosome Analysis

```bash
# Process all chromosomes in parallel (one config per chromosome)
for chrom in 1 2 3 X; do
    CUDA_VISIBLE_DEVICES=$((chrom % 4)) \
    python -m methyl_modeler.cli configs/chr${chrom}-CG.json &
done
wait
```

### Example 3: Quality Control Pipeline

```python
# 1. Cluster all samples for QC
from methyl_cluster import MethylCluster, MethylClusterConfig

config = MethylClusterConfig(
    samples=all_sample_paths,
    chrom='1',
    ctx='CG',
    clustering_method='hdbscan',
    output_dir='/output/qc'
)

result = MethylCluster(config).run()

# 2. Remove outliers
outliers = [s for s, label in result['cluster_assignments'].items() if label == -1]
good_samples = [s for s in all_sample_paths if s not in outliers]

# 3. Create centroids without outliers
from methyl_centroid import MethylCentroid

centroid = MethylCentroid(
    add_samples=good_samples,
    chrom='1',
    ctx='CG',
    centroid_output_path='/centroids/qc_clean'
).build_centroid()
```

## Configuration Management

All analyses use JSON configuration files for reproducibility:

```json
{
  "study_name": "Healthy vs Cancer CG Methylation",
  "centroid1_path": "/centroids/healthy/chr1-CG.h5",
  "centroid2_path": "/centroids/cancer/chr1-CG.h5",
  "centroid1_name": "Healthy",
  "centroid2_name": "Cancer",
  "chrom": "1",
  "ctx": "CG",
  "fdr_threshold": 0.01,
  "min_delta_mean": 0.1,
  "target_balanced_accuracy": 0.95,
  "output_dir": "/output/analysis",
  "use_gpu": true
}
```

Run with:
```bash
./packages/methylmodeler/modeler /configs/analysis.json
```

## Troubleshooting

### GPU Not Detected

```bash
# Check NVIDIA driver
nvidia-smi

# Install CuPy for your CUDA version
pip install cupy-cuda11x

# Verify detection
python -c "from methyl_utils import is_gpu_available; print(is_gpu_available())"
```

### Out of Memory

```python
# Clean up GPU memory
from methyl_utils import cleanup_gpu_memory
cleanup_gpu_memory()

# Or disable GPU
config.use_gpu = False
```

### No DMPs Found

```python
# Relax filtering criteria
config.fdr_threshold = 0.05  # Instead of 0.01
config.min_delta_mean = 0.05  # Instead of 0.1
```

See individual package documentation for detailed troubleshooting guides.

## Project Structure

```
MethylPipeline/
├── packages/                    # Python packages
│   ├── methylutils/            # Core utilities + GPU helpers
│   ├── methylcentroid/         # Centroid generation
│   ├── methylcluster/          # Sample clustering/QC
│   ├── methylmodeler/          # DMP detection + model packaging
│   ├── methylclassifier/       # Classification CLI/API
│   ├── methylmapper/           # Gene mapping + enrichment hooks
│   └── methylenricher/         # Functional enrichment CLI
├── docker/                      # Container definitions
│   ├── Dockerfile
│   └── docker-compose.yml
├── scripts/                     # Setup and automation helpers
│   ├── setup_dev.sh
│   ├── setup_host.sh
│   ├── setup_prod.sh
│   ├── run_container.sh
│   └── install_all.sh
├── requirements-pipeline.txt    # Pipeline-level Python deps
├── requirements-gpu.txt         # GPU/CUDA deps (CUDA 12.x)
├── docs/                        # Pipeline-level documentation
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT.md
│   ├── PRODUCTION.md
│   └── METHYLPIPELINE_COMPREHENSIVE_DOCUMENTATION.md
├── mkdocs.yml                   # Documentation site navigation
├── pyproject.toml               # Repo-level tooling config
└── README.md                    # This file
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Update documentation
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2024 MethylPipeline Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Citation

```bibtex
@software{methylpipeline2024,
  title={MethylPipeline: Unified Genomics Pipeline for Methylation Analysis},
  author={MethylPipeline Contributors},
  year={2024},
  url={https://github.com/yourusername/MethylPipeline},
  note={Comprehensive toolkit for methylation-based biomarker discovery and classification with GPU acceleration}
}
```

## Support

- **Documentation**: See links above for comprehensive guides
- **Issues**: [GitHub Issues](https://github.com/yourusername/MethylPipeline/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/MethylPipeline/discussions)

---

**MethylPipeline** - Empowering genomics research with statistical rigor, Bayesian methods, and GPU acceleration.
