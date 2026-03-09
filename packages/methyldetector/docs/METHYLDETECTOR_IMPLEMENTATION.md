# MethylDetector Implementation

This document describes how MethylDetector is implemented on top of **MethylUtils**: centroid comparison, statistics, ECDF scoring, filtering, and classifier training.

---

## Architecture

- **MethylUtils** owns all centroid comparison math: Welch test, FDR correction, ECDF overlap, `effect_size`, and ECDFClassifier.
- **MethylDetector** owns the pipeline: config, per-chromosome/context orchestration, staged filtering, DMP selection, classifier invocation, and exports.

```mermaid
flowchart LR
    Config[JSON Config]
    Detector[MethylDetector]
    Pair[MethylCentroidPair]
    Welch[Welch mean test]
    FDR[fdr_tsbh]
    ECDF[Continuous ECDF overlap]
    Effect[effect_size formula]
    Filter[Biological Filter]
    Clf[ECDFClassifier]
    Out[CSV and Classifier model]

    Config --> Detector
    Detector --> Pair
    Pair --> Welch
    Welch --> FDR
    FDR --> ECDF
    ECDF --> Effect
    Effect --> Filter
    Filter --> Clf
    Clf --> Out
```

---

## MethylCentroidPair (methyl_utils)

### `compare_centroids(centroid1, centroid2, position_subset=None)`

The primary comparison entry point.

- Aligns centroids to common positions; applies `position_subset` to restrict the comparison when a pre-filter has already reduced the candidate set.
- Runs a Welch-style unequal-variance mean-difference test on every aligned position.
- Applies Two-Stage Benjamini-Hochberg FDR correction.
- Returns a DataFrame with columns: `position`, `p_value`, `q_value`, `mean1`, `mean2`, `delta_mean`, `delta_sign`, `variance1`, `variance2`, `n1`, `n2`, `overlap_approx`, `effect_size` (initial discrete overlap-based), `alpha1/beta1/alpha2/beta2` (retained for EAT downstream), `dist` (always `DIST_ECDF = 5`).

### `load_and_align(path1, path2, min_coverage=...)`

Loads centroid HDF5 files, intersects positions, and applies the coverage filter. Returns `(centroid1, centroid2, common_positions)`.

### `validate_centroid_parameters(centroid1, centroid2)`

Pre-run sanity check (N, means, variances, ECDF availability).

### `extract_methylation_fractions(...)`

Extracts methylation fractions for real validation samples at the selected DMP positions.

---

## MethylUtils modules used

| Module / symbol | Role in MethylDetector |
|----------------|------------------------|
| `MethylCentroidPair` | All centroid comparison (see above) |
| `statistical_tests.welch_mean_test` | Per-position Welch t-test |
| `statistical_tests.ecdf_effect_size` | Continuous ECDF overlap + final `effect_size` |
| `statistical_tests.ecdf_overlap_integral` | Integration of min(f1, f2) |
| `statistical_tests.effect_size_from_components` | `\|delta_mean\| * (1-overlap) * exp(-λ*(√v1+√v2))` |
| `core.distribution_views.ECDFView` | PCHIP-based CDF/PDF, built lazily for DMP positions only |
| `ecdf_classifier.ECDFClassifier` | PCHIP PDF log-likelihood classifier |
| `load_from_h5` | Loading centroid H5 for bin_counts extraction at classifier build |
| `gpu_detection`, `memory_manager` | GPU and memory handling |
| `core.methyl_frame.MethylSample` | Validation sample loading |
| Optional: `compute_eat_T` | EAT reweighting (when enabled) |

---

## Detection Pipeline (per chromosome × context)

### 1. Pre-filter (cheap delta_mean gate)

Computes `|mean1 - mean2|` from centroid means (`Sx/N`) at all common positions. Positions below `delta_mean_reduction` (or `min_delta_mean` if not set) are removed before any expensive computation.

**Why**: Welch test (`scipy.stats.t.sf`) is CPU-bound. CHH has 70M+ positions. A position removed here would be discarded by the biological filter anyway, so pre-filtering costs nothing biologically.

**Statistical note**: FDR is then applied to the pre-filtered subset. Q-values are therefore liberal relative to the full test set — a known screen-and-test trade-off acceptable for practical genomics.

### 2. Centroid alignment and coverage filter

`MethylCentroidPair.compare_centroids(..., position_subset=pre_filter_positions)` restricts the comparison to the pre-filtered set.

### 3. Welch test + FDR

`welch_mean_test` on all pre-filtered positions. Two-stage BH correction (`fdr_tsbh`). Retain positions with `q_value <= alpha`.

### 4. Lazy ECDFView construction

For the surviving DMP positions only, build two `ECDFView` objects:

```python
idx_in_c1 = np.searchsorted(pos1, dmp_positions)
idx_in_c2 = np.searchsorted(pos2, dmp_positions)
ecdf_view1 = ECDFView(bin_edges, bin_counts_c1[idx_in_c1], Sx1[idx_in_c1], N1[idx_in_c1], Sx2_1[idx_in_c1])
ecdf_view2 = ECDFView(bin_edges, bin_counts_c2[idx_in_c2], Sx2[idx_in_c2], N2[idx_in_c2], Sx2_2[idx_in_c2])
```

Both views use their **own correct per-centroid indices** so the PCHIP PDFs correspond to the right genomic positions in each centroid.

### 5. Continuous ECDF overlap and final effect_size

`ecdf_effect_size(delta_mean, var1, var2, ecdf_view1, ecdf_view2, sequential_indices, lambda_var, grid_size)` — the pre-sliced views mean the indices are simply `0, 1, 2, …`.

Output: `overlap`, `effect_size`, `effect_size_reliability` added to the DMP DataFrame.

### 6. Biological filter

```
keep = (|delta_mean| >= min_delta_mean) AND
       (overlap      <= max_overlap) AND
       (effect_size  >= min_effect_size)   # or effect_size_quantile
```

Sort surviving DMPs by `effect_size` descending; add `effect_size_ecdf` column.

---

## Classifier Training

MethylDetector trains an `ECDFClassifier` on the selected biological DMPs.

### Building the classifier

At the three call sites (centroid self-check, validation, model save), MethylDetector:

1. Normalises `effect_size` → `weight` (divided by max, clipped to `[1e-6, 1]`).
2. Calls `_extract_bin_counts_for_dmps(dmps_df)` to reload the `bin_counts` histograms for the selected DMP positions from the centroid H5 files.
3. Calls `ECDFClassifier.from_dataframe(dmpDF, bin_edges, bc1, bc2, temperature=...)`.

Fallback to `BetaClassifier` is in place for cases where centroid H5 files are unavailable.

### `_extract_bin_counts_for_dmps(dmps_df)`

Groups DMPs by chromosome × context, loads the corresponding centroid H5 files (once per group), and extracts `bin_counts` at the DMP positions via `np.searchsorted`. Returns `(bin_edges, bc1, bc2)`.

### ECDFClassifier prediction

```
log L(class_k | x) = Σ_i  w_i · log F'_k_i(x_i)
P(class_k | x) ∝ exp( log L / T )
```

Per-position PCHIP PDF values are pre-computed into a dense lookup table at construction time; prediction uses `np.interp` (no Python loop over samples). Supports NaN positions (contribute zero to the log-likelihood sum), Platt calibration, `.save()`/`.load()` via `.npz`.

---

## Model Serialisation

The classifier model is saved as a `.pkl` package containing:

- `classifier`: `ECDFClassifier` instance (holds `bin_edges`, `bin_counts_c1/c2`, `weights`, `directions`, `temperature`).
- `dmpDF`: DataFrame with `pos`, `weight`, `context`, `delta_sign`.
- `metadata`: version, `classifier_type` (`"ECDFClassifier"` or `"BetaClassifier"` fallback), contexts, config, centroid file references.

---

## Summary

| Layer | Component | Role |
|-------|-----------|------|
| MethylUtils | `MethylCentroidPair` | Centroid load, align, compare (Welch + FDR + initial effect_size) |
| MethylUtils | `statistical_tests` | Welch test, ecdf_overlap_integral, effect_size_from_components |
| MethylUtils | `ECDFView` | Lazy PCHIP CDF/PDF for DMP positions only |
| MethylUtils | `ECDFClassifier` | PCHIP PDF log-likelihood classifier, save/load |
| MethylUtils | GPU/memory | Device selection, memory management |
| MethylDetector | `MethylDetector` | Config, orchestration, pre-filter, biological filter, classifier invocation, export |

For theoretical background, see [MethylDetector_Theoretical_Foundation.md](MethylDetector_Theoretical_Foundation.md).
