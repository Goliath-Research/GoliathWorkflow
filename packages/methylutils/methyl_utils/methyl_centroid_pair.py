"""
MethylCentroidPair: Mathematical Comparison of Two Methylation Centroids

This module provides the core mathematical operations for comparing two methylation
centroids. It encapsulates the statistical analysis logic that can be reused for:

1. DMP detection (MethylDetector)
2. Multi-centroid classification (MethylCentroids)
3. Clustering analysis (MethylCluster)
4. Differential methylation analysis

The class provides a clean API for centroid-to-centroid comparisons while leveraging
the full power of MethylUtils for GPU acceleration and statistical computations.

Author: MethylDetector Team
Version: 1.0.0
"""

import logging
from typing import Optional, Tuple, Dict, Any, List, Union
from pathlib import Path

import numpy as np
import pandas as pd

# Import from MethylUtils with comprehensive integration
from methyl_utils import (
    # MethylSample class
    MethylSample,
    # Statistical functions
    likelihood_ratio_test_beta,
    beta_mle_estimation,
    compute_bhattacharyya_distance,
    # GPU detection functions
    is_gpu_available,
    get_cupy,
    get_gpu_memory_gb,
    get_gpu_device_count,
    print_gpu_status,
    cleanup_gpu_memory,
    # Memory management
    get_memory_manager,
    force_gpu_cleanup,
    # Performance profiling
    get_performance_profiler,
    start_performance_monitoring,
    stop_performance_monitoring,
    # Validation functions
    validate_methylation_data,
    validate_sample_data
)
from methyl_utils.logging_utils import setup_module_logging

logger = setup_module_logging(__name__)

# Type aliases for better type hints
ArrayLike = Union[np.ndarray, 'cp.ndarray'] if 'cp' in globals() else np.ndarray
DataFrameType = Union[pd.DataFrame, Any]  # Any for cuDF when available


# Constants
BD_CAP = 20.0  # Cap Bhattacharyya Distance to prevent overflow when converting to BC (exp(-20) ≈ 0)

# Simplified dtype for centroid comparison results
# Only essential columns - MethylDetector will compute biological importance
CENTROID_COMPARISON_DTYPE = np.dtype([
    ('position', np.uint32),
    ('p_value', np.float32),
    ('q_value', np.float32),
    ('alpha1', np.float64),
    ('beta1', np.float64),
    ('alpha2', np.float64),
    ('beta2', np.float64),
    ('mean1', np.float32),
    ('mean2', np.float32),
    ('delta_mean', np.float32),
    ('bhattacharyya', np.float32),  # Bhattacharyya Distance (will be converted to BC by MethylDetector)
])


class MethylCentroidPair:
    """
    Simplified mathematical comparison engine for two methylation centroids.

    This class encapsulates the core statistical operations needed to compare
    two methylation centroids and identify differentially methylated positions (DMPs).
    It provides essential metrics that MethylDetector uses for DMP filtering and ranking.

    Key features:
    - Statistical DMP detection using likelihood ratio tests  
    - Beta parameter estimation (MLE)
    - Bhattacharyya Distance computation
    - FDR correction (Benjamini-Hochberg)
    - GPU acceleration support via MethylUtils
    - Memory-efficient batch processing
    - Always returns pandas DataFrame
    
    Note: Biological importance and weights are computed by MethylDetector,
    not here. This keeps the separation of concerns clean.
    """

    def __init__(self, min_coverage: int = 4):
        """
        Initialize MethylCentroidPair with minimal configuration.

        Args:
            min_coverage: Minimum coverage threshold for filtering positions (default: 4)
        """
        self.min_coverage = min_coverage

        # Initialize GPU backend
        self.gpu_available = is_gpu_available()
        self.gpu_memory_gb = get_gpu_memory_gb() if self.gpu_available else 0.0
        self.gpu_device_count = get_gpu_device_count() if self.gpu_available else 0

        # Initialize array backend
        if self.gpu_available:
            try:
                import cupy as cp
                self.cp = cp
                self.xp = cp
                self.to_cpu = cp.asnumpy
                logger.info(f"GPU backend initialized: {self.gpu_device_count} device(s), {self.gpu_memory_gb:.1f}GB memory")
            except ImportError:
                self.gpu_available = False
                self._init_cpu_backend()
        else:
            self._init_cpu_backend()

        # Initialize utilities
        self.memory_manager = get_memory_manager()
        self.performance_profiler = get_performance_profiler()

    @classmethod
    def load_and_align(cls, path1: Union[str, Path], path2: Union[str, Path], min_coverage: int = 4) -> Tuple[MethylSample, MethylSample, np.ndarray]:
        """
        Load two centroids from paths, align on common positions, and return aligned MethylSamples.

        Handles validation, zero-coverage clamping, and efficient indexing using native numpy.

        Args:
            path1, path2: Paths to HDF5 centroid files.
            min_coverage: Minimum coverage threshold for validation (default: 4)

        Returns:
            (centroid1: MethylSample, centroid2: MethylSample, common_pos: np.ndarray)
        """
        # Load via MethylSample (native HDF5 parsing)
        centroid1 = MethylSample.load_from_h5(path1)
        centroid2 = MethylSample.load_from_h5(path2)

        # Validate extended centroids (assume is_extended_centroid checks N, Sx, etc.)
        if not centroid1.is_extended_centroid or not centroid2.is_extended_centroid:
            raise ValueError("Both inputs must be extended centroids with N, Sx, Sx2, log sums.")

        # Assume positions are sorted (typical for genomic data); if not, sort them
        if not np.all(np.diff(centroid1.pos) > 0):
            logger.warning("Centroid1 positions not sorted; sorting for alignment.")
            sort_idx1 = np.argsort(centroid1.pos)
            centroid1 = cls._slice_sample(centroid1, sort_idx1)
        if not np.all(np.diff(centroid2.pos) > 0):
            logger.warning("Centroid2 positions not sorted; sorting for alignment.")
            sort_idx2 = np.argsort(centroid2.pos)
            centroid2 = cls._slice_sample(centroid2, sort_idx2)

        # Find common positions efficiently (numpy intersection)
        common_pos = np.intersect1d(centroid1.pos, centroid2.pos, assume_unique=True)

        if len(common_pos) == 0:
            raise ValueError("No common positions between centroids.")

        # Fast index lookup with np.searchsorted (O(log n) per query, O(n log n) total)
        idx1 = np.searchsorted(centroid1.pos, common_pos, side='left')
        idx2 = np.searchsorted(centroid2.pos, common_pos, side='left')

        # Verify exact matches (positions must be unique and sorted)
        if not np.all(centroid1.pos[idx1] == common_pos) or not np.all(centroid2.pos[idx2] == common_pos):
            raise ValueError("Position mismatch during alignment; duplicates or unsorted positions?")

        # Slice using apply_mask (native method in MethylSample)
        aligned1 = centroid1.apply_mask(idx1)
        aligned2 = centroid2.apply_mask(idx2)

        # Clamp zero-coverage in-place (efficient masking)
        for cent in [aligned1, aligned2]:
            zero_mask = (cent.mC + cent.uC) == 0
            if np.any(zero_mask):
                cent.uC[zero_mask] = 1  # Ensure mean=0, avoid div-by-zero in comparisons
                logger.debug(f"Clamped {np.sum(zero_mask)} zero-coverage positions in centroid")

        # Validate min_coverage post-alignment
        max_n = max(
            aligned1.N.max() if aligned1.N is not None else 0,
            aligned2.N.max() if aligned2.N is not None else 0
        )
        if max_n < min_coverage:
            logger.warning(f"Max coverage {max_n} < min_coverage {min_coverage}; proceeding with warning.")

        return aligned1, aligned2, common_pos

    def _init_cpu_backend(self):
        """Initialize CPU backend."""
        self.cp = None
        self.xp = np
        self.to_cpu = lambda a: a
        logger.info("CPU backend initialized")

    def compare_centroids(
        self, 
        centroid1: MethylSample, 
        centroid2: MethylSample
    ) -> pd.DataFrame:
        """
        Compare two centroids and return statistical results as DataFrame.

        This is the main entry point for centroid comparison. It performs:
        1. Input validation
        2. Position alignment
        3. Statistical testing (LRT)
        4. Parameter estimation (Beta MLE)
        5. Bhattacharyya Distance computation
        6. FDR correction

        Note: biological_importance is NOT computed here - MethylDetector
        will compute it as delta_mean / (BC + eps) where BC = exp(-BD)

        Args:
            centroid1: First methylation centroid (extended centroid required)
            centroid2: Second methylation centroid (extended centroid required)

        Returns:
            pandas DataFrame with columns: position, p_value, q_value,
            alpha1, beta1, alpha2, beta2, mean1, mean2, delta_mean, bhattacharyya

        Raises:
            ValueError: If centroids are not extended centroids or validation fails
        """
        start_performance_monitoring()

        try:
            # Validate inputs
            self._validate_centroids(centroid1, centroid2)

            # Align centroids (find common positions)
            common_positions = self._align_centroids(centroid1, centroid2)

            if len(common_positions) == 0:
                logger.warning("No common positions found between centroids")
                return pd.DataFrame()  # Empty DataFrame

            logger.info(f"Comparing centroids at {len(common_positions)} common positions")

            # Perform statistical analysis (LRT, parameter estimation, Bhattacharyya Distance)
            results_array = self._compute_statistics(centroid1, centroid2, common_positions)

            # Apply FDR correction
            results_array = self._apply_fdr_correction(results_array)

            # Compute Bhattacharyya Distance
            results_array = self._compute_bhattacharyya(results_array)

            logger.info(f"Comparison complete: {len(results_array)} positions analyzed")

            # Always return as DataFrame
            return pd.DataFrame(results_array)

        finally:
            stop_performance_monitoring()

    def _validate_centroids(self, centroid1: MethylSample, centroid2: MethylSample) -> None:
        """Validate that centroids are suitable for comparison."""
        if not (centroid1.is_extended_centroid and centroid2.is_extended_centroid):
            raise ValueError(
                "MethylCentroidPair requires extended centroids. "
                f"Centroid1 extended: {centroid1.is_extended_centroid}, "
                f"Centroid2 extended: {centroid2.is_extended_centroid}"
            )

        # Use MethylUtils validation on the methylation proportions
        # MethylSample.mean contains the proper methylation proportions (0-1)
        validate_methylation_data(centroid1.mean, centroid1.N)
        validate_methylation_data(centroid2.mean, centroid2.N)

    def _align_centroids(self, centroid1: MethylSample, centroid2: MethylSample) -> np.ndarray:
        """Find common positions between centroids."""
        # Find intersection of positions
        common_positions = np.intersect1d(centroid1.pos, centroid2.pos)

        # Filter by minimum coverage if centroids have coverage info
        if hasattr(centroid1, 'mC') and hasattr(centroid1, 'uC') and \
           hasattr(centroid2, 'mC') and hasattr(centroid2, 'uC'):

            # Get coverage for common positions
            c1_mask = np.isin(centroid1.pos, common_positions)
            c2_mask = np.isin(centroid2.pos, common_positions)

            c1_coverage = centroid1.mC[c1_mask] + centroid1.uC[c1_mask]
            c2_coverage = centroid2.mC[c2_mask] + centroid2.uC[c2_mask]

            # Filter positions by minimum coverage
            coverage_mask = (c1_coverage + c2_coverage) >= self.min_coverage

            # Get positions that pass coverage filter
            c1_positions = centroid1.pos[c1_mask][coverage_mask]
            common_positions = c1_positions

        return common_positions

    def _compute_statistics(
        self, centroid1: MethylSample, 
        centroid2: MethylSample,
        positions: np.ndarray
    ) -> np.ndarray:
        """Compute statistical tests and parameter estimates for given positions."""

        # Calculate optimal batch size
        batch_size = self.memory_manager.calculate_optimal_chunk_size(
            total_positions=len(positions),
            data_structure="extended_centroid",
            maximize_gpu_usage=self.gpu_available
        )

        if batch_size > len(positions):
            batch_size = len(positions)

        logger.debug(f"Using batch size: {batch_size} positions")

        # Pre-allocate result array
        results_array = np.empty(len(positions), dtype=CENTROID_COMPARISON_DTYPE)

        for i in range(0, len(positions), batch_size):
            batch_positions = positions[i:i + batch_size]
            batch_end = i + len(batch_positions)

            # Extract batch data from centroids and fill results
            self._process_batch(centroid1, centroid2, batch_positions,
                              results_array[i:batch_end])

        return results_array

    def _process_batch(self, centroid1: MethylSample, centroid2: MethylSample,
                      positions: np.ndarray, results_view: np.ndarray) -> None:
        """Process a batch of positions for statistical analysis and fill results array."""

        # Find indices in centroids
        indices1 = np.searchsorted(centroid1.pos, positions)
        indices2 = np.searchsorted(centroid2.pos, positions)

        # Extract data directly as arrays for vectorized operations
        N1 = centroid1.N[indices1].astype(np.float32)
        log_x_sum1 = centroid1.log_x_sum[indices1].astype(np.float32)
        log_1mx_sum1 = centroid1.log_1_minus_x_sum[indices1].astype(np.float32)

        N2 = centroid2.N[indices2].astype(np.float32)
        log_x_sum2 = centroid2.log_x_sum[indices2].astype(np.float32)
        log_1mx_sum2 = centroid2.log_1_minus_x_sum[indices2].astype(np.float32)

        # Estimate Beta parameters using MLE (vectorized)
        alpha1, beta1 = beta_mle_estimation(N1, log_x_sum1, log_1mx_sum1)
        alpha2, beta2 = beta_mle_estimation(N2, log_x_sum2, log_1mx_sum2)

        # Compute means and delta_mean (vectorized)
        mean1 = alpha1 / (alpha1 + beta1)
        mean2 = alpha2 / (alpha2 + beta2)
        delta_mean = np.abs(mean1 - mean2)

        # Create temporary centroid objects for LRT (still needed for current API)
        class TempCentroid:
            def __init__(self, N, log_x_sum, log_1_minus_x_sum, mC, uC):
                self.N = N
                self.log_x_sum = log_x_sum
                self.log_1_minus_x_sum = log_1_minus_x_sum
                self.mC = mC
                self.uC = uC
                self.is_extended_centroid = True
                # Add attributes needed for the z-test
                self.alpha = None  # Will be computed by the z-test function
                self.beta = None   # Will be computed by the z-test function
                self.mean = None   # Will be computed by the z-test function

        centroid1_batch = TempCentroid(
            N=N1, log_x_sum=log_x_sum1, log_1_minus_x_sum=log_1mx_sum1,
            mC=centroid1.mC[indices1], uC=centroid1.uC[indices1]
        )

        centroid2_batch = TempCentroid(
            N=N2, log_x_sum=log_x_sum2, log_1_minus_x_sum=log_1mx_sum2,
            mC=centroid2.mC[indices2], uC=centroid2.uC[indices2]
        )

        # Perform likelihood ratio test
        lrt_result = likelihood_ratio_test_beta(
            centroid1_batch, centroid2_batch, use_gpu=self.gpu_available
        )

        if lrt_result is None:
            logger.warning("LRT returned None, using fallback values")
            p_values = np.ones(len(positions), dtype=np.float32)
        else:
            _, p_values = lrt_result
            p_values = p_values.astype(np.float32)

        # Fill results array directly (vectorized assignment)
        results_view['position'] = positions.astype(np.uint32)
        results_view['p_value'] = p_values
        results_view['q_value'] = p_values  # Will be updated by FDR correction
        results_view['alpha1'] = alpha1.astype(np.float64)
        results_view['beta1'] = beta1.astype(np.float64)
        results_view['alpha2'] = alpha2.astype(np.float64)
        results_view['beta2'] = beta2.astype(np.float64)
        results_view['mean1'] = mean1.astype(np.float32)
        results_view['mean2'] = mean2.astype(np.float32)
        results_view['delta_mean'] = delta_mean.astype(np.float32)
        results_view['bhattacharyya'] = np.zeros(len(positions), dtype=np.float32)  # Will be computed in _compute_bhattacharyya

    def _apply_fdr_correction(self, results_array: np.ndarray) -> np.ndarray:
        """Apply FDR correction to p-values."""
        if len(results_array) == 0:
            return results_array

        # Extract p-values
        p_values = results_array['p_value']

        try:
            # Try to use statsmodels if available
            from statsmodels.stats.multitest import multipletests
            _, q_values, _, _ = multipletests(p_values, alpha=0.05, method='fdr_bh')
        except ImportError:
            # Fallback: Implement Benjamini-Hochberg FDR correction manually
            logger.warning("statsmodels not available, using manual FDR correction")
            q_values = self._benjamini_hochberg_fdr(p_values)

        # Update q-values in place (vectorized)
        results_array['q_value'] = q_values.astype(np.float32)

        return results_array

    def _benjamini_hochberg_fdr(self, p_values: np.ndarray) -> np.ndarray:
        """
        Manual implementation of Benjamini-Hochberg FDR correction.

        Args:
            p_values: Array of p-values to correct

        Returns:
            Array of q-values (FDR-corrected p-values)
        """
        if len(p_values) == 0:
            return np.array([])

        # Sort p-values and get original indices
        sorted_indices = np.argsort(p_values)
        sorted_p = p_values[sorted_indices]
        n = len(sorted_p)

        # Calculate BH q-values
        q_values = np.zeros(n)
        q_values[n-1] = sorted_p[n-1]  # Last value unchanged

        for i in range(n-2, -1, -1):
            q_values[i] = min(q_values[i+1], sorted_p[i] * n / (i+1))

        # Reorder back to original positions
        original_order = np.zeros(n, dtype=int)
        original_order[sorted_indices] = np.arange(n)
        q_values = q_values[original_order]

        return q_values

    def _compute_bhattacharyya(self, results_array: np.ndarray) -> np.ndarray:
        """
        Compute Bhattacharyya Distance for all results (vectorized).
        
        Note: Only computes BD (distance), not BC (coefficient).
        MethylDetector will convert BD to BC using: BC = exp(-BD)
        """
        if len(results_array) == 0:
            return results_array

        # Extract Beta parameters for vectorized computation
        alpha1 = results_array['alpha1'].astype(np.float64)
        beta1 = results_array['beta1'].astype(np.float64)
        alpha2 = results_array['alpha2'].astype(np.float64)
        beta2 = results_array['beta2'].astype(np.float64)

        # Compute Bhattacharyya Distance (vectorized, GPU-accelerated if available)
        bd = compute_bhattacharyya_distance(alpha1, beta1, alpha2, beta2, use_gpu=self.gpu_available)
        
        # Cap to prevent overflow when converting to BC (BC = exp(-BD))
        # exp(-20) ≈ 2e-9 which is effectively 0 (perfect separation)
        bd = np.minimum(bd, BD_CAP)

        # Store Bhattacharyya Distance in results
        results_array['bhattacharyya'] = bd.astype(np.float32)

        return results_array

    def cleanup(self):
        """Clean up resources."""
        if self.gpu_available:
            force_gpu_cleanup()
            cleanup_gpu_memory()
        logger.info("MethylCentroidPair cleanup completed")
