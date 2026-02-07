# MethylClassifier Configuration File Guide

## Overview

MethylClassifier supports JSON configuration files for reproducible classification runs. Use a config file with `--config` (recommended) or pass paths and options via the command line.

## Recommended: Multi-chromosome classification (MethylDetector output)

Typical workflow after running MethylDetector: classify samples using all chromosome classifiers with optional Platt calibration.

**Example:** `configs/PCa_vs_Healthy_classifier_config.json`

```json
{
  "model_dir": "/work/data/david-gladys/all-prostate/detection/PCa_vs_Healthy_optimized",
  "model_path": null,
  "input_path": "/work/data/david-gladys/all-prostate",
  "output_path": "/work/data/david-gladys/all-prostate/classification/PCa_vs_Healthy.csv",
  "temperature": 1.0,
  "enable_platt_calibration": true,
  "trimmed_percentile_low": 0.10,
  "trimmed_percentile_high": 0.01,
  "chromosome_weights": null,
  "debug": false,
  "no_filter": false,
  "log_level": "INFO"
}
```

Run (from `packages/methylclassifier` or use the path relative to your cwd):

```bash
methyl_classifier --config configs/PCa_vs_Healthy_classifier_config.json
```

From the **MethylPipeline repo root** use:

```bash
methyl_classifier --config packages/methylclassifier/configs/PCa_vs_Healthy_classifier_config.json
```

- **model_dir**: MethylDetector output directory containing `classifier-1.pkl`, `classifier-2.pkl`, etc. Set **model_path** to `null` when using **model_dir**.
- **input_path**: Directory of sample folders (each with `{chrom}-CG.h5`, etc.) or path to a single .h5 file/directory.
- **enable_platt_calibration**: Set to `true` if MethylDetector was run with `enable_platt_calibration` so that saved Platt calibrators are used.
- **chromosome_weights**: `null` = compute weights from trimmed-mean effect_size; or e.g. `{"1": 0.4, "2": 0.3}` for fixed weights.

## Basic configuration

### Minimal (single-chromosome)

```json
{
  "model_path": "models/classifier-1-CG.pkl",
  "input_path": "samples/"
}
```

## Configuration fields

### Required

| Field | Type | Description |
|-------|------|-------------|
| `model_path` or `model_dir` | string or null | Single classifier .pkl path, or **directory** with `classifier-{chrom}.pkl` (e.g. MethylDetector `output_dir`). Use `model_dir` + `model_path: null` for multi-chromosome. |
| `input_path` or `samples` | string or array | Path to .h5 file or directory of sample folders; or list of sample directory paths (each with `{chrom}-CG.h5`, etc.) |

### Optional

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `output_path` | string or null | null | CSV file for classification results |
| `temperature` | number | 1.0 | Softmax temperature for probabilities |
| `enable_platt_calibration` | boolean | false | Use pre-fitted Platt calibrator from model if present |
| `trimmed_percentile_low` | number | 0.10 | Lower percentile for chromosome weight (effect_size) |
| `trimmed_percentile_high` | number | 0.01 | Upper percentile for chromosome weight |
| `chromosome_weights` | object or null | null | Fixed weights per chromosome, e.g. `{"1": 0.4, "2": 0.3}`; overrides trimmed-mean when set |
| `debug` | boolean | false | Enable debug output |
| `no_filter` | boolean | false | Process all .h5 without chromosome/context filtering |
| `log_level` | string | `"INFO"` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

## Usage

### Basic Usage

```bash
methyl_classifier --config classification_config.json
```

### Multi-class Model Build

Build a multi-class model (optional BMM centroids) using:

```bash
python build_multiclass_model.py configs/example_multiclass_model.json
```

### With command-line overrides

Command-line arguments override config file values:

```bash
methyl_classifier --config configs/PCa_vs_Healthy_classifier_config.json \
  --model-dir /path/to/detection \
  --input /path/to/samples \
  --output custom_results.csv \
  --debug
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
    debug=False,
    log_level="INFO"
)

# Save to file
config.to_json(Path("my_classification_config.json"))

# Load from file
loaded = ClassificationConfig.from_json(Path("configs/PCa_vs_Healthy_classifier_config.json"))
```

## Example Configurations

### Configuration 1: Fast Production Classification

```json
{
  "model_path": "models/production_classifier-chr1-CG.pkl",
  "input_path": "samples/batch_001/",
  "output_path": "results/batch_001_results.csv",
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
  "debug": false,
  "log_level": "INFO"
}
```

**Use case**: General-purpose classification with automatic method selection

### Multi-chromosome with samples list

Use **samples** instead of **input_path** when you have a list of sample directories:

```json
{
  "model_dir": "/path/to/detection/output",
  "model_path": null,
  "samples": ["/path/to/sample1/", "/path/to/sample2/"],
  "output_path": "results/multi_chromosome_results.csv",
  "temperature": 1.0,
  "enable_platt_calibration": true,
  "trimmed_percentile_low": 0.10,
  "trimmed_percentile_high": 0.01,
  "chromosome_weights": null,
  "debug": false,
  "no_filter": false,
  "log_level": "INFO"
}
```

### Configuration 4: Debug Analysis

```json
{
  "model_path": "models/test_classifier-chr1-CG.pkl",
  "input_path": "samples/problematic_sample.h5",
  "output_path": null,
  "debug": true,
  "no_filter": false,
  "log_level": "DEBUG"
}
```

**Use case**: Debugging specific sample classification issues

## Integration with Other Tools

### MethylModeler Output → MethylClassifier Input

```bash
# Step 1: Train classifier with MethylModeler
md --config detector_config.json

# Step 2: Create classification config using the trained model
cat > classification_config.json << 'EOF'
{
  "model_path": "output/classifier-chr1-CG.pkl",
  "input_path": "new_samples/",
  "output_path": "results/classification.csv"
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
        output_path=f"results/batch_{i:03d}_results.csv"
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
#   "input_path": "samples/"
# }

# Command overrides input path:
methyl_classifier --config config.json --input new_samples/

# Effective configuration:
# - model_path: "models/classifier.pkl" (from config)
# - input_path: "new_samples/" (from command-line)
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

### 3. Separate Configs for Different Stages

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
✅ **Compatible with existing projects** - Similar to MethylModeler
✅ **Command-line overrides available** - Flexibility when needed
✅ **Smart defaults built-in** - No configuration needed for good performance
✅ **Validated schemas** - Clear error messages for invalid configs

Config files make MethylClassifier easier to use in production workflows!

