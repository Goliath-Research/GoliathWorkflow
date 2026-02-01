# MethylCentroid Usage Guide

## Overview

MethylCentroid calculates representative methylation profiles (centroids) from
groups of samples. It focuses on accurate aggregation, memory efficiency, and
GPU-optional acceleration.

## Quick Start

### Command Line (Inside Container)

```bash
cd /home/ubuntu/MethylPipeline/packages/methylcentroid
./mc --batch-config configs/pb-cancer_batch_stage1_config.json
```

The `./mc` script executes inside the `methylpipeline` Docker container, ensuring
CUDA and dependencies are configured.

### Python API

```python
from methyl_centroid import MethylCentroid

mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./output',
    add_samples=['/data/sample1', '/data/sample2', '/data/sample3'],
    min_coverage=4
)

results = mc.build_centroid()
print(f"Centroid saved to: {results.final_centroid_path}")
```

## Configuration Files

### Batch Processing Configuration

```json
{
  "chromosomes": ["1", "2", "3", "X"],
  "contexts": ["CG", "CHG", "CHH"],
  "base_config": {
    "samples": [
      "/data/healthy1",
      "/data/healthy2",
      "/data/healthy3"
    ],
    "output_dir": "/output/centroids",
    "min_coverage": 4,
    "use_gpu": true
  },
  "continue_on_error": true
}
```

### Individual Configuration

```json
{
  "chrom": "1",
  "ctx": "CG",
  "samples": [
    "/data/sample1",
    "/data/sample2",
    "/data/sample3"
  ],
  "output_dir": "/output/centroids",
  "min_coverage": 4,
  "use_gpu": true,
  "verbose": true
}
```

## Key Parameters

### Coverage Parameters

- **`min_coverage`**: Minimum coverage threshold for positions (default: 4)

### Performance Parameters

- **`use_gpu`**: Enable GPU acceleration (default: true)
  - You can force CPU with CLI `--no-gpu`
- **`verbose`**: Enable detailed logging (default: true)

### Cohort Inputs

- **`samples`**: Existing cohort samples (for updates)
- **`add_samples`**: New samples to add
- **`remove_samples`**: Samples to remove

## Output Files

### Primary Outputs

1. **`{chrom}-{ctx}.h5`**: HDF5 file containing centroid data
   - Structure: `pos`, `mC`, `uC`, `N`, `Sx`, `Sx2`, `log_x_sum`, `log_1_minus_x_sum`
2. **`{chrom}-{ctx}_config.json`**: Metadata and configuration

## Common Workflows

### Workflow 1: Create Centroid for Healthy Cohort

```python
from methyl_centroid import MethylCentroid

mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids/healthy',
    add_samples=[
        'healthy_sample1',
        'healthy_sample2',
        # ... more samples
    ],
    min_coverage=4
)

mc.build_centroid()
```

### Workflow 2: Incremental Updates

```python
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids/healthy',
    samples=['healthy_sample1', 'healthy_sample2'],
    add_samples=['healthy_sample_new1', 'healthy_sample_new2']
)

mc.build_centroid()
```

### Workflow 3: Optional Binned Stats

```python
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids/healthy',
    add_samples=['sample1', 'sample2'],
    min_coverage=4,
    enable_binned_stats=True,
    binned_stats_bins=32
)
mc.build_centroid()
```

## Integration with MethylPipeline

MethylCentroid is typically the first step in the pipeline:

```
MethylCentroid → MethylDetector → MethylClassifier
    (Generate)      (Detect)          (Predict)
```

### Input

- Raw methylation samples (HDF5 files from alignment)
- Multiple samples per group (e.g., 35 healthy, 12 cancer)

### Output

- Centroids (one per group)
- Used by MethylDetector for DMP detection
# MethylCentroid Usage Guide

## Overview

MethylCentroid calculates representative methylation profiles (centroids) from
groups of samples. It focuses on accurate aggregation, memory efficiency, and
GPU-optional acceleration.

## Quick Start

### Command Line (Inside Container)

```bash
cd /home/ubuntu/MethylPipeline/packages/methylcentroid
./mc --batch-config configs/pb-cancer_batch_stage1_config.json
```

The `./mc` script executes inside the `methylpipeline` Docker container, ensuring
CUDA and dependencies are configured.

### Python API

```python
from methyl_centroid import MethylCentroid

mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./output',
    add_samples=['/data/sample1', '/data/sample2', '/data/sample3'],
    min_coverage=4
)

results = mc.build_centroid()
print(f"Centroid saved to: {results.final_centroid_path}")
```

## Configuration Files

### Batch Processing Configuration

```json
{
  "chromosomes": ["1", "2", "3", "X"],
  "contexts": ["CG", "CHG", "CHH"],
  "base_config": {
    "samples": [
      "/data/healthy1",
      "/data/healthy2",
      "/data/healthy3"
    ],
    "output_dir": "/output/centroids",
    "min_coverage": 4,
    "use_gpu": true
  },
  "continue_on_error": true
}
```

### Individual Configuration

```json
{
  "chrom": "1",
  "ctx": "CG",
  "samples": [
    "/data/sample1",
    "/data/sample2",
    "/data/sample3"
  ],
  "output_dir": "/output/centroids",
  "min_coverage": 4,
  "use_gpu": true,
  "verbose": true
}
```

## Key Parameters

### Coverage Parameters

- **`min_coverage`**: Minimum coverage threshold for positions (default: 4)

### Performance Parameters

- **`use_gpu`**: Enable GPU acceleration (default: true)
  - You can force CPU with CLI `--no-gpu`
- **`verbose`**: Enable detailed logging (default: true)

### Cohort Inputs

- **`samples`**: Existing cohort samples (for updates)
- **`add_samples`**: New samples to add
- **`remove_samples`**: Samples to remove

## Output Files

### Primary Outputs

1. **`{chrom}-{ctx}.h5`**: HDF5 file containing centroid data
   - Structure: `pos`, `mC`, `uC`, `N`, `Sx`, `Sx2`, `log_x_sum`, `log_1_minus_x_sum`
2. **`{chrom}-{ctx}_config.json`**: Metadata and configuration

## Common Workflows

### Workflow 1: Create Centroid for Healthy Cohort

```python
from methyl_centroid import MethylCentroid

mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids/healthy',
    add_samples=[
        'healthy_sample1',
        'healthy_sample2',
        # ... more samples
    ],
    min_coverage=4
)

mc.build_centroid()
```

### Workflow 2: Incremental Updates

```python
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids/healthy',
    samples=['healthy_sample1', 'healthy_sample2'],
    add_samples=['healthy_sample_new1', 'healthy_sample_new2']
)

mc.build_centroid()
```

### Workflow 3: Optional Binned Stats

```python
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids/healthy',
    add_samples=['sample1', 'sample2'],
    min_coverage=4,
    enable_binned_stats=True,
    binned_stats_bins=32
)
mc.build_centroid()
```

## Integration with MethylPipeline

MethylCentroid is typically the first step in the pipeline:

```
MethylCentroid → MethylDetector → MethylClassifier
    (Generate)      (Detect)          (Predict)
```

### Input

- Raw methylation samples (HDF5 files from alignment)
- Multiple samples per group (e.g., 35 healthy, 12 cancer)

### Output

- Centroids (one per group)
- Used by MethylDetector for DMP detection
