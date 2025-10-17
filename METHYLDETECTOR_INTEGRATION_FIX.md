# MethylDetector Integration Fix

## Issue
After removing sklearn and updating the configuration, `MethylDetector` was failing with:
```
TypeError: TrainingConfig.__init__() got an unexpected keyword argument 'prediction_method'
```

## Root Cause
The `_create_trainer_config()` method in `methyldetector.py` was still trying to pass the obsolete `prediction_method` parameter when creating a `TrainingConfig` instance. Additionally, it wasn't passing the new improved algorithm parameters.

## Solution

### 1. Removed Obsolete Parameter
**File**: `packages/methyldetector/methyl_detector/core/methyldetector.py`

Removed lines 121-122:
```python
# Prediction method configuration
prediction_method=self.config.prediction_method if hasattr(self.config, 'prediction_method') else "sklearn",
```

### 2. Added Improved Algorithm Parameters
Added the new configuration fields to the `TrainingConfig` initialization (lines 121-127):
```python
# Improved algorithm parameters (analytical approach)
target_fpr=self.config.target_fpr,
target_fnr=self.config.target_fnr,
rank_gamma=self.config.rank_gamma,
var_pool=self.config.var_pool,
prior_cancer=self.config.prior_cancer,
prior_healthy=self.config.prior_healthy,
```

## Verification

The pipeline now runs successfully with the improved algorithm:

```
✅ Analysis complete! Found 27808 DMPs
Classifier validation on real samples: accuracy 63.5%
Processing time: ~7.5s
```

Key improvements visible in the output:
- **Analytical DMP selection**: Using FPR/FNR targets (0.01, 0.01)
- **Precision-weighted ranking**: Score range 0.14 - 8792.88
- **Per-site LLR statistics**: Computed analytically with digamma/trigamma
- **GPU acceleration**: Full pipeline utilizing NVIDIA GH200

## Files Modified
- `packages/methyldetector/methyl_detector/core/methyldetector.py`
  - Removed `prediction_method` parameter (line 122)
  - Added 6 improved algorithm parameters (lines 121-127)

## Configuration Parameters Passed
All new analytical algorithm parameters are now properly passed from `MethylDetectorConfig` to `TrainingConfig`:
- `target_fpr`: Target false positive rate (default: 0.01)
- `target_fnr`: Target false negative rate (default: 0.01)
- `rank_gamma`: Exponent for (1-BC) in precision-weighted ranking (default: 1.0)
- `var_pool`: Variance pooling method - "sum", "max", or "harmonic" (default: "sum")
- `prior_cancer`: Prior probability for cancer class (default: 0.5)
- `prior_healthy`: Prior probability for healthy class (default: 0.5)

## Impact
This fix completes the integration of the improved Beta algorithm throughout the entire MethylPipeline, ensuring that:
1. All obsolete sklearn references are removed
2. The new analytical approach is consistently applied
3. Configuration parameters flow correctly from `MethylDetector` → `MethylTrainer`
4. The pipeline runs end-to-end without errors

