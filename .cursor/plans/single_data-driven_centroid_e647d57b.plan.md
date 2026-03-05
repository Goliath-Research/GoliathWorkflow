---
name: Single data-driven centroid
overview: Consolidate to one centroid type that stores only N, mC, uC, Sx, Sx2 (mean/variance) and first-class bin_edges/bin_counts (ECDF). Remove MethylBasicCentroid and MethylBetaBinomialCentroid, drop log_x_sum/log_1_minus_x_sum and all Beta-Binomial count stats. Derive Beta parameters from Sx/Sx2/N via method-of-moments. Update MethylUtils, MethylCentroid, MethylCentroidExplorer, MethylDetector, MethylClassifier, MethylCluster, IO, tests, and docs.
todos: []
isProject: false
---

# Single data-driven centroid (N, mC, uC, Sx, Sx2, bin_edges, bin_counts)

## Target schema

One centroid type with:

- **Per-position table**: `pos`, `mC`, `uC`, `tnc`, `N`, `Sx`, `Sx2`
- **Binned stats (first-class)**: `bin_edges` (global, length `n_bins + 1`), `bin_counts` (shape `(n_positions, n_bins)`); `n_bins` is a build-time constant (e.g. `binned_stats_bins` in config)

**Removed**:

- `log_x_sum`, `log_1_minus_x_sum` (Beta MLE)
- All Beta-Binomial count columns: `sum_cov`, `sum_cov2`, `sum_mC`, `sum_uC`, `sum_mC2`, `sum_uC2`, `Sx3`, `Sx4`, `count_zero`, `count_one`

**Derived (not stored)**:

- Mean = Sx/N, variance = (Sx2 - Sx²/N)/(N-1)
- Beta (alpha, beta) = method-of-moments from N, Sx, Sx2 via existing `beta_mom_estimation` in [packages/methylutils/methyl_utils/statistical_tests.py](packages/methylutils/methyl_utils/statistical_tests.py)

---

## 1. MethylUtils – core centroid and IO

### 1.1 [packages/methylutils/methyl_utils/core/methyl_frame.py](packages/methylutils/methyl_utils/core/methyl_frame.py)

- **Remove** classes: `MethylBasicCentroid`, `MethylBetaBinomialCentroid`.
- **Keep** `MethylExtendedCentroid` as the single centroid class; change `_required_cols` to `{pos, mC, uC, tnc, N, Sx, Sx2}` only (remove `log_x_sum`, `log_1_minus_x_sum`). Remove `_required_stats` or set to `{Sx, Sx2}`.
- **Alpha/beta**: In `MethylExtendedCentroid.alpha` (and `.beta`), stop using `beta_estimation_hybrid` (which needs log sums). Use only `beta_mom_estimation(N, Sx, Sx2)` from `statistical_tests` to compute and cache alpha/beta.
- **Remove** properties: `log_x_sum`, `log_1_minus_x_sum`.
- **add_sample / remove_sample**: Update to accumulate only N, mC, uC, Sx, Sx2 (no log sums). Signatures and return type stay `MethylExtendedCentroid`. If binned_stats are present, add/remove must update `bin_counts` (and keep `bin_edges` unchanged).
- **to_numpy**: Emit only the single dtype (pos, mC, uC, tnc, N, Sx, Sx2). No log or BB columns.
- **save_to_h5**: Write only core columns and `binned_stats` group (bin_edges, bin_counts). Do not write log_x_sum, log_1_minus_x_sum, or BB columns.
- **MethylFrame** (base): Keep `binned_stats` and `set_binned_stats`; ensure `apply_mask` and save/load still handle `binned_stats` (bin_counts sliced by position).

### 1.2 [packages/methylutils/methyl_utils/core/centroid_builder.py](packages/methylutils/methyl_utils/core/centroid_builder.py)

- **Remove** `store_extended_stats` and all accumulators for log sums and BB count stats (log_x_sum, log_1x_sum, sum_cov, sum_cov2, sum_mC, sum_uC, sum_mC2, sum_uC2, Sx3, Sx4, count_zero, count_one).
- **Keep** accumulators: pos, mC_sum, uC_sum, N, Sx, Sx2, tnc; add **bin_edges** (fixed at build from config, e.g. `np.linspace(0, 1, n_bins+1)`) and **bin_counts** (per-position histogram).
- **Constructor**: Accept `binned_stats_bins` (or equivalent); always build binned_stats (bin_edges + bin_counts). No optional “extended” vs “BB” mode.
- **finalize()**: Return a single type: `MethylExtendedCentroid` with DataFrame containing only pos, mC, uC, tnc, N, Sx, Sx2, and set `binned_stats = {bin_edges, bin_counts}` on the instance.
- **add_sample**: Update to accumulate only N, mC, uC, Sx, Sx2 and bin_counts (no log sums, no BB stats).
- **release_gpu**: Update attribute list to match remaining accumulators (including bin_counts).

### 1.3 [packages/methylutils/methyl_utils/core/io.py](packages/methylutils/methyl_utils/core/io.py)

- **load_from_h5**: After building `data` from HDF5, detect centroid by presence of N and Sx, Sx2 (and core columns). Always instantiate `MethylExtendedCentroid`; never `MethylBasicCentroid` or `MethylBetaBinomialCentroid`. Do not require or load `log_x_sum`, `log_1_minus_x_sum`, or BB columns (if present in file, ignore for compatibility).
- **Save path**: Already handled by methyl_frame save_to_h5 (writes only new schema).
- **binned_stats**: Load `binned_stats/bin_edges` and `binned_stats/bin_counts` when present and set on the centroid (e.g. via `set_binned_stats`).

### 1.4 [packages/methylutils/methyl_utils/**init**.py](packages/methylutils/methyl_utils/__init__.py) and [packages/methylutils/**init**.py](packages/methylutils/__init__.py)

- **Remove** exports: `MethylBasicCentroid`, `MethylBetaBinomialCentroid`.
- **Keep** `MethylCentroid` and `MethylBetaCentroid` as aliases for `MethylExtendedCentroid`.
- **Dtypes**: Remove or replace `METHYL_EXTENDED_ONLY_DTYPE` (and any BB dtype) with a single centroid dtype: pos, mC, uC, tnc, N, Sx, Sx2. Remove log_x_sum, log_1_minus_x_sum and BB fields from any public dtype constants.

---

## 2. MethylUtils – pair, tests, distribution views, ECDF

### 2.1 [packages/methylutils/methyl_utils/methyl_centroid_pair.py](packages/methylutils/methyl_utils/methyl_centroid_pair.py)

- **Types**: Use only `MethylExtendedCentroid` (no MethylBetaBinomialCentroid).
- **Beta path**: Use centroid.N, Sx, Sx2 (and derived alpha/beta from MoM) only. Remove all uses of `log_x_sum`, `log_1_minus_x_sum`, `sum_cov`, `sum_cov2`, `alpha_bb`, `beta_bb`, and other BB-only fields.
- **ECDF path**: Keep and rely on `binned_stats` (bin_edges, bin_counts); require same bin_edges for both centroids when using ECDF.
- **distribution=beta_binomial**: Remove or map to Beta (MoM) or ECDF; document that Beta-Binomial is no longer a separate centroid type.
- **Zero-fill / empty centroid**: Still return `MethylExtendedCentroid` with only core columns (no log, no BB).

### 2.2 [packages/methylutils/methyl_utils/statistical_tests.py](packages/methylutils/methyl_utils/statistical_tests.py)

- **Functions** that take `log_x_sum` / `log_1_minus_x_sum` for centroid-based tests: switch to MoM from N, Sx, Sx2 where appropriate, or accept only (N, Sx, Sx2) and use `beta_mom_estimation`.
- `**_estimate_beta_params_bounded`**: Used in pair tests; either refactor to use (N, Sx, Sx2) and MoM, or keep for internal use with explicit N, Sx, Sx2 (no log sums from centroid).
- **beta_binomial_mom_estimation**: Keep for non-centroid use if needed; centroid code paths will no longer pass count stats from centroids.

### 2.3 [packages/methylutils/methyl_utils/core/distribution_views.py](packages/methylutils/methyl_utils/core/distribution_views.py)

- **BetaView**: Build from Sx, N, Sx2 (MoM alpha/beta). Remove dependency on `log_x_sum` or BB columns.
- **ECDFView**: Unchanged; requires `binned_stats` (bin_edges, bin_counts).
- **BetaBinomial view**: Remove or implement as thin wrapper over Beta (MoM) if still needed for API compatibility; no centroid-specific count stats.
- `**ecdf_view_from_centroid` / `log_probability(..., mode="ecdf")`**: Keep; they already require binned_stats.

### 2.4 [packages/methylutils/methyl_utils/ecdf_fit.py](packages/methylutils/methyl_utils/ecdf_fit.py)

- **Centroid extraction**: Remove use of `centroid.alpha_bb`, `centroid.beta_bb`. Use `centroid.alpha`, `centroid.beta` (now from MoM) when fitting or comparing to ECDF.

### 2.5 MethylUtils tests and docs

- **Tests** that construct MethylBasicCentroid or MethylBetaBinomialCentroid: update to use MethylExtendedCentroid with only core + binned_stats (e.g. [packages/methylutils/methyl_utils/tests/test_centroid_builder.py](packages/methylutils/methyl_utils/tests/test_centroid_builder.py), [packages/methylutils/methyl_utils/tests/test_centroid_creation.py](packages/methylutils/methyl_utils/tests/test_centroid_creation.py)).
- **Docs**: [packages/methylutils/docs/METHYLSAMPLE_CLASS_HIERARCHY.md](packages/methylutils/docs/METHYLSAMPLE_CLASS_HIERARCHY.md) and related: describe single centroid (MethylExtendedCentroid) with N, mC, uC, Sx, Sx2, bin_edges, bin_counts; remove Basic/BetaBinomial from hierarchy.

---

## 3. MethylCentroid package

### 3.1 [packages/methylcentroid/methyl_centroid/methyl_centroid.py](packages/methylcentroid/methyl_centroid/methyl_centroid.py)

- **Builder usage**: Call MethylCentroidBuilder with only the new contract (no `store_extended_stats`); always pass `binned_stats_bins` and have builder produce binned_stats.
- **Centroid type**: Everywhere use `MethylExtendedCentroid` only. Remove creation of `MethylBasicCentroid` (e.g. save_centroid branch that chose Basic vs Extended from columns); always save as MethylExtendedCentroid with core columns + binned_stats.
- **Empty/min_samples**: When creating an empty or filtered centroid, use MethylExtendedCentroid with columns pos, mC, uC, tnc, N, Sx, Sx2 only (no log, no BB); set binned_stats to None or empty if no bins.
- **Dtype / structured arrays**: Use the single centroid dtype (no log_x_sum, log_1_minus_x_sum) in `_compute_centroid_for_positions` and save path.
- **Config**: Keep `enable_binned_stats` and `binned_stats_bins`; treat binned_stats as the standard output (recommend enable_binned_stats=True or make it default and only mode for the single centroid).

### 3.2 [packages/methylcentroid/methyl_centroid/explorer.py](packages/methylcentroid/methyl_centroid/explorer.py) (MethylCentroidExplorer)

- **DataFrame export / display**: Stop reading or displaying `log_x_sum`, `log_1_minus_x_sum`, `alpha_bb`, `beta_bb`, and BB columns (sum_cov, sum_cov2, sum_mC, sum_uC, etc.). Keep `alpha`, `beta` (now from MoM).
- **Property getter**: Remove alpha_bb/beta_bb branch; keep scalar alpha/beta from centroid for PDF/overlay.
- **Docs/comments**: Update to describe single centroid with N, Sx, Sx2, binned_stats.

---

## 4. MethylDetector, MethylClassifier, MethylCluster

### 4.1 [packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py)

- **Require** centroids to have `binned_stats` (already does); ensure no use of `alpha_bb`/`beta_bb` or log sums. Use only mean/variance (Sx, N, Sx2) and ECDF (binned_stats) as needed.
- **Config / messages**: Keep “build with enable_binned_stats” style messaging; align with single centroid format.

### 4.2 [packages/methylclassifier/methyl_classifier/utils/multiclass_builder.py](packages/methylclassifier/methyl_classifier/utils/multiclass_builder.py) and data loading

- **centroid.alpha / centroid.beta**: No API change; these remain on MethylExtendedCentroid (now computed via MoM from Sx, Sx2, N). Verify classifiers still work with MoM-derived alpha/beta.

### 4.3 [packages/methylcluster/methyl_cluster/centroid_manager.py](packages/methylcluster/methyl_cluster/centroid_manager.py)

- **centroid.alpha / centroid.beta**: Same as classifier; no API change. Confirm no use of alpha_bb or BB-only fields.

---

## 5. Backward compatibility and migration

- **Loading old HDF5**: If file has `log_x_sum`, `log_1_minus_x_sum`, or BB columns, do not load them into the centroid; load only pos, mC, uC, tnc, N, Sx, Sx2 and binned_stats (if present). This allows old files to be read; re-saving will write new format.
- **Saving**: Always write the new schema only (no log or BB columns).
- **Document** in release notes that centroid format has changed and old centroid H5 files are readable but will be saved in the new format.

---

## 6. Order of implementation (suggested)

1. **MethylUtils methyl_frame**: Single centroid class, remove Basic/BB, alpha/beta from MoM, add/remove_sample and to_numpy/save with new schema only.
2. **MethylUtils centroid_builder**: Only N, mC, uC, Sx, Sx2, bin_edges, bin_counts; always output MethylExtendedCentroid with binned_stats.
3. **MethylUtils io**: Load/save single format; type detection only MethylExtendedCentroid for centroids.
4. **MethylUtils init / dtypes**: Remove Basic/BB exports and old dtypes.
5. **MethylUtils methyl_centroid_pair, statistical_tests, distribution_views, ecdf_fit**: Remove log/BB dependencies; use MoM and binned_stats only.
6. **MethylCentroid package**: Use only new builder and MethylExtendedCentroid; update explorer.
7. **MethylDetector, MethylClassifier, MethylCluster**: Verify and minimal changes (no alpha_bb; keep alpha/beta).
8. **Tests and docs**: Update across MethylUtils, MethylCentroid, and dependent packages.

---

## Files to touch (summary)


| Package          | Files                                                                                                                                                                                                                                                        |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| MethylUtils      | core/methyl_frame.py, core/centroid_builder.py, core/io.py, core/distribution_views.py, methyl_centroid_pair.py, statistical_tests.py, ecdf_fit.py, **init**.py (methylutils and package); memory_manager.py if it references log/BB columns; tests and docs |
| MethylCentroid   | methyl_centroid.py, explorer.py, tests                                                                                                                                                                                                                       |
| MethylDetector   | methyldetector.py (verify only)                                                                                                                                                                                                                              |
| MethylClassifier | multiclass_builder.py, data_loader (verify)                                                                                                                                                                                                                  |
| MethylCluster    | centroid_manager.py (verify)                                                                                                                                                                                                                                 |


No change to the theoretical ECDF or overlap logic; only the centroid storage and class hierarchy are simplified to a single data-driven format.