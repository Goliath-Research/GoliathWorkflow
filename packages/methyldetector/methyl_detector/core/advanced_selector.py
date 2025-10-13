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


@dataclass
class OptimizationResult:
    """Result of advanced optimization algorithm."""
    selected_indices: List[int]
    k: int
    final_performance: float
    algorithm: str
    optimal: bool
    iterations: int
    time_elapsed: float
    objective_value: float
    metadata: Dict[str, Any]


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

    # Clip extreme values to prevent overflow during summation
    # Beta LLR moments can become very large with extreme parameters
    max_reasonable_value = 1e10  # Reasonable upper bound for moments
    mu_d = xp.clip(mu_d, -max_reasonable_value, max_reasonable_value)
    var_d = xp.clip(var_d, 1e-10, max_reasonable_value)  # Variance must be positive
    mu_h = xp.clip(mu_h, -max_reasonable_value, max_reasonable_value)
    var_h = xp.clip(var_h, 1e-10, max_reasonable_value)

    # Combine moments using numerically stable summation
    combined_mu_d = xp.sum(mu_d)
    combined_var_d = xp.sum(var_d)
    combined_mu_h = xp.sum(mu_h)
    combined_var_h = xp.sum(var_h)

    # Additional overflow protection for the combined values
    combined_mu_d = xp.clip(combined_mu_d, -max_reasonable_value, max_reasonable_value)
    combined_var_d = xp.maximum(combined_var_d, 1e-10)
    combined_mu_h = xp.clip(combined_mu_h, -max_reasonable_value, max_reasonable_value)
    combined_var_h = xp.maximum(combined_var_h, 1e-10)
    
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


def select_subset_simulated_annealing(
    filtered_results: List[DMPFilterResult],
    target_auc: float = 0.95,
    metric: str = 'auc',
    target_youden: float = 0.9,
    initial_temp: float = 100.0,
    final_temp: float = 0.01,
    cooling_rate: float = 0.95,
    max_iterations: int = 10000,
    use_gpu: bool = True
) -> OptimizationResult:
    """
    Select minimal DMP subset using Simulated Annealing.
    
    This algorithm probabilistically explores the solution space, accepting
    worse solutions with decreasing probability to escape local optima.
    
    Args:
        filtered_results: List of DMP results sorted by ranking
        target_auc: Target AUC threshold (if metric='auc')
        metric: Performance metric ('auc' or 'youden')
        target_youden: Target Youden's J threshold (if metric='youden')
        initial_temp: Starting temperature
        final_temp: Ending temperature
        cooling_rate: Temperature reduction factor
        max_iterations: Maximum number of iterations
        use_gpu: Whether to use GPU acceleration
    
    Returns:
        OptimizationResult with selected DMP subset
    """
    start_time = time.time()
    n_dmps = len(filtered_results)
    target_value = target_auc if metric == 'auc' else target_youden
    
    logger.info(f"Starting Simulated Annealing optimization for {n_dmps} DMPs")
    logger.info(f"Target {metric}: {target_value:.3f}")
    
    def objective_function(selected_indices: List[int]) -> float:
        """Objective to minimize: penalized subset size."""
        if len(selected_indices) == 0:
            return float('inf')
        
        performance = compute_subset_performance(
            selected_indices, filtered_results, use_gpu, metric
        )
        
        if performance >= target_value:
            # Feasible solution: minimize size
            return len(selected_indices)
        else:
            # Infeasible solution: heavy penalty
            penalty = 1000 * (target_value - performance) ** 2
            return len(selected_indices) + penalty
    
    def get_random_neighbor(current_solution: List[int]) -> List[int]:
        """Generate a random neighbor solution."""
        current_set = set(current_solution)
        operation = np.random.choice(['add', 'remove', 'swap'], p=[0.4, 0.3, 0.3])
        
        if operation == 'add' and len(current_solution) < n_dmps:
            # Add a random DMP not in current solution
            available = [i for i in range(n_dmps) if i not in current_set]
            if available:
                new_dmp = np.random.choice(available)
                return sorted(current_solution + [new_dmp])
        
        elif operation == 'remove' and len(current_solution) > 1:
            # Remove a random DMP from current solution
            to_remove = np.random.choice(current_solution)
            return [i for i in current_solution if i != to_remove]
        
        elif operation == 'swap' and len(current_solution) > 0:
            # Replace one DMP with another
            available = [i for i in range(n_dmps) if i not in current_set]
            if available and current_solution:
                to_remove = np.random.choice(current_solution)
                to_add = np.random.choice(available)
                new_solution = [i if i != to_remove else to_add for i in current_solution]
                return sorted(new_solution)
        
        # Fallback: return current solution
        return current_solution
    
    # Initialize with greedy solution (first k DMPs until target is met)
    current_solution = []
    for i in range(min(50, n_dmps)):  # Limit initial search
        test_solution = list(range(i + 1))
        performance = compute_subset_performance(
            test_solution, filtered_results, use_gpu, metric
        )
        if performance >= target_value:
            current_solution = test_solution
            break
    
    # If no feasible solution found, start with top 10 DMPs
    if not current_solution:
        current_solution = list(range(min(10, n_dmps)))
    
    current_cost = objective_function(current_solution)
    best_solution = current_solution.copy()
    best_cost = current_cost
    
    temperature = initial_temp
    iteration = 0
    accepted_moves = 0
    rejected_moves = 0
    
    logger.info(f"Initial solution: k={len(current_solution)}, cost={current_cost:.3f}")
    
    # Simulated Annealing main loop
    while iteration < max_iterations and temperature > final_temp:
        # Generate neighbor
        new_solution = get_random_neighbor(current_solution)
        new_cost = objective_function(new_solution)
        
        # Acceptance criterion
        accept = False
        if new_cost < current_cost:
            # Always accept improvements
            accept = True
            accepted_moves += 1
        else:
            # Accept worse solutions with probability
            delta = new_cost - current_cost
            probability = np.exp(-delta / temperature)
            
            if np.random.random() < probability:
                accept = True
                accepted_moves += 1
            else:
                rejected_moves += 1
        
        if accept:
            current_solution = new_solution
            current_cost = new_cost
            
            # Update best solution
            if new_cost < best_cost:
                best_solution = new_solution.copy()
                best_cost = new_cost
                
                if iteration % 1000 == 0:
                    perf = compute_subset_performance(
                        best_solution, filtered_results, use_gpu, metric
                    )
                    logger.info(
                        f"Iteration {iteration}: k={len(best_solution)}, "
                        f"{metric}={perf:.3f}, temp={temperature:.3f}"
                    )
        
        # Cool down
        temperature *= cooling_rate
        iteration += 1
        
        # Early stopping if very good solution found
        if best_cost <= len(best_solution) and best_cost < 10:
            logger.info(f"Early stopping: excellent solution found at iteration {iteration}")
            break
    
    end_time = time.time()
    final_performance = compute_subset_performance(
        best_solution, filtered_results, use_gpu, metric
    )
    
    logger.info("Simulated Annealing completed:")
    logger.info(f"  Iterations: {iteration}")
    logger.info(f"  Final solution: k={len(best_solution)}")
    logger.info(f"  Final {metric}: {final_performance:.3f}")
    logger.info(f"  Time elapsed: {end_time - start_time:.2f}s")
    logger.info(f"  Accepted moves: {accepted_moves}")
    logger.info(f"  Rejected moves: {rejected_moves}")
    
    return OptimizationResult(
        selected_indices=best_solution,
        k=len(best_solution),
        final_performance=final_performance,
        algorithm="simulated_annealing",
        optimal=False,  # Heuristic algorithm
        iterations=iteration,
        time_elapsed=end_time - start_time,
        objective_value=best_cost,
        metadata={
            "initial_temp": initial_temp,
            "final_temp": temperature,
            "cooling_rate": cooling_rate,
            "accepted_moves": accepted_moves,
            "rejected_moves": rejected_moves,
            "acceptance_rate": accepted_moves / (accepted_moves + rejected_moves) if (accepted_moves + rejected_moves) > 0 else 0.0
        }
    )


def select_subset_hierarchical_clustering(
    filtered_results: List[DMPFilterResult],
    target_auc: float = 0.95,
    metric: str = 'auc',
    target_youden: float = 0.9,
    cluster_threshold: float = 0.1,
    use_gpu: bool = True
) -> OptimizationResult:
    """
    Select minimal DMP subset using hierarchical clustering approach.
    
    This algorithm groups similar DMPs and selects representatives from each cluster,
    dramatically reducing the search space for large-scale problems.
    
    Args:
        filtered_results: List of DMP results sorted by ranking
        target_auc: Target AUC threshold
        metric: Performance metric ('auc' or 'youden')
        target_youden: Target Youden's J threshold
        cluster_threshold: Similarity threshold for clustering
        use_gpu: Whether to use GPU acceleration
    
    Returns:
        OptimizationResult with selected DMP subset
    """
    start_time = time.time()
    n_dmps = len(filtered_results)
    target_value = target_auc if metric == 'auc' else target_youden
    
    logger.info(f"Starting Hierarchical Clustering optimization for {n_dmps} DMPs")
    
    # Step 1: Cluster DMPs based on similarity
    clusters = cluster_dmps_by_similarity(filtered_results, cluster_threshold, use_gpu)
    logger.info(f"Created {len(clusters)} clusters from {n_dmps} DMPs")
    
    # Step 2: Select best representative from each cluster
    cluster_representatives = []
    for cluster in clusters:
        # Select DMP with highest composite weight in cluster
        best_idx = max(cluster, key=lambda i: filtered_results[i].w if hasattr(filtered_results[i], 'w') else 1.0)
        cluster_representatives.append(best_idx)
    
    # Step 3: Greedy selection on representatives (much smaller search space)
    current_selection = []
    sorted_representatives = sorted(cluster_representatives, 
                                 key=lambda i: filtered_results[i].w if hasattr(filtered_results[i], 'w') else 1.0, 
                                 reverse=True)
    
    for rep_idx in sorted_representatives:
        test_selection = current_selection + [rep_idx]
        performance = compute_subset_performance(test_selection, filtered_results, use_gpu, metric)
        
        if performance >= target_value:
            current_selection = test_selection
            break
        else:
            current_selection = test_selection
    
    # Step 4: Local optimization within selected clusters
    final_selection = []
    for cluster_rep in current_selection:
        # Find which cluster this representative belongs to
        rep_cluster = next(cluster for cluster in clusters if cluster_rep in cluster)
        
        # Try all DMPs in this cluster to find the best one
        best_local = cluster_rep
        best_performance = 0.0
        
        for candidate in rep_cluster:
            test_selection = [idx if idx != cluster_rep else candidate for idx in current_selection]
            performance = compute_subset_performance(test_selection, filtered_results, use_gpu, metric)
            
            if performance > best_performance:
                best_performance = performance
                best_local = candidate
        
        final_selection.append(best_local)
    
    # Final performance check
    final_performance = compute_subset_performance(final_selection, filtered_results, use_gpu, metric)
    
    end_time = time.time()
    
    logger.info("Hierarchical Clustering completed:")
    logger.info(f"  Clusters created: {len(clusters)}")
    logger.info(f"  Final solution: k={len(final_selection)}")
    logger.info(f"  Final {metric}: {final_performance:.3f}")
    logger.info(f"  Time elapsed: {end_time - start_time:.2f}s")
    
    return OptimizationResult(
        selected_indices=final_selection,
        k=len(final_selection),
        final_performance=final_performance,
        algorithm="hierarchical_clustering",
        optimal=False,
        iterations=len(clusters),
        time_elapsed=end_time - start_time,
        objective_value=len(final_selection),
        metadata={
            "n_clusters": len(clusters),
            "cluster_threshold": cluster_threshold,
            "reduction_ratio": len(clusters) / n_dmps
        }
    )


def cluster_dmps_by_similarity(
    filtered_results: List[DMPFilterResult],
    threshold: float = 0.1,
    use_gpu: bool = True
) -> List[List[int]]:
    """
    Cluster DMPs based on Beta distribution similarity.
    
    Args:
        filtered_results: List of DMP results
        threshold: Similarity threshold for clustering
        use_gpu: Whether to use GPU acceleration
    
    Returns:
        List of clusters, where each cluster is a list of DMP indices
    """
    n_dmps = len(filtered_results)
    xp = cp if use_gpu and GPU_AVAILABLE else np
    
    # Extract Beta parameters
    alpha1 = xp.array([r.alpha1 for r in filtered_results])
    beta1 = xp.array([r.beta1 for r in filtered_results])
    alpha2 = xp.array([r.alpha2 for r in filtered_results])
    beta2 = xp.array([r.beta2 for r in filtered_results])
    
    # Compute pairwise similarities using Jeffreys divergence
    clusters = []
    unclustered = set(range(n_dmps))
    
    while unclustered:
        # Start new cluster with first unclustered DMP
        seed = min(unclustered)
        current_cluster = [seed]
        unclustered.remove(seed)
        
        # Find similar DMPs
        to_check = list(unclustered)
        for candidate in to_check:
            # Compute similarity between seed and candidate
            jd1 = compute_jeffreys_divergence_single(
                alpha1[seed], beta1[seed], alpha1[candidate], beta1[candidate], use_gpu
            )
            jd2 = compute_jeffreys_divergence_single(
                alpha2[seed], beta2[seed], alpha2[candidate], beta2[candidate], use_gpu
            )
            
            # Average divergence between both groups
            avg_divergence = (jd1 + jd2) / 2
            
            if avg_divergence < threshold:
                current_cluster.append(candidate)
                unclustered.remove(candidate)
        
        clusters.append(current_cluster)
    
    return clusters


def compute_jeffreys_divergence_single(a1: float, b1: float, a2: float, b2: float, use_gpu: bool = False) -> float:
    """Compute Jeffreys divergence between two Beta distributions."""
    try:
        from methyl_utils.metrics_core import compute_jeffreys_divergence
        # Use vectorized version with single elements
        result = compute_jeffreys_divergence(
            np.array([a1]), np.array([b1]), np.array([a2]), np.array([b2]), use_gpu
        )
        return float(result[0])
    except:
        # Fallback to basic calculation
        from scipy.special import betaln, digamma
        
        kl1 = (betaln(a2, b2) - betaln(a1, b1) + 
               (a1 - a2) * digamma(a1) + (b1 - b2) * digamma(b1) - 
               (a1 + b1 - a2 - b2) * digamma(a1 + b1))
        
        kl2 = (betaln(a1, b1) - betaln(a2, b2) + 
               (a2 - a1) * digamma(a2) + (b2 - b1) * digamma(b2) - 
               (a2 + b2 - a1 - b1) * digamma(a2 + b2))
        
        return float(kl1 + kl2)


def select_subset_fast_greedy_plus(
    filtered_results: List[DMPFilterResult],
    target_auc: float = 0.95,
    metric: str = 'auc',
    target_youden: float = 0.9,
    use_gpu: bool = True,
    local_search_iterations: int = 100
) -> OptimizationResult:
    """
    Fast greedy algorithm with local search optimization for large-scale problems.
    
    Designed for thousands to tens of thousands of DMPs with O(n log n) complexity.
    
    Args:
        filtered_results: List of DMP results sorted by ranking
        target_auc: Target AUC threshold
        metric: Performance metric ('auc' or 'youden')
        target_youden: Target Youden's J threshold
        use_gpu: Whether to use GPU acceleration
        local_search_iterations: Number of local search iterations
    
    Returns:
        OptimizationResult with selected DMP subset
    """
    start_time = time.time()
    n_dmps = len(filtered_results)
    target_value = target_auc if metric == 'auc' else target_youden
    
    logger.info(f"Starting Fast Greedy+ optimization for {n_dmps} DMPs")
    
    # Phase 1: Smart initialization using binary search
    logger.info("Phase 1: Binary search initialization")
    
    # Binary search to find approximate minimal size
    left, right = 1, min(1000, n_dmps)  # Cap at 1000 DMPs for efficiency
    best_k = right
    
    while left <= right:
        mid = (left + right) // 2
        test_indices = list(range(mid))  # Top mid DMPs
        performance = compute_subset_performance(test_indices, filtered_results, use_gpu, metric)
        
        if performance >= target_value:
            best_k = mid
            right = mid - 1
        else:
            left = mid + 1
    
    # Start with binary search result
    current_solution = list(range(best_k))
    current_performance = compute_subset_performance(current_solution, filtered_results, use_gpu, metric)
    
    logger.info(f"Binary search result: k={best_k}, {metric}={current_performance:.3f}")
    
    # Phase 2: Fast local search with strategic moves
    logger.info("Phase 2: Strategic local search")
    
    best_solution = current_solution.copy()
    best_size = len(best_solution)
    
    # Pre-compute individual DMP contributions for efficiency
    individual_scores = []
    for i in range(n_dmps):
        if i < len(current_solution):
            # Already selected
            individual_scores.append(float('inf'))
        else:
            # Test adding this DMP
            test_selection = current_solution + [i]
            perf = compute_subset_performance(test_selection, filtered_results, use_gpu, metric)
            contribution = perf - current_performance
            individual_scores.append(contribution)
    
    # Strategic local search
    for iteration in range(local_search_iterations):
        improved = False
        
        # Strategy 1: Try swapping out low-performing DMPs
        if len(current_solution) > 1:
            # Find the least contributing DMP in current solution
            removal_candidates = []
            for i, idx in enumerate(current_solution):
                test_solution = [current_solution[j] for j in range(len(current_solution)) if j != i]
                if len(test_solution) > 0:
                    test_perf = compute_subset_performance(test_solution, filtered_results, use_gpu, metric)
                    performance_loss = current_performance - test_perf
                    removal_candidates.append((idx, performance_loss, test_solution))
            
            # Try removing DMPs with minimal performance impact
            removal_candidates.sort(key=lambda x: x[1])  # Sort by performance loss
            
            for removed_idx, loss, reduced_solution in removal_candidates[:3]:  # Try top 3
                if len(reduced_solution) < best_size:
                    reduced_perf = compute_subset_performance(reduced_solution, filtered_results, use_gpu, metric)
                    
                    if reduced_perf >= target_value:
                        current_solution = reduced_solution
                        current_performance = reduced_perf
                        best_solution = reduced_solution.copy()
                        best_size = len(best_solution)
                        improved = True
                        logger.info(f"Removed DMP {removed_idx}: k={len(current_solution)}, {metric}={current_performance:.3f}")
                        break
        
        # Strategy 2: Try beneficial swaps
        if not improved and len(current_solution) < n_dmps:
            # Find best candidates to add
            current_set = set(current_solution)
            candidates = [(i, score) for i, score in enumerate(individual_scores) 
                         if i not in current_set and score != float('inf')]
            candidates.sort(key=lambda x: x[1], reverse=True)
            
            # Try swapping with best candidates
            for add_idx, add_score in candidates[:10]:  # Try top 10 candidates
                for remove_idx in current_solution:
                    swap_solution = [idx if idx != remove_idx else add_idx for idx in current_solution]
                    swap_perf = compute_subset_performance(swap_solution, filtered_results, use_gpu, metric)
                    
                    if swap_perf >= target_value and len(swap_solution) <= best_size:
                        current_solution = swap_solution
                        current_performance = swap_perf
                        if len(swap_solution) < best_size:
                            best_solution = swap_solution.copy()
                            best_size = len(best_solution)
                        improved = True
                        logger.info(f"Swapped {remove_idx}→{add_idx}: k={len(current_solution)}, {metric}={current_performance:.3f}")
                        break
                
                if improved:
                    break
        
        if not improved:
            break
    
    end_time = time.time()
    final_performance = compute_subset_performance(best_solution, filtered_results, use_gpu, metric)
    
    logger.info("Fast Greedy+ completed:")
    logger.info(f"  Iterations: {iteration + 1}")
    logger.info(f"  Final solution: k={len(best_solution)}")
    logger.info(f"  Final {metric}: {final_performance:.3f}")
    logger.info(f"  Time elapsed: {end_time - start_time:.2f}s")
    
    return OptimizationResult(
        selected_indices=best_solution,
        k=len(best_solution),
        final_performance=final_performance,
        algorithm="fast_greedy_plus",
        optimal=False,
        iterations=iteration + 1,
        time_elapsed=end_time - start_time,
        objective_value=len(best_solution),
        metadata={
            "binary_search_k": best_k,
            "local_search_iterations": iteration + 1
        }
    )


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


def select_subset_divide_and_conquer(
    filtered_results: List[DMPFilterResult],
    target_auc: float = 0.95,
    metric: str = 'auc',
    target_youden: float = 0.9,
    chunk_size: int = 1000,
    use_gpu: bool = True
) -> OptimizationResult:
    """
    Divide-and-conquer approach for very large DMP sets (10K+ DMPs).
    
    Divides the problem into manageable chunks, optimizes each chunk,
    then combines and refines the results.
    
    Args:
        filtered_results: List of DMP results sorted by ranking
        target_auc: Target AUC threshold
        metric: Performance metric ('auc' or 'youden')
        target_youden: Target Youden's J threshold
        chunk_size: Size of each chunk for processing
        use_gpu: Whether to use GPU acceleration
    
    Returns:
        OptimizationResult with selected DMP subset
    """
    start_time = time.time()
    n_dmps = len(filtered_results)
    target_value = target_auc if metric == 'auc' else target_youden
    
    logger.info(f"Starting Divide-and-Conquer optimization for {n_dmps} DMPs")
    logger.info(f"Using chunk size: {chunk_size}")
    
    # Phase 1: Divide into chunks and optimize each
    chunks = []
    chunk_solutions = []
    
    for i in range(0, n_dmps, chunk_size):
        chunk = filtered_results[i:i + chunk_size]
        chunks.append(chunk)
        
        # Optimize this chunk using fast greedy
        chunk_result = select_subset_fast_greedy_plus(
            chunk, target_auc=target_value, metric=metric, 
            target_youden=target_youden, use_gpu=use_gpu,
            local_search_iterations=50
        )
        
        # Convert local indices to global indices
        global_indices = [i + idx for idx in chunk_result.selected_indices]
        chunk_solutions.append(global_indices)
        
        logger.info(f"Chunk {len(chunk_solutions)}: {len(chunk)} → {len(global_indices)} DMPs")
    
    # Phase 2: Combine chunk solutions
    logger.info("Phase 2: Combining chunk solutions")
    
    combined_solution = []
    for chunk_sol in chunk_solutions:
        combined_solution.extend(chunk_sol)
    
    # Remove duplicates and sort
    combined_solution = sorted(list(set(combined_solution)))
    
    # Phase 3: Global refinement
    logger.info("Phase 3: Global refinement")
    
    # Check if combined solution meets target
    combined_performance = compute_subset_performance(combined_solution, filtered_results, use_gpu, metric)
    
    if combined_performance >= target_value:
        # Try to reduce the combined solution
        final_solution = combined_solution.copy()
        
        # Iteratively remove least important DMPs
        while len(final_solution) > 1:
            removal_candidates = []
            
            for i, dmp_idx in enumerate(final_solution):
                test_solution = [final_solution[j] for j in range(len(final_solution)) if j != i]
                test_perf = compute_subset_performance(test_solution, filtered_results, use_gpu, metric)
                
                if test_perf >= target_value:
                    removal_candidates.append((dmp_idx, test_perf, test_solution))
            
            if removal_candidates:
                # Remove the DMP with best remaining performance
                best_removal = max(removal_candidates, key=lambda x: x[1])
                final_solution = best_removal[2]
                logger.info(f"Removed DMP {best_removal[0]}: k={len(final_solution)}, {metric}={best_removal[1]:.3f}")
            else:
                break
    else:
        # Combined solution doesn't meet target, need to add more
        final_solution = combined_solution.copy()
        remaining_dmps = [i for i in range(n_dmps) if i not in set(final_solution)]
        
        # Add DMPs until target is met
        for dmp_idx in remaining_dmps:
            test_solution = final_solution + [dmp_idx]
            test_perf = compute_subset_performance(test_solution, filtered_results, use_gpu, metric)
            
            final_solution = test_solution
            if test_perf >= target_value:
                break
    
    end_time = time.time()
    final_performance = compute_subset_performance(final_solution, filtered_results, use_gpu, metric)
    
    logger.info("Divide-and-Conquer completed:")
    logger.info(f"  Chunks processed: {len(chunks)}")
    logger.info(f"  Combined solution size: {len(combined_solution)}")
    logger.info(f"  Final solution: k={len(final_solution)}")
    logger.info(f"  Final {metric}: {final_performance:.3f}")
    logger.info(f"  Time elapsed: {end_time - start_time:.2f}s")
    
    return OptimizationResult(
        selected_indices=final_solution,
        k=len(final_solution),
        final_performance=final_performance,
        algorithm="divide_and_conquer",
        optimal=False,
        iterations=len(chunks),
        time_elapsed=end_time - start_time,
        objective_value=len(final_solution),
        metadata={
            "n_chunks": len(chunks),
            "chunk_size": chunk_size,
            "combined_size": len(combined_solution),
            "reduction_achieved": len(combined_solution) - len(final_solution)
        }
    )


def select_optimal_subset_adaptive(
    filtered_results: List[DMPFilterResult],
    target_auc: float = 0.95,
    metric: str = 'auc',
    target_youden: float = 0.9,
    algorithm: str = 'auto',
    time_budget: int = 60,
    use_gpu: bool = True
) -> Dict[str, Union[List[int], int, float, bool, str, Dict]]:
    """
    Adaptive DMP selection that chooses the best algorithm based on problem size.

    Optimized for genomic-scale problems (thousands to tens of thousands of DMPs).

    Args:
        filtered_results: List of DMP results sorted by ranking
        target_auc: Target AUC threshold
        metric: Performance metric ('auc' or 'youden')
        target_youden: Target Youden's J threshold
        algorithm: Algorithm choice ('auto', 'biological_significance_threshold', 'simulated_annealing',
                  'hierarchical', 'fast_greedy_plus', 'divide_conquer', 'greedy')
        time_budget: Time budget in seconds
        use_gpu: Whether to use GPU acceleration

    Returns:
        Dictionary with optimization results compatible with existing interface
    """
    n_dmps = len(filtered_results)
    
    # Intelligent algorithm selection based on problem scale
    if algorithm == 'auto':
        if n_dmps < 50:
            chosen_algorithm = 'simulated_annealing'
        elif n_dmps < 1000:
            chosen_algorithm = 'hierarchical'
        elif n_dmps < 5000:
            chosen_algorithm = 'fast_greedy_plus'
        else:
            chosen_algorithm = 'divide_conquer'
    else:
        chosen_algorithm = algorithm
    
    logger.info(f"Selected {chosen_algorithm} for {n_dmps} DMPs (time budget: {time_budget}s)")
    
    # Execute chosen algorithm
    if chosen_algorithm == 'biological_significance_threshold':
        result = select_subset_biological_significance_threshold(
            filtered_results=filtered_results,
            target_auc=target_auc,
            metric=metric,
            target_youden=target_youden,
            use_gpu=use_gpu
        )

    elif chosen_algorithm == 'simulated_annealing':
        max_iterations = min(time_budget * 50, n_dmps * 10)
        result = select_subset_simulated_annealing(
            filtered_results=filtered_results,
            target_auc=target_auc,
            metric=metric,
            target_youden=target_youden,
            max_iterations=max_iterations,
            use_gpu=use_gpu
        )

    elif chosen_algorithm == 'hierarchical':
        result = select_subset_hierarchical_clustering(
            filtered_results=filtered_results,
            target_auc=target_auc,
            metric=metric,
            target_youden=target_youden,
            use_gpu=use_gpu
        )

    elif chosen_algorithm == 'fast_greedy_plus':
        result = select_subset_fast_greedy_plus(
            filtered_results=filtered_results,
            target_auc=target_auc,
            metric=metric,
            target_youden=target_youden,
            use_gpu=use_gpu,
            local_search_iterations=min(100, time_budget * 2)
        )

    elif chosen_algorithm == 'divide_conquer':
        # Adaptive chunk size based on problem size
        chunk_size = max(500, min(2000, n_dmps // 10))
        result = select_subset_divide_and_conquer(
            filtered_results=filtered_results,
            target_auc=target_auc,
            metric=metric,
            target_youden=target_youden,
            chunk_size=chunk_size,
            use_gpu=use_gpu
        )

    else:
        # Fallback to existing greedy algorithm
        from .dmp_selector import select_min_subset_analytic

        return select_min_subset_analytic(
            filtered_results=filtered_results,
            target_auc=target_auc,
            use_gpu=use_gpu,
            metric=metric,
            target_youden=target_youden
        )
    
    # Convert to compatible format
    return {
        "selected_local_idxs": result.selected_indices,
        "k": result.k,
        "metric_curve": [(result.k, result.final_performance)],
        "gpu_acceleration_used": use_gpu and GPU_AVAILABLE,
        "algorithm": result.algorithm,
        "optimal": result.optimal,
        "time_elapsed": result.time_elapsed,
        "final_performance": result.final_performance,
        "metadata": result.metadata
    }


# Backward compatibility alias
select_min_subset_advanced = select_optimal_subset_adaptive


__all__ = [
    'OptimizationResult',
    'compute_subset_performance',
    'select_subset_simulated_annealing',
    'select_subset_biological_significance_threshold',
    'select_optimal_subset_adaptive',
    'select_min_subset_advanced'
]
