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
    MethylExtendedCentroid,
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
from .core.methyl_frame import MethylExtendedCentroid

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
    - FDR correction (Storey's q-value method)
    - GPU acceleration support via MethylUtils
    - Memory-efficient batch processing
    - Always returns pandas DataFrame
    
    Note: Biological importance and weights are computed by MethylDetector,
    not here. This keeps the separation of concerns clean.
    """

    def __init__(self, centroid1: MethylExtendedCentroid, centroid2: MethylExtendedCentroid):
        self.centroid1 = centroid1
        self.centroid2 = centroid2
        self.common_pos = np.intersect1d(centroid1.pos, centroid2.pos)
        
        if len(self.common_pos) == 0:
            raise ValueError("Centroids have no common positions")

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
        from methyl_utils.core.io import load_from_h5
        centroid1 = load_from_h5(path1)
        centroid2 = load_from_h5(path2)

        # Validate extended centroids (assume is_extended_centroid checks N, Sx, etc.)
        if not centroid1.is_extended_centroid or not centroid2.is_extended_centroid:
            raise ValueError("Both inputs must be extended centroids with N, Sx, Sx2, log sums.")

        # Assume positions are sorted (typical for genomic data); if not, sort them
        pos1_vals = centroid1.pos.values if hasattr(centroid1.pos, 'values') else np.asarray(centroid1.pos)
        pos2_vals = centroid2.pos.values if hasattr(centroid2.pos, 'values') else np.asarray(centroid2.pos)
        if not np.all(np.diff(pos1_vals) > 0):
            logger.warning("Centroid1 positions not sorted; sorting for alignment.")
            sort_idx1 = np.argsort(pos1_vals)
            centroid1 = centroid1.apply_mask(sort_idx1)
            pos1_vals = centroid1.pos.values if hasattr(centroid1.pos, 'values') else np.asarray(centroid1.pos)
        if not np.all(np.diff(pos2_vals) > 0):
            logger.warning("Centroid2 positions not sorted; sorting for alignment.")
            sort_idx2 = np.argsort(pos2_vals)
            centroid2 = centroid2.apply_mask(sort_idx2)
            pos2_vals = centroid2.pos.values if hasattr(centroid2.pos, 'values') else np.asarray(centroid2.pos)

        # Find common positions efficiently (numpy intersection)
        common_pos = np.intersect1d(pos1_vals, pos2_vals, assume_unique=True)

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

    @classmethod
    def load_and_align_from_samples(cls, centroid1: MethylSample, centroid2: MethylSample,
                                   min_coverage: int = 4) -> Tuple[MethylSample, MethylSample, np.ndarray]:
        """
        Align two already-loaded centroids on common positions.

        Args:
            centroid1, centroid2: Already loaded MethylSample objects
            min_coverage: Minimum coverage threshold for validation (default: 4)

        Returns:
            (centroid1: MethylSample, centroid2: MethylSample, common_pos: np.ndarray)
        """
        # Validate extended centroids
        if not centroid1.is_extended_centroid or not centroid2.is_extended_centroid:
            raise ValueError("Both inputs must be extended centroids with N, Sx, Sx2, log sums.")

        # Assume positions are sorted (typical for genomic data); if not, sort them
        pos1_vals = centroid1.pos.values if hasattr(centroid1.pos, 'values') else np.asarray(centroid1.pos)
        pos2_vals = centroid2.pos.values if hasattr(centroid2.pos, 'values') else np.asarray(centroid2.pos)
        if not np.all(np.diff(pos1_vals) > 0):
            logger.warning("Centroid1 positions not sorted; sorting for alignment.")
            sort_idx1 = np.argsort(pos1_vals)
            centroid1 = centroid1.apply_mask(sort_idx1)
            pos1_vals = centroid1.pos.values if hasattr(centroid1.pos, 'values') else np.asarray(centroid1.pos)
        if not np.all(np.diff(pos2_vals) > 0):
            logger.warning("Centroid2 positions not sorted; sorting for alignment.")
            sort_idx2 = np.argsort(pos2_vals)
            centroid2 = centroid2.apply_mask(sort_idx2)
            pos2_vals = centroid2.pos.values if hasattr(centroid2.pos, 'values') else np.asarray(centroid2.pos)

        # Find common positions efficiently (numpy intersection)
        common_pos = np.intersect1d(pos1_vals, pos2_vals, assume_unique=True)

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

    @classmethod
    def create_reference_sample(
        cls,
        positions: np.ndarray,
        context: str = "CG",
        min_coverage: int = 4
    ) -> MethylExtendedCentroid:
        """
        Create an empty extended centroid for use as a reference/alignment template.

        Args:
            positions: Genomic positions to include
            context: Methylation context (CG, CHG, CHH)
            min_coverage: Minimum coverage threshold

        Returns:
            MethylExtendedCentroid with zero-filled data
        """
        from methyl_utils.core.methyl_frame import MethylExtendedCentroid
        import pandas as pd

        n_positions = len(positions)
        # Create dummy tnc values based on context
        context_map = {"CG": 0, "CHG": 1, "CHH": 2}
        tnc_base = context_map.get(context, 0)
        dummy_tnc = np.full(n_positions, tnc_base, dtype=np.uint8)

        df = pd.DataFrame({
            "pos": positions.astype(np.uint32),
            "mC": np.zeros(n_positions, dtype=np.uint32),
            "uC": np.ones(n_positions, dtype=np.uint32) * min_coverage,  # Ensure coverage >= min_coverage
            "tnc": dummy_tnc,
            "N": np.ones(n_positions, dtype=np.uint32),
            "Sx": np.zeros(n_positions, dtype=np.float32),
            "Sx2": np.zeros(n_positions, dtype=np.float32),
            "log_x_sum": np.zeros(n_positions, dtype=np.float32),
            "log_1_minus_x_sum": np.zeros(n_positions, dtype=np.float32),
        })

        return MethylExtendedCentroid(df, metadata={"context": context})

    @classmethod
    def align_samples(
        cls,
        sample1: MethylSample,
        sample2: MethylSample
    ) -> tuple[MethylSample, MethylSample, np.ndarray]:
        """
        Align two samples on common positions.

        Args:
            sample1: First sample
            sample2: Second sample

        Returns:
            Tuple of (aligned_sample1, aligned_sample2, common_positions)
        """
        return cls.load_and_align_from_samples(sample1, sample2)

    @staticmethod
    def ensure_cpu(sample: MethylSample) -> MethylSample:
        """
        Ensure a sample is on CPU (convert from GPU if needed).

        Args:
            sample: Sample that may be on GPU

        Returns:
            CPU version of the sample
        """
        return sample.to_cpu()

    @classmethod
    def extract_methylation_fractions(
        cls,
        sample_paths: List[Union[str, Path]],
        reference_positions: Dict[str, np.ndarray],
        chromosome: str,
        min_coverage: int = 4
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray]]:
        """
        Extract methylation fractions from samples aligned to reference positions.
        
        This method efficiently loads samples, aligns them to reference positions by context,
        and extracts methylation fractions without creating full centroid objects.
        
        Args:
            sample_paths: List of paths to sample HDF5 files or directories
            reference_positions: Dictionary mapping context (CG, CHG, CHH) to position arrays
            chromosome: Chromosome identifier
            min_coverage: Minimum coverage threshold
            
        Returns:
            Tuple of (methylation_fractions_matrix, positions_array, context_indices_dict)
            - methylation_fractions_matrix: (n_samples, n_positions) array with NaN for missing positions
            - positions_array: (n_positions,) array of all reference positions in order
            - context_indices_dict: Dictionary mapping context to index arrays in the full position array
        """
        from methyl_utils.core.io import load_from_h5
        from pathlib import Path
        import numpy as np
        
        # Build ordered position array and position-to-index mapping
        all_positions = []
        position_to_index = {}
        context_indices_dict = {}
        
        for ctx in ["CG", "CHG", "CHH"]:
            if ctx in reference_positions:
                ctx_positions = reference_positions[ctx].astype(np.uint32)
                start_idx = len(all_positions)
                ctx_indices = []
                for pos in ctx_positions:
                    if pos not in position_to_index:
                        position_to_index[pos] = len(all_positions)
                        all_positions.append(pos)
                        ctx_indices.append(position_to_index[pos])
                    else:
                        ctx_indices.append(position_to_index[pos])
                context_indices_dict[ctx] = np.array(ctx_indices, dtype=np.int64)
        
        all_positions = np.array(all_positions, dtype=np.uint32)
        n_positions = len(all_positions)
        n_samples = len(sample_paths)
        
        # Initialize result matrix with NaN
        X = np.full((n_samples, n_positions), np.nan, dtype=np.float32)
        
        # Process each sample
        for i, sample_path in enumerate(sample_paths):
            sample_path = Path(sample_path)
            
            # Process each context
            for ctx in reference_positions.keys():
                ctx_positions = reference_positions[ctx].astype(np.uint32)
                
                # Determine H5 file path
                if sample_path.suffix == '.h5':
                    h5_file = sample_path
                elif sample_path.is_file():
                    h5_file = sample_path
                else:
                    h5_file = sample_path / f"{chromosome}-{ctx}.h5"
                
                if not h5_file.exists():
                    continue
                
                try:
                    # Load sample
                    sample = load_from_h5(h5_file)
                    
                    # Align to reference positions
                    aligned = sample.align_to_positions(ctx_positions)
                    
                    if len(aligned) == 0:
                        continue
                    
                    # Extract methylation fractions efficiently
                    mC_vals = aligned.mC.values if hasattr(aligned.mC, 'values') else np.asarray(aligned.mC)
                    uC_vals = aligned.uC.values if hasattr(aligned.uC, 'values') else np.asarray(aligned.uC)
                    pos_vals = aligned.pos.values if hasattr(aligned.pos, 'values') else np.asarray(aligned.pos)
                    
                    # Calculate methylation fractions
                    total_reads = mC_vals + uC_vals
                    with np.errstate(divide='ignore', invalid='ignore'):
                        meth_fractions = np.where(total_reads >= min_coverage, mC_vals / total_reads, np.nan)
                    
                    # Map to correct indices in result matrix using position lookup
                    for j, pos in enumerate(pos_vals):
                        if pos in position_to_index:
                            idx = position_to_index[pos]
                            X[i, idx] = meth_fractions[j]
                            
                except Exception as e:
                    logger.debug(f"Failed to process {h5_file}: {e}")
                    continue
        
        return X, all_positions, context_indices_dict

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
        pos1_vals = centroid1.pos.values if hasattr(centroid1.pos, 'values') else np.asarray(centroid1.pos)
        pos2_vals = centroid2.pos.values if hasattr(centroid2.pos, 'values') else np.asarray(centroid2.pos)
        common_positions = np.intersect1d(pos1_vals, pos2_vals)

        # Filter by minimum coverage if centroids have coverage info
        if hasattr(centroid1, 'mC') and hasattr(centroid1, 'uC') and \
           hasattr(centroid2, 'mC') and hasattr(centroid2, 'uC'):

            # Get coverage for common positions
            c1_mask = np.isin(pos1_vals, common_positions)
            c2_mask = np.isin(pos2_vals, common_positions)

            mC1_vals = centroid1.mC.values if hasattr(centroid1.mC, 'values') else np.asarray(centroid1.mC)
            uC1_vals = centroid1.uC.values if hasattr(centroid1.uC, 'values') else np.asarray(centroid1.uC)
            mC2_vals = centroid2.mC.values if hasattr(centroid2.mC, 'values') else np.asarray(centroid2.mC)
            uC2_vals = centroid2.uC.values if hasattr(centroid2.uC, 'values') else np.asarray(centroid2.uC)

            c1_coverage = mC1_vals[c1_mask] + uC1_vals[c1_mask]
            c2_coverage = mC2_vals[c2_mask] + uC2_vals[c2_mask]

            # Filter positions by minimum coverage
            coverage_mask = (c1_coverage + c2_coverage) >= self.min_coverage

            # Get positions that pass coverage filter
            c1_positions = pos1_vals[c1_mask][coverage_mask]
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

        # Use pre-computed Beta parameters from centroids (already bounded correctly)
        # These are computed by MethylSample._estimate_beta_params_bounded_extended
        alpha1 = centroid1.alpha[indices1].astype(np.float32)
        beta1 = centroid1.beta[indices1].astype(np.float32)
        alpha2 = centroid2.alpha[indices2].astype(np.float32)
        beta2 = centroid2.beta[indices2].astype(np.float32)

        # Extract other data needed for statistical tests
        N1 = centroid1.N[indices1].astype(np.float32)
        N2 = centroid2.N[indices2].astype(np.float32)
        log_x_sum1 = centroid1.log_x_sum[indices1].astype(np.float32)
        log_1mx_sum1 = centroid1.log_1_minus_x_sum[indices1].astype(np.float32)
        log_x_sum2 = centroid2.log_x_sum[indices2].astype(np.float32)
        log_1mx_sum2 = centroid2.log_1_minus_x_sum[indices2].astype(np.float32)

        # Use MethylSample's encapsulated mean property which includes adaptive estimation
        # This ensures consistency with edge case handling for small samples vs large samples
        mean1 = centroid1.mean[indices1].astype(np.float32)
        mean2 = centroid2.mean[indices2].astype(np.float32)
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
        """Apply FDR correction to p-values using Storey's method."""
        if len(results_array) == 0:
            return results_array

        # Extract p-values
        p_values = results_array['p_value']

        try:
            # Use Storey's two-stage FDR method (adaptive FDR control)
            from statsmodels.stats.multitest import multipletests
            _, q_values, _, _ = multipletests(p_values, alpha=0.05, method='fdr_tsbh')
        except ImportError:
            # Fallback: Implement Storey's method manually
            logger.warning("statsmodels not available, using manual Storey's FDR correction")
            q_values = self._storey_qvalue(p_values)

        # Update q-values in place (vectorized)
        results_array['q_value'] = q_values.astype(np.float32)

        return results_array

    @staticmethod
    def validate_centroid_parameters(centroid1: MethylSample, centroid2: MethylSample,
                                   extreme_threshold: float = 1000) -> dict:
        """
        Validate centroid parameters by comparing alpha/beta against simple statistics.

        This is a utility method that can be used by higher-level components like
        MethylModeler to validate the quality of beta parameter estimation.

        Args:
            centroid1: First centroid to validate
            centroid2: Second centroid to validate
            extreme_threshold: Threshold for detecting extreme beta parameters

        Returns:
            Dictionary with validation results and statistics
        """
        if not centroid1.is_extended_centroid or not centroid2.is_extended_centroid:
            return {"error": "Both centroids must be extended centroids"}

        # Align centroids to common positions for proper comparison
        try:
            centroid1, centroid2, common_pos = MethylCentroidPair.load_and_align_from_samples(centroid1, centroid2)
        except ValueError as e:
            return {"error": f"Failed to align centroids: {e}"}

        # Get Beta parameters using MethylSample's encapsulated methods
        alpha1, beta1 = centroid1.get_beta_parameters()
        alpha2, beta2 = centroid2.get_beta_parameters()

        # Get sample statistics
        N1 = centroid1.N
        Sx1 = centroid1.Sx
        Sx2_1 = centroid1.Sx2

        N2 = centroid2.N
        Sx2 = centroid2.Sx
        Sx2_2 = centroid2.Sx2

        results = {
            "centroid1": {
                "n_positions": len(alpha1),
                "alpha_stats": {"mean": float(alpha1.mean()), "std": float(alpha1.std())},
                "beta_stats": {"mean": float(beta1.mean()), "std": float(beta1.std())},
                "sample_stats": {"min_N": int(N1.min()), "max_N": int(N1.max()), "mean_N": float(N1.mean()), "std_N": float(N1.std())}
            },
            "centroid2": {
                "n_positions": len(alpha2),
                "alpha_stats": {"mean": float(alpha2.mean()), "std": float(alpha2.std())},
                "beta_stats": {"mean": float(beta2.mean()), "std": float(beta2.std())},
                "sample_stats": {"min_N": int(N2.min()), "max_N": int(N2.max()), "mean_N": float(N2.mean()), "std_N": float(N2.std())}
            },
            "validation": {},
            "warnings": []
        }

        # Estimate mean and variance from Sx and Sx2 (assuming Normal) for validation
        valid_positions1 = N1 >= 5  # At least 5 samples for reliable variance estimate
        valid_positions2 = N2 >= 5

        if np.any(valid_positions1):
            N1_valid = N1[valid_positions1]
            Sx1_valid = Sx1[valid_positions1]
            Sx2_1_valid = Sx2_1[valid_positions1]

            normal_mean1 = float(np.median(Sx1_valid / N1_valid))
            normal_var1 = float(np.median((Sx2_1_valid - (Sx1_valid**2)/N1_valid) / (N1_valid - 1)))

            # Use MethylSample's mean and variance properties for Beta comparison
            beta_mean1 = float(centroid1.mean[valid_positions1].mean())
            beta_var1 = float(centroid1.variance[valid_positions1].mean())

            results["validation"]["centroid1"] = {
                "normal_estimate": {"mean": normal_mean1, "var": normal_var1},
                "beta_estimate": {"mean": beta_mean1, "var": beta_var1},
                "mean_difference": abs(normal_mean1 - beta_mean1)
            }

            # Check if estimates are reasonable - only warn for large samples where Beta should be accurate
            mean_N1 = float(N1_valid.mean())
            mean_diff = abs(normal_mean1 - beta_mean1)
            if mean_N1 >= 20 and mean_diff > 0.1:
                results["warnings"].append(f"Centroid1: Large mean difference ({mean_diff:.4f}) between normal and beta estimates (N={mean_N1:.1f})")
            elif mean_N1 < 20 and mean_diff > 0.1:
                logger.debug(f"Centroid1: Expected difference ({mean_diff:.4f}) for small samples (N={mean_N1:.1f} < 20), using normal approximation")

        if np.any(valid_positions2):
            N2_valid = N2[valid_positions2]
            Sx2_valid = Sx2[valid_positions2]
            Sx2_2_valid = Sx2_2[valid_positions2]

            normal_mean2 = float(np.median(Sx2_valid / N2_valid))
            normal_var2 = float(np.median((Sx2_2_valid - (Sx2_valid**2)/N2_valid) / (N2_valid - 1)))

            # Use MethylSample's mean and variance properties for Beta comparison
            beta_mean2 = float(centroid2.mean[valid_positions2].mean())
            beta_var2 = float(centroid2.variance[valid_positions2].mean())

            results["validation"]["centroid2"] = {
                "normal_estimate": {"mean": normal_mean2, "var": normal_var2},
                "beta_estimate": {"mean": beta_mean2, "var": beta_var2},
                "mean_difference": abs(normal_mean2 - beta_mean2)
            }

            # Check if estimates are reasonable - only warn for large samples where Beta should be accurate
            mean_N2 = float(N2_valid.mean())
            mean_diff = abs(normal_mean2 - beta_mean2)
            if mean_N2 >= 20 and mean_diff > 0.1:
                results["warnings"].append(f"Centroid2: Large mean difference ({mean_diff:.4f}) between normal and beta estimates (N={mean_N2:.1f})")
            elif mean_N2 < 20 and mean_diff > 0.1:
                logger.debug(f"Centroid2: Expected difference ({mean_diff:.4f}) for small samples (N={mean_N2:.1f} < 20), using normal approximation")

        # Check for extreme parameters - only warn for large samples where Beta should be stable
        n_extreme1 = int(np.sum((alpha1 > extreme_threshold) | (beta1 > extreme_threshold)))
        n_extreme2 = int(np.sum((alpha2 > extreme_threshold) | (beta2 > extreme_threshold)))

        mean_N_overall = (centroid1.N.mean() + centroid2.N.mean()) / 2.0
        if n_extreme1 > 0 and mean_N_overall >= 20:
            results["warnings"].append(f"Centroid1 has {n_extreme1} positions with extreme Beta parameters (> {extreme_threshold})")
        elif n_extreme1 > 0 and mean_N_overall < 20:
            logger.debug(f"Centroid1 has {n_extreme1} positions with extreme Beta parameters, but using normal approximation for small samples (N={mean_N_overall:.1f} < 20)")

        if n_extreme2 > 0 and mean_N_overall >= 20:
            results["warnings"].append(f"Centroid2 has {n_extreme2} positions with extreme Beta parameters (> {extreme_threshold})")
        elif n_extreme2 > 0 and mean_N_overall < 20:
            logger.debug(f"Centroid2 has {n_extreme2} positions with extreme Beta parameters, but using normal approximation for small samples (N={mean_N_overall:.1f} < 20)")

        # Check group separation using trimmed mean to focus on truly discriminative positions
        # Calculate absolute differences between centroids at each position
        position_diffs = np.abs(centroid1.mean - centroid2.mean)

        # Sort differences to identify positions with minimal differences
        sorted_diffs = np.sort(position_diffs)

        # Remove only 10% from positions with least difference (bottom 10%) to focus
        # on positions that actually show group differences, keeping the most discriminative
        n_positions = len(sorted_diffs)
        trim_bottom = int(0.10 * n_positions)  # Remove bottom 10% (least different)

        if trim_bottom < n_positions:
            # Keep positions with meaningful differences
            trimmed_diffs = sorted_diffs[trim_bottom:]
            mean_diff = float(np.mean(trimmed_diffs))
        else:
            # Fallback to simple mean if trimming would remove too much data
            mean_diff = abs(centroid1.mean.mean() - centroid2.mean.mean())

        # Add detailed statistics about position differences
        results["group_separation"] = float(mean_diff)
        results["separation_stats"] = {
            "mean_diff": float(np.mean(position_diffs)),
            "median_diff": float(np.median(position_diffs)),
            "std_diff": float(np.std(position_diffs)),
            "min_diff": float(np.min(position_diffs)),
            "max_diff": float(np.max(position_diffs)),
            "percentile_90_diff": float(np.percentile(position_diffs, 90)),
            "percentile_95_diff": float(np.percentile(position_diffs, 95)),
            "percentile_99_diff": float(np.percentile(position_diffs, 99)),
            "n_positions_above_0_1": int(np.sum(position_diffs > 0.1)),
            "n_positions_above_0_2": int(np.sum(position_diffs > 0.2)),
            "n_positions_above_0_5": int(np.sum(position_diffs > 0.5))
        }

        if mean_diff < 0.05:
            results["warnings"].append(f"Poor separation between centroids (trimmed mean difference = {mean_diff:.4f})")

        return results

    @staticmethod
    def compute_effect_sizes(alpha1: np.ndarray, beta1: np.ndarray, alpha2: np.ndarray, beta2: np.ndarray,
                           delta_mean: np.ndarray, bc_values: np.ndarray, gamma: float = 1.0,
                           numerical_epsilon: float = 1e-6) -> np.ndarray:
        """
        Compute effect sizes using the corrected formula that respects MethylSample's variance handling.

        Effect size = |delta_mu| * (1 - BC)^gamma / sqrt(var1 + var2)

        Args:
            alpha1, beta1: Beta parameters for centroid 1
            alpha2, beta2: Beta parameters for centroid 2
            delta_mean: Absolute difference in means
            bc_values: Bhattacharyya coefficient values (overlap)
            gamma: Gamma parameter for overlap penalty
            numerical_epsilon: Small value to prevent division by zero

        Returns:
            Array of effect size values (unnormalized, preserving biological importance)
        """
        # Use MethylSample's variance formula: var = mean * (1 - mean) / (tau + 1)
        eps = 1e-12
        tau1 = alpha1 + beta1
        tau2 = alpha2 + beta2
        mean1 = alpha1 / np.maximum(tau1, eps)
        mean2 = alpha2 / np.maximum(tau2, eps)

        var1 = mean1 * (1 - mean1) / np.maximum(tau1 + 1, eps)
        var2 = mean2 * (1 - mean2) / np.maximum(tau2 + 1, eps)

        # Combined standard deviation
        combined_std = np.sqrt(var1 + var2)
        combined_std = np.maximum(combined_std, numerical_epsilon)

        # Compute effect size: |delta_mu| / sqrt(var1 + var2) * (1 - BC)^gamma
        overlap_penalty = (1 - bc_values) ** gamma
        raw_effect_size = np.abs(delta_mean) / combined_std * overlap_penalty

        # Apply soft minimum to avoid zeros but preserve relative differences
        # Keep raw effect sizes to maintain biological importance for classification
        effect_sizes = np.maximum(raw_effect_size, 1e-8)  # Very small floor to avoid exact zeros

        return effect_sizes

    def _storey_qvalue(self, p_values: np.ndarray, lambda_seq=None) -> np.ndarray:
        """
        Manual implementation of Storey's q-value method (adaptive FDR control).
        
        Storey's method estimates π₀ (proportion of true null hypotheses) and uses
        it to adjust the FDR, making it less conservative than Benjamini-Hochberg
        when many true positives exist (common in genomics).

        Args:
            p_values: Array of p-values to correct
            lambda_seq: Sequence of λ values for π₀ estimation (default: 0.05 to 0.95)

        Returns:
            Array of q-values (Storey's FDR-corrected p-values)
        """
        if len(p_values) == 0:
            return np.array([])

        n = len(p_values)
        
        # Default lambda sequence for π₀ estimation
        if lambda_seq is None:
            lambda_seq = np.arange(0.05, 0.96, 0.05)
        
        # Estimate π₀ (proportion of true nulls) using bootstrap method
        pi0_estimates = []
        for lam in lambda_seq:
            # Count p-values > lambda
            w = np.sum(p_values > lam)
            # Estimate π₀ as: (# p-values > λ) / ((1 - λ) * total tests)
            pi0_est = w / (n * (1.0 - lam))
            pi0_estimates.append(pi0_est)
        
        # Use smoothing spline or simple average for π₀
        # For simplicity, use the minimum to be conservative
        pi0 = min(1.0, np.mean(pi0_estimates))
        pi0 = max(0.0, pi0)  # Ensure π₀ is in [0, 1]
        
        logger.debug(f"Storey's π₀ estimate: {pi0:.4f} (proportion of true nulls)")
        
        # Sort p-values and get original indices
        sorted_indices = np.argsort(p_values)
        sorted_p = p_values[sorted_indices]
        
        # Calculate q-values using π₀ adjustment
        # q(p_i) = min(π₀ * n * p_i / i) for all j >= i
        q_values = np.zeros(n)
        q_values[n-1] = min(1.0, pi0 * sorted_p[n-1])
        
        for i in range(n-2, -1, -1):
            q_val = min(1.0, pi0 * n * sorted_p[i] / (i + 1))
            q_values[i] = min(q_val, q_values[i+1])
        
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
