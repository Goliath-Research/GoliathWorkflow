# Beta Classifier Accuracy Fix Summary

## Problem
Beta classifier accuracy dropped from expected 100% to ~63% after refactoring, even though sklearn achieved AUC=1.0 on the same data.

## Root Causes Identified

### 1. **Beta Parameter Recalculation Without Bounds**
**Location**: `methyl_utils/methyl_centroid_pair.py` line 349-358

**Problem**: The code was recalculating Beta parameters using `beta_mle_estimation()` on aggregated centroids (N=10,000+ samples), producing extreme values (alpha/beta = 647 million!). This caused:
- Numerical instability in Beta log-pdf calculations
- All probabilities collapsing to 0 or 1
- Meaningless log-likelihoods (e.g., -150 billion)

**Solution**: Use pre-computed `centroid.alpha` and `centroid.beta` directly:
```python
# BEFORE (wrong):
alpha1_mle, beta1_mle = beta_mle_estimation(N1, log_x_sum1, log_1mx_sum1)
alpha1 = np.clip(alpha1_mle, 1e-6, max_reasonable_param)  # Too late!

# AFTER (correct):
alpha1 = centroid1.alpha[indices1].astype(np.float32)
beta1 = centroid1.beta[indices1].astype(np.float32)
```

The `MethylSample` class already computes properly bounded parameters (max=1e5=100K) using `_estimate_beta_params_bounded_extended()`.

### 2. **Directions Logic Not Matching copilot.py**
**Location**: `methyl_utils/probabilistic_beta_classifier.py` line 105-116

**Problem**: Implemented complex per-DMP "directions" logic to swap alpha/beta based on which centroid has higher methylation. This was:
- Not present in `copilot.py` reference implementation
- Adding unnecessary complexity
- Not needed when labels are configured correctly

**Solution**: Remove directions logic entirely:
```python
# BEFORE (wrong):
directions = self.data.get('directions', np.ones(self.n_dmps))
alpha_class0 = np.where(directions == 1, alpha1_base, alpha2_base)
alpha_class1 = np.where(directions == 1, alpha2_base, alpha1_base)

# AFTER (correct - following copilot.py):
alpha_class0 = alpha1_base  # Direct assignment: centroid1=class0
alpha_class1 = alpha2_base  # centroid2=class1
```

### 3. **Insufficient DMPs for Classification**
**Problem**: Testing with only 136 DMPs when 20K+ are needed for robust classification.

**Solution**: Use sufficient DMPs (min 20,000) as validated by binary search:
```json
{
  "min_dmps_for_export": 20000,
  "target_auc": 0.9999
}
```

## Changes Made

### Files Modified

1. **`methyl_utils/methyl_centroid_pair.py`**
   - Replaced `beta_mle_estimation()` calls with direct use of `centroid.alpha`/`centroid.beta`
   - Removed manual bounds checking (now handled by `MethylSample`)

2. **`methyl_utils/probabilistic_beta_classifier.py`**
   - Removed all directions logic from `predict_proba()`
   - Removed debug output for production use
   - Simplified to direct centroid1=class0, centroid2=class1 assignment

3. **`methyl_trainer/trainer_class.py`**
   - Disabled `_calibrate_directions()` call in `_create_classifier()`
   - Removed validation debug output
   - Added comment explaining removal of directions calibration

## Results

### Before Fix
- Accuracy: **63.5%** with 136 DMPs
- Beta parameters: 647 million (extreme!)
- Log-likelihoods: -150 billion (numerical instability)
- All samples predicted as class-1

### After Fix
- Accuracy: **99.0%** with 20,000 DMPs
- Beta parameters: bounded to max 100K
- Log-likelihoods: reasonable (-78K to -53K range)
- Proper class separation with confident predictions

## Key Lessons

1. **Trust Pre-computed Values**: Don't recalculate bounded parameters
2. **Follow Reference Implementation**: copilot.py had the correct approach (no directions)
3. **Sufficient Data**: 20K DMPs >> 136 DMPs for robust classification
4. **Numerical Stability**: Extreme parameter values (millions) break Beta distributions

## Validation

```bash
cd /home/ubuntu/MethylPipeline/packages/methyldetector
./md configs/pb-hc12-2-CG_config.json

# Output:
# ✅ Binary search complete: selected k=20000 DMPs with AUC=1.0000
# ✅ Training complete: 20000 DMPs, accuracy=0.990
```

## Configuration Example

```json
{
  "centroid1_path": "/path/to/healthy.h5",
  "centroid2_path": "/path/to/cancer.h5",
  "min_delta_mean": 0.2,
  "max_bc": 0.6,
  "target_auc": 0.9999,
  "min_dmps_for_export": 20000
}
```

Note: No need to specify `centroid1_label`/`centroid2_label` - the classifier correctly distinguishes centroid1 vs centroid2 samples regardless of label names.

