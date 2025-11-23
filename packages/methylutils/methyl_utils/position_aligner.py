# position_aligner.py
"""
Position alignment utilities for genomic methylation data.

This module provides the PositionAligner class which handles the complex task of
aligning genomic positions across multiple samples with different position sets.
Also, it keeps track of the number of samples that have contributed to the centroid,
and the accumulators for the centroid calculation.

In other words, it handles a dynamic list of samples, and the accumulators for the
centroid calculation (while keeping the position range dynamic).
It is used by the methylcentroid module to compute the centroid.

This implementation automatically detects GPU support and uses GPU acceleration
when available, providing a transparent interface to the application.
"""

import numpy as np
from typing import Tuple, Optional, List
from pathlib import Path
import logging
from .models import (
    PositionMethylationStats,
    GroupMethylationStats,
    AlignmentStats,
    MethylationAnalysisResults,
)

logger = logging.getLogger(__name__)

# GPU detection and acceleration - using methyl_utils package
try:
    from .gpu_detection import is_gpu_available, get_cupy
    from .logging_utils import get_logger
    from .core.methyl_frame import MethylFrame
except ImportError:
    # Fallback if methyl_utils package is not available
    def is_gpu_available():
        return False
    def get_cupy():
        return None
    def get_logger(name):
        return logging.getLogger(name)
    MethylFrame = None

# Initialize GPU state
_GPU_AVAILABLE = is_gpu_available()
_GPU_ACCELERATION = get_cupy() if _GPU_AVAILABLE else None

def _get_gpu_ops():
    """Get GPU operations if available, otherwise return None."""
    return _GPU_ACCELERATION


class PositionAligner:
    """
    Handles position alignment for genomic methylation data across multiple samples.

    This class manages the dynamic expansion of position ranges and provides
    efficient alignment of sample data to centroid positions. It automatically
    detects GPU support and uses GPU acceleration when available, providing
    a transparent interface to the application.

    Key Features:
    - Dynamic position range expansion as new samples are added
    - Efficient position intersection using numpy/cupy
    - Memory-efficient accumulator management with GPU support
    - Support for incremental updates
    - Proper tracking of sample contributions per position (N accumulator)
    - Automatic GPU acceleration when available
    - Comprehensive methylation level statistics tracking
    - Support for MethylSample objects for better type safety and clarity

    Usage:
        Use add_sample() and remove_sample() methods with MethylSample objects
        for adding and removing samples from the aligner.

        Use get_valid_positions() to find positions in a sample that meet coverage criteria.
        Use get_valid_positions_from_centroid() to find positions in centroid that meet coverage criteria.
        Use get_common_positions() to find positions common between centroid and sample.

    Attributes:
        max_samples (int): Maximum number of samples supported
        gpu_available (bool): Whether GPU acceleration is available and enabled
        min_coverage (int): Minimum coverage threshold for valid positions
        sample_count (int): Number of samples currently in the aligner
        position_range (tuple): Current position range as (min_pos, max_pos)
        total_positions (int): Total number of positions in the current range
        valid_positions (int): Number of valid positions meeting coverage criteria
        is_initialized (bool): Whether the aligner has been initialized with data
        has_data (bool): Whether the aligner contains any sample data
    """

    def __init__(self, max_samples: int = 1000, use_gpu: bool = True):
        """
        Initialize the position aligner with hybrid sparse/dense approach.

        Args:
            max_samples: Maximum number of samples to support (for tnc_data array sizing)
            use_gpu: Whether to use GPU acceleration if available (default: True)
        """
        self.max_samples = max_samples
        self.gpu_available = bool(use_gpu and _GPU_AVAILABLE)
        self.cp = _GPU_ACCELERATION if self.gpu_available else None

        # Position range tracking
        self.global_pos = None
        
        # Dense accumulators
        self.mC_sum = None
        self.uC_sum = None
        self.N_sum = None
        self.methylation_level_sum = None
        self.methylation_level_sq_sum = None
        self.log_methylation_sum = None
        self.log_one_minus_methylation_sum = None
        self.tnc = None
        
        # Sample tracking
        self.sample_count = 0
        self.active_samples = set()
        
        # Valid positions (filtered by coverage)
        self.valid_pos = None
        self.min_coverage = 4

        if self.gpu_available:
            logger.info("Using GPU-accelerated position alignment with hybrid sparse/dense approach")
        else:
            logger.info("Using CPU position alignment with hybrid sparse/dense approach")

    @property
    def is_initialized(self) -> bool:
        """
        Check if the aligner has been initialized with position data.
        
        Returns:
            bool: True if position range has been set, False otherwise
        """
        return self.global_pos is not None

    @property
    def has_data(self) -> bool:
        """
        Check if the aligner contains any sample data.
        
        Returns:
            bool: True if at least one sample has been added, False otherwise
        """
        return self.sample_count > 0

    @property
    def position_range(self) -> Optional[Tuple[np.uint32, np.uint32]]:
        """
        Get the current position range.
        
        Returns:
            tuple: (min_pos, max_pos) if initialized, None otherwise
        """
        if self.is_initialized:
            return self._to_cpu(self.global_pos)[0], self._to_cpu(self.global_pos)[-1]
        return None

    @property
    def total_positions(self) -> int:
        """
        Get the total number of positions in the current range.
        
        Returns:
            int: Number of positions in the range, 0 if not initialized
        """
        return len(self.global_pos) if self.is_initialized else 0

    @property
    def valid_positions(self) -> int:
        """
        Get the number of valid positions meeting coverage criteria.
        
        Returns:
            int: Number of valid positions, 0 if no data or no valid positions
        """
        if not self.has_data:
            return 0
        try:
            valid_pos, _, _, _ = self.compute_valid_positions()
            return len(valid_pos)
        except RuntimeError:
            return 0

    @property
    def coverage_threshold(self) -> int:
        """
        Get the current minimum coverage threshold.
        
        Returns:
            int: Minimum coverage required for a position to be considered valid
        """
        return self.min_coverage

    @coverage_threshold.setter
    def coverage_threshold(self, value: int):
        """
        Set the minimum coverage threshold for valid positions.
        
        Args:
            value: Minimum coverage threshold (must be >= 1)
        """
        self.set_min_coverage(value)

    @property
    def gpu_acceleration(self) -> bool:
        """
        Check if GPU acceleration is available and enabled.
        
        Returns:
            bool: True if GPU acceleration is available and enabled, False otherwise
        """
        return bool(self.gpu_available)

    @property
    def memory_usage_mb(self) -> float:
        """
        Estimate memory usage in megabytes for sparse implementation.
        
        Returns:
            float: Estimated memory usage in MB, 0 if not initialized
        """
        if not self.is_initialized:
            return 0.0
        
        num_pos = len(self.global_pos)
        # uint32: 3 arrays (mC, uC, N) * 4 bytes
        # float32: 4 arrays * 4 bytes
        # uint8: tnc * 1 byte
        total_bytes = num_pos * (3*4 + 4*4 + 1)
        return total_bytes / (1024 * 1024)

    @property
    def methylation_stats_available(self) -> bool:
        """
        Check if methylation statistics are available.
        
        Returns:
            bool: True if methylation level accumulators are initialized
        """
        return self.methylation_level_sum is not None

    def set_min_coverage(self, min_coverage: int):
        """
        Set the minimum coverage threshold for valid positions.
        
        Args:
            min_coverage: Minimum coverage threshold (must be >= 1)
        """
        self.min_coverage = max(1, min_coverage)
        self.valid_pos = None

    def _create_array(self, size: int, dtype) -> np.ndarray:
        """Create arrays on GPU if available, otherwise on CPU."""
        if self.gpu_available:
            return self.cp.zeros(size, dtype=dtype)
        else:
            return np.zeros(size, dtype=dtype)

    def _to_device(self, array: np.ndarray) -> np.ndarray:
        """Convert array to GPU array if GPU is available."""
        if self.gpu_available:
            # Convert to NumPy first if it's CuPy
            if hasattr(array, "get"):
                array = array.get()
            return self.cp.asarray(array)
        else:
            # Ensure it's NumPy
            if hasattr(array, "get"):
                return array.get()
            return array

    def _to_cpu(self, array: np.ndarray) -> np.ndarray:
        """Convert array to CPU array."""
        if self.gpu_available and hasattr(array, "get"):
            return array.get()
        return array

    def expand_global_positions(self, new_positions: np.ndarray):
        """
        Expand the global positions with new unique positions and update accumulators.
        
        Args:
            new_positions: Array of new positions to include
        """
        new_positions = np.unique(np.asarray(new_positions, dtype=np.uint32))
        if len(new_positions) == 0:
            return

        if not self.is_initialized:
            self.global_pos = self._to_device(np.sort(new_positions))
            num_pos = len(self.global_pos)
            self.mC_sum = self._create_array(num_pos, np.uint32)
            self.uC_sum = self._create_array(num_pos, np.uint32)
            self.N_sum = self._create_array(num_pos, np.uint32)
            self.methylation_level_sum = self._create_array(num_pos, np.float32)
            self.methylation_level_sq_sum = self._create_array(num_pos, np.float32)
            self.log_methylation_sum = self._create_array(num_pos, np.float32)
            self.log_one_minus_methylation_sum = self._create_array(num_pos, np.float32)
            self.tnc = self._create_array(num_pos, np.uint8)
            return

        cpu_global = self._to_cpu(self.global_pos)
        cpu_new_positions = np.asarray(new_positions, dtype=np.uint32)
        new_unique = np.setdiff1d(cpu_new_positions, cpu_global)
        if len(new_unique) == 0:
            return

        combined_pos = np.sort(np.concatenate((cpu_global, new_unique)))
        new_global = self._to_device(combined_pos)

        old_indices = np.searchsorted(combined_pos, cpu_global)

        # Create new arrays with the expanded size
        new_mC_sum = self._create_array(len(combined_pos), np.uint32)
        new_uC_sum = self._create_array(len(combined_pos), np.uint32)
        new_N_sum = self._create_array(len(combined_pos), np.uint32)
        new_methylation_level_sum = self._create_array(len(combined_pos), np.float32)
        new_methylation_level_sq_sum = self._create_array(len(combined_pos), np.float32)
        new_log_methylation_sum = self._create_array(len(combined_pos), np.float32)
        new_log_one_minus_methylation_sum = self._create_array(len(combined_pos), np.float32)
        new_tnc = self._create_array(len(combined_pos), np.uint8)

        # Copy existing data to new arrays at the correct positions
        new_mC_sum[old_indices] = self.mC_sum
        new_uC_sum[old_indices] = self.uC_sum
        new_N_sum[old_indices] = self.N_sum
        new_methylation_level_sum[old_indices] = self.methylation_level_sum
        new_methylation_level_sq_sum[old_indices] = self.methylation_level_sq_sum
        new_log_methylation_sum[old_indices] = self.log_methylation_sum
        new_log_one_minus_methylation_sum[old_indices] = self.log_one_minus_methylation_sum
        new_tnc[old_indices] = self.tnc

        # Update references to new arrays
        self.mC_sum = new_mC_sum
        self.uC_sum = new_uC_sum
        self.N_sum = new_N_sum
        self.methylation_level_sum = new_methylation_level_sum
        self.methylation_level_sq_sum = new_methylation_level_sq_sum
        self.log_methylation_sum = new_log_methylation_sum
        self.log_one_minus_methylation_sum = new_log_one_minus_methylation_sum
        self.tnc = new_tnc

        self.global_pos = new_global
        self.valid_pos = None

    def add_sample_data(
        self,
        sample_pos: np.ndarray,
        mC: np.ndarray,
        uC: np.ndarray,
        tnc: np.ndarray,
        sample_index: int,
    ) -> bool:
        """
        Add sample data to the accumulators with efficient vectorized operations.

        Args:
            sample_pos: Position array for the sample
            mC: Methylated cytosine counts
            uC: Unmethylated cytosine counts
            tnc: Trinucleotide context codes
            sample_index: Index of the sample in the sample list

        Returns:
            True if successful, False otherwise
        """
        if len(sample_pos) == 0:
            return False

        # Validate array lengths match
        if not (len(sample_pos) == len(mC) == len(uC) == len(tnc)):
            return False

        # Expand global positions if necessary
        self.expand_global_positions(sample_pos)

        cpu_global = self._to_cpu(self.global_pos)
        cpu_sample_pos = np.asarray(sample_pos, dtype=np.uint32)
        indices = np.searchsorted(cpu_global, cpu_sample_pos)
        # Ensure both arrays are CPU numpy arrays for comparison
        cpu_global_at_indices = np.asarray(cpu_global[indices], dtype=np.uint32)
        cpu_sample_pos_array = np.asarray(cpu_sample_pos, dtype=np.uint32)
        valid = (indices < len(cpu_global)) & (cpu_global_at_indices == cpu_sample_pos_array)
        indices = indices[valid]

        if len(indices) == 0:
            return False

        valid_mC = mC[valid].astype(np.uint32)
        valid_uC = uC[valid].astype(np.uint32)
        valid_tnc = tnc[valid].astype(np.uint8)

        # Convert numpy arrays to match the type of accumulators (CPU or GPU)
        if hasattr(self.mC_sum, '__array_function__') and 'cupy' in str(type(self.mC_sum)):
            # Accumulators are CuPy arrays, convert valid arrays to CuPy
            try:
                import cupy as cp
                valid_mC = cp.asarray(valid_mC)
                valid_uC = cp.asarray(valid_uC)
            except ImportError:
                # Fallback: convert accumulators to CPU
                self.mC_sum = self._to_cpu(self.mC_sum)
                self.uC_sum = self._to_cpu(self.uC_sum)
                self.N_sum = self._to_cpu(self.N_sum)
        
        self.mC_sum[indices] += valid_mC
        self.uC_sum[indices] += valid_uC
        self.N_sum[indices] += 1

        total_coverage = valid_mC + valid_uC
        
        # Use appropriate divide function based on array type
        if hasattr(valid_mC, '__array_function__') and 'cupy' in str(type(valid_mC)):
            # CuPy arrays - use simpler approach without 'where' parameter
            try:
                import cupy as cp
                ml = cp.zeros_like(valid_mC, dtype=cp.float32)
                mask = total_coverage > 0
                ml[mask] = valid_mC[mask] / total_coverage[mask]
            except ImportError:
                # Fallback to CPU
                valid_mC_cpu = self._to_cpu(valid_mC)
                total_coverage_cpu = self._to_cpu(total_coverage)
                ml = np.divide(valid_mC_cpu, total_coverage_cpu, out=np.zeros_like(valid_mC_cpu, dtype=np.float32), where=total_coverage_cpu > 0)
        else:
            # NumPy arrays
            ml = np.divide(valid_mC, total_coverage, out=np.zeros_like(valid_mC, dtype=np.float32), where=total_coverage > 0)
        
        ml_sq = ml ** 2

        # Use a robust approach to avoid log(0) warnings
        epsilon = 1e-10
        
        # Use appropriate functions based on array type
        if hasattr(ml, '__array_function__') and 'cupy' in str(type(ml)):
            # CuPy arrays
            try:
                import cupy as cp
                safe_ml = cp.clip(ml, epsilon, 1 - epsilon)
                log_ml = cp.log(safe_ml)
                
                # Compute log(1 - safe_ml) carefully to avoid log(0)
                one_minus_safe_ml = 1 - safe_ml
                # Clip to ensure we don't take log of values too close to 0
                one_minus_safe_ml = cp.clip(one_minus_safe_ml, epsilon, 1 - epsilon)
                log_1_ml = cp.log(one_minus_safe_ml)
            except ImportError:
                # Fallback to CPU
                ml_cpu = self._to_cpu(ml)
                safe_ml = np.clip(ml_cpu, epsilon, 1 - epsilon)
                log_ml = np.log(safe_ml)
                one_minus_safe_ml = 1 - safe_ml
                one_minus_safe_ml = np.clip(one_minus_safe_ml, epsilon, 1 - epsilon)
                log_1_ml = np.log(one_minus_safe_ml)
        else:
            # NumPy arrays
            safe_ml = np.clip(ml, epsilon, 1 - epsilon)
            log_ml = np.log(safe_ml)
            
            # Compute log(1 - safe_ml) carefully to avoid log(0)
            one_minus_safe_ml = 1 - safe_ml
            # Clip to ensure we don't take log of values too close to 0
            one_minus_safe_ml = np.clip(one_minus_safe_ml, epsilon, 1 - epsilon)
            log_1_ml = np.log(one_minus_safe_ml)

        self.methylation_level_sum[indices] += ml
        self.methylation_level_sq_sum[indices] += ml_sq
        self.log_methylation_sum[indices] += log_ml
        self.log_one_minus_methylation_sum[indices] += log_1_ml

        # Set tnc for unset positions
        unset_mask = self.tnc[indices] == 0
        self.tnc[indices[unset_mask]] = valid_tnc[unset_mask]

        self.sample_count += 1
        self.active_samples.add(sample_index)
        self.valid_pos = None
        return True

    def remove_sample_data(
        self, 
        sample_pos: np.ndarray, 
        mC: np.ndarray, 
        uC: np.ndarray, 
        sample_index: int
    ) -> bool:
        """
        Remove sample data from the accumulators with efficient vectorized operations.

        Args:
            sample_pos: Position array for the sample
            mC: Methylated cytosine counts
            uC: Unmethylated cytosine counts
            sample_index: Index of the sample in the sample list

        Returns:
            True if successful, False otherwise
        """
        if not self.is_initialized:
            return False

        cpu_global = self._to_cpu(self.global_pos)
        cpu_sample_pos = np.asarray(sample_pos, dtype=np.uint32)
        indices = np.searchsorted(cpu_global, cpu_sample_pos)
        # Ensure both arrays are CPU numpy arrays for comparison
        cpu_global_at_indices = np.asarray(cpu_global[indices], dtype=np.uint32)
        cpu_sample_pos_array = np.asarray(cpu_sample_pos, dtype=np.uint32)
        valid = (indices < len(cpu_global)) & (cpu_global_at_indices == cpu_sample_pos_array)
        indices = indices[valid]

        if len(indices) == 0:
            return False

        valid_mC = mC[valid].astype(np.uint32)
        valid_uC = uC[valid].astype(np.uint32)

        self.mC_sum[indices] -= valid_mC
        self.uC_sum[indices] -= valid_uC
        self.N_sum[indices] -= 1

        total_coverage = valid_mC + valid_uC
        
        # Use appropriate divide function based on array type
        if hasattr(valid_mC, '__array_function__') and 'cupy' in str(type(valid_mC)):
            # CuPy arrays - use simpler approach without 'where' parameter
            try:
                import cupy as cp
                ml = cp.zeros_like(valid_mC, dtype=cp.float32)
                mask = total_coverage > 0
                ml[mask] = valid_mC[mask] / total_coverage[mask]
            except ImportError:
                # Fallback to CPU
                valid_mC_cpu = self._to_cpu(valid_mC)
                total_coverage_cpu = self._to_cpu(total_coverage)
                ml = np.divide(valid_mC_cpu, total_coverage_cpu, out=np.zeros_like(valid_mC_cpu, dtype=np.float32), where=total_coverage_cpu > 0)
        else:
            # NumPy arrays
            ml = np.divide(valid_mC, total_coverage, out=np.zeros_like(valid_mC, dtype=np.float32), where=total_coverage > 0)
        
        ml_sq = ml ** 2

        # Use a robust approach to avoid log(0) warnings
        epsilon = 1e-10
        
        # Use appropriate functions based on array type
        if hasattr(ml, '__array_function__') and 'cupy' in str(type(ml)):
            # CuPy arrays
            try:
                import cupy as cp
                safe_ml = cp.clip(ml, epsilon, 1 - epsilon)
                log_ml = cp.log(safe_ml)
                
                # Compute log(1 - safe_ml) carefully to avoid log(0)
                one_minus_safe_ml = 1 - safe_ml
                # Clip to ensure we don't take log of values too close to 0
                one_minus_safe_ml = cp.clip(one_minus_safe_ml, epsilon, 1 - epsilon)
                log_1_ml = cp.log(one_minus_safe_ml)
            except ImportError:
                # Fallback to CPU
                ml_cpu = self._to_cpu(ml)
                safe_ml = np.clip(ml_cpu, epsilon, 1 - epsilon)
                log_ml = np.log(safe_ml)
                one_minus_safe_ml = 1 - safe_ml
                one_minus_safe_ml = np.clip(one_minus_safe_ml, epsilon, 1 - epsilon)
                log_1_ml = np.log(one_minus_safe_ml)
        else:
            # NumPy arrays
            safe_ml = np.clip(ml, epsilon, 1 - epsilon)
            log_ml = np.log(safe_ml)
            
            # Compute log(1 - safe_ml) carefully to avoid log(0)
            one_minus_safe_ml = 1 - safe_ml
            # Clip to ensure we don't take log of values too close to 0
            one_minus_safe_ml = np.clip(one_minus_safe_ml, epsilon, 1 - epsilon)
            log_1_ml = np.log(one_minus_safe_ml)

        self.methylation_level_sum[indices] -= ml
        self.methylation_level_sq_sum[indices] -= ml_sq
        self.log_methylation_sum[indices] -= log_ml
        self.log_one_minus_methylation_sum[indices] -= log_1_ml

        self.sample_count -= 1
        self.active_samples.remove(sample_index)
        self.valid_pos = None
        return True

    def add_sample(self, sample: MethylFrame, sample_index: int) -> bool:
        """
        Add a MethylSample to the accumulators.
        
        Args:
            sample: MethylSample instance containing methylation data
            sample_index: Index of the sample in the sample list
            
        Returns:
            True if successful, False otherwise
        """
        if MethylFrame is None:
            raise ImportError("MethylFrame is not available. Please install methyl_utils package.")
        
        # Check if it's a MethylFrame instance (new architecture)
        if not isinstance(sample, MethylFrame):
            raise TypeError(f"Expected MethylFrame (MethylSample/MethylBasicCentroid/MethylExtendedCentroid), got {type(sample)}")
        
        if len(sample.pos) == 0:
            return False
        
        # For regular samples, use the existing optimized add_sample_data method
        if not sample.is_centroid:
            return self.add_sample_data(sample.pos, sample.mC, sample.uC, sample.tnc, sample_index)
        
        # For centroids, we need to handle the accumulated values differently
        # Extract data from MethylSample
        pos = sample.pos
        mC = sample.mC
        uC = sample.uC
        tnc = sample.tnc
        
        # For centroids, use the accumulated values directly
        N = sample.N if sample.N is not None else np.ones_like(mC, dtype=np.uint32)
        
        # Get methylation level statistics if available
        ml_sum = sample.Sx if sample.Sx is not None else np.zeros_like(mC, dtype=np.float32)
        ml_sq_sum = sample.Sx2 if sample.Sx2 is not None else np.zeros_like(mC, dtype=np.float32)
        log_x_sum = sample.log_x_sum if sample.log_x_sum is not None else np.zeros_like(mC, dtype=np.float32)
        log_1_minus_x_sum = sample.log_1_minus_x_sum if sample.log_1_minus_x_sum is not None else np.zeros_like(mC, dtype=np.float32)
        
        # Expand global positions if necessary
        self.expand_global_positions(pos)
        
        # Convert sample data to GPU if available for better performance
        if self.gpu_available:
            sample_pos_gpu = self._to_device(np.asarray(pos, dtype=np.uint32))
            mC_gpu = self._to_device(np.asarray(mC, dtype=np.uint32))
            uC_gpu = self._to_device(np.asarray(uC, dtype=np.uint32))
            N_gpu = self._to_device(np.asarray(N, dtype=np.uint32))
            tnc_gpu = self._to_device(np.asarray(tnc, dtype=np.uint8))
            
            # Use GPU searchsorted for better performance with large arrays
            indices = self.cp.searchsorted(self.global_pos, sample_pos_gpu)
            
            # GPU-based validation
            valid_mask = (indices < len(self.global_pos)) & (self.global_pos[indices] == sample_pos_gpu)
            indices = indices[valid_mask]
            
            if len(indices) == 0:
                return False
            
            # GPU-optimized array operations
            self.mC_sum[indices] += mC_gpu[valid_mask]
            self.uC_sum[indices] += uC_gpu[valid_mask]
            self.N_sum[indices] += N_gpu[valid_mask]
            
            # Add methylation level statistics for centroids
            ml_sum_gpu = self._to_device(np.asarray(ml_sum, dtype=np.float32))
            ml_sq_sum_gpu = self._to_device(np.asarray(ml_sq_sum, dtype=np.float32))
            log_x_sum_gpu = self._to_device(np.asarray(log_x_sum, dtype=np.float32))
            log_1_minus_x_sum_gpu = self._to_device(np.asarray(log_1_minus_x_sum, dtype=np.float32))
            
            self.methylation_level_sum[indices] += ml_sum_gpu[valid_mask]
            self.methylation_level_sq_sum[indices] += ml_sq_sum_gpu[valid_mask]
            self.log_methylation_sum[indices] += log_x_sum_gpu[valid_mask]
            self.log_one_minus_methylation_sum[indices] += log_1_minus_x_sum_gpu[valid_mask]
            
            # Set tnc for unset positions (GPU operation)
            valid_tnc = tnc_gpu[valid_mask]
            unset_mask = self.tnc[indices] == 0
            self.tnc[indices[unset_mask]] = valid_tnc[unset_mask]
            
        else:
            # CPU fallback with optimized operations
            cpu_global = self._to_cpu(self.global_pos)
            cpu_sample_pos = np.asarray(pos, dtype=np.uint32)
            indices = np.searchsorted(cpu_global, cpu_sample_pos)
            
            # Vectorized validation
            cpu_global_at_indices = np.asarray(cpu_global[indices], dtype=np.uint32)
            cpu_sample_pos_array = np.asarray(cpu_sample_pos, dtype=np.uint32)
            valid = (indices < len(cpu_global)) & (cpu_global_at_indices == cpu_sample_pos_array)
            indices = indices[valid]
            
            if len(indices) == 0:
                return False
            
            # Vectorized array operations
            self.mC_sum[indices] += mC[valid]
            self.uC_sum[indices] += uC[valid]
            self.N_sum[indices] += N[valid]
            
            # Add methylation level statistics for centroids
            self.methylation_level_sum[indices] += ml_sum[valid]
            self.methylation_level_sq_sum[indices] += ml_sq_sum[valid]
            self.log_methylation_sum[indices] += log_x_sum[valid]
            self.log_one_minus_methylation_sum[indices] += log_1_minus_x_sum[valid]
            
            # Set tnc for unset positions
            valid_tnc = tnc[valid].astype(np.uint8)
            unset_mask = self.tnc[indices] == 0
            self.tnc[indices[unset_mask]] = valid_tnc[unset_mask]
        
        self.sample_count += 1
        self.active_samples.add(sample_index)
        self.valid_pos = None
        return True
    
    def remove_sample(self, sample: MethylFrame, sample_index: int) -> bool:
        """
        Remove a MethylSample from the accumulators.
        
        Args:
            sample: MethylSample instance containing methylation data
            sample_index: Index of the sample in the sample list
            
        Returns:
            True if successful, False otherwise
        """
        if MethylFrame is None:
            raise ImportError("MethylFrame is not available. Please install methyl_utils package.")
        
        # Check if it's a MethylFrame instance (new architecture)
        if not isinstance(sample, MethylFrame):
            raise TypeError(f"Expected MethylFrame (MethylSample/MethylBasicCentroid/MethylExtendedCentroid), got {type(sample)}")
        
        if not self.is_initialized:
            return False
        
        # For regular samples, use the existing optimized remove_sample_data method
        if not sample.is_centroid:
            return self.remove_sample_data(sample.pos, sample.mC, sample.uC, sample_index)
        
        # For centroids, we need to handle the accumulated values differently
        # Extract data from MethylSample
        pos = sample.pos
        mC = sample.mC
        uC = sample.uC
        
        # For centroids, use the accumulated values directly
        N = sample.N if sample.N is not None else np.ones_like(mC, dtype=np.uint32)
        
        # Get methylation level statistics if available
        ml_sum = sample.Sx if sample.Sx is not None else np.zeros_like(mC, dtype=np.float32)
        ml_sq_sum = sample.Sx2 if sample.Sx2 is not None else np.zeros_like(mC, dtype=np.float32)
        log_x_sum = sample.log_x_sum if sample.log_x_sum is not None else np.zeros_like(mC, dtype=np.float32)
        log_1_minus_x_sum = sample.log_1_minus_x_sum if sample.log_1_minus_x_sum is not None else np.zeros_like(mC, dtype=np.float32)
        
        # Convert sample data to GPU if available for better performance
        if self.gpu_available:
            sample_pos_gpu = self._to_device(np.asarray(pos, dtype=np.uint32))
            mC_gpu = self._to_device(np.asarray(mC, dtype=np.uint32))
            uC_gpu = self._to_device(np.asarray(uC, dtype=np.uint32))
            N_gpu = self._to_device(np.asarray(N, dtype=np.uint32))
            
            # Use GPU searchsorted for better performance with large arrays
            indices = self.cp.searchsorted(self.global_pos, sample_pos_gpu)
            
            # GPU-based validation
            valid_mask = (indices < len(self.global_pos)) & (self.global_pos[indices] == sample_pos_gpu)
            indices = indices[valid_mask]
            
            if len(indices) == 0:
                return False
            
            # GPU-optimized array operations
            self.mC_sum[indices] -= mC_gpu[valid_mask]
            self.uC_sum[indices] -= uC_gpu[valid_mask]
            self.N_sum[indices] -= N_gpu[valid_mask]
            
            # Remove methylation level statistics for centroids
            ml_sum_gpu = self._to_device(np.asarray(ml_sum, dtype=np.float32))
            ml_sq_sum_gpu = self._to_device(np.asarray(ml_sq_sum, dtype=np.float32))
            log_x_sum_gpu = self._to_device(np.asarray(log_x_sum, dtype=np.float32))
            log_1_minus_x_sum_gpu = self._to_device(np.asarray(log_1_minus_x_sum, dtype=np.float32))
            
            self.methylation_level_sum[indices] -= ml_sum_gpu[valid_mask]
            self.methylation_level_sq_sum[indices] -= ml_sq_sum_gpu[valid_mask]
            self.log_methylation_sum[indices] -= log_x_sum_gpu[valid_mask]
            self.log_one_minus_methylation_sum[indices] -= log_1_minus_x_sum_gpu[valid_mask]
            
        else:
            # CPU fallback with optimized operations
            cpu_global = self._to_cpu(self.global_pos)
            cpu_sample_pos = np.asarray(pos, dtype=np.uint32)
            indices = np.searchsorted(cpu_global, cpu_sample_pos)
            
            # Vectorized validation
            cpu_global_at_indices = np.asarray(cpu_global[indices], dtype=np.uint32)
            cpu_sample_pos_array = np.asarray(cpu_sample_pos, dtype=np.uint32)
            valid = (indices < len(cpu_global)) & (cpu_global_at_indices == cpu_sample_pos_array)
            indices = indices[valid]
            
            if len(indices) == 0:
                return False
            
            # Vectorized array operations
            self.mC_sum[indices] -= mC[valid]
            self.uC_sum[indices] -= uC[valid]
            self.N_sum[indices] -= N[valid]
            
            # Remove methylation level statistics for centroids
            self.methylation_level_sum[indices] -= ml_sum[valid]
            self.methylation_level_sq_sum[indices] -= ml_sq_sum[valid]
            self.log_methylation_sum[indices] -= log_x_sum[valid]
            self.log_one_minus_methylation_sum[indices] -= log_1_minus_x_sum[valid]
        
        self.sample_count = max(0, self.sample_count - 1)
        self.active_samples.discard(sample_index)
        self.valid_pos = None
        return True
    

    def compute_valid_positions(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]: 
        """
        Compute valid positions and centroid data from accumulators.
        
        Returns:
            Tuple of (valid_positions, centroid_mC, centroid_uC, centroid_N) arrays
        """
        if self.sample_count == 0:
            raise RuntimeError("No samples available")
        
        # Convert GPU arrays to CPU for operations
        cpu_mC_sum = self._to_cpu(self.mC_sum)
        cpu_uC_sum = self._to_cpu(self.uC_sum)
        cpu_N_sum = self._to_cpu(self.N_sum)
        total_coverage = cpu_mC_sum + cpu_uC_sum
        valid_mask = (total_coverage >= self.min_coverage) & (cpu_N_sum > 0)
        
        valid_pos = self.global_pos[valid_mask]
        centroid_mC = self.mC_sum[valid_mask]
        centroid_uC = self.uC_sum[valid_mask]
        centroid_N = self.N_sum[valid_mask]
        
        if len(valid_pos) == 0:
            raise RuntimeError("No valid positions found with sufficient coverage")
        
        self.valid_pos = self._to_cpu(valid_pos)
        return self._to_cpu(valid_pos), self._to_cpu(centroid_mC), self._to_cpu(centroid_uC), self._to_cpu(centroid_N)

    def get_centroid_sample(self) -> MethylFrame:
        """
        Get the current centroid as a MethylSample object.

        This method computes the centroid from accumulated data and returns it as a
        MethylSample object, which is the proper way to handle centroids in the
        methyl_utils ecosystem.

        Returns:
            MethylSample object representing the current centroid with valid positions only.

        Raises:
            RuntimeError: If no samples have been added or no valid positions found.
        """
        if MethylFrame is None:
            raise ImportError("MethylFrame is not available. Please install methyl_utils package.")

        if self.sample_count == 0:
            raise RuntimeError("No samples available")

        # Get valid positions directly from the existing method
        valid_pos = self.get_valid_positions_from_centroid()

        if len(valid_pos) == 0:
            raise RuntimeError("No valid positions found with sufficient coverage")

        # Get indices in global arrays for the valid positions
        global_indices = np.searchsorted(self._to_cpu(self.global_pos), valid_pos)

        # Extract centroid data for valid positions
        centroid_mC = self._to_cpu(self.mC_sum)[global_indices]
        centroid_uC = self._to_cpu(self.uC_sum)[global_indices]
        centroid_N = self._to_cpu(self.N_sum)[global_indices]
        tnc = self._to_cpu(self.tnc)[global_indices]

        # Calculate average methylation values for the centroid
        avg_mC = np.round(centroid_mC / centroid_N).astype(np.uint32)
        avg_uC = np.round(centroid_uC / centroid_N).astype(np.uint32)

        # Extract methylation statistics if available
        Sx = None
        Sx2 = None
        log_x_sum = None
        log_1_minus_x_sum = None

        if self.methylation_stats_available:
            Sx = self._to_cpu(self.methylation_level_sum)[global_indices]
            Sx2 = self._to_cpu(self.methylation_level_sq_sum)[global_indices]
            log_x_sum = self._to_cpu(self.log_methylation_sum)[global_indices]
            log_1_minus_x_sum = self._to_cpu(self.log_one_minus_methylation_sum)[global_indices]

        # Create MethylFrame object for the centroid
        import pandas as pd
        from methyl_utils.core.methyl_frame import MethylSample, MethylBasicCentroid, MethylExtendedCentroid
        
        # Build DataFrame
        df_data = {
            'pos': valid_pos,
            'mC': avg_mC,
            'uC': avg_uC,
            'tnc': tnc,
        }
        
        # Determine which class to use based on available data
        if Sx is not None and Sx2 is not None and log_x_sum is not None and log_1_minus_x_sum is not None:
            # Extended centroid
            df_data.update({
                'N': centroid_N,
                'Sx': Sx,
                'Sx2': Sx2,
                'log_x_sum': log_x_sum,
                'log_1_minus_x_sum': log_1_minus_x_sum
            })
            df = pd.DataFrame(df_data)
            return MethylExtendedCentroid(df, metadata=None)
        elif centroid_N is not None:
            # Basic centroid
            df_data['N'] = centroid_N
            df = pd.DataFrame(df_data)
            return MethylBasicCentroid(df, metadata=None)
        else:
            # Basic sample
            df = pd.DataFrame(df_data)
            return MethylSample(df, metadata=None)


    def compute_methylation_statistics(
        self,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Compute detailed methylation level statistics for each position using optimized GPU acceleration.

        This method calculates comprehensive methylation statistics including
        average methylation levels, means, and standard deviations across samples
        for each valid position. Optimized for millions of positions with GPU acceleration.

        Returns:
            Tuple containing:
                - valid_positions: Array of genomic positions meeting coverage criteria
                - avg_methylation_levels: Average methylation level per position (mC/(mC+uC))
                - methylation_means: Mean methylation level across samples per position
                - methylation_stdevs: Standard deviation of methylation levels per position
                - centroid_N: Number of samples contributing to each position

        Raises:
            RuntimeError: If no samples have been added or methylation stats not available

        Example:
            >>> valid_pos, avg_levels, means, stdevs, N = aligner.compute_methylation_statistics()
            >>> print(f"Position {valid_pos[0]}: avg={avg_levels[0]:.3f}, mean={means[0]:.3f}, stdev={stdevs[0]:.3f}")
        """
        if self.sample_count == 0:
            raise RuntimeError("No samples available")

        # GPU-optimized calculations for large datasets
        if self.gpu_available:
            # All operations on GPU for maximum performance
            total_coverage = self.mC_sum + self.uC_sum
            valid_mask = (total_coverage >= self.min_coverage) & (self.N_sum > 0)
            
            valid_pos = self.global_pos[valid_mask]
            
            # GPU-optimized division with proper handling of zeros
            avg_methylation_levels = self.cp.divide(
                self.mC_sum[valid_mask],
                total_coverage[valid_mask],
                out=self.cp.zeros_like(self.mC_sum[valid_mask], dtype=self.cp.float32),
                where=total_coverage[valid_mask] > 0,
            )

            methylation_means = self.cp.divide(
                self.methylation_level_sum[valid_mask],
                self.N_sum[valid_mask],
                out=self.cp.zeros_like(self.methylation_level_sum[valid_mask], dtype=self.cp.float32),
                where=self.N_sum[valid_mask] > 0,
            )

            # GPU-optimized variance calculation
            variance_numerator = self.methylation_level_sq_sum[valid_mask] - (
                self.methylation_level_sum[valid_mask] ** 2 / self.N_sum[valid_mask]
            )
            
            variance = self.cp.divide(
                variance_numerator,
                self.N_sum[valid_mask] - 1,
                out=self.cp.zeros_like(variance_numerator, dtype=self.cp.float32),
                where=(self.N_sum[valid_mask] - 1) > 0,
            )
            
            # GPU-optimized clipping and sqrt
            variance = self.cp.maximum(variance, 0.0)
            methylation_stdevs = self.cp.sqrt(variance)

            centroid_N = self.N_sum[valid_mask]

            return (
                self._to_cpu(valid_pos),
                self._to_cpu(avg_methylation_levels),
                self._to_cpu(methylation_means),
                self._to_cpu(methylation_stdevs),
                self._to_cpu(centroid_N),
            )
        else:
            # CPU fallback with vectorized operations
            total_coverage = self.mC_sum + self.uC_sum
            valid_mask = (total_coverage >= self.min_coverage) & (self.N_sum > 0)
            
            valid_pos = self.global_pos[valid_mask]
            avg_methylation_levels = np.divide(
                self.mC_sum[valid_mask],
                total_coverage[valid_mask],
                out=np.zeros_like(self.mC_sum[valid_mask], dtype=np.float32),
                where=total_coverage[valid_mask] > 0,
            )

            methylation_means = np.divide(
                self.methylation_level_sum[valid_mask],
                self.N_sum[valid_mask],
                out=np.zeros_like(self.methylation_level_sum[valid_mask], dtype=np.float32),
                where=self.N_sum[valid_mask] > 0,
            )

            variance_numerator = self.methylation_level_sq_sum[valid_mask] - (
                self.methylation_level_sum[valid_mask] ** 2 / self.N_sum[valid_mask]
            )
            
            variance = np.divide(
                variance_numerator,
                self.N_sum[valid_mask] - 1,
                out=np.zeros_like(variance_numerator, dtype=np.float32),
                where=(self.N_sum[valid_mask] - 1) > 0,
            )
            
            variance = np.maximum(variance, 0.0)
            methylation_stdevs = np.sqrt(variance)

            centroid_N = self.N_sum[valid_mask]

            return (
                self._to_cpu(valid_pos),
                self._to_cpu(avg_methylation_levels),
                self._to_cpu(methylation_means),
                self._to_cpu(methylation_stdevs),
                self._to_cpu(centroid_N),
            )

    def get_group_methylation_statistics(self) -> dict:
        """
        Calculate group-level methylation statistics using GPU acceleration.

        Returns:
            dict: Dictionary containing group methylation statistics
        """
        if self.sample_count == 0:
            return {
                "group_avg_methylation": 0.0,
                "group_methylation_mean": 0.0,
                "group_methylation_stdev": 0.0,
                "total_positions": 0,
                "total_samples": 0,
                "total_mC": 0,
                "total_uC": 0,
                "total_coverage": 0
            }

        valid_pos, centroid_mC, centroid_uC, centroid_N = self.compute_valid_positions()
        
        if len(valid_pos) == 0:
            return {
                "group_avg_methylation": 0.0,
                "group_methylation_mean": 0.0,
                "group_methylation_stdev": 0.0,
                "total_positions": 0,
                "total_samples": 0,
                "total_mC": 0,
                "total_uC": 0,
                "total_coverage": 0
            }

        total_mC = np.sum(centroid_mC)
        total_uC = np.sum(centroid_uC)
        group_avg_methylation = (
            total_mC / (total_mC + total_uC) if (total_mC + total_uC) > 0 else 0.0
        )

        total_N = np.sum(centroid_N)
        total_methylation_sum = np.sum(self.methylation_level_sum)
        group_methylation_mean = total_methylation_sum / total_N if total_N > 0 else 0.0

        total_variance_numerator = np.sum(self.methylation_level_sq_sum) - (total_methylation_sum**2 / total_N)
        # Ensure variance is non-negative (handle floating-point precision issues)
        variance = max(0.0, total_variance_numerator / (total_N - 1)) if (total_N - 1) > 0 else 0.0
        group_methylation_stdev = np.sqrt(variance)

        return {
            "group_avg_methylation": float(group_avg_methylation),
            "group_methylation_mean": float(group_methylation_mean),
            "group_methylation_stdev": float(group_methylation_stdev),
            "total_positions": len(valid_pos),
            "total_samples": self.sample_count,
            "total_mC": int(total_mC),
            "total_uC": int(total_uC),
            "total_coverage": int(total_mC + total_uC)
        }

    def get_valid_positions(self, sample: MethylSample) -> np.ndarray:
        """
        Get valid positions from a sample that meet minimum coverage criteria.

        Args:
            sample: MethylSample instance containing sample data

        Returns:
            Array of positions that meet coverage criteria (>= min_coverage)
        """
        if MethylFrame is None:
            raise ImportError("MethylFrame is not available. Please install methyl_utils package.")

        # Check if it's a MethylFrame instance (new architecture)
        from methyl_utils.core.methyl_frame import MethylFrame
        if not isinstance(sample, MethylFrame):
            raise TypeError(f"Expected MethylFrame (MethylSample/MethylBasicCentroid/MethylExtendedCentroid), got {type(sample)}")

        # Calculate coverage for each position
        total_coverage = sample.mC + sample.uC

        # Find positions that meet minimum coverage
        valid_mask = total_coverage >= self.min_coverage

        return sample.pos[valid_mask]

    def get_valid_positions_from_centroid(self) -> np.ndarray:
        """
        Get valid positions from the centroid that meet minimum coverage criteria.

        Returns:
            Array of positions in the centroid that meet coverage criteria
        """
        if self.sample_count == 0:
            return np.array([], dtype=np.uint32)

        # Convert GPU arrays to CPU for operations
        cpu_mC_sum = self._to_cpu(self.mC_sum)
        cpu_uC_sum = self._to_cpu(self.uC_sum)
        cpu_N_sum = self._to_cpu(self.N_sum)
        total_coverage = cpu_mC_sum + cpu_uC_sum
        valid_mask = (total_coverage >= self.min_coverage) & (cpu_N_sum > 0)

        valid_pos = self.global_pos[valid_mask]
        return self._to_cpu(valid_pos)

    def get_common_positions(self, sample: MethylSample) -> np.ndarray:
        """
        Get positions that are common between the centroid's valid positions and a sample.

        Args:
            sample: MethylSample instance containing sample data

        Returns:
            Array of positions that are both valid in centroid and present in sample
        """
        if MethylFrame is None:
            raise ImportError("MethylFrame is not available. Please install methyl_utils package.")

        # Check if it's a MethylFrame instance (new architecture)
        from methyl_utils.core.methyl_frame import MethylFrame
        if not isinstance(sample, MethylFrame):
            raise TypeError(f"Expected MethylFrame (MethylSample/MethylBasicCentroid/MethylExtendedCentroid), got {type(sample)}")

        # Get centroid's valid positions
        valid_pos = self.get_valid_positions_from_centroid()

        sample_pos = sample.pos

        # Ensure both arrays are CPU numpy arrays for comparison
        cpu_valid_pos = np.asarray(valid_pos, dtype=np.uint32)
        cpu_sample_pos = np.asarray(sample_pos, dtype=np.uint32)

        # Find intersection of valid centroid positions and sample positions
        common_pos = np.intersect1d(cpu_valid_pos, cpu_sample_pos)

        return common_pos

    def align_sample_to_centroid(self, sample: MethylSample) -> Tuple[np.ndarray, np.ndarray]:
        """
        Align a sample to the centroid's valid positions and return sample data for common positions.

        Args:
            sample: MethylSample instance containing sample data

        Returns:
            Tuple of (sample_mC, sample_uC) for positions common to both sample and centroid
        """
        if MethylFrame is None:
            raise ImportError("MethylFrame is not available. Please install methyl_utils package.")

        # Check if it's a MethylFrame instance (new architecture)
        from methyl_utils.core.methyl_frame import MethylFrame
        if not isinstance(sample, MethylFrame):
            raise TypeError(f"Expected MethylFrame (MethylSample/MethylBasicCentroid/MethylExtendedCentroid), got {type(sample)}")

        common_pos = self.get_common_positions(sample)

        if len(common_pos) == 0:
            return np.array([], dtype=np.uint32), np.array([], dtype=np.uint32)
        
        sorted_pos = sample.pos
        mC = sample.mC
        uC = sample.uC
        
        common_indices = np.searchsorted(sorted_pos, common_pos)
        
        # Check if all common positions exist in sample
        # Ensure both arrays are CPU numpy arrays for comparison
        cpu_sorted_pos_at_indices = np.asarray(sorted_pos[common_indices], dtype=np.uint32)
        cpu_common_pos = np.asarray(common_pos, dtype=np.uint32)
                    
        valid_mask = (common_indices < len(sorted_pos)) & (cpu_sorted_pos_at_indices == cpu_common_pos)

        # Ensure returned arrays are NumPy arrays, not CuPy arrays
        result_mC = mC[common_indices[valid_mask]]
        result_uC = uC[common_indices[valid_mask]]

        return self._to_cpu(result_mC), self._to_cpu(result_uC)

    def get_position_range(self) -> Tuple[np.uint32, np.uint32]:
        """
        Get the current position range.
        
        Returns:
            tuple: (min_pos, max_pos) if initialized, raises RuntimeError otherwise
            
        Raises:
            RuntimeError: If the aligner has not been initialized with data
        """
        if not self.is_initialized:
            raise RuntimeError("Position aligner has not been initialized with data")
        return self._to_cpu(self.global_pos)[0], self._to_cpu(self.global_pos)[-1]

    def get_sample_count(self) -> int:
        """
        Get the number of samples that have contributed to the centroid.
        
        Returns:
            int: Number of samples currently in the aligner
        """
        return self.sample_count

    def reset(self):
        """
        Reset the position aligner to initial state, clearing all sparse data.
        """
        self.global_pos = None
        self.mC_sum = None
        self.uC_sum = None
        self.N_sum = None
        self.methylation_level_sum = None
        self.methylation_level_sq_sum = None
        self.log_methylation_sum = None
        self.log_one_minus_methylation_sum = None
        self.tnc = None
        
        self.sample_count = 0
        self.active_samples.clear()
        self.valid_pos = None

    def get_alignment_stats(self) -> dict:
        """
        Get comprehensive statistics about the current alignment state.
        
        This method provides a complete overview of the aligner's current state,
        including position ranges, sample counts, coverage information, and
        methylation statistics.

        Returns:
            dict: Dictionary containing:
                - position_range: Tuple of (min_pos, max_pos) or None if not initialized
                - total_positions: Total number of positions in the range
                - valid_positions: Number of positions meeting coverage criteria
                - sample_count: Number of samples in the aligner
                - min_coverage: Current minimum coverage threshold
                - gpu_acceleration: Whether GPU acceleration is enabled
                - methylation_stats: Group methylation statistics (if available)

        Example:
            >>> stats = aligner.get_alignment_stats()
            >>> print(f"Position range: {stats['position_range']}")
            >>> print(f"Valid positions: {stats['valid_positions']}")
            >>> print(f"Sample count: {stats['sample_count']}")
            >>> if stats['methylation_stats']:
            ...     print(f"Group methylation: {stats['methylation_stats']['group_avg_methylation']:.3f}")
        """
        if not self.is_initialized:
            return {
                "position_range": None,
                "total_positions": 0,
                "valid_positions": 0,
                "sample_count": 0,
                "min_coverage": self.min_coverage,
                "gpu_acceleration": bool(self.gpu_available),
                "methylation_stats": None,
            }

        valid_pos, _, _, _ = self.compute_valid_positions()

        # Get methylation statistics if available
        methylation_stats = None
        if self.methylation_stats_available and self.sample_count > 0:
            methylation_stats = self.get_group_methylation_statistics()

        # Calculate centroid-specific statistics
        centroid_min_pos = int(np.min(self._to_cpu(valid_pos))) if len(valid_pos) > 0 else None
        centroid_max_pos = int(np.max(self._to_cpu(valid_pos))) if len(valid_pos) > 0 else None
        centroid_position_range = (centroid_min_pos, centroid_max_pos) if centroid_min_pos is not None else None
        
        return {
            "position_range": centroid_position_range,  # Centroid position range, not full dataset
            "total_positions": len(valid_pos),  # Total positions in centroid
            "valid_positions": len(valid_pos),  # Number of valid positions (same as total for centroid)
            "sample_count": self.sample_count,
            "min_coverage": self.min_coverage,
            "gpu_acceleration": bool(self.gpu_available),
            "methylation_stats": methylation_stats,
        }

    def get_alignment_stats_model(self) -> AlignmentStats:
        """
        Get alignment statistics as a Pydantic model.
        
        Returns:
            AlignmentStats: Structured alignment statistics
        """
        stats_dict = self.get_alignment_stats()
        
        # Convert position_range tuple to proper format
        position_range = None
        if stats_dict["position_range"] is not None:
            min_pos, max_pos = stats_dict["position_range"]
            position_range = (int(min_pos), int(max_pos))
        
        return AlignmentStats(
            position_range=position_range,
            total_positions=stats_dict["total_positions"],
            valid_positions=stats_dict["valid_positions"],
            sample_count=stats_dict["sample_count"],
            min_coverage=stats_dict["min_coverage"],
            gpu_acceleration=stats_dict["gpu_acceleration"],
            memory_usage_mb=self.memory_usage_mb,
            is_initialized=self.is_initialized,
            has_data=self.has_data,
            methylation_stats_available=self.methylation_stats_available
        )

    def get_group_methylation_stats_model(self) -> Optional[GroupMethylationStats]:
        """
        Get group methylation statistics as a Pydantic model.
        
        Returns:
            GroupMethylationStats: Structured group methylation statistics, or None if not available
        """
        if not self.methylation_stats_available or not self.has_data:
            return None
        
        stats_dict = self.get_group_methylation_statistics()
        return GroupMethylationStats(**stats_dict)

    def get_position_methylation_stats_models(self) -> List[PositionMethylationStats]:
        """
        Get per-position methylation statistics as Pydantic models.
        
        Returns:
            List[PositionMethylationStats]: List of structured position methylation statistics
        """
        if not self.methylation_stats_available or not self.has_data:
            return []
        
        try:
            valid_pos, avg_levels, means, stdevs, N = self.compute_methylation_statistics()
            
            position_stats = []
            for i in range(len(valid_pos)):
                # Find index in global_pos
                pos = valid_pos[i]
                global_idx = np.searchsorted(self._to_cpu(self.global_pos), pos)
                
                mC_sum_val = self.mC_sum[global_idx]
                uC_sum_val = self.uC_sum[global_idx]
                
                position_stat = PositionMethylationStats(
                    position=int(pos),
                    avg_methylation_level=float(avg_levels[i]),
                    methylation_mean=float(means[i]),
                    methylation_stdev=float(stdevs[i]),
                    sample_count=int(N[i]),
                    total_coverage=int(mC_sum_val + uC_sum_val),
                    mC_sum=int(mC_sum_val),
                    uC_sum=int(uC_sum_val)
                )
                position_stats.append(position_stat)
            
            return position_stats
        except RuntimeError:
            return []

    def create_analysis_results(
        self, 
        analysis_id: str, 
        metadata: Optional[dict] = None
    ) -> MethylationAnalysisResults:
        """
        Create complete analysis results as a Pydantic model.
        
        Args:
            analysis_id: Unique identifier for this analysis
            metadata: Additional metadata about the analysis
            
        Returns:
            MethylationAnalysisResults: Complete analysis results
        """
        # Get alignment stats model
        alignment_stats_model = self.get_alignment_stats_model()
        
        # Get group stats model if available
        group_stats_model = None
        if self.methylation_stats_available and self.has_data:
            group_stats_model = self.get_group_methylation_stats_model()
        
        # Get position stats models if available
        position_stats_models = []
        if self.methylation_stats_available and self.has_data:
            position_stats_models = self.get_position_methylation_stats_models()
        
        # Create metadata
        metadata = metadata or {}
        
        return MethylationAnalysisResults(
            analysis_id=analysis_id,
            alignment_stats=alignment_stats_model,
            group_stats=group_stats_model,
            position_stats=position_stats_models,
            metadata=metadata
        )

    def save_analysis_results(
        self, 
        analysis_id: str, 
        filepath: Path, 
        metadata: Optional[dict] = None
    ) -> None:
        """
        Create and save analysis results to a JSON file.
        
        Args:
            analysis_id: Unique identifier for this analysis
            filepath: Path to save the JSON file
            metadata: Additional metadata about the analysis
        """
        results = self.create_analysis_results(analysis_id, metadata)
        results.save_to_json(filepath)
        logger.info(f"Analysis results saved to: {filepath}")

    def load_extended_centroid(self, centroid: MethylSample) -> bool:
        """
        Load extended centroid data from MethylSample into accumulators.

        Args:
            centroid: MethylSample instance containing centroid data

        Returns:
            bool: True if successful, False otherwise

        Example:
            >>> centroid = MethylSample.load_from_h5("centroid.h5")
            >>> success = aligner.load_extended_centroid(centroid)
            >>> if success:
            ...     print("Centroid state loaded successfully")
        """
        if MethylFrame is None:
            raise ImportError("MethylFrame is not available. Please install methyl_utils package.")
        
        if not isinstance(centroid, MethylFrame):
            raise TypeError(f"Expected MethylFrame (MethylSample/MethylBasicCentroid/MethylExtendedCentroid), got {type(centroid)}")
        
        if not centroid.is_centroid:
            raise ValueError("Provided MethylSample is not a centroid (missing N field)")
        
        try:
            positions = centroid.pos
            avg_mC = centroid.mC
            avg_uC = centroid.uC
            N = centroid.N
            
            self.expand_global_positions(positions)
            
            # Find indices in global_pos for loaded positions
            indices = np.searchsorted(self._to_cpu(self.global_pos), positions)
            
            self.mC_sum[indices] = (avg_mC * N).astype(np.uint32)
            self.uC_sum[indices] = (avg_uC * N).astype(np.uint32)
            self.N_sum[indices] = N.astype(np.uint32)
            
            if centroid.Sx is not None and centroid.Sx2 is not None:
                self.methylation_level_sum[indices] = centroid.Sx
                self.methylation_level_sq_sum[indices] = centroid.Sx2
            else:
                ml = avg_mC / (avg_mC + avg_uC)
                self.methylation_level_sum[indices] = ml * N
                self.methylation_level_sq_sum[indices] = (ml ** 2) * N
            
            if centroid.log_x_sum is not None and centroid.log_1_minus_x_sum is not None:
                self.log_methylation_sum[indices] = centroid.log_x_sum
                self.log_one_minus_methylation_sum[indices] = centroid.log_1_minus_x_sum
            else:
                epsilon = 1e-10
                ml = avg_mC / (avg_mC + avg_uC)
                safe_ml = np.clip(ml, epsilon, 1 - epsilon)
                self.log_methylation_sum[indices] = np.log(safe_ml) * N
                self.log_one_minus_methylation_sum[indices] = np.log(1 - safe_ml) * N
            
            self.tnc[indices] = centroid.tnc
            
            self.sample_count = int(np.max(N)) if len(N) > 0 else 0
            
            return True
                
        except Exception as e:
            logger.error(f"Error loading centroid data: {e}")
            return False

    def get_gpu_memory_info(self) -> dict:
        """
        Get GPU memory usage information for monitoring large datasets.
        
        Returns:
            Dictionary with GPU memory information
        """
        if not self.gpu_available:
            return {"gpu_available": False, "error": "GPU not available"}
        
        try:
            from methyl_utils.gpu_detection import get_memory_info
            memory_info = get_memory_info()
            
            # Calculate memory usage for our arrays
            array_memory_mb = 0
            if self.is_initialized:
                array_memory_mb = self.memory_usage_mb
            
            return {
                "gpu_available": True,
                "gpu_memory_used_bytes": memory_info.get('gpu_memory_used', 0),
                "gpu_memory_total_bytes": memory_info.get('gpu_memory_total', 0),
                "gpu_memory_free_bytes": memory_info.get('gpu_memory_free', 0),
                "gpu_memory_used_gb": memory_info.get('gpu_memory_used', 0) / (1024**3),
                "gpu_memory_total_gb": memory_info.get('gpu_memory_total', 0) / (1024**3),
                "gpu_memory_free_gb": memory_info.get('gpu_memory_free', 0) / (1024**3),
                "aligner_memory_mb": array_memory_mb,
                "memory_utilization_percent": (memory_info.get('gpu_memory_used', 0) / max(memory_info.get('gpu_memory_total', 1), 1)) * 100
            }
        except Exception as e:
            return {"gpu_available": True, "error": f"Failed to get memory info: {e}"}
    
    def cleanup_gpu_memory(self) -> bool:
        """
        Clean up GPU memory to free unused blocks.
        
        Returns:
            True if cleanup was successful, False otherwise
        """
        if not self.gpu_available:
            return False
        
        try:
            from methyl_utils.gpu_detection import cleanup_gpu_memory
            return cleanup_gpu_memory()
        except Exception as e:
            logger.warning(f"GPU memory cleanup failed: {e}")
            return False
    
    def optimize_for_large_datasets(self) -> dict:
        """
        Optimize the aligner for handling millions of positions.
        
        Returns:
            Dictionary with optimization recommendations and status
        """
        recommendations = []
        status = {"optimized": True}
        
        if not self.gpu_available:
            recommendations.append("Enable GPU acceleration for better performance with large datasets")
            status["optimized"] = False
        
        if self.is_initialized:
            total_positions = self.total_positions
            if total_positions > 1_000_000:
                recommendations.append(f"Large dataset detected ({total_positions:,} positions). Consider using GPU acceleration.")
                
                # Check memory usage
                memory_info = self.get_gpu_memory_info()
                if memory_info.get("gpu_available", False):
                    utilization = memory_info.get("memory_utilization_percent", 0)
                    if utilization > 80:
                        recommendations.append(f"High GPU memory usage ({utilization:.1f}%). Consider cleaning up memory.")
                        status["optimized"] = False
            
            # Check if we should pre-allocate more memory
            if total_positions > 10_000_000 and self.gpu_available:
                recommendations.append("Very large dataset detected. Consider increasing GPU memory allocation.")
        
        return {
            "optimized": status["optimized"],
            "recommendations": recommendations,
            "total_positions": self.total_positions if self.is_initialized else 0,
            "gpu_available": self.gpu_available,
            "memory_info": self.get_gpu_memory_info() if self.gpu_available else None
        }

    def get_debug_info(self) -> dict:
        """
        Get debugging information about the current state of the position aligner.
        
        Returns:
            Dictionary with debug information
        """
        info = {
            "sample_count": self.sample_count,
            "active_samples": len(self.active_samples),
            "is_initialized": self.is_initialized,
            "has_data": self.has_data,
            "coverage_threshold": self.coverage_threshold,
            "gpu_acceleration": self.gpu_acceleration,
            "memory_usage_mb": self.memory_usage_mb
        }
        
        if self.is_initialized:
            cpu_global = self._to_cpu(self.global_pos)
            info.update({
                "global_pos_shape": cpu_global.shape,
                "total_positions": self.total_positions,
                "valid_positions": self.valid_positions,
                "position_range": self.position_range,
                "mC_sum_shape": self.mC_sum.shape if self.mC_sum is not None else None,
                "uC_sum_shape": self.uC_sum.shape if self.uC_sum is not None else None,
                "N_sum_shape": self.N_sum.shape if self.N_sum is not None else None,
                "methylation_stats_available": self.methylation_stats_available
            })
        
        # Add GPU memory info
        if self.gpu_available:
            info["gpu_memory_info"] = self.get_gpu_memory_info()
        
        return info


def align_multiple_samples(
    samples: List[MethylSample], min_coverage: int = 4, use_gpu: bool = True
) -> PositionAligner:
    """
    Convenience function to align multiple samples at once.

    Args:
        samples: List of MethylSample instances
        min_coverage: Minimum coverage threshold for valid positions
        use_gpu: Whether to use GPU acceleration if available

    Returns:
        PositionAligner instance with all samples aligned
    """
    if MethylSample is None:
        raise ImportError("MethylSample is not available. Please install methyl_utils package.")
    
    aligner = PositionAligner(max_samples=len(samples), use_gpu=use_gpu)
    aligner.set_min_coverage(min_coverage)

    # Precollect all positions
    all_pos = []
    for sample in samples:
        if isinstance(sample, MethylFrame):
            all_pos.append(sample.pos)
    
    if all_pos:
        unique_pos = np.unique(np.concatenate(all_pos))
        aligner.expand_global_positions(unique_pos)

    for i, sample in enumerate(samples):
        if isinstance(sample, MethylFrame):
            aligner.add_sample(sample, i)

    return aligner