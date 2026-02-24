# MethylClassifier

**Bayesian Probabilistic Classifier for DNA Methylation Data**

## Overview

MethylClassifier is a Bayesian probabilistic classifier that assigns DNA methylation samples to biological classes (e.g., healthy vs. cancer) based on their methylation patterns at differentially methylated positions (DMPs). It uses exact Beta distribution likelihoods for mathematically optimal, interpretable classification.

### Key Features

- **Probabilistic Classification**: Exact Beta distribution likelihoods (no approximations or ML training)
- **True Posterior Probabilities**: Bayesian framework provides P(class | data)
- **Missing Data Handling**: Robust to incomplete methylation coverage
- **Multi-class Support**: Single model can classify multiple disease groups
- **Multiple Prediction Modes**: Standard Bayesian, threshold-based, calibrated
- **Temperature Scaling**: Control prediction confidence/sharpness
- **Platt Calibration**: Optional probability calibration for improved confidence estimates
- **No Training Required**: Uses pre-computed Beta parameters from centroids
- **Fast & Efficient**: Batch processing with NumPy/SciPy optimization
- **Hybrid Beta/BMM Likelihoods**: Optional Beta Mixture override for refined DMPs

## Quick Start

### Installation

```bash
cd packages/methylclassifier
poetry install
```

### Basic Usage

```python
from methyl_classifier import MethylClassifier
from methyl_classifier.models.config import ClassifierConfig
import numpy as np

# Load classifier
config = ClassifierConfig(
    model_path="classifier-1-CG.pkl",
    temperature=1.0
)
classifier = MethylClassifier(config)
classifier.load_classifier(config.model_path)

# Prepare sample data (shape: n_samples × n_dmps)
methylation_data = np.random.rand(10, 5000)  # 10 samples, 5000 DMPs

# Get predictions
predictions = classifier.predict(methylation_data)
probabilities = classifier.predict_proba(methylation_data)

print(f"Predicted classes: {predictions}")
print(f"Class probabilities:\n{probabilities}")
```

### Command Line

```bash
methyl_classifier \
    --model classifier-1-CG.pkl \
    --input sample.h5 \
    --output results.csv \
    --temperature 1.0
```

## How It Works

### The Mathematical Foundation

MethylClassifier implements **Naive Bayes classification** with Beta distributions:

1. **Centroids**: Each class (e.g., healthy, cancer) has Beta distribution parameters (α, β) at each DMP position
2. **Likelihood**: For a sample with methylation value x at position i:
   ```
   P(x_i | Class k) = Beta_PDF(x_i; α_k,i, β_k,i)
   ```
3. **Posterior**: Using Bayes' theorem:
   ```
   P(Class k | X) ∝ P(Class k) × ∏ Beta_PDF(x_i; α_k,i, β_k,i)
   ```
4. **Prediction**: Assign to class with highest posterior probability

### Optional Beta Mixture (BMM) Override

When detector-stage BMM refinement is enabled, MethylClassifier can use **Beta Mixture**
likelihoods for those DMPs (and fall back to Beta for the rest). This preserves the
Bayesian formulation while better modeling multi-modal methylation distributions.

### Why Probabilistic Instead of ML?

| Feature | Probabilistic (MethylClassifier) | ML (RF/SVM/NN) |
|---------|----------------------------------|----------------|
| Training | None needed | Synthetic data generation |
| Accuracy | Exact Beta PDF | Finite sample approximation |
| Probabilities | True Bayesian posteriors | Calibrated scores |
| Missing Data | Natural handling | Imputation required |
| Interpretability | Each DMP contributes via likelihood | Black box |

## Classification Algorithm

For each sample:

1. **Extract methylation values** at DMP positions → X = [x₁, x₂, ..., xₙ]
2. **Compute log-likelihoods** for each class:
   ```
   log P(X | Class 0) = Σ log Beta_PDF(x_i; α₀,ᵢ, β₀,ᵢ)
   log P(X | Class 1) = Σ log Beta_PDF(x_i; α₁,ᵢ, β₁,ᵢ)
   ```
3. **Average by available positions** (handles missing data):
   ```
   avg_log_like = Σ log_like / n_available
   ```
4. **Apply temperature scaling** (optional):
   ```
   scaled_log_like = avg_log_like / T
   ```
5. **Convert to probabilities** (softmax):
   ```
   P(Class k | X) = exp(scaled_log_like_k) / Σ exp(scaled_log_like_j)
   ```
6. **Predict**: argmax P(Class k | X)

## Documentation

- **[Theoretical Foundation](docs/MethylClassifier_Theoretical_Foundation.md)** — Beta/Naive Bayes, posterior, BMM option
- **[Implementation (MethylUtils)](docs/METHYLCLASSIFIER_IMPLEMENTATION.md)** — How MethylClassifier uses MethylUtils and MethylDetector output
- **[User Manual](docs/USAGE.md)** — Docker and virtual environment setup, using one or several contexts, improving balanced accuracy
- **[Comprehensive Documentation](docs/METHYLCLASSIFIER_COMPREHENSIVE_DOCUMENTATION.md)** — Full API, mathematical theory, algorithm, examples, troubleshooting
- **[Config File Guide](CONFIG_FILE_GUIDE.md)** — Configuration schema and options
- **Effect size and classifier accuracy:** See [MethylDetector CLASSIFIER_WEIGHTS_AND_ACCURACY](../methyldetector/docs/CLASSIFIER_WEIGHTS_AND_ACCURACY.md) for how effect_size flows into the classifier

## Examples

### Example 1: Single Sample Classification

```python
from pathlib import Path
from methyl_utils import MethylSample
import numpy as np

# Load sample
sample = MethylSample.load_from_h5("patient001/1-CG.h5")

# Extract methylation at DMP positions
dmp_positions = classifier.get_feature_info()['positions']
sample_indices = np.searchsorted(sample.pos, dmp_positions)
valid = (sample_indices < len(sample.pos)) & (sample.pos[sample_indices] == dmp_positions)

methylation = np.zeros(len(dmp_positions))
methylation[valid] = sample.mC[sample_indices[valid]] / (
    sample.mC[sample_indices[valid]] + sample.uC[sample_indices[valid]]
)

# Classify
prediction = classifier.predict(methylation.reshape(1, -1), 
                                availability_mask=valid.reshape(1, -1))
proba = classifier.predict_proba(methylation.reshape(1, -1), 
                                 availability_mask=valid.reshape(1, -1))

print(f"Prediction: Class {prediction[0]}")
print(f"P(Healthy): {proba[0, 0]:.3f}")
print(f"P(Cancer): {proba[0, 1]:.3f}")
print(f"Coverage: {np.mean(valid):.1%}")
```

### Example 2: Batch Classification

```python
# Classify multiple samples
methylation_matrix = np.random.rand(100, 5000)  # 100 samples
predictions = classifier.predict(methylation_matrix)
probabilities = classifier.predict_proba(methylation_matrix)

# Get high-confidence predictions
confidence = np.max(probabilities, axis=1)
high_conf = confidence > 0.9
print(f"High confidence predictions: {np.sum(high_conf)} / {len(predictions)}")
```

### Example 3: With Missing Data

```python
# Sample with 30% missing data
methylation = np.random.rand(10, 5000)
methylation[np.random.rand(10, 5000) < 0.3] = np.nan

# Create availability mask
availability = ~np.isnan(methylation)
methylation[np.isnan(methylation)] = 0.0  # Masked positions ignored anyway

# Classify
predictions = classifier.predict(methylation, availability_mask=availability)
print(f"Predictions with {100-np.mean(availability)*100:.0f}% missing data: {predictions}")
```

## Model Training

Models are trained using **MethylModeler**:

1. **Create centroids** from sample groups (healthy/cancer) using MethylCentroid
2. **Detect DMPs** using MethylModeler (statistical + biological filtering)
3. **Select optimal DMPs** via binary search with Balanced Accuracy
4. **Save classifier** as .pkl file with Beta parameters and metadata

## Multi-class Model (Beta/BMM)

You can build a **multi-class** classifier (e.g., healthy + multiple cancers) using a
single DMP list and per-class centroids. If BMM centroids are available, the model
will use Beta Mixture likelihoods for those DMPs.

```bash
python build_multiclass_model.py configs/example_multiclass_model.json
```

See `configs/example_multiclass_model.json` for the full schema.

The resulting `.pkl` can be used with the same CLI or Python API.

See MethylModeler documentation for training pipeline details.

## Model Format

Models are saved as pickle files (.pkl) containing:

```python
{
    'classifier': ProbabilisticBetaClassifier,
    'metadata': {
        'chromosome': '1',
        'context': 'CG',
        'n_dmps': 5000,
        'validation_accuracy': 0.956,
        'centroid1_name': 'healthy',
        'centroid2_name': 'cancer',
        ...
    },
    'data': {
        'positions': array([...]),
        'alpha1': array([...]),  # Beta params for class 0
        'beta1': array([...]),
        'alpha2': array([...]),  # Beta params for class 1
        'beta2': array([...]),
        ...
    }
}
```

## Advanced Features

### Temperature Scaling

Control prediction confidence:

```python
# Default: T=1.0 (standard Bayesian)
classifier.classifier.set_temperature(1.0)

# Softer predictions: T>1.0 (less confident, closer to 0.5)
classifier.classifier.set_temperature(2.5)

# Sharper predictions: T<1.0 (more confident, closer to 0/1)
classifier.classifier.set_temperature(0.5)
```

### Platt Calibration

Improve probability calibration:

```python
# Enable during classification (uses pre-fitted calibrator)
config = ClassifierConfig(
    model_path="classifier-1-CG.pkl",
    enable_platt_calibration=True
)
classifier = MethylClassifier(config)
calibrated_proba = classifier.predict_proba(X)
```

### Threshold-Based Prediction

Analytical decision-making using LLR:

```python
results = classifier.predict_with_threshold(
    methylation_data,
    adjust_for_missing=True
)
print(f"Decision: {results['decision'][0]}")
print(f"Sum LLR: {results['sumLLR'][0]:.2f}")
```

## API Reference

### Main Classes

- **`MethylClassifier`**: High-level classifier interface
- **`ProbabilisticBetaClassifier`**: Low-level Beta distribution classifier
- **`ClassifierConfig`**: Configuration for MethylClassifier

### Key Methods

- **`predict(X, availability_mask, debug)`**: Predict class labels
- **`predict_proba(X, availability_mask, debug)`**: Predict posterior probabilities
- **`predict_with_threshold(X, ...)`**: Threshold-based classification
- **`get_feature_info()`**: Get DMP feature information

See [full API reference](docs/METHYLCLASSIFIER_COMPREHENSIVE_DOCUMENTATION.md#api-reference) for details.

## Troubleshooting

### Common Issues

**Dimension mismatch**: Ensure sample has all DMP positions or use availability mask

**Low confidence**: Check coverage, temperature, and model calibration

**Import errors**: Ensure MethylUtils is installed and in PYTHONPATH

**NaN predictions**: Check for invalid Beta parameters or all-missing data

See [troubleshooting guide](docs/METHYLCLASSIFIER_COMPREHENSIVE_DOCUMENTATION.md#troubleshooting) for solutions.

## Integration with MethylPipeline

MethylClassifier is part of the MethylPipeline ecosystem:

1. **MethylCentroid** → Create centroids from samples
2. **MethylModeler** → Detect DMPs and train models
3. FeatureCuts/Bayesian optimization → Optimize DMP selection
4. **MethylClassifier** → Classify new samples (this package)
5. **MethylMapper** → Map DMPs to genes + disease context
6. **MethylEnricher** → Functional enrichment analysis on MethylMapper outputs

### Running MethylClassifier with MethylDetector output

You can run MethylClassifier as soon as MethylDetector has finished. You do **not** need to wait for MethylMapper or MethylEnricher.

1. **Model directory**: Use MethylDetector’s `output_dir` as MethylClassifier’s `model_dir`. That directory contains the per-chromosome classifier files (`classifier-1.pkl`, `classifier-2.pkl`, …, `classifier-X.pkl`, `classifier-Y.pkl`) produced by MethylDetector.

2. **Input**: Point `input_path` to your sample data:
   - A **directory** of sample folders (each with per-chromosome `.h5` files such as `1-CG.h5`, `1-CHG.h5`, …), or
   - A **single** sample directory or `.h5` path, depending on what the classifier expects.

3. **Example config** (e.g. `configs/PCa_vs_Healthy_classifier_config.json`):

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

Set **enable_platt_calibration** to `true` when MethylDetector was run with Platt calibration. Leave **chromosome_weights** as `null` to compute weights from trimmed-mean effect_size.

4. **Run**:

```bash
methyl_classifier --config configs/PCa_vs_Healthy_classifier_config.json
```

Override paths from the command line if needed:

```bash
methyl_classifier --config configs/PCa_vs_Healthy_classifier_config.json \
  --model-dir /path/to/detection/output \
  --input /path/to/samples \
  --output results.csv
```

## Performance

- **Speed**: ~1-10 ms per sample (5000 DMPs)
- **Memory**: ~100 MB per 10,000 DMPs
- **Scalability**: Batch processing for thousands of samples

## License

MIT License - see LICENSE file for details.

## Citation

If you use MethylClassifier in your research, please cite:

```
[Citation to be added]
```

## Support

- **Documentation**: [Full Documentation](docs/METHYLCLASSIFIER_COMPREHENSIVE_DOCUMENTATION.md)
- **Issues**: GitHub Issues
- **Email**: support@methylpipeline.org
