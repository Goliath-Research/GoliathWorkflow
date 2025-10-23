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

Classify samples using a trained model:

```bash
methyl-classifier --model classifier_chr1-CG.pkl \
                  --samples patient_001.h5 patient_002.h5 \
                  --output results.csv
```

### Classification with Configuration File

```bash
methyl-classifier --config example_classification_config.yaml
```

See `configs/example_classification_config.yaml` for a complete example.

### Batch Classification

Classify all samples in a directory:

```bash
methyl-classifier --model classifier_chr1-CG.pkl \
                  --input-dir /path/to/samples/ \
                  --output-dir /path/to/results/
```

## Python API

### Basic Classification

```python
from methyl_classifier import MethylClassifier, ClassifierConfig
from methyl_utils import MethylSample

# Load classifier
config = ClassifierConfig(
    model_path="classifier_chr1-CG.pkl",
    temperature=1.0
)
classifier = MethylClassifier(config)
classifier.load_classifier(config.model_path)

# Load and classify sample
sample = MethylSample.load_from_h5("patient_001.h5")
methylation_data = sample.methylation_levels  # Extract features

prediction = classifier.predict(methylation_data)
probabilities = classifier.predict_proba(methylation_data)

print(f"Prediction: {prediction}")
print(f"Probabilities: {probabilities}")
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
- `model_path`: Path to trained classifier PKL file (from MethylTrainer)
- `temperature`: Temperature for probability calibration (default: 1.0)
- `enable_platt_calibration`: Use Platt scaling if available (default: false)

### Input
- `input_samples`: List of sample paths to classify
- `input_dir`: Directory containing samples (alternative to list)
- `file_pattern`: Pattern to match files (default: "*.h5")

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

