---
name: Assumption-free funnel
overview: Replace the Welch t-test (which assumes CLT normality) with a distribution-free Mann-Whitney U test computed from bin_counts histograms; add a DerSimonian-Laird heterogeneity decomposition using already-stored centroid fields (Sm, Su, Swx2, Sc2) to separate within-sample measurement noise from biological variability; and introduce a biological-only DMP rescue track so biologically important positions survive even when statistical significance cannot be guaranteed.
todos:
  - id: mann-whitney-fn
    content: Add vectorized mann_whitney_from_bin_counts() to statistical_tests.py
    status: pending
  - id: dl-het-fn
    content: Add dl_heterogeneity() to statistical_tests.py using Sm, Su, Swx2, Sc2, N
    status: pending
  - id: centroid-pair-dtype
    content: Add tau2_1, tau2_2 fields to CENTROID_COMPARISON_DTYPE in methyl_centroid_pair.py
    status: pending
  - id: centroid-pair-batch
    content: "In _process_batch: replace welch_mean_test with mann_whitney_from_bin_counts, call dl_heterogeneity, deduplicate bc1/bc2 extraction"
    status: pending
  - id: config-bio-only
    content: Add biological_only_* and max_tau2_for_dmp config fields to config.py
    status: pending
  - id: detector-bio-track
    content: Add biological-only DMP rescue track in methyldetector.py with statistical_dmp / biological_dmp flags
    status: pending
  - id: eat-decouple
    content: Decouple EAT from p_value manipulation — apply only to effect_size as a multiplicative weight
    status: pending
isProject: false
---

# Assumption-Free Funnel Filter

## Mathematical Foundation

### Why Mann-Whitney from bin_counts

The centroid already stores `bin_counts[i, k]` — how many of the N samples at position i had methylation fraction in bin k (20 bins over [0,1] by default). The Mann-Whitney U statistic counts concordant pairs between two groups and is computed exactly from two such histograms:

```
cs2   = cumsum(bc2, axis=1)                          # cumulative counts for group 2
shifted_cs2 = [zeros | cs2[:, :-1]]                 # counts BELOW each bin (axis shift)
U     = sum(bc1 * shifted_cs2, axis=1)              # pairs where x1 > x2
      + 0.5 * sum(bc1 * bc2, axis=1)                # tied pairs
```

Asymptotic p-value (tie-corrected):

```
N = N1 + N2
t_k = bc1[:,k] + bc2[:,k]                           # total obs in bin k (all ties)
tie_corr = sum(t_k * (t_k**2 - 1), axis=1) / (N*(N-1))
Var(U) = N1*N2/12 * ( (N+1) - tie_corr )
z = (U - N1*N2/2) / sqrt(Var(U))
p_value = 2 * norm.sf(|z|)
```

This replaces `welch_mean_test`. No normality assumption. The only assumption is independent samples — the same assumption Welch makes, without CLT.

### Why DerSimonian-Laird from existing centroid fields

From the stored fields, with no new data required:

```
c_total_j  = Sm_j + Su_j                            # total read coverage for group j
theta_j    = Sm_j / c_total_j                       # coverage-weighted pooled proportion
Q_j        = Swx2_j - Sm_j² / c_total_j            # Cochran's Q (between-sample heterogeneity)
denom_j    = c_total_j - Sc2_j / c_total_j          # DL denominator
tau2_j     = max(0,  (Q_j - (N_j - 1)) / denom_j)  # between-sample biological variance
```

`Q_j` measures overdispersion beyond binomial noise. `tau2_j` is the biological between-sample variance, stripped of within-sample measurement noise. This is used as an **auxiliary column** in the results and optionally as a second filter dimension (high tau2 in both groups may indicate heterogeneous subpopulations rather than a clean DMP).

> Note: `Q_j = Swx2_j - Sm_j²/(Sm_j+Su_j)` is 100% computable from existing centroid fields without any new accumulators.

### Biological-only rescue track

```
Final DMPs = (q_value ≤ alpha  AND  biological filters)     [statistical confirmation]
           ∪ (biological-only filters, stricter thresholds)  [biological evidence only]
```

Each output row carries two new boolean columns: `statistical_dmp` and `biological_dmp`.

---

## Changes Required

### 1. `[packages/methylutils/methyl_utils/statistical_tests.py](packages/methylutils/methyl_utils/statistical_tests.py)`

Add two new functions (do not remove `welch_mean_test` — it stays as fallback):

**a) `mann_whitney_from_bin_counts(bc1, bc2, n1, n2)`**

- Inputs: `(n_pos, n_bins)` batch arrays already extracted in `_process_batch`, plus `N1`, `N2` 1-D arrays
- Returns `{"u_stat", "p_value"}` (vectorized, no loops)
- Guard: if `Var(U) ≤ 0` for any position (both N = 0, or all in one bin), return `p_value = 1.0`

**b) `dl_heterogeneity(Sm, Su, Swx2, Sc2, N)`**

- Single-group function; call once per centroid in `_process_batch`
- Returns `{"theta", "Q", "tau2"}` — all `(n_pos,)` arrays
- `Q = Swx2 - Sm²/c_total`; `tau2 = max(0, (Q-(N-1))/(c_total-Sc2/c_total))`

### 2. `[packages/methylutils/methyl_utils/methyl_centroid_pair.py](packages/methylutils/methyl_utils/methyl_centroid_pair.py)`

In `_process_batch` (line ~800), after the ECDF-only simplification:

- Extract `Sm1, Su1, Swx2_1, Sc2_1` from `centroid1[indices1]` (all properties already exist)
- Extract `Sm2, Su2, Swx2_2, Sc2_2` from `centroid2[indices2]`
- **Replace** `welch_mean_test(...)` with `mann_whitney_from_bin_counts(bc1_batch, bc2_batch, N1, N2)` using `bc1_batch` and `bc2_batch` already extracted for Bhattacharyya at lines 1213-1215 (extract once, reuse)
- Call `dl_heterogeneity(...)` for each group and store `tau2_1`, `tau2_2` in the results array

Add two new fields to `CENTROID_COMPARISON_DTYPE` (line ~68):

```python
('tau2_1', np.float32),   # DL biological between-sample variance, group 1
('tau2_2', np.float32),   # DL biological between-sample variance, group 2
```

### 3. `[packages/methyldetector/methyl_detector/models/config.py](packages/methyldetector/methyl_detector/models/config.py)`

Add biological-only track parameters:

```python
biological_only_min_delta_mean: Optional[float] = Field(default=None, ...)
biological_only_max_overlap:    Optional[float] = Field(default=None, ...)
biological_only_min_effect_size: Optional[float] = Field(default=None, ...)
max_tau2_for_dmp: Optional[float] = Field(
    default=None,
    description="If set, exclude positions where both tau2_1 and tau2_2 exceed this value "
                "(suggests heterogeneous subpopulations rather than a clean DMP)."
)
```

### 4. `[packages/methyldetector/methyl_detector/core/methyldetector.py](packages/methyldetector/methyl_detector/core/methyldetector.py)`

**a) Replace `welch_mean_test` with `mann_whitney_from_bin_counts`** — the `MethylCentroidPair` already handles this internally after change 2, so no direct call here.

**b) After the statistical filter at line 426**, add the biological-only rescue:

```python
# Statistical track
stat_dmps = comparison_results[comparison_results['q_value'] <= self.config.alpha].copy()
stat_dmps['statistical_dmp'] = True
stat_dmps['biological_dmp'] = False

# Biological-only rescue (positions that failed statistical gate)
if any of the biological_only config params are set:
    candidates = comparison_results[comparison_results['q_value'] > self.config.alpha]
    bio_only = _apply_biological_filters(candidates,
        min_delta_mean=config.biological_only_min_delta_mean,
        max_overlap=config.biological_only_max_overlap,
        min_effect_size=config.biological_only_min_effect_size)
    bio_only['statistical_dmp'] = False
    bio_only['biological_dmp'] = True
    stat_dmps = pd.concat([stat_dmps, bio_only])
```

**c) EAT decoupling** (if EAT is kept): replace p-value multiplication/division (lines 573-601) with an `eat_effect_weight` multiplier applied only to the `effect_size` column, leaving `p_value` and `q_value` untouched.

---

## What is NOT changed

- `effect_size_from_components` — stays as-is; the ECDF overlap integral is already distribution-free
- `_apply_fdr_correction` — Storey's TSBH stays; the FDR liberal bias from pre-filtering is a known screen-and-test tradeoff
- `ecdf_overlap_integral` and the final biological filters on `overlap` / `effect_size` — already fully distribution-free
- The centroid H5 schema — no new accumulator fields needed (DL uses fields already stored)
- `welch_mean_test` function — kept as available utility, just no longer the primary gate

---

## Assumption Inventory After Changes


| Test / Step               | Assumption after change                                      | Status                              |
| ------------------------- | ------------------------------------------------------------ | ----------------------------------- |
| Mann-Whitney U (new gate) | Independent samples                                          | Minimal — same as before            |
| MW asymptotic Normal      | N1, N2 > ~8                                                  | Much weaker than t-distribution CLT |
| DL tau2                   | Coverage similar across samples (for tie_corr approximation) | Auxiliary metric only               |
| FDR (Storey TSBH)         | Independence / PRDS, sufficient nulls                        | Unchanged — known tradeoff          |
| ECDF overlap integral     | Continuous distribution                                      | Already in place                    |
| EAT (if kept)             | EAT score used only as effect-size weight, not on p-values   | Statistical gate is now clean       |


