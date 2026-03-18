# MethylClassifier Theoretical Foundation

## Goal

MethylClassifier assigns DNA methylation samples to biological classes (e.g. healthy vs cancer) using methylation at **differentially methylated positions (DMPs)**. It uses an **ECDF-based Naive Bayes** framework: no parametric distribution (Beta, Normal, Beta-Binomial, or Beta-Mixture) is used. Class-wise centroids provide an empirical distribution per position via `binned_stats` (`bin_edges`, `bin_counts`); the likelihood is the PCHIP-derived PDF from that ECDF. Parameters come from **MethylDetector** output.

## Model: Naive Bayes with ECDF Likelihoods

Per DMP position \(i\) and class \(k\), the class centroid has a per-position empirical distribution from **binned_stats** (bin_edges, bin_counts). The PDF is defined by spline interpolation so that \(F(x)\) and \(F'(x)\) exist for any \(x \in [0,1]\).

$$P(x_i \mid \text{Class } k) = \mathrm{PDF}_{\mathrm{ECDF},k,i}(x_i)$$

- **Source**: Centroid for class \(k\) at position \(i\) has binned_stats; the ECDF view gives a continuous PDF via the spline derivative. A small floor is applied to avoid \(\log(0)\).
- **No Beta/Normal/BMM**: Only the empirical distribution (ECDF) is used; no \(\alpha, \beta\) or other parametric form.

**Naive Bayes assumption**: Methylation values at different DMPs are independent given the class, so the likelihood over all positions is the product of per-position likelihoods.

## Posterior and Prediction

By Bayes' theorem:

$$P(\text{Class } k \mid X) \propto P(\text{Class } k) \prod_i P(x_i \mid \text{Class } k)$$

In practice the implementation uses **weighted mean log-likelihoods** for numerical stability and to avoid scale blow-up with many DMPs:

$$
\mathrm{meanLogL}_k(X) =
\frac{\sum_i w_i \cdot \mathrm{clamp}(\log P(x_i \mid \mathrm{Class}\ k), \mathrm{cap})}
{\sum_i w_i}
$$

Each DMP can be **weighted** (e.g. by `effect_size` from MethylDetector). Very small per-position log-PDF values are capped so a few near-zero loci do not dominate the average when using large DMP sets.

## Optional Extensions

- **Temperature scaling**: A temperature parameter can sharpen or soften the posterior. The implementation scales it by the effective number of weighted loci, \(T_{\mathrm{eff}} = T \sqrt{n_{\mathrm{effective}}}\), so probabilities stay well-behaved as the number of DMPs grows.
- **Platt calibration**: Optional probability calibration (Platt scaling) can be applied to the raw posteriors for better-calibrated confidence estimates.

## Multi-Chromosome Models

When `model_dir` contains multiple `classifier-*.pkl` files, MethylClassifier loads one classifier per chromosome and combines the resulting probabilities with normalized chromosome weights:

$$
P(\mathrm{Class} \mid X) =
\mathrm{normalize}\left(\sum_{\mathrm{chrom}} w_{\mathrm{chrom}} \cdot P_{\mathrm{chrom}}(\mathrm{Class} \mid X_{\mathrm{chrom}})\right)
$$

Where:

- \(w_{\mathrm{chrom}}\) comes from config, trimmed-mean `effect_size`, or fitted validation weights.
- \(X_{\mathrm{chrom}}\) is the methylation vector aligned to that chromosome classifier's DMP order.

## Summary

| Aspect | Role |
|--------|------|
| Training | None in MethylClassifier; centroids and DMPs come from MethylDetector (ECDF-based comparison and training). |
| Likelihood | **ECDF only**: per-position PDF from centroid `binned_stats`; weighted mean log-likelihood across DMPs. |
| Weights | Per-DMP weights (e.g. `effect_size`) for loci; optional chromosome weights for directory / multi-chromosome models. |
| Output | Posterior probabilities per class; prediction = argmax after temperature-scaled softmax. |

For full derivations, API, and examples, see [METHYLCLASSIFIER_COMPREHENSIVE_DOCUMENTATION.md](METHYLCLASSIFIER_COMPREHENSIVE_DOCUMENTATION.md).
