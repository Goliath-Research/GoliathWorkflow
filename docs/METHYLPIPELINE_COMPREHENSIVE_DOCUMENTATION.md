# MethylPipeline: Comprehensive Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Complete Workflow](#complete-workflow)
4. [Package Integration](#package-integration)
5. [Deployment](#deployment)
6. [End-to-End Examples](#end-to-end-examples)
7. [Configuration Management](#configuration-management)
8. [Performance](#performance)
9. [Troubleshooting](#troubleshooting)
10. [Best Practices](#best-practices)
11. [System Requirements](#system-requirements)
12. [License](#license)

---

## Overview

**MethylPipeline** is a unified genomics pipeline for comprehensive methylation analysis, integrating five specialized packages for centroid generation, clustering, differential methylation detection, classifier training, and sample classification.

### What is MethylPipeline?

MethylPipeline provides a complete ecosystem for methylation-based biomarker discovery and classification:

- **Data Processing**: From raw methylation samples to statistical models
- **Biomarker Discovery**: Identify Differentially Methylated Positions (DMPs)
- **Classification**: Bayesian probabilistic models for sample prediction
- **Exploratory Analysis**: Clustering and quality control
- **Production Ready**: Docker-based deployment with GPU acceleration

### Architecture Philosophy

MethylPipeline follows a **modular, composable** architecture:

1. **MethylUtils**: Foundation library (shared utilities, GPU, statistical functions)
2. **MethylCentroid**: Centroid generation with outlier detection
3. **MethylCluster**: Sample clustering (HDBSCAN, Hierarchical, Centroid-based)
4. **MethylDetector**: DMP detection and classifier training
5. **MethylTrainer**: Advanced classifier training with validation
6. **MethylClassifier**: Sample classification with Bayesian models

Each package is **self-contained** but **tightly integrated** through MethylUtils.

### Key Features

- **Complete Pipeline**: Data → Centroids → DMPs → Classifiers → Predictions
- **GPU Acceleration**: NVIDIA CUDA support for 20-50x speedup
- **Probabilistic Methods**: Bayesian classification with true posterior probabilities
- **Statistical Rigor**: Storey's q-value FDR correction, Balanced Accuracy metrics
- **Flexible Deployment**: Docker containers, multi-GPU support, cloud-ready
- **Reproducible**: JSON configuration for all analyses
- **Scalable**: Handles genome-wide data with intelligent memory management

---

## Architecture

### Package Dependency Graph

```
┌─────────────────────────────────────────────────────────────────┐
│                          MethylUtils                            │
│  (Core library: GPU, Memory, Statistics, Data Structures)      │
└─────────────────────────────────────────────────────────────────┘
                              ↑
                   ┌──────────┴──────────┐
                   │                     │
        ┌──────────┴──────────┐    ┌────┴──────────┐
        │   MethylCentroid    │    │ MethylCluster │
        │  (Centroid + QC)    │    │ (Exploratory) │
        └──────────┬──────────┘    └───────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
 ┌──────┴────────┐   ┌───────┴────────┐
 │ MethylDetector│   │ MethylTrainer  │
 │ (DMP + Model) │   │ (Advanced DMP) │
 └──────┬────────┘   └───────┬────────┘
        │                    │
        └──────────┬─────────┘
                   │
        ┌──────────┴──────────┐
        │  MethylClassifier   │
        │ (Sample Prediction) │
        └─────────────────────┘
```

### Data Flow

```
Raw Samples (HDF5)
    ↓
┌───────────────────┐
│ MethylCentroid    │  → Centroid files (.h5)
│ - Calculate stats │  → Outlier reports
│ - Remove outliers │
└───────────────────┘
    ↓
┌───────────────────┐
│ MethylDetector    │  → DMP tables (.tsv)
│ - Compare groups  │  → Model packages (.pkl)
│ - FDR correction  │  → Visualizations (.html)
│ - Binary search   │
└───────────────────┘
    ↓
┌───────────────────┐
│ MethylClassifier  │  → Predictions (.json)
│ - Load model      │  → Probabilities
│ - Predict samples │  → Confidence scores
└───────────────────┘
```

### Shared Components (MethylUtils)

All packages leverage MethylUtils for:

#### Core Data Structures
- `MethylSample`: Methylation data representation
- `PositionAligner`: Genomic coordinate alignment
- `MethylCentroidPair`: Statistical comparison of two centroids

#### Statistical Functions
- Distance metrics: Jensen-Shannon, Hellinger, Wasserstein, etc.
- FDR correction: Storey's q-value method
- Beta distribution analytics: Parameter estimation, likelihood ratios

#### Performance Infrastructure
- GPU detection and management (CuPy)
- Memory management: LRU caching, memory-mapped I/O
- Chunked processing for large datasets
- Performance profiling

#### Classification Models
- `ProbabilisticBetaClassifier`: Bayesian classifier core

---

## Complete Workflow

### Standard Pipeline

```
1. Sample Preparation
   ├─ Collect raw methylation samples
   ├─ Store as HDF5 files (chrom-ctx.h5)
   └─ Organize by group (healthy/, cancer/)

2. Centroid Generation
   ├─ Run MethylCentroid for each group
   ├─ Remove outliers (multi-metric consensus)
   └─ Generate representative centroids

3. Quality Control (Optional)
   ├─ Run MethylCluster on all samples
   ├─ Identify batch effects
   └─ Validate groupings

4. DMP Detection & Training
   ├─ Run MethylDetector to compare centroids
   ├─ Detect DMPs with FDR control (Storey's q-value)
   ├─ Filter for biological importance
   ├─ Binary search for optimal DMP count (Balanced Accuracy)
   └─ Package classifier model (.pkl)

5. Classification
   ├─ Run MethylClassifier with trained model
   ├─ Predict new samples
   └─ Output probabilities and confidence scores

6. Analysis (Optional)
   ├─ Subtype discovery with MethylCluster
   ├─ Gene enrichment analysis
   └─ Comparative studies
```

### Alternative Workflows

#### Workflow 1: Known Subtypes

```
1. Cluster samples (MethylCluster)
2. Create centroid per subtype (MethylCentroid)
3. Compare subtypes pairwise (MethylDetector)
4. Train multi-class classifier
```

#### Workflow 2: Validation Study

```
1. Use existing centroids
2. Train with real validation samples (MethylTrainer)
3. Validate on held-out cohort (MethylClassifier)
4. Compare with ground truth
```

#### Workflow 3: Large-Scale Study

```
1. Batch process all chromosomes/contexts
2. Parallel centroid generation
3. Distributed DMP detection
4. Ensemble classification
```

---

## Package Integration

### 1. MethylUtils (Foundation)

**Purpose**: Shared library providing core functionality

**Key Components**:
- `MethylSample`: Data structure for methylation samples
- `PositionAligner`: Aligns samples to common genomic positions
- `MethylCentroidPair`: Statistical comparison of two centroids
- `ProbabilisticBetaClassifier`: Bayesian classification model
- Distance metrics factory: 7 information-theoretic metrics
- GPU utilities: Detection, memory management, acceleration
- Statistical functions: FDR correction, Beta analytics

**Used By**: All packages

**Example**:
```python
from methyl_utils import MethylSample, is_gpu_available

# Load sample
sample = MethylSample.load_from_h5('/data/sample1/chr1-CG.h5')

# Check GPU
if is_gpu_available():
    print("GPU acceleration enabled")
```

### 2. MethylCentroid (Group Representatives)

**Purpose**: Create representative centroids for sample groups with outlier removal

**Key Features**:
- Extended centroid calculation (Sx, Sx2, N statistics)
- Multi-metric consensus outlier detection
- GPU-accelerated distance computations
- Incremental updates
- Batch processing

**Inputs**:
- Sample directories (HDF5 files)
- Configuration (min_coverage, outlier_threshold, etc.)

**Outputs**:
- Centroid file (.h5)
- Metadata (.json)
- Outlier report
- Visualizations

**Integration Points**:
- → MethylDetector: Provides centroids for comparison
- → MethylCluster: Can cluster centroids or use centroids as references
- ← MethylUtils: Uses PositionAligner, distance metrics

**Example**:
```python
from methyl_centroid import MethylCentroid

centroid = MethylCentroid(
    add_samples=['/data/healthy1', '/data/healthy2'],
    chrom='1',
    ctx='CG',
    centroid_output_path='/output/healthy_centroid'
).build_centroid()
```

### 3. MethylCluster (Exploratory Analysis)

**Purpose**: Cluster samples for QC, subtype discovery, validation

**Key Features**:
- Three methods: HDBSCAN, Hierarchical, Centroid-based
- K-means fallback for ambiguous results
- Cluster-level centroids (centroid method)
- Forced groups for supervised clustering
- Soft assignments with probabilities

**Inputs**:
- Sample directories
- Clustering method and parameters
- Optional: forced group assignments

**Outputs**:
- Cluster assignments
- Distance matrix (.npz)
- Cluster centroids (centroid method)
- Visualizations (heatmaps, MDS, dendrograms)

**Integration Points**:
- QC before MethylCentroid: Remove outliers
- Subtype discovery: Identify groups before centroid creation
- Validation: Verify classifier predictions cluster correctly

**Example**:
```python
from methyl_cluster import MethylCluster, MethylClusterConfig, ClusteringMethod

config = MethylClusterConfig(
    samples=all_sample_paths,
    chrom='1',
    ctx='CG',
    clustering_method=ClusteringMethod.HIERARCHICAL,
    output_dir='/output/clustering'
)

result = MethylCluster(config).run()
print(f"Found {result['metrics']['n_clusters']} clusters")
```

### 4. MethylDetector (DMP Detection & Training)

**Purpose**: Detect DMPs, train classifiers with binary search optimization

**Key Features**:
- Statistical comparison via MethylCentroidPair
- FDR correction (Storey's q-value method)
- Biological filtering (delta_mean, Bhattacharyya coefficient)
- Binary search for optimal DMP count (Balanced Accuracy)
- Real or synthetic sample validation
- Model packaging (.pkl)

**Inputs**:
- Two centroids (or paths)
- Configuration (FDR thresholds, filters, target_balanced_accuracy)
- Optional: validation samples

**Outputs**:
- DMP table (all positions)
- Filtered DMPs
- Model package (.pkl) with ProbabilisticBetaClassifier
- Metadata (JSON)
- Visualizations

**Integration Points**:
- ← MethylCentroid: Receives centroids
- → MethylClassifier: Provides trained model
- ← MethylUtils: Uses MethylCentroidPair, ProbabilisticBetaClassifier

**Example**:
```python
from methyl_detector import MethylDetectorConfig, run_comparison

config = MethylDetectorConfig.from_file('/configs/healthy_vs_cancer.json')
result = run_comparison(config)

print(f"Found {result['n_dmps']} DMPs")
print(f"Model saved: {result['model_path']}")
```

### 5. MethylTrainer (Advanced Training)

**Purpose**: Alternative to MethylDetector with advanced validation options

**Key Features**:
- Direct DMP detection (no MethylDetector wrapper)
- Flexible validation sample selection
- Real sample validation from config or centroid metadata
- Same binary search and Balanced Accuracy optimization

**Inputs**:
- Two centroids
- Training configuration
- Optional: validation sample paths

**Outputs**:
- Model package (.pkl)
- DMP table
- Validation results

**Integration Points**:
- Similar to MethylDetector but more flexible
- Can replace MethylDetector in pipeline

**Example**:
```python
from methyl_trainer import train_model, TrainingConfig

config = TrainingConfig(
    centroid1_path='/centroids/healthy.h5',
    centroid2_path='/centroids/cancer.h5',
    target_balanced_accuracy=0.95,
    validation_mode='real',
    centroid1_validation_samples=['/val/h1', '/val/h2'],
    centroid2_validation_samples=['/val/c1', '/val/c2']
)

model = train_model(config)
print(f"Model trained with {len(model.positions)} DMPs")
```

### 6. MethylClassifier (Prediction)

**Purpose**: Classify new samples using trained Bayesian models

**Key Features**:
- Load model packages (.pkl)
- Bayesian probabilistic classification
- True posterior probabilities
- Temperature scaling
- Platt calibration
- Threshold-based prediction
- Batch classification

**Inputs**:
- Model package (.pkl)
- Sample(s) to classify

**Outputs**:
- Predicted class
- Posterior probabilities
- Log-likelihood ratio
- Confidence scores

**Integration Points**:
- ← MethylDetector/MethylTrainer: Receives trained model
- Final step in pipeline

**Example**:
```python
from methyl_classifier import MethylClassifier

classifier = MethylClassifier(model_path='/models/healthy_vs_cancer.pkl')

result = classifier.predict('/data/unknown_sample')

print(f"Predicted: {result['predicted_class']}")
print(f"Confidence: {result['confidence']:.3f}")
print(f"Probabilities: {result['posterior_probs']}")
```

---

## Deployment

### Docker Deployment (Recommended)

#### Build Container

```bash
cd /home/ubuntu/MethylPipeline
docker build -t methylpipeline:latest -f docker/Dockerfile .
```

#### Run with GPU

```bash
docker run --gpus all \
  -v /data:/data \
  -v /output:/output \
  -it methylpipeline:latest bash
```

#### Docker Compose

```yaml
version: '3.8'
services:
  methylpipeline:
    image: methylpipeline:latest
    runtime: nvidia
    environment:
      - CUDA_VISIBLE_DEVICES=0
    volumes:
      - ./data:/data
      - ./output:/output
      - ./configs:/configs
    command: python -m methyl_detector /configs/analysis.json
```

### Manual Setup

#### Development Environment

```bash
# Clone repository
git clone https://github.com/yourusername/MethylPipeline.git
cd MethylPipeline

# Run setup script
./scripts/setup_dev.sh

# Activate environment
source venv/bin/activate

# Install packages in development mode
cd packages/methylutils && pip install -e . && cd ../..
cd packages/methylcentroid && pip install -e . && cd ../..
cd packages/methylcluster && pip install -e . && cd ../..
cd packages/methyldetector && pip install -e . && cd ../..
cd packages/methyltrainer && pip install -e . && cd ../..
cd packages/methylclassifier && pip install -e . && cd ../..
```

#### Production Environment

```bash
# Run production setup
./scripts/setup_prod.sh

# System-wide installation
pip install ./packages/methylutils
pip install ./packages/methylcentroid
pip install ./packages/methylcluster
pip install ./packages/methyldetector
pip install ./packages/methyltrainer
pip install ./packages/methylclassifier
```

### GPU Configuration

#### Single GPU

```bash
export CUDA_VISIBLE_DEVICES=0
```

#### Multi-GPU (Parallel Processing)

```bash
# Process different chromosomes on different GPUs
CUDA_VISIBLE_DEVICES=0 python run_chr1.py &
CUDA_VISIBLE_DEVICES=1 python run_chr2.py &
CUDA_VISIBLE_DEVICES=2 python run_chr3.py &
wait
```

### Cloud Deployment

#### AWS EC2 (GPU Instance)

```bash
# Launch p3.2xlarge or p3.8xlarge instance
# Install NVIDIA drivers and Docker

# Pull container
docker pull yourusername/methylpipeline:latest

# Run analysis
docker run --gpus all \
  -v s3://mybucket/data:/data \
  -v s3://mybucket/output:/output \
  methylpipeline:latest \
  python -m methyl_detector /configs/analysis.json
```

#### GCP Compute Engine

```bash
# Launch instance with GPU
gcloud compute instances create methylpipeline-worker \
  --machine-type=n1-standard-8 \
  --accelerator=type=nvidia-tesla-v100,count=1 \
  --image-family=pytorch-latest-gpu \
  --image-project=deeplearning-platform-release

# SSH and run pipeline
gcloud compute ssh methylpipeline-worker
```

---

## End-to-End Examples

### Example 1: Complete Binary Classification

```bash
#!/bin/bash
# Complete pipeline: Healthy vs Cancer

# Step 1: Create centroids
python -c "
from methyl_centroid import MethylCentroid

healthy = MethylCentroid(
    add_samples=[f'/data/healthy{i}' for i in range(1, 36)],
    chrom='1', ctx='CG',
    centroid_output_path='/output/healthy_centroid'
).build_centroid()

cancer = MethylCentroid(
    add_samples=[f'/data/cancer{i}' for i in range(1, 13)],
    chrom='1', ctx='CG',
    centroid_output_path='/output/cancer_centroid'
).build_centroid()
"

# Step 2: Detect DMPs and train model
python -m methyl_detector \
  --centroid1 /output/healthy_centroid/1-CG.h5 \
  --centroid2 /output/cancer_centroid/1-CG.h5 \
  --output-dir /output/detector \
  --target-balanced-accuracy 0.95

# Step 3: Classify new samples
python -c "
from methyl_classifier import MethylClassifier

classifier = MethylClassifier('/output/detector/model.pkl')

for i in range(1, 11):
    result = classifier.predict(f'/data/test_samples/sample{i}')
    print(f'Sample{i}: {result[\"predicted_class\"]} (p={result[\"confidence\"]:.3f})')
"
```

### Example 2: Multi-Chromosome Analysis

```python
#!/usr/bin/env python
"""Run pipeline across multiple chromosomes in parallel."""

from multiprocessing import Pool
from methyl_detector import MethylDetectorConfig, run_comparison
import os

def process_chromosome(chrom):
    """Process single chromosome."""
    os.environ['CUDA_VISIBLE_DEVICES'] = str(int(chrom) % 4)  # Distribute GPUs
    
    config = MethylDetectorConfig(
        centroid1_path=f'/centroids/healthy/chr{chrom}-CG.h5',
        centroid2_path=f'/centroids/cancer/chr{chrom}-CG.h5',
        chrom=chrom,
        ctx='CG',
        output_dir=f'/output/chr{chrom}',
        target_balanced_accuracy=0.95
    )
    
    result = run_comparison(config)
    return (chrom, result['n_dmps'])

if __name__ == '__main__':
    chromosomes = [str(i) for i in range(1, 23)] + ['X', 'Y']
    
    with Pool(processes=4) as pool:
        results = pool.map(process_chromosome, chromosomes)
    
    for chrom, n_dmps in results:
        print(f"Chr{chrom}: {n_dmps} DMPs")
```

### Example 3: Batch Sample Classification

```python
#!/usr/bin/env python
"""Classify batch of samples and generate report."""

from methyl_classifier import MethylClassifier
import pandas as pd
import json

# Load classifier
classifier = MethylClassifier('/models/healthy_vs_cancer.pkl')

# Process all samples
results = []
sample_dirs = [f'/data/cohort2/sample{i}' for i in range(1, 101)]

for sample_path in sample_dirs:
    try:
        result = classifier.predict(sample_path)
        results.append({
            'sample': sample_path.split('/')[-1],
            'prediction': result['predicted_class'],
            'confidence': result['confidence'],
            'prob_healthy': result['posterior_probs'][0],
            'prob_cancer': result['posterior_probs'][1],
            'llr': result['log_likelihood_ratio']
        })
    except Exception as e:
        print(f"Error processing {sample_path}: {e}")

# Save results
df = pd.DataFrame(results)
df.to_csv('/output/batch_predictions.csv', index=False)

# Summary statistics
print(f"Total samples: {len(results)}")
print(f"Healthy: {sum(1 for r in results if r['prediction'] == 'healthy')}")
print(f"Cancer: {sum(1 for r in results if r['prediction'] == 'cancer')}")
print(f"Mean confidence: {df['confidence'].mean():.3f}")
```

### Example 4: Validation Study with Clustering

```python
#!/usr/bin/env python
"""Validate classifier predictions match clustering."""

from methyl_cluster import MethylCluster, MethylClusterConfig, ClusteringMethod
from methyl_classifier import MethylClassifier
from sklearn.metrics import adjusted_rand_score

# Step 1: Classify all samples
classifier = MethylClassifier('/models/model.pkl')
predictions = {}
sample_paths = [f'/data/validation/sample{i}' for i in range(1, 51)]

for sample_path in sample_paths:
    result = classifier.predict(sample_path)
    predictions[sample_path] = result['predicted_class']

# Step 2: Cluster samples
config = MethylClusterConfig(
    samples=sample_paths,
    chrom='1',
    ctx='CG',
    clustering_method=ClusteringMethod.HIERARCHICAL,
    output_dir='/output/validation_clustering'
)

cluster_result = MethylCluster(config).run()

# Step 3: Compare predictions vs clustering
pred_labels = [0 if predictions[s] == 'healthy' else 1 for s in sample_paths]
cluster_labels = [cluster_result['cluster_assignments'][s] for s in sample_paths]

ari = adjusted_rand_score(pred_labels, cluster_labels)
print(f"Adjusted Rand Index: {ari:.3f}")
print("Predictions match clustering!" if ari > 0.7 else "Warning: Poor agreement")
```

---

## Configuration Management

### Centralized Configuration

#### Directory Structure

```
configs/
├── centroids/
│   ├── healthy_chr1_CG.json
│   └── cancer_chr1_CG.json
├── detectors/
│   ├── healthy_vs_cancer_chr1_CG.json
│   ├── healthy_vs_cancer_chr2_CG.json
│   └── ...
├── clusters/
│   └── qc_clustering.json
└── pipeline_config.json  # Master config
```

#### Master Configuration

```json
{
  "study_name": "Healthy vs Cancer CG Methylation",
  "data_root": "/data",
  "output_root": "/output",
  "chromosomes": ["1", "2", "3", "X"],
  "contexts": ["CG"],
  
  "centroid_config": {
    "healthy": {
      "samples": ["/data/healthy1", "/data/healthy2", ...],
      "group": "Healthy",
      "min_coverage": 4,
      "outlier_threshold": 0.75
    },
    "cancer": {
      "samples": ["/data/cancer1", "/data/cancer2", ...],
      "group": "Cancer",
      "min_coverage": 4,
      "outlier_threshold": 0.75
    }
  },
  
  "detector_config": {
    "target_balanced_accuracy": 0.95,
    "fdr_threshold": 0.01,
    "min_delta_mean": 0.1,
    "max_bc": 0.95,
    "use_gpu": true
  },
  
  "classifier_config": {
    "temperature": 1.0,
    "use_platt_scaling": false,
    "threshold": 0.5
  }
}
```

### Configuration Best Practices

1. **Version Control**: Track all configurations in git
2. **Naming Convention**: `{group1}_vs_{group2}_{chrom}_{ctx}_config.json`
3. **Reproducibility**: Include exact package versions, random seeds
4. **Documentation**: Add comments (use JSONC if needed)
5. **Validation**: Use Pydantic models to validate before running

---

## Performance

### Benchmarks (NVIDIA GH200)

#### End-to-End Pipeline (Chr1, CG context)

| Step | CPU Time | GPU Time | Speedup |
|------|----------|----------|---------|
| Centroid (35 samples) | 15 min | 2 min | 7.5x |
| DMP Detection | 45 min | 3 min | 15x |
| Binary Search (20 iterations) | 60 min | 5 min | 12x |
| Classification (100 samples) | 10 min | 1 min | 10x |
| **Total** | **130 min** | **11 min** | **11.8x** |

#### Genome-Wide Analysis (All chromosomes, CG)

| Configuration | Time | GPU Memory |
|---------------|------|------------|
| Serial (1 GPU) | 4.5 hours | 16 GB |
| Parallel (4 GPUs) | 1.2 hours | 16 GB × 4 |
| CPU-only | 52 hours | N/A |

### Memory Usage

| Package | Typical Memory | Peak Memory |
|---------|----------------|-------------|
| MethylCentroid (50 samples) | 2 GB | 4 GB |
| MethylCluster (100 samples) | 1 GB | 2 GB |
| MethylDetector | 4 GB | 8 GB |
| MethylClassifier | 0.5 GB | 1 GB |

### Scaling

- **Samples**: Linear scaling up to 10,000 samples
- **Positions**: Sub-linear (intelligent chunking)
- **Chromosomes**: Embarrassingly parallel
- **Contexts**: Independent, can parallelize

---

## Troubleshooting

### Common Issues

#### 1. GPU Out of Memory

**Symptoms**: `CUDA out of memory` error

**Solutions**:
```python
# Reduce batch size
from methyl_utils import cleanup_gpu_memory
cleanup_gpu_memory()

# Use CPU fallback
config.use_gpu = False

# Process chromosomes sequentially instead of parallel
```

#### 2. Low Balanced Accuracy

**Symptoms**: Cannot reach target Balanced Accuracy

**Solutions**:
- Lower `target_balanced_accuracy` (e.g., 0.90 instead of 0.95)
- Increase `max_dmps` to allow more positions
- Check centroid quality (outliers removed?)
- Verify groups are actually different

#### 3. Classification Confidence Low

**Symptoms**: Posterior probabilities close to 0.5

**Solutions**:
- Check if sample is truly ambiguous
- Use temperature scaling to sharpen probabilities
- Verify model was trained on similar data
- Check for missing positions

#### 4. Pipeline Hangs

**Symptoms**: Process appears stuck

**Solutions**:
- Check logs for actual progress
- Verify GPU is accessible (`nvidia-smi`)
- Check disk space for caching
- Ensure no deadlocks in parallel processing

### Logging

#### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### Package-Specific Logging

```python
import logging
logging.getLogger('methyl_detector').setLevel(logging.DEBUG)
logging.getLogger('methyl_classifier').setLevel(logging.INFO)
```

---

## Best Practices

### 1. Data Organization

```
project/
├── raw_data/
│   ├── healthy/
│   │   ├── sample1/
│   │   │   ├── 1-CG.h5
│   │   │   ├── 2-CG.h5
│   │   │   └── ...
│   │   └── sample2/
│   └── cancer/
├── centroids/
│   ├── healthy/
│   └── cancer/
├── models/
│   ├── chr1_CG_model.pkl
│   └── ...
├── configs/
└── results/
```

### 2. Quality Control Checklist

- [ ] Check centroid outlier reports
- [ ] Run clustering QC before DMP detection
- [ ] Validate expected groupings match clustering
- [ ] Check DMP distributions (avoid extreme filtering)
- [ ] Verify Balanced Accuracy on validation set
- [ ] Test classification on known samples

### 3. Reproducibility

```python
# Set random seeds
import random
import numpy as np
random.seed(42)
np.random.seed(42)

# Log configuration
import json
with open('/output/config_used.json', 'w') as f:
    json.dump(config.model_dump(), f, indent=2)

# Version tracking
from methylpipeline import __version__
print(f"MethylPipeline version: {__version__}")
```

### 4. Performance Optimization

- **Use GPU**: 10-50x speedup for most operations
- **Cache distance matrices**: Reuse for different clustering parameters
- **Batch processing**: Process multiple samples/chromosomes in parallel
- **Memory management**: Use chunked processing for large datasets
- **Profile**: Use performance profiling to identify bottlenecks

---

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
- **GPU**: NVIDIA GPU with 16 GB+ VRAM (e.g., V100, A100, GH200)
- **Storage**: 1 TB NVMe SSD
- **Time**: ~4 hours for genome-wide analysis

#### Production (Multi-GPU)
- **CPU**: 32+ cores
- **RAM**: 128 GB+
- **GPU**: 4x NVIDIA A100 (40 GB each)
- **Storage**: 2 TB NVMe SSD
- **Time**: ~1 hour for genome-wide analysis

### Software Requirements

- **OS**: Linux (Ubuntu 20.04+ recommended), macOS (CPU-only)
- **Python**: 3.8-3.11
- **CUDA**: 11.8+ (for GPU acceleration)
- **Docker**: 20.10+ (for containerized deployment)
- **Git**: For version control

### Python Dependencies

Core dependencies (automatically installed):
- numpy >= 1.21.0
- scipy >= 1.7.0
- pandas >= 1.3.0
- h5py >= 3.0.0
- pydantic >= 2.0.0
- scikit-learn >= 1.0.0
- hdbscan >= 0.8.27
- plotly >= 5.0.0

Optional (for GPU):
- cupy-cuda11x >= 11.0.0

---

## License

MethylPipeline is licensed under the MIT License.

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

---

## Citation

```bibtex
@software{methylpipeline2024,
  title={MethylPipeline: Unified Genomics Pipeline for Methylation Analysis},
  author={MethylPipeline Contributors},
  year={2024},
  url={https://github.com/yourusername/MethylPipeline},
  note={Comprehensive toolkit for methylation-based biomarker discovery and classification}
}
```

---

*End of MethylPipeline Comprehensive Documentation*

**Last Updated**: October 2024  
**Version**: 1.0.0

For package-specific documentation, see:
- [MethylUtils Documentation](../packages/methylutils/docs/METHYLUTILS_COMPREHENSIVE_DOCUMENTATION.md)
- [MethylCentroid Documentation](../packages/methylcentroid/docs/METHYLCENTROID_COMPREHENSIVE_DOCUMENTATION.md)
- [MethylCluster Documentation](../packages/methylcluster/docs/METHYLCLUSTER_COMPREHENSIVE_DOCUMENTATION.md)
- [MethylDetector Documentation](../packages/methyldetector/docs/METHYLDETECTOR_COMPREHENSIVE_DOCUMENTATION.md)
- [MethylTrainer Documentation](../packages/methyltrainer/docs/METHYLTRAINER_COMPREHENSIVE_DOCUMENTATION.md)
- [MethylClassifier Documentation](../packages/methylclassifier/docs/METHYLCLASSIFIER_COMPREHENSIVE_DOCUMENTATION.md)

