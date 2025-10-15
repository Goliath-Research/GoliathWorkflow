# Validation with Real Samples

## Overview

MethylDetector now supports validating the DMP classifier using **real samples** from the centroids, rather than only synthetic samples generated from Beta distributions.

This provides a more realistic assessment of classifier performance and ensures DMPs generalize well to actual data.

## Configuration Options

### Validation Mode

Set the `validation_mode` parameter in your configuration:

```json
{
  "validation_mode": "synthetic"  // or "real"
}
```

- **`synthetic`** (default): Generate synthetic samples from Beta distributions
- **`real`**: Use actual sample data from HDF5 files

### Specifying Validation Samples

When using `validation_mode: "real"`, you can specify validation samples in two ways:

#### Option 1: Use Centroid Metadata (Recommended)

```json
{
  "validation_mode": "real",
  "centroid1_validation_samples": "use_metadata",
  "centroid2_validation_samples": "use_metadata"
}
```

This reads the `samples_used` field from the centroid HDF5 metadata. MethylCentroid automatically embeds this information when creating centroids.

**Advantages:**
- Self-documenting: No need to track samples separately
- Automatic: Uses the exact samples that built the centroid
- Provenance: Full audit trail of centroid creation

#### Option 2: Manually Specify Sample Paths

```json
{
  "validation_mode": "real",
  "centroid1_validation_samples": [
    "/home/ubuntu/Work/samples/healthy/sample1",
    "/home/ubuntu/Work/samples/healthy/sample2"
  ],
  "centroid2_validation_samples": [
    "/home/ubuntu/Work/samples/cancer/sample1",
    "/home/ubuntu/Work/samples/cancer/sample2"
  ]
}
```

**Advantages:**
- Flexible: Use different samples than those that built the centroid
- Relocatable: Specify current sample locations if files moved
- Custom validation sets: Test on holdout samples

## Centroid Metadata

### What MethylCentroid Saves

Starting with the latest version, MethylCentroid automatically saves the following metadata in every centroid:

```python
{
  "laboratory": "...",
  "disease": "...",
  "group": "...",
  "batch": "...",
  "samples_used": ["/path/to/sample1", "/path/to/sample2", ...],  # NEW
  "outliers_removed": ["/path/to/outlier1", ...],                 # NEW
  "creation_date": "2024-01-15T10:30:00",                         # NEW
  "min_coverage": 4,
  "alpha": 0.05,
  "distance_metrics": ["jensen_shannon", "wasserstein"]
}
```

### Reading Centroid Metadata

You can inspect centroid metadata using MethylUtils:

```python
from methyl_utils import MethylSample

# Load centroid
centroid = MethylSample.load_from_h5("path/to/centroid.h5")

# Access metadata
print(centroid.metadata['samples_used'])
print(centroid.metadata['outliers_removed'])
print(centroid.metadata['creation_date'])
```

## Example Workflows

### Workflow 1: Automatic Validation with Metadata

1. **Create centroids with MethylCentroid** (automatically saves metadata):
   ```bash
   ./mc --config centroid_config.json
   ```

2. **Run MethylDetector with automatic validation**:
   ```bash
   ./md --config detector_config.json
   ```
   
   Config:
   ```json
   {
     "validation_mode": "real",
     "centroid1_validation_samples": "use_metadata",
     "centroid2_validation_samples": "use_metadata"
   }
   ```

### Workflow 2: Custom Validation Samples

Use this when you want to:
- Validate on a subset of samples
- Validate on holdout samples not used in centroid creation
- Use samples from a different location

```json
{
  "validation_mode": "real",
  "centroid1_validation_samples": [
    "/current/location/sample1",
    "/current/location/sample2"
  ],
  "centroid2_validation_samples": [
    "/current/location/sample3",
    "/current/location/sample4"
  ]
}
```

### Workflow 3: Fallback to Synthetic

If real samples can't be loaded (missing files, permissions, etc.), MethylDetector automatically falls back to synthetic validation:

```
WARNING: Failed to load sufficient samples, falling back to synthetic validation
```

## Migration Guide

### For Existing Centroids Without Metadata

Old centroids don't have the new `samples_used` metadata field. You have two options:

**Option 1: Regenerate Centroids** (Recommended)
```bash
# Run MethylCentroid again to generate new centroids with metadata
./mc --config centroid_config.json
```

**Option 2: Specify Samples Manually**
```json
{
  "validation_mode": "real",
  "centroid1_validation_samples": ["/path/to/sample1", ...],
  "centroid2_validation_samples": ["/path/to/sample1", ...]
}
```

## Best Practices

1. **Use `"use_metadata"` when possible**: This ensures you're validating on the exact samples used to build the centroid.

2. **Check validation logs**: Look for messages like:
   ```
   Loading 15 samples from centroid 1
   Loading 15 samples from centroid 2
   Class 0 accuracy: 98.5%
   Class 1 accuracy: 97.2%
   ```

3. **Handle missing samples gracefully**: MethylDetector will skip missing samples and fall back to synthetic validation if needed.

4. **Document sample locations**: If using custom paths, document them in your analysis notes.

## Comparison: Synthetic vs Real Validation

| Aspect | Synthetic Validation | Real Validation |
|--------|---------------------|-----------------|
| **Speed** | Fast (generate from Beta) | Slower (load HDF5 files) |
| **Accuracy** | Models theoretical distributions | Tests actual data |
| **Sample Count** | Configurable (default 100) | Limited by available samples |
| **Setup** | No additional config needed | Requires sample paths or metadata |
| **Use Case** | Quick testing, many samples | Production validation, realistic assessment |

## Troubleshooting

### "No validation samples available"
- Check that centroids have `samples_used` in metadata
- Or manually specify sample paths in config
- Verify sample files exist at specified paths

### "Failed to load sample X"
- Verify HDF5 file exists: `{sample_dir}/{chrom}-{ctx}.h5`
- Check file permissions
- Ensure chromosome/context match centroid

### Low Accuracy on Real Samples
- Check that validation samples match the centroid group
- Verify DMP positions exist in validation samples
- Consider if samples have sufficient coverage

## API Reference

### Configuration Fields

```python
validation_mode: str = "synthetic"  # or "real"
centroid1_validation_samples: Optional[Union[str, List[str]]] = None
centroid2_validation_samples: Optional[Union[str, List[str]]] = None
```

### Methods

```python
def _validate_classifier_on_real_samples(
    self,
    classifier,
    biological_dmps_df: pd.DataFrame
) -> float:
    """Validate classifier on real samples from centroids."""
    
def _get_validation_sample_paths(
    self, 
    centroid_path: Path, 
    config_samples
) -> List[str]:
    """Get validation sample paths from config or metadata."""
    
def _load_sample_methylation_at_dmps(
    self,
    sample_dir: Union[str, Path],
    chrom: str,
    ctx: str,
    dmp_positions: np.ndarray
) -> Optional[np.ndarray]:
    """Load methylation values from a sample at DMP positions."""
```

## Future Enhancements

Potential improvements:
- Cross-validation with k-fold splits
- Stratified sampling for balanced validation
- Validation metrics beyond accuracy (precision, recall, AUC)
- Parallel sample loading for faster validation
- Caching of validation sample data

## Support

For issues or questions:
- GitHub Issues: https://github.com/epimethyl/MethylPipeline/issues
- Email: dizada@epimethyl.com

