# MethylDetector Theoretical Foundation

## Goal

`MethylDetector` identifies differentially methylated positions (DMPs) between two methylation centroids (e.g. healthy vs disease) with:

- **Statistical rigour**: Histogram-derived Mann-Whitney U testing with FDR correction.
- **Biological relevance**: A single canonical score (`effect_size`) that penalises positions where the distributions overlap heavily or where within-group variance is large.
- **Computational tractability**: A staged funnel that first reduces the aligned locus set with `delta_mean_reduction`, then evaluates non-parametric significance and ECDF overlap only on the surviving candidates before top-k validation from cached ECDF log-likelihoods.

All distribution comparisons use the **ECDF only** — no Beta, Normal, or Beta-Binomial models.

---

## Staged Pipeline

```
Centroid H5 files (must have binned_stats)
    │
    ├─ Stage 1 — Pre-filter (cheap, on aligned loci)
    │     Start from positions present in both centroids after min_coverage.
    │     Compute |delta_mean| = |mean1 - mean2| from centroid means (Sx/N).
    │     Keep only loci with |delta_mean| >= delta_mean_reduction.
    │     Purpose: avoid running the expensive statistical gate on positions that will
    │     be discarded by the biological filter later.
    │
    ├─ Stage 2 — Centroid alignment handoff
    │     Carry the shared genomic coordinates forward as per-centroid indices so
    │     every surviving position refers to the same locus in both centroids.
    │
    ├─ Stage 3 — Statistical significance test
    │     For each aligned position:
    │         U reconstructed from centroid bin_counts with tie correction
    │         z_U = (U - n1*n2/2) / sqrt(var_U)
    │         p_value = 2 * norm.sf(|z_U|)
    │     No parametric mean-difference test is used in the detector pipeline.
    │
    ├─ Stage 4 — FDR correction
    │     Two-stage Benjamini-Hochberg (statsmodels fdr_tsbh) on the
    │     pre-filtered position set.
    │     Note: FDR is applied to the pre-filtered subset only; q-values are
    │     therefore liberal relative to testing all positions.
    │
    ├─ Stage 5 — Statistical filter + heterogeneity filter
    │     Retain positions with q_value <= alpha.
    │     Optionally drop loci where both groups exceed max_tau2_for_dmp.
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
    │     Optional EAT reweighting multiplies final effect_size only.
    │
    ├─ Stage 8 — Biological filter
    │     Within each context, keep the minimum prefix whose cumulative
    │     effect_size reaches effect_size_coverage of the total effect mass.
    │
    ├─ Stage 9 — Optional biological-only rescue
    │     Select non-significant but high-effect loci separately with
    │     biological_only_effect_size_coverage and keep them explicitly flagged.
    │
    └─ Stage 10 — Held-out top-k selection
          Use repeated stratified validation splits, cached ECDF log-likelihoods,
          and balanced accuracy to choose the final top-k prefix.
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

The variances used in `effect_size` are the **sample variances** from `(Sx2 - Sx²/N)/(N-1)`. They are used only in the biological reliability penalty, not in the significance test itself. This keeps the detector non-parametric at the statistical-testing stage while still down-weighting diffuse, heterogeneous loci in `effect_size`.

---

## Why the Pre-filter Is Before the Statistical Test

The histogram-derived Mann-Whitney U stage and the later continuous ECDF overlap stage both become expensive at CHH scale. Positions not present in both centroids cannot be tested at all; among the aligned loci, positions with `|delta_mean| < delta_mean_reduction` will be removed by the biological filter regardless of statistical significance, so pre-filtering them before the statistical gate avoids this work without any loss of biologically strong DMPs.

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
| Statistical test | Histogram-derived Mann-Whitney U from centroid `bin_counts` |
| Multiple testing | Two-stage Benjamini-Hochberg (statsmodels fdr_tsbh) |
| Pre-filter gate | `delta_mean_reduction` (before the statistical test) |
| Overlap | Continuous ECDF overlap: ∫ min(f1, f2) |
| Biological score | Canonical `effect_size` formula with lambda_var penalty |
| Biological filter | Per-context `effect_size_coverage` cumulative mass selection |
| Rescue track | Optional `biological_only_effect_size_coverage` on non-significant loci |
| Validation | Repeated stratified holdout BA with cached ECDF log-likelihood prefixes |
| Classifier | ECDFClassifier: PCHIP PDF log-likelihood, effect_size-weighted |
