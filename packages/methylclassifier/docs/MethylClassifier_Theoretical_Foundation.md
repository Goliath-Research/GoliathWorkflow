# MethylClassifier Theoretical Foundation

## Goal

MethylClassifier assigns DNA methylation samples to biological classes (e.g. healthy vs cancer) using methylation at **differentially methylated positions (DMPs)**. It uses a **Bayesian classification** framework: no training is performed in MethylClassifier; it loads pre-computed class-wise Beta (and optionally Beta Mixture) parameters from **MethylDetector** output and computes posterior class probabilities.

## Model: Naive Bayes with Beta Likelihoods

Per DMP position \(i\) and class \(k\), methylation is modeled as:

$$P(x_i \mid \text{Class } k) = \mathrm{BetaPDF}(x_i; \alpha_{k,i}, \beta_{k,i})$$

- **Parameters**: \(\alpha_{k,i}, \beta_{k,i}\) come from centroids (MethylCentroid) and DMP selection (MethylDetector). Mean methylation at position \(i\) for class \(k\) is \(\alpha_{k,i} / (\alpha_{k,i} + \beta_{k,i})\).
- **Beta PDF**: \(\mathrm{BetaPDF}(x; \alpha, \beta) = x^{\alpha-1}(1-x)^{\beta-1} / B(\alpha, \beta)\), with \(B(\alpha,\beta)\) the Beta function.

**Naive Bayes assumption**: Methylation values at different DMPs are independent given the class, so the likelihood over all positions is the product of per-position likelihoods.

## Posterior and Prediction

By Bayes' theorem:

$$P(\text{Class } k \mid X) \propto P(\text{Class } k) \prod_i P(x_i \mid \text{Class } k)$$

In practice the implementation uses **log-likelihoods** (sum of log Beta PDFs) for numerical stability. Optionally, each DMP can be **weighted** (e.g. by effect_size from MethylDetector); the classifier then uses a weighted sum of log-likelihoods. Prediction is the class with highest posterior probability (argmax over \(k\)).

## Optional Extensions

- **Beta Mixture (BMM)**: When MethylDetector was run with BMM refinement, some DMPs have Beta Mixture likelihoods; MethylClassifier uses those where available and falls back to Beta otherwise. The Bayesian formulation (posterior from likelihood × prior) is unchanged.
- **Temperature scaling**: A temperature parameter can sharpen or soften the posterior (e.g. softmax over log-likelihoods with temperature \(T\)).
- **Platt calibration**: Optional probability calibration (Platt scaling) can be applied to the raw posteriors for better-calibrated confidence estimates.

## Summary

| Aspect | Role |
|--------|------|
| Training | None in MethylClassifier; parameters come from MethylDetector (which uses MethylUtils BetaClassifier/BetaBinomialClassifier for training). |
| Likelihood | Beta (and optionally BMM) per DMP; Naive Bayes product over positions. |
| Weights | Per-DMP weights (e.g. from effect_size) weight the log-likelihood sum. |
| Output | Posterior probabilities per class; prediction = argmax. |

For full derivations, API, and examples, see [METHYLCLASSIFIER_COMPREHENSIVE_DOCUMENTATION.md](METHYLCLASSIFIER_COMPREHENSIVE_DOCUMENTATION.md).
