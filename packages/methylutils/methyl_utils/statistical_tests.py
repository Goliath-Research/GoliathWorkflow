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


# SciPy functions are accessed through DistanceCalculator when needed













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


def ecdf_bhattacharyya_trapezoidal_from_bin_counts(
    bc1: np.ndarray,
    bc2: np.ndarray,
    bin_edges: np.ndarray,
    grid_size: int = 256,
    use_gpu: bool = True,
) -> np.ndarray:
    """
    Approximate Bhattacharyya coefficient by interpolating the ECDF on a dense
    uniform grid, then taking finite differences to estimate the PDF.
    
    This provides a smoother approximation when bins are unmatched or coarse, 
    while avoiding the full PCHIP spline overhead.
    """
    from .metrics_core import DistanceCalculator
    calc = DistanceCalculator()
    
    if use_gpu and getattr(calc, 'gpu_available', False) and hasattr(calc, 'cp'):
        xp = calc.cp
    else:
        xp = np
        
    bc1 = xp.asarray(bc1, dtype=xp.float64)
    bc2 = xp.asarray(bc2, dtype=xp.float64)
    bin_edges = xp.asarray(bin_edges, dtype=xp.float64)

    squeeze = False
    if bc1.ndim == 1:
        bc1 = bc1.reshape(1, -1)
        bc2 = bc2.reshape(1, -1)
        squeeze = True

    n_pos = bc1.shape[0]
    total1 = xp.maximum(xp.sum(bc1, axis=1, keepdims=True), 1e-20)
    total2 = xp.maximum(xp.sum(bc2, axis=1, keepdims=True), 1e-20)

    cumsum1 = xp.cumsum(bc1, axis=1) / total1
    cumsum2 = xp.cumsum(bc2, axis=1) / total2

    # Prepend 0 to form CDF at bin edges
    zeros = xp.zeros((n_pos, 1), dtype=xp.float64)
    cdf1_edges = xp.concatenate([zeros, cumsum1], axis=1)
    cdf2_edges = xp.concatenate([zeros, cumsum2], axis=1)

    grid = xp.linspace(0.0, 1.0, grid_size, dtype=xp.float64)

    # Vectorized searchsorted for interpolation
    idx = xp.searchsorted(bin_edges, grid, side="right") - 1
    idx = xp.clip(idx, 0, len(bin_edges) - 2)

    # Calculate fractional distance t
    widths = xp.maximum(bin_edges[idx + 1] - bin_edges[idx], 1e-20)
    t = (grid - bin_edges[idx]) / widths
    t = xp.clip(t, 0.0, 1.0)

    # Linearly interpolate CDF
    cdf1_grid = (1.0 - t) * cdf1_edges[:, idx] + t * cdf1_edges[:, idx + 1]
    cdf2_grid = (1.0 - t) * cdf2_edges[:, idx] + t * cdf2_edges[:, idx + 1]

    # Compute probability masses over the grid intervals
    p1_grid = xp.maximum(xp.diff(cdf1_grid, axis=1), 0.0)
    p2_grid = xp.maximum(xp.diff(cdf2_grid, axis=1), 0.0)

    # Bhattacharyya coefficient
    overlap = xp.sum(xp.sqrt(p1_grid * p2_grid), axis=1)
    
    out = xp.clip(overlap, 0.0, 1.0)
    if squeeze:
        out = out[0]
        
    if use_gpu and getattr(calc, 'gpu_available', False) and hasattr(xp, 'asnumpy'):
        return xp.asnumpy(out)
    return out

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
    "mann_whitney_from_bin_counts",
    "dl_heterogeneity",
    "ecdf_overlap_integral",
    "effect_size_from_components",
    "ecdf_effect_size",
    "optimize_lambda_var",
    "ecdf_bhattacharyya_trapezoidal_from_bin_counts",
]
