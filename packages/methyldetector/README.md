# MethylDetector

**Detect Differentially Methylated Positions and Train Bayesian Classifiers**

## Overview

MethylDetector is a production-ready package for detecting Differentially Methylated Positions (DMPs) between two methylation centroids. It combines statistical rigor (Storey's q-value FDR correction) with biological filtering to identify meaningful biomarkers for downstream analysis.

### What is MethylDetector?

MethylDetector provides comprehensive DMP detection and analysis:

- **DMP Detection**: Statistical comparison of two centroids with FDR control
- **Biological Filtering**: Effect size and distribution overlap criteria for meaningful DMPs
- **Multi-Chromosome Support**: Process single or multiple chromosomes in one run
- **Multi-Context Support**: Process CG, CHG, CHH contexts together
- **GPU Acceleration**: High-performance processing with NVIDIA GPUs
- **Comprehensive Output**: Detailed DMP tables with statistical metadata

## Key Features

- 🔬 **Statistical Rigor**: Storey's q-value FDR correction (recommended for genomics)
- 📊 **Biological Filtering**: Delta mean, Bhattacharyya coefficient, coverage thresholds
- 🧬 **Multi-Context Support**: Process CG, CHG, CHH contexts together
- 🧬 **Multi-Chromosome Support**: Process multiple chromosomes in a single run
- 🚀 **GPU Acceleration**: High-performance processing with NVIDIA GPUs
- 📊 **Comprehensive Output**: Detailed DMP tables with statistical metadata
- ⚡ **Memory Efficient**: Intelligent chunking for large genomic datasets
- ✅ **Type Safe**: Full type hints with comprehensive validation
- 📋 **Clean Configuration**: Simplified parameter management with validation warnings

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
  "max_bc": 0.6,
  "biological_filters": ["bhattacharyya"]
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
  "max_bc": 0.6,
  "biological_filters": ["bhattacharyya"]
}
```

Each chromosome will:
- Process independently with its own centroids
- Generate separate output files: `dmps-1.csv`, `dmps-2.csv`, etc.
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
- **`biological_filters`**: List of filters to apply (default: `["delta_mean", "bhattacharyya"]`)

### Context Weighting

- **`use_context_weights`**: Enable context weighting for multi-context analysis (default: `true`)

### Performance

- **`use_gpu`**: Enable GPU acceleration (default: `true`)
- **`random_state`**: Random seed for reproducibility (default: `42`)

## Output Files

### Per Chromosome

1. **`dmps-{chromosome}.csv`** - All biological DMPs with full metadata
2. **`dmps-{chromosome}-biological-sorted.csv`** - Biological DMPs sorted by significance

`results-{chromosome}.json` includes `bmm_summary` and `bmm_centroid_files` when BMM refinement runs.

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

5. Generate Reports
   ├─ DMP tables (CSV) with full statistical metadata
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

## Statistical Rigor

MethylDetector uses **Storey's q-value FDR correction** for multiple testing correction:

- **Adaptive FDR control**: Adjusts for different proportions of true null hypotheses
- **Recommended for genomics**: Superior to Bonferroni correction for large datasets
- **q ≤ α threshold**: Controls false discovery rate at specified level
- **Biological filtering**: Additional effect size and overlap criteria for meaningful DMPs

## Integration with MethylPipeline

### Workflow Position

```
MethylCentroid → MethylDetector → Downstream Analysis
    (Generate)     (DMP Detection)   (Gene mapping, enrichment, etc.)
```

### Inputs

- Centroids from **MethylCentroid** (HDF5 files in directory format)

### Outputs

- DMP tables (CSV) for downstream analysis
- Statistical metadata for each significant position
- Ready for gene mapping, functional enrichment, and biomarker discovery

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

### Too Many DMPs Detected

**Problem**: `dmps-{chromosome}.csv` contains too many positions

**Solutions**:
```json
{
  "alpha": 0.001,  // Stricter FDR threshold
  "min_delta_mean": 0.3,  // Higher effect size threshold
  "max_bc": 0.4  // Less overlap allowed
}
```

### Too Few DMPs Detected

**Problem**: Very few or no DMPs found

**Solutions**:
```json
{
  "alpha": 0.05,  // Relax FDR threshold
  "min_delta_mean": 0.1,  // Lower effect size threshold
  "max_bc": 0.8  // Allow more overlap
}
```

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
