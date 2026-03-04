---
name: ECDF comparison performance
overview: Speed up ECDF/KS comparison across many positions by vectorizing the per-position loop and optionally reducing grid size; fix exp overflow in sigmoid; optionally document or improve compare_centroids runtime.
todos: []
isProject: false
---

# ECDF comparison performance and overflow fix

## Where time is spent

- **Your 125s run**: The log "Context CG: Compared 4,133,410 positions in 125.90s" is the full block: `compare_centroids()` (LRT + FDR + per-position stats in [methyl_centroid_pair.py](packages/methylutils/methyl_utils/methyl_centroid_pair.py)) plus, when there are q-value hits, `_compute_missing_metrics_df()` in the detector. With **0 significant DMPs (q≤0.01)** the detector only runs ECDF/KS on 0 rows, so in this run the 125s is almost entirely **compare_centroids** (LRT and `_process_batch` over 4.1M positions).
- **When ECDF/KS is slow**: As soon as many positions pass the q-value filter (e.g. hundreds of thousands), the detector calls `welch_d_ks_overlap` for each chunk, which calls [ecdf_ks_statistic](packages/methylutils/methyl_utils/statistical_tests.py) (lines 978–993). That function uses a **Python for-loop over every position** and for each position evaluates both ECDFs on a 256-point grid. So ECDF comparison cost is **O(positions × grid_size)** in a tight Python loop—the main bottleneck when you have many significant DMPs.

## 1. Vectorize ECDF/KS (main speedup)

**Goal**: Replace the per-position Python loop in `ecdf_ks_statistic` with a single vectorized computation so all positions are handled in NumPy at once.

**Approach**:

- **Batch CDF evaluation**: ECDFView currently has `_cdf(position_idx, x)` (single position). Add a batch path that, for a set of position indices and a shared grid, returns CDF values for all positions at all grid points.
  - In [distribution_views.py](packages/methylutils/methyl_utils/core/distribution_views.py): Add e.g. `_cdf_batch(self, position_indices: np.ndarray, grid: np.ndarray) -> np.ndarray` returning shape `(len(position_indices), len(grid))`.
  - Use the existing **piecewise-linear representation** already in memory: `_cdf_at_edges` has shape `(n_positions, n_edges)`. For each grid point `g`, compute the CDF at `g` for all requested positions via `np.interp` in a loop over grid points, or implement a small vectorized interp over positions (index into `_bin_edges` and `_cdf_at_edges` and linear interpolate). Avoid per-position Python calls.
  - If PCHIP is used, the batch path can either use the same piecewise-linear fallback for speed (consistent with bin edges) or, if needed, call the interpolators in a single NumPy loop that fills a preallocated array—still much faster than 4M Python iterations.
- **Use batch in statistical_tests**: In [statistical_tests.py](packages/methylutils/methyl_utils/statistical_tests.py), change `ecdf_ks_statistic` to:
  - Build a single `grid` of size `grid_size`.
  - Call `ecdf_view1._cdf_batch(position_indices, grid)` and `ecdf_view2._cdf_batch(position_indices, grid)` to get two arrays of shape `(n_positions, grid_size)`.
  - Compute `ks_stats = np.max(np.abs(f1 - f2), axis=1)` in one go.
  - Fall back to the current per-position loop only if `_cdf_batch` is not available (e.g. old view type).
- **Result**: ECDF/KS for N positions becomes O(N × grid_size) in NumPy instead of N Python iterations; large N (e.g. 100k–4M) should see a big speedup.

## 2. Configurable grid size (optional tradeoff)

- In [methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py), `_compute_chunk_metrics_df` currently calls `welch_d_ks_overlap(..., grid_size=256)`.
- Add an optional config knob (e.g. `ecdf_ks_grid_size`, default 256). Use it in the detector when calling `welch_d_ks_overlap`. Reducing to 128 or 64 can further cut cost with a small loss in KS resolution.
- In [config.py](packages/methyldetector/methyl_detector/models/config.py) add the new field if you want it user-facing.

## 3. Overflow in exp (RuntimeWarning)

- The warning `overflow encountered in exp` comes from `expit(scale * corrected_d)` in [statistical_tests.py](packages/methylutils/methyl_utils/statistical_tests.py) (line 1066). For very large positive `scale * corrected_d`, `exp(-x)` underflows; for very large negative values, `exp(-x)` can overflow in some implementations.
- **Fix**: Clip the argument to `expit` to a safe range (e.g. `np.clip(scale * corrected_d, -700.0, 700.0)`) before calling `expit`, so `bounded_effect_size` remains in (0, 1) and no warning is raised.

## 4. compare_centroids (125s for 4.1M positions)

- The current 125s is dominated by `compare_centroids`: LRT ([likelihood_ratio_test_beta](packages/methylutils/methyl_utils/statistical_tests.py)) and then `_process_batch` (distribution selection, p-values, metrics) over 4.1M positions in one or few batches.
- **No code change in this plan.** If you want to tackle that next, options include: profiling LRT vs rest of `_process_batch`, ensuring LRT uses GPU when available, or a two-phase design (e.g. cheap screening then full comparison on a subset). That would be a separate follow-up.

## Implementation order

1. **Vectorize ECDF/KS**: Add `_cdf_batch` to ECDFView and switch `ecdf_ks_statistic` to use it (with fallback).
2. **Overflow fix**: Clip input to `expit` in `welch_d_ks_overlap`.
3. **Grid size**: Add optional `ecdf_ks_grid_size` and pass it through from config to `welch_d_ks_overlap` in the detector.

After (1) and (2), when you have many positions passing q-value filter, ECDF comparison should be much faster and the overflow warning should disappear. The 125s you saw with 0 DMPs will not change until compare_centroids itself is optimized (item 4).