"""
Advanced DMP Selection Algorithms

This module implements sophisticated optimization algorithms for minimal DMP subset selection,
improving upon the basic greedy approach with better exploration and optimality guarantees.
"""

import numpy as np
import logging
from typing import List, Dict, Union, Tuple, Optional, Any
from dataclasses import dataclass
import time
from scipy.stats import norm
from scipy.optimize import root_scalar

# Import directly from MethylUtils
from methyl_utils.gpu_detection import is_gpu_available, is_cupyx_scipy_special_available
# Import statistical functions from MethylUtils (required)
from methyl_utils import compute_beta_llr_moments

# Import DMPFilterResult for type hints
from .dmp_filter import DMPFilterResult

logger = logging.getLogger(__name__)

# GPU imports with fallback
GPU_AVAILABLE = is_gpu_available()
CUPYX_SCIPY_SPECIAL_AVAILABLE = is_cupyx_scipy_special_available()

if GPU_AVAILABLE and CUPYX_SCIPY_SPECIAL_AVAILABLE:
    try:
        import cupy as cp
        logger.debug("GPU acceleration available for advanced DMP selector")
    except ImportError as e:
        logger.warning(f"Failed to import GPU libraries: {e}")
        GPU_AVAILABLE = False
else:
    logger.debug("GPU not available, using CPU-only mode for advanced DMP selector")



def compute_subset_performance(
    selected_indices: List[int],
    filtered_results: List[DMPFilterResult],
    use_gpu: bool = False,
    metric: str = 'auc'
) -> float:
    """
    Compute performance metric for a subset of DMPs.
    
    Args:
        selected_indices: Indices of selected DMPs
        filtered_results: List of all DMP results
        use_gpu: Whether to use GPU acceleration
        metric: Performance metric ('auc' or 'youden')
    
    Returns:
        Performance value
    """
    if len(selected_indices) == 0:
        return 0.0
    
    xp = cp if use_gpu and GPU_AVAILABLE else np
    
    # Extract Beta parameters for selected DMPs
    selected_results = [filtered_results[i] for i in selected_indices]

    alpha1 = xp.array([float(r.alpha1) for r in selected_results])
    beta1 = xp.array([float(r.beta1) for r in selected_results])
    alpha2 = xp.array([float(r.alpha2) for r in selected_results])
    beta2 = xp.array([float(r.beta2) for r in selected_results])

    # Compute LLR moments for each DMP individually to determine correct orientation
    da = alpha1 - alpha2
    db = beta1 - beta2

    mu1_ind, var1_ind = compute_beta_llr_moments(alpha1, beta1, da, db, use_gpu)
    mu2_ind, var2_ind = compute_beta_llr_moments(alpha2, beta2, da, db, use_gpu)

    # Ensure LLR moments are CuPy arrays if using GPU
    if use_gpu and GPU_AVAILABLE:
        mu1_ind = xp.asarray(mu1_ind)
        mu2_ind = xp.asarray(mu2_ind)

    # Determine correct orientation based on LLR moments (higher mu = better discrimination)
    directions_from_llr = xp.where(mu1_ind > mu2_ind, 1, -1)

    # Handle directional flipping based on LLR-determined directions
    mask_flip = directions_from_llr == -1
    alpha1_flip = xp.where(mask_flip, alpha2, alpha1)
    beta1_flip = xp.where(mask_flip, beta2, beta1)
    alpha2_flip = xp.where(mask_flip, alpha1, alpha2)
    beta2_flip = xp.where(mask_flip, beta1, beta2)

    # Compute moments with correct orientation
    da_flip = alpha1_flip - alpha2_flip
    db_flip = beta1_flip - beta2_flip

    mu_d, var_d = compute_beta_llr_moments(alpha1_flip, beta1_flip, da_flip, db_flip, use_gpu)
    mu_h, var_h = compute_beta_llr_moments(alpha2_flip, beta2_flip, da_flip, db_flip, use_gpu)
    
    # Combine moments
    combined_mu_d = xp.sum(mu_d)
    combined_var_d = xp.sum(var_d)
    combined_mu_h = xp.sum(mu_h)
    combined_var_h = xp.sum(var_h)
    
    delta_mu = xp.abs(combined_mu_d - combined_mu_h)
    total_var = combined_var_d + combined_var_h

    # Handle numerical stability issues
    if total_var <= 1e-10 or not xp.isfinite(total_var):
        # If variance is too small or invalid, return default AUC
        return 0.5

    d_val = delta_mu / xp.sqrt(total_var)

    # Clip extreme d values to prevent numerical issues
    d_val = xp.clip(d_val, 0, 10)

    if metric == 'auc':
        # Convert to CPU for norm.cdf if using GPU
        if use_gpu and GPU_AVAILABLE:
            d_val_cpu = float(d_val.get())
        else:
            d_val_cpu = float(d_val)

        # Ensure d_val_cpu is finite
        if not np.isfinite(d_val_cpu):
            return 0.5

        return norm.cdf(d_val_cpu)
    
    elif metric == 'youden':
        # Compute optimal Youden's J with numerical stability checks
        mu_d_val = float(combined_mu_d.get() if use_gpu and GPU_AVAILABLE else combined_mu_d)
        sigma_d_val = float(xp.sqrt(combined_var_d).get() if use_gpu and GPU_AVAILABLE else xp.sqrt(combined_var_d))
        mu_h_val = float(combined_mu_h.get() if use_gpu and GPU_AVAILABLE else combined_mu_h)
        sigma_h_val = float(xp.sqrt(combined_var_h).get() if use_gpu and GPU_AVAILABLE else xp.sqrt(combined_var_h))

        # Check for numerical stability
        if not np.isfinite(mu_d_val) or not np.isfinite(mu_h_val) or \
           not np.isfinite(sigma_d_val) or not np.isfinite(sigma_h_val) or \
           sigma_d_val <= 1e-10 or sigma_h_val <= 1e-10:
            return 0.0

        def neg_youden(t):
            # Handle division by zero
            if sigma_d_val <= 1e-10:
                tpr = 1.0 if t >= mu_d_val else 0.0
            else:
                tpr = 1 - norm.cdf((t - mu_d_val) / sigma_d_val)

            if sigma_h_val <= 1e-10:
                fpr = 1.0 if t >= mu_h_val else 0.0
            else:
                fpr = 1 - norm.cdf((t - mu_h_val) / sigma_h_val)

            youden_j = tpr - fpr
            return -youden_j

        try:
            # Ensure bracket is valid
            lower_bound = mu_h_val - 3*max(sigma_h_val, 0.1)
            upper_bound = mu_d_val + 3*max(sigma_d_val, 0.1)

            if lower_bound >= upper_bound:
                return 0.0

            res = root_scalar(
                neg_youden,
                bracket=[lower_bound, upper_bound],
                method='brentq'
            )
            return -neg_youden(res.root)
        except (ValueError, RuntimeError):
            return 0.0
    
    return 0.0

def select_subset_biological_significance_threshold(
    filtered_results: List[DMPFilterResult],
    target_auc: float = 0.95,
    metric: str = 'auc',
    target_youden: float = 0.9,
    use_gpu: bool = True
) -> OptimizationResult:
    """
    Select all DMPs above the biological significance threshold required for discrimination.

    This method uses binary search to efficiently find the smallest subset size that achieves
    the target performance, then selects all DMPs with biological significance above that threshold.

    This differs from minimal set selection by including all biologically significant DMPs above
    the threshold needed for target performance, rather than finding the smallest set.

    Args:
        filtered_results: List of DMP results
        target_auc: Target AUC threshold
        metric: Performance metric ('auc' or 'youden')
        target_youden: Target Youden's J threshold
        use_gpu: Whether to use GPU acceleration

    Returns:
        OptimizationResult with all biologically significant DMPs
    """
    start_time = time.time()
    n_dmps = len(filtered_results)
    target_value = target_auc if metric == 'auc' else target_youden

    logger.info(f"Starting Biological Significance Threshold selection for {n_dmps} DMPs")
    logger.info(f"Target {metric}: {target_value:.3f}")

    # Compute biological significance scores for all DMPs
    biological_significance_scores = []
    for i, r in enumerate(filtered_results):
        # Use the same ranking metric as the filter: delta_mean / (1 - overlap + epsilon)
        overlap = r.distribution_overlap if r.distribution_overlap is not None else 0.5
        significance = r.Δμ / (1 - overlap + 1e-6)
        biological_significance_scores.append((i, significance))

    # Sort by biological significance (descending)
    biological_significance_scores.sort(key=lambda x: x[1], reverse=True)

    # Find the minimum significance threshold needed for target performance using binary search
    threshold_significance = None
    threshold_index = None

    # Binary search for the smallest k that achieves target performance
    # Since DMPs are sorted by significance, performance should be non-decreasing with k
    low, high = 1, n_dmps
    best_k = n_dmps  # Default to all DMPs

    logger.info(f"Using binary search to find optimal subset size (range: {low}-{high})")

    while low <= high:
        mid = (low + high) // 2
        test_indices = [idx for idx, _ in biological_significance_scores[:mid]]
        performance = compute_subset_performance(test_indices, filtered_results, use_gpu, metric)

        logger.info(f"Testing subset of size {mid}: {performance:.3f}")

        if performance >= target_value:
            # This k achieves target - try smaller k
            best_k = mid
            high = mid - 1
        else:
            # This k doesn't achieve target - need larger k
            low = mid + 1

    # Verify the found k actually achieves the target (in case of edge cases)
    if best_k <= n_dmps:
        test_indices = [idx for idx, _ in biological_significance_scores[:best_k]]
        final_performance = compute_subset_performance(test_indices, filtered_results, use_gpu, metric)

        if final_performance >= target_value:
            threshold_significance = biological_significance_scores[best_k-1][1]
            threshold_index = best_k
            logger.info(f"Binary search found optimal k={best_k} with performance {final_performance:.3f}")
        else:
            # Fallback: use all DMPs
            logger.warning(f"Binary search result doesn't meet target, falling back to all DMPs")
            threshold_significance = biological_significance_scores[-1][1] if biological_significance_scores else 0.0
            threshold_index = n_dmps
    else:
        # Fallback: use all DMPs
        threshold_significance = biological_significance_scores[-1][1] if biological_significance_scores else 0.0
        threshold_index = n_dmps

    # Select ALL DMPs above or equal to the threshold significance
    selected_indices = []
    for i, (_, significance) in enumerate(biological_significance_scores):
        if significance >= threshold_significance:
            selected_indices.append(biological_significance_scores[i][0])

    # Sort selected indices for consistency
    selected_indices.sort()

    # Compute final performance
    final_performance = compute_subset_performance(selected_indices, filtered_results, use_gpu, metric)

    end_time = time.time()

    logger.info("Biological Significance Threshold selection completed:")
    logger.info(f"  Threshold significance: {threshold_significance:.6f}")
    logger.info(f"  Threshold would select top-{threshold_index} DMPs")
    logger.info(f"  Final selection: k={len(selected_indices)} DMPs")
    logger.info(f"  Final {metric}: {final_performance:.3f}")
    logger.info(f"  Time elapsed: {end_time - start_time:.2f}s")

    return OptimizationResult(
        selected_indices=selected_indices,
        k=len(selected_indices),
        final_performance=final_performance,
        algorithm="biological_significance_threshold",
        optimal=False,  # This is a threshold-based approach, not optimization
        iterations=1,  # Single pass through data
        time_elapsed=end_time - start_time,
        objective_value=len(selected_indices),  # Number selected (for comparison)
        metadata={
            "threshold_significance": threshold_significance,
            "threshold_would_select_k": threshold_index,
            "selection_ratio": len(selected_indices) / n_dmps if n_dmps > 0 else 0,
            "biological_significance_range": {
                "max": biological_significance_scores[0][1] if biological_significance_scores else 0,
                "min": biological_significance_scores[-1][1] if biological_significance_scores else 0,
                "threshold": threshold_significance
            }
        }
    )

