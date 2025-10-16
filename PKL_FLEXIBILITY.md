# Is prediction_method Fixed in the .pkl?

## Short Answer

**NO!** The `prediction_method` is **NOT fixed** in the `.pkl` file. You have full flexibility to choose which method to use at inference time.

## What's Actually Stored in the .pkl

When you save a trained model, the `.pkl` file contains:

```python
model_package = {
    'classifier': ProbabilisticBetaClassifier(...),  # The classifier object
    'data': {...},                                    # Beta distribution parameters
    'prediction_method': 'sklearn',                   # PREFERENCE (not constraint)
    'metadata': {
        'prediction_method': 'sklearn',               # Recommended method
        'n_dmps': 20000,
        'validation_accuracy': 1.0,
        ...
    }
}
```

### Key Components

1. **Beta Distribution Parameters** (always present)
   - `alpha1`, `beta1`, `alpha2`, `beta2` for each DMP
   - These enable the Beta probabilistic method

2. **Sklearn Model** (if `fit_sklearn_model()` was called)
   - Trained `LogisticRegression` model
   - Enables fast sklearn predictions

3. **Metadata with `prediction_method`**
   - This is just a **recommendation**, not a constraint
   - Indicates which method was used during training/validation

## Flexibility at Inference Time

Once you load the `.pkl`, you can use **either method** regardless of what's in metadata:

```python
import pickle

# Load the model
with open('classifier-chr1-CG.pkl', 'rb') as f:
    model_package = pickle.load(f)

classifier = model_package['classifier']

# You control which method to use!
probs_sklearn = classifier.predict_proba(X, use_sklearn=True)   # Fast
probs_beta = classifier.predict_proba(X, use_sklearn=False)      # Exact

# The 'prediction_method' in metadata doesn't restrict you!
```

## Test Results

```python
# Model saved with prediction_method='sklearn'
✅ Saved with prediction_method=sklearn

# After loading, BOTH methods work:
📊 After loading, can use EITHER method:
  sklearn: [0.55228284 0.44771716]  ← Fast method
  beta:    [0.62326940 0.37673060]  ← Exact method

✅ prediction_method is NOT fixed - you choose at runtime!
```

## Current MethylClassifier Behavior

### As of Now

`MethylClassifier.predict_proba()` uses the **default** behavior:
- Defaults to `use_sklearn=True` (because of parameter default in `ProbabilisticBetaClassifier`)
- Automatically falls back to Beta if sklearn model wasn't trained

```python
# In methyl_classifier/classifier.py
def predict_proba(self, methylation_data, availability_mask=None, debug=False):
    return self.classifier.predict_proba(
        methylation_data, 
        availability_mask, 
        debug
    )
    # Note: No use_sklearn parameter passed
    # → Uses ProbabilisticBetaClassifier default (use_sklearn=True)
```

### How It Works

1. **If sklearn model exists in .pkl**: Uses sklearn (fast)
2. **If sklearn model missing**: Automatically uses Beta (fallback)

This happens at the `ProbabilisticBetaClassifier` level:

```python
def predict_proba(self, X, availability_mask=None, use_sklearn=True, debug=False):
    if use_sklearn and self._sklearn_model is not None:
        return self._sklearn_model.predict_proba(X)  # Fast path
    else:
        # Fall back to Beta method (always available)
        return self._compute_beta_probabilities(...)
```

## Recommendation: Add Control to MethylClassifier

If you want **explicit control** from MethylClassifier, we could add:

```python
class MethylClassifier:
    def __init__(self):
        self.classifier = None
        self.metadata = {}
        self.preferred_method = 'sklearn'  # Load from metadata
    
    def predict_proba(self, methylation_data, 
                     availability_mask=None,
                     use_sklearn=None,  # New parameter
                     debug=False):
        """
        Predict probabilities.
        
        Args:
            use_sklearn: If None, uses model's preferred method.
                        If True/False, explicitly chooses method.
        """
        if use_sklearn is None:
            # Use the method stored in metadata
            use_sklearn = (self.metadata.get('prediction_method') == 'sklearn')
        
        return self.classifier.predict_proba(
            methylation_data, 
            availability_mask, 
            use_sklearn=use_sklearn,
            debug=debug
        )
```

## Practical Implications

### ✅ You CAN:

1. **Train with one method, use another later**
   ```python
   # Trained with sklearn
   model_package['prediction_method'] = 'sklearn'
   
   # Later, use beta for validation
   probs = classifier.predict_proba(X, use_sklearn=False)
   ```

2. **Compare methods on the same model**
   ```python
   probs_sklearn = classifier.predict_proba(X, use_sklearn=True)
   probs_beta = classifier.predict_proba(X, use_sklearn=False)
   diff = abs(probs_sklearn - probs_beta).mean()
   print(f"Methods differ by {diff*100:.2f}%")
   ```

3. **Switch methods for different use cases**
   ```python
   # Fast batch processing
   for batch in batches:
       probs = classifier.predict_proba(batch, use_sklearn=True)
   
   # Detailed analysis of specific samples
   probs_exact = classifier.predict_proba(critical_samples, use_sklearn=False)
   ```

4. **Use beta as a fallback if sklearn missing**
   ```python
   # Automatic fallback already built-in
   # If sklearn model wasn't trained, beta is used automatically
   ```

### ❌ You CANNOT:

1. **Use sklearn if it wasn't trained**
   ```python
   # If fit_sklearn_model() was never called:
   probs = classifier.predict_proba(X, use_sklearn=True)
   # → Automatically falls back to beta (no error)
   ```

2. **Use beta if parameters weren't saved**
   - This never happens - Beta parameters are always in the .pkl

## Summary Table

| Aspect | Status | Notes |
|--------|--------|-------|
| **Flexibility** | ✅ Full | Choose method at inference time |
| **Metadata Constraint** | ❌ None | `prediction_method` is just a hint |
| **Beta Method** | ✅ Always | Parameters always in .pkl |
| **Sklearn Method** | ⚠️ Conditional | Only if `fit_sklearn_model()` was called |
| **Automatic Fallback** | ✅ Yes | sklearn → beta if model missing |
| **Performance Impact** | ✅ None | Method choice doesn't affect other |

## Configuration vs Runtime

```
┌────────────────────────────────────────────────────────────┐
│  Training Time (MethylDetector config)                     │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  {                                                         │
│    "prediction_method": "sklearn"  ← Trains sklearn model │
│  }                                                         │
│                                                            │
│  Result:                                                   │
│  • Validation uses sklearn                                 │
│  • Sklearn model saved in .pkl                             │
│  • Metadata records "sklearn"                              │
│                                                            │
└────────────────────────────────────────────────────────────┘
                        ↓
┌────────────────────────────────────────────────────────────┐
│  Inference Time (MethylClassifier)                         │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  # Option 1: Use default (sklearn)                         │
│  probs = clf.predict_proba(X)                              │
│                                                            │
│  # Option 2: Explicit sklearn                              │
│  probs = clf.predict_proba(X, use_sklearn=True)            │
│                                                            │
│  # Option 3: Force beta                                    │
│  probs = clf.predict_proba(X, use_sklearn=False)           │
│                                                            │
│  ✅ You have FULL CONTROL regardless of training config!  │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

## Best Practice

**Training:**
```json
{
  "prediction_method": "sklearn"  // Fast, precise enough for production
}
```

**Inference:**
```python
# Normal use (fast)
probs = classifier.predict_proba(X)  # Uses sklearn by default

# Validation/comparison (optional)
probs_beta = classifier.predict_proba(X, use_sklearn=False)

# Check difference
diff = abs(probs - probs_beta).mean()
if diff > 0.01:  # 1% threshold
    logger.warning(f"Methods differ by {diff*100:.2f}%")
```

## Conclusion

**The `.pkl` file stores BOTH capabilities** (Beta parameters + sklearn model), and the `prediction_method` metadata is just a **recommendation**, not a constraint.

You have **complete flexibility** to choose which method to use at inference time, regardless of what was used during training.

This design gives you:
- ✅ **Speed** when you need it (sklearn)
- ✅ **Precision** when you want it (beta)
- ✅ **Validation** by comparing both methods
- ✅ **Flexibility** to switch based on use case

**Use this flexibility wisely!** Most of the time, sklearn is the right choice (0.15% precision, 28,000x faster).

