---
name: Explorer approx overlap alignment and options
overview: The Explorer already uses discrete Bhattacharyya for approximate overlap; the large gap vs exact (147 vs 17254 above 0.5) is likely due to bin_edges misalignment or the discrete BC overestimating overlap. Add bin_edges alignment check with Normal fallback, and an option to use Normal-based overlap for Phase 1 so approx is comparable to exact scale.
todos: []
isProject: false
---

# Fix approximate effect size: bin alignment and overlap method

## Finding

- The Explorer **already uses discrete Bhattacharyya** for Phase 1: `discrete_overlap_from_bin_counts(bc1, bc2, method="bhattacharyya")` (sum sqrt(p1*p2) over bins). So "using discrete Bhattacharyya" is in place.
- **Why approx can be much lower than exact**: (1) **Bin alignment**: `discrete_overlap_from_bin_counts` does not use `bin_edges` — it only sees counts. If the two centroids were built with **different** `bin_edges`, then bin index `i` in centroid1 is a different value range than bin `i` in centroid2. Comparing them gives meaningless overlap (often inflated → high overlap_approx → low effect size). (2) **Different notion**: Exact uses `(1 - ks_d)` (ECDF KS separation); approx uses discrete BC. Binned histograms can look more similar than the true ECDFs → discrete overlap overestimated → approx effect size too small.

## Approach

1. **Require aligned bin_edges for discrete overlap**  
   In [packages/methyldetector/methyl_detector/explorer.py](packages/methyldetector/methyl_detector/explorer.py), after loading centroids and before Phase 1:
   - Compare `centroid1.binned_stats["bin_edges"]` and `centroid2.binned_stats["bin_edges"]` (shape and `np.allclose`).
   - If they differ: **do not** call `discrete_overlap_from_bin_counts`; pass `overlap_approx=None` into `welch_d_fast_overlap_approx` so it uses the **Normal-based** overlap `2 * norm.cdf(-welch_d/2)`. Log a warning that discrete overlap was skipped due to bin_edges mismatch.
   - If they match: keep current behavior (discrete Bhattacharyya).

2. **Optional: force Normal overlap for Phase 1**  
   Add a parameter (e.g. `approx_overlap: Literal["auto", "discrete", "normal"] = "auto"`):
   - `"auto"`: use discrete Bhattacharyya when bin_edges align, else Normal.
   - `"discrete"`: use discrete (error or warning if bin_edges differ).
   - `"normal"`: always use Normal overlap (ignore bin counts for overlap; same as passing `overlap_approx=None`).

   This lets users compare approximate effect size with Normal vs discrete overlap and see if Normal brings approx closer to the exact scale (e.g. 17K vs 147).

3. **Report which overlap was used**  
   Add to the report dict: `approx_overlap_method: "discrete_bhattacharyya" | "normal"` so the user can see whether alignment or method was applied.

4. **Phase 2 (exact) and bin_edges**  
   Phase 2 builds `ECDFView(bin_edges, bc1_k, ...)` and `ECDFView(bin_edges, bc2_k, ...)` with `bin_edges` from **centroid1** only. If centroid2 was built with different edges, `bc2_k` is in the wrong bin space and ECDF is wrong. So: when bin_edges differ, Phase 2 refinement should be **skipped** or **warn** (or require same_edges for ECDF). For consistency, require same bin_edges for the whole run; if they differ, use Normal for Phase 1 and skip Phase 2 refinement (or log warning and still run Phase 2 with centroid1 edges — current behavior — but document that both centroids should use the same bin_edges in the pipeline).

## Files to change

- **[packages/methyldetector/methyl_detector/explorer.py](packages/methyldetector/methyl_detector/explorer.py)**  
  - Add helper to check `same_bin_edges(centroid1, centroid2)` (compare `binned_stats["bin_edges"]`).  
  - In `run()`, before Phase 1: if `approx_overlap == "normal"` or bin_edges differ, set `overlap_approx = None`; else compute `overlap_approx = discrete_overlap_from_bin_counts(bc1, bc2, method="bhattacharyya")`.  
  - Add `approx_overlap` to constructor (default `"auto"`).  
  - Set report field `approx_overlap_method` to `"normal"` or `"discrete_bhattacharyya"`.  
  - Optional: when bin_edges differ, log warning and, if we want to be strict, skip Phase 2 (or leave as-is and document).

- **[packages/methyldetector/methyl_detector/cli/explorer_main.py](packages/methyldetector/methyl_detector/cli/explorer_main.py)**  
  - Add `--approx-overlap` with choices `auto`, `discrete`, `normal` and pass into `MethylDetectorExplorer`.

- **[packages/methyldetector/docs/METHYLDETECTOR_EXPLORER.md](packages/methyldetector/docs/METHYLDETECTOR_EXPLORER.md)**  
  - State that discrete Bhattacharyya is used for approximate overlap when both centroids share the same `bin_edges`; otherwise Normal-based overlap is used.  
  - Document `--approx-overlap`: `auto` (default), `discrete`, `normal`.  
  - Note that for comparable exact vs approx results, both centroids must be built with the same `binned_stats_bins` / bin_edges; using `--approx-overlap normal` avoids bin alignment issues for the approximation.

## Summary

- **We already use discrete Bhattacharyya**; the problem is likely bin_edges misalignment or the discrete metric overestimating overlap.  
- **Fix**: Check bin_edges; when they differ (or when user chooses `normal`), use Normal overlap for Phase 1 and report the method used.  
- **Optional**: `--approx-overlap normal` to force Normal-based approximate overlap and see if approx counts (e.g. above 0.5) get closer to exact.
