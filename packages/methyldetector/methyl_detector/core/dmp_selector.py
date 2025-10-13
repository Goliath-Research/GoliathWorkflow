# new module e.g. dmp_selector.py (or place near bottom of dmp_filter.py if you prefer)
import numpy as np
from typing import List, Dict, Union
import logging
# scipy.special imports removed - using MethylUtils functions instead
from scipy.stats import norm
from scipy.optimize import root_scalar

# Import directly from MethylUtils
from methyl_utils.gpu_detection import is_gpu_available, is_cupyx_scipy_special_available, cleanup_gpu_memory
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
        logger.debug("GPU acceleration available for DMP selector")
    except ImportError as e:
        logger.warning(f"Failed to import GPU libraries: {e}")
        GPU_AVAILABLE = False
else:
    logger.debug("GPU not available, using CPU-only mode for DMP selector")

def select_min_subset_analytic(
    filtered_results: List['DMPFilterResult'], 
    target_auc: float = 0.95, 
    use_gpu: bool = True,
    metric: str = 'auc', 
    target_youden: float = 0.9
) -> Dict[str, Union[List[int], int, List[tuple], bool]]:
    """
    Analytic selection of min DMP subset.
    
    Args:
        filtered_results: List of DMPFilterResult, assumed sorted by ranking measure descending.
        target_auc: Target AUC threshold.
        use_gpu: Use GPU if available.
        metric: 'auc' (default) or 'youden'.
        target_youden: Target max Youden's J.
        
    Returns:
        dict with selected indices, k, metric_curve, gpu_used.
    """
    use_gpu_acc = use_gpu and GPU_AVAILABLE and CUPYX_SCIPY_SPECIAL_AVAILABLE
    xp = cp if use_gpu_acc else np
    
    n = len(filtered_results)
    if n == 0:
        return {
            "selected_local_idxs": [], 
            "k": 0, "metric_curve": [], 
            "gpu_acceleration_used": use_gpu_acc
        }
    
    # Extract arrays - ensure we use the correct array type
    alpha1 = xp.array([float(r.alpha1) for r in filtered_results])
    beta1 = xp.array([float(r.beta1) for r in filtered_results])
    alpha2 = xp.array([float(r.alpha2) for r in filtered_results])
    beta2 = xp.array([float(r.beta2) for r in filtered_results])
    directions = xp.array([int(r.direction) for r in filtered_results])
    
    # Flip for hypo (direction == -1)
    mask_flip = directions == -1
    alpha1_flip = xp.where(mask_flip, alpha2, alpha1)
    beta1_flip = xp.where(mask_flip, beta2, beta1)
    alpha2_flip = xp.where(mask_flip, alpha1, alpha2)
    beta2_flip = xp.where(mask_flip, beta1, beta2)
    
    # Compute da, db for flipped
    da = alpha1_flip - alpha2_flip
    db = beta1_flip - beta2_flip
    
    # Moments under disease (flipped a1,b1)
    mu_d, var_d = compute_beta_llr_moments(alpha1_flip, beta1_flip, da, db, use_gpu_acc)
    
    # Moments under healthy (flipped a2,b2)
    mu_h, var_h = compute_beta_llr_moments(alpha2_flip, beta2_flip, da, db, use_gpu_acc)
    
    # Cumulative (since sorted, add sequentially)
    cum_mu_d = xp.cumsum(mu_d)
    cum_var_d = xp.cumsum(var_d)
    cum_mu_h = xp.cumsum(mu_h)
    cum_var_h = xp.cumsum(var_h)
    
    # Separation
    delta_mu = xp.abs(cum_mu_d - cum_mu_h)
    total_var = cum_var_d + cum_var_h
    d_vals = delta_mu / xp.sqrt(total_var)
    
    # Convert to NumPy for norm.cdf if using GPU
    if use_gpu_acc:
        d_vals_np = d_vals.get()  # Convert CuPy array to NumPy
    else:
        d_vals_np = d_vals
    auc_approx = norm.cdf(d_vals_np)  # Assuming delta_mu >0 after flip
    
    # For curve
    metric_curve = []
    selected = []
    for k in range(1, n + 1):
        if metric == 'auc':
            metric_now = auc_approx[k-1]
            target_value = target_auc
        else:  # youden
            def neg_youden(t, mu_d_k, sigma_d_k, mu_h_k, sigma_h_k):
                tpr = 1 - norm.cdf((t - mu_d_k) / sigma_d_k)
                fpr = 1 - norm.cdf((t - mu_h_k) / sigma_h_k)
                return -(tpr - fpr)
            
            # Convert to Python floats if using GPU
            if use_gpu_acc:
                mu_d_k = float(cum_mu_d[k-1].get())
                sigma_d_k = np.sqrt(float(cum_var_d[k-1].get()))
                mu_h_k = float(cum_mu_h[k-1].get())
                sigma_h_k = np.sqrt(float(cum_var_h[k-1].get()))
            else:
                mu_d_k = float(cum_mu_d[k-1])
                sigma_d_k = np.sqrt(float(cum_var_d[k-1]))
                mu_h_k = float(cum_mu_h[k-1])
                sigma_h_k = np.sqrt(float(cum_var_h[k-1]))
            
            # Bracket: assume mu_h - 3 sigma_h to mu_d + 3 sigma_d
            res = root_scalar(
                lambda t: -neg_youden(t, mu_d_k, sigma_d_k, mu_h_k, sigma_h_k),
                bracket=[mu_h_k - 3*sigma_h_k, mu_d_k + 3*sigma_d_k],
                method='brentq'
            )
            t_opt = res.root
            metric_now = -neg_youden(t_opt, mu_d_k, sigma_d_k, mu_h_k, sigma_h_k)  # Positive Youden
            target_value = target_youden
        
        metric_curve.append((k, metric_now))
        
        if metric_now >= target_value:
            selected = list(range(k))  # Indices 0 to k-1
            break
    
    # Backward pruning
    improved: bool = True
    while improved and len(selected) > 1:
        improved = False
        # Try removing each DMP in current subset
        for j in list(selected):
            trial = [t for t in selected if t != j]
            
            # Compute cumulative moments for trial subset
            trial_indices = xp.array(trial)
            trial_mu_d = xp.sum(mu_d[trial_indices])
            trial_var_d = xp.sum(var_d[trial_indices])
            trial_mu_h = xp.sum(mu_h[trial_indices])
            trial_var_h = xp.sum(var_h[trial_indices])
            
            # Compute metric for trial subset
            trial_delta_mu = xp.abs(trial_mu_d - trial_mu_h)
            trial_total_var = trial_var_d + trial_var_h
            trial_d = trial_delta_mu / xp.sqrt(trial_total_var + 1e-10)
            
            if metric == 'auc':
                # Convert to NumPy for norm.cdf if using GPU
                if use_gpu_acc:
                    trial_d_np = float(trial_d.get())  # Convert CuPy scalar to Python float
                else:
                    trial_d_np = float(trial_d)
                trial_metric = norm.cdf(trial_d_np)
                target_value = target_auc
            else:  # youden
                def neg_youden(t, mu_d_k, sigma_d_k, mu_h_k, sigma_h_k):
                    tpr = 1 - norm.cdf((t - mu_d_k) / sigma_d_k)
                    fpr = 1 - norm.cdf((t - mu_h_k) / sigma_h_k)
                    return -(tpr - fpr)
                
                # Convert to Python floats if using GPU
                if use_gpu_acc:
                    mu_d_k = float(trial_mu_d.get())
                    sigma_d_k = np.sqrt(float(trial_var_d.get()))
                    mu_h_k = float(trial_mu_h.get())
                    sigma_h_k = np.sqrt(float(trial_var_h.get()))
                else:
                    mu_d_k = float(trial_mu_d)
                    sigma_d_k = np.sqrt(float(trial_var_d))
                    mu_h_k = float(trial_mu_h)
                    sigma_h_k = np.sqrt(float(trial_var_h))
                
                # Bracket for root finding
                try:
                    res = root_scalar(
                        lambda t: -neg_youden(t, mu_d_k, sigma_d_k, mu_h_k, sigma_h_k),
                        bracket=[mu_h_k - 3*sigma_h_k, mu_d_k + 3*sigma_d_k],
                        method='brentq'
                    )
                    t_opt = res.root
                    trial_metric = -neg_youden(t_opt, mu_d_k, sigma_d_k, mu_h_k, sigma_h_k)
                except ValueError:
                    trial_metric = 0.0  # Fallback if root finding fails
                target_value = target_youden
            
            # If trial subset meets target, update selected
            if trial_metric >= target_value:
                selected = trial
                improved = True
                metric_curve.append((len(selected), float(trial_metric)))
                break  # Restart loop with new subset

    if use_gpu_acc:
        cleanup_gpu_memory()

    return {
        "selected_local_idxs": selected,
        "k": len(selected),
        "metric_curve": metric_curve,
        "gpu_acceleration_used": use_gpu_acc
    }