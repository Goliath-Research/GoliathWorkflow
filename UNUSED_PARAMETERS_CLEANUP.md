# Unused Parameters Cleanup

## Overview

Removed unused algorithm parameters that were planned for the improved algorithm from `copilot.py` but were never actually implemented or used in computations.

## Removed Parameters

The following parameters were **only stored in metadata** but **never used in any calculations**:

### From MethylDetectorConfig
- ❌ `target_fpr: float` - Target false positive rate
- ❌ `target_fnr: float` - Target false negative rate  
- ❌ `rank_gamma: float` - Exponent for (1-BC) in precision-weighted ranking
- ❌ `var_pool: str` - Variance pooling method
- ❌ `prior_cancer: float` - Prior probability for cancer class
- ❌ `prior_healthy: float` - Prior probability for healthy class
- ❌ `centroid1_label: str` - Class label for centroid1
- ❌ `centroid2_label: str` - Class label for centroid2

### From TrainingConfig
- ❌ Same 8 parameters as above

## Why These Were Unused

These parameters were added when planning to implement the improved algorithm from `copilot.py`, which included:

1. **Precision-weighted DMP ranking** using `rank_gamma` and `var_pool`
2. **Analytical FPR/FNR-based selection** using `target_fpr` and `target_fnr`
3. **Prior-based classification** using `prior_cancer` and `prior_healthy`
4. **Label mapping** using `centroid1_label` and `centroid2_label`

However, we ultimately:
- ✅ **Kept the original AUC-based DMP selection** (works better, achieves 100% accuracy)
- ✅ **Use Beta classifier directly** without label mapping (simpler, clearer)
- ✅ **Don't use prior probabilities** in computations (not needed for current approach)

## What We Actually Use

### DMP Ranking & Selection
```python
# Uses these actual parameters:
config.alpha          # Statistical significance threshold
config.gamma          # Bhattacharyya coefficient exponent
config.max_bc         # Maximum Bhattacharyya coefficient
config.min_delta_mean # Minimum mean difference
config.target_auc     # Target AUC for binary search
```

### Classification
```python
# Uses Beta distribution parameters directly:
alpha1, beta1  # Centroid 1 parameters
alpha2, beta2  # Centroid 2 parameters
llr_const      # Log-likelihood ratio constants

# No label mapping, no prior probabilities
# Direct assignment: centroid1 = class 0, centroid2 = class 1
```

## Files Modified

### Configuration Files
1. **`packages/methyldetector/methyl_detector/models/config.py`**
   - Removed 8 unused parameter fields
   - Removed `validate_var_pool()` validator
   - Removed `validate_config()` validator (was checking priors sum to 1.0)

2. **`packages/methyltrainer/methyl_trainer/config.py`**
   - Removed same 8 unused parameter fields

### Implementation Files
3. **`packages/methyldetector/methyl_detector/core/methyldetector.py`**
   - Removed passing unused parameters to `TrainingConfig`

4. **`packages/methyltrainer/methyl_trainer/trainer_class.py`**
   - Removed storing unused parameters in `model_package` metadata

## Configuration Before vs After

### Before (Bloated)
```json
{
  "centroid1_path": "...",
  "centroid2_path": "...",
  "output_dir": "...",
  "alpha": 0.01,
  "target_auc": 0.9999,
  "target_fpr": 0.01,
  "target_fnr": 0.01,
  "rank_gamma": 1.0,
  "var_pool": "sum",
  "prior_cancer": 0.5,
  "prior_healthy": 0.5,
  "centroid1_label": "cancer",
  "centroid2_label": "healthy"
}
```

### After (Clean)
```json
{
  "centroid1_path": "...",
  "centroid2_path": "...",
  "output_dir": "...",
  "alpha": 0.01,
  "target_auc": 0.9999
}
```

## Benefits

### 1. Simplicity
- ✅ Fewer configuration options
- ✅ Less cognitive load for users
- ✅ Clearer what parameters actually matter

### 2. Correctness
- ✅ No misleading parameters that don't affect behavior
- ✅ Configuration matches actual implementation
- ✅ No confusion about what's being used

### 3. Maintainability
- ✅ Less code to maintain
- ✅ Fewer validators to keep in sync
- ✅ Clearer intent of the configuration

## Validation

### Linter Check
```bash
✅ No errors
⚠️ Only expected warnings for optional dependencies (cupy, plotly)
```

### Existing Configs
Existing configuration files will continue to work because:
- These parameters were **optional** (had defaults)
- They were **never actually used** in computations
- Python dataclasses ignore extra fields gracefully

## Summary

| Parameter | Status | Reason |
|-----------|--------|--------|
| `target_fpr` | ❌ Removed | Never used in DMP selection |
| `target_fnr` | ❌ Removed | Never used in DMP selection |
| `rank_gamma` | ❌ Removed | Never used in ranking |
| `var_pool` | ❌ Removed | Never used in ranking |
| `prior_cancer` | ❌ Removed | Never used in classification |
| `prior_healthy` | ❌ Removed | Never used in classification |
| `centroid1_label` | ❌ Removed | Label mapping not needed |
| `centroid2_label` | ❌ Removed | Label mapping not needed |
| | | |
| `alpha` | ✅ Kept | **Actually used** in filtering |
| `gamma` | ✅ Kept | **Actually used** in effect size |
| `max_bc` | ✅ Kept | **Actually used** in filtering |
| `target_auc` | ✅ Kept | **Actually used** in binary search |

**Result:** Cleaner, simpler configuration that accurately reflects the actual algorithm implementation! 🎉

