# MethylCentroid Theoretical Foundation

## Overview

MethylCentroid summarizes per-position methylation across a cohort of samples using **sufficient statistics**. This enables robust downstream modeling (Normal, Beta, Beta-Binomial, Beta Mixture) while avoiding storage of full sample matrices and supporting streaming updates and GPU-friendly aggregation.

## Notation

For a genomic position, let the sample index be \(i = 1, \ldots, N\). Let \(mC_i\) and \(uC_i\) be methylated and unmethylated counts. Define:

- **Coverage**: \(n_i = mC_i + uC_i\)
- **Methylation fraction**: \(x_i = mC_i / n_i \in [0, 1]\)

The centroid stores aggregated statistics across all contributing samples at each position.

## Centroid Definition

The centroid mean at position \(i\) is:

$$\mu_i = \frac{1}{N} \sum_{j=1}^{N} x_{ij}$$

Rather than storing all \(x_{ij}\), the centroid stores **sufficient statistics** that allow parameter estimation for multiple probabilistic models without retaining the full sample matrix.

## Sufficient Statistics Stored

### Always present (extended centroid)

| Symbol | Name in code | Definition |
|--------|----------------|------------|
| \(N\) | `N` | \(\sum_i 1\) (number of samples) |
| \(S_x\) | `Sx` | \(\sum_i x_i\) |
| \(S_{x^2}\) | `Sx2` | \(\sum_i x_i^2\) |
| \(\sum \log x\) | `log_x_sum` | \(\sum_i \log(x_i)\) |
| \(\sum \log(1-x)\) | `log_1_minus_x_sum` | \(\sum_i \log(1 - x_i)\) |

### Optional (when `store_extended_stats=True`, Beta-Binomial / higher moments)

| Symbol | Name in code | Definition |
|--------|----------------|------------|
| \(\Sigma n\) | `sum_cov` | \(\sum_i n_i\) |
| \(\Sigma n^2\) | `sum_cov2` | \(\sum_i n_i^2\) |
| \(\Sigma mC\) | `sum_mC` | \(\sum_i mC_i\) |
| \(\Sigma uC\) | `sum_uC` | \(\sum_i uC_i\) |
| \(\Sigma mC^2\) | `sum_mC2` | \(\sum_i mC_i^2\) |
| \(\Sigma uC^2\) | `sum_uC2` | \(\sum_i uC_i^2\) |
| \(S_{x^3}\) | `Sx3` | \(\sum_i x_i^3\) |
| \(S_{x^4}\) | `Sx4` | \(\sum_i x_i^4\) |
| \(c_0\) | `count_zero` | \(\sum_i \mathbb{1}[x_i = 0]\) |
| \(c_1\) | `count_one` | \(\sum_i \mathbb{1}[x_i = 1]\) |

These are computed incrementally as samples are added (or removed when using in-memory centroid updates).

---

## Probabilistic Distributions

The stored statistics support parameter estimation for the following distributions. Downstream comparison (e.g. **MethylCentroidPair**) can use these for p-values, means, and overlap.

### 1. Normal distribution (approximation)

For large-sample regimes, methylation fractions can be approximated as \(x_i \sim \mathcal{N}(\mu, \sigma^2)\). The centroid provides:

$$\hat{\mu} = \frac{S_x}{N}, \qquad \hat{\sigma}^2 = \frac{S_{x^2} - S_x^2/N}{\max(N-1, 1)}$$

**Required statistics**: \(N\), \(S_x\), \(S_{x^2}\).

### 2. Beta distribution

Methylation fractions are bounded in \([0,1]\), so the Beta distribution is a natural model:

$$x_i \sim \mathrm{Beta}(\alpha, \beta)$$

The log-likelihood depends on \(\sum_i \log x_i\) and \(\sum_i \log(1-x_i)\). Thus \((N, \log X, \log(1-X))\) are **sufficient for MLE** of \(\alpha, \beta\). The implementation uses a bounded MLE routine (see MethylUtils `beta_mle_estimation`). Derived moments:

$$\mathbb{E}[x] = \frac{\alpha}{\alpha+\beta}, \qquad \mathrm{Var}(x) = \frac{\alpha\beta}{(\alpha+\beta)^2(\alpha+\beta+1)}$$

**Required statistics**: \(N\), `log_x_sum`, `log_1_minus_x_sum`.

### 3. Beta-Binomial distribution

Counts are modeled with overdispersion:

$$mC_i \mid p_i \sim \mathrm{Binomial}(n_i, p_i), \qquad p_i \sim \mathrm{Beta}(\alpha, \beta)$$

The centroid stores aggregated count statistics (\(\Sigma mC\), \(\Sigma uC\), \(\Sigma n\), \(\Sigma n^2\), etc.) to support coverage-aware modeling and LRT-style tests. Pooled \((\alpha, \beta)\) can be obtained from the log-sum statistics.

**Required statistics**: Same as Beta, plus `sum_cov`, `sum_mC`, `sum_uC`, etc. (present on **MethylBetaBinomialCentroid**).

### 4. Beta mixture model (BMM)

A flexible multi-modal model:

$$x_i \sim \sum_{k=1}^K w_k \, \mathrm{Beta}(\alpha_k, \beta_k)$$

Fitting mixtures typically requires sample-level values or a histogram. **Binned statistics** (per-position histograms) are optional and stored only when explicitly enabled; otherwise refinement can use masked subsets or sample-based values.

---

## Why Sufficient Statistics?

- **Memory**: Storage scales with number of positions, not positions × samples.
- **Streaming**: New samples update aggregates without reloading previous samples.
- **GPU**: Vectorized accumulation maps well to GPU kernels (MethylCentroidBuilder).
- **Model flexibility**: Normal, Beta, Beta-Binomial, and mixture views can be derived from the same centroid.

## Summary table

| Distribution    | Parameters        | Required statistics |
|----------------|-------------------|----------------------|
| Normal         | \(\mu, \sigma^2\) | \(N, S_x, S_{x^2}\) |
| Beta           | \(\alpha, \beta\) | \(N\), log_x_sum, log_1_minus_x_sum |
| Beta-Binomial  | \(\alpha, \beta\), coverage | Beta stats + \(\Sigma n\), \(\Sigma mC\), \(\Sigma uC\), etc. |
| Beta Mixture   | \(\{w_k, \alpha_k, \beta_k\}\) | Optional binned histograms or samples |

## References

- **Formulas and LaTeX**: `docs/METHYLCENTROID_DISTRIBUTIONS.tex`
- **Implementation**: MethylUtils `MethylCentroidBuilder`, `MethylExtendedCentroid`, `MethylBetaBinomialCentroid`; comparison via `MethylCentroidPair` with distribution selection (`auto`, `beta`, `normal`, `beta_binomial`, `beta_mixture`).
