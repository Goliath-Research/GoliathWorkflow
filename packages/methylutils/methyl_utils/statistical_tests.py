"""
Statistical test functions for methylation analysis.

This module provides functions for statistical testing, FDR correction,
and meta-analysis commonly used in methylation studies.
"""

import logging
import numpy as np
from typing import Tuple, Optional, Any, Dict

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
        # TempCentroid or centroid with N, Sx, Sx2 (MoM)
        N1 = np.asarray(centroid1.N, dtype=np.float64).ravel()
        N2 = np.asarray(centroid2.N, dtype=np.float64).ravel()
        if hasattr(centroid1, "Sx") and hasattr(centroid1, "Sx2"):
            alpha1, beta1 = beta_mom_estimation(n=N1, Sx=np.asarray(centroid1.Sx, dtype=np.float64).ravel(), Sx2=np.asarray(centroid1.Sx2, dtype=np.float64).ravel())
            alpha2, beta2 = beta_mom_estimation(n=N2, Sx=np.asarray(centroid2.Sx, dtype=np.float64).ravel(), Sx2=np.asarray(centroid2.Sx2, dtype=np.float64).ravel())
        else:
            alpha1, beta1 = _estimate_beta_params_bounded(N1, centroid1.log_x_sum, centroid1.log_1_minus_x_sum)
            alpha2, beta2 = _estimate_beta_params_bounded(N2, centroid2.log_x_sum, centroid2.log_1_minus_x_sum)
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
    n = np.asarray(n, dtype=np.float64).ravel()
    log_x_sum = np.asarray(log_x_sum, dtype=np.float64).ravel()
    log_mean = np.where(n > 0, log_x_sum / np.maximum(n, 1e-20), 0.0)
    log_mean = np.asarray(log_mean, dtype=np.float64)
    log_mean = np.clip(log_mean, -500.0, 500.0)  # safe for exp; avoid pandas __array_ufunc__ path
    with np.errstate(over="ignore", invalid="ignore"):
        mean_est = np.exp(log_mean)
    mean_est = np.clip(np.asarray(mean_est, dtype=np.float64), 1e-6, 1 - 1e-6)

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


def welch_mean_test(
    delta_mean: np.ndarray,
    var1: np.ndarray,
    n1: np.ndarray,
    var2: np.ndarray,
    n2: np.ndarray,
) -> Dict[str, np.ndarray]:
    """
    Welch-style test for difference in means with unequal variances.

    Returns absolute t statistic, Welch-Satterthwaite dof, standard error,
    and a two-sided p-value.
    """
    from scipy.stats import t as t_dist

    delta_mean = np.asarray(delta_mean, dtype=np.float64).ravel()
    var1 = np.asarray(var1, dtype=np.float64).ravel()
    n1 = np.asarray(n1, dtype=np.float64).ravel()
    var2 = np.asarray(var2, dtype=np.float64).ravel()
    n2 = np.asarray(n2, dtype=np.float64).ravel()

    term1 = np.maximum(var1, 0.0) / np.maximum(n1, 1.0)
    term2 = np.maximum(var2, 0.0) / np.maximum(n2, 1.0)
    se = np.sqrt(term1 + term2)
    se = np.maximum(se, 1e-12)
    t_stat = np.abs(delta_mean) / se

    denom = (
        (term1 ** 2) / np.maximum(n1 - 1.0, 1.0)
        + (term2 ** 2) / np.maximum(n2 - 1.0, 1.0)
    )
    dof = np.where(
        denom > 0.0,
        ((term1 + term2) ** 2) / denom,
        np.maximum(n1 + n2 - 2.0, 1.0),
    )
    dof = np.maximum(dof, 1.0)
    p_values = 2.0 * t_dist.sf(np.abs(t_stat), df=dof)
    p_values = np.clip(np.asarray(p_values, dtype=np.float64), 1e-300, 1.0)
    return {
        "t_stat": np.asarray(t_stat, dtype=np.float64),
        "p_value": p_values,
        "dof": np.asarray(dof, dtype=np.float64),
        "standard_error": np.asarray(se, dtype=np.float64),
    }


def mann_whitney_from_bin_counts(
    bc1: np.ndarray,
    bc2: np.ndarray,
    n1: np.ndarray,
    n2: np.ndarray,
) -> Dict[str, np.ndarray]:
    """
    Vectorized Mann-Whitney U test using centroid bin-count histograms.

    The histogram approximation counts all pairs where a group-1 sample falls in a
    strictly larger bin than a group-2 sample, plus half credit for tied bins.
    """
    from scipy.stats import norm

    bc1 = np.asarray(bc1, dtype=np.float64)
    bc2 = np.asarray(bc2, dtype=np.float64)
    if bc1.ndim == 1:
        bc1 = bc1.reshape(1, -1)
        bc2 = bc2.reshape(1, -1)

    n1 = np.asarray(n1, dtype=np.float64).ravel()
    n2 = np.asarray(n2, dtype=np.float64).ravel()
    if n1.size != bc1.shape[0]:
        n1 = np.resize(n1, bc1.shape[0])
    if n2.size != bc2.shape[0]:
        n2 = np.resize(n2, bc2.shape[0])

    # Reconstruct U from histogram counts: lower bins in group2 contribute a win,
    # same-bin pairs count as ties worth 0.5.
    cs2 = np.cumsum(bc2, axis=1)
    lower_than_bin = np.concatenate(
        [np.zeros((bc2.shape[0], 1), dtype=np.float64), cs2[:, :-1]],
        axis=1,
    )
    u_stat = np.sum(bc1 * lower_than_bin, axis=1) + 0.5 * np.sum(bc1 * bc2, axis=1)

    total_n = np.maximum(n1 + n2, 0.0)
    ties = bc1 + bc2
    denom = np.maximum(total_n * np.maximum(total_n - 1.0, 0.0), 1.0)
    tie_corr = np.sum(ties * (ties**2 - 1.0), axis=1) / denom
    var_u = (n1 * n2 / 12.0) * np.maximum((total_n + 1.0) - tie_corr, 0.0)

    mean_u = (n1 * n2) / 2.0
    z_stat = np.zeros_like(u_stat, dtype=np.float64)
    valid = (n1 > 0) & (n2 > 0) & np.isfinite(var_u) & (var_u > 0.0)
    z_stat[valid] = (u_stat[valid] - mean_u[valid]) / np.sqrt(var_u[valid])
    p_value = np.ones_like(u_stat, dtype=np.float64)
    p_value[valid] = 2.0 * norm.sf(np.abs(z_stat[valid]))
    p_value = np.clip(p_value, 1e-300, 1.0)

    return {
        "u_stat": np.asarray(u_stat, dtype=np.float64),
        "z_stat": np.asarray(z_stat, dtype=np.float64),
        "p_value": np.asarray(p_value, dtype=np.float64),
        "var_u": np.asarray(var_u, dtype=np.float64),
    }


def dl_heterogeneity(
    Sm: np.ndarray,
    Su: np.ndarray,
    Swx2: np.ndarray,
    Sc2: np.ndarray,
    N: np.ndarray,
) -> Dict[str, np.ndarray]:
    """
    DerSimonian-Laird-style decomposition of between-sample heterogeneity using
    centroid sufficient statistics already stored in MethylCentroid.
    """
    Sm = np.asarray(Sm, dtype=np.float64).ravel()
    Su = np.asarray(Su, dtype=np.float64).ravel()
    Swx2 = np.asarray(Swx2, dtype=np.float64).ravel()
    Sc2 = np.asarray(Sc2, dtype=np.float64).ravel()
    N = np.asarray(N, dtype=np.float64).ravel()

    c_total = np.maximum(Sm + Su, 1e-12)
    theta = Sm / c_total
    Q = Swx2 - (Sm**2 / c_total)
    denom = c_total - (Sc2 / c_total)
    tau2 = np.maximum(0.0, (Q - np.maximum(N - 1.0, 0.0)) / np.maximum(denom, 1e-12))

    return {
        "theta": np.asarray(theta, dtype=np.float64),
        "Q": np.asarray(Q, dtype=np.float64),
        "tau2": np.asarray(tau2, dtype=np.float64),
    }


def ecdf_overlap_integral(
    ecdf_view1: "ECDFView",
    ecdf_view2: "ECDFView",
    position_indices: np.ndarray,
    grid_size: int = 512,
) -> np.ndarray:
    """
    Continuous overlap between two ECDF-derived densities:
        overlap = integral_0^1 min(f1(x), f2(x)) dx

    PDF values are renormalized on the integration grid to guard against
    small numerical drift in PCHIP derivatives.
    """
    position_indices = np.asarray(position_indices, dtype=np.intp).ravel()
    grid = np.linspace(0.0, 1.0, grid_size, dtype=np.float64)
    trapz = getattr(np, "trapezoid", np.trapz)

    if hasattr(ecdf_view1, "_pdf_batch") and hasattr(ecdf_view2, "_pdf_batch"):
        pdf1 = np.asarray(ecdf_view1._pdf_batch(position_indices, grid), dtype=np.float64)
        pdf2 = np.asarray(ecdf_view2._pdf_batch(position_indices, grid), dtype=np.float64)
    else:
        pdf1 = np.zeros((len(position_indices), len(grid)), dtype=np.float64)
        pdf2 = np.zeros((len(position_indices), len(grid)), dtype=np.float64)
        for i, pos_idx in enumerate(position_indices):
            pdf1[i] = np.asarray([ecdf_view1._pdf(int(pos_idx), float(x)) for x in grid], dtype=np.float64)
            pdf2[i] = np.asarray([ecdf_view2._pdf(int(pos_idx), float(x)) for x in grid], dtype=np.float64)

    pdf1 = np.maximum(pdf1, 0.0)
    pdf2 = np.maximum(pdf2, 0.0)
    area1 = trapz(pdf1, grid, axis=1)
    area2 = trapz(pdf2, grid, axis=1)
    pdf1 = pdf1 / np.maximum(area1[:, None], 1e-12)
    pdf2 = pdf2 / np.maximum(area2[:, None], 1e-12)
    overlap = trapz(np.minimum(pdf1, pdf2), grid, axis=1)
    return np.clip(np.asarray(overlap, dtype=np.float64), 0.0, 1.0)


def effect_size_from_components(
    delta_mean: np.ndarray,
    overlap: np.ndarray,
    var1: np.ndarray,
    var2: np.ndarray,
    lambda_var: float = 2.0,
) -> Dict[str, np.ndarray]:
    """
    Canonical biological effect size used across MethylUtils/MethylDetector:

        effect_size = |delta_mean| * (1 - overlap) *
                      exp(-lambda_var * (sqrt(var1) + sqrt(var2)))
    """
    delta_mean = np.asarray(delta_mean, dtype=np.float64).ravel()
    overlap = np.asarray(overlap, dtype=np.float64).ravel()
    var1 = np.asarray(var1, dtype=np.float64).ravel()
    var2 = np.asarray(var2, dtype=np.float64).ravel()

    overlap = np.clip(overlap, 0.0, 1.0)
    var1 = np.maximum(var1, 0.0)
    var2 = np.maximum(var2, 0.0)
    reliability = np.exp(-float(lambda_var) * (np.sqrt(var1) + np.sqrt(var2)))
    effect_size = np.abs(delta_mean) * (1.0 - overlap) * reliability
    effect_size = np.clip(effect_size, 0.0, 1.0)
    return {
        "effect_size": np.asarray(effect_size, dtype=np.float64),
        "reliability": np.asarray(reliability, dtype=np.float64),
    }


def ecdf_effect_size(
    delta_mean: np.ndarray,
    var1: np.ndarray,
    var2: np.ndarray,
    ecdf_view1: "ECDFView",
    ecdf_view2: "ECDFView",
    position_indices: np.ndarray,
    lambda_var: float = 2.0,
    grid_size: int = 512,
) -> Dict[str, np.ndarray]:
    """
    Compute continuous-ECDF overlap and the canonical biological effect size.
    """
    overlap = ecdf_overlap_integral(
        ecdf_view1=ecdf_view1,
        ecdf_view2=ecdf_view2,
        position_indices=position_indices,
        grid_size=grid_size,
    )
    effect = effect_size_from_components(
        delta_mean=delta_mean,
        overlap=overlap,
        var1=var1,
        var2=var2,
        lambda_var=lambda_var,
    )
    return {
        "overlap": overlap,
        "effect_size": effect["effect_size"],
        "reliability": effect["reliability"],
    }


def optimize_lambda_var(
    delta_mean: np.ndarray,
    overlap: np.ndarray,
    var1: np.ndarray,
    var2: np.ndarray,
    target_scores: np.ndarray,
    lambda_values: np.ndarray,
) -> Dict[str, Any]:
    """
    Choose lambda_var by maximizing Spearman correlation between effect_size
    and a caller-provided target score (for example 1 - p_value).
    """
    from scipy.stats import spearmanr

    target_scores = np.asarray(target_scores, dtype=np.float64).ravel()
    lambda_values = np.asarray(lambda_values, dtype=np.float64).ravel()
    best_lambda = float(lambda_values[0]) if len(lambda_values) else 0.0
    best_corr = -np.inf
    best_effect = None
    for lam in lambda_values:
        effect = effect_size_from_components(
            delta_mean=delta_mean,
            overlap=overlap,
            var1=var1,
            var2=var2,
            lambda_var=float(lam),
        )["effect_size"]
        if np.nanstd(effect) <= 0.0 or np.nanstd(target_scores) <= 0.0:
            corr = np.nan
        else:
            corr, _ = spearmanr(effect, target_scores)
        if np.isfinite(corr) and corr > best_corr:
            best_corr = float(corr)
            best_lambda = float(lam)
            best_effect = np.asarray(effect, dtype=np.float64)
    if best_effect is None:
        best_effect = effect_size_from_components(
            delta_mean=delta_mean,
            overlap=overlap,
            var1=var1,
            var2=var2,
            lambda_var=best_lambda,
        )["effect_size"]
        best_corr = float("nan")
    return {
        "lambda_var": best_lambda,
        "correlation": best_corr,
        "effect_size": np.asarray(best_effect, dtype=np.float64),
    }


def discrete_overlap_from_bin_counts(
    bc1: np.ndarray,
    bc2: np.ndarray,
    method: str = "bhattacharyya",
) -> np.ndarray:
    """
    Compute overlap in [0, 1] between two binned count distributions (discrete).
    Respects asymmetry of the underlying distribution (e.g. ECDF).

    Args:
        bc1: Bin counts for centroid 1, shape (n_bins,) or (n_positions, n_bins).
        bc2: Bin counts for centroid 2, same shape as bc1.
        method: "bhattacharyya" (sum sqrt(p1*p2)) or "histogram_intersection" (sum min(p1,p2)).

    Returns:
        Overlap per position, shape (n_positions,) or scalar if inputs are (n_bins,).
    """
    bc1 = np.asarray(bc1, dtype=np.float64)
    bc2 = np.asarray(bc2, dtype=np.float64)
    squeeze = False
    if bc1.ndim == 1:
        bc1 = bc1.reshape(1, -1)
        bc2 = bc2.reshape(1, -1)
        squeeze = True
    total1 = np.sum(bc1, axis=1, keepdims=True)
    total2 = np.sum(bc2, axis=1, keepdims=True)
    total1 = np.maximum(total1, 1e-20)
    total2 = np.maximum(total2, 1e-20)
    p1 = bc1 / total1
    p2 = bc2 / total2
    if method == "histogram_intersection":
        overlap = np.sum(np.minimum(p1, p2), axis=1)
    else:
        # Bhattacharyya coefficient (discrete): sum sqrt(p1 * p2)
        overlap = np.sum(np.sqrt(np.maximum(p1 * p2, 0.0)), axis=1)
    out = np.clip(overlap.astype(np.float64), 0.0, 1.0)
    return out[0] if squeeze else out


def welch_d_fast_overlap_approx(
    delta_mean: np.ndarray,
    var1: np.ndarray,
    n1: np.ndarray,
    var2: np.ndarray,
    n2: np.ndarray,
    scale: float = 3.0,
    overlap_approx: Optional[np.ndarray] = None,
) -> dict:
    """
    Fast biological metrics without ECDF: Welch's d, overlap (discrete or Normal fallback),
    and bounded effect size approx. Use for funnel filtering before computing real ECDF metrics.

    Args:
        delta_mean, var1, n1, var2, n2: Per-position stats (same as welch_d_ks_overlap).
        scale: Sigmoid scale for bounded_effect_size (default 3.0).
        overlap_approx: Optional precomputed overlap (e.g. from discrete_overlap_from_bin_counts).
            If None, use Normal-based fallback: 2 * norm.cdf(-welch_d/2).

    Returns:
        Dict with welch_d, overlap_approx, bounded_effect_size_approx. Effect is max(0, 2*sigmoid(x)-1)
        so no difference (x=0) gives 0; range [0,1].
    """
    from scipy.special import expit
    from scipy.stats import norm
    WELCH_D_MAX = 50.0
    delta_mean = np.asarray(delta_mean, dtype=np.float64).ravel()
    var1 = np.asarray(var1, dtype=np.float64).ravel()
    n1 = np.asarray(n1, dtype=np.float64).ravel()
    var2 = np.asarray(var2, dtype=np.float64).ravel()
    n2 = np.asarray(n2, dtype=np.float64).ravel()
    se = np.sqrt(var1 / np.maximum(n1, 1) + var2 / np.maximum(n2, 1))
    se = np.maximum(se, 1e-12)
    welch_d = np.abs(delta_mean) / se
    welch_d = np.minimum(welch_d, WELCH_D_MAX)
    n_pos = len(welch_d)
    if overlap_approx is not None:
        overlap_approx = np.asarray(overlap_approx, dtype=np.float64).ravel()
        if len(overlap_approx) != n_pos:
            overlap_approx = np.resize(overlap_approx, n_pos)
        overlap_approx = np.clip(overlap_approx, 0.0, 1.0)
        # Replace NaN with Normal fallback for that position
        bad = ~np.isfinite(overlap_approx)
        if np.any(bad):
            overlap_approx = overlap_approx.copy()
            overlap_approx[bad] = 2.0 * norm.cdf(-welch_d[bad] / 2.0)
    else:
        overlap_approx = 2.0 * norm.cdf(-welch_d / 2.0)
        overlap_approx = np.clip(overlap_approx, 0.0, 1.0)
    expit_arg = np.clip(scale * welch_d * (1.0 - overlap_approx), -700.0, 700.0)
    bounded_effect_size_approx = np.clip(2.0 * expit(expit_arg) - 1.0, 0.0, 1.0)
    return {
        "welch_d": welch_d,
        "overlap_approx": overlap_approx,
        "bounded_effect_size_approx": bounded_effect_size_approx,
    }


def welch_d_ks_overlap(
    delta_mean: np.ndarray,
    var1: np.ndarray,
    n1: np.ndarray,
    var2: np.ndarray,
    n2: np.ndarray,
    ecdf_view1: Optional[Any] = None,
    ecdf_view2: Optional[Any] = None,
    position_indices: Optional[np.ndarray] = None,
    scale: float = 3.0,
    grid_size: int = 256,
) -> dict:
    """
    Welch's d = |delta_mean| / sqrt(var1/n1 + var2/n2).
    If ECDF views and position_indices are provided: KS statistic D at each position.
    Effect size uses the KS test statistic T = sqrt(n_eff)*D (same as drives ks_p) so it correlates
    with statistical significance: corrected_d = welch_d * min(T, 15), bounded_effect_size = max(0, 2*sigmoid(scale * corrected_d) - 1).
    welch_d keeps biological meaning (mean difference); T aligns with the test. n_eff = 2/(1/n1+1/n2).
    No difference (welch_d=0 or ks_d=0) gives effect 0; strong separation gives effect 1; range [0,1].
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

    # Use KS test statistic T = sqrt(n_eff)*D so effect size aligns with KS p-value (Option 2:
    # biological meaning via welch_d, replacement for the test via T). effect = sigmoid(scale * d * T).
    n_eff = 2.0 / (1.0 / np.maximum(n1, 1) + 1.0 / np.maximum(n2, 1))
    T = np.sqrt(n_eff) * ks_d  # same statistic that drives ks_p
    T = np.minimum(T, 15.0)  # cap so sigmoid(scale * welch_d * T) stays in a sensible range
    corrected_d = welch_d * T
    expit_arg = np.clip(scale * corrected_d, -700.0, 700.0)
    bounded_effect_size = np.clip(2.0 * expit(expit_arg) - 1.0, 0.0, 1.0)

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
    "welch_mean_test",
    "mann_whitney_from_bin_counts",
    "dl_heterogeneity",
    "ecdf_overlap_integral",
    "effect_size_from_components",
    "ecdf_effect_size",
    "optimize_lambda_var",
    "discrete_overlap_from_bin_counts",
    "welch_d_fast_overlap_approx",
    "welch_d_ks_overlap",
]
