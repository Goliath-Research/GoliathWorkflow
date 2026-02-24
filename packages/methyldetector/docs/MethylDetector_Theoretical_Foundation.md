# MethylDetector Theoretical Foundation

## Goal

MethylDetector identifies **differentially methylated positions (DMPs)** between two methylation centroids (e.g. healthy vs disease) with:

- **FDR control**: Storey's q-value method for multiple-testing correction
- **Biological relevance**: Effect size and distribution overlap to keep meaningful DMPs

Downstream, selected DMPs are used for classifier training and validation (Balanced Accuracy).

## Probabilistic Model

Per genomic position, methylation is modeled as bounded in \([0, 1]\), so the natural choice is the **Beta distribution**:

- \(x \sim \text{Beta}(\alpha, \beta)\)
- Mean: \(\mu = \alpha / (\alpha + \beta)\)
- Variance: \(\sigma^2 = \frac{\alpha\beta}{(\alpha+\beta)^2(\alpha+\beta+1)}\)

Centroid sufficient statistics (from MethylCentroid) provide MLEs for \(\alpha, \beta\) per position and per group. MethylDetector (via MethylUtils **MethylCentroidPair**) can use:

- **Beta**: default for mean/overlap and LRT
- **Normal**: approximation when appropriate (delta_mean_mode / overlap_mode)
- **Beta-Binomial**: coverage-aware; optional

Distribution selection is configured by `delta_mean_mode`, `overlap_mode`, and `distribution` in the detector config and is implemented in MethylCentroidPair.

## Likelihood Ratio Test (LRT)

For each position, test:

- \(H_0\): same Beta in both groups — \(\text{Beta}(\alpha_1, \beta_1) = \text{Beta}(\alpha_2, \beta_2)\)
- \(H_1\): different Betas

**Test statistic:**

$$\Lambda = -2 \log \frac{\mathcal{L}(H_0)}{\mathcal{L}(H_1)}$$

- \(\mathcal{L}(H_0)\): likelihood under null (pooled parameters)
- \(\mathcal{L}(H_1)\): likelihood under alternative (separate \(\alpha_1,\beta_1\) and \(\alpha_2,\beta_2\))

Under \(H_0\), \(\Lambda \sim \chi^2_2\) (2 degrees of freedom). **P-value:**

$$p = P(\chi^2_2 \geq \Lambda) = 1 - F_{\chi^2_2}(\Lambda)$$

Implementation: MethylUtils `likelihood_ratio_test_beta`; MethylCentroidPair calls it and returns p-values in the comparison table.

## FDR Correction: Storey's q-value

Given \(m\) positions with p-values \(p_1, \ldots, p_m\):

1. **Estimate \(\pi_0\)** (proportion of true nulls), e.g. at a tuning parameter \(\lambda\):
   $$\hat{\pi}_0(\lambda) = \frac{\#\{p_i > \lambda\}}{m(1-\lambda)}$$

2. **Compute q-values** from sorted p-values so that q-value controls the false discovery rate.

Implementation: MethylUtils `storey_qvalues`. MethylCentroidPair (or the detector pipeline) uses it to attach q-values to each position. Positions with \(q \leq \alpha\) are statistically significant DMPs.

## Effect Size (Single Biological Importance Measure)

**effect_size** is the only biological importance measure in the pipeline. It is computed by **MethylCentroidPair**; MethylDetector uses it as provided.

**Formula:**

$$\text{effect\_size} = \frac{|\Delta\mu|}{\max(\text{overlap}, \epsilon) \times \sigma_{\text{combined}}} \times \text{variance\_reliability}$$

- **\(\Delta\mu\)**: \(|\mu_1 - \mu_2|\) (delta mean)
- **overlap**: Bhattacharyya coefficient \(\text{BC} = e^{-\text{BD}}\) (BD = Bhattacharyya distance)
- **\(\epsilon\)**: min_overlap_floor (e.g. 0.01) to avoid division by zero
- **\(\sigma_{\text{combined}}\)**: \(\sqrt{\text{var}_1 + \text{var}_2}\) from Beta variances
- **variance_reliability**: \(1 / (1 + \max(\text{var}_1, \text{var}_2) / 0.05)\) to down-weight noisy (high-variance) positions

Larger \(|\Delta\mu|\) and smaller overlap increase effect_size; higher variance decreases it. Downstream (e.g. MethylClassifier) use effect_size for weighting and ranking.

## Overlap: Bhattacharyya Coefficient and Distance

- **Bhattacharyya coefficient (BC)**: in \([0, 1]\); 1 = identical distributions, 0 = no overlap. Used as “overlap” in filters and in effect_size.
- **Bhattacharyya distance (BD)**: \(-\ln(\text{BC})\); stored in comparison output; \(\text{BC} = e^{-\text{BD}}\).

Optional: **Jeffreys divergence** (symmetric KL) is available in MethylUtils for additional metrics; the primary overlap used for biological filtering is BC.

## Balanced Accuracy

For validation and DMP selection under class imbalance:

$$\text{Balanced Accuracy} = \frac{\text{Sensitivity} + \text{Specificity}}{2}$$

with Sensitivity = TP/(TP+FN), Specificity = TN/(TN+FP). This treats both classes equally and is used as a target (e.g. target_balanced_accuracy) when selecting how many DMPs to keep.

## Summary Table

| Component | Role |
|-----------|------|
| Distribution | Beta (default); Normal / Beta-Binomial via MethylCentroidPair modes |
| LRT | \(H_0\): same Beta vs \(H_1\): different; \(\Lambda \sim \chi^2_2\) |
| q-value | Storey's method (MethylUtils `storey_qvalues`) |
| effect_size | \|Δμ\| / (max(overlap, ε) × σ_combined) × variance_reliability (MethylCentroidPair) |
| Overlap | Bhattacharyya coefficient BC = exp(-BD) |
| Validation | Balanced Accuracy |

## References

- Full derivations and extra metrics: [METHYLMODELER_COMPREHENSIVE_DOCUMENTATION.md](METHYLMODELER_COMPREHENSIVE_DOCUMENTATION.md)
- LRT and q-values: MethylUtils `statistical_tests` (`likelihood_ratio_test_beta`, `storey_qvalues`)
- Effect size and overlap: MethylUtils `MethylCentroidPair` (compare_centroids output)
