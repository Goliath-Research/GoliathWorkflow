# Prediction Methods in MethylPipeline

## Overview

The `ProbabilisticBetaClassifier` now supports **two methods for computing classification probabilities**, both of which return proper probability distributions (not just 0.0 or 1.0):

1. **sklearn method** (default): Fast, trained logistic regression model
2. **beta method**: Exact probabilistic inference using Beta distributions

## Configuration

Users can control which method is used via the `prediction_method` configuration parameter:

```json
{
  "prediction_method": "sklearn"  // or "beta"
}
```

### In MethylDetector Config (`pb-hc12-2-CG_config.json`)

```json
{
  "centroid1_path": "path/to/centroid1.h5",
  "centroid2_path": "path/to/centroid2.h5",
  "output_dir": "results/",
  "prediction_method": "sklearn",  // ← Add this parameter
  ...
}
```

### In MethylTrainer Config

```python
from methyl_trainer import TrainingConfig

config = TrainingConfig(
    centroid1_path="path/to/centroid1.h5",
    centroid2_path="path/to/centroid2.h5",
    output_path="model.pkl",
    prediction_method="sklearn",  # or "beta"
    ...
)
```

## Method Comparison

| Feature | sklearn (default) | beta |
|---------|------------------|------|
| **Speed** | ⚡ Fast | 🐢 Slower |
| **Probabilities** | ✅ Continuous, smooth | ✅ Continuous, sharp |
| **Training** | Requires training samples | Uses Beta parameters |
| **Interpretation** | Empirical probabilities | Exact Bayesian inference |
| **Uncertainty** | Moderate confidence | High confidence (sharp) |
| **Best for** | Real-time classification | Research, validation |

## Example Outputs

### sklearn Method (Fast)
```
Sample 1: Class 0 | P(class0)=0.6610, P(class1)=0.3390
Sample 2: Class 1 | P(class0)=0.3391, P(class1)=0.6609
Sample 3: Class 0 | P(class0)=0.5413, P(class1)=0.4587  ← Uncertain
```

**Characteristics:**
- Smoother probability transitions
- More moderate confidence levels
- Better for uncertain/ambiguous samples
- Typical range: 0.3-0.7 for confident predictions

### beta Method (Exact Probabilistic)
```
Sample 1: Class 0 | P(class0)=0.9936, P(class1)=0.0064
Sample 2: Class 1 | P(class0)=0.0896, P(class1)=0.9104
Sample 3: Class 0 | P(class0)=0.9451, P(class1)=0.0549  ← Still confident
```

**Characteristics:**
- Sharper probability distributions
- Higher confidence levels
- Based on exact Beta distribution likelihoods
- Typical range: 0.01-0.99 for confident predictions

## Technical Details

### sklearn Method

1. During training, a `LogisticRegression` model is fitted on validation samples
2. Uses methylation values at DMPs as features
3. Returns `predict_proba()` from the trained sklearn model
4. Faster because it's a simple linear model

```python
classifier.predict_proba(X, use_sklearn=True)
# Returns: array([[0.661, 0.339], [0.339, 0.661], ...])
```

### beta Method

1. Uses Beta distribution parameters (α, β) for each centroid at each DMP
2. Computes log-likelihood for each sample under each centroid's distribution
3. Applies Bayes' rule with uniform priors to get posterior probabilities
4. More computationally intensive but theoretically exact

```python
classifier.predict_proba(X, use_sklearn=False)
# Returns: array([[0.994, 0.006], [0.090, 0.910], ...])
```

## Important Notes

### ✅ Both Methods Always Return Probabilities

- **Before fix**: Sometimes returned only 0.0 or 1.0 (hard classifications)
- **After fix**: Both methods return continuous probabilities in (0, 1)

### 📊 Reporting

In the final analysis report, **each sample receives two probabilities** (P(class0), P(class1)) that:
- Sum to 1.0
- Are continuous values (not just 0 or 1)
- Indicate classification confidence

The report will show:
```
Sample Classification Results:
  Sample 1: Class 0 (66.1% confidence)
  Sample 2: Class 1 (66.1% confidence)
  Sample 3: Class 0 (54.1% confidence)
  
Overall Accuracy: 95.2%
```

### 🔧 Model Package

The trained model saves the `prediction_method` preference:

```python
import pickle

with open("classifier-chr1-CG.pkl", "rb") as f:
    model_package = pickle.load(f)

print(model_package['prediction_method'])  # "sklearn" or "beta"
print(model_package['metadata']['prediction_method'])  # Also stored in metadata
```

## Validation

During training, the configured prediction method is used for validation:

```
✅ Classifier validation: accuracy 95.2% (method: sklearn)
```

or

```
✅ Classifier validation: accuracy 98.7% (method: beta)
```

## Recommendations

### Use **sklearn** (default) when:
- You need fast predictions
- You have sufficient training data
- You want smoother probability estimates
- You're classifying many samples in production

### Use **beta** when:
- You need theoretically exact probabilities
- You want maximum confidence discrimination
- You're validating the model scientifically
- Speed is not a concern

## Migration Guide

### For Existing Configs

Add the `prediction_method` parameter to your JSON config files:

```json
{
  "prediction_method": "sklearn"
}
```

If omitted, defaults to `"sklearn"` (fast method).

### For Code

```python
# Old code (still works, defaults to sklearn)
probs = classifier.predict_proba(X)

# New code (explicit control)
probs_sklearn = classifier.predict_proba(X, use_sklearn=True)
probs_beta = classifier.predict_proba(X, use_sklearn=False)
```

## Summary

🎯 **Key Takeaway**: Both methods now return proper probability distributions, giving users meaningful confidence scores for each classification. The choice between methods is a trade-off between speed (sklearn) and theoretical exactness (beta).

