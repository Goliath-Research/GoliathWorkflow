# MethylDetector Theoretical Foundation

## Goal

MethylDetector identifies **differentially methylated positions (DMPs)** between two methylation centroids (e.g. healthy vs disease) with:

- **FDR control**: Storey's q-value method for multiple-testing correction
- **Biological relevance**: Effect size and distribution overlap to keep meaningful DMPs

Downstream, selected DMPs are used for classifier training and validation (Balanced Accuracy).

## Probabilistic Model

Per genomic position, methylation is bounded in \([0, 1]\). MethylDetector uses **only the empirical distribution (ECDF)** for comparison and overlap. Centroids must have **binned_stats** (in memory: bin_edges, bin_counts), built with `binned_stats_bins` (default 20). In HDF5 only `methylation_data.attrs["bins"]` and `methylation_data["bin_counts"]` are stored; bin edges are derived. MethylUtils **MethylCentroidPair** computes overlap, p-values, and effect size using ECDF only; Normal, Beta, Beta-Binomial, and Beta-Mixture are not supported.

## Statistical Testing

Per-position significance and effect size are computed by MethylUtils **MethylCentroidPair** using **ECDF-based** metrics (e.g. z-test on means with variances, or KS-based tests). P-values and q-values are attached to the comparison table. Implementation: MethylUtils statistical_tests and MethylCentroidPair.

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
- **\(\sigma_{\text{combined}}\)**: \(\sqrt{\text{var}_1 + \text{var}_2}\) from centroid variances (from N, Sx, Sx2 or ECDF)
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
| Distribution | **ECDF only** (binned_stats required; build with binned_stats_bins, default 20) |
| Testing | ECDF-based p-values (MethylCentroidPair) |
| q-value | Storey's method (MethylUtils `storey_qvalues`) |
| effect_size | From MethylCentroidPair (overlap and delta mean; ECDF-based overlap) |
| Overlap | ECDF-based (e.g. 1 − KS or discrete overlap from bin_counts) |
| Validation | Balanced Accuracy |

## References

- Full derivations and extra metrics: [METHYLMODELER_COMPREHENSIVE_DOCUMENTATION.md](METHYLMODELER_COMPREHENSIVE_DOCUMENTATION.md)
- Testing and q-values: MethylUtils `statistical_tests` (ECDF-based tests, `storey_qvalues`)
- Effect size and overlap: MethylUtils `MethylCentroidPair` (compare_centroids output)
