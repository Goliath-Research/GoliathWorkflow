"""
Beta Distribution Analytics for Methylation Analysis.

This module provides GPU-accelerated analytical functions for Beta distribution
operations used in DMP ranking, selection, and classification. It implements
the analytical approach from the improved algorithm that avoids simulations
and provides exact calculations using digamma/trigamma functions.

Key features:
- Analytical LLR (log-likelihood ratio) moment computation
- Precision-weighted ranking scores
- Bhattacharyya coefficient calculation
- Stable Beta log-PDF computation
- Full GPU acceleration via CuPy when available
"""

import numpy as np
from typing import Tuple, Union, Optional
from scipy.special import betaln, digamma, polygamma

# Import GPU utilities
try:
    from .gpu_detection import is_gpu_available
    from .gpu_utils import _prepare_arrays_for_backend, _ensure_cpu_output
    from .metrics_core import DistanceCalculator
except ImportError:
    from gpu_detection import is_gpu_available
    from gpu_utils import _prepare_arrays_for_backend, _ensure_cpu_output
    from metrics_core import DistanceCalculator

# Constants
DEFAULT_EPS = 1e-12
MIN_BETA_PARAM = 1e-6


def compute_per_site_llr_stats(
    aC: np.ndarray,
    bC: np.ndarray,
    aH: np.ndarray,
    bH: np.ndarray,
    use_gpu: bool = True
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute analytical moments of per-site log-likelihood ratio under Beta distributions.
    
    For each CpG position, computes the mean and variance of the LLR statistic:
        LLR(x) = log[Beta(x|aC,bC)] - log[Beta(x|aH,bH)]
    
    under both the Cancer and Healthy distributions. This uses exact analytical
    formulas involving digamma and trigamma functions.
    
    Args:
        aC, bC: Beta parameters for Cancer distribution (arrays)
        aH, bH: Beta parameters for Healthy distribution (arrays)
        use_gpu: Whether to use GPU acceleration if available
    
    Returns:
        Tuple of (muC, varC, muH, varH, const):
            - muC: Expected LLR under Cancer distribution
            - varC: Variance of LLR under Cancer distribution
            - muH: Expected LLR under Healthy distribution
            - varH: Variance of LLR under Healthy distribution
            - const: Constant term (betaln difference)
    
    Reference:
        copilot.py lines 58-83
    """
    calc = DistanceCalculator()
    xp, xdigamma, xpolygamma, xbetaln = calc.get_backend(use_gpu)
    
    # Prepare arrays for backend
    (aC, bC, aH, bH), _ = _prepare_arrays_for_backend([aC, bC, aH, bH], calc, use_gpu)
    
    # Coefficient differences
    c1 = aC - aH  # Difference in alpha parameters
    c2 = bC - bH  # Difference in beta parameters
    
    # Constant term: -[betaln(aC,bC) - betaln(aH,bH)]
    const = -(xbetaln(aC, bC) - xbetaln(aH, bH))
    
    # Helper function for trigamma
    def trigamma(x):
        return xpolygamma(1, x)
    
    # === Compute moments under Cancer distribution ===
    # E[log X] and E[log(1-X)] under Beta(aC, bC)
    sum_ab_C = aC + bC
    e_logX_C = xdigamma(aC) - xdigamma(sum_ab_C)
    e_log1mX_C = xdigamma(bC) - xdigamma(sum_ab_C)
    
    # Var[log X], Var[log(1-X)], Cov[log X, log(1-X)] under Beta(aC, bC)
    var_logX_C = trigamma(aC) - trigamma(sum_ab_C)
    var_log1mX_C = trigamma(bC) - trigamma(sum_ab_C)
    cov_logX_log1mX_C = -trigamma(sum_ab_C)
    
    # Mean and variance of LLR under Cancer
    muC = c1 * e_logX_C + c2 * e_log1mX_C + const
    varC = c1 * c1 * var_logX_C + c2 * c2 * var_log1mX_C + 2 * c1 * c2 * cov_logX_log1mX_C
    varC = xp.maximum(varC, DEFAULT_EPS)  # Ensure positive variance
    
    # === Compute moments under Healthy distribution ===
    # E[log X] and E[log(1-X)] under Beta(aH, bH)
    sum_ab_H = aH + bH
    e_logX_H = xdigamma(aH) - xdigamma(sum_ab_H)
    e_log1mX_H = xdigamma(bH) - xdigamma(sum_ab_H)
    
    # Var[log X], Var[log(1-X)], Cov[log X, log(1-X)] under Beta(aH, bH)
    var_logX_H = trigamma(aH) - trigamma(sum_ab_H)
    var_log1mX_H = trigamma(bH) - trigamma(sum_ab_H)
    cov_logX_log1mX_H = -trigamma(sum_ab_H)
    
    # Mean and variance of LLR under Healthy
    muH = c1 * e_logX_H + c2 * e_log1mX_H + const
    varH = c1 * c1 * var_logX_H + c2 * c2 * var_log1mX_H + 2 * c1 * c2 * cov_logX_log1mX_H
    varH = xp.maximum(varH, DEFAULT_EPS)  # Ensure positive variance
    
    # Ensure output is CPU array
    return _ensure_cpu_output((muC, varC, muH, varH, const), calc, use_gpu)


def compute_precision_weighted_score(
    dmu: Union[np.ndarray, float],
    BC: Union[np.ndarray, float],
    varC_prop: Union[np.ndarray, float],
    varH_prop: Union[np.ndarray, float],
    gamma: float = 1.0,
    pool: str = "sum",
    eps: float = DEFAULT_EPS
) -> Union[np.ndarray, float]:
    """
    Compute precision-weighted ranking score for DMPs.
    
    Formula:
        score = (|Δμ| / √pooled_var) × (1 - BC)^γ
    
    This score balances:
    - Effect size (|Δμ|)
    - Precision (1/√variance)
    - Distribution separation (1 - BC, where BC is overlap)
    
    Args:
        dmu: Absolute difference in means |muC - muH|
        BC: Bhattacharyya coefficient (overlap measure, 0-1)
        varC_prop: Beta variance under Cancer distribution
        varH_prop: Beta variance under Healthy distribution
        gamma: Exponent for (1-BC) term (default 1.0)
        pool: Variance pooling method: "sum" | "max" | "harmonic"
        eps: Small constant for numerical stability
    
    Returns:
        Precision-weighted score (higher is better)
    
    Reference:
        copilot.py lines 104-121
    """
    # Convert inputs to arrays if needed
    dmu = np.asarray(dmu)
    BC = np.asarray(BC)
    varC_prop = np.asarray(varC_prop)
    varH_prop = np.asarray(varH_prop)
    
    # Compute pooled variance based on method
    if pool == "sum":
        pooled = varC_prop + varH_prop
    elif pool == "max":
        pooled = np.maximum(varC_prop, varH_prop)
    elif pool == "harmonic":
        # Harmonic mean: 2 / (1/varC + 1/varH)
        pooled = 2.0 / (1.0 / (varC_prop + eps) + 1.0 / (varH_prop + eps))
    else:
        # Default to sum
        pooled = varC_prop + varH_prop
    
    # Compute score: (|Δμ| / √pooled_var) × (1 - BC)^γ
    precision_term = np.abs(dmu) / np.sqrt(pooled + eps)
    separation_term = (1.0 - BC) ** gamma
    score = precision_term * separation_term
    
    return score


def compute_bhattacharyya_coefficient(
    a1: np.ndarray,
    b1: np.ndarray,
    a2: np.ndarray,
    b2: np.ndarray,
    use_gpu: bool = True
) -> np.ndarray:
    """
    Compute Bhattacharyya coefficient between two Beta distributions.
    
    The Bhattacharyya coefficient is a measure of overlap between distributions,
    ranging from 0 (no overlap) to 1 (identical distributions).
    
    Formula:
        BC = exp(betaln((a1+a2)/2, (b1+b2)/2) - 0.5*[betaln(a1,b1) + betaln(a2,b2)])
    
    This is equivalent to:
        BC = ∫ √[Beta(x|a1,b1) × Beta(x|a2,b2)] dx
    
    Args:
        a1, b1: Parameters of first Beta distribution
        a2, b2: Parameters of second Beta distribution
        use_gpu: Whether to use GPU acceleration if available
    
    Returns:
        Bhattacharyya coefficient (0-1, where 1 = identical distributions)
    
    Note:
        This is different from Bhattacharyya Distance (BD = -ln(BC)).
        MethylUtils typically stores BD, so BC = exp(-BD).
    
    Reference:
        copilot.py lines 46-49
    """
    calc = DistanceCalculator()
    xp, _, _, xbetaln = calc.get_backend(use_gpu)
    
    # Prepare arrays for backend
    (a1, b1, a2, b2), _ = _prepare_arrays_for_backend([a1, b1, a2, b2], calc, use_gpu)
    
    # Compute Bhattacharyya coefficient
    # BC = B((a1+a2)/2, (b1+b2)/2) / √[B(a1,b1) × B(a2,b2)]
    # In log space: ln(BC) = betaln(avg) - 0.5*[betaln(1) + betaln(2)]
    ln_numerator = xbetaln(0.5 * (a1 + a2), 0.5 * (b1 + b2))
    ln_denominator = 0.5 * (xbetaln(a1, b1) + xbetaln(a2, b2))
    ln_BC = ln_numerator - ln_denominator
    
    BC = xp.exp(ln_BC)
    
    # Ensure output is CPU array
    return _ensure_cpu_output(BC, calc, use_gpu)


def beta_log_pdf(
    x: np.ndarray,
    a: np.ndarray,
    b: np.ndarray,
    use_gpu: bool = True,
    eps: float = 1e-12
) -> np.ndarray:
    """
    Compute log probability density of Beta distribution in a numerically stable way.
    
    Formula:
        log p(x|a,b) = (a-1)×log(x) + (b-1)×log(1-x) - betaln(a,b)
    
    Args:
        x: Values to evaluate (must be in (0,1))
        a, b: Beta distribution parameters (must be > 0)
        use_gpu: Whether to use GPU acceleration if available
        eps: Small constant for clipping x away from boundaries
    
    Returns:
        Log probability density values
    
    Note:
        Values are clipped to [eps, 1-eps] to avoid log(0) issues.
    
    Reference:
        copilot.py lines 40-44
    """
    calc = DistanceCalculator()
    xp, _, _, xbetaln = calc.get_backend(use_gpu)
    
    # Prepare arrays for backend
    (x, a, b), _ = _prepare_arrays_for_backend([x, a, b], calc, use_gpu)
    
    # Clip x to avoid log(0) or log(negative)
    x_clipped = xp.clip(x, eps, 1.0 - eps)
    
    # Compute log PDF
    log_pdf = (a - 1) * xp.log(x_clipped) + (b - 1) * xp.log(1 - x_clipped) - xbetaln(a, b)
    
    # Ensure output is CPU array
    return _ensure_cpu_output(log_pdf, calc, use_gpu)


def compute_beta_mean(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Compute mean of Beta distribution: μ = a/(a+b)"""
    return a / (a + b)


def compute_beta_variance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """
    Compute variance of Beta distribution (proportion variance).
    
    Formula:
        Var[X] = ab / [(a+b)² × (a+b+1)]
    """
    sum_ab = a + b
    return (a * b) / ((sum_ab ** 2) * (sum_ab + 1))


def log_beta_binomial_pmf(
    k: np.ndarray,
    n: np.ndarray,
    a: np.ndarray,
    b: np.ndarray,
    use_gpu: bool = True,
) -> np.ndarray:
    """
    Compute log PMF of the Beta-Binomial distribution in a GPU-aware way.

    log P(K=k | n, a, b) = log C(n, k) + betaln(k+a, n-k+b) - betaln(a, b)

    Identity for log-combinations without gammaln:
      log C(n, k) = -betaln(k+1, n-k+1) + log(n+1)

    Args:
        k: successes (ints)
        n: trials (ints)
        a, b: Beta prior parameters
        use_gpu: Whether to use GPU acceleration if available

    Returns:
        Array of log PMF values
    """
    calc = DistanceCalculator()
    xp, _, _, xbetaln = calc.get_backend(use_gpu)

    # Prepare arrays for backend
    (k, n, a, b), _ = _prepare_arrays_for_backend([k, n, a, b], calc, use_gpu)

    # Clip/validate ranges
    k = xp.clip(k, 0, n)
    a = xp.maximum(a, MIN_BETA_PARAM)
    b = xp.maximum(b, MIN_BETA_PARAM)

    # log C(n,k) via betaln identity
    log_comb = -xbetaln(k + 1, (n - k) + 1) + xp.log(n + 1)
    log_p = log_comb + xbetaln(k + a, (n - k) + b) - xbetaln(a, b)
    return _ensure_cpu_output(log_p, calc, use_gpu)


# Export all public functions
__all__ = [
    'compute_per_site_llr_stats',
    'compute_precision_weighted_score',
    'compute_bhattacharyya_coefficient',
    'beta_log_pdf',
    'compute_beta_mean',
    'compute_beta_variance',
    'log_beta_binomial_pmf',
]

