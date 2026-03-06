# Architecture Documentation

This document describes the architecture of the MethylPipeline system.

## System Overview

MethylPipeline is a monorepo containing 10 integrated Python packages for methylation-based genomic analysis: MethylUtils, MethylCentroid, MethylCluster, MethylDetector, MethylClassifier, MethylMapper, MethylEnricher, MethylAlignmentQC, MethylPredictor, and MethylValidation. The system uses a single data-driven centroid type and ECDF-based comparison for DMP detection, with optional Explorer CLIs for centroid and detector tuning. It is designed to leverage GPU acceleration for high-performance computation on large-scale genomic datasets.

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

#### 3. MethylCluster

**Purpose**: Perform exploratory clustering and QC on methylation samples

**Key Features**:
- HDBSCAN, hierarchical, and centroid-based clustering engines
- Forced group assignments, soft membership probabilities
- GPU-accelerated distance matrices via MethylUtils
- Visualization outputs (heatmaps, dendrograms, cluster trees)

**Dependencies**:
- methylutils
- numpy / pandas / scipy
- scikit-learn
- hdbscan

#### 4. MethylModeler

**Purpose**: Detect differentially methylated positions and package classifiers

**Key Features**:
- Storey's q-value FDR with biological filter (min_effect_size)
- **Biological filter**: Keep DMPs with **effect_size ≥ min_effect_size** when min_effect_size is set. effect_size = 1 − BC (separation) in [0, 1].
- Multi-context weighting and Balanced Accuracy optimization
- Synthetic or real-sample validation with FeatureCuts/Bayesian optimization
- Classifier packaging for direct consumption by MethylClassifier

**Why Bhattacharyya for “overlap”? (biologist’s view)**  
A good DMP has (1) **large |delta_mean|** (means of the two groups far apart) and (2) **small overlap** (little “confusion range” where both distributions have mass). We need a number for “overlap” that is 0 when the distributions don’t overlap and 1 when they are identical. The **Bhattacharyya coefficient** does exactly that:

- **BC = ∫ √(p(x) q(x)) dx** over the methylation axis. For two Beta (or Normal) distributions this has a closed form. BC ∈ [0, 1]: **BC = 0** ⇒ no overlap (perfect separation), **BC = 1** ⇒ identical distributions (total confusion). So we **define overlap = BC**.
- **BD = −ln(BC)** is the Bhattacharyya distance. It’s a one-to-one transform: small overlap (BC → 0) ⇒ BD large; large overlap (BC → 1) ⇒ BD → 0. We often store BD (numerically stable when BC is tiny) and convert back with **BC = exp(−BD)** for filters and export.

**Effect size and min_effect_size**  
**effect_size = 1 − BC** (separation), **bounded in [0, 1]**: 0 = identical distributions, 1 = no overlap. Config **min_effect_size** (in [0, 1]) keeps DMPs with effect_size ≥ min_effect_size.

**Dependencies**:
- methylutils
- numpy / pandas / cupy
- h5py

#### 5. MethylClassifier

**Purpose**: Classify samples using packaged probabilistic models

**Key Features**:
- Batch classification with posterior probabilities
- Temperature scaling and optional Platt calibration
- Availability-mask handling for missing CpGs
- Multi-class models (healthy + multiple cancers)
- Hybrid Beta/BMM likelihoods when BMM centroids are available
- Command-line interface plus Python API

**Dependencies**:
- methylutils
- numpy / scipy

#### 6. MethylMapper

**Purpose**: Map DMPs to genes using genomic coordinates

**Key Features**:
- Genomic interval operations
- Azure SQL database integration for gene annotations
- Distance-based mapping
- Regulatory region identification

**Dependencies**:
- methylutils
- bedtools/pybedtools (local mode)
- pyodbc/pymssql (Azure SQL mode)
- External APIs (Grok, Open Targets, optional DisGeNET) for disease context

#### 7. MethylEnricher

**Purpose**: Perform gene set enrichment analysis

**Key Features**:
- Pathway enrichment
- GO term enrichment
- Statistical significance testing
- Direct consumption of MethylMapper CSV/TSV outputs

**Dependencies**:
- gseapy (Enrichr API)
- pandas / numpy

## Data Flow

### Typical Pipeline Flow

```
1. Raw Data (HDF5)
   ↓
2. MethylCentroid (group representatives)
   ↓
3. MethylCluster (QC & clustering, optional)
   ↓
4. MethylModeler (DMP detection + model packaging)
   ↓
5. MethylClassifier (sample inference)
   ↓
6. MethylMapper (gene mapping + disease enrichment)
   ↓
7. MethylEnricher (functional enrichment)
```

### Pipeline configuration (project config)

A single **project config** (JSON) defines the two cohorts, the project root, and optional shared parameters. All step configs are derived from it using **Pydantic** models (no raw dict configs). Paths follow a fixed convention so each project has one folder and step outputs live in fixed subdirs.

**Path convention**: `output_base` is a global output folder; each project has a subfolder `{output_base}/{project_name}`. All step outputs live under that project folder:

- **project root**: `{output_base}/{project_name}`
- **centroids**: `{project_root}/centroids/{group1.label}` and `{project_root}/centroids/{group2.label}`
- **detection**: `{project_root}/detection`
- **mapper**: `{project_root}/mapper`
- **enricher**: `{project_root}/enricher`
- **classifier**: `{project_root}/classifier`
- **alignment_qc**: `{project_root}/alignment_qc` (one JSON per sample for MethylAlignmentQC)

**Project config fields** (see `methyl_utils.pipeline_config.ProjectConfig`):

- `project_name`: identifier and subfolder name (e.g. `"PCa_vs_Healthy"`)
- `output_base`: global output directory; step outputs go under `{output_base}/{project_name}`
- `group1` / `group2`: each has `label` and `sample_paths` (list of sample dirs or paths to list files)
- Optional: `chromosomes`, `contexts`, `path_remap` (prefix replacement when samples move, e.g. to NAS)

**Using `--project`**: Each tool can be run with `--project project.json` (and optional `--step-override step.json`). A resolver builds that step’s Pydantic config from the project and overrides. Standalone step configs (no `--project`) still work.

| Tool | Project usage |
|------|----------------|
| **MethylCentroid** | `--project project.json --group group1` (or `group2`); optional `--step-override`. Output goes to `{output_base}/{project_name}/centroids/{group1|group2.label}`. |
| **MethylDetector** | `--project project.json`; optional `--step-override`. Writes to `{output_base}/{project_name}/detection`. |
| **MethylMapper** (bedtools) | `--project project.json`; optional `--step-override`. Input CSVs from `detection_dir`, output to `mapper_dir`. Still requires `--gtf`. |
| **MethylEnricher** | `--project project.json`; optional `--step-override`. Input = mapper combined CSV, output to `enricher_dir`. |
| **MethylClassifier** | `--project project.json`; optional `--step-override`. Output to `classifier_dir`. |
| **MethylAlignmentQC** | `--project project.json`; optional `--step-override`. Output to `{output_base}/{project_name}/alignment_qc` (one JSON per sample). |

CLI commands: `methyl-centroid`, `methyl-centroid-explorer`, `methyl-detector`, `methyl-detector-explorer`, `methyl-mapper`, `methyl-enricher`, `methyl-classifier`, `methyl-predictor`, `methyl-validation`, `methyl-qc` / `methyl-alignment-qc`.

Shared types and loader live in **MethylUtils**: `ProjectConfig`, `GroupConfig`, `DerivedPaths`, `load_project()`.

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

- **Base Image**: nvidia/cuda:13.0.0-devel-ubuntu22.04
- **Python**: 3.10 in virtual environment
- **Mount**: Project directory mounted at `/workspace`
- **Install Mode**: Editable (`pip install -e .`)

### Production Container

- **Base Image**: nvidia/cuda:13.0.0-devel-ubuntu22.04
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

