# MethylClassifier: Comprehensive Documentation

**Version:** 0.1.0  
**Last Updated:** 2025-10-23

**Related documentation:**
- **Theory (Beta, Naive Bayes, posterior):** [MethylClassifier_Theoretical_Foundation.md](MethylClassifier_Theoretical_Foundation.md)
- **Implementation (MethylUtils):** [METHYLCLASSIFIER_IMPLEMENTATION.md](METHYLCLASSIFIER_IMPLEMENTATION.md)
- **User Manual (Docker, venv, contexts, improving balanced accuracy):** [USAGE.md](USAGE.md)

---

## Table of Contents

1. [Overview](#overview)
2. [Installation](#installation)
3. [Mathematical Theory](#mathematical-theory)
4. [Classification Algorithm](#classification-algorithm)
5. [Usage Guide](#usage-guide)
6. [API Reference](#api-reference)
7. [Model Format](#model-format)
8. [Advanced Features](#advanced-features)
9. [Examples](#examples)
10. [Troubleshooting](#troubleshooting)

---

## Overview

### What is MethylClassifier?

**MethylClassifier** is a Bayesian probabilistic classifier for DNA methylation data that assigns samples to biological classes (e.g., healthy vs. cancer) based on their methylation patterns at differentially methylated positions (DMPs).

### Key Features

- **Probabilistic Classification**: Uses exact Beta distribution likelihoods (no approximations)
- **Bayesian Framework**: Provides true posterior probabilities P(class | data)
- **Handles Missing Data**: Robust to incomplete methylation coverage
- **No Training Required**: Uses pre-computed Beta parameters from centroids
- **Multiple Prediction Modes**:
  - Standard Bayesian (posterior probabilities)
  - Threshold-based (log-likelihood ratio)
  - Calibrated (Platt scaling)
- **Temperature Control**: Softmax temperature for confidence calibration
- **Binary + Multi-class Classification**: Supports two-class and multi-class models (e.g., healthy vs. multiple cancers)
- **Multi-Chromosome Support**: Combine predictions from multiple chromosome classifiers with weighted probabilities based on trimmed-mean effect_size
- **Hybrid Beta/BMM Likelihoods**: Optional Beta Mixture override for refined DMPs (when BMM centroids are available)

### Why Probabilistic Instead of Machine Learning?

Traditional ML approaches (Random Forest, SVM, Neural Networks) require:
- Generating synthetic training data
- Learning from finite samples
- Approximating probability distributions

**MethylClassifier's probabilistic approach:**
- Uses exact Beta distribution parameters from centroids
- No sampling error or approximation
- Mathematically optimal under Bayesian framework
- Direct interpretation of results

---

## Installation

### Requirements

- Python ≥ 3.8
- NumPy ≥ 1.20
- SciPy ≥ 1.7
- scikit-learn (for Platt calibration)
- MethylUtils package

### Install from Source

```bash
cd packages/methylclassifier
poetry install
```

### Verify Installation

```bash
python -c "from methyl_classifier import MethylClassifier; print('✓ MethylClassifier installed')"
```

---

## Mathematical Theory

### The Bayesian Classification Framework

MethylClassifier implements **Naive Bayes classification** using Beta distributions for continuous methylation data.

#### 1. Centroids and Beta Distributions

Each **centroid** (e.g., healthy, cancer) is represented by Beta distribution parameters at each DMP position:

$$
\text{Centroid } k \text{ at position } i:\quad \text{Methylation} \sim \mathrm{Beta}(\alpha_{k,i}, \beta_{k,i})
$$

Where:
- $\alpha$ (alpha): Shape parameter related to methylated counts
- $\beta$ (beta): Shape parameter related to unmethylated counts
- Mean methylation = $\alpha / (\alpha + \beta)$

#### 2. Likelihood Function

For a sample with methylation value $x$ at position $i$, the likelihood under class $k$ is:

$$
P(x_i \mid \text{Class } k) = \mathrm{BetaPDF}(x_i; \alpha_{k,i}, \beta_{k,i})
$$

The Beta probability density function:

$$
\mathrm{BetaPDF}(x; \alpha, \beta) = \frac{x^{\alpha-1}(1-x)^{\beta-1}}{B(\alpha, \beta)}
$$

Where $B(\alpha, \beta)$ is the Beta function (normalization constant).

#### 3. Naive Bayes Assumption

**Assumption**: Methylation values at different DMPs are independent given the class.

This allows us to multiply likelihoods:

$$
P(x_1, x_2, \ldots, x_n \mid \text{Class } k) = \prod_{i=1}^{n} P(x_i \mid \text{Class } k)
$$

#### 4. Posterior Probability (Bayes' Theorem)

Given a sample's methylation pattern $\mathbf{X} = (x_1, x_2, \ldots, x_n)$, we compute posterior probabilities:

$$
P(\text{Class } k \mid \mathbf{X}) = \frac{P(\mathbf{X} \mid \text{Class } k) \cdot P(\text{Class } k)}{P(\mathbf{X})}
$$

Where:
- $P(\mathbf{X} \mid \text{Class } k)$: Likelihood (from Beta distributions)
- $P(\text{Class } k)$: Prior probability (default: 0.5 for binary classification)
- $P(\mathbf{X})$: Evidence (normalizing constant)

#### 5. Log-Space Computation

For numerical stability, we work in log space:

$$
\log P(\text{Class } k \mid \mathbf{X}) \propto \log P(\text{Class } k) + \sum_{i=1}^{n} \log \mathrm{BetaPDF}(x_i; \alpha_{k,i}, \beta_{k,i})
$$

#### 6. Posterior Probabilities

Final posteriors are computed using the **softmax** (log-sum-exp trick):

$$
P(\text{Class } k \mid \mathbf{X}) = \frac{\exp(\log P(\text{Class } k \mid \mathbf{X}))}{\sum_j \exp(\log P(\text{Class } j \mid \mathbf{X}))}
$$

### Why This Works for Methylation Data

1. **Beta distributions naturally model methylation**: Methylation levels ∈ [0,1] are well-represented by Beta distributions
2. **Centroids capture population statistics**: Alpha and beta parameters encode the mean and variance of methylation at each position
3. **DMPs are informative**: Only differentially methylated positions are used (high discriminatory power)
4. **Bayesian optimality**: Under the naive Bayes assumption, this is the optimal classifier

### Implementation (MethylUtils)

MethylClassifier does not implement the Beta likelihood or training; it loads classifiers produced by **MethylDetector**, which uses MethylUtils **BetaClassifier** / **BetaBinomialClassifier** for training. The stored classifier objects are MethylUtils instances; MethylClassifier calls their `.predict_proba()`, `.predict()`, and optionally `.predict_proba_calibrated()` or `.predict_with_threshold()`. Sample loading uses MethylUtils **MethylSample** and **load_from_h5** via the DataLoader. For full details, see [METHYLCLASSIFIER_IMPLEMENTATION.md](METHYLCLASSIFIER_IMPLEMENTATION.md).

---

## Classification Algorithm

### Standard Bayesian Prediction

#### Step 1: Load Model

```python
from methyl_classifier import MethylClassifier
from methyl_classifier.models.config import ClassifierConfig

config = ClassifierConfig(
    model_path="classifier-1-CG.pkl",
    temperature=1.0,
    enable_platt_calibration=False
)
classifier = MethylClassifier(config)
```

#### Step 2: Prepare Sample Data

Input format: **Methylation matrix** of shape (n_samples, n_dmps)
- Values in [0, 1] representing methylation levels (mC / (mC + uC))
- DMPs must match the positions in the trained model
- Missing values can be handled via availability mask

```python
import numpy as np

# Example: 3 samples, 100 DMPs
methylation_data = np.array([
    [0.75, 0.23, 0.89, ...],  # Sample 1
    [0.12, 0.88, 0.45, ...],  # Sample 2
    [0.65, 0.34, 0.91, ...]   # Sample 3
])

# Optional: Mark which positions are available (True) or missing (False)
availability_mask = np.array([
    [True, True, False, ...],
    [True, True, True, ...],
    [True, False, True, ...]
])
```

#### Step 3: Predict

```python
# Get class predictions (0 or 1)
predictions = classifier.predict(methylation_data, availability_mask)
# Output: array([0, 1, 0])

# Get posterior probabilities
probabilities = classifier.predict_proba(methylation_data, availability_mask)
# Output: array([[0.85, 0.15],  # Sample 1: 85% class 0, 15% class 1
#                [0.12, 0.88],  # Sample 2: 12% class 0, 88% class 1
#                [0.73, 0.27]]) # Sample 3: 73% class 0, 27% class 1
```

### Detailed Algorithm Steps

#### For Each Sample:

**1. Extract methylation values at DMP positions**
```
X = [x₁, x₂, ..., xₙ] where n = number of DMPs
```

**2. Clip values to valid range** (avoid numerical issues)
```
X_clipped = clip(X, ε, 1-ε)  where ε = 1e-6
```

**3. Compute log-likelihoods for each class**

For **Class 0** (e.g., Healthy):
```python
log_p_class0 = Σ log Beta_PDF(x_i; α₀,ᵢ, β₀,ᵢ)  for available positions i
```

For **Class 1** (e.g., Cancer):
```python
log_p_class1 = Σ log Beta_PDF(x_i; α₁,ᵢ, β₁,ᵢ)  for available positions i
```

**4. Average by available positions** (handles missing data)
```python
avg_log_like_class0 = log_p_class0 / n_available
avg_log_like_class1 = log_p_class1 / n_available
```

**5. Apply temperature scaling**
```python
scaled_log_like_class0 = avg_log_like_class0 / T
scaled_log_like_class1 = avg_log_like_class1 / T
```
Where T is the temperature parameter (default: 1.0)

**6. Convert to probabilities** (softmax with log-sum-exp)
```python
max_log = max(scaled_log_like_class0, scaled_log_like_class1)
exp_class0 = exp(scaled_log_like_class0 - max_log)
exp_class1 = exp(scaled_log_like_class1 - max_log)

P(Class 0 | X) = exp_class0 / (exp_class0 + exp_class1)
P(Class 1 | X) = exp_class1 / (exp_class0 + exp_class1)
```

**7. Make prediction**
```python
predicted_class = argmax([P(Class 0 | X), P(Class 1 | X)])
```

### Handling Missing Data

The classifier handles missing methylation values robustly:

1. **Availability Mask**: Boolean array indicating which positions have data
2. **Selective Computation**: Only available positions contribute to log-likelihood
3. **Normalization**: Averaged by number of available positions (not total DMPs)

Example:
```python
# Sample with 80% coverage
availability = np.random.rand(100) > 0.2  # 80 True, 20 False

# Classifier automatically handles missing positions
proba = classifier.predict_proba(methylation_data, availability_mask=availability)
```

### Temperature Parameter

The **temperature** controls the "sharpness" of probability predictions:

- **T = 1.0** (default): Standard Bayesian probabilities
- **T > 1.0**: Softer probabilities (more uncertain, probabilities closer to 0.5)
- **T < 1.0**: Sharper probabilities (more confident, probabilities closer to 0 or 1)

Example:
```python
classifier.classifier.set_temperature(2.5)  # Softer predictions
proba = classifier.predict_proba(methylation_data)
```

Useful when:
- Model is overconfident → increase T
- Need more decisive predictions → decrease T
- Calibrating uncertainty → tune T on validation set

---

## Usage Guide

### Multi-Chromosome Classification

MethylClassifier supports combining predictions from multiple chromosome-specific classifiers. This approach:

1. **Loads all classifiers** from a directory matching pattern `classifier-{chrom}.pkl`
2. **Computes chromosome weights** from trimmed-mean effect_size of selected DMPs in each classifier
3. **Runs predictions** through each chromosome classifier independently
4. **Combines weighted probabilities** to produce final classification

#### Weighting Method

Chromosome weights are computed using **asymmetric trimmed-mean** of effect_size values from each classifier's `selected_dmps_df`:

```
For each chromosome:
  1. Extract effect_size values from selected_dmps_df
  2. Compute asymmetric trimmed mean:
     - Remove bottom X% (low effect sizes - less informative DMPs)
     - Remove only top Y% (outliers - preserving high effect_size DMPs that are critical for classification)
  3. Use trimmed mean as raw weight
  4. Normalize all weights to sum to 1.0
```

**Why Asymmetric Trimming?**
In disease classification (e.g., cancer vs. healthy), DMPs with **high effect_size are the most important** for distinguishing between groups. Symmetric trimming (removing equal percentages from both ends) would discard these crucial markers. Asymmetric trimming:
- Removes more low effect_size DMPs (less informative)
- Preserves most high effect_size DMPs (only extreme outliers removed)
- Default: Remove bottom 10%, top 1%

Alternatively, you can provide predefined weights via `chromosome_weights` parameter.

#### Example: Multi-Chromosome Classification

```python
from methyl_classifier import MethylClassifier, ClassifierConfig

# Automatic weight calculation from effect_size with asymmetric trimming
config = ClassifierConfig(
    model_dir="/path/to/classifiers/",  # Contains classifier-1.pkl, classifier-2.pkl, ...
    trimmed_percentile_low=0.10,   # Remove bottom 10% (less informative)
    trimmed_percentile_high=0.01  # Remove only top 1% (preserve important DMPs)
)

# Or use predefined weights
# config = ClassifierConfig(
#     model_dir="/path/to/classifiers/",
#     chromosome_weights={'1': 0.4, '2': 0.3, '3': 0.2, '4': 0.1}
# )

classifier = MethylClassifier(config)

# Classification uses weighted combination of all chromosomes
probas = classifier.predict_proba(methylation_data)
predictions = classifier.predict(methylation_data)

print(f"Chromosome weights: {classifier.chromosome_weights}")
```

#### Mathematical Foundation

For multi-chromosome classification, the final probability is:

$$
P(\text{Class} \mid \text{data}) = \sum_{\mathrm{chrom}} w_{\mathrm{chrom}} \cdot P_{\mathrm{chrom}}(\text{Class} \mid \text{data}_{\mathrm{chrom}})
$$

Where:
- $w_{\mathrm{chrom}}$ is the normalized weight for chromosome $\mathrm{chrom}$
- $P_{\mathrm{chrom}}$ is the probability from that chromosome's classifier
- Weights are computed from trimmed-mean effect_size or provided explicitly

### Basic Usage

#### 1. Single Sample Classification

```python
from methyl_classifier import MethylClassifier
from methyl_classifier.models.config import ClassifierConfig
import numpy as np

# Configure
config = ClassifierConfig(
    model_path="path/to/classifier-1-CG.pkl",
    temperature=1.0
)

# Load classifier
classifier = MethylClassifier(config)
classifier.load_classifier(config.model_path)

# Prepare sample (1 sample, 100 DMPs)
sample_methylation = np.random.rand(1, 100)  # Replace with real data

# Predict
prediction = classifier.predict(sample_methylation)
probability = classifier.predict_proba(sample_methylation)

print(f"Predicted class: {prediction[0]}")
print(f"Probabilities: Class 0={probability[0,0]:.3f}, Class 1={probability[0,1]:.3f}")
```

#### 2. Batch Classification

```python
# Multiple samples
n_samples = 50
n_dmps = 100

methylation_matrix = np.random.rand(n_samples, n_dmps)  # Replace with real data

# Batch predict
predictions = classifier.predict(methylation_matrix)
probabilities = classifier.predict_proba(methylation_matrix)

# Results
for i in range(n_samples):
    print(f"Sample {i}: Class {predictions[i]}, P={probabilities[i, predictions[i]]:.3f}")
```

#### 3. With Missing Data

```python
# Create sample with missing values
methylation = np.random.rand(10, 100)
methylation[np.random.rand(10, 100) < 0.2] = np.nan  # 20% missing

# Create availability mask
availability = ~np.isnan(methylation)

# Replace NaN with 0 (masked positions are ignored anyway)
methylation[np.isnan(methylation)] = 0.0

# Classify
predictions = classifier.predict(methylation, availability_mask=availability)
```

### Loading Models

#### Enhanced PKL Format (Recommended)

Modern models include metadata:

```python
import pickle

with open('classifier-1-CG.pkl', 'rb') as f:
    model_package = pickle.load(f)

print(f"Chromosome: {model_package['metadata']['chromosome']}")
print(f"Context: {model_package['metadata']['context']}")
print(f"Number of DMPs: {model_package['metadata']['n_dmps']}")
print(f"Validation accuracy: {model_package['metadata']['validation_accuracy']}")
```

#### Legacy Format

Older models contain only the classifier object:

```python
classifier = MethylClassifier(config)
classifier.load_classifier(model_path)  # Automatically detects format
```

### Command-Line Interface

**Using a config file (recommended):**

```bash
methyl_classifier --config configs/PCa_vs_Healthy_classifier_config.json
```

Example config for multi-chromosome mode with Platt calibration:

```json
{
  "model_dir": "/path/to/detection/PCa_vs_Healthy_optimized",
  "model_path": null,
  "input_path": "/path/to/samples",
  "output_path": "/path/to/classification/PCa_vs_Healthy.csv",
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

**CLI without config:**

```bash
# Single chromosome
methyl_classifier --model classifier-1-CG.pkl --input sample.h5 --output results.csv

# Multi-chromosome
methyl_classifier --model-dir /path/to/classifiers/ --input samples_directory/ --output results.csv
```

---

## API Reference

### `MethylClassifier` Class

Main interface for classification.

#### Constructor

```python
MethylClassifier(config: ClassifierConfig)
```

**Parameters:**
- `config`: ClassifierConfig object with model path and settings

**Attributes:**
- `classifier`: ProbabilisticBetaClassifier instance
- `chromosome`: Chromosome identifier (from metadata)
- `context`: Methylation context (CG, CHG, CHH)
- `n_classes`: Number of classes (2 for binary, N for multi-class)
- `class_names`: List of class names
- `metadata`: Dict with training metadata

#### Methods

##### `load_classifier(model_path: Path)`

Load a trained classifier from pickle file.

**Parameters:**
- `model_path`: Path to .pkl file

**Raises:**
- `RuntimeError`: If loading fails

---

##### `predict(methylation_data, availability_mask=None, debug=False)`

Predict class labels.

**Parameters:**
- `methylation_data`: np.ndarray of shape (n_samples, n_dmps), values in [0,1]
- `availability_mask`: Optional boolean mask of same shape
- `debug`: Enable debug output for first sample

**Returns:**
- np.ndarray of shape (n_samples,) with class predictions (0 or 1)

**Example:**
```python
predictions = classifier.predict(methylation_data)
```

---

##### `predict_proba(methylation_data, availability_mask=None, debug=False)`

Predict class probabilities.

**Parameters:**
- `methylation_data`: np.ndarray of shape (n_samples, n_dmps)
- `availability_mask`: Optional boolean mask
- `debug`: Enable debug output

**Returns:**
- np.ndarray of shape (n_samples, 2) with posterior probabilities
  - Column 0: P(Class 0 | data)
  - Column 1: P(Class 1 | data)

**Example:**
```python
probabilities = classifier.predict_proba(methylation_data)
print(f"P(Class 1) = {probabilities[0, 1]:.3f}")
```

---

##### `predict_with_threshold(methylation_data, availability_mask=None, adjust_for_missing=True, debug=False)`

Threshold-based prediction using log-likelihood ratios.

**Parameters:**
- `methylation_data`: np.ndarray of shape (n_samples, n_dmps)
- `availability_mask`: Optional boolean mask
- `adjust_for_missing`: Adjust threshold for missing positions
- `debug`: Enable debug output

**Returns:**
- Dict with keys:
  - `predictions`: Class predictions (0 or 1)
  - `P_C`: Posterior probability for class 1
  - `P_H`: Posterior probability for class 0
  - `sumLLR`: Sum of log-likelihood ratios
  - `decision`: Array of decision strings
  - `threshold_used`: Threshold value used
  - `used_positions`: Number of positions used per sample

**Example:**
```python
results = classifier.predict_with_threshold(methylation_data)
print(f"Decision: {results['decision'][0]}")
print(f"LLR: {results['sumLLR'][0]:.2f}")
```

---

##### `get_feature_info()`

Get information about DMP features.

**Returns:**
- Dict with keys:
  - `n_features`: Number of DMPs
  - `positions`: Genomic positions
  - `weights`: DMP weights (if available)
  - `directions`: Direction indicators

**Example:**
```python
info = classifier.get_feature_info()
print(f"Using {info['n_features']} DMPs")
```

---

### `ProbabilisticBetaClassifier` Class

Low-level classifier (accessed via `MethylClassifier.classifier`).

#### Key Methods

##### `set_temperature(temperature: float)`

Set softmax temperature.

**Parameters:**
- `temperature`: Temperature value (≥ 0.1)

**Example:**
```python
classifier.classifier.set_temperature(2.5)
```

---

##### `calibrate_platt(X_val, y_val, availability_mask=None)`

Fit Platt scaling calibration on validation data.

**Parameters:**
- `X_val`: Validation methylation data
- `y_val`: True labels (0 or 1)
- `availability_mask`: Optional mask

**Example:**
```python
classifier.classifier.calibrate_platt(X_validation, y_validation)
```

---

##### `predict_proba_calibrated(X, availability_mask=None)`

Predict with Platt-calibrated probabilities.

**Parameters:**
- `X`: Methylation data
- `availability_mask`: Optional mask

**Returns:**
- np.ndarray of calibrated probabilities

**Example:**
```python
calibrated_proba = classifier.classifier.predict_proba_calibrated(X)
```

---

### `ClassifierConfig` Class

Configuration for MethylClassifier.

#### Fields

```python
@dataclass
class ClassifierConfig:
    model_path: str              # Path to classifier .pkl file
    temperature: float = 1.0     # Softmax temperature
    enable_platt_calibration: bool = False  # Use Platt scaling
```

---

## Model Format

### PKL File Structure

MethylClassifier models are saved as Python pickle files (.pkl) with the following structure:

#### Enhanced Format (Current)

```python
model_package = {
    'classifier': ProbabilisticBetaClassifier(...),
    'data': {
        'positions': np.array([...]),  # Genomic positions
        'alpha1': np.array([...]),     # Beta params for class 0
        'beta1': np.array([...]),
        'alpha2': np.array([...]),     # Beta params for class 1
        'beta2': np.array([...]),
        'weights': np.array([...]),    # DMP weights
        'directions': np.array([...]), # Direction indicators
        'llr_const': np.array([...])   # LLR constants
    },
    'metadata': {
        'chromosome': '1',
        'context': 'CG',
        'n_dmps': 5000,
        'validation_accuracy': 0.956,
        'training_date': '2025-10-23',
        'centroid1_name': 'healthy',
        'centroid2_name': 'cancer',
        'config': {
            'alpha': 0.01,
            'min_delta_mean': 0.2,
            'max_bc': 0.5,
            'target_balanced_accuracy': 0.95
        },
        'platt_calibrator': b'...'  # Serialized LogisticRegression (if fitted)
    },
    'selected_dmps_df': pd.DataFrame(...),  # DMP information
    'validation_accuracy': 0.956,
    'chromosome': '1',
    'context': 'CG',
    'n_dmps': 5000
}
```

### Training Data Requirements

To create a classifier, you need:

1. **Two centroids** (e.g., healthy and cancer populations)
   - Each centroid contains Beta parameters (α, β) at each genomic position
   - Created using MethylCentroid from individual samples

2. **Differentially methylated positions (DMPs)**
   - Identified using MethylModeler via statistical comparison of centroids
   - Selected based on:
     - Statistical significance (q-value ≤ α)
     - Effect size (balanced accuracy ≥ target)
     - Biological significance (delta mean, overlap)

3. **Validation samples** (optional but recommended)
   - Real samples from each class
   - Used to assess classifier performance
   - Can be used for Platt calibration

### Multi-class Model Build

You can build a multi-class classifier (e.g., healthy + multiple cancers) from:

- A **global DMP list** (CSV with `chromosome`, `context`, `position`)
- Per-class centroid directories (`{chrom}-{context}.h5`)
- Optional BMM centroids per class (for mixture likelihoods)

Example:

```bash
python build_multiclass_model.py configs/example_multiclass_model.json
```

See `configs/example_multiclass_model.json` for the full schema (centroid dirs, optional BMM centroids).

---

## Advanced Features

### 1. Platt Scaling Calibration

**Purpose**: Improve probability calibration when model is over/under-confident.

**When to use**:
- Posteriors don't match true frequencies
- Need well-calibrated probabilities for decision-making
- Have validation data available

**How it works**:
1. Computes raw log-likelihood ratios on validation set
2. Fits logistic regression: P(y=1 | LLR) = σ(a·LLR + b)
3. Transforms future predictions through fitted logistic function

**Usage**:
```python
# During training (in MethylModeler/)
config = MethylModelerConfig(
    ...
    enable_platt_calibration=True,
    validation_mode="real",
    centroid1_validation_samples=[...],
    centroid2_validation_samples=[...]
)

# Calibrator is automatically fitted and saved in model

# During prediction
config = ClassifierConfig(
    model_path="classifier-1-CG.pkl",
    enable_platt_calibration=True  # Use pre-fitted calibrator
)
classifier = MethylClassifier(config)
calibrated_proba = classifier.predict_proba(X)
```

### 2. Temperature Scaling

**Purpose**: Control confidence/sharpness of predictions.

**Temperature effects**:
- **T < 1**: Sharper predictions (more extreme probabilities)
- **T = 1**: Standard Bayesian (default)
- **T > 1**: Softer predictions (more conservative probabilities)

**Mathematical effect**:
$$
P(\text{Class } k \mid \mathbf{X}) \propto \exp(\mathrm{log\_likelihood}_k / T)
$$

**Usage**:
```python
# Set temperature
classifier.classifier.set_temperature(2.5)

# Predictions now use softened probabilities
proba = classifier.predict_proba(X)
```

**Tuning temperature**:
```python
import numpy as np
from scipy.optimize import minimize_scalar

def expected_calibration_error(T, classifier, X_val, y_val):
    """Compute ECE for a given temperature."""
    classifier.classifier.set_temperature(T)
    proba = classifier.predict_proba(X_val)
    
    # Bin predictions and compute calibration error
    bins = np.linspace(0, 1, 11)
    ece = 0.0
    for i in range(len(bins)-1):
        mask = (proba[:, 1] >= bins[i]) & (proba[:, 1] < bins[i+1])
        if np.sum(mask) > 0:
            avg_confidence = np.mean(proba[mask, 1])
            avg_accuracy = np.mean(y_val[mask])
            ece += np.abs(avg_confidence - avg_accuracy) * np.sum(mask)
    ece /= len(y_val)
    return ece

# Find optimal temperature
result = minimize_scalar(
    lambda T: expected_calibration_error(T, classifier, X_val, y_val),
    bounds=(0.1, 10.0),
    method='bounded'
)
optimal_T = result.x
```

### 3. Beta Mixture (BMM) Likelihoods

When detector-stage BMM refinement is enabled, MethylClassifier can use **Beta Mixture**
likelihoods for those DMPs (and fall back to Beta for the rest). This better models
multi-modal methylation distributions while preserving the Bayesian framework.

**Inputs**:
- `bmm_centroids/bmm-centroid-{chromosome}-{context}.json` (centroid1)
- `bmm_centroids/bmm-centroid-{chromosome}-{context}-centroid2.json` (centroid2)

**Behavior**:
- Uses mixture log-pdf for positions with valid BMM parameters in both classes
- Falls back to Beta log-pdf for all other positions

### 3. Threshold-Based Classification

**Purpose**: Analytical decision-making using LLR thresholds instead of posteriors.

**When to use**:
- Need interpretable decision boundaries
- Want to adjust decision threshold for cost-sensitive classification
- Have theoretical threshold from Neyman-Pearson framework

**How it works**:
1. Computes sum of log-likelihood ratios: Σ(logL₁ - logL₀)
2. Adjusts threshold for missing positions (optional)
3. Makes decision: predict Class 1 if sumLLR + log(π₁/π₀) > threshold

**Usage**:
```python
# Requires model trained with threshold information
results = classifier.predict_with_threshold(
    methylation_data,
    adjust_for_missing=True
)

print(f"Decision: {results['decision'][0]}")
print(f"Sum LLR: {results['sumLLR'][0]:.2f}")
print(f"Threshold: {results['threshold_used']:.2f}")
print(f"Positions used: {results['used_positions'][0]}/{classifier.n_dmps}")
```

### 4. Handling Low Coverage Samples

**Strategies** for samples with many missing DMPs:

**1. Availability mask** (automatic):
```python
# Classifier handles this internally
availability = ~np.isnan(methylation_data)
proba = classifier.predict_proba(methylation_data, availability_mask=availability)
```

**2. Minimum coverage threshold**:
```python
def filter_low_coverage(methylation_data, min_coverage=0.5):
    """Filter samples with < 50% DMP coverage."""
    availability = ~np.isnan(methylation_data)
    coverage = np.mean(availability, axis=1)
    return coverage >= min_coverage

mask = filter_low_coverage(methylation_data, min_coverage=0.5)
predictions = classifier.predict(methylation_data[mask])
```

**3. Coverage-weighted confidence**:
```python
proba = classifier.predict_proba(methylation_data, availability_mask)
coverage = np.mean(availability_mask, axis=1)

# Adjust confidence based on coverage
adjusted_confidence = np.max(proba, axis=1) * coverage
```

---

## Examples

### Example 1: Basic Classification Pipeline

```python
from methyl_classifier import MethylClassifier
from methyl_classifier.models.config import ClassifierConfig
from methyl_utils import MethylSample
import numpy as np
from pathlib import Path

# 1. Load classifier
config = ClassifierConfig(
    model_path="models/classifier-1-CG.pkl",
    temperature=1.0
)
classifier = MethylClassifier(config)
classifier.load_classifier(config.model_path)

# 2. Load sample
sample_path = Path("samples/patient001/1-CG.h5")
sample = MethylSample.load_from_h5(sample_path)

# 3. Extract methylation at DMP positions
dmp_positions = classifier.get_feature_info()['positions']
sample_indices = np.searchsorted(sample.pos, dmp_positions)

# Validate positions match
valid_mask = (sample_indices < len(sample.pos)) & (sample.pos[sample_indices] == dmp_positions)

# Compute methylation levels
methylation = np.zeros(len(dmp_positions))
methylation[valid_mask] = sample.mC[sample_indices[valid_mask]] / (
    sample.mC[sample_indices[valid_mask]] + sample.uC[sample_indices[valid_mask]]
)

# 4. Create availability mask
availability = valid_mask & (methylation >= 0) & (methylation <= 1)

# 5. Classify
methylation_matrix = methylation.reshape(1, -1)
availability_matrix = availability.reshape(1, -1)

prediction = classifier.predict(methylation_matrix, availability_matrix)
probabilities = classifier.predict_proba(methylation_matrix, availability_matrix)

# 6. Report results
print(f"Sample: {sample_path.parent.name}")
print(f"Predicted class: {prediction[0]}")
print(f"P(Healthy): {probabilities[0, 0]:.3f}")
print(f"P(Cancer): {probabilities[0, 1]:.3f}")
print(f"Coverage: {np.mean(availability):.1%}")
```

### Example 2: Batch Classification from Directory

```python
from pathlib import Path
import pandas as pd

def classify_directory(classifier, samples_dir, chrom="1", context="CG"):
    """Classify all samples in a directory."""
    results = []
    
    samples_dir = Path(samples_dir)
    sample_files = list(samples_dir.glob(f"*/{chrom}-{context}.h5"))
    
    dmp_positions = classifier.get_feature_info()['positions']
    
    for sample_file in sample_files:
        sample_name = sample_file.parent.name
        
        try:
            # Load sample
            sample = MethylSample.load_from_h5(sample_file)
            
            # Extract methylation at DMPs
            sample_indices = np.searchsorted(sample.pos, dmp_positions)
            valid_mask = (sample_indices < len(sample.pos)) & \
                        (sample.pos[sample_indices] == dmp_positions)
            
            methylation = np.zeros(len(dmp_positions))
            methylation[valid_mask] = sample.mC[sample_indices[valid_mask]] / (
                sample.mC[sample_indices[valid_mask]] + sample.uC[sample_indices[valid_mask]]
            )
            
            availability = valid_mask & (methylation >= 0) & (methylation <= 1)
            
            # Classify
            methylation_matrix = methylation.reshape(1, -1)
            availability_matrix = availability.reshape(1, -1)
            
            prediction = classifier.predict(methylation_matrix, availability_matrix)[0]
            proba = classifier.predict_proba(methylation_matrix, availability_matrix)[0]
            
            results.append({
                'sample_name': sample_name,
                'predicted_class': int(prediction),
                'P_class0': proba[0],
                'P_class1': proba[1],
                'coverage': np.mean(availability),
                'n_dmps_used': np.sum(availability)
            })
            
        except Exception as e:
            print(f"Error processing {sample_name}: {e}")
    
    return pd.DataFrame(results)

# Usage
results_df = classify_directory(classifier, "samples/patients/", chrom="1", context="CG")
results_df.to_csv("classification_results.csv", index=False)
print(results_df)
```

### Example 3: Cross-Validation Evaluation

```python
from sklearn.metrics import accuracy_score, roc_auc_score, classification_report
import numpy as np

def evaluate_classifier(classifier, X_val, y_val, availability_mask=None):
    """Comprehensive evaluation of classifier."""
    
    # Predictions
    y_pred = classifier.predict(X_val, availability_mask)
    y_proba = classifier.predict_proba(X_val, availability_mask)
    
    # Metrics
    accuracy = accuracy_score(y_val, y_pred)
    auc = roc_auc_score(y_val, y_proba[:, 1])
    
    # Balanced accuracy (for imbalanced data)
    class0_acc = np.mean(y_pred[y_val == 0] == 0)
    class1_acc = np.mean(y_pred[y_val == 1] == 1)
    balanced_acc = (class0_acc + class1_acc) / 2
    
    # Classification report
    report = classification_report(y_val, y_pred, target_names=['Healthy', 'Cancer'])
    
    print("=== Classifier Evaluation ===")
    print(f"Accuracy: {accuracy:.3f}")
    print(f"Balanced Accuracy: {balanced_acc:.3f}")
    print(f"AUC: {auc:.3f}")
    print(f"\nPer-Class Accuracy:")
    print(f"  Healthy (Class 0): {class0_acc:.3f}")
    print(f"  Cancer (Class 1): {class1_acc:.3f}")
    print(f"\nClassification Report:")
    print(report)
    
    return {
        'accuracy': accuracy,
        'balanced_accuracy': balanced_acc,
        'auc': auc,
        'class0_accuracy': class0_acc,
        'class1_accuracy': class1_acc
    }

# Usage
metrics = evaluate_classifier(classifier, X_validation, y_validation, availability_validation)
```

### Example 4: Temperature Calibration

```python
def calibrate_temperature(classifier, X_val, y_val, availability_mask=None):
    """Find optimal temperature for calibration."""
    from scipy.optimize import minimize_scalar
    
    def negative_log_likelihood(T):
        """Negative log-likelihood for temperature T."""
        classifier.classifier.set_temperature(T)
        proba = classifier.predict_proba(X_val, availability_mask)
        
        # Get probabilities for true classes
        true_proba = proba[np.arange(len(y_val)), y_val]
        
        # Negative log-likelihood
        return -np.mean(np.log(true_proba + 1e-15))
    
    # Find optimal temperature
    result = minimize_scalar(
        negative_log_likelihood,
        bounds=(0.1, 10.0),
        method='bounded'
    )
    
    optimal_T = result.x
    optimal_nll = result.fun
    
    print(f"Optimal temperature: {optimal_T:.3f}")
    print(f"Negative log-likelihood: {optimal_nll:.3f}")
    
    # Set optimal temperature
    classifier.classifier.set_temperature(optimal_T)
    
    return optimal_T

# Usage
optimal_temp = calibrate_temperature(classifier, X_val, y_val, availability_val)
```

---

## Troubleshooting

### Common Issues

#### 1. Dimension Mismatch Error

**Error:** `ValueError: Expected 5000 features, got 4892`

**Cause:** Sample doesn't have all DMP positions

**Solution:**
```python
# Create availability mask for missing positions
dmp_positions = classifier.get_feature_info()['positions']
sample_positions = sample.pos

# Find which DMPs are in the sample
dmp_indices = np.searchsorted(sample_positions, dmp_positions)
valid = (dmp_indices < len(sample_positions)) & \
        (sample_positions[dmp_indices] == dmp_positions)

# Create methylation array with zeros for missing
methylation = np.zeros(len(dmp_positions))
methylation[valid] = sample.methylation_levels[dmp_indices[valid]]

# Use availability mask
availability = valid
proba = classifier.predict_proba(methylation.reshape(1, -1), 
                                 availability_mask=availability.reshape(1, -1))
```

#### 2. Low Confidence Predictions

**Symptom:** All predictions near 0.5 probability

**Possible causes:**
1. Low DMP coverage
2. Sample from different population
3. Poor model calibration
4. Temperature too high

**Solutions:**
```python
# Check coverage
coverage = np.mean(availability_mask)
print(f"Coverage: {coverage:.1%}")

# Try lowering temperature
classifier.classifier.set_temperature(0.5)

# Check if sample matches model chromosome/context
print(f"Model: {classifier.chromosome}-{classifier.context}")
print(f"Sample: {sample_chrom}-{sample_context}")
```

#### 3. Module Import Errors

**Error:** `ImportError: cannot import name 'ProbabilisticBetaClassifier'`

**Solution:**
```bash
# Ensure MethylUtils is installed
cd packages/methylutils
poetry install

# Ensure MethylClassifier can find MethylUtils
export PYTHONPATH="${PYTHONPATH}:/path/to/MethylPipeline/packages"
```

#### 4. Model Loading Fails

**Error:** `ModuleNotFoundError: No module named 'methyl_modeler'`

**Cause:** Old model format with different module names

**Solution:**
The `CustomUnpickler` in MethylClassifier automatically handles this. If it still fails:

```python
import sys
sys.modules['methyl_modeler'] = methyl_utils
sys.modules['methyl_modeler.classifiers'] = methyl_utils

# Now load normally
classifier.load_classifier(model_path)
```

#### 5. NaN in Predictions

**Symptom:** `predict_proba` returns NaN

**Causes:**
- Invalid Beta parameters (α ≤ 0 or β ≤ 0)
- All positions have missing data
- Numerical overflow in log-likelihood

**Solution:**
```python
# Check for invalid parameters
info = classifier.get_feature_info()
alpha1 = classifier.classifier.data['alpha1']
beta1 = classifier.classifier.data['beta1']

invalid = (alpha1 <= 0) | (beta1 <= 0) | ~np.isfinite(alpha1) | ~np.isfinite(beta1)
print(f"Invalid parameters: {np.sum(invalid)} / {len(alpha1)}")

# Verify sample data
print(f"Sample values: min={np.nanmin(methylation)}, max={np.nanmax(methylation)}")
print(f"NaN count: {np.sum(np.isnan(methylation))}")
print(f"Available positions: {np.sum(availability_mask)}")
```

---

## Performance Considerations

### Speed Optimization

**Batch Processing:**
```python
# Process 1000 samples at once (faster than one-by-one)
batch_predictions = classifier.predict(methylation_matrix_1000x5000)
```

**Memory Management:**
```python
# For very large batches, process in chunks
chunk_size = 100
n_samples = len(methylation_data)

predictions = []
for i in range(0, n_samples, chunk_size):
    chunk = methylation_data[i:i+chunk_size]
    pred = classifier.predict(chunk)
    predictions.append(pred)

predictions = np.concatenate(predictions)
```

### Expected Performance

- **Single sample**: ~1-10 ms (depends on number of DMPs)
- **Batch (100 samples)**: ~50-200 ms
- **Memory**: ~100 MB per 10,000 DMPs

---

## References

### Theoretical Background

1. **Naive Bayes Classification**
   - Murphy, K. P. (2012). *Machine Learning: A Probabilistic Perspective*. MIT Press.

2. **Beta Distributions for Methylation**
   - Ji, Y., et al. (2008). "Flexible and interpretable genotyping of DNA methylation." *Genome Research*.

3. **Platt Scaling**
   - Platt, J. (1999). "Probabilistic outputs for support vector machines." *Advances in Large Margin Classifiers*.

4. **Temperature Scaling**
   - Guo, C., et al. (2017). "On Calibration of Modern Neural Networks." *ICML*.

### Related Documentation

- **MethylModeler**: DMP detection and model training
- ****: Classifier training pipeline
- **MethylUtils**: Core utilities and Beta distribution operations
- **MethylCentroid**: Centroid creation from samples

---

## Version History

### v0.1.0 (2025-10-23)
- Initial release
- Bayesian probabilistic classification
- Beta distribution likelihoods
- Temperature scaling support
- Platt calibration support
- Threshold-based prediction
- Missing data handling
- Enhanced PKL format with metadata

---

## License

MIT License - see LICENSE file for details.

---

## Support

For questions or issues:
- GitHub Issues: https://github.com/your-repo/MethylPipeline
- Documentation: https://methylpipeline.readthedocs.io
- Email: support@methylpipeline.org

---

*Generated: 2025-10-23*

