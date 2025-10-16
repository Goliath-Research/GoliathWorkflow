# MethylClassifier Configuration File Guide

## Overview

MethylClassifier now supports JSON configuration files, similar to MethylDetector and other projects in the pipeline. This improves reproducibility and makes it easier to manage complex classification workflows.

## Basic Configuration

### Minimal Example

```json
{
  "model_path": "models/classifier.pkl",
  "input_path": "samples/"
}
```

### Complete Example

```json
{
  "model_path": "models/classifier-chr1-CG.pkl",
  "input_path": "samples/prostate_cohort/",
  "output_path": "results/classification_results.csv",
  "prediction_method": null,
  "debug": false,
  "no_filter": false,
  "log_level": "INFO"
}
```

## Configuration Fields

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `model_path` | string | Path to trained classifier model (.pkl file) |
| `input_path` | string | Path to input .h5 file or directory containing .h5 files |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `output_path` | string/null | null | CSV file for classification results |
| `prediction_method` | string/null | null | Prediction method: `"sklearn"`, `"beta"`, or `null` (smart default) |
| `debug` | boolean | false | Enable debug output |
| `no_filter` | boolean | false | Process all .h5 files without chromosome/context filtering |
| `log_level` | string | `"INFO"` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

## Prediction Method Options

### `null` (Recommended - Smart Default)

```json
{
  "prediction_method": null
}
```

Automatically chooses:
- **beta** for ≤10 DMPs (fast enough, exact)
- **sklearn** for >10 DMPs (much faster, excellent precision)

### `"sklearn"` (Fast)

```json
{
  "prediction_method": "sklearn"
}
```

Forces sklearn method:
- 28,000x faster than beta (for 20k DMPs)
- 0.15% average difference
- Recommended for production

### `"beta"` (Exact)

```json
{
  "prediction_method": "beta"
}
```

Forces beta method:
- Exact Bayesian inference
- Slower for large DMP sets
- Use for validation or critical samples

## Usage

### Basic Usage

```bash
methyl_classifier --config classification_config.json
```

### With Command-Line Overrides

Command-line arguments override config file values:

```bash
# Override prediction method
methyl_classifier --config config.json --use-sklearn

# Override multiple settings
methyl_classifier --config config.json --use-sklearn --debug --output custom_results.csv
```

### Creating Configs Programmatically

```python
from methyl_classifier.config_schema import ClassificationConfig
from pathlib import Path

# Create config object
config = ClassificationConfig(
    model_path="models/classifier.pkl",
    input_path="samples/",
    output_path="results.csv",
    prediction_method=None,  # Smart default
    debug=False,
    log_level="INFO"
)

# Save to file
config.to_json(Path("my_classification_config.json"))

# Load from file
loaded = ClassificationConfig.from_json(Path("my_classification_config.json"))
```

## Example Configurations

### Configuration 1: Fast Production Classification

```json
{
  "model_path": "models/production_classifier-chr1-CG.pkl",
  "input_path": "samples/batch_001/",
  "output_path": "results/batch_001_results.csv",
  "prediction_method": "sklearn",
  "debug": false,
  "log_level": "INFO"
}
```

**Use case**: High-throughput classification of many samples

### Configuration 2: Validation with Exact Inference

```json
{
  "model_path": "models/validation_classifier-chr1-CG.pkl",
  "input_path": "samples/validation_set/",
  "output_path": "results/validation_results.csv",
  "prediction_method": "beta",
  "debug": true,
  "log_level": "DEBUG"
}
```

**Use case**: Validation studies requiring maximum precision

### Configuration 3: Smart Default for General Use

```json
{
  "model_path": "models/classifier-chr1-CG.pkl",
  "input_path": "samples/",
  "output_path": "results/results.csv",
  "prediction_method": null,
  "debug": false,
  "log_level": "INFO"
}
```

**Use case**: General-purpose classification with automatic method selection

### Configuration 4: Debug Analysis

```json
{
  "model_path": "models/test_classifier-chr1-CG.pkl",
  "input_path": "samples/problematic_sample.h5",
  "output_path": null,
  "prediction_method": null,
  "debug": true,
  "no_filter": false,
  "log_level": "DEBUG"
}
```

**Use case**: Debugging specific sample classification issues

## Integration with Other Tools

### MethylDetector Output → MethylClassifier Input

```bash
# Step 1: Train classifier with MethylDetector
md --config detector_config.json

# Step 2: Create classification config using the trained model
cat > classification_config.json << 'EOF'
{
  "model_path": "output/classifier-chr1-CG.pkl",
  "input_path": "new_samples/",
  "output_path": "results/classification.csv",
  "prediction_method": null
}
EOF

# Step 3: Classify new samples
methyl_classifier --config classification_config.json
```

### Batch Processing Multiple Classifiers

```python
from pathlib import Path
from methyl_classifier.config_schema import ClassificationConfig

# Define multiple classifiers and sample sets
configs = [
    {"model": "chr1-CG.pkl", "samples": "batch_001/"},
    {"model": "chr2-CG.pkl", "samples": "batch_002/"},
    {"model": "chr3-CG.pkl", "samples": "batch_003/"},
]

# Generate config files
for i, cfg in enumerate(configs, 1):
    config = ClassificationConfig(
        model_path=f"models/{cfg['model']}",
        input_path=f"samples/{cfg['samples']}",
        output_path=f"results/batch_{i:03d}_results.csv",
        prediction_method=None
    )
    config.to_json(Path(f"configs/classification_config_{i:03d}.json"))
```

## Command-Line Override Priority

When both config file and command-line arguments are provided:

1. **Config file** provides base configuration
2. **Command-line arguments** override specific values
3. **Result**: Merged configuration

Example:

```bash
# Config file has:
# {
#   "model_path": "models/classifier.pkl",
#   "input_path": "samples/",
#   "prediction_method": "beta"
# }

# Command overrides prediction_method:
methyl_classifier --config config.json --use-sklearn

# Effective configuration:
# - model_path: "models/classifier.pkl" (from config)
# - input_path: "samples/" (from config)
# - prediction_method: "sklearn" (from command-line)
```

## Validation

The config schema validates:
- ✅ Required fields are present
- ✅ Field types are correct
- ✅ Enum values are valid (e.g., log_level)
- ✅ Paths can be parsed

Invalid configs will produce clear error messages:

```bash
$ methyl_classifier --config bad_config.json
❌ Failed to load config file: 1 validation error for ClassificationConfig
model_path
  field required (type=value_error.missing)
```

## Best Practices

### 1. Use Version Control

Store config files in git to track classification parameters:

```bash
git add configs/classification_*.json
git commit -m "Add classification configs for prostate cancer cohort"
```

### 2. Descriptive Names

Use meaningful names for config files:

✅ Good:
- `classification_prostate_chr1_CG.json`
- `validation_set_exact_inference.json`
- `production_fast_sklearn.json`

❌ Bad:
- `config.json`
- `test.json`
- `config1.json`

### 3. Document Prediction Method Choices

Add comments in commit messages explaining why you chose a specific method:

```bash
git commit -m "Use sklearn method for production (28,000x faster, 0.15% diff acceptable)"
```

### 4. Use Smart Defaults

Unless you have a specific reason, use `prediction_method: null`:

```json
{
  "prediction_method": null  // Smart default: sklearn for >10 DMPs, beta for ≤10
}
```

### 5. Separate Configs for Different Stages

```
configs/
├── training_configs/
│   └── detector_chr1_CG.json
└── classification_configs/
    ├── production_classification.json
    ├── validation_classification.json
    └── debug_classification.json
```

## See Also

- [SMART_DEFAULTS.md](SMART_DEFAULTS.md) - Smart prediction method selection
- [PRECISION_ANALYSIS.md](../../PRECISION_ANALYSIS.md) - sklearn vs beta comparison
- [PKL_FLEXIBILITY.md](../../PKL_FLEXIBILITY.md) - Model persistence details
- [PREDICTION_METHOD_USAGE.md](PREDICTION_METHOD_USAGE.md) - API usage guide

## Summary

✅ **Config files improve reproducibility** - Track exact parameters used
✅ **Compatible with existing projects** - Similar to MethylDetector
✅ **Command-line overrides available** - Flexibility when needed
✅ **Smart defaults built-in** - No configuration needed for good performance
✅ **Validated schemas** - Clear error messages for invalid configs

Config files make MethylClassifier easier to use in production workflows!

