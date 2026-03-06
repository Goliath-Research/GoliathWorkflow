---
name: Bounded effect size zero baseline
overview: Fix the bounded effect size formula so that identical distributions (delta_mean=0, welch_d=0, ks_d=0, overlap=1) yield effect size 0 instead of 0.5, restoring correct agreement with other metrics across MethylDetectorExplorer and MethylDetector.
todos: []
isProject: false
---

# Bounded effect size: no-difference → 0

## Problem

After the latest changes, when two centroids have **identical** methylation at a position (mean1 = mean2, delta_mean = 0, welch_d = 0, ks_d = 0, overlap = 1, ks_p = 1), both approximate and precise **bounded_effect_size** are **0.5** instead of **0**. That breaks agreement with the rest of the metrics (all of which correctly indicate “no difference”).

Cause: the formula is `bounded_effect_size = sigmoid(scale * welch_d * separation)`. When the argument is 0, `sigmoid(0) = 0.5`.

## Approach

Keep the same argument (scale × welch_d × separation) but map it so that **0 argument → 0 effect** and **large argument → 1 effect**:

- **New formula**: `effect = max(0, 2 * sigmoid(x) - 1)` with `x = scale * welch_d * separation`.
- Then: `x = 0` → sigmoid(0) = 0.5 → effect = 0; `x → +∞` → effect → 1; range stays **[0, 1]**.

Apply this mapping everywhere bounded effect size is computed so Explorer and MethylDetector stay consistent.

## Files and changes

### 1. MethylUtils – shared formula

**[packages/methylutils/methyl_utils/statistical_tests.py](packages/methylutils/methyl_utils/statistical_tests.py)**

- `**welch_d_fast_overlap_approx`** (around 1123–1124):  
Replace  
`bounded_effect_size_approx = expit(expit_arg)`  
with  
`bounded_effect_size_approx = np.clip(2.0 * expit(expit_arg) - 1.0, 0.0, 1.0)`.
- `**welch_d_ks_overlap**` (around 1186–1187):  
Replace  
`bounded_effect_size = expit(expit_arg)`  
with  
`bounded_effect_size = np.clip(2.0 * expit(expit_arg) - 1.0, 0.0, 1.0)`.
- Update docstrings that say “sigmoid(0) → 0.5” to state that **no difference → effect 0** and that the mapping is `2*sigmoid(x)-1` clamped to [0,1].

### 2. MethylDetectorExplorer – calibration

**[packages/methyldetector/methyl_detector/explorer.py](packages/methyldetector/methyl_detector/explorer.py)**

- **Scale calibration** (around 390 and 398): when computing `bes = expit(s * welch_d_k * T)` for the grid search and for the final calibrated values, use the same mapping:  
`bes = np.clip(2.0 * expit(s * welch_d_k * T) - 1.0, 0.0, 1.0)`  
(and similarly for the single scale used when not calibrating, if any direct `expit` remains).
- Phase 1 and Phase 2 effect sizes already come from the MethylUtils functions above, so no further Explorer changes are needed for the main table; only the calibration branch must use the shifted formula.

### 3. MethylDetector core

**[packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py)**

- All `bounded_effect_size` values are produced by `welch_d_ks_overlap` or the fast approximate path (which calls `welch_d_fast_overlap_approx`). So **no code changes** in methyldetector.py are required once the MethylUtils functions are updated.

### 4. Documentation

- **[packages/methyldetector/docs/Effect_Size_Theory.tex](packages/methyldetector/docs/Effect_Size_Theory.tex)** (if it describes the bounded effect): state that the reported effect is `max(0, 2σ(s·d·T)−1)` so that no difference gives 0 and strong separation gives 1.
- **Explorer doc** [packages/methyldetector/docs/METHYLDETECTOR_EXPLORER.md](packages/methyldetector/docs/METHYLDETECTOR_EXPLORER.md): optionally add one line that bounded_effect_size is in [0,1] with 0 = no difference (no code change required for behavior).

## Verification

- Unit tests: run Explorer tests and any MethylUtils tests that assert on effect size.
- Sanity check: for a position with mean1=mean2=0, variance 0, overlap=1, welch_d=0, ks_d=0, expect **bounded_effect_size_approx** and **bounded_effect_size** both **0.0** (not 0.5).

