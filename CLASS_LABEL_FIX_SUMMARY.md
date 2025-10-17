# Class Label Fix - Summary

## Problem Identified

### The "Swapping Class Labels" Issue

The pipeline had a **systematic class label inversion** caused by hard-coded assumptions about which centroid represented which class.

### Root Causes

1. **Hard-coded assumptions in 3 places**:
   - `trainer_class.py` line 311-314: Assumed alpha1=Cancer, alpha2=Healthy
   - `probabilistic_beta_classifier.py` line 218-221: Assumed alpha1=Cancer, alpha2=Healthy
   - `probabilistic_beta_classifier.py` line 145-147: Swapped centroid assignments

2. **No configuration for class labels**:
   - The code had no way to know which centroid represented which class
   - It blindly assumed centroid1=Cancer, centroid2=Healthy

3. **User's actual data was backwards**:
   - `centroid1_path`: `/pb-healthy/` → Healthy samples
   - `centroid2_path`: `/pb-cancer-12/` → Cancer samples

### Impact

**Validation results before fix**:
```
Swapping class labels for validation - improves accuracy from 0.365 to 0.635
```

This meant:
- The classifier was predicting the **opposite class** 63.5% of the time
- Only 36.5% accuracy without swapping (worse than random!)
- Validation code had a workaround that detected and reported the "swapped" accuracy

**Threshold calculation before fix**:
```
threshold=46625340608551370752.000 (4.66×10¹⁹)
FNR=1.0000 (100% false negatives!)
```

The inverted class labels caused the LLR statistics to be computed backwards, resulting in an absurdly high threshold that classified everything as Healthy.

## Solution Implemented

### 1. Added Configuration Fields

**Files**: `config.py` (both MethylDetector and MethylTrainer)

```python
centroid1_label: str = "cancer"  # or "healthy"
centroid2_label: str = "healthy"  # or "cancer"
```

With validation ensuring:
- Labels must be 'cancer' or 'healthy' (case-insensitive)
- Labels must be different
- Users explicitly specify which centroid is which class

### 2. Dynamic Class Assignment in DMP Selection

**File**: `trainer_class.py`, `_select_dmps_binary_search()` (lines 310-322)

```python
# Extract Beta parameters for sorted DMPs - assign based on config labels
if self.config.centroid1_label.lower() == 'cancer':
    # centroid1 is cancer, centroid2 is healthy
    alpha_C = sorted_df['alpha1'].values
    beta_C = sorted_df['beta1'].values
    alpha_H = sorted_df['alpha2'].values
    beta_H = sorted_df['beta2'].values
else:
    # centroid1 is healthy, centroid2 is cancer
    alpha_C = sorted_df['alpha2'].values
    beta_C = sorted_df['beta2'].values
    alpha_H = sorted_df['alpha1'].values
    beta_H = sorted_df['beta1'].values
```

This ensures the LLR statistics (`muC`, `varC`, `muH`, `varH`) are computed with the correct class assignments.

### 3. Dynamic Class Assignment in Classifier Creation

**File**: `trainer_class.py`, `_create_classifier()` (lines 734-741)

```python
# Compute LLR constants - assign based on config labels
if self.config.centroid1_label.lower() == 'cancer':
    llr_const = -(betaln(alpha1, beta1) - betaln(alpha2, beta2))
else:
    # Swap the sign for inverted labels
    llr_const = -(betaln(alpha2, beta2) - betaln(alpha1, beta1))

# Store label info in classifier data
classifier_data = {
    ...
    'centroid1_label': self.config.centroid1_label,
    'centroid2_label': self.config.centroid2_label
}
```

### 4. Dynamic Class Assignment in Predictions

**File**: `probabilistic_beta_classifier.py`, `predict_with_threshold()` (lines 217-231)

```python
centroid1_label = self.data.get('centroid1_label', 'cancer').lower()

if centroid1_label == 'cancer':
    alpha_C = self.data['alpha1']
    beta_C = self.data['beta1']
    alpha_H = self.data['alpha2']
    beta_H = self.data['beta2']
else:
    alpha_C = self.data['alpha2']
    beta_C = self.data['beta2']
    alpha_H = self.data['alpha1']
    beta_H = self.data['beta1']
```

**File**: `probabilistic_beta_classifier.py`, `predict_proba()` (lines 145-156)

```python
centroid1_label = self.data.get('centroid1_label', 'cancer').lower()

if centroid1_label == 'cancer':
    log_likelihoods[:, 0] = log_like_centroid2  # Healthy ← centroid2
    log_likelihoods[:, 1] = log_like_centroid1  # Cancer ← centroid1
else:
    log_likelihoods[:, 0] = log_like_centroid1  # Healthy ← centroid1
    log_likelihoods[:, 1] = log_like_centroid2  # Cancer ← centroid2
```

### 5. Dynamic Labels in Validation

**File**: `trainer_class.py`, `_validate_on_real_samples()` (lines 973-980)

```python
# Create labels - assign based on config centroid labels
# Classifier predicts: 0=Healthy, 1=Cancer
if self.config.centroid1_label.lower() == 'cancer':
    y_true = np.array([1] * len(X_val_class0) + [0] * len(X_val_class1))
else:
    y_true = np.array([0] * len(X_val_class0) + [1] * len(X_val_class1))
```

## Results After Fix

### ✅ Label Swapping Eliminated

**Before**:
```
Swapping class labels for validation - improves accuracy from 0.365 to 0.635
```

**After**:
```
Classifier validation on real samples: accuracy 63.5%
```

No more swapping! The labels are correctly aligned.

### ✅ Threshold Improved

**Before**:
```
threshold=46625340608551370752.000 (4.66×10¹⁹)
FNR=1.0000
```

**After**:
```
threshold=104194835218893440.000 (1.04×10¹⁷)
FNR=0.1082
```

- Threshold reduced by ~450x
- FNR improved from 1.0 (100%) to 0.1082 (10.82%)

## Remaining Issues

### ⚠️ Low Accuracy (63.5%)

While the class labels are now correct, 63.5% accuracy for a 2-class problem is only 13.5% better than random guessing (50%). This suggests:

1. **Selected DMPs may not be discriminative enough**
   - Need to investigate why precision-weighted ranking selected these specific DMPs
   - May need to adjust filtering parameters (min_delta_mean, max_bc, rank_gamma)

2. **Threshold still very high (1.04×10¹⁷)**
   - While much better than before, this is still astronomically high
   - Suggests the LLR distributions may have extreme values
   - Could indicate numerical instability or data quality issues

3. **FNR above target (0.1082 vs 0.01)**
   - The analytical selection couldn't meet the target FNR=0.01
   - Even with all 27,808 DMPs, FNR is still 10.82%
   - This means the classifier misses 10.82% of cancer samples

### Possible Next Steps

1. **Investigate DMP quality**:
   - Check the distribution of effect sizes
   - Analyze Bhattacharyya coefficients
   - Look at per-DMP discrimination power

2. **Debug threshold calculation**:
   - Add logging for muC, varC, muH, varH distributions
   - Check for numerical overflow/underflow
   - Validate the Gaussian approximation assumptions

3. **Alternative ranking methods**:
   - Try different var_pool methods ("max", "harmonic")
   - Adjust rank_gamma to penalize overlap more/less
   - Consider tighter biological filters

4. **Data quality checks**:
   - Verify centroid quality (N_samples, coverage)
   - Check for batch effects or confounders
   - Ensure validation samples are representative

## Usage

To use the fixed pipeline, always specify centroid labels in your config:

```json
{
  "centroid1_path": "/path/to/healthy/centroid.h5",
  "centroid2_path": "/path/to/cancer/centroid.h5",
  "centroid1_label": "healthy",
  "centroid2_label": "cancer",
  ...
}
```

**Defaults** (if not specified):
- `centroid1_label`: "cancer"
- `centroid2_label`: "healthy"

## Files Modified

1. `packages/methyldetector/methyl_detector/models/config.py`
   - Added `centroid1_label`, `centroid2_label` fields
   - Added validation for labels

2. `packages/methyltrainer/methyl_trainer/config.py`
   - Added `centroid1_label`, `centroid2_label` fields

3. `packages/methyldetector/methyl_detector/core/methyldetector.py`
   - Pass new fields to TrainingConfig

4. `packages/methyltrainer/methyl_trainer/trainer_class.py`
   - Dynamic class assignment in `_select_dmps_binary_search()`
   - Dynamic LLR constants in `_create_classifier()`
   - Dynamic labels in `_validate_on_real_samples()`

5. `packages/methylutils/methyl_utils/probabilistic_beta_classifier.py`
   - Dynamic class assignment in `predict_with_threshold()`
   - Dynamic class assignment in `predict_proba()`

## Summary

✅ **Fixed**: Class label inversion - no more swapping
✅ **Fixed**: Threshold calculation now uses correct class assignments
✅ **Improved**: FNR from 1.0 → 0.1082 (10x better)
⚠️ **Remaining**: Low accuracy (63.5%) needs further investigation
⚠️ **Remaining**: High threshold (1.04×10¹⁷) suggests numerical issues

The pipeline now correctly handles class labels, but the modest accuracy suggests the selected DMPs or threshold calculation may need further refinement.

