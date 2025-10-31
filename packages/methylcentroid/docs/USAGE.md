# MethylCentroid Usage Guide

## Overview

MethylCentroid calculates representative methylation profiles (centroids) from groups of samples with automatic outlier detection. This guide covers practical usage patterns and workflows.

## Quick Start

### Command Line (Inside Container)

```bash
cd /home/ubuntu/MethylPipeline/packages/methylcentroid
./mc --batch-config configs/pb-cancer_batch_stage1_config.json
```

The `./mc` script executes inside the `methylpipeline` Docker container, ensuring all dependencies (CUDA, RAPIDS, etc.) are properly configured.

### Python API

```python
from methyl_centroid import MethylCentroid

# Basic usage with automatic outlier detection
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./output',
    add_samples=['/data/sample1', '/data/sample2', '/data/sample3'],
    min_coverage=4,
    max_iterations=10,
    α=0.05
)

results = mc.build_centroid()
print(f"Removed {results.total_samples_removed} outliers")
print(f"Centroid saved to: {results.final_centroid_path}")
```

## Configuration Files

### Batch Processing Configuration

Create a JSON config file for processing multiple chromosome/context combinations:

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
    "max_iterations": 10,
    "α": 0.05
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
  "max_iterations": 10,
  "α": 0.05,
  "min_samples": 3,
  "distance_metrics": ["jeffreys", "jensen_shannon", "hellinger"]
}
```

## Key Parameters

### Outlier Detection Parameters

- **`max_iterations`**: Maximum number of outlier removal iterations (default: 10)
  - Typically converges in 2-5 iterations
- **`α`**: Significance level for outlier detection (default: 0.05)
  - Lower values = stricter outlier filtering
- **`min_samples`**: Minimum samples to keep (default: 3)
  - Stops outlier removal if below this threshold
- **`distance_metrics`**: List of metrics to use for consensus
  - Available: `jeffreys`, `jensen_shannon`, `weighted_jensen_shannon`, `hellinger`, `wasserstein`
- **`min_metrics_agree`**: Number of metrics that must agree (default: 1)
  - Higher values = more conservative outlier detection

### Coverage Parameters

- **`min_coverage`**: Minimum coverage threshold for positions (default: 4)
  - Positions with coverage < min_coverage are excluded from centroid
- **`coverage_percentage_threshold`**: Optional percentage-based filtering

### Performance Parameters

- **`verbose`**: Enable detailed logging (default: True)
- **`use_gpu`**: Enable GPU acceleration (default: True)
  - Automatic CPU fallback if GPU unavailable

## Output Files

### Primary Outputs

1. **`chr{chrom}-{ctx}_centroid.h5`**: HDF5 file containing centroid data
   - Structure: `pos`, `mC`, `uC`, `N`, `Sx`, `Sx2` arrays
2. **`chr{chrom}-{ctx}_centroid.json`**: Metadata and configuration
   - Samples processed, outliers removed, parameters used
3. **`outlier_report.json`**: Outlier detection results
   - Iteration-by-iteration outlier details with p-values

### Optional Outputs

- **`metadata.json`**: Extended metadata (if enabled)
- **`visualizations.html`**: Interactive plots (if enabled)

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
    max_iterations=10,
    α=0.05
)

results = mc.build_centroid()
```

### Workflow 2: Incremental Updates

```python
# Add new samples to existing centroid
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids/healthy',
    add_samples=['healthy_sample_new1', 'healthy_sample_new2']
)

mc.build_centroid()
```

### Workflow 3: Strict Outlier Filtering

```python
# More conservative outlier detection
mc = MethylCentroid(
    chrom='1',
    ctx='CG',
    output_dir='./centroids/strict',
    add_samples=[...],
    max_iterations=5,  # Fewer iterations
    α=0.01,  # Stricter significance
    min_metrics_agree=2,  # Require multiple metrics to agree
    distance_metrics=['jensen_shannon', 'hellinger', 'wasserstein']
)

results = mc.build_centroid()
```

## Advanced: Outlier Detection Methods

MethylCentroid automatically selects the most appropriate outlier detection algorithm based on sample size:

### Probabilistic Method (≥20 samples)
- Uses Beta distribution fitting
- Most statistically rigorous
- Provides calibrated probabilities

### Multi-Metric Consensus (5-19 samples)
- Combines multiple distance metrics
- Reduces false positives
- Good balance of rigor and robustness

### Single-Metric Detection (3-4 samples)
- Uses single distance metric (Jensen-Shannon)
- Simple and interpretable
- Works with minimal samples

You can force a specific method by adjusting sample size or using the detector factory directly.

## Integration with MethylPipeline

MethylCentroid is typically the first step in the pipeline:

```
MethylCentroid → MethylModeler → MethylClassifier
    (Generate)      (Train Model)     (Predict)
```

### Input

- Raw methylation samples (HDF5 files from alignment)
- Multiple samples per group (e.g., 35 healthy, 12 cancer)

### Output

- Cleaned centroids (one per group)
- Used by MethylModeler for DMP detection
- Used by  for classifier training

## Troubleshooting

### Problem: No Outliers Detected

**Symptom**: `total_samples_removed = 0` despite potential outliers

**Solutions**:
```python
# Try stricter parameters
mc = MethylCentroid(
    α=0.01,  # Lower significance threshold
    min_metrics_agree=2,  # Require consensus
    distance_metrics=['hellinger', 'wasserstein']  # Add more metrics
)
```

### Problem: Too Many Samples Removed

**Symptom**: `total_samples_removed` is very high (>20%)

**Solutions**:
```python
# Relax parameters
mc = MethylCentroid(
    α=0.10,  # Higher threshold
    max_iterations=5,  # Fewer iterations
    min_samples=5  # Keep more samples
)
```

### Problem: Out of Memory

**Symptom**: OOM errors during processing

**Solutions**:
```python
# Process chromosomes separately
# Or reduce batch size
mc = MethylCentroid(
    ...,
    enable_caching=False,  # Disable caching to save memory
    chunk_size=100000  # Smaller chunks
)
```

### Problem: GPU Errors

**Symptom**: CUDA errors or GPU unavailable

**Solutions**:
```python
# Automatic fallback
mc = MethylCentroid(
    ...,
    use_gpu=False  # Force CPU
)
```

## Best Practices

1. **Start with Defaults**: Default parameters work well for most cases
2. **Monitor Outlier Rate**: 5-10% removed is normal; >20% suggests issues
3. **Validate Results**: Check that outliers are genuine technical issues
4. **Use Batch Processing**: More efficient for multiple chromosome/context combinations
5. **Enable Logging**: Use `verbose=True` to understand what's happening

## See Also

- [MethylCentroid Comprehensive Documentation](METHYLCENTROID_COMPREHENSIVE_DOCUMENTATION.md)
- [Theoretical Foundation](MethylCentroid_Theoretical_Foundation.md)
- [MethylPipeline Integration](../methylmodeler/docs/METHYLDETECTOR_COMPREHENSIVE_DOCUMENTATION.md)

