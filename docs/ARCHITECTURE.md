# Architecture Documentation

This document describes the architecture of the MethylPipeline system.

## System Overview

MethylPipeline is a monorepo containing 7 integrated Python packages for methylation-based genomic analysis. The system is designed to leverage GPU acceleration for high-performance computation on large-scale genomic datasets.

## Component Architecture

### Package Hierarchy

```
┌─────────────────────────────────────────┐
│         Application Layer               │
│  ┌──────────┐  ┌──────────┐            │
│  │Classifier│  │Enricher  │            │
│  └────┬─────┘  └────┬─────┘            │
│       │             │                   │
│  ┌────┴─────┐  ┌───┴──────┐  ┌────────┐│
│  │ Trainer  │  │  Mapper  │  │Detector││
│  └────┬─────┘  └────┬─────┘  └───┬────┘│
│       │             │             │     │
│  ┌────┴─────────────┴─────────────┴───┐ │
│  │        Centroid Generation         │ │
│  └────────────────┬───────────────────┘ │
│                   │                     │
└───────────────────┼─────────────────────┘
                    │
          ┌─────────┴─────────┐
          │   MethylUtils     │
          │  (Core Library)   │
          └───────────────────┘
                    │
          ┌─────────┴─────────┐
          │  GPU/CUDA Layer   │
          │  CuPy, RAPIDS     │
          └───────────────────┘
```

### Core Components

#### 1. MethylUtils (Core Library)

**Purpose**: Foundational utilities and GPU-optimized operations

**Key Features**:
- Logging infrastructure with GPU-aware logging
- GPU memory management and monitoring
- HDF5 file I/O with compression support
- MethylSample class for genomic data representation
- Statistical functions optimized for GPU (CuPy)
- Mathematical operations with automatic CPU/GPU fallback

**Dependencies**:
- CuPy (GPU arrays)
- RAPIDS cuDF (GPU DataFrames)
- h5py (HDF5 support)
- nvidia-ml-py (GPU monitoring)

**Module Structure**:
```
methyl_utils/
├── __init__.py
├── logging.py          # Logging utilities
├── gpu_utils.py        # GPU management
├── hdf5_utils.py       # HDF5 I/O
├── sample.py           # MethylSample class
├── stats.py            # Statistical functions
└── math_ops.py         # Math operations
```

#### 2. MethylCentroid

**Purpose**: Generate representative centroids for sample groups

**Key Features**:
- Compute mean methylation profiles
- Handle missing data
- GPU-accelerated aggregation

**Dependencies**:
- methylutils

#### 3. MethylDetector

**Purpose**: Detect differentially methylated positions (DMPs)

**Key Features**:
- Statistical testing (t-test, Mann-Whitney U)
- Effect size calculations (Cohen's d, Hedges' g)
- Multiple testing correction (FDR, Bonferroni)
- Batch processing support
- GPU-accelerated computation

**Dependencies**:
- methylutils
- scipy (statistical tests)

#### 4. MethylMapper

**Purpose**: Map DMPs to genes using genomic coordinates

**Key Features**:
- Genomic interval operations
- Azure SQL database integration for gene annotations
- Distance-based mapping
- Regulatory region identification

**Dependencies**:
- methylutils
- pyodbc/pymssql (SQL connectivity)

#### 5. MethylTrainer

**Purpose**: Train machine learning models for classification

**Key Features**:
- Feature selection
- Model training (Random Forest, SVM, Neural Networks)
- Cross-validation
- Model persistence
- GPU-accelerated training where possible

**Dependencies**:
- methylutils
- scikit-learn
- torch (for neural networks)

#### 6. MethylClassifier

**Purpose**: Classify samples using trained models

**Key Features**:
- Batch classification
- Confidence scoring
- Model ensemble support
- Command-line interface

**Dependencies**:
- methylutils
- methyltrainer

#### 7. MethylEnricher

**Purpose**: Perform gene set enrichment analysis

**Key Features**:
- Pathway enrichment
- GO term enrichment
- Statistical significance testing
- Visualization support

**Dependencies**:
- methylutils
- scipy
- matplotlib

## Data Flow

### Typical Pipeline Flow

```
1. Raw Data (HDF5)
   ↓
2. MethylDetector (DMP Detection)
   ↓
3. MethylMapper (Gene Mapping)
   ↓
4. MethylEnricher (Enrichment Analysis)
   
Parallel:
5. MethylCentroid → MethylTrainer → MethylClassifier
```

### Data Formats

#### HDF5 Structure

```
sample.h5
├── /metadata
│   ├── sample_id
│   ├── tissue_type
│   └── platform
├── /methylation
│   ├── beta_values  [N x M array]
│   ├── chromosomes  [N array]
│   └── positions    [N array]
└── /quality
    └── detection_p  [N x M array]
```

#### MethylSample Object

```python
class MethylSample:
    sample_id: str
    beta_values: cupy.ndarray  # GPU array
    chromosomes: cupy.ndarray
    positions: cupy.ndarray
    metadata: dict
```

## GPU Architecture

### GPU Memory Management

The system implements a hierarchical memory management strategy:

1. **Automatic Detection**: Check GPU availability at runtime
2. **Memory Pools**: Use CuPy memory pools for efficient allocation
3. **Chunked Processing**: Process data in chunks to fit GPU memory
4. **Automatic Fallback**: Fall back to CPU if GPU memory insufficient

### GPU Optimization Patterns

```python
# Pattern 1: Automatic GPU/CPU fallback
def compute_stats(data):
    try:
        import cupy as cp
        gpu_data = cp.asarray(data)
        return cp.mean(gpu_data, axis=0)
    except (ImportError, cp.cuda.memory.OutOfMemoryError):
        import numpy as np
        return np.mean(data, axis=0)

# Pattern 2: Chunked processing
def process_large_dataset(data, chunk_size=10000):
    results = []
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i+chunk_size]
        result = process_chunk_gpu(chunk)
        results.append(result)
    return concatenate_results(results)

# Pattern 3: Context manager for GPU memory
with gpu_memory_context():
    # GPU operations here
    result = heavy_gpu_computation(data)
# Memory freed automatically
```

## Container Architecture

### Development Container

- **Base Image**: nvidia/cuda:12.8.0-devel-ubuntu22.04
- **Python**: 3.10 in virtual environment
- **Mount**: Project directory mounted at `/workspace`
- **Install Mode**: Editable (`pip install -e .`)

### Production Container

- **Base Image**: nvidia/cuda:12.8.0-devel-ubuntu22.04
- **Python**: 3.10 in virtual environment
- **Install Mode**: Regular (`pip install .`)
- **Packages**: Baked into image
- **Health Check**: Automated CUDA availability check

### Volume Structure

Development:
```
Volumes:
  /home/ubuntu/MethylPipeline → /workspace
  /home/ubuntu/working_dir → /home/ubuntu/working_dir
  /home/ubuntu/Work → /home/ubuntu/Work
```

Production:
```
Volumes:
  /home/ubuntu/working_dir → /home/ubuntu/working_dir
  /home/ubuntu/Work → /home/ubuntu/Work
Note: Code is in container, not mounted
```

## Performance Considerations

### GPU Acceleration

Operations optimized for GPU:
- Matrix operations (CuPy)
- Statistical computations (CuPy)
- DataFrame operations (RAPIDS cuDF)
- Parallel processing (CUDA kernels)

### Memory Optimization

- Lazy loading of large HDF5 files
- Chunked processing for genome-wide data
- Memory-mapped arrays for large datasets
- Automatic garbage collection

### I/O Optimization

- HDF5 with compression (zstd, gzip)
- Parallel I/O where possible
- Caching frequently accessed data
- Batch operations to minimize I/O

## Scalability

### Single Machine

- GPU: Up to 96GB GPU memory (GH200)
- CPU: 16+ vCPU for parallel preprocessing
- Memory: 128GB+ RAM recommended
- Storage: NVMe SSD for fast I/O

### Multi-Machine (Future)

Considerations for scaling:
- Distributed task queue (Celery, Dask)
- Shared storage (NFS, GlusterFS, Ceph)
- Load balancing
- Container orchestration (Kubernetes)

## Security

### Container Isolation

- Non-root user (ubuntu, UID 999)
- Limited system access
- Network isolation options
- Resource limits via cgroups

### Data Security

- Encrypted volumes for sensitive data
- Secure database connections (SSL)
- Audit logging
- Access control

## External Dependencies

### HPC/Commercial Applications

Not included in this monorepo:
- Preprocessing tools (run on separate HPC infrastructure)
- Commercial genomics platforms
- C-based alignment tools

These are independent and interface via:
- Shared file system
- Standardized file formats (HDF5, VCF, BED)

### Databases

- Azure SQL Server (gene annotations, mapping)
- Connection via pyodbc/pymssql
- Configuration via environment variables

## Monitoring and Observability

### Logging

Centralized logging via MethylUtils:
- Structured logging (JSON)
- GPU metrics in logs
- Performance metrics
- Error tracking

### Metrics

Key metrics to monitor:
- GPU utilization
- GPU memory usage
- Processing throughput
- Error rates

### Health Checks

Container health checks:
- CUDA availability
- Python import tests
- GPU memory check

## Future Considerations

### Planned Enhancements

1. **Distributed Computing**: Dask integration for multi-GPU
2. **Real-time Processing**: Streaming data support
3. **Web Interface**: Flask/FastAPI for web access
4. **API Gateway**: RESTful API for remote access
5. **Cloud Deployment**: AWS/Azure/GCP support

### Known Limitations

1. Single GPU per container (multi-GPU requires code changes)
2. Limited to Linux (CUDA requirement)
3. HDF5 file locking issues with NFS (use HDF5_USE_FILE_LOCKING=FALSE)
4. CuPy compilation cache requires persistent storage

