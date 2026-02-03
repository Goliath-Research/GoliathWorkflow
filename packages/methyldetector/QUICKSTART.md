# MethylDetector Quick Start Guide

This guide will help you get MethylDetector up and running quickly.

## Prerequisites

- Docker and Docker Compose (if using container)
- NVIDIA GPU with CUDA support (optional, but recommended)
- Python 3.8+ (if running directly)

## Quick Start

### 1. Basic Configuration

Create a JSON configuration file with only the essential parameters:

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
  "biological_filters": ["bhattacharyya"],
  "use_gpu": true
}
```


### 2. Run Analysis

```bash
# From command line
./detector config.json

# With verbose output
./detector config.json --verbose

# With log file
./detector config.json --log-file output.log
```

### 3. Check Results

After completion, check your output directory:

```
output/
├── dmps-1.csv              # All biological DMPs
├── dmps-1-3-optimized.csv  # Final optimized DMPs
├── classifier-1.pkl        # Trained classifier
├── results-1.json          # Validation results
└── bmm_centroids/          # BMM centroids (if refinement enabled)
```

## Multi-Chromosome Processing

Process multiple chromosomes in a single run:

```json
{
  "chromosome": ["1", "2", "3", "X"],
  "contexts": ["CG"],
  "centroid1_dir": "/path/to/healthy/centroids",
  "centroid2_dir": "/path/to/cancer/centroids",
  "output_dir": "/path/to/output"
}
```

Each chromosome will be processed independently and generate separate output files.

## Multi-Context Analysis

Process multiple methylation contexts (CG, CHG, CHH) together:

```json
{
  "chromosome": "1",
  "contexts": ["CG", "CHG", "CHH"],
  "centroid1_dir": "/path/to/healthy/centroids",
  "centroid2_dir": "/path/to/cancer/centroids",
  "output_dir": "/path/to/output",
  "use_context_weights": true
}
```

Contexts will be automatically weighted based on their biological importance.

## Using Python API

```python
from methyl_detector.models.config import MethylModelerConfig
from methyl_detector.core.methyldetector import MethylDetector
from methyl_detector.utils.file_utils import load_config_from_json

# Load configuration
config = load_config_from_json("config.json")

# Initialize and run
detector = MethylDetector(config)
result = detector.run()

# Handle results (single or multiple chromosomes)
if isinstance(result, list):
    print(f"Processed {len(result)} chromosomes")
    for i, r in enumerate(result):
        print(f"Chromosome {i+1}: {r.total_biological_dmps:,} DMPs")
else:
    print(f"Found {result.total_biological_dmps:,} DMPs")
```

## Configuration Examples

### Minimal Configuration

```json
{
  "chromosome": "1",
  "contexts": ["CG"],
  "centroid1_dir": "/centroids/healthy",
  "centroid2_dir": "/centroids/cancer",
  "output_dir": "/output"
}
```

### With Optimization

```json
{
  "chromosome": "1",
  "contexts": ["CG"],
  "centroid1_dir": "/centroids/healthy",
  "centroid2_dir": "/centroids/cancer",
  "output_dir": "/output",
  "optimize_dmps": true,
  "optimization_method": "featurecuts",
  "target_balanced_accuracy": 0.95
}
```

### With Real Validation Samples

```json
{
  "chromosome": "1",
  "contexts": ["CG"],
  "centroid1_dir": "/centroids/healthy",
  "centroid2_dir": "/centroids/cancer",
  "output_dir": "/output",
  "validation_mode": "real",
  "validation_split_ratio": 0.2,
  "centroid1_validation_samples": [
    "/samples/healthy1",
    "/samples/healthy2"
  ],
  "centroid2_validation_samples": [
    "/samples/cancer1",
    "/samples/cancer2"
  ],
  "optimize_dmps": true
}
```

### Using Metadata for Validation

```json
{
  "chromosome": "1",
  "contexts": ["CG"],
  "centroid1_dir": "/centroids/healthy",
  "centroid2_dir": "/centroids/cancer",
  "output_dir": "/output",
  "validation_mode": "real",
  "centroid1_validation_samples": "use_metadata",
  "centroid2_validation_samples": "use_metadata"
}
```

This will read sample paths from the centroid HDF5 file metadata.

## Data Format

### Centroid Files

Centroid files must be in HDF5 format with naming:
- Format: `{chromosome}-{context}.h5`
- Example: `1-CG.h5`, `1-CHG.h5`, `X-CG.h5`

Files should be in the directories specified by `centroid1_dir` and `centroid2_dir`.

### Validation Samples

Validation samples can be:
- Directory paths containing `.h5` files with format `{chromosome}-{context}.h5`
- Or `"use_metadata"` to read from centroid file metadata

## Output Files

### Per Chromosome Outputs

- **`dmps-{chromosome}.csv`**: All biological DMPs with full metadata
- **`dmps-{chromosome}-1-biological.csv`**: Stage 1 biological DMPs (if optimization enabled)
- **`dmps-{chromosome}-2-pre-optimization.csv`**: Stage 2 pre-optimization DMPs
- **`dmps-{chromosome}-3-optimized.csv`**: Stage 3 final optimized DMPs
- **`classifier-{chromosome}.pkl`**: Trained BetaClassifier model
- **`results-{chromosome}.json`**: Validation results and summary

### CSV Columns

Each DMP CSV includes:
- Position information: `chromosome`, `context`, `position`
- Statistics: `p_value`, `q_value`, `delta_mean`, `delta_sign`
- Biological metrics: `overlap`, `effect_size`, `context_weight`
- Beta parameters: `alpha1`, `beta1`, `alpha2`, `beta2`
- Mean methylation: `mean1`, `mean2`

## Troubleshooting

### No DMPs Found

If you get 0 biological DMPs, try relaxing filters:

```json
{
  "alpha": 0.05,          // Increase from 0.01
  "min_delta_mean": 0.1,  // Decrease from 0.2
  "max_bc": 0.8          // Increase from 0.5
}
```

### GPU Out of Memory

Disable GPU if you encounter memory errors:

```json
{
  "use_gpu": false
}
```

### Validation Errors

Ensure validation samples exist and are accessible:

```bash
# Check sample directories exist
ls /path/to/validation/samples/

# Check H5 files are present
ls /path/to/validation/samples/*/1-CG.h5
```

### Configuration Validation Errors

Common issues:
- `centroid1_dir` and `centroid2_dir` must exist and be directories
- `chromosome` must be valid (1-22, X, Y, M, MT)
- `contexts` must be valid (CG, CHG, CHH)
- File format: `{chromosome}-{context}.h5`

## Next Steps

1. **Explore Results**: Load and analyze the CSV files
2. **Use Classifier**: Load the `.pkl` file with MethylClassifier
3. **Multi-Chromosome**: Try processing multiple chromosomes
4. **Context Selection**: Experiment with different context combinations

See the [main README](README.md) for complete documentation.
