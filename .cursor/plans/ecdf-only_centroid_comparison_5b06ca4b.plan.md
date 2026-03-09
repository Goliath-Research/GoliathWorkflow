---
name: ECDF-only centroid comparison
overview: Remove all non-ECDF distribution paths (Beta, Normal, Beta-Mixture) from MethylCentroidPair and MethylDetector, leaving a single unconditional ECDF-based comparison pipeline. Alpha/beta parameters must remain in the output because BetaClassifier and EAT consume them downstream.
todos: []
isProject: false
---

# ECDF-Only Centroid Comparison

## What is kept

- `alpha1/beta1/alpha2/beta2` in `CENTROID_COMPARISON_DTYPE` — **must stay**. They are read by BetaClassifier construction (3 call sites in `methyldetector.py`), EAT transformation, and synthetic validation sample generation.
- `bhattacharyya` column — kept, but now always computed from the fast discrete-bin-count path rather than from analytical Beta Bhattacharyya distance.
- `delta_sign` and `delta_mean` — already based on sample means; no change.
- Welch test — already universal and distribution-independent; no change.

## Changes required

### 1. [`methyl_centroid_pair.py`](packages/methylutils/methyl_utils/methyl_centroid_pair.py)

**a) `__init__` — remove distribution-selection parameters**

Remove these parameters completely (they all become dead code once `_process_batch` is simplified):

```python
# Remove:
distribution: str = "auto",
delta_mean_mode: str = "mean",
overlap_mode: str = "beta",
min_samples_normal: int = 6,
min_samples_beta: int = 10,
min_coverage_binom: int = 10,
overdispersion_threshold: float = 1.5,
enable_mixture: bool = True,
max_N_for_ecdf: int = 30,
bmm_centroid1: Any = None,
bmm_centroid2: Any = None,
```

Also remove the stored attributes, `_prepare_bmm_maps`, `_bmm_map1/2`, `_bmm_positions_common`.

**b) `_process_batch` — collapse to ECDF-only logic**

Remove:
- The entire mask setup block (`use_normal_mask`, `use_beta_mask`, `use_mixture_mask`, `use_ecdf_mask`, `force_mixture`)
- The `TempCentroid` class and its two instantiations (dead code; fed only into the LRT that no longer exists)
- The entire Beta-Mixture LLR p-value override block (`if np.any(use_mixture_mask):`)
- The `if np.any(use_ecdf_mask) and ... elif np.any(use_beta_mask):` p-value branch (Welch replaces both)
- The `delta_mean_mode` branching for `mean1_out`/`mean2_out` — always use `mean_normal1`/`mean_normal2`
- The mixture mean/variance computation (`mix_mean1/2`, `mix_var1/2`)
- The `overlap_mode` branching for Bhattacharyya — always use the discrete fast path
- The `_bhattacharyya_normal` call and the `compute_bhattacharyya_distance` in-batch call
- The ECDF override for `bhattacharyya` (`if bhattacharyya is not None and np.any(use_ecdf_mask)...`)

What `_process_batch` becomes:

```python
# 1. Index lookup (unchanged)
indices1 = np.searchsorted(centroid1.pos, positions)
indices2 = np.searchsorted(centroid2.pos, positions)

# 2. Extract arrays (alpha/beta still extracted for downstream BetaClassifier)
alpha1, beta1 = centroid1.alpha[indices1], centroid1.beta[indices1]
alpha2, beta2 = centroid2.alpha[indices2], centroid2.beta[indices2]
N1, N2 = centroid1.N[indices1], centroid2.N[indices2]
Sx1, Sx2_vals = centroid1.Sx[indices1], centroid2.Sx[indices2]
Sx2_1, Sx2_2  = centroid1.Sx2[indices1], centroid2.Sx2[indices2]

# 3. Sample moments — used for Welch test, means, variances
mean_normal1 = Sx1 / max(N1, 1)
mean_normal2 = Sx2_vals / max(N2, 1)
var_normal1  = (Sx2_1 - Sx1²/N1) / max(N1-1, 1)
var_normal2  = (Sx2_2 - Sx2_vals²/N2) / max(N2-1, 1)

# 4. Welch test (unchanged)
p_values = welch_mean_test(mean_normal1 - mean_normal2, var_normal1, N1, var_normal2, N2)["p_value"]
dist_ids  = np.full(len(positions), DIST_ECDF, dtype=np.uint8)

# 5. Bhattacharyya from discrete bin-count overlap (requires binned_stats — raise if missing)
bc1 = bs1["bin_counts"][indices1]
bc2 = bs2["bin_counts"][indices2]
overlap_approx = discrete_overlap_from_bin_counts(bc1, bc2)
bhattacharyya  = -np.log(np.clip(overlap_approx, 1e-10, 1.0)).astype(np.float32)

# 6. Mean/variance output — always sample-based
mean1_out   = mean_normal1.astype(np.float32)
mean2_out   = mean_normal2.astype(np.float32)
signed_delta = mean1_out - mean2_out
delta_mean  = np.abs(signed_delta)
var1_out = var_normal1.astype(np.float32)
var2_out = var_normal2.astype(np.float32)

# 7. Initial effect_size using sample variance (consistent with Welch test)
bc_values    = np.exp(-np.clip(bhattacharyya.astype(np.float64), 0.0, BD_CAP))
effect_sizes = effect_size_from_components(
    delta_mean=delta_mean.astype(np.float64),
    overlap=bc_values,
    var1=var_normal1, var2=var_normal2,
    lambda_var=2.0,
)["effect_size"]
```

Also raise `ValueError` at the start of the method if `binned_stats` is absent (currently a soft warning), since ECDF is no longer optional.

**c) Remove `_compute_bhattacharyya`** — the entire method is for `overlap_mode == "beta"` post-batch computation, which the ECDF-only path never needs.

**d) `compare_centroids`** — remove the `if self.overlap_mode == "beta": results_array = self._compute_bhattacharyya(results_array)` call and remove the `_prepare_bmm_maps` call.

**e) Remove DIST constants that no longer apply**:
```python
# Remove:
DIST_BETA = 1
DIST_NORMAL = 2
DIST_BETA_BINOM = 3
DIST_BETA_MIXTURE = 4
# Keep:
DIST_ECDF = 5
```

**f) `compute_effect_sizes_altA`** — currently recomputes Beta model variance from `alpha/beta` internally. Remove the internal Beta variance computation; accept `var1/var2` as explicit arguments (or just call `effect_size_from_components` directly from `_process_batch`, bypassing this method).

---

### 2. [`models/config.py`](packages/methyldetector/methyl_detector/models/config.py)

Remove these fields and their validators:

```python
# Remove:
distribution: str          # was: "auto", "beta", "normal", "ecdf", "beta_mixture"
delta_mean_mode: str       # was: "mean", "beta", "normal", "auto", "legacy"
overlap_mode: str          # was: "beta", "normal", "auto", "legacy"
max_N_for_ecdf: int        # was: auto-mode threshold
# Also remove validators: validate_distribution, validate_delta_mean_mode, validate_overlap_mode
```

Also update the stale comment at line 164:
```python
# Remove: "# Biological Filter (effect_size from MethylCentroidPair: |delta_mean|/(overlap*combined_std))"
```

---

### 3. [`methyldetector.py`](packages/methyldetector/methyl_detector/core/methyldetector.py)

Remove the four removed config fields from the `MethylCentroidPair(...)` construction:

```python
# Before:
centroid_pair = MethylCentroidPair(
    min_coverage=effective_min_coverage,
    delta_mean_mode=self.config.delta_mean_mode,
    overlap_mode=self.config.overlap_mode,
    distribution=self.config.distribution,
    max_N_for_ecdf=getattr(self.config, "max_N_for_ecdf", 30),
)

# After:
centroid_pair = MethylCentroidPair(min_coverage=effective_min_coverage)
```

Also update the `DIST_NAMES` dict used in CSV export to remove the non-ECDF entries, keeping only `{5: 'ECDF'}`.

---

### 4. [`configs/project_Healthy_vs_PCa1-4.json`](configs/project_Healthy_vs_PCa1-4.json)

No changes needed. The detection block does not currently set `distribution`, `delta_mean_mode`, `overlap_mode`, or `max_N_for_ecdf` — they all rely on defaults that will be removed.

---

## What is NOT changed

- `bmm_refine_*` config fields and `_refine_dmps_with_bmm` in the detector — these are a post-detection stage that operates on the final DMP DataFrame and is independent of the comparison distribution.
- `CENTROID_COMPARISON_DTYPE` fields `alpha1/beta1/alpha2/beta2` — kept because BetaClassifier and EAT need them.
- `dist` field in `CENTROID_COMPARISON_DTYPE` — kept (always `DIST_ECDF = 5`); simplifies downstream CSV reading.
- `compute_bhattacharyya_distance` in `metrics_core.py` — not touched; the function is registered in the metric