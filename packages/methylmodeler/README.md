# MethylModeler

**Detect Differentially Methylated Positions and Train Bayesian Classifiers**

## Overview

MethylModeler is a production-ready package for detecting Differentially Methylated Positions (DMPs) between two methylation centroids and training Bayesian classifiers optimized with Balanced Accuracy. It combines statistical rigor (Storey's q-value FDR correction) with biological filtering to identify meaningful biomarkers.

### What is MethylModeler?

MethylModeler bridges centroid generation and classification:

- **DMP Detection**: Statistical comparison of two centroids with FDR control
- **Biological Filtering**: Effect size and overlap criteria for meaningful DMPs
- **Classifier Training**: Binary search to find optimal DMP subset
- **Balanced Accuracy Optimization**: Robust to class imbalance (e.g., 35 healthy vs 12 cancer)
- **Model Packaging**: Creates `.pkl` files for MethylClassifier

## Key Features

- 🔬 **Statistical Rigor**: Storey's q-value FDR correction (recommended for genomics)
- 📊 **Biological Filtering**: Delta mean, Bhattacharyya coefficient, coverage thresholds
- 🎯 **Balanced Accuracy**: Unbiased metric robust to class imbalance
- 🔍 **Binary Search**: Finds optimal DMP count for target accuracy
- 🧬 **Gene Mapping**: Feature importance at gene level
- 🚀 **GPU Acceleration**: 15-20x speedup with NVIDIA GPUs
- 📦 **Model Packaging**: Complete metadata for reproducibility
- ✅ **Validation Modes**: Real or synthetic sample validation

## Installation

```bash
# Install from source
cd packages/methylmodeler
pip install -e .

# Or as part of MethylPipeline
pip install methylpipeline
```

## Quick Start

### Basic Usage

```python
from methyl_modeler import MethylModelerConfig, run_comparison

# Create configuration
config = MethylModelerConfig(
    centroid1_path='/centroids/healthy.h5',
    centroid2_path='/centroids/cancer.h5',
    centroid1_name='Healthy',
    centroid2_name='Cancer',
    chrom='1',
    ctx='CG',
    output_dir='/output/detector',
    target_balanced_accuracy=0.95
)

# Run analysis
result = run_comparison(config)

print(f"Found {result['n_dmps']} DMPs")
print(f"Model saved to: {result['model_path']}")
print(f"Validation Balanced Accuracy: {result['validation_balanced_accuracy']:.3f}")
```

### Command Line Interface

```bash
# Run with JSON configuration
methyl-modeler /configs/healthy_vs_cancer.json

# Or specify parameters directly
methyl-modeler \
  --centroid1 /centroids/healthy.h5 \
  --centroid2 /centroids/cancer.h5 \
  --output-dir /output \
  --target-balanced-accuracy 0.95
```

### Configuration File Example

```json
{
  "centroid1_path": "/centroids/healthy/chr1-CG.h5",
  "centroid2_path": "/centroids/cancer/chr1-CG.h5",
  "centroid1_name": "Healthy",
  "centroid2_name": "Cancer",
  "chrom": "1",
  "ctx": "CG",
  
  "fdr_threshold": 0.01,
  "min_delta_mean": 0.1,
  "max_bc": 0.95,
  "min_N_pct": 0.1,
  
  "target_balanced_accuracy": 0.95,
  "min_dmps": 10,
  "max_dmps": 10000,
  
  "validation_mode": "real",
  "centroid1_validation_samples": ["/val/healthy1", "/val/healthy2"],
  "centroid2_validation_samples": ["/val/cancer1", "/val/cancer2"],
  
  "output_dir": "/output/detector",
  "use_gpu": true
}
```

## Core Workflow

```
1. Load Centroids
   ├─ Read centroid1 (e.g., Healthy)
   ├─ Read centroid2 (e.g., Cancer)
   └─ Align to common positions

2. Statistical Testing
   ├─ Compute likelihood ratio at each position
   ├─ Calculate p-values
   ├─ Apply FDR correction (Storey's q-value)
   └─ Identify significant positions

3. Biological Filtering
   ├─ Filter by minimum coverage (min_N_pct)
   ├─ Filter by effect size (min_delta_mean)
   ├─ Filter by distribution overlap (max_bc)
   └─ Rank by biological importance

4. Binary Search for Optimal DMPs
   ├─ Start with candidate DMPs
   ├─ For each DMP count:
   │   ├─ Train ProbabilisticBetaClassifier
   │   ├─ Validate on real or synthetic samples
   │   └─ Compute Balanced Accuracy
   ├─ Binary search to reach target_balanced_accuracy
   └─ Select optimal DMP set

5. Create Model Package
   ├─ Package ProbabilisticBetaClassifier
   ├─ Include DMP positions and Beta parameters
   ├─ Add metadata (centroid names, parameters)
   └─ Save as .pkl file

6. Generate Reports
   ├─ DMP table (all positions)
   ├─ Selected DMPs (CSV)
   ├─ Gene-level importance
   ├─ Visualizations (volcano plots, heatmaps)
   └─ Summary statistics (JSON)
```

## Configuration Parameters

### Centroid Specification

- **`centroid1_path`**: Path to first centroid HDF5 file
- **`centroid2_path`**: Path to second centroid HDF5 file
- **`centroid1_name`**: Name for class 1 (e.g., "Healthy")
- **`centroid2_name`**: Name for class 2 (e.g., "Cancer")
- **`chrom`**: Chromosome identifier
- **`ctx`**: Context (CG, CHG, or CHH)

### Statistical Parameters

- **`fdr_threshold`**: FDR q-value threshold (default: 0.01)
  - Uses Storey's q-value method for adaptive FDR control
- **`alpha`**: Legacy significance level parameter (default: 0.05)

### Biological Filtering

- **`apply_dmp_filtering`**: Enable biological filtering (default: true)
- **`min_delta_mean`**: Minimum effect size (default: 0.1)
  - Absolute difference in mean methylation levels
- **`max_bc`**: Maximum Bhattacharyya coefficient (default: 0.95)
  - Lower values = less overlap = stronger discrimination
- **`min_N_pct`**: Minimum coverage percentage (default: 0.1)
  - Positions must have coverage ≥ 10% of maximum

### Classifier Training

- **`target_balanced_accuracy`**: Target for binary search (default: 0.95)
  - Balanced Accuracy = (Sensitivity + Specificity) / 2
  - Robust to class imbalance
- **`min_dmps`**: Minimum DMPs to consider (default: 10)
- **`max_dmps`**: Maximum DMPs to consider (default: 10000)
- **`optimize_for_validation_accuracy`**: Optimize for validation set (default: true)

### Validation

- **`validation_mode`**: "real" or "synthetic" (default: "synthetic")
- **`centroid1_validation_samples`**: Paths to group 1 validation samples
- **`centroid2_validation_samples`**: Paths to group 2 validation samples
- **`n_synthetic_samples_per_class`**: Number of synthetic samples (default: 100)

### Output & Performance

- **`output_dir`**: Output directory (required)
- **`use_gpu`**: Enable GPU acceleration (default: true)

## Output Files

### Primary Outputs

1. **`methyl_modeler_classifier.pkl`** - Trained model for MethylClassifier
2. **`methyl_modeler_selected_dmps.csv`** - Final DMP set used in classifier
3. **`methyl_modeler_all_dmps.csv`** - All detected DMPs (pre-binary search)
4. **`methyl_modeler_summary.json`** - Complete analysis metadata

### Additional Outputs

5. **`methyl_modeler_gene_weights.csv`** - Gene-level feature importance
6. **`volcano_plot.html`** - Interactive volcano plot
7. **`dmp_heatmap.html`** - DMP methylation heatmap
8. **`validation_results.json`** - Validation metrics

## Documentation

📚 **[Comprehensive Documentation](docs/METHYLDETECTOR_COMPREHENSIVE_DOCUMENTATION.modeler)** - Complete guide covering:
- Statistical methods (likelihood ratio tests, FDR correction, effect sizes)
- Biological filtering criteria and rationale
- Binary search algorithm for DMP selection
- Balanced Accuracy vs AUC comparison
- Advanced configuration options
- Usage examples and best practices
- Integration with MethylPipeline

## Examples

### Example 1: Basic DMP Detection

```python
from methyl_modeler import MethylModelerConfig, run_comparison

config = MethylModelerConfig(
    centroid1_path='/centroids/healthy.h5',
    centroid2_path='/centroids/cancer.h5',
    centroid1_name='Healthy',
    centroid2_name='Cancer',
    chrom='1',
    ctx='CG',
    output_dir='/output/basic'
)

result = run_comparison(config)
print(f"Detected {result['n_dmps']} DMPs")
```

### Example 2: With Real Validation Samples

```python
config = MethylModelerConfig(
    centroid1_path='/centroids/healthy.h5',
    centroid2_path='/centroids/cancer.h5',
    centroid1_name='Healthy',
    centroid2_name='Cancer',
    chrom='1',
    ctx='CG',
    
    validation_mode='real',
    centroid1_validation_samples=[
        '/val/healthy1', '/val/healthy2', '/val/healthy3'
    ],
    centroid2_validation_samples=[
        '/val/cancer1', '/val/cancer2'
    ],
    
    output_dir='/output/validated'
)

result = run_comparison(config)
print(f"Validation Balanced Accuracy: {result['validation_balanced_accuracy']:.3f}")
```

### Example 3: Strict Biological Filtering

```python
config = MethylModelerConfig(
    centroid1_path='/centroids/healthy.h5',
    centroid2_path='/centroids/cancer.h5',
    centroid1_name='Healthy',
    centroid2_name='Cancer',
    chrom='1',
    ctx='CG',
    
    # Strict filtering for high-confidence DMPs
    fdr_threshold=0.001,  # Very stringent FDR
    min_delta_mean=0.2,   # Large effect size
    max_bc=0.8,           # Strong discrimination
    min_N_pct=0.2,        # High coverage
    
    target_balanced_accuracy=0.98,  # Higher target
    
    output_dir='/output/strict'
)

result = run_comparison(config)
print(f"High-confidence DMPs: {result['n_dmps']}")
```

### Example 4: Load and Inspect Results

```python
import json
import pandas as pd

# Load summary
with open('/output/detector/methyl_modeler_summary.json') as f:
    summary = json.load(f)

print(f"Total DMPs tested: {summary['total_positions']}")
print(f"Significant DMPs: {summary['n_significant_dmps']}")
print(f"Selected for classifier: {summary['n_selected_dmps']}")
print(f"Target Balanced Accuracy: {summary['target_balanced_accuracy']}")

# Load DMP table
dmps = pd.read_csv('/output/detector/methyl_modeler_selected_dmps.csv')
print(dmps.head())

# Load gene weights
genes = pd.read_csv('/output/detector/methyl_modeler_gene_weights.csv')
top_genes = genes.nlargest(10, 'importance')
print("Top 10 genes:")
print(top_genes[['gene_name', 'importance', 'n_dmps']])
```

### Example 5: Batch Process Multiple Chromosomes

```python
from methyl_modeler import MethylModelerConfig, run_comparison

chromosomes = ['1', '2', '3', 'X']
results = {}

for chrom in chromosomes:
    config = MethylModelerConfig(
        centroid1_path=f'/centroids/healthy/chr{chrom}-CG.h5',
        centroid2_path=f'/centroids/cancer/chr{chrom}-CG.h5',
        centroid1_name='Healthy',
        centroid2_name='Cancer',
        chrom=chrom,
        ctx='CG',
        output_dir=f'/output/chr{chrom}',
        target_balanced_accuracy=0.95
    )
    
    result = run_comparison(config)
    results[chrom] = result['n_dmps']
    print(f"Chr{chrom}: {result['n_dmps']} DMPs")

# Summary
print(f"Total DMPs across chromosomes: {sum(results.values())}")
```

## Why Balanced Accuracy?

MethylModeler uses **Balanced Accuracy** instead of AUC for DMP selection because:

1. **Robust to Class Imbalance**: Works correctly with unbalanced datasets (e.g., 35 healthy vs 12 cancer)
2. **Interpretable**: Simple average of Sensitivity and Specificity
3. **Unbiased**: Treats both classes equally regardless of sample sizes
4. **Validated**: Widely used in medical/genomics research

**Formula**:
$$
\text{Balanced Accuracy} = \frac{\text{Sensitivity} + \text{Specificity}}{2}
$$

See [Classification Documentation](docs/Classification.modeler) for detailed comparison with AUC.

## Integration with MethylPipeline

### Workflow Position

```
MethylCentroid → MethylModeler → MethylClassifier
    (Generate)     (Train Model)    (Predict)
```

### Inputs

- Centroids from **MethylCentroid** (HDF5 files)
- Optional: Validation samples

### Outputs

- Model package (`.pkl`) for **MethylClassifier**
- DMP tables for analysis
- Gene importance for biological interpretation

### Alternative: MethylTrainer

**MethylTrainer** provides similar functionality with more flexibility in validation sample selection.

## Performance

### GPU Acceleration

| Operation | CPU Time | GPU Time | Speedup |
|-----------|----------|----------|---------|
| DMP Detection (1M positions) | 45 min | 3 min | 15x |
| Binary Search (20 iterations) | 60 min | 5 min | 12x |
| Complete Analysis | 105 min | 8 min | 13x |

### Memory Usage

- Typical: 4 GB
- Peak: 8 GB (during binary search)
- Scales linearly with number of positions

## Troubleshooting

### No DMPs Found

**Problem**: `n_dmps = 0` in results

**Solutions**:
```python
# Lower FDR threshold
config.fdr_threshold = 0.05  # Instead of 0.01

# Relax biological filters
config.min_delta_mean = 0.05  # Instead of 0.1
config.max_bc = 0.98          # Instead of 0.95

# Check if centroids are actually different
# Run without filtering first
config.apply_dmp_filtering = False
```

### Cannot Reach Target Balanced Accuracy

**Problem**: Binary search fails to converge

**Solutions**:
```python
# Lower target
config.target_balanced_accuracy = 0.90  # Instead of 0.95

# Increase max DMPs
config.max_dmps = 50000  # Instead of 10000

# Check validation samples are representative
# Verify centroids have sufficient samples
```

### GPU Out of Memory

**Problem**: CUDA out of memory errors

**Solutions**:
```python
# Disable GPU
config.use_gpu = False

# Or cleanup between operations
from methyl_utils import cleanup_gpu_memory
cleanup_gpu_memory()
```

## API Reference

### Main Function

```python
run_comparison(config: MethylModelerConfig) -> Dict[str, Any]
```

Runs complete DMP detection and classifier training workflow.

**Returns**: Dictionary with:
- `n_dmps`: Number of selected DMPs
- `model_path`: Path to saved model package
- `validation_balanced_accuracy`: Validation performance
- `dmp_table_path`: Path to DMP CSV
- `summary_path`: Path to summary JSON

### Configuration Class

```python
class MethylModelerConfig(BaseModel):
    # Centroid specification
    centroid1_path: str
    centroid2_path: str
    centroid1_name: str
    centroid2_name: str
    chrom: str
    ctx: str
    
    # Statistical parameters
    fdr_threshold: float = 0.01
    
    # Biological filtering
    min_delta_mean: float = 0.1
    max_bc: float = 0.95
    min_N_pct: float = 0.1
    
    # Classifier training
    target_balanced_accuracy: float = 0.95
    min_dmps: int = 10
    max_dmps: int = 10000
    
    # Validation
    validation_mode: str = "synthetic"
    
    # Output
    output_dir: str
    use_gpu: bool = True
```

See [Comprehensive Documentation](docs/METHYLDETECTOR_COMPREHENSIVE_DOCUMENTATION.modeler) for complete API reference.

## Contributing

Please ensure:
1. Tests pass: `pytest tests/`
2. Configurations validate: Check with Pydantic
3. Documentation updated

## License

MIT License - see [LICENSE](../../LICENSE) file for details.

## Citation

```bibtex
@software{methylmodeler2024,
  title={MethylModeler: DMP Detection and Bayesian Classifier Training},
  author={MethylPipeline Contributors},
  year={2024},
  url={https://github.com/yourusername/MethylPipeline}
}
```

---

For more information, see:
- [MethylModeler Comprehensive Documentation](docs/METHYLDETECTOR_COMPREHENSIVE_DOCUMENTATION.modeler)
- [MethylPipeline Documentation](../../docs/METHYLPIPELINE_COMPREHENSIVE_DOCUMENTATION.modeler)
