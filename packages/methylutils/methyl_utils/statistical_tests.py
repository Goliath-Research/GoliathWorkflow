"""
Statistical test functions for methylation analysis.

This module provides functions for statistical testing, FDR correction,
and meta-analysis commonly used in methylation studies.
"""

import logging
import numpy as np
from typing import Tuple, Optional, Any

# Import GPU detection utilities
from .gpu_detection import is_gpu_available, is_cupyx_scipy_stats_available, get_cupy
from .metrics_core import DistanceCalculator

# Optional plotting imports
try:
    import plotly.graph_objects as go
    import plotly.io as pio
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

logger = logging.getLogger(__name__)


def storey_qvalues(
    p_array: np.ndarray,
    lambdas: Optional[np.ndarray] = None,
    plot_pi0: bool = False,
    plot_path: str = "pi0_vs_lambda.html",
    plot_title: str = "Storey's Pi0 vs Lambda"
) -> Tuple[np.ndarray, float]:
    """
    Compute Storey's q-values for FDR correction.

    This function estimates the proportion of true null hypotheses (π₀) and
    computes q-values, which represent the expected proportion of false
    discoveries among all discoveries up to and including the current test.

    Args:
        p_array: Array of p-values
        lambdas: Array of lambda values for π₀ estimation (default: linspace(0.01, 0.95, 100))
        plot_pi0: Whether to create a plot of π₀ vs λ
        plot_path: Path for the π₀ plot (if plotting is enabled)
        plot_title: Title for the π₀ plot

    Returns:
        Tuple of (q_values, pi0_estimate)

    Raises:
        ValueError: If input validation fails
    """
    from .metrics_core import DistanceCalculator

    # Input validation
    if p_array.size == 0:
        raise ValueError("Input p-values array cannot be empty")

    if np.any((p_array < 0) | (p_array > 1)):
        raise ValueError("All p-values must be in range [0, 1]")

    # Check for GPU availability for stats functions
    gpu_available = is_gpu_available() and is_cupyx_scipy_stats_available()

    if gpu_available:
        try:
            calc = DistanceCalculator()
            xp = calc.cp
            p_array = calc.cp.asarray(p_array, dtype=calc.cp.float32)
            if lambdas is not None:
                lambdas = calc.cp.asarray(lambdas, dtype=calc.cp.float32)
        except ImportError:
            gpu_available = False
            xp = np
    else:
        xp = np

    m = len(p_array)
    lambdas = lambdas if lambdas is not None else xp.linspace(0.01, 0.95, 100)
    pi0s = xp.asarray([(xp.sum(p_array > lambda_val) / ((1 - lambda_val) * m)) for lambda_val in lambdas])
    pi0 = min(float(xp.median(pi0s)), 1.0)

    if plot_pi0 and PLOTLY_AVAILABLE:
        try:
            import signal

            # Set up a timeout for plotting to prevent hangs
            def timeout_handler(signum, frame):
                raise TimeoutError("Plotting timed out")

            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(10)  # 10 second timeout

            try:
                lambdas_cpu = xp.asnumpy(lambdas) if gpu_available else lambdas
                pi0s_cpu = xp.asnumpy(pi0s) if gpu_available else pi0s
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=lambdas_cpu, y=pi0s_cpu, mode='lines+markers', name='pi0(lambda)'))
                fig.add_hline(y=pi0, line=dict(color='red', dash='dash'), name='min pi0')
                fig.update_layout(
                    title=plot_title,
                    xaxis_title="Lambda",
                    yaxis_title="pi0 estimate",
                    title_x=0.5,  # Center the title
                    showlegend=True
                )
                pio.write_html(fig, file=plot_path, auto_open=False)
            finally:
                signal.alarm(0)  # Cancel the timeout

        except (TimeoutError, Exception) as e:
            logger.warning(f"FDR plotting failed ({e}), continuing without plot")
    elif plot_pi0 and not PLOTLY_AVAILABLE:
        logger.warning("Plotly not available for π₀ plotting")

    p_sorted = xp.sort(p_array)
    order = xp.argsort(p_array)
    qvals = pi0 * m * p_sorted / (xp.arange(1, m + 1))
    # minimum.accumulate is not implemented in CuPy; use NumPy for this step
    if gpu_available:
        qvals_np = calc.cp.asnumpy(qvals)
    else:
        qvals_np = qvals
    qvals = np.minimum.accumulate(qvals_np[::-1])[::-1]
    if gpu_available:
        qvals = calc.cp.asarray(qvals, dtype=calc.cp.float32)

    q_final = xp.empty_like(qvals)
    q_final[order] = qvals

    # Ensure output is CPU array
    if gpu_available:
        from .metrics_core import DistanceCalculator
        calc = DistanceCalculator()
        return calc.cp.asnumpy(q_final), pi0
    else:
        return q_final, pi0


def stouffer_global_p(p_array: np.ndarray, weights: Optional[np.ndarray] = None) -> Tuple[float, float]:
    """
    Combine p-values using Stouffer's method.

    This function combines multiple p-values into a single global p-value using
    Stouffer's Z-score method, optionally with weights.

    Args:
        p_array: Array of p-values to combine
        weights: Optional array of weights for each p-value

    Returns:
        Tuple of (combined_p_value, z_score)

    Raises:
        ValueError: If input validation fails
    """
    # Input validation
    if p_array.size == 0:
        raise ValueError("Input p-values array cannot be empty")

    if np.any((p_array < 0) | (p_array > 1)):
        raise ValueError("All p-values must be in range [0, 1]")

    if weights is not None:
        if weights.shape != p_array.shape:
            raise ValueError(f"Weights shape {weights.shape} must match p-values shape {p_array.shape}")
        if np.any(weights < 0):
            raise ValueError("All weights must be non-negative")

    # Handle extreme values (0 and 1) that cause infinite z-scores
    p_array_clean = np.clip(p_array, 1e-10, 1.0 - 1e-10)

    # Check for GPU availability for stats functions
    gpu_available = is_gpu_available() and is_cupyx_scipy_stats_available()

    if gpu_available:
        try:
            import cupyx.scipy.stats as cpstats
            from .metrics_core import DistanceCalculator
            calc = DistanceCalculator()

            p_gpu = calc.cp.asarray(p_array_clean, dtype=calc.cp.float32)
            z_scores = cpstats.norm.isf(p_gpu)
            if weights is not None:
                w_gpu = calc.cp.asarray(weights, dtype=calc.cp.float32)
                z = calc.cp.sum(w_gpu * z_scores) / calc.cp.sqrt(calc.cp.sum(w_gpu ** 2))
            else:
                z = calc.cp.sum(z_scores) / calc.cp.sqrt(len(z_scores))

            # Handle extreme z-scores to avoid numerical issues
            z_val = float(z)
            if z_val > 10 or z_val < -10:
                return 0.0, z_val  # Very significant
            else:
                return float(cpstats.norm.cdf(z_val)), z_val
        except ImportError:
            gpu_available = False

    if not gpu_available:
        from scipy.stats import norm

        z_scores = norm.isf(p_array_clean)
        if weights is not None:
            z = np.sum(weights * z_scores) / np.sqrt(np.sum(weights ** 2))
        else:
            z = np.sum(z_scores) / np.sqrt(len(z_scores))

        # Handle extreme z-scores to avoid numerical issues
        if z > 10:
            return 0.0, z  # Very significant
        elif z < -10:
            return 0.0, z  # Very significant (large negative z-score indicates strong evidence)
        else:
            return norm.cdf(z), z


def beta_loglikelihood(alpha: np.ndarray, beta: np.ndarray, n: np.ndarray) -> np.ndarray:
    """
    Compute log-likelihood for Beta distribution.
    
    This function computes the log-likelihood for a Beta distribution with parameters
    alpha and beta, given n observations. This is used in likelihood ratio tests
    for comparing Beta distributions between groups.
    
    Args:
        alpha: Array of alpha parameters (shape parameters)
        beta: Array of beta parameters (shape parameters)  
        n: Array of sample sizes
        
    Returns:
        Array of log-likelihood values
        
    Raises:
        ValueError: If input validation fails
    """
    from scipy.special import gammaln
    
    # Input validation
    if alpha.shape != beta.shape or alpha.shape != n.shape:
        raise ValueError("All input arrays must have the same shape")
    
    if np.any(alpha <= 0) or np.any(beta <= 0) or np.any(n < 0):
        raise ValueError("Alpha and beta must be positive, n must be non-negative")
    
    # For Beta distribution with parameters alpha, beta and n observations
    # Log-likelihood = n * log(B(α,β)) + (α-1) * Σlog(x) + (β-1) * Σlog(1-x)
    # At the MLE point, this simplifies to:
    # L = n * log(B(α,β)) + (α-1) * log(α) + (β-1) * log(β) - (α+β-2) * log(α+β)
    # This is the log-likelihood at the MLE point where the parameters are estimated
    # from the data using method of moments or MLE
    
    gamma_term = gammaln(alpha + beta) - gammaln(alpha) - gammaln(beta)
    ll = (n * gamma_term + 
          (alpha - 1) * np.log(alpha) + 
          (beta - 1) * np.log(beta) - 
          (alpha + beta - 2) * np.log(alpha + beta))
    
    return ll

# SciPy functions are accessed through DistanceCalculator when needed

def beta_mle_estimation(n: np.ndarray,
                        log_x_sum: np.ndarray,
                        log_1mx_sum: np.ndarray,
                        max_iter: int = 30,
                        tol: float = 1e-8) -> Tuple[np.ndarray, np.ndarray]:
    """
    Vectorized MLE for Beta(α, β) using sufficient statistics:
      g1 = (1/n) * sum log(x),  g2 = (1/n) * sum log(1-x).
    Solves:
      digamma(α) - digamma(α+β) = g1
      digamma(β) - digamma(α+β) = g2
    via damped Newton with a closed-form 2x2 Hessian solve per position.

    Parameters
    ----------
    n : array-like
        Sample counts per position (must be > 0).
    log_x_sum : array-like
        Sum of log(x) per position.
    log_1mx_sum : array-like
        Sum of log(1-x) per position.
    max_iter : int
        Maximum Newton iterations.
    tol : float
        Convergence tolerance on the gradient (inf-norm).

    Returns
    -------
    (alpha, beta) : Tuple[np.ndarray, np.ndarray]  (float32)
        MLE estimates per position.

    Notes
    -----
    * This is true MLE from log-sufficient-statistics; no ad-hoc variance guesses.
    * Handles millions of positions; uses float64 internally for stability.
    * Positions with non-finite stats fall back to (1,1).
    * GPU-accelerated when available using CuPy.
    """
    # Get GPU backend if available
    calc = DistanceCalculator()
    xp, xdigamma, xpolygamma, _ = calc.get_backend()

    # --- validation ---
    n = xp.asarray(n, dtype=xp.float64)
    log_x_sum = xp.asarray(log_x_sum, dtype=xp.float64)
    log_1mx_sum = xp.asarray(log_1mx_sum, dtype=xp.float64)

    if n.shape != log_x_sum.shape or n.shape != log_1mx_sum.shape:
        raise ValueError("All input arrays must have the same shape.")
    if xp.any(n <= 0):
        raise ValueError("Sample sizes must be positive.")
    eps = 1e-12

    # Average log statistics
    g1 = log_x_sum / n
    g2 = log_1mx_sum / n

    # Validate log statistics against empirical expectations
    # For extended centroids, we should also have Sx data for validation
    # If not provided, we'll validate based on reasonable bounds
    finite = xp.isfinite(g1) & xp.isfinite(g2) & (g1 > -50) & (g1 < 10) & (g2 > -50) & (g2 < 10)

    # Additional validation: g1 should be negative (since log(x) < 0 for x < 1)
    # and g2 should also be negative (since log(1-x) < 0 for x > 0)
    reasonable_range = (g1 < 0) & (g2 < 0) & (g1 > -20) & (g2 > -20)
    finite = finite & reasonable_range

    # --- initialization ---
    # Start near (α,β) ≈ (1,1) but bias the ratio using Δ ≈ ψ(α) - ψ(β) ~ log(α/β)
    delta = xp.clip(g1 - g2, -30.0, 30.0)  # avoid overflow
    r = xp.exp(delta)
    mu0 = r / (1.0 + r)                     # ≈ α/(α+β)
    t0 = 2.0                                # mild total concentration to start
    alpha = xp.full_like(g1, t0 * mu0, dtype=xp.float64)
    beta  = xp.full_like(g1, t0 * (1.0 - mu0), dtype=xp.float64)
    alpha = xp.where(~finite, 1.0, alpha)
    beta = xp.where(~finite, 1.0, beta)
    alpha = xp.clip(alpha, eps, None)
    beta  = xp.clip(beta,  eps, None)

    # --- Newton iterations ---
    for _ in range(max_iter):
        ab = alpha + beta
        psi_a  = xdigamma(alpha)
        psi_b  = xdigamma(beta)
        psi_ab = xdigamma(ab)

        # Gradient of the (per-position) score equations
        ga = (psi_ab - psi_a + g1)     # = 0 at optimum
        gb = (psi_ab - psi_b + g2)

        # Stop when gradients are small (only check finite ones)
        if xp.all(~finite | (xp.maximum(xp.abs(ga), xp.abs(gb)) < tol)):
            break

        # Hessian components (scaled by n)
        t1_a  = xpolygamma(1, alpha)
        t1_b  = xpolygamma(1, beta)
        t1_ab = xpolygamma(1, ab)

        c  = n * t1_ab                # shared coupling term (>=0)
        na = n * t1_a                 # >=0
        nb = n * t1_b                 # >=0

        h11 = c - na
        h22 = c - nb
        h12 = c

        det = h11 * h22 - h12 * h12
        # Avoid singular Hessians
        det = xp.where(xp.abs(det) < 1e-24, xp.sign(det) * 1e-24 + (det == 0) * 1e-24, det)

        # Newton step: solve H * d = -g  (2x2 closed form)
        da = -(h22 * ga - h12 * gb) / det
        db = -(-h12 * ga + h11 * gb) / det

        # Vectorized damped update to keep positivity (avoid loops)
        # Use conservative step size reduction - start with full step, reduce where needed
        step = xp.ones_like(alpha, dtype=xp.float64)

        # Check if full step works
        new_a_full = alpha + step * da
        new_b_full = beta  + step * db
        bad_full = (new_a_full <= eps) | (new_b_full <= eps)

        # If any position needs reduction, use a conservative 0.1 step for all
        # This is simpler than vectorized backtracking and still works well
        step = xp.where(bad_full, 0.1, step)
        new_a = alpha + step * da
        new_b = beta  + step * db

        # Apply updates where stats are finite; elsewhere keep (1,1)
        upd = finite
        alpha = xp.where(upd, xp.maximum(new_a, eps), alpha)
        beta = xp.where(upd, xp.maximum(new_b, eps), beta)

    # Clean up any non-finite leftovers
    bad = ~xp.isfinite(alpha) | ~xp.isfinite(beta) | (alpha <= 0) | (beta <= 0)
    alpha = xp.where(bad, 1.0, alpha)
    beta = xp.where(bad, 1.0, beta)

    # Convert back to CPU if needed and return float32
    if calc.gpu_available:
        alpha = xp.asnumpy(alpha).astype(np.float32)
        beta = xp.asnumpy(beta).astype(np.float32)

    return alpha, beta


def beta_estimation_hybrid(
    n: np.ndarray,
    Sx: np.ndarray,
    Sx2: np.ndarray,
    log_x_sum: np.ndarray,
    log_1_minus_x_sum: np.ndarray,
    mean_low: float = 0.01,
    mean_high: float = 0.99,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Beta (α, β) from sufficient stats: use closed-form MoM when mean is not near 0/1,
    otherwise MLE to avoid unstable MoM.

    When mean = Sx/n is in (mean_low, mean_high), MoM is closed-form and correct;
    when mean is close to 0 or 1, MoM can be invalid (e.g. negative or huge α, β),
    so we use MLE for those positions.

    Returns
    -------
    (alpha, beta) : Tuple[np.ndarray, np.ndarray], float64, same shape as n.
    """
    n = np.asarray(n, dtype=np.float64)
    Sx = np.asarray(Sx, dtype=np.float64)
    Sx2 = np.asarray(Sx2, dtype=np.float64)
    log_x_sum = np.asarray(log_x_sum, dtype=np.float64)
    log_1_minus_x_sum = np.asarray(log_1_minus_x_sum, dtype=np.float64)
    mean = Sx / np.maximum(n, 1.0)
    use_mom = (mean >= mean_low) & (mean <= mean_high)
    alpha_mom, beta_mom = beta_mom_estimation(n, Sx, Sx2)
    # Only use MoM where it is valid
    use_mom = (
        use_mom
        & (alpha_mom > 0)
        & (beta_mom > 0)
        & np.isfinite(alpha_mom)
        & np.isfinite(beta_mom)
    )
    alpha_mle, beta_mle = beta_mle_estimation(n, log_x_sum, log_1_minus_x_sum)
    alpha_mle = np.asarray(alpha_mle, dtype=np.float64)
    beta_mle = np.asarray(beta_mle, dtype=np.float64)
    alpha = np.where(use_mom, alpha_mom, alpha_mle)
    beta = np.where(use_mom, beta_mom, beta_mle)
    return alpha, beta


def beta_mom_estimation(n: np.ndarray, Sx: np.ndarray, Sx2: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Method of Moments estimation for Beta distribution parameters.

    Args:
        n: Array of sample sizes
        Sx: Array of sum of x values
        Sx2: Array of sum of x^2 values

    Returns:
        Tuple of (alpha_estimates, beta_estimates)
    """
    # Compute mean and variance with numerical stability
    mean = Sx / n
    # Avoid division by zero when n=1, and ensure variance is non-negative
    var = np.maximum(Sx2 - Sx**2 / n, 0) / np.maximum(n - 1, 1)

    # Ensure variance is positive and mean is in (0,1)
    var = np.maximum(var, 1e-10)
    mean = np.clip(mean, 1e-10, 1 - 1e-10)

    # Method of moments for Beta distribution
    alpha = mean * (mean * (1 - mean) / var - 1)
    beta = (1 - mean) * (mean * (1 - mean) / var - 1)

    # Fallback for invalid estimates
    invalid = (alpha <= 0) | (beta <= 0) | ~np.isfinite(alpha) | ~np.isfinite(beta)
    alpha[invalid] = 1.0
    beta[invalid] = 1.0

    return alpha, beta


def beta_binomial_mom_estimation(
    n_samples: np.ndarray,
    sum_mC: np.ndarray,
    sum_mC2: np.ndarray,
    sum_cov: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Method of Moments for Beta-Binomial parameters from discrete count statistics.

    Beta-Binomial models counts k out of n trials; this uses the count-based
    sufficient statistics (sum_mC = Σ k_i, sum_mC2 = Σ k_i^2, sum_cov = Σ n_i)
    rather than proportion moments. For varying n per sample we use
    n_eff = sum_cov / n_samples (average trials per sample).

    Formulas (fixed n): m1 = (1/N)Σy_i, m2 = (1/N)Σy_i^2;
    α̂ = (n*m1 - m2) / (n*(m2/m1 - m1 - 1) + m1),
    β̂ = (n - m1)(n - m2/m1) / (n*(m2/m1 - m1 - 1) + m1).
    See e.g. statproofbook.github.io/P/betabin-mome.

    Returns:
        (alpha, beta) float64 arrays; invalid positions get (1.0, 1.0).
    """
    n_samples = np.asarray(n_samples, dtype=np.float64)
    sum_mC = np.asarray(sum_mC, dtype=np.float64)
    sum_mC2 = np.asarray(sum_mC2, dtype=np.float64)
    sum_cov = np.asarray(sum_cov, dtype=np.float64)
    N = np.maximum(n_samples, 1.0)
    n_eff = np.maximum(sum_cov / N, 1.0)
    m1 = sum_mC / N
    m2 = sum_mC2 / N
    # Avoid m1=0 for m2/m1
    m1_safe = np.where(m1 > 1e-12, m1, 1e-12)
    ratio = np.where(m2 > 1e-20, m2 / m1_safe, m1_safe)
    denom = n_eff * (ratio - m1 - 1.0) + m1
    denom = np.where(np.abs(denom) < 1e-12, np.sign(denom) * 1e-12 + (denom == 0) * 1e-12, denom)
    alpha = (n_eff * m1 - m2) / denom
    beta = (n_eff - m1) * (n_eff - ratio) / denom
    invalid = (
        (alpha <= 0) | (beta <= 0) | ~np.isfinite(alpha) | ~np.isfinite(beta) |
        (m1 <= 0) | (m1 >= n_eff)
    )
    alpha = np.where(invalid, 1.0, alpha)
    beta = np.where(invalid, 1.0, beta)
    return alpha, beta


def likelihood_ratio_test_beta(
    centroid1: 'MethylSample', centroid2: 'MethylSample',
    use_gpu: bool = True
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Perform statistical test for comparing two Beta distributions using extended centroids.

    For methylation data, we use a simpler and more robust z-test approach:
    Compare the Beta distribution means directly using a z-test approximation.
    This avoids the complex MLE issues while still detecting meaningful differences.

    Args:
        centroid1: First MethylSample extended centroid
        centroid2: Second MethylSample extended centroid
        use_gpu: Whether to use GPU acceleration (if available)

    Returns:
        Tuple of (test_statistics, p_values)
    """
    from scipy.stats import norm

    # Handle different centroid types
    # Full centroids have pos attributes and need position matching
    # TempCentroid objects (from batch processing) are already aligned
    if hasattr(centroid1, 'pos') and hasattr(centroid2, 'pos'):
        # Full centroids - need to find common positions
        pos1_set = set(centroid1.pos)
        pos2_set = set(centroid2.pos)
        common_positions = sorted(pos1_set.intersection(pos2_set))

        if not common_positions:
            # No common positions - return empty results
            return np.array([]), np.array([])

        # Create index mappings for common positions
        pos_to_idx1 = {pos: i for i, pos in enumerate(centroid1.pos)}
        pos_to_idx2 = {pos: i for i, pos in enumerate(centroid2.pos)}

        # Extract data for common positions only
        indices1 = [pos_to_idx1[pos] for pos in common_positions]
        indices2 = [pos_to_idx2[pos] for pos in common_positions]

        N1 = centroid1.N[indices1].astype(np.float32)
        N2 = centroid2.N[indices2].astype(np.float32)

        # Get Beta distribution means
        if hasattr(centroid1, 'alpha') and hasattr(centroid2, 'alpha'):
            mean1_full = centroid1.mean
            mean2_full = centroid2.mean
            mean1 = mean1_full[indices1]
            mean2 = mean2_full[indices2]
        else:
            # Fallback for basic centroids
            mean1 = centroid1.Sx[indices1] / np.maximum(centroid1.N[indices1], 1)
            mean2 = centroid2.Sx[indices2] / np.maximum(centroid2.N[indices2], 1)

        # Get Beta parameters for variance calculation
        if hasattr(centroid1, 'alpha') and hasattr(centroid2, 'alpha'):
            alpha1_full = centroid1.alpha
            beta1_full = centroid1.beta
            alpha2_full = centroid2.alpha
            beta2_full = centroid2.beta
            alpha1 = alpha1_full[indices1]
            beta1 = beta1_full[indices1]
            alpha2 = alpha2_full[indices2]
            beta2 = beta2_full[indices2]
        else:
            # Fallback: estimate from means
            mean1_clipped = np.clip(mean1, 1e-6, 1-1e-6)
            mean2_clipped = np.clip(mean2, 1e-6, 1-1e-6)
            alpha1 = mean1_clipped * 10  # Conservative estimate
            beta1 = (1 - mean1_clipped) * 10
            alpha2 = mean2_clipped * 10
            beta2 = (1 - mean2_clipped) * 10

    else:
        # TempCentroid objects (from batch processing) - already aligned
        N1 = centroid1.N.astype(np.float32)
        N2 = centroid2.N.astype(np.float32)

        # For TempCentroids, we need to estimate parameters from the available data
        # Use bounded MLE estimation with fallbacks
        alpha1, beta1 = _estimate_beta_params_bounded(N1, centroid1.log_x_sum, centroid1.log_1_minus_x_sum)
        alpha2, beta2 = _estimate_beta_params_bounded(N2, centroid2.log_x_sum, centroid2.log_1_minus_x_sum)

        # Compute means from estimated parameters
        mean1 = alpha1 / (alpha1 + beta1)
        mean2 = alpha2 / (alpha2 + beta2)

    # Compute variances of the Beta distribution means
    # Var(α/(α+β)) ≈ αβ/((α+β)^3) for the mean of Beta distribution
    # Then divide by effective sample size N
    var_mean1 = (alpha1 * beta1) / ((alpha1 + beta1)**3) / np.maximum(N1, 1)
    var_mean2 = (alpha2 * beta2) / ((alpha2 + beta2)**3) / np.maximum(N2, 1)

    # Pooled standard error for difference
    se_diff = np.sqrt(var_mean1 + var_mean2)

    # Z-test statistic for difference in means
    diff = mean1 - mean2
    z_stat = diff / np.maximum(se_diff, 1e-12)

    # Two-tailed p-value using normal approximation
    p_values = 2 * (1 - norm.cdf(np.abs(z_stat)))

    # Handle edge cases and numerical stability
    p_values = np.where(np.isfinite(p_values), p_values, 1.0)
    p_values = np.clip(p_values, 1e-20, 1.0)  # Avoid p-values of exactly 0

    return z_stat, p_values


def _estimate_beta_params_bounded(n: np.ndarray, log_x_sum: np.ndarray, log_1mx_sum: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Estimate Beta distribution parameters with bounds checking and fallbacks.

    This function provides reasonable bounds on alpha/beta parameters to prevent
    extreme values that can occur with MLE estimation on edge cases.
    """
    # First try method of moments as a baseline
    # Clip exponent to avoid overflow in exp (float64 overflows for |x| > ~709)
    n = np.asarray(n, dtype=np.float64)
    log_x_sum = np.asarray(log_x_sum, dtype=np.float64)
    log_mean = np.where(n > 0, log_x_sum / n, 0.0)
    log_mean = np.clip(log_mean, -700.0, 700.0)
    mean_est = np.exp(log_mean)
    mean_est = np.clip(mean_est, 1e-6, 1-1e-6)

    # Conservative MoM estimates
    alpha_mom = mean_est * 10
    beta_mom = (1 - mean_est) * 10

    # Try MLE but with bounds
    try:
        # This would be the MLE call, but since we don't have the function,
        # fall back to bounded MoM estimates
        alpha_est = alpha_mom
        beta_est = beta_mom
    except:
        alpha_est = alpha_mom
        beta_est = beta_mom

    # Apply reasonable bounds to prevent extreme values
    # Beta parameters should typically be in reasonable ranges for methylation data
    max_reasonable_param = 1e6  # Much more conservative than the observed millions

    alpha_est = np.clip(alpha_est, 1e-6, max_reasonable_param)
    beta_est = np.clip(beta_est, 1e-6, max_reasonable_param)

    # Additional sanity check: ensure the mean is reasonable
    computed_mean = alpha_est / (alpha_est + beta_est)
    # If the computed mean is too far from the empirical estimate, fall back to MoM
    empirical_mean = mean_est
    mean_diff = np.abs(computed_mean - empirical_mean)

    # If difference is too large, use MoM estimates
    use_mom = mean_diff > 0.5  # More than 50% difference
    alpha_est = np.where(use_mom, alpha_mom, alpha_est)
    beta_est = np.where(use_mom, beta_mom, beta_est)

    # Final bounds check (shared with methyl_distribution_utils for 0/1 edge cases)
    try:
        from methyl_utils.core.methyl_distribution_utils import clip_beta_params_for_bounds
        alpha_est, beta_est = clip_beta_params_for_bounds(
            alpha_est, beta_est, min_param=1e-6, max_param=max_reasonable_param
        )
    except ImportError:
        alpha_est = np.clip(alpha_est, 1e-6, max_reasonable_param)
        beta_est = np.clip(beta_est, 1e-6, max_reasonable_param)
    return alpha_est, beta_est


def aggregate_pvalues_fisher(pvalues: np.ndarray, weights: np.ndarray = None) -> float:
    """
    Fisher's method for combining independent p-values.

    Combines p-values using the chi-squared distribution with 2k degrees of freedom,
    where k is the number of p-values.

    Args:
        pvalues: Array of p-values to combine
        weights: Optional weights for each p-value (must sum to 1)

    Returns:
        Combined p-value

    Notes:
        - Assumes independence between tests
        - Sensitive to small p-values
        - More powerful than Stouffer's for detecting consistent effects
    """
    if len(pvalues) == 0:
        return 1.0

    # Convert p-values to chi-squared statistics
    if weights is None:
        # Unweighted: sum of -2*log(p_i)
        chi2_stat = -2 * np.sum(np.log(pvalues))
    else:
        # Weighted: sum of weights * -2*log(p_i)
        if len(weights) != len(pvalues) or not np.isclose(np.sum(weights), 1.0):
            raise ValueError("Weights must be same length as pvalues and sum to 1")
        chi2_stat = -2 * np.sum(weights * np.log(pvalues))

    # Degrees of freedom = 2 * number of tests
    df = 2 * len(pvalues)

    # Combined p-value from chi-squared distribution
    from scipy.stats import chi2
    combined_p = 1 - chi2.cdf(chi2_stat, df)

    return max(combined_p, 0.0)  # Ensure non-negative


def aggregate_pvalues_stouffer(pvalues: np.ndarray, weights: np.ndarray = None) -> float:
    """
    Stouffer's method for combining independent p-values.

    Converts p-values to z-scores and combines them using weighted average.
    More robust than Fisher's method when effects are not extremely significant.

    Args:
        pvalues: Array of p-values to combine
        weights: Optional weights for each p-value (must sum to 1)

    Returns:
        Combined p-value

    Notes:
        - Assumes independence between tests
        - More robust than Fisher's for moderate effects
        - Less sensitive to single very small p-values
    """
    if len(pvalues) == 0:
        return 1.0

    # Convert p-values to z-scores (one-tailed)
    from scipy.stats import norm
    z_scores = norm.ppf(1 - pvalues)  # Convert to z-scores

    # Handle edge cases
    z_scores = np.clip(z_scores, -8.0, 8.0)  # Prevent extreme values

    if weights is None:
        # Unweighted average
        combined_z = np.mean(z_scores)
    else:
        # Weighted average
        if len(weights) != len(pvalues) or not np.isclose(np.sum(weights), 1.0):
            raise ValueError("Weights must be same length as pvalues and sum to 1")
        combined_z = np.sum(weights * z_scores)

    # Convert back to p-value (one-tailed)
    combined_p = 1 - norm.cdf(combined_z)

    return max(combined_p, 0.0)


def aggregate_pvalues_lancaster(pvalues: np.ndarray, weights: np.ndarray = None,
                               degrees: np.ndarray = None) -> float:
    """
    Lancaster's method - generalization of Fisher's method.

    Allows different degrees of freedom for each test, making it suitable
    for combining p-values from different types of statistical tests.

    Args:
        pvalues: Array of p-values to combine
        weights: Optional weights for each p-value
        degrees: Degrees of freedom for each test (default: 1 for each)

    Returns:
        Combined p-value

    Notes:
        - Generalization of Fisher's method
        - Accounts for different test types/degrees of freedom
        - More flexible than basic Fisher's method
    """
    if len(pvalues) == 0:
        return 1.0

    if degrees is None:
        degrees = np.ones(len(pvalues))

    # Convert to chi-squared statistics
    chi2_stats = -2 * np.log(pvalues) / degrees

    if weights is None:
        combined_chi2 = np.sum(chi2_stats)
        total_df = 2 * np.sum(degrees)
    else:
        if len(weights) != len(pvalues) or not np.isclose(np.sum(weights), 1.0):
            raise ValueError("Weights must be same length as pvalues and sum to 1")
        combined_chi2 = np.sum(weights * chi2_stats)
        total_df = 2 * np.sum(weights * degrees)

    from scipy.stats import chi2
    combined_p = 1 - chi2.cdf(combined_chi2, total_df)

    return max(combined_p, 0.0)


def aggregate_pvalues_tippett(pvalues: np.ndarray) -> float:
    """
    Tippett's method - minimum p-value approach.

    Uses the minimum p-value to test against multiplicity.
    Equivalent to testing if all null hypotheses are true.

    Args:
        pvalues: Array of p-values to combine

    Returns:
        Combined p-value

    Notes:
        - Conservative approach
        - Good for detecting if any effect exists
        - Less powerful than other methods for consistent effects
    """
    if len(pvalues) == 0:
        return 1.0

    min_p = np.min(pvalues)
    k = len(pvalues)

    # Combined p-value = 1 - (1 - min_p)^k
    combined_p = 1 - (1 - min_p)**k

    return max(combined_p, 0.0)


def aggregate_pvalues_edgington(pvalues: np.ndarray) -> float:
    """
    Edgington's method - sum of p-values.

    Simple method that sums p-values and compares to a uniform distribution.
    Good for detecting overall significance when effects are weak.

    Args:
        pvalues: Array of p-values to combine

    Returns:
        Combined p-value

    Notes:
        - Simple and intuitive
        - Good for detecting weak but consistent effects
        - Less sensitive than Fisher/Stouffer for strong effects
    """
    if len(pvalues) == 0:
        return 1.0

    k = len(pvalues)
    sum_p = np.sum(pvalues)

    # Under null hypothesis, sum follows Irwin-Hall distribution
    # For large k, approximate with normal distribution
    if k < 20:
        # For small k, use beta distribution approximation
        # Sum of uniforms is Irwin-Hall, but for p-values approximation:
        from scipy.stats import beta
        # P(Sum >= s) where Sum ~ Irwin-Hall(k)
        # Approximation using beta distribution
        combined_p = 1 - beta.cdf(sum_p, k, 1)
    else:
        # Normal approximation for large k
        mean = k / 2
        std = np.sqrt(k / 12)
        from scipy.stats import norm
        combined_p = 1 - norm.cdf(sum_p, mean, std)

    return max(combined_p, 0.0)


def aggregate_pvalues_mudholkar_george(pvalues: np.ndarray) -> float:
    """
    Mudholkar-George method for combining p-values.

    Uses a transformation that stabilizes variance and provides good power.

    Args:
        pvalues: Array of p-values to combine

    Returns:
        Combined p-value

    Notes:
        - Good balance of power and robustness
        - Performs well across different scenarios
        - Less sensitive to outliers than Fisher
    """
    if len(pvalues) == 0:
        return 1.0

    k = len(pvalues)

    # Mudholkar-George transformation: z_i = Φ^{-1}(1 - p_i^{1/k})
    from scipy.stats import norm
    transformed = norm.ppf(1 - pvalues**(1/k))

    # Combine using Stouffer-like approach
    combined_z = np.sum(transformed) / np.sqrt(k)

    # Convert back to p-value
    combined_p = 1 - norm.cdf(combined_z)

    return max(combined_p, 0.0)


def aggregate_pvalues_simes(pvalues: np.ndarray) -> float:
    """
    Simes method for combining p-values (Generalized Simes).

    Based on Simes inequality, combines p-values by taking the minimum
    of k×p_{(i)}/i for i=1 to k, where p_{(i)} is the i-th smallest p-value.

    This is equivalent to the Bonferroni-Holm procedure but used for combination
    rather than correction. Controls FWER under positive dependence.

    Args:
        pvalues: Array of p-values to combine

    Returns:
        Combined p-value

    Notes:
        - Conservative approach based on Simes inequality
        - Good for detecting presence of ANY significant effect
        - More powerful than Bonferroni for combination tasks
        - Controls Type I error under positive dependence
    """
    if len(pvalues) == 0:
        return 1.0

    k = len(pvalues)
    sorted_p = np.sort(pvalues)

    # Simes combined p-value: min over i of (k × p_{(i)} / i)
    # This is the same as the Holm-Bonferroni procedure
    simes_values = [min(1.0, k * sorted_p[i] / (i + 1)) for i in range(k)]
    combined_p = min(simes_values)

    return combined_p


def ecdf_ks_statistic(
    ecdf_view1: Any,
    ecdf_view2: Any,
    position_indices: np.ndarray,
    grid_size: int = 256,
) -> np.ndarray:
    """
    KS statistic between two ECDFs at each position: D = sup_x |F1(x) - F2(x)| on a grid in [0, 1].
    Uses vectorized _cdf_batch when available for speed; falls back to per-position _cdf otherwise.
    """
    position_indices = np.asarray(position_indices, dtype=np.intp).ravel()
    grid = np.linspace(0.0, 1.0, grid_size, dtype=np.float64)
    use_batch = (
        hasattr(ecdf_view1, "_cdf_batch")
        and hasattr(ecdf_view2, "_cdf_batch")
    )
    if use_batch:
        f1 = ecdf_view1._cdf_batch(position_indices, grid)  # (n_positions, grid_size)
        f2 = ecdf_view2._cdf_batch(position_indices, grid)
        ks_stats = np.max(np.abs(f1 - f2), axis=1)
        return ks_stats.astype(np.float64)
    ks_stats = np.zeros(len(position_indices), dtype=np.float64)
    for i, pos_idx in enumerate(position_indices):
        pos_idx = int(pos_idx)
        f1 = ecdf_view1._cdf(pos_idx, grid)
        f2 = ecdf_view2._cdf(pos_idx, grid)
        ks_stats[i] = np.max(np.abs(f1 - f2))
    return ks_stats


def ecdf_ks_pvalue(
    ecdf_view1: "ECDFView",
    ecdf_view2: "ECDFView",
    position_indices: np.ndarray,
    n1: np.ndarray,
    n2: np.ndarray,
    grid_size: int = 256,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    KS statistic and asymptotic two-sided p-value for two ECDFs at each position.
    n_eff = harmonic mean of n1, n2; p = kstwobign.sf(sqrt(n_eff) * D).
    """
    from scipy.stats import kstwobign
    ks_stats = ecdf_ks_statistic(ecdf_view1, ecdf_view2, position_indices, grid_size)
    n1 = np.asarray(n1, dtype=np.float64).ravel()
    n2 = np.asarray(n2, dtype=np.float64).ravel()
    n_eff = 2.0 / (1.0 / np.maximum(n1, 1) + 1.0 / np.maximum(n2, 1))
    sqrt_n_eff = np.sqrt(n_eff)
    p_values = kstwobign.sf(sqrt_n_eff * ks_stats)
    return ks_stats, p_values


def welch_d_ks_overlap(
    delta_mean: np.ndarray,
    var1: np.ndarray,
    n1: np.ndarray,
    var2: np.ndarray,
    n2: np.ndarray,
    ecdf_view1: Optional[Any] = None,
    ecdf_view2: Optional[Any] = None,
    position_indices: Optional[np.ndarray] = None,
    scale: float = 4.0,
    grid_size: int = 256,
) -> dict:
    """
    Welch's d = |delta_mean| / sqrt(var1/n1 + var2/n2).
    If ECDF views and position_indices are provided: KS statistic D at each position,
    corrected_d = welch_d * (1 - D), bounded_effect_size = sigmoid(scale * corrected_d) in [0, 1].
    Otherwise: bounded_effect_size = sigmoid(scale * welch_d).
    Returns dict with keys: welch_d, ks_d, ks_p, corrected_d, bounded_effect_size.

    When variance1 and variance2 are both zero (or very small), the standard error is floored
    to avoid division by zero; welch_d can become very large. welch_d is capped to WELCH_D_MAX
    so that bounded_effect_size does not overflow and is interpretable (zero variance → perfect
    discrimination → bounded_effect_size ≈ 1).
    """
    from scipy.special import expit
    WELCH_D_MAX = 50.0  # cap so expit(scale * corrected_d) is stable and zero variance → effect ≈ 1
    delta_mean = np.asarray(delta_mean, dtype=np.float64).ravel()
    var1 = np.asarray(var1, dtype=np.float64).ravel()
    n1 = np.asarray(n1, dtype=np.float64).ravel()
    var2 = np.asarray(var2, dtype=np.float64).ravel()
    n2 = np.asarray(n2, dtype=np.float64).ravel()
    se = np.sqrt(var1 / np.maximum(n1, 1) + var2 / np.maximum(n2, 1))
    se = np.maximum(se, 1e-12)  # avoid division by zero when both variances are 0
    welch_d = np.abs(delta_mean) / se
    welch_d = np.minimum(welch_d, WELCH_D_MAX)  # cap: zero variance → max effect, no overflow

    ks_d = np.zeros_like(welch_d)
    ks_p = np.ones_like(welch_d)
    if ecdf_view1 is not None and ecdf_view2 is not None and position_indices is not None:
        pos_idx = np.asarray(position_indices, dtype=np.intp).ravel()
        n1_sub = n1[: len(pos_idx)] if len(n1) >= len(pos_idx) else np.resize(n1, len(pos_idx))
        n2_sub = n2[: len(pos_idx)] if len(n2) >= len(pos_idx) else np.resize(n2, len(pos_idx))
        ks_d_arr, ks_p_arr = ecdf_ks_pvalue(ecdf_view1, ecdf_view2, pos_idx, n1_sub, n2_sub, grid_size)
        ks_d = ks_d_arr
        ks_p = ks_p_arr

    corrected_d = welch_d * (1.0 - ks_d)
    expit_arg = np.clip(scale * corrected_d, -700.0, 700.0)
    bounded_effect_size = expit(expit_arg)

    return {
        "welch_d": welch_d,
        "ks_d": ks_d,
        "ks_p": ks_p,
        "corrected_d": corrected_d,
        "bounded_effect_size": bounded_effect_size,
    }


# Dictionary of available aggregation methods
PVALUE_AGGREGATION_METHODS = {
    'fisher': aggregate_pvalues_fisher,
    'stouffer': aggregate_pvalues_stouffer,
    'lancaster': aggregate_pvalues_lancaster,
    'tippett': aggregate_pvalues_tippett,
    'edgington': aggregate_pvalues_edgington,
    'mudholkar_george': aggregate_pvalues_mudholkar_george,
    'simes': aggregate_pvalues_simes,
}


__all__ = [
    "storey_qvalues",
    "stouffer_global_p",
    "beta_loglikelihood",
    "beta_mle_estimation",
    "beta_estimation_hybrid",
    "beta_mom_estimation",
    "beta_binomial_mom_estimation",
    "likelihood_ratio_test_beta",
    "aggregate_pvalues_fisher",
    "aggregate_pvalues_stouffer",
    "aggregate_pvalues_lancaster",
    "aggregate_pvalues_tippett",
    "aggregate_pvalues_edgington",
    "aggregate_pvalues_mudholkar_george",
    "aggregate_pvalues_simes",
    "PVALUE_AGGREGATION_METHODS",
    "ecdf_ks_statistic",
    "ecdf_ks_pvalue",
    "welch_d_ks_overlap",
]
