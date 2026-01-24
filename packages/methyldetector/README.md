# MethylDetector

**Detect Differentially Methylated Positions and Train Bayesian Classifiers**

## Overview

MethylDetector is a production-ready package for detecting Differentially Methylated Positions (DMPs) between two methylation centroids and training Bayesian classifiers optimized with Balanced Accuracy. It combines statistical rigor (Storey's q-value FDR correction) with biological filtering to identify meaningful biomarkers.

### What is MethylDetector?

MethylDetector bridges centroid generation and classification:

- **DMP Detection**: Statistical comparison of two centroids with FDR control
- **Biological Filtering**: Effect size and overlap criteria for meaningful DMPs
- **Classifier Training**: Optimized DMP selection using FeatureCuts or Bayesian Optimization
- **Balanced Accuracy Optimization**: Robust to class imbalance (e.g., 35 healthy vs 12 cancer)
- **Model Packaging**: Creates `.pkl` files for MethylClassifier
- **Multi-Chromosome Support**: Process single or multiple chromosomes in one run

## Key Features

- 🔬 **Statistical Rigor**: Storey's q-value FDR correction (recommended for genomics)
- 📊 **Biological Filtering**: Delta mean, Bhattacharyya coefficient, coverage thresholds
- 🎯 **Balanced Accuracy**: Unbiased metric robust to class imbalance
- 🔍 **FeatureCuts Optimization**: Efficient non-monotonic optimization for DMP selection
- 🧬 **Multi-Context Support**: Process CG, CHG, CHH contexts together
- 🧬 **Multi-Chromosome Support**: Process multiple chromosomes in a single run
- 🚀 **GPU Acceleration**: 15-20x speedup with NVIDIA GPUs
- 📦 **Model Packaging**: Complete metadata for reproducibility
- ✅ **Validation Modes**: Real or synthetic sample validation with proper train/test splits

## Installation

```bash
# Install from source
cd packages/methyldetector
pip install -e .

# Or as part of MethylPipeline
pip install methylpipeline
```

## Quick Start

### Basic Usage - Single Chromosome

```json
{
  "chromosome": "1",
  "contexts": ["CG"],
  "centroid1_dir": "/path/to/healthy/centroids",
  "centroid2_dir": "/path/to/cancer/centroids",
  "output_dir": "/path/to/output",
  "alpha": 0.01,
  "min_delta_mean": 0.2,
  "max_bc": 0.5,
  "optimize_dmps": true,
  "optimization_method": "featurecuts",
  "validation_mode": "real",
  "validation_split_ratio": 0.2
}
```

```bash
./detector config.json
```

### Multi-Chromosome Usage

Process multiple chromosomes in a single run:

```json
{
  "chromosome": ["1", "2", "3", "X"],
  "contexts": ["CG"],
  "centroid1_dir": "/path/to/healthy/centroids",
  "centroid2_dir": "/path/to/cancer/centroids",
  "output_dir": "/path/to/output",
  "alpha": 0.01,
  "min_delta_mean": 0.2,
  "max_bc": 0.5
}
```

Each chromosome will:
- Process independently with its own centroids
- Generate separate output files: `dmps-1.csv`, `dmps-2.csv`, `classifier-1.pkl`, etc.
- Continue processing even if one fails (with error logging)

### Command Line Interface

```bash
# Run with JSON configuration
./detector config.json

# With verbose output
./detector config.json --verbose

# With log file
./detector config.json --log-file output.log
```

### Python API

```python
from methyl_detector.models.config import MethylModelerConfig
from methyl_detector.core.methyldetector import MethylDetector
from methyl_detector.utils.file_utils import load_config_from_json

# Load configuration
config = load_config_from_json("config.json")

# Initialize and run
detector = MethylDetector(config)
result = detector.run()

# Handle single or multiple results
if isinstance(result, list):
    print(f"Processed {len(result)} chromosomes")
    for r in result:
        print(f"  DMPs: {r.total_biological_dmps:,}")
else:
    print(f"DMPs: {result.total_biological_dmps:,}")
```

## Configuration Parameters

### Input/Output

- **`chromosome`**: Single chromosome (e.g., `"1"`) or list (e.g., `["1", "2", "X"]`)
- **`contexts`**: List of contexts to process (default: `["CG"]`)
  - Options: `"CG"`, `"CHG"`, `"CHH"` or any combination
- **`centroid1_dir`**: Directory containing centroid1 `.h5` files (format: `{chrom}-{context}.h5`)
- **`centroid2_dir`**: Directory containing centroid2 `.h5` files
- **`output_dir`**: Output directory for results

### Statistical Parameters

- **`alpha`**: FDR q-value threshold (default: `0.01`)
  - Uses Storey's q-value method for adaptive FDR control

### Biological Filtering

- **`min_delta_mean`**: Minimum absolute difference in mean methylation (default: `0.2`)
- **`max_bc`**: Maximum Bhattacharyya coefficient / overlap (default: `0.6`)
  - Lower values = less overlap = stronger discrimination
- **`min_N_pct`**: Minimum coverage percentage (default: `0.1`)
  - Positions must have coverage ≥ 10% of samples
- **`biological_filters`**: List of filters to apply (default: `["delta_mean", "bhattacharyya"]`)

### Context Weighting

- **`use_context_weights`**: Enable trimmed-mean context weighting (default: `true`)
- **`trimmed_percentile_low`**: Lower percentile to trim (default: `0.10`)
- **`trimmed_percentile_high`**: Upper percentile to trim (default: `0.01`)

### DMP Optimization

- **`optimize_dmps`**: Enable DMP count optimization (default: `false`)
- **`optimization_method`**: `"binary_search"`, `"featurecuts"`, or `"bayesian_optimization"` (default: `"featurecuts"`)
  - `binary_search`: Fastest (~log N evaluations), assumes monotonic BA increase (use with proper weighting)
  - `featurecuts`: Fast logarithmic sampling (~18 evaluations), handles non-monotonic functions
  - `bayesian_optimization`: Most thorough search (~50 evaluations), handles complex optimization landscapes
- **`target_balanced_accuracy`**: Target BA for optimization (default: `0.95`)
- **`min_dmps_for_export`**: Minimum DMPs to export (default: `1000`)

### Validation

- **`validation_mode`**: `"real"` or `"synthetic"` (default: `"synthetic"`)
- **`centroid1_validation_samples`**: List of sample directories or `"use_metadata"`
- **`centroid2_validation_samples`**: List of sample directories or `"use_metadata"`
- **`validation_split_ratio`**: Train/test split for validation (default: `0.0`)
  - `0.0`: Use all samples for calibration (no split)
  - `0.1-0.9`: Split into calibration and test sets (recommended: `0.2`)

### Classifier Settings

- **`classifier_type`**: `"beta"` (recommended) or `"beta_binomial"`
- **`min_sample_coverage`**: Minimum coverage for positions (default: `10`)
- **`classifier_coverage_weighting`**: Weight by sample precision (default: `true`)

### Performance

- **`use_gpu`**: Enable GPU acceleration (default: `true`)
- **`random_state`**: Random seed for reproducibility (default: `42`)

## Output Files

### Per Chromosome

1. **`dmps-{chromosome}.csv`** - All biological DMPs with full metadata
2. **`dmps-{chromosome}-1-biological.csv`** - Stage 1: Biological DMPs (if optimization enabled)
3. **`dmps-{chromosome}-2-pre-optimization.csv`** - Stage 2: Pre-optimization DMPs (if optimization enabled)
4. **`dmps-{chromosome}-3-optimized.csv`** - Stage 3: Final optimized DMPs (if optimization enabled)
5. **`classifier-{chromosome}.pkl`** - Trained BetaClassifier model
6. **`results-{chromosome}.json`** - Validation results and summary

### CSV Columns

- `chromosome`, `context`, `position`
- `p_value`, `q_value`, `delta_mean`, `delta_sign`
- `overlap` (Bhattacharyya coefficient)
- `effect_size`, `context_weight`
- `alpha1`, `beta1`, `alpha2`, `beta2` (Beta distribution parameters)
- `mean1`, `mean2` (mean methylation levels)

## Core Workflow

```
1. Load Centroids
   ├─ Read centroid files for each context
   ├─ Format: {chromosome}-{context}.h5
   └─ Align to common positions

2. Statistical Testing
   ├─ Compute likelihood ratio at each position
   ├─ Calculate p-values
   ├─ Apply FDR correction (Storey's q-value)
   └─ Identify significant positions (q ≤ alpha)

3. Biological Filtering
   ├─ Filter by minimum coverage (min_N_pct)
   ├─ Filter by effect size (min_delta_mean)
   ├─ Filter by distribution overlap (max_bc)
   └─ Rank by biological importance (effect_size)

4. Context Weighting (multi-context only)
   ├─ Compute trimmed mean of effect_size per context
   ├─ Normalize weights to sum=1.0
   └─ Assign weights to each DMP

5. DMP Optimization (optional)
   ├─ Load validation samples
   ├─ FeatureCuts or Bayesian Optimization
   ├─ Evaluate Balanced Accuracy for candidate k values
   ├─ Find minimum k achieving maximum BA
   └─ Select optimal DMP subset

6. Create Model Package
   ├─ Package BetaClassifier
   ├─ Include DMP positions and Beta parameters
   ├─ Add metadata (chromosome, contexts, n_dmps)
   └─ Save as .pkl file

7. Generate Reports
   ├─ DMP tables (CSV)
   ├─ Validation results (JSON)
   └─ Summary statistics
```

## Multi-Chromosome Processing

MethylDetector supports processing multiple chromosomes in a single run:

### Benefits

- **Efficient**: Single Python process, shared GPU memory management
- **Robust**: One chromosome failure doesn't stop others
- **Consistent**: Same configuration applied to all chromosomes
- **Organized**: Each chromosome gets its own output files

### Example

```json
{
  "chromosome": ["1", "2", "3", "X"],
  "contexts": ["CG"],
  "centroid1_dir": "/centroids/healthy",
  "centroid2_dir": "/centroids/cancer",
  "output_dir": "/models/all_chromosomes"
}
```

**Output structure:**
```
/models/all_chromosomes/
├── dmps-1.csv
├── classifier-1.pkl
├── results-1.json
├── dmps-2.csv
├── classifier-2.pkl
├── results-2.json
└── ...
```

## Why Balanced Accuracy?

MethylDetector uses **Balanced Accuracy** instead of AUC because:

1. **Robust to Class Imbalance**: Works correctly with unbalanced datasets (e.g., 35 healthy vs 12 cancer)
2. **Interpretable**: Simple average of Sensitivity and Specificity
3. **Unbiased**: Treats both classes equally regardless of sample sizes
4. **Validated**: Widely used in medical/genomics research

**Formula**:
$$
\text{Balanced Accuracy} = \frac{\text{Sensitivity} + \text{Specificity}}{2}
$$

## Integration with MethylPipeline

### Workflow Position

```
MethylCentroid → MethylDetector → MethylClassifier
    (Generate)     (Train Model)    (Predict)
```

### Inputs

- Centroids from **MethylCentroid** (HDF5 files in directory format)
- Optional: Validation samples

### Outputs

- Model packages (`.pkl`) for **MethylClassifier**
- DMP tables for analysis
- Validation results

## Performance

### GPU Acceleration

| Operation | CPU Time | GPU Time | Speedup |
|-----------|----------|----------|---------|
| DMP Detection (1M positions) | 45 min | 3 min | 15x |
| FeatureCuts Optimization (~18 evals) | 60 min | 5 min | 12x |
| Complete Analysis | 105 min | 8 min | 13x |

### Memory Usage

- Typical: 4-8 GB
- Peak: 10-15 GB (during optimization)
- Scales linearly with number of positions

## Troubleshooting

### No DMPs Found

**Problem**: `total_biological_dmps = 0`

**Solutions**:
```json
{
  "alpha": 0.05,  // Relax FDR threshold
  "min_delta_mean": 0.1,  // Lower effect size threshold
  "max_bc": 0.8  // Allow more overlap
}
```

### Cannot Reach Target Balanced Accuracy

**Problem**: Optimization finds low BA values

**Solutions**:
- Check validation samples are representative
- Verify centroids have sufficient samples
- Lower `target_balanced_accuracy` (e.g., `0.90`)
- Increase `min_dmps_for_export` if too few DMPs

### GPU Out of Memory

**Problem**: CUDA out of memory errors

**Solutions**:
```json
{
  "use_gpu": false  // Disable GPU
}
```

Or process chromosomes sequentially instead of in parallel.

### Out-of-Bounds Errors During Validation

**Problem**: Index errors when loading validation samples

**Solution**: This has been fixed in recent versions. Ensure you're using the latest code.

## Examples

See `configs/` directory for example configuration files:
- `pc-hc1-1-CG_config.json` - Single chromosome with real validation
- `pb-c1c2-1-CG_config.json` - Multi-context example
- `multi-context-example.json` - Multi-context configuration

## Documentation

- **[Quick Start Guide](QUICKSTART.md)** - Get started quickly
- **[Context Selection Guide](CONTEXT_SELECTION_GUIDE.md)** - Choosing methylation contexts
- **[Comprehensive Documentation](docs/METHYLMODELER_COMPREHENSIVE_DOCUMENTATION.md)** - Complete API reference

## Contributing

Please ensure:
1. Tests pass: `pytest tests/`
2. Configurations validate: Check with Pydantic
3. Documentation updated

## License

MIT License - see [LICENSE](../../LICENSE) file for details.

---

For more information, see:
- [MethylPipeline Documentation](../../docs/)
