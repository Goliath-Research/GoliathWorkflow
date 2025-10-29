# MethylClassifier Usage Guide

## Overview

MethylClassifier classifies methylation samples using trained Bayesian models. It loads classifiers trained by MethylTrainer and applies them to new samples.

## Installation

```bash
cd packages/methylclassifier
poetry install
```

## Command-Line Usage

### Basic Classification

Classify samples using a trained model (single chromosome):

```bash
methyl-classifier --model classifier-1-CG.pkl \
                  --samples patient_001.h5 patient_002.h5 \
                  --output results.csv
```

### Multi-Chromosome Classification

Classify samples using all chromosome classifiers from a directory:

```bash
methyl-classifier --model-dir /path/to/classifiers/ \
                  --input samples/ \
                  --output results.csv
```

The directory should contain files matching pattern `classifier-{chrom}.pkl` (e.g., `classifier-1.pkl`, `classifier-2.pkl`). Probabilities from each chromosome classifier are weighted by trimmed-mean effect_size and combined.

### Classification with Configuration File

```bash
methyl-classifier --config example_classification_config.json
```

See `configs/example_classification_config.json` for a complete example. 

For multi-chromosome mode, see `configs/example_multi_chromosome_config.json`.

For classifying a list of samples with merged contexts (CG+CHG+CHH), see `configs/example_samples_list_config.json`.

### Batch Classification

Classify all samples in a directory (single chromosome):

```bash
methyl-classifier --model classifier-1-CG.pkl \
                  --input-dir /path/to/samples/ \
                  --output-dir /path/to/results/
```

### Multi-Chromosome Batch Classification

Classify all samples using multiple chromosome classifiers:

```bash
methyl-classifier --model-dir /path/to/classifiers/ \
                  --input /path/to/samples/ \
                  --output results.csv
```

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

# Or use predefined weights:
# config = ClassifierConfig(
#     model_dir="/path/to/classifiers/",
#     chromosome_weights={'1': 0.4, '2': 0.3, '3': 0.3}
# )

classifier = MethylClassifier(config)

# Classify sample (will combine weighted probabilities from all chromosomes)
prediction = classifier.predict(methylation_data)
probabilities = classifier.predict_proba(methylation_data)

print(f"Multi-chromosome prediction: {prediction}")
print(f"Weighted probabilities: {probabilities}")
print(f"Chromosome weights: {classifier.chromosome_weights}")
```

### Classifying Multiple Samples with Merged Contexts

```python
from methyl_classifier import MethylClassifier, ClassifierConfig

# Load multi-chromosome classifier
config = ClassifierConfig(
    model_dir="/path/to/classifiers/",
    trimmed_percentile=0.10
)
classifier = MethylClassifier(config)

# Load and classify multiple samples (each with merged CG+CHG+CHH contexts)
from methyl_classifier.cli import classify_samples

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

Or using a config file:
```json
{
  "model_dir": "/path/to/classifiers/",
  "samples": [
    "/path/to/sample1/",
    "/path/to/sample2/",
    "/path/to/sample3/"
  ],
  "output_path": "results.csv"
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

## Configuration Parameters

### Model
- `model_path`: Path to trained classifier PKL file (single chromosome) or directory (multi-chromosome mode)
- `model_dir`: Path to directory containing `classifier-{chrom}.pkl` files (alternative to `model_path`)
- `temperature`: Temperature for probability calibration (default: 1.0)
- `enable_platt_calibration`: Use Platt scaling if available (default: false)
- `trimmed_percentile_low`: Lower percentile for trimmed-mean effect_size calculation - removes bottom X% (default: 0.10, range: 0.0-0.5)
- `trimmed_percentile_high`: Upper percentile for trimmed-mean effect_size calculation - removes top X% (default: 0.01, range: 0.0-0.5). High effect_size DMPs are critical for disease classification, so only extreme outliers are removed.
- `chromosome_weights`: Optional predefined chromosome weights dict (e.g., `{'1': 0.4, '2': 0.3, '3': 0.3}`) - bypasses trimmed-mean calculation if provided

### Input
- `input_path`: Path to single .h5 file or directory containing .h5 files (legacy)
- `samples`: List of sample directory paths. Each directory should contain `{chrom}-CG.h5`, `{chrom}-CHG.h5`, `{chrom}-CHH.h5` files for each chromosome. Contexts are automatically merged per chromosome before classification.

### Output
- `output_dir`: Directory for results
- `output_format`: Format for results ("csv", "json", or "both")
- `include_probabilities`: Include class probabilities (default: true)
- `include_metadata`: Include sample metadata (default: true)

### Classification
- `confidence_threshold`: Minimum probability for confident classification (default: 0.5)
- `verbose`: Enable verbose logging (default: true)

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

MethylClassifier is part of the MethylPipeline ecosystem:
- Uses models from **MethylTrainer**
- Classifies samples against **MethylCentroid** references
- Integrates with **MethylUtils** for p-value testing

