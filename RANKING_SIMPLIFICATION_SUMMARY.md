# DMP Ranking Simplification - Summary

## Overview

Removed inferior ranking options to simplify the configuration and prevent users from accidentally choosing suboptimal methods. The pipeline now **always uses the superior precision-weighted score**.

## Changes Made

### 1. Removed `rank_mode` Config Parameter

**Before** (4 options):
```python
rank_mode: str = "delta_bc_var"  # Options: "delta_bc_var", "bc", "jeffreys", "hybrid"
```

**After** (no choice needed):
```python
# Always uses precision-weighted scoring - no config needed
```

### 2. Simplified Config Files

**MethylDetectorConfig** (`packages/methyldetector/methyl_detector/models/config.py`):
- ❌ Removed `rank_mode` field
- ❌ Removed `rank_mode` validator
- ✅ Kept `rank_gamma` (tuning parameter for the optimal method)
- ✅ Kept `var_pool` (tuning parameter for the optimal method)

**TrainingConfig** (`packages/methyltrainer/methyl_trainer/config.py`):
- ❌ Removed `rank_mode` field
- ✅ Kept `rank_gamma` with improved description
- ✅ Kept `var_pool`

### 3. Simplified MethylTrainer Code

**`_compute_effect_size()`** (`packages/methyltrainer/methyl_trainer/trainer_class.py`):

**Before**: 130 lines with conditional logic for 4 different ranking modes
**After**: 60 lines with single, optimal method

Removed:
- ❌ `if rank_mode == "delta_bc_var"` conditional
- ❌ `elif rank_mode == "bc"` branch (inferior: overlap only)
- ❌ `elif rank_mode == "jeffreys"` branch (inferior: divergence only)
- ❌ `elif rank_mode == "hybrid"` branch (complex, not better)
- ❌ Fallback error handling

**New implementation**: Always uses precision-weighted score
```python
score = (|Δμ| / √pooled_var) × (1 - BC)^γ
```

### 4. Cleaned Up Model Metadata

Removed `rank_mode` from model package:
```python
# Before
'rank_mode': self.config.rank_mode,  # ❌ Removed

# After - cleaner metadata
'rank_gamma': self.config.rank_gamma,  # ✅ Kept (tuning param)
'var_pool': self.config.var_pool,      # ✅ Kept (tuning param)
```

## Why This Is Better

### 1. **Simpler User Experience**
- Users don't have to choose between "delta_bc_var", "bc", "jeffreys", "hybrid"
- No risk of accidentally selecting an inferior method
- Fewer parameters to learn and configure

### 2. **Superior Method Always Used**
The precision-weighted score is objectively better because it combines:
- ✅ **Delta mean** (|Δμ|) - Effect size
- ✅ **Variance** (1/√var) - Precision/confidence
- ✅ **Overlap** ((1-BC)^γ) - Distribution separation

Other methods were inferior:
- ❌ "bc" - Only uses overlap, ignores effect size and variance
- ❌ "jeffreys" - Only uses divergence, no precision weighting
- ❌ "hybrid" - Complex combination with no proven advantage

### 3. **Cleaner Codebase**
- **70 lines of code removed** from `_compute_effect_size()`
- No conditional logic for different ranking modes
- Easier to maintain and test
- Clearer intent

### 4. **Still Configurable**
Users can still tune the optimal method:
- `rank_gamma`: Controls overlap penalty strength (default 1.0)
- `var_pool`: Controls how variances are combined ("sum", "max", "harmonic")

## What Users See Now

**Before** (confusing):
```python
config = TrainingConfig(
    rank_mode="delta_bc_var",  # Which one do I choose?
    rank_gamma=1.0,
    var_pool="sum",
    ...
)
```

**After** (clear):
```python
config = TrainingConfig(
    rank_gamma=1.0,    # Tune overlap penalty (optional)
    var_pool="sum",    # Tune variance pooling (optional)
    ...
)
```

## Technical Details

### The Precision-Weighted Score Formula

```
score = (|Δμ| / √pooled_var) × (1 - BC)^γ
```

Where:
- **|Δμ|**: Absolute difference in methylation means
- **pooled_var**: Combined variance (sum, max, or harmonic mean)
- **BC**: Bhattacharyya coefficient (0 = no overlap, 1 = identical)
- **γ**: Overlap penalty exponent (default 1.0)

### Why Each Component Matters

1. **|Δμ| (effect size)**: Larger differences are more biologically meaningful
2. **1/√var (precision)**: Low variance means high confidence in the measurement
3. **(1-BC)^γ (separation)**: Well-separated distributions are easier to distinguish

## Migration Notes

If you have existing code or configs with `rank_mode`:
- **Simply remove it** - the optimal method is now automatic
- Keep `rank_gamma` and `var_pool` if you were tuning those
- No other changes needed

## Benefits Summary

✅ **Simpler configuration** - One less parameter to worry about
✅ **Better results** - Always uses the optimal method
✅ **Cleaner code** - 70 lines removed
✅ **Still tunable** - Keep the parameters that matter
✅ **No confusion** - No choosing between good and bad options

## Date

October 17, 2025

