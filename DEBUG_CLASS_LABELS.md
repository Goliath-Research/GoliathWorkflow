# Class Label Investigation

## Current Behavior
- Swapping still needed regardless of centroid order
- Accuracy: 36.5% → 63.5% after swap
- **63.5% is barely better than random (50%)**

## The Core Problem

### In `trainer_class.py` validation (lines 958-962):
```python
y_true = np.array([0] * len(X_val_class0) + [1] * len(X_val_class1))
y_pred = classifier.predict(X_val)
```

- centroid1 samples → `y_true = 0`
- centroid2 samples → `y_true = 1`

### In `probabilistic_beta_classifier.py` (lines 218-221, 248, 283, 300):
```python
alpha_C = self.data['alpha1']  # HARD-CODED: alpha1 = Cancer
beta_C = self.data['beta1']
alpha_H = self.data['alpha2']  # HARD-CODED: alpha2 = Healthy
beta_H = self.data['beta2']

sumLLR[i] = np.sum(logL_C - logL_H)  # Positive LLR favors Cancer
predictions = ((sumLLR + log_prior_odds) > threshold).astype(int)  # 1 = Cancer
decisions = np.where(predictions == 1, 'Cancer', 'Healthy')  # 1 = Cancer, 0 = Healthy
```

The classifier ALWAYS assumes:
- `alpha1/beta1` → Cancer → predict as `1`
- `alpha2/beta2` → Healthy → predict as `0`

But validation assigns labels based on centroid order:
- centroid1 → `0`
- centroid2 → `1`

## The Mismatch

Your data:
- centroid1 = `pb-healthy` → stored as alpha1/beta1 → classifier calls it "Cancer" → predicts as 1
- centroid2 = `pb-cancer` → stored as alpha2/beta2 → classifier calls it "Healthy" → predicts as 0

When validating:
- Healthy samples (centroid1) have true_label=0, but predicted_label=1 (Cancer) ❌
- Cancer samples (centroid2) have true_label=1, but predicted_label=0 (Healthy) ❌

Result: 100% - 36.5% = 63.5% error rate, swapped labels give 63.5% "accuracy"

## Why 63.5% is Still Bad

**63.5% accuracy for a 2-class problem is only 13.5% better than random guessing!**

This suggests:
1. ✅ Class labels are definitely inverted (explains systematic error)
2. ❌ Selected DMPs might not be very discriminative (explains low accuracy)
3. ❌ Threshold might be poorly calibrated
4. ❌ The analytical selection with FNR=1.0 indicates it couldn't meet the target

Looking at the output:
```
WARNING: Full panel of 27808 DMPs achieves FNR=1.0000 > target 0.0100
Analytical selection: k=27808, FPR=0.0100, FNR=1.0000, threshold=46625340608551370752.000
```

**The threshold is astronomically high (4.66×10¹⁹)!** This is nonsensical and suggests the analytical approach is completely broken for this data.

## Root Causes

### 1. Class Label Inversion (Confirmed)
- Hard-coded assumption: alpha1=Cancer, alpha2=Healthy
- Reality: depends on config centroid order
- **Fix needed**: Add class label configuration

### 2. Broken Threshold Calculation (Critical)
- Threshold: 4.66×10¹⁹ is impossibly high
- FNR: 1.0 means it classifies ALL samples as Healthy
- This explains why swapping gives exactly (1 - accuracy)

### 3. Poor DMP Selection
- With FNR=1.0, the analytical selection failed completely
- The Gaussian approximation for LLR distributions might be invalid
- The selected DMPs might not be discriminative enough

## Next Steps

1. **Fix the class label assumption** - add explicit class labels to config
2. **Debug the threshold calculation** - why is it so high?
3. **Validate the analytical LLR moments** - are they correct?
4. **Check the selected DMPs** - are they actually discriminative?

