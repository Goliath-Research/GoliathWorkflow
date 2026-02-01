# MethylCentroid Theoretical Foundation

## Overview

MethylCentroid summarizes per-position methylation across a cohort of samples
using sufficient statistics. This enables robust downstream modeling while
avoiding storage of full sample matrices.

## Centroid Definition

Let $x_i$ be the methylation fraction for sample $i$ at a given position, and
$N$ the number of samples. The centroid mean is:

```
μ = (1/N) × Σ x_i
```

Rather than storing all $x_i$, the centroid stores aggregate statistics that
are sufficient for parameter estimation across common models.

## Sufficient Statistics

Key aggregates include:
- $N$, $S_x = \sum x_i$, $S_{x^2} = \sum x_i^2$
- $\sum \log(x_i)$, $\sum \log(1-x_i)$
- Coverage aggregates $\sum n_i$, $\sum n_i^2$, $\sum mC_i$, $\sum uC_i$
- Higher moments $S_{x^3}$, $S_{x^4}$ and boundary counts $c_0$, $c_1$

These are computed incrementally as samples are added or removed.

## Distributional Modeling

The stored statistics support estimation for:
- **Normal**: mean/variance from $S_x$, $S_{x^2}$
- **Beta**: MLE from log-sums
- **Beta-Binomial**: coverage-aware overdispersion
- **Beta Mixture**: fitted on masked subsets (optionally using binned histograms)

For full derivations and formulas, see:

📄 **`docs/METHYLCENTROID_DISTRIBUTIONS.tex`**
📄 **`docs/METHYLCENTROID_DISTRIBUTIONS.pdf`**

## Practical Implications

- **Memory efficiency**: storage scales with positions, not samples.
- **Incremental updates**: new samples update aggregates without reprocessing.
- **GPU readiness**: vectorized aggregates map well to GPU kernels.

## Summary

MethylCentroid’s theoretical basis is a sufficient-statistics approach that
balances statistical rigor with computational scalability for large genomes.
