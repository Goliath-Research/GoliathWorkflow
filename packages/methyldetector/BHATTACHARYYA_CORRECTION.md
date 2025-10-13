# Bhattacharyya Distance vs Coefficient Correction

## Summary

Fixed critical mathematical error in biological importance calculation where Bhattacharyya Distance (BD) was incorrectly treated as Bhattacharyya Coefficient (BC).

## The Problem

**MethylUtils computes Bhattacharyya Distance (BD), not Bhattacharyya Coefficient (BC).**

### Key Differences:

| Metric | Symbol | Range | Interpretation |
|--------|--------|-------|----------------|
| **Bhattacharyya Coefficient** | BC | [0, 1] | Overlap: 1 = complete overlap, 0 = no overlap |
| **Bhattacharyya Distance** | BD | [0, ∞] | Separation: 0 = complete overlap, ∞ = complete separation |

### Mathematical Relationship:
```
BD = -ln(BC)
BC = exp(-BD)
```

## The Issue

**Original (INCORRECT) formula** assumed `bhattacharyya` column was BC:
```python
biological_importance = |delta_mean| / (bhattacharyya + eps)
```

**Problem:** If `bhattacharyya` is actually BD (distance):
- High BD (good separation) → High denominator → **LOW importance** ❌ WRONG!
- Low BD (poor separation) → Low denominator → **HIGH importance** ❌ WRONG!

This would completely invert the ranking, selecting poorly separated DMPs!

## The Solution

**Corrected formula** converts BD to BC first:
```python
# Step 1: Convert Bhattacharyya Distance to Coefficient
bc = np.exp(-bhattacharyya)  # BD → BC conversion

# Step 2: Compute biological importance
biological_importance = |delta_mean| / (bc + eps)
```

**Result:** Now correctly gives:
- High BD → Low BC (low overlap) → **HIGH importance** ✅ CORRECT!
- Low BD → High BC (high overlap) → **LOW importance** ✅ CORRECT!

### Mathematical Equivalence

The corrected formula is equivalent to:
```python
biological_importance = |delta_mean| * exp(BD)
```

This shows that importance increases exponentially with both effect size (delta_mean) and distribution separation (BD).

## Example

Consider two DMPs:

### DMP 1: Well-separated distributions
- delta_mean = 0.4
- BD = 2.0 (good separation)
- BC = exp(-2.0) = 0.135
- **Importance = 0.4 / 0.135 = 2.96** ✅ HIGH

### DMP 2: Poorly separated distributions
- delta_mean = 0.4 (same effect size)
- BD = 0.5 (poor separation)
- BC = exp(-0.5) = 0.606
- **Importance = 0.4 / 0.606 = 0.66** ✅ LOW

**Result:** DMP 1 gets ~4.5x higher importance score, correctly prioritizing well-separated distributions.

## Implementation Details

### Changed Files:

1. **`methyl_detector/core/methyldetector.py`**
   - `_compute_biological_importance()`: Added BD→BC conversion
   - `_apply_biological_filters()`: Updated comments to clarify BD filtering
   - `_save_results()`: Updated summary text with formula explanation

2. **`methyl_detector/models/config.py`**
   - `max_bc` parameter: Updated description to clarify it's BD (distance), not BC (coefficient)
   - `eps` parameter: Updated description to show BC is derived from BD
   - `biological_filters`: Updated description to clarify Bhattacharyya Distance

### Code Changes:

```python
def _compute_biological_importance(self) -> None:
    """Compute biological importance = delta_mean / (BC + eps) on self.df.
    
    Note: MethylUtils computes Bhattacharyya Distance (BD), not coefficient (BC).
    We convert: BC = exp(-BD), then compute: importance = |delta_mean| / (BC + eps)
    This is mathematically equivalent to: |delta_mean| * exp(BD)
    """
    eps = self.config.eps
    
    if 'bhattacharyya' not in self.df.columns:
        logger.warning("Bhattacharyya column not found, cannot compute biological importance")
        self.df['biological_importance'] = np.abs(self.df['delta_mean'])
    else:
        # Convert Bhattacharyya Distance (BD) to Coefficient (BC)
        # BC = exp(-BD), where BC ∈ [0,1] represents overlap
        bc = np.exp(-self.df['bhattacharyya'])
        
        # Compute biological importance: delta_mean / (BC + eps)
        # Higher delta_mean and lower overlap (lower BC) = higher importance
        self.df['biological_importance'] = np.abs(self.df['delta_mean']) / (bc + eps)
```

## Configuration Parameter Clarification

The parameter `max_bc` is somewhat misnamed but retained for backward compatibility:

```python
max_bc: Optional[float] = Field(
    default=0.3, ge=0.0,
    description="Minimum Bhattacharyya Distance (BD) threshold. BD = -ln(BC) where BC is coefficient. Higher BD = better separation between distributions. Typical range: 0-5+"
)
```

**Usage:**
- `max_bc = 0.3`: Keep only DMPs with BD ≥ 0.3
- Higher values = stricter filtering, requiring better separation
- Typical range: 0.3 to 2.0
  - 0.3 → BC ≈ 0.74 (moderate overlap)
  - 1.0 → BC ≈ 0.37 (low overlap)
  - 2.0 → BC ≈ 0.14 (very low overlap)

## Output Columns in CSV

For biologist-friendly interpretation, the output CSV includes **both** metrics:

| Column Name | Range | Interpretation | For Biologists |
|-------------|-------|----------------|----------------|
| `bhattacharyya_distance` | 0-∞ (capped at 20) | Separation measure | Higher = better separation |
| `bhattacharyya_coefficient` | 0-1 | Overlap measure | **Lower = better separation** ✅ More intuitive! |

**Example values:**
- BD = 20.0 → BC = 2e-9 ≈ 0 → Excellent separation (virtually no overlap)
- BD = 2.0 → BC = 0.135 → Good separation (13.5% overlap)
- BD = 0.5 → BC = 0.606 → Poor separation (60.6% overlap)

**For biologists:** Look at `bhattacharyya_coefficient` - values close to 0 indicate well-separated distributions (good DMPs for classification).

## Testing Recommendations

1. **Verify BD values**: Check that `bhattacharyya_distance` column contains distance values (typically 0-20 range)
2. **Verify BC values**: Check that `bhattacharyya_coefficient` column contains values in 0-1 range
3. **Check ranking**: Higher BD (lower BC) DMPs should have higher biological importance
4. **Validate selection**: Binary search should select DMPs with good separation (high BD, low BC)
5. **Compare with oldselection.py**: Results should match proven implementation

## Impact

✅ **Critical fix**: Without this correction, the pipeline would select the WRONG DMPs (poorly separated instead of well separated)

✅ **Correct ranking**: DMPs now properly ranked by biological importance

✅ **Better classification**: Classifier trained on genuinely discriminative DMPs

## References

- Bhattacharyya, A. (1943). "On a measure of divergence between two statistical populations defined by their probability distributions"
- MethylUtils documentation: `compute_bhattacharyya_distance()` returns BD, not BC

