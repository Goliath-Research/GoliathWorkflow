---
name: Distribution-based DMP selection Stage 10
overview: Add an optional distribution-based classifier DMP selection at Stage 10 that keeps as many DMPs as possible while dropping the long tail of low effect_size (e.g. by percentile or relative-to-max threshold), instead of or in addition to the fixed max_dmps_for_classifier cap.
todos: []
isProject: false
---

# Distribution-based DMP selection at Stage 10

## Current behavior

- **Stage 10** ([packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py)): `_select_dmps_multicontext()` returns the **full** biological funnel sorted by `effect_size` (no optimization). Both CSV export and classifier use this set.
- **Classifier cap**: Inside `_build_ecdf_classifier()`, if `max_dmps_for_classifier` is set, the dataframe is truncated to the **top N rows** by effect_size before building the classifier. Export CSV still uses the full `selected_dmps_df`; only the classifier sees the cap.
- **Legacy**: `_optimize_dmps_binary_search()` finds the *minimum* k achieving target balanced accuracy; it is not on the active path (see [packages/methyldetector/docs/METHYLDETECTOR_IMPLEMENTATION.md](packages/methyldetector/docs/METHYLDETECTOR_IMPLEMENTATION.md)).

## Goal

**Maximize** the number of DMPs used for the classifier (and optionally for export) by analyzing the **effect_size distribution** and dropping only DMPs with “much less importance” than others—i.e. remove the long tail instead of a fixed count cap.

## Proposed design

### 1. Distribution-based cutoff (new config + logic)

Add one or two optional config knobs that define a **minimum effect_size threshold** derived from the distribution of effect_size (already sorted descending):

| Approach | Config (example) | Semantics |
|----------|------------------|-----------|
| **Percentile** | `classifier_effect_size_min_percentile: Optional[float] = None` (e.g. `0.05`) | Keep DMPs with `effect_size >=` the 5th percentile of the effect_size values. Drops the bottom 5% of the *distribution by value* (typically many rows if there’s a long tail). |
| **Relative to max** | `classifier_effect_size_min_relative: Optional[float] = None` (e.g. `0.01`) | Keep DMPs with `effect_size >= min_relative * max(effect_size)`. Same idea as the existing weight floor `1e-6` but as a hard filter. |

- **Where to apply**: Apply the cutoff in **one** place so behavior is consistent:
  - **Option A** — In `_select_dmps_multicontext()`: trim the returned dataframe by the distribution-based threshold. Then both **CSV export** and **classifier** use the same trimmed set (maximized DMPs, no weak tail).
  - **Option B** — Only in `_build_ecdf_classifier()` (like current `max_dmps_for_classifier`): export stays full; only the classifier input is trimmed.  

**Recommendation**: **Option A** so a single “selected” set is used everywhere and the CSV reflects what the classifier actually uses.

### 2. Order of operations

When both distribution-based cutoff and `max_dmps_for_classifier` exist:

1. Start with full biological funnel sorted by effect_size desc.
2. **If** `classifier_effect_size_min_percentile` or `classifier_effect_size_min_relative` is set: drop rows below the computed threshold → “maximized” set (no weak tail).
3. **If** `max_dmps_for_classifier` is set and `len(dmps_df) > max_dmps_for_classifier`: further cap to top `max_dmps_for_classifier` rows.

So: distribution trim first (data-driven), then optional fixed cap. If only distribution trim is set, the count is fully data-driven.

### 3. Implementation points

- **Config** ([packages/methyldetector/methyl_detector/models/config.py](packages/methyldetector/methyl_detector/models/config.py)):
  - `classifier_effect_size_min_percentile: Optional[float] = None` in `[0, 1)` (e.g. `0.05` = drop below 5th percentile).
  - `classifier_effect_size_min_relative: Optional[float] = None` in `(0, 1]` (e.g. `0.01` = keep only effect_size >= 1% of max).  
  - At most one of the two should be used in practice (document that; optionally add a validator that only one is set, or apply both and use the stricter threshold).

- **Trim logic** (new helper or inside `_select_dmps_multicontext`):
  - Input: `sorted_df` (biological funnel, sorted by effect_size desc).
  - Compute threshold:  
    - If percentile: `thresh = np.nanpercentile(sorted_df['effect_size'].values, 100 * classifier_effect_size_min_percentile)`.  
    - If relative: `thresh = classifier_effect_size_min_relative * sorted_df['effect_size'].max()`.
  - Keep rows with `effect_size >= thresh` (already sorted, so this is a prefix or a mask). Log how many were dropped.

- **Call site**: In `_select_dmps_multicontext()`, after `sorted_df = self._compute_biological_importance(...)` and before the centroid self-check and return, apply the distribution-based trim if configured. Then the returned dataframe is the “maximized” set (no weak tail). If `max_dmps_for_classifier` is also used, it is applied later in `_build_ecdf_classifier()` as today.

- **Export and model**: No change to callers: `_export_unified_csv(selected_dmps_df)` and `_save_unified_model(None, selected_dmps_df)` already use `selected_dmps_df`; once that is trimmed in `_select_dmps_multicontext`, both export and classifier automatically use the same set.

### 4. Documentation

- Update [packages/methyldetector/docs/MethylDetector_Theoretical_Foundation.md](packages/methyldetector/docs/MethylDetector_Theoretical_Foundation.md) Stage 10 box: describe distribution-based option (drop DMPs below a percentile or relative-to-max threshold to maximize count while removing weak tail); mention that legacy top-k minimization is unused and that optional `max_dmps_for_classifier` can still cap after the distribution trim.
- Update [packages/methyldetector/docs/METHYLDETECTOR_IMPLEMENTATION.md](packages/methyldetector/docs/METHYLDETECTOR_IMPLEMENTATION.md) export handoff section accordingly.

### 5. Edge cases

- If both percentile and relative are set: apply both and keep the **stricter** (higher) threshold so we never keep DMPs below either rule.
- Empty or all-NaN effect_size: skip trim and use full set (or log warning).
- Very high percentile (e.g. 0.95): only top 5% of values kept (fewer DMPs); user trades off “maximize count” vs “drop weak tail”.

---

## Summary

- Add optional **distribution-based** trim at Stage 10: drop DMPs with effect_size below a **percentile** or **relative-to-max** threshold so the retained set is “as many DMPs as possible without the long weak tail.”
- Apply this trim in `_select_dmps_multicontext()` so both CSV and classifier use the same trimmed set; keep `max_dmps_for_classifier` as an optional second cap applied in `_build_ecdf_classifier()`.
- New config: `classifier_effect_size_min_percentile` and/or `classifier_effect_size_min_relative`; document and update Stage 10 docs.
