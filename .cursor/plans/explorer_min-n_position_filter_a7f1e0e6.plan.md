---
name: Explorer min-N position filter
overview: Add a pre-delta_mean position filter to MethylDetectorExplorer so only positions with sufficient N in both centroids are considered. Expose the filter via CLI options --min-N (absolute) or --min-N-pct (percentage), with default 5%.
todos: []
isProject: false
---

# MethylDetectorExplorer min-N position filter

## Goal

Filter positions **before** computing delta_mean and approximate effect size so that only positions with a minimum N in both groups are compared. The threshold is configurable as either an absolute count (`--min-N`) or a fraction of the better-covered group at that position (`--min-N-pct`), with **default 5%** when no absolute min is set.

## Behavior

- **Absolute (`--min-N`)**: Keep position only if `n1 >= min_N` and `n2 >= min_N` (both centroids have at least that many samples at the position).
- **Percentage (`--min-N-pct`, default `0.05`)**: Keep position only if `min(n1, n2) >= min_N_pct * max(n1, n2)`. So the smaller group must have at least 5% of the larger group’s count at that position (avoids comparing when one group has almost no data). When `max(n1, n2) == 0`, the position is dropped.
- **Precedence**: If `--min-N` is set, use the absolute filter only. Otherwise use the percentage filter with `--min-N-pct` (default 5%).

Filtering happens immediately after `load_and_align` and `_require_binned_stats`, before any subsampling (`sample_fraction`) and before `_extract_phase1_data` / delta_mean and overlap computation.

## Files to change

1. **[packages/methyldetector/methyl_detector/explorer.py](packages/methyldetector/methyl_detector/explorer.py)**
  - Add constructor parameters: `min_N: Optional[int] = None`, `min_N_pct: float = 0.05`.
  - In `run()`, after loading centroids and validating binned_stats:
    - Get per-position counts: `n1_all = _to_arr(centroid1.N)`, `n2_all = _to_arr(centroid2.N)` (length = `n_total`).
    - Build keep mask:
      - If `min_N is not None`: `keep = (n1_all >= min_N) & (n2_all >= min_N)`.
      - Else: `max_n = np.maximum(n1_all, n2_all)`, `min_n = np.minimum(n1_all, n2_all)`, `keep = (max_n > 0) & (min_n >= min_N_pct * max_n)`.
    - `indices_after_N_filter = np.where(keep)[0]`; use this as the pool for the rest of the run (subsampling and Phase 1 operate on this subset only).
  - Subsampling: if `sample_fraction < 1`, draw from `len(indices_after_N_filter)` and map back to original indices via `indices_after_N_filter[phase1_local]`; otherwise `phase1_indices = indices_after_N_filter`.
  - Report: add `positions_after_min_N_filter` (or similar) so users see how many positions passed the filter; keep `total_positions` as the pre-filter count.
2. **[packages/methyldetector/methyl_detector/cli/explorer_main.py](packages/methyldetector/methyl_detector/cli/explorer_main.py)**
  - Add `--min-N` (int, default `None`) and `--min-N-pct` (float, default `0.05`), with help text explaining they control the minimum N filter applied before comparing centroids.
  - Pass `min_N` and `min_N_pct` into `MethylDetectorExplorer(...)`.
3. **Documentation**
  - **[packages/methyldetector/docs/METHYLDETECTOR_EXPLORER.md](packages/methyldetector/docs/METHYLDETECTOR_EXPLORER.md)**: Document `--min-N` and `--min-N-pct` in the options table and briefly in the “Why two phases?” or a small “Position filter” note (filter applied before Phase 1; default 5% keeps positions where the smaller group has at least 5% of the larger group’s count).

## Implementation notes

- Reuse `_to_arr()` for `centroid1.N` and `centroid2.N` so the filter works whether they are arrays or pandas-like.
- No changes to `_extract_phase1_data` or `_choose_k`; they continue to receive indices into the full aligned arrays, but those indices will now be a subset that passed the N filter (and optionally subsampling).
- Tests in [packages/methyldetector/tests/test_explorer.py](packages/methyldetector/tests/test_explorer.py) focus on K heuristics and helpers; adding a small unit test for the N-filter logic (e.g. a helper that computes the keep mask from n1, n2, min_N, min_N_pct) would be optional but recommended if the filter logic is factored into a tiny helper for clarity.

