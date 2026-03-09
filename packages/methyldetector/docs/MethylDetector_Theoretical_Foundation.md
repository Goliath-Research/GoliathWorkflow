# MethylDetector Theoretical Foundation

## Goal

`MethylDetector` identifies differentially methylated positions (DMPs) between two methylation centroids (e.g. healthy vs disease) with:

- **Statistical rigour**: Welch-style unequal-variance mean-difference testing and FDR correction.
- **Biological relevance**: A single canonical score (`effect_size`) that penalises positions where the distributions overlap heavily or where within-group variance is large.
- **Computational tractability**: A staged funnel that avoids CPU-bound ECDF work on millions of positions that could never pass the biological filter.

All distribution comparisons use the **ECDF only** — no Beta, Normal, or Beta-Binomial models.

---

## Staged Pipeline

```
Centroid H5 files (must have binned_stats)
    │
    ├─ Stage 1 — Pre-filter (cheap)
    │     Compute |delta_mean| = |mean1 - mean2| from centroid means (Sx/N).
    │     Discard positions below delta_mean_reduction / min_delta_mean threshold.
    │     Purpose: avoid running the expensive Welch test on positions that will
    │     be discarded by the biological filter later.
    │
    ├─ Stage 2 — Centroid alignment
    │     np.intersect1d(pos1, pos2) + coverage filter (min(N1,N2) >= min_coverage).
    │
    ├─ Stage 3 — Welch-style significance test
    │     For each aligned position:
    │         t_stat = |mean1 - mean2| / sqrt(var1/N1 + var2/N2)
    │         p_value = 2 * t_dist.sf(t_stat, df=Welch-Satterthwaite dof)
    │     Sample variances from (Sx2 - Sx²/N)/(N-1).
    │
    ├─ Stage 4 — FDR correction
    │     Two-stage Benjamini-Hochberg (statsmodels fdr_tsbh) on the
    │     pre-filtered position set.
    │     Note: FDR is applied to the pre-filtered subset only; q-values are
    │     therefore liberal relative to testing all positions.
    │
    ├─ Stage 5 — Statistical filter
    │     Retain positions with q_value <= alpha.
    │
    ├─ Stage 6 — Lazy ECDFView construction
    │     Build PchipInterpolator only for the surviving DMP positions,
    │     using the correct per-centroid indices.  Not the full centroid.
    │
    ├─ Stage 7 — Continuous ECDF overlap and effect_size
    │     For each retained position:
    │         overlap = ∫₀¹ min(f1(x), f2(x)) dx
    │     where f1, f2 are PCHIP-derived PDFs from centroid binned_stats.
    │     effect_size = |delta_mean| * (1 - overlap) * exp(-λ * (√var1 + √var2))
    │
    └─ Stage 8 — Biological filter
          AND of: |delta_mean| >= min_delta_mean
                  overlap      <= max_overlap
                  effect_size  >= min_effect_size  (or effect_size_quantile)
          Sort surviving DMPs descending by effect_size.
```

---

## Canonical Effect Size

```
effect_size = |delta_mean| * (1 - overlap) * exp(-lambda_var * (sqrt(var1) + sqrt(var2)))
```

| Term | Meaning |
|------|---------|
| `\|delta_mean\|` | Absolute difference in mean methylation between groups |
| `1 - overlap` | Distributional separation; 0 = complete overlap, 1 = no overlap |
| `exp(-lambda_var * (√var1 + √var2))` | Reliability penalty; reduces score for diffuse, heterogeneous positions |

`lambda_var` (default `2.0`) controls the strength of the variance penalty. Both variances are treated independently so no equal-variance assumption is made.

---

## Overlap Definition

```
overlap = ∫₀¹ min(f1(x), f2(x)) dx
```

where `f1(x)` and `f2(x)` are the PCHIP-derived PDFs obtained by differentiating the spline CDF built from centroid `binned_stats`. The integral is evaluated with the trapezoidal rule on a dense grid (default 512 points). PDFs are renormalised before integration to guard against small numerical drift in spline derivatives.

This definition captures bimodal distributions and is consistent with the ECDFClassifier used in the downstream classification stage.

---

## Variance in the Reliability Term

The variances used in `effect_size` are the **sample variances** from `(Sx2 - Sx²/N)/(N-1)`, i.e. the same estimator used by the Welch test. This makes the reliability penalty consistent with the statistical test — a position penalised by the Welch test for high within-group spread is also penalised in `effect_size`.

---

## Why the Pre-filter Is Before the Statistical Test

The Welch t-test calls `scipy.stats.t.sf`, which is CPU-bound. For CHH contexts with more than 70 million positions, testing every position is expensive. Positions with `|delta_mean| < threshold` will be removed by the biological filter regardless of statistical significance, so pre-filtering them before the test avoids this work without any loss of biological DMPs.

The cost is a liberal FDR: BH correction is applied to the pre-filtered subset rather than the full set. In practice, for prostate-cancer-scale data (CG context: ~2000 statistically significant positions out of 4.3 million), the effect is small.

---

## Classifier

MethylDetector trains an **ECDFClassifier** on the selected biological DMPs.

```
log L(class_k | x) = Σ_i  w_i · log F'_k_i(x_i)
P(class_k | x) ∝ exp( log L / T )
```

where:
- `x_i` is the methylation fraction at DMP position `i` for a new sample.
- `F'_k_i(x)` is the PCHIP-derived PDF from the centroid of class `k` at position `i`.
- `w_i = effect_size_i / max(effect_size)` — positions with larger `effect_size` contribute more.
- `T` is the temperature parameter (default `2.0`).

The ECDFClassifier stores the `bin_counts` histograms per DMP position rather than `alpha/beta` parameters, and uses the same PCHIP PDF model as the DMP detection stage.

---

## Summary Table

| Component | Role |
|-----------|------|
| Distribution model | ECDF only (binned_stats, 20 bins default) |
| Statistical test | Welch-style mean-difference t-test |
| Multiple testing | Two-stage Benjamini-Hochberg (statsmodels fdr_tsbh) |
| Pre-filter gate | `delta_mean_reduction` or `min_delta_mean` (before Welch test) |
| Overlap | Continuous ECDF overlap: ∫ min(f1, f2) |
| Biological score | Canonical `effect_size` formula with lambda_var penalty |
| Biological filters | `min_delta_mean`, `max_overlap`, `min_effect_size`, `effect_size_quantile` |
| Classifier | ECDFClassifier: PCHIP PDF log-likelihood, effect_size-weighted |
