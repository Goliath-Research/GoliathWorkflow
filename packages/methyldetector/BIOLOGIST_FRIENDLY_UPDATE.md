# Biologist-Friendly Update: Using Bhattacharyya Coefficient Throughout

## Summary

Updated MethylDetector to use **Bhattacharyya Coefficient (BC)** instead of Bhattacharyya Distance (BD) for all user-facing configuration and outputs. This makes the tool much more intuitive for biologists.

## Key Changes

### 1. Configuration Parameter: `max_bc`

**Before (confusing for biologists):**
```json
"max_bc": 0.3  // Minimum BD threshold - higher values = stricter
```
- Used Bhattacharyya Distance (BD)
- Range: 0 to ∞ (typically 0-20)
- Interpretation: "minimum separation required" (confusing!)

**After (intuitive for biologists):**
```json
"max_bc": 0.6  // Maximum overlap allowed - lower values = stricter
```
- Uses Bhattacharyya Coefficient (BC)
- Range: 0 to 1
- Interpretation: "maximum overlap allowed" (clear!)

### 2. Filtering Logic

**Before:**
- Filter: `BD >= max_bc` (minimum distance required)
- Example: `max_bc=0.3` → Keep DMPs with BD ≥ 0.3

**After:**
- Filter: `BC <= max_bc` (maximum overlap allowed)
- Example: `max_bc=0.6` → Keep DMPs with ≤60% overlap

### 3. Output CSV Columns

**Removed:**
- `bhattacharyya_distance` (confusing BD values like 20.0)

**Added:**
- `bhattacharyya_coefficient` (intuitive BC values 0-1)

**Column interpretation:**
- `bhattacharyya_coefficient = 0.001` → 0.1% overlap (EXCELLENT DMP!)
- `bhattacharyya_coefficient = 0.135` → 13.5% overlap (GOOD DMP)
- `bhattacharyya_coefficient = 0.606` → 60.6% overlap (POOR DMP)

## For Biologists: How to Use max_bc

### Typical Values:

| max_bc | Interpretation | Use Case |
|--------|----------------|----------|
| 0.3 | Maximum 30% overlap | Very strict - only excellent DMPs |
| 0.5 | Maximum 50% overlap | Moderate - good quality DMPs |
| 0.6 | Maximum 60% overlap | Lenient - includes moderate DMPs |
| 0.8 | Maximum 80% overlap | Very lenient - most DMPs pass |

### Examples:

**Strict filtering (high-quality biomarkers):**
```json
{
    "min_delta_mean": 0.3,
    "max_bc": 0.3,
    "min_selected_dmps": 100
}
```
Interpretation: "I want DMPs with at least 30% methylation difference AND less than 30% overlap"

**Moderate filtering (balanced approach):**
```json
{
    "min_delta_mean": 0.2,
    "max_bc": 0.6,
    "min_selected_dmps": 500
}
```
Interpretation: "I want DMPs with at least 20% methylation difference AND less than 60% overlap"

**Lenient filtering (exploratory analysis):**
```json
{
    "min_delta_mean": 0.1,
    "max_bc": 0.8,
    "min_selected_dmps": 1000
}
```
Interpretation: "I want DMPs with at least 10% methylation difference AND less than 80% overlap"

## Understanding Overlap (BC)

### What BC Represents:

BC measures **how much the two methylation distributions overlap**:

```
BC = 0.0 ───────────────────────> BC = 1.0
Perfect separation          Complete overlap
(Best DMPs)                 (Worst DMPs)

     Group1    Group2               Group1/Group2
        █         █                      ████
        █         █                      ████
        █         █                      ████
      No overlap                   Total overlap
```

### Real Examples:

**Excellent DMP (BC = 0.001):**
```
Cancer:   ████████████████████      (highly methylated)
Healthy:  ██                        (lowly methylated)
Overlap:  Almost none (0.1%)
```

**Poor DMP (BC = 0.75):**
```
Cancer:   ████████████              (moderately methylated)
Healthy:  ████████████              (moderately methylated)
Overlap:  Substantial (75%)
```

## Internal Implementation

Under the hood, MethylDetector:

1. **Receives BD from MethylUtils** (Bhattacharyya Distance)
2. **Converts to BC immediately** using helper function:
   ```python
   def bhattacharyya_coefficient(bd):
       return np.exp(-bd)
   ```
3. **Works exclusively with BC** for filtering and ranking
4. **Outputs only BC** in CSV files

This conversion happens automatically - biologists never see BD values!

## Migration Guide

### Old Config File:
```json
{
    "max_bc": 0.3,  // This was BD (distance)
    "biological_filters": ["bhattacharyya"]
}
```

### New Config File:
```json
{
    "max_bc": 0.6,  // This is now BC (overlap)
    "biological_filters": ["bhattacharyya"]
}
```

**Important:** If you used `max_bc = 0.3` with old BD:
- BD = 0.3 → BC = exp(-0.3) ≈ 0.74
- New equivalent: `max_bc = 0.74`

Common conversions:
- BD = 0.3 → BC = 0.74 (lenient)
- BD = 0.5 → BC = 0.61 (moderate)
- BD = 1.0 → BC = 0.37 (strict)
- BD = 2.0 → BC = 0.14 (very strict)

## Benefits

✅ **Intuitive range:** 0-1 instead of 0-∞
✅ **Clear meaning:** "60% overlap" vs "distance of 0.5"
✅ **Familiar concept:** Biologists understand overlap/similarity
✅ **No confusion:** Values like 20.0 no longer appear
✅ **Easy filtering:** "I want max 50% overlap" → `max_bc=0.5`

## Technical Details

### Helper Function:
```python
def bhattacharyya_coefficient(bd: np.ndarray) -> np.ndarray:
    """
    Convert Bhattacharyya Distance (BD) to Coefficient (BC).
    
    Args:
        bd: Distance values from MethylUtils (0 to ∞, capped at 20)
        
    Returns:
        Coefficient values (0 to 1)
        - 0 = no overlap (perfect separation)
        - 1 = complete overlap (identical distributions)
    
    Formula: BC = exp(-BD)
    """
    return np.exp(-bd)
```

### Processing Pipeline:
```
MethylUtils (BD values) 
    ↓
bhattacharyya_coefficient() 
    ↓
DataFrame with BC column
    ↓
Filter: BC <= max_bc
    ↓
Rank: importance = delta_mean / BC
    ↓
Output CSV (BC values only)
```

## Summary

**Before:** Confusing BD values (0-20), filtering by minimum distance
**After:** Intuitive BC values (0-1), filtering by maximum overlap

This change makes MethylDetector much more accessible to biologists without changing the underlying mathematics or quality of DMP selection!

