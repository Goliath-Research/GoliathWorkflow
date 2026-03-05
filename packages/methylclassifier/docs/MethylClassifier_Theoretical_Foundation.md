# MethylClassifier Theoretical Foundation

## Goal

MethylClassifier assigns DNA methylation samples to biological classes (e.g. healthy vs cancer) using methylation at **differentially methylated positions (DMPs)**. It uses a **Bayesian classification** framework with **ECDF-based likelihoods**: no parametric distribution (Beta, Normal, Beta-Binomial, or Beta-Mixture) is used. Class-wise centroids provide an **empirical distribution (ECDF)** per position via binned_stats (bin_edges, bin_counts); the likelihood is the PDF from that ECDF (spline-interpolated). Parameters come from **MethylDetector** output (centroids with binned_stats).

## Model: Naive Bayes with ECDF Likelihoods

Per DMP position \(i\) and class \(k\), the class centroid has a per-position empirical distribution from **binned_stats** (bin_edges, bin_counts). The PDF is defined by spline interpolation so that \(F(x)\) and \(F'(x)\) exist for any \(x \in [0,1]\).

$$P(x_i \mid \text{Class } k) = \mathrm{PDF}_{\mathrm{ECDF},k,i}(x_i)$$

- **Source**: Centroid for class \(k\) at position \(i\) has binned_stats; the ECDF view gives a continuous PDF via the spline derivative. A small floor is applied to avoid \(\log(0)\).
- **No Beta/Normal/BMM**: Only the empirical distribution (ECDF) is used; no \(\alpha, \beta\) or other parametric form.

**Naive Bayes assumption**: Methylation values at different DMPs are independent given the class, so the likelihood over all positions is the product of per-position likelihoods.

## Posterior and Prediction

By Bayes' theorem:

$$P(\text{Class } k \mid X) \propto P(\text{Class } k) \prod_i P(x_i \mid \text{Class } k)$$

In practice the implementation uses **log-likelihoods** (sum of log PDF values) for numerical stability. Each DMP can be **weighted** (e.g. by effect_size from MethylDetector); the classifier then uses a weighted sum of log-likelihoods. Prediction is the class with highest posterior probability (argmax over \(k\)).

## Optional Extensions

- **Temperature scaling**: A temperature parameter can sharpen or soften the posterior (e.g. softmax over log-likelihoods with temperature \(T\)).
- **Platt calibration**: Optional probability calibration (Platt scaling) can be applied to the raw posteriors for better-calibrated confidence estimates.

## Summary

| Aspect | Role |
|--------|------|
| Training | None in MethylClassifier; centroids and DMPs come from MethylDetector (ECDF-based comparison and training). |
| Likelihood | **ECDF only**: per-position PDF from centroid binned_stats; Naive Bayes product over positions. |
| Weights | Per-DMP weights (e.g. from effect_size) weight the log-likelihood sum. |
| Output | Posterior probabilities per class; prediction = argmax. |

For full derivations, API, and examples, see [METHYLCLASSIFIER_COMPREHENSIVE_DOCUMENTATION.md](METHYLCLASSIFIER_COMPREHENSIVE_DOCUMENTATION.md).
