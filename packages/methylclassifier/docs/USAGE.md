# MethylClassifier Usage Guide

## Overview

MethylClassifier classifies methylation samples using trained Bayesian models. It loads classifiers produced by **MethylDetector** (per-chromosome) or single trained models and applies them to new samples. Classification can use a JSON config file or command-line arguments.

## Installation

```bash
cd packages/methylclassifier
poetry install
```

## Command-Line Usage

### Classification with configuration file (recommended)

Use a JSON config file for reproducible runs. Example for **multi-chromosome** mode (MethylDetector output) with Platt calibration:

```bash
# From the methylclassifier package directory:
methyl_classifier --config configs/PCa_vs_Healthy_classifier_config.json

# From the MethylPipeline repo root:
methyl_classifier --config packages/methylclassifier/configs/PCa_vs_Healthy_classifier_config.json
```

Example config (`configs/PCa_vs_Healthy_classifier_config.json`):

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

- **model_dir**: Directory containing `classifier-{chrom}.pkl` files (e.g. MethylDetector `output_dir`). Use this for multi-chromosome mode; set **model_path** to `null`.
- **input_path**: Path to a directory of sample folders (each with `{chrom}-CG.h5`, etc.) or to a single .h5 file/directory.
- **output_path**: CSV file for classification results.
- **enable_platt_calibration**: Use pre-fitted Platt calibrator from the model if available (set to `true` when MethylDetector was run with `enable_platt_calibration`).
- **trimmed_percentile_low** / **trimmed_percentile_high**: Used to compute chromosome weights from effect sizes when **chromosome_weights** is `null` and **weight_method** is not `linear_fitted`.
- **weight_method**: How to obtain chromosome weights: `config`, `effect_size`, `linear_fitted`, `logistic_fitted`, or `elasticnet_fitted`. If omitted, inferred: `config` when **chromosome_weights** is set, else `effect_size`.
- **Fitted methods** (`linear_fitted`, `logistic_fitted`, `elasticnet_fitted`) require labeled validation data (e.g. centroid validation). Weights are fitted from per-chromosome P(class1) and class labels, then projected to non-negative and sum-to-one. **linear_fitted**: linear regression (or Ridge/Lasso). **logistic_fitted**: LogisticRegression (L1/L2 or unpenalized). **elasticnet_fitted**: ElasticNet regression (L1/L2 mix via **weight_fit_l1_ratio**).
- **weight_fit_regularization**: For `linear_fitted`: `none`, `ridge`, or `lasso`. For `logistic_fitted`: `none`, `l1`, or `l2`. For `elasticnet_fitted`: ignored. Default `none`.
- **weight_fit_alpha**: Regularization strength (inverse of C for logistic). Default `1.0`.
- **weight_fit_l1_ratio**: For `elasticnet_fitted` only: balance L1/L2 (0=ridge-like, 1=lasso-like). Default `0.5`.
- **project_name**: When set, after classification the classifier is saved as `<project_name>-classifier.pkl` and the list of sample folders as `<project_name>-samples.txt` (or .csv) in the same directory as the classification output. You can override paths with **save_classifier_path** and **samples_list_export_path**.

Override paths from the command line if needed:

```bash
methyl_classifier --config configs/PCa_vs_Healthy_classifier_config.json \
  --model-dir /path/to/detection/output \
  --input /path/to/samples \
  --output /path/to/classification/results.csv
```

### Single-chromosome classification

Classify using one trained model (single chromosome/context):

```bash
methyl_classifier --model classifier-1-CG.pkl \
                  --input samples/ \
                  --output results.csv
```

### Multi-chromosome classification (CLI only)

```bash
methyl_classifier --model-dir /path/to/classifiers/ \
                  --input /path/to/samples/ \
                  --output results.csv
```

The directory must contain files matching `classifier-{chrom}.pkl` (e.g. `classifier-1.pkl`, `classifier-2.pkl`). Probabilities from each chromosome are combined using weights from **weight_method**: trimmed-mean effect_size (default), predefined **chromosome_weights** (`config`), or **linear_fitted** (fit from validation data when centroid validation is used).

### Alternative: samples list in config

Instead of **input_path**, you can pass a list of sample directories in the config (**samples**). Each directory should contain `{chrom}-CG.h5` (and optionally CHG/CHH) per chromosome. See `CONFIG_FILE_GUIDE.md` for the full schema.

## Python API

### Basic Classification (Single Chromosome)

```python
from methyl_classifier import MethylClassifier, ClassifierConfig
from methyl_utils import MethylSample

# Load single classifier
config = ClassifierConfig(
    model_path="classifier-1-CG.pkl",
    temperature=1.0
)
classifier = MethylClassifier(config)

# Load and classify sample
sample = MethylSample.load_from_h5("patient_001.h5")
methylation_data = sample.methylation_levels  # Extract features

prediction = classifier.predict(methylation_data)
probabilities = classifier.predict_proba(methylation_data)

print(f"Prediction: {prediction}")
print(f"Probabilities: {probabilities}")
```

### Multi-Chromosome Classification

```python
from methyl_classifier import MethylClassifier, ClassifierConfig

# Load all chromosome classifiers from directory
config = ClassifierConfig(
    model_dir="/path/to/classifiers/",  # Contains classifier-1.pkl, classifier-2.pkl, etc.
    temperature=1.0,
    trimmed_percentile_low=0.10,   # Remove bottom 10% of effect sizes (less informative DMPs)
    trimmed_percentile_high=0.01   # Remove only top 1% of effect sizes (outliers, preserving important DMPs)
)

# Or use predefined weights (weight_method="config"):
# config = ClassifierConfig(
#     model_dir="/path/to/classifiers/",
#     chromosome_weights={'1': 0.4, '2': 0.3, '3': 0.3}
# )
# Or fit weights from validation data (weight_method="linear_fitted"):
# config = ClassifierConfig(model_dir="/path/to/classifiers/", weight_method="linear_fitted")
# Then call classifier.fit_chromosome_weights(chrom_proba_matrix, labels, method="linear", regularization="ridge", alpha=1.0)
# with (n_samples x n_chroms) chrom_proba_matrix and binary labels.

classifier = MethylClassifier(config)

# Classify sample (will combine weighted probabilities from all chromosomes)
prediction = classifier.predict(methylation_data)
probabilities = classifier.predict_proba(methylation_data)

print(f"Multi-chromosome prediction: {prediction}")
print(f"Weighted probabilities: {probabilities}")
print(f"Chromosome weights: {classifier.chromosome_weights}")
```

### Classifying multiple samples with merged contexts

```python
from methyl_classifier import MethylClassifier, ClassifierConfig
from methyl_classifier.cli import classify_samples

config = ClassifierConfig(
    model_dir="/path/to/classifiers/",
    trimmed_percentile_low=0.10,
    trimmed_percentile_high=0.01,
    enable_platt_calibration=True,
)
classifier = MethylClassifier(config)

sample_dirs = [
    "/path/to/sample1/",  # Contains 1-CG.h5, 1-CHG.h5, 1-CHH.h5, etc.
    "/path/to/sample2/",
    "/path/to/sample3/"
]

classify_samples(
    classifier=classifier,
    samples_list=sample_dirs,
    output_file="results.csv",
    debug=False
)
```

Or use a config file with **samples** instead of **input_path**:
```json
{
  "model_dir": "/path/to/classifiers/",
  "model_path": null,
  "samples": ["/path/to/sample1/", "/path/to/sample2/"],
  "output_path": "results.csv",
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

### Classification with P-Values

Test if samples belong to centroids:

```python
from methyl_utils import MethylSample

# Load centroids and test sample
centroid_healthy = MethylSample.load_from_h5("healthy_centroid.h5")
centroid_cancer = MethylSample.load_from_h5("cancer_centroid.h5")
test_sample = MethylSample.load_from_h5("patient_001.h5")

# Test goodness of fit
p_healthy = centroid_healthy.prob_belongs(test_sample)
p_cancer = centroid_cancer.prob_belongs(test_sample)

print(f"P(belongs to healthy): {p_healthy:.4f}")
print(f"P(belongs to cancer): {p_cancer:.4f}")

# Interpret results
if p_healthy > 0.05 and p_cancer < 0.05:
    print("Classification: Healthy (high confidence)")
elif p_cancer > 0.05 and p_healthy < 0.05:
    print("Classification: Cancer (high confidence)")
elif p_healthy > 0.05 and p_cancer > 0.05:
    print("Ambiguous: Fits both centroids")
else:
    print("Outlier: Doesn't fit either centroid")
```

## Configuration parameters (config JSON)

When using `--config`, the JSON file can include:

### Model
| Field | Type | Description |
|-------|------|-------------|
| `model_dir` | string or null | Directory with `classifier-{chrom}.pkl` (multi-chromosome; e.g. MethylDetector output_dir) |
| `model_path` | string or null | Single classifier .pkl (single-chromosome). Use `null` when using `model_dir` |
| `temperature` | number | Softmax temperature (default: 1.0) |
| `enable_platt_calibration` | boolean | Use pre-fitted Platt calibrator from model if present (default: false) |
| `trimmed_percentile_low` | number | Lower percentile for chromosome weight from effect_size (default: 0.10) |
| `trimmed_percentile_high` | number | Upper percentile for chromosome weight (default: 0.01) |
| `chromosome_weights` | object or null | Optional `{"1": 0.4, "2": 0.3, ...}`; if set, overrides trimmed-mean weights |

### Input / output
| Field | Type | Description |
|-------|------|-------------|
| `input_path` | string | Path to .h5 file or directory of sample folders (required unless `samples` is set) |
| `samples` | array of strings | Alternative: list of sample directory paths (each with `{chrom}-CG.h5`, etc.) |
| `output_path` | string or null | Output CSV path for classification results |

### Run options
| Field | Type | Description |
|-------|------|-------------|
| `debug` | boolean | Extra debug output (default: false) |
| `no_filter` | boolean | Process all .h5 without chromosome/context filter (default: false) |
| `log_level` | string | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `"INFO"`) |

## Output Format

### CSV Output

```csv
sample_id,prediction,probability_class0,probability_class1,confidence,classification
patient_001,1,0.15,0.85,high,Cancer
patient_002,0,0.92,0.08,high,Healthy
patient_003,1,0.45,0.55,low,Cancer
```

### JSON Output

```json
{
  "patient_001": {
    "prediction": 1,
    "probabilities": [0.15, 0.85],
    "class_names": ["Healthy", "Cancer"],
    "confidence": "high",
    "classification": "Cancer"
  }
}
```

## Model Information

Trained models contain:
- `classifier`: ProbabilisticBetaClassifier instance
- `metadata`: Training information (chromosome, context, DMPs, accuracy)
- `selected_dmps_df`: DataFrame of selected DMPs

To inspect a model:

```python
import pickle

with open("classifier_chr1-CG.pkl", "rb") as f:
    model_package = pickle.load(f)
    
print(f"Chromosome: {model_package['metadata']['chromosome']}")
print(f"Context: {model_package['metadata']['context']}")
print(f"Number of DMPs: {model_package['metadata']['n_dmps']}")
print(f"Validation accuracy: {model_package['metadata']['validation']['overall_accuracy']:.2%}")
```

## Quality Control

Use `prob_belongs()` for quality control:

```python
from methyl_utils import MethylSample

# Load reference centroids
centroid_ref = MethylSample.load_from_h5("reference_centroid.h5")

# Check if samples belong
samples = ["sample_001.h5", "sample_002.h5", "sample_003.h5"]
outliers = []

for sample_path in samples:
    sample = MethylSample.load_from_h5(sample_path)
    p_value = centroid_ref.prob_belongs(sample)
    
    if p_value < 0.01:  # Strict threshold
        outliers.append((sample_path, p_value))
        print(f"⚠️  {sample_path}: Outlier detected (p={p_value:.6f})")
    else:
        print(f"✓  {sample_path}: Normal (p={p_value:.4f})")

print(f"\nFound {len(outliers)} outliers out of {len(samples)} samples")
```

## Troubleshooting

### Model Loading Errors
- Verify model file exists and is readable
- Check pickle compatibility (models trained with older versions may have issues)
- Use CustomUnpickler for backward compatibility

### Low Confidence Classifications
- Check sample quality (coverage, methylation levels)
- Use `prob_belongs()` to verify sample belongs to known groups
- Consider retraining model with more DMPs

### Memory Issues
- Process samples in batches
- Use GPU if available (`use_gpu=True`)
- Reduce number of concurrent samples

## Integration

### Aggregating MethylDetector outputs (multi-chromosome)

After **MethylDetector** has been run for all chromosomes, it writes one classifier per chromosome in its output directory (e.g. `classifier-1.pkl`, `classifier-2.pkl`, ...). **MethylClassifier** can load that directory and aggregate all chromosome classifiers:

1. Set **MethylDetector** `output_dir` (e.g. `/path/to/PCa_vs_Healthy_optimized`) so it contains `classifier-{chrom}.pkl` for each chromosome.
2. Point **MethylClassifier** at that directory with **multi-chromosome mode**:
   - Config: `"model_dir": "/path/to/PCa_vs_Healthy_optimized"` (and `"model_path": null`).
   - CLI: `methyl-classifier --model-dir /path/to/PCa_vs_Healthy_optimized --input /path/to/samples/ --output results.csv`
3. MethylClassifier will load all `classifier-*.pkl` files, compute chromosome weights from the saved DMP weights (trimmed-mean), and combine predictions with a weighted average of per-chromosome probabilities.

Sample directories for classification should contain `{chrom}-CG.h5` (and optionally `{chrom}-CHG.h5`, `{chrom}-CHH.h5`) per chromosome, as expected by the data loader.

MethylClassifier is part of the MethylPipeline ecosystem:
- Uses models from **MethylDetector** (per-chromosome classifiers) or single trained models
- Classifies samples against **MethylCentroid** references
- Integrates with **MethylUtils** for p-value testing

