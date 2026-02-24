# MethylUtils: Comprehensive Documentation

**Related documentation:** [MethylUtils Theoretical Foundation](MethylUtils_Theoretical_Foundation.md), [Implementation](METHYLUTILS_IMPLEMENTATION.md), [Usage (Docker and venv)](USAGE.md).

## Table of Contents

1. [Overview](#overview)
2. [Mathematical Foundations](#mathematical-foundations)
3. [Distance and Effect-Size Metrics](#distance-and-effect-size-metrics)
4. [Data Structures and API](#data-structures-and-api)
5. [GPU and Performance](#gpu-and-performance)
6. [References](#references)

---

## Overview

MethylUtils is the foundational core library of MethylPipeline. It provides:

- **Core types**: `MethylSample`, `MethylCentroidPair`, `PositionAligner`, `MethylFrame`
- **GPU/CPU utilities**: Automatic GPU detection, memory management, backend-agnostic array handling
- **Statistical building blocks**: Beta distribution modeling, method-of-moments, seven distance/effect-size metrics
- **I/O**: HDF5 with Z-standard compression, memory-mapped and chunked processing

All higher-level packages (MethylCentroid, MethylCluster, MethylDetector, MethylClassifier, etc.) depend on MethylUtils for data structures, metrics, and GPU acceleration.

---

## Mathematical Foundations

### Beta Distribution for Methylation

Methylation level at a position is a fraction in $[0,1]$. The Beta distribution is the natural model:

$$
f(x \mid \alpha, \beta) = \frac{x^{\alpha-1}(1-x)^{\beta-1}}{B(\alpha,\beta)}, \quad x \in (0,1),\ \alpha,\beta > 0
$$

where $B(\alpha,\beta) = \frac{\Gamma(\alpha)\Gamma(\beta)}{\Gamma(\alpha+\beta)}$ is the Beta function.

**Mean and variance:**

$$
\mu = \mathbb{E}[x] = \frac{\alpha}{\alpha + \beta}, \qquad
\sigma^2 = \mathrm{Var}(x) = \frac{\alpha\beta}{(\alpha+\beta)^2(\alpha+\beta+1)}
$$

**Log-PDF** (used for likelihood and log-likelihood ratios):

$$
\log f(x \mid \alpha, \beta) = (\alpha-1)\log x + (\beta-1)\log(1-x) - \ln B(\alpha,\beta)
$$

### Method-of-Moments from Coverage and Methylation Fraction

Given per-position methylation fraction $m = k/n$ (methylated counts $k$, coverage $n$), MethylUtils derives Beta parameters via a simple method-of-moments style mapping:

- Effective size: $n_{\mathrm{eff}} = n - 1$
- $\alpha = m \cdot (n-1)$ (clamped to a minimum $> 0$)
- $\beta = (1-m) \cdot (n-1)$ (clamped to a minimum $> 0$)

Invalid or low-coverage positions fall back to a uniform Beta$(1,1)$. This yields a Beta with mean close to $m$ and variance that decreases with coverage, suitable for distance and likelihood computations.

---

## Distance and Effect-Size Metrics

All metrics below are implemented for **Beta distributions** parameterized by $(\alpha_1,\beta_1)$ and $(\alpha_2,\beta_2)$, with optional GPU acceleration via CuPy.

### KL Divergence (Beta)

For Beta distributions, the KL divergence has a closed form using the digamma function $\psi(z) = \frac{d}{dz}\ln\Gamma(z)$:

$$
D_{\mathrm{KL}}(P_1 \| P_2) = \ln\frac{B(\alpha_2,\beta_2)}{B(\alpha_1,\beta_1)} + (\alpha_1-\alpha_2)\psi(\alpha_1) + (\beta_1-\beta_2)\psi(\beta_1) - (\alpha_1+\beta_1-\alpha_2-\beta_2)\psi(\alpha_1+\beta_1)
$$

### Jeffreys Divergence

Symmetric KL divergence:

$$
J(P_1, P_2) = D_{\mathrm{KL}}(P_1 \| P_2) + D_{\mathrm{KL}}(P_2 \| P_1)
$$

### Bhattacharyya Coefficient (Overlap)

$$
BC(P_1, P_2) = \int \sqrt{p_1(x)\,p_2(x)}\,\mathrm{d}x
$$

For Beta distributions, in log-space (using $\ln B$):

$$
\ln BC = \ln B\left(\frac{\alpha_1+\alpha_2}{2}, \frac{\beta_1+\beta_2}{2}\right) - \frac{1}{2}\bigl[\ln B(\alpha_1,\beta_1) + \ln B(\alpha_2,\beta_2)\bigr]
$$

So $BC = \exp(\ln BC)$. Range: $BC \in (0, 1]$; $BC = 1$ for identical distributions.

### Bhattacharyya Distance

$$
BD = -\ln(BC)
$$

So $BD \in [0, +\infty)$; $BD = 0$ when $P_1 = P_2$.

### Hellinger Distance (Normalized)

$$
H(P_1, P_2) = \sqrt{1 - BC}
$$

MethylUtils uses this normalized form so that $H \in [0, 1]$, comparable to Jensen–Shannon distance.

### Jensen–Shannon Distance

Midpoint distribution $M$ with parameters $\alpha_m = (\alpha_1+\alpha_2)/2$, $\beta_m = (\beta_1+\beta_2)/2$. Jensen–Shannon divergence:

$$
\mathrm{JSD}(P_1, P_2) = \frac{1}{2} D_{\mathrm{KL}}(P_1 \| M) + \frac{1}{2} D_{\mathrm{KL}}(P_2 \| M)
$$

The **Jensen–Shannon distance** (metric) is:

$$
d_{\mathrm{JS}} = \sqrt{\frac{\mathrm{JSD}}{\ln 2}}
$$

so that $d_{\mathrm{JS}} \in [0, 1]$.

### Wasserstein Distance (Moment Approximation)

For computational efficiency, MethylUtils uses a moment-based approximation for Beta distributions:

$$
\mu_i = \frac{\alpha_i}{\alpha_i+\beta_i}, \qquad
\sigma_i^2 = \frac{\alpha_i\beta_i}{(\alpha_i+\beta_i)^2(\alpha_i+\beta_i+1)}, \quad i=1,2
$$

$$
d_{\mathrm{W}} \approx |\mu_1 - \mu_2| + \bigl|\sqrt{\sigma_1^2} - \sqrt{\sigma_2^2}\bigr|
$$

This is exact for normals and a stable approximation for Beta.

### Effect Size (MethylCentroidPair)

Used for biological importance and DMP ranking. With $\Delta\mu = |\mu_1 - \mu_2|$, Bhattacharyya coefficient $BC$, and combined variance $\sigma_{\mathrm{combined}}^2 = \sigma_1^2 + \sigma_2^2$ (using Beta variance above), and variance under MethylSample’s convention $\mathrm{var}_i = \mu_i(1-\mu_i)/(\alpha_i+\beta_i+1)$:

$$
\text{effect\_size} = \frac{|\Delta\mu|}{\sqrt{\sigma_1^2 + \sigma_2^2}} \cdot (1 - BC)^\gamma
$$

with $\gamma = 1$ by default. A small floor is applied to avoid zero effect sizes. This combines mean separation, overlap (low $BC$ increases effect size), and scale (variance).

---

## Data Structures and API

- **MethylSample**: Per-position methylation data (counts or fractions), HDF5 serialization, position-indexed access.
- **MethylCentroidPair**: Wraps two MethylSamples; computes distances, effect sizes, and metrics (e.g. Jeffreys, Bhattacharyya, Hellinger, JSD, Wasserstein) over positions.
- **MethylFrame**: DataFrame-oriented methylation data; supports GPU (cuDF) and chunked processing.
- **PositionAligner**: Aligns positions across samples/centroids for joint comparison.

The **metrics factory** (`get_metric_factory()`, `create_metric_computer(...)`) provides a unified interface to all distance metrics with optional GPU.

---

## GPU and Performance

- **Backend**: CuPy when available; otherwise NumPy/SciPy. All metric functions accept `use_gpu=True` (default) and fall back to CPU if GPU is unavailable.
- **Arrays**: Inputs are converted to the active backend (CPU/GPU); outputs are returned as CPU arrays unless otherwise documented.
- **Memory**: Float32 is used where appropriate; chunked processing and memory-mapped I/O are used in pipeline packages that build on MethylUtils.

---

## References

- Package README: [MethylUtils README](../README.md)
- Metric implementations: `methyl_utils/metrics_core.py`, `methyl_utils/beta_analytics.py`
- Effect size and centroid comparison: `methyl_utils/methyl_centroid_pair.py`
- MethylPipeline Theory and packages: [docs/THEORY_AND_PACKAGES.md](../../../docs/THEORY_AND_PACKAGES.md)
