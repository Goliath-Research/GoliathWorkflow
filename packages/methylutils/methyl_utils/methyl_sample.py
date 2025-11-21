from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union, Tuple, Dict, Any, List
import struct
import numpy as np
import pandas as pd
import json  # For serialization if needed


# Import HDF5 dependencies - these should be available in the container
try:
    import hdf5plugin   # noqa: F401 - Must be imported before h5py
    import h5py
    HDF5_AVAILABLE = True
except ImportError:
    HDF5_AVAILABLE = False
    h5py = None
    hdf5plugin = None

# Import GPU dependencies
try:
    from methyl_utils.gpu_detection import cupy as cp
except ImportError:
    cp = None

# ---------- Bit layout (LSB-first) ----------
# Byte layout: bits 0..4 = tnc (5 bits), bits 5..6 = context (2 bits), bit 7 = strand (1 bit)
TNC_MASK     = 0b1_1111      # 5 bits
CONTEXT_MASK = 0b11          # 2 bits
STRAND_MASK  = 0b1           # 1 bit

CONTEXT_SHIFT = 5
STRAND_SHIFT  = 7

# ---------- Methylation Data Types ----------
# Basic sample dtype (pos, mC, uC, tnc)
METHYL_SAMPLE_DTYPE = [
    ("pos", np.uint32),
    ("mC", np.uint32),
    ("uC", np.uint32),
    ("tnc", np.uint8),
]

# Basic centroid dtype (sample + N)
METHYL_CENTROID_DTYPE = [
    ("pos", np.uint32),
    ("mC", np.uint32),
    ("uC", np.uint32),
    ("tnc", np.uint8),
    ("N", np.uint32),  # Number of samples contributing to each position
]

# Extended centroid dtype (centroid + Sx, Sx2, log_x_sum, log_1_minus_x_sum)
METHYL_EXTENDED_CENTROID_DTYPE = [
    ("pos", np.uint32),
    ("mC", np.uint32),
    ("uC", np.uint32),
    ("tnc", np.uint8),
    ("N", np.uint32),  # Number of samples contributing to each position
    ("Sx", np.float32),  # Sum of methylation levels
    ("Sx2", np.float32),  # Sum of squared methylation levels
    ("log_x_sum", np.float32),  # Sum of log(methylation_level) for Beta distribution
    ("log_1_minus_x_sum", np.float32),  # Sum of log(1 - methylation_level) for Beta distribution
]

# Type aliases for better type hints (compatible with older Python versions)
MethylSampleDtype = np.ndarray
MethylCentroidDtype = np.ndarray
MethylExtendedCentroidDtype = np.ndarray

def get_methyl_dtype(extended: bool = False) -> list:
    """
    Get the appropriate methylation dtype based on the data type.
    
    Args:
        extended: If True, return extended centroid dtype with statistics
        
    Returns:
        List of (field_name, dtype) tuples for numpy structured array
    """
    if extended:
        return METHYL_EXTENDED_CENTROID_DTYPE
    else:
        return METHYL_CENTROID_DTYPE

def _pack_tnc_byte(tnc: int, context: int, strand: int) -> int:
    # Range checks (raise ValueError on bad inputs)
    if not (0 <= tnc <= TNC_MASK):         
        raise ValueError(f"tnc out of range [0..31]: {tnc}")
    if not (0 <= context <= CONTEXT_MASK): 
        raise ValueError(f"context out of range [0..3]: {context}")
    if not (0 <= strand <= STRAND_MASK):   
        raise ValueError(f"strand out of range [0..1]: {strand}")

    return (tnc & TNC_MASK) | ((context & CONTEXT_MASK) << CONTEXT_SHIFT) | ((strand & STRAND_MASK) << STRAND_SHIFT)

def _unpack_tnc_byte(b: int) -> tuple[int, int, int]:
    tnc     =  b & TNC_MASK
    context = (b >> CONTEXT_SHIFT) & CONTEXT_MASK
    strand  = (b >> STRAND_SHIFT) & STRAND_MASK

    return tnc, context, strand

# Precompile struct for perf; little-endian: <IHHBB
# fields: pos(uint32), mC(uint16), uC(uint16), tnc_byte(uint8), pad(uint8)
_RECORD_STRUCT = struct.Struct("<IHHBB")
RECORD_SIZE = _RECORD_STRUCT.size  # should be 10

@dataclass(slots=True)
class TNCBits:
    """Holds the 3 bitfields and knows how to pack/unpack to a single byte."""
    tnc: int       # 0..31
    context: int   # 0..3
    strand: int    # 0..1

    def to_byte(self) -> int:
        return _pack_tnc_byte(self.tnc, self.context, self.strand)
    
    @classmethod
    def from_byte(cls, b: int) -> TNCBits:
        tnc, context, strand = _unpack_tnc_byte(b)
        return cls(tnc=tnc, context=context, strand=strand)


@dataclass(slots=True)
class MethylSample:
    """
    Represents a methylation sample - individual sample with methylation counts.

    Contains basic methylation data: genomic positions, methylated counts,
    unmethylated counts, and trinucleotide context information.
    """
    # Core methylation data (always present)
    pos: np.ndarray  # uint32 - genomic positions
    mC: np.ndarray   # uint32 - methylated counts
    uC: np.ndarray   # uint32 - unmethylated counts
    tnc: np.ndarray  # uint8 - trinucleotide context + strand info

    # Metadata (optional)
    _metadata: Optional[Dict[str, Any]]
    
    def __post_init__(self):
        """Validate data types after initialization."""
        if self._metadata is None:
            self._metadata = {}
        self._validate_data_types()

    def _validate_data_types(self):
        """Validate that all arrays have the correct data types."""
        # Core arrays should always be present
        assert self.pos.dtype == np.uint32, f"pos should be uint32, got {self.pos.dtype}"
        assert self.mC.dtype == np.uint32, f"mC should be uint32, got {self.mC.dtype}"
        assert self.uC.dtype == np.uint32, f"uC should be uint32, got {self.uC.dtype}"
        assert self.tnc.dtype == np.uint8, f"tnc should be uint8, got {self.tnc.dtype}"

        # All arrays should have the same length
        expected_length = len(self.pos)
        assert len(self.mC) == expected_length, f"mC length {len(self.mC)} != pos length {expected_length}"
        assert len(self.uC) == expected_length, f"uC length {len(self.uC)} != pos length {expected_length}"
        assert len(self.tnc) == expected_length, f"tnc length {len(self.tnc)} != pos length {expected_length}"

    # Base class properties
    @property
    def sample_type(self) -> str:
        """Determine the type of sample."""
        return "sample"

    @property
    def is_centroid(self) -> bool:
        """Check if this is a centroid."""
        return False

    @property
    def is_extended_centroid(self) -> bool:
        """Check if this is an extended centroid."""
        return False
    
    # Metadata properties (read-write for easy manipulation)
    @property
    def laboratory(self) -> Optional[str]:
        """Get laboratory name from metadata."""
        return self._metadata.get("laboratory") if self._metadata else None
    
    @laboratory.setter
    def laboratory(self, value: str):
        """Set laboratory name in metadata."""
        if self._metadata is None:
            self._metadata = {}
        self._metadata["laboratory"] = value
    
    @property
    def disease(self) -> Optional[str]:
        """Get disease from metadata."""
        return self._metadata.get("disease") if self._metadata else None
    
    @disease.setter
    def disease(self, value: str):
        """Set disease in metadata."""
        if self._metadata is None:
            self._metadata = {}
        self._metadata["disease"] = value
    
    @property
    def group(self) -> Optional[str]:
        """Get group identifier from metadata."""
        return self._metadata.get("group") if self._metadata else None
    
    @group.setter
    def group(self, value: str):
        """Set group identifier in metadata."""
        if self._metadata is None:
            self._metadata = {}
        self._metadata["group"] = value
    
    @property
    def batch(self) -> Optional[str]:
        """Get batch identifier from metadata."""
        return self._metadata.get("batch") if self._metadata else None
    
    @batch.setter
    def batch(self, value: str):
        """Set batch identifier in metadata."""
        if self._metadata is None:
            self._metadata = {}
        self._metadata["batch"] = value
    
    @property
    def chromosome(self) -> Optional[str]:
        """Get chromosome from metadata."""
        return self._metadata.get("chromosome") if self._metadata else None
    
    @chromosome.setter
    def chromosome(self, value: str):
        """Set chromosome in metadata."""
        if self._metadata is None:
            self._metadata = {}
        self._metadata["chromosome"] = value
    
    @property
    def context(self) -> Optional[str]:
        """Get methylation context from metadata."""
        return self._metadata.get("context") if self._metadata else None
    
    @context.setter
    def context(self, value: str):
        """Set methylation context in metadata."""
        if self._metadata is None:
            self._metadata = {}
        self._metadata["context"] = value
    
    @property
    def metadata(self) -> Optional[Dict[str, Any]]:
        """Get all metadata."""
        return self._metadata
    
    @metadata.setter
    def metadata(self, value: Dict[str, Any]):
        """Set all metadata at once."""
        self._metadata = value
    
    @property
    def samples(self) -> List[str]:
        """List of sample file paths that form this centroid (from metadata)."""
        if not self._metadata:
            return []
        # Check for 'sample_paths' first, fall back to 'samples_used'
        return self._metadata.get('sample_paths') or self._metadata.get('samples_used', [])

    @property
    def group_name(self) -> str:
        """Group name or label for this centroid (from metadata)."""
        return self._metadata.get('group_name', 'Unknown') if self._metadata else 'Unknown'

    @property
    def metadata(self) -> Optional[Dict[str, Any]]:
        """Full metadata dictionary (read-only)."""
        return self._metadata

    # Utility properties for memory and size calculations
    @property
    def position_count(self) -> int:
        """
        Number of genomic positions in this sample.

        Returns:
            Integer count of positions
        """
        return len(self.pos)

    @property
    def memory_usage_mb(self) -> float:
        """
        Total memory usage of this sample in megabytes.

        Calculates memory used by all arrays (pos, mC, uC, tnc, N, Sx, Sx2, log_x_sum, log_1_minus_x_sum).

        Returns:
            Memory usage in MB
        """
        total_bytes = 0

        # Core arrays (always present)
        for attr in ['pos', 'mC', 'uC', 'tnc']:
            if hasattr(self, attr):
                arr = getattr(self, attr)
                if hasattr(arr, 'nbytes'):
                    total_bytes += arr.nbytes

        # Centroid arrays (optional)
        for attr in ['N', 'Sx', 'Sx2', 'log_x_sum', 'log_1_minus_x_sum']:
            if hasattr(self, attr):
                arr = getattr(self, attr)
                if arr is not None and hasattr(arr, 'nbytes'):
                    total_bytes += arr.nbytes

        return total_bytes / (1024 * 1024)  # Convert to MB

    @property
    def bytes_per_position(self) -> float:
        """
        Average bytes per genomic position.

        Useful for estimating how many samples can fit in GPU memory or for cache sizing.
        This gives the memory footprint per position across all arrays.

        Returns:
            Average bytes per position
        """
        if self.position_count == 0:
            return 0.0
        return (self.memory_usage_mb * 1024 * 1024) / self.position_count

    @property
    def coverage_stats(self) -> dict:
        """
        Coverage statistics for this sample.

        Returns:
            Dictionary with coverage statistics:
            - min_coverage: Minimum coverage across positions
            - max_coverage: Maximum coverage across positions
            - mean_coverage: Mean coverage across positions
            - median_coverage: Median coverage across positions
            - positions_with_coverage: Number of positions with non-zero coverage
            - coverage_distribution: Coverage values for analysis
        """
        coverage = self.mC + self.uC

        return {
            'min_coverage': int(np.min(coverage)) if len(coverage) > 0 else 0,
            'max_coverage': int(np.max(coverage)) if len(coverage) > 0 else 0,
            'mean_coverage': float(np.mean(coverage)) if len(coverage) > 0 else 0.0,
            'median_coverage': float(np.median(coverage)) if len(coverage) > 0 else 0.0,
            'positions_with_coverage': int(np.sum(coverage > 0)),
            'total_positions': self.position_count,
            'coverage_fraction': float(np.sum(coverage > 0) / self.position_count) if self.position_count > 0 else 0.0
        }

    @property
    def methylation_stats(self) -> dict:
        """
        Methylation level statistics for this sample.

        Returns:
            Dictionary with methylation statistics:
            - mean_methylation: Mean methylation level (0-1)
            - positions_covered: Number of positions with coverage > 0
            - methylation_distribution: Methylation levels for analysis
        """
        coverage = self.mC + self.uC
        valid_positions = coverage > 0

        if not np.any(valid_positions):
            return {
                'mean_methylation': 0.0,
                'positions_covered': 0,
                'methylation_levels': np.array([])
            }

        methylation_levels = np.zeros(len(coverage), dtype=np.float32)
        methylation_levels[valid_positions] = self.mC[valid_positions] / coverage[valid_positions]

        return {
            'mean_methylation': float(np.mean(methylation_levels[valid_positions])),
            'positions_covered': int(np.sum(valid_positions)),
            'methylation_levels': methylation_levels[valid_positions]
        }

    def prob_belongs(self, sample: 'MethylSample', use_gpu: bool = True) -> float:
        """
        Test if a sample belongs to this centroid using statistical hypothesis testing.

        Automatically chooses the appropriate statistical approach based on centroid size:
        - CLT (Normal approximation) for large centroids (N > 30 samples)
        - Beta distribution exact calculation for small centroids (N ≤ 30 samples)

        The method performs a statistical test to determine if a sample belongs to the
        centroid's distribution, using the most appropriate statistical framework.

        Args:
            sample: Test sample to evaluate
            use_gpu: Whether to use GPU acceleration if available (default: True)

        Returns:
            p_value: Two-tailed p-value from statistical test
                     - p > 0.05: Sample likely belongs to this centroid
                     - p < 0.05: Sample likely does not belong (outlier/different group)

        Example:
            >>> centroid_healthy = MethylSample.load_from_h5("healthy.h5")
            >>> test_sample = MethylSample.load_from_h5("patient.h5")
            >>> p_value = centroid_healthy.prob_belongs(test_sample)
            >>> print(f"P-value: {p_value:.4f}")
        """
        # Use the p_value method which implements the appropriate statistical test
        return self.p_value(sample, use_gpu)

    def z_score(self, sample: 'MethylSample', use_gpu: bool = True) -> float:
        """
        Calculate Z-score for statistical test of sample belonging to this centroid.

        Automatically chooses between:
        - CLT (Normal approximation) for large centroids (N > 30)
        - Beta distribution exact calculation for small centroids (N ≤ 30)

        Args:
            sample: Test sample to evaluate
            use_gpu: Whether to use GPU acceleration if available (default: True)

        Returns:
            z_score: Z-statistic measuring deviation from expected distribution
        """
        try:
            from methyl_utils.beta_analytics import compute_beta_mean, compute_beta_variance, beta_log_pdf
            from methyl_utils.gpu_detection import is_gpu_available
            from methyl_utils.metrics_core import DistanceCalculator
            from methyl_utils.gpu_utils import _prepare_arrays_for_backend, _ensure_cpu_output
        except ImportError:
            # Handle relative imports when running as module
            from .beta_analytics import compute_beta_mean, compute_beta_variance, beta_log_pdf
            from .gpu_detection import is_gpu_available
            from .metrics_core import DistanceCalculator
            from .gpu_utils import _prepare_arrays_for_backend, _ensure_cpu_output

        # Determine if GPU should be used
        use_gpu = use_gpu and is_gpu_available()
        calc = DistanceCalculator()
        xp = calc.get_backend(use_gpu)[0]  # Get numpy or cupy

        # 1. Find common positions
        common_pos = np.intersect1d(self.pos, sample.pos, assume_unique=True)
        if len(common_pos) == 0:
            return 0.0  # No overlap = neutral score

        # 2. Get indices for alignment
        self_idx = np.searchsorted(self.pos, common_pos)
        sample_idx = np.searchsorted(sample.pos, common_pos)

        # 3. Choose statistical approach based on centroid size
        if self.is_centroid and self.N is not None:
            # Check average sample size across common positions
            avg_sample_size = np.mean(self.N[self_idx])
            use_clt = avg_sample_size > 30  # Use CLT for large sample sizes
        else:
            use_clt = True  # Default to CLT if no N information available

        # 4. Get centroid's Beta parameters
        alpha = self.alpha[self_idx]
        beta_param = self.beta[self_idx]

        # 5. Get sample's methylation levels
        sample_mC = sample.mC[sample_idx]
        sample_uC = sample.uC[sample_idx]
        sample_total = sample_mC + sample_uC

        # Filter valid positions (coverage > 0)
        valid = sample_total > 0
        if np.sum(valid) == 0:
            return 0.0  # No valid positions = neutral score

        # Valid methylation levels
        sample_meth = sample_mC[valid] / sample_total[valid]
        alpha_valid = alpha[valid]
        beta_valid = beta_param[valid]

        if use_clt:
            # CLT approach for large centroids (N > 30)
            centroid_mean = compute_beta_mean(alpha_valid, beta_valid)
            centroid_var = compute_beta_variance(alpha_valid, beta_valid)

            # Transfer to GPU if requested
            if use_gpu:
                arrays, _ = _prepare_arrays_for_backend(
                    [sample_meth, centroid_mean, centroid_var],
                    calc,
                    use_gpu
                )
                sample_meth_gpu, centroid_mean_gpu, centroid_var_gpu = arrays
            else:
                sample_meth_gpu = sample_meth
                centroid_mean_gpu = centroid_mean
                centroid_var_gpu = centroid_var

            # Compute Z-score using CLT
            sum_observed = xp.sum(sample_meth_gpu)
            sum_expected = xp.sum(centroid_mean_gpu)
            sum_variance = xp.sum(centroid_var_gpu**2)  # Variance of sum

            # Convert back to CPU for final computation
            if use_gpu:
                sum_observed = float(_ensure_cpu_output(sum_observed, calc, use_gpu))
                sum_expected = float(_ensure_cpu_output(sum_expected, calc, use_gpu))
                sum_variance = float(_ensure_cpu_output(sum_variance, calc, use_gpu))

            if sum_variance < 1e-12:
                return 0.0  # No variance = perfect match

            z_score = (sum_observed - sum_expected) / np.sqrt(sum_variance)

        else:
            # Beta distribution exact approach for small centroids (N ≤ 30)
            # Compute log-likelihood of sample under centroid's Beta distribution
            sample_meth_clipped = np.clip(sample_meth, 1e-6, 1-1e-6)  # Avoid boundary issues

            # Use beta_log_pdf for exact likelihood calculation
            log_likelihoods = beta_log_pdf(sample_meth_clipped, alpha_valid, beta_valid, use_gpu=use_gpu)

            # For small N, we compare to the expected log-likelihood under the centroid
            # This is equivalent to a likelihood ratio test
            # We'll use the average log-likelihood difference as our test statistic

            # Compute expected log-likelihood under the centroid (approximate using mean)
            centroid_mean = compute_beta_mean(alpha_valid, beta_valid)
            centroid_mean_clipped = np.clip(centroid_mean, 1e-6, 1-1e-6)

            expected_log_like = beta_log_pdf(centroid_mean_clipped, alpha_valid, beta_valid, use_gpu=False)

            # Test statistic: difference between observed and expected log-likelihoods
            log_like_diff = log_likelihoods - expected_log_like

            # For the Z-score, we'll standardize this difference
            # Use the variance of log-likelihoods under the centroid distribution
            # This is approximate but better than CLT for small N

            # Simple approach: use the average log-likelihood difference
            # and assume it's approximately normal for the test statistic
            mean_diff = np.mean(log_like_diff)
            std_diff = np.std(log_like_diff) if len(log_like_diff) > 1 else 1.0

            if std_diff < 1e-12:
                z_score = 0.0
            else:
                z_score = mean_diff / (std_diff / np.sqrt(len(log_like_diff)))

        return float(z_score)

    def p_value(self, sample: 'MethylSample', use_gpu: bool = True) -> float:
        """
        Calculate p-value for statistical test of sample belonging to this centroid.

        This computes the two-tailed p-value from the Z-score, representing the
        probability of observing a deviation as extreme as the sample under the
        null hypothesis that the sample belongs to this centroid.

        Args:
            sample: Test sample to evaluate
            use_gpu: Whether to use GPU acceleration if available (default: True)

        Returns:
            p_value: Two-tailed p-value from Z-test
                     - p > 0.05: Sample likely belongs to this centroid
                     - p < 0.05: Sample likely does not belong (outlier/different group)
        """
        from scipy.stats import norm
        z_score = self.z_score(sample, use_gpu)
        p_value = 2 * (1 - norm.cdf(np.abs(z_score)))
        return float(p_value)

    def statistical_test(self, sample: 'MethylSample', use_gpu: bool = True) -> Tuple[float, float]:
        """
        Calculate both Z-score and p-value for statistical test of sample belonging.

        Returns the core statistical measures used to determine if a sample belongs
        to this centroid using the Central Limit Theorem approach.

        Args:
            sample: Test sample to evaluate
            use_gpu: Whether to use GPU acceleration if available (default: True)

        Returns:
            Tuple of (z_score, p_value):
            - z_score: Z-statistic measuring deviation from expected distribution
            - p_value: Two-tailed p-value from Z-test
        """
        z_score = self.z_score(sample, use_gpu)
        p_value = self.p_value(sample, use_gpu)
        return z_score, p_value

    def add_sample(self, sample: 'MethylSample', use_gpu: bool = True) -> 'MethylSample':
        """
        Create a new centroid by adding a sample to this centroid.

        This is a convenience method that uses PositionAligner internally to
        combine this centroid with an additional sample, creating a new centroid
        with updated statistics.

        Args:
            sample: Sample to add to this centroid
            use_gpu: Whether to use GPU acceleration if available (default: True)

        Returns:
            New MethylSample centroid with the added sample

        Raises:
            ValueError: If this MethylSample is not a centroid

        Example:
            >>> centroid = MethylSample.load_from_h5("healthy_centroid.h5")
            >>> new_sample = MethylSample.load_from_h5("patient_sample.h5")
            >>> updated_centroid = centroid.add_sample(new_sample)
        """
        if not self.is_centroid:
            raise ValueError("Can only add samples to centroid objects (must have N field)")

        try:
            from .position_aligner import PositionAligner
        except ImportError:
            from position_aligner import PositionAligner

        # Create aligner and load this centroid
        aligner = PositionAligner(use_gpu=use_gpu)
        success = aligner.load_extended_centroid(self)
        if not success:
            raise RuntimeError("Failed to load centroid into aligner")

        # Add the new sample with the correct sample index
        # The sample index should be the total number of samples already in the centroid
        next_sample_index = int(np.max(self.N)) if self.N is not None else 0
        success = aligner.add_sample(sample, sample_index=next_sample_index)
        if not success:
            raise RuntimeError("Failed to add sample to centroid")

        # Create new centroid
        return aligner.get_centroid_sample()

    def remove_sample(self, sample: 'MethylSample', use_gpu: bool = True) -> 'MethylSample':
        """
        Create a new centroid by removing a sample from this centroid.

        This is a convenience method that uses PositionAligner internally to
        remove a sample from this centroid, creating a new centroid with updated
        statistics.

        Args:
            sample: Sample to remove from this centroid
            use_gpu: Whether to use GPU acceleration if available (default: True)

        Returns:
            New MethylSample centroid with the sample removed

        Raises:
            ValueError: If this MethylSample is not a centroid

        Example:
            >>> centroid = MethylSample.load_from_h5("centroid_with_outlier.h5")
            >>> outlier_sample = MethylSample.load_from_h5("outlier.h5")
            >>> cleaned_centroid = centroid.remove_sample(outlier_sample)
        """
        if not self.is_centroid:
            raise ValueError("Can only remove samples from centroid objects (must have N field)")

        try:
            from .position_aligner import PositionAligner
        except ImportError:
            from position_aligner import PositionAligner

        # Create aligner and load this centroid
        aligner = PositionAligner(use_gpu=use_gpu)
        success = aligner.load_extended_centroid(self)
        if not success:
            raise RuntimeError("Failed to load centroid into aligner")

        # Remove the sample
        success = aligner.remove_sample(sample, sample_index=0)  # Use dummy index
        if not success:
            raise RuntimeError("Failed to remove sample from centroid")

        # Create new centroid
        return aligner.get_centroid_sample()

    @classmethod
    def create_centroid_from_samples(cls, samples: List['MethylSample'], use_gpu: bool = True) -> 'MethylCentroid':
        """
        Create a centroid from a list of individual samples.

        This is a class method that provides a convenient way to build centroids
        from collections of samples without manually using PositionAligner.

        Args:
            samples: List of MethylSample objects to combine into a centroid
            use_gpu: Whether to use GPU acceleration if available (default: True)

        Returns:
            New MethylSample centroid representing the combined samples

        Raises:
            ValueError: If samples list is empty

        Example:
            >>> samples = [MethylSample.load_from_h5(f"sample_{i}.h5") for i in range(10)]
            >>> centroid = MethylSample.create_centroid_from_samples(samples)
        """
        if len(samples) == 0:
            raise ValueError("At least one sample required to create centroid")

        try:
            from .position_aligner import PositionAligner
        except ImportError:
            from position_aligner import PositionAligner

        # Create aligner and add all samples
        aligner = PositionAligner(use_gpu=use_gpu)
        for i, sample in enumerate(samples):
            success = aligner.add_sample(sample, sample_index=i)
            if not success:
                raise RuntimeError(f"Failed to add sample {i} to centroid")

        # Create centroid
        return aligner.get_centroid_sample()

    def create_aligned_sample(self, mask: np.ndarray) -> 'MethylSample':
        """
        Create a new MethylSample with only the positions specified by the mask.
        
        Args:
            mask: Boolean array indicating which positions to keep
            
        Returns:
            New MethylSample instance with filtered data
        """
        # Ensure mask is boolean and has correct length
        assert mask.dtype == bool, f"mask should be boolean, got {mask.dtype}"
        assert len(mask) == len(self.pos), f"mask length {len(mask)} != pos length {len(self.pos)}"
        
        # Create aligned sample with proper type enforcement
        aligned_sample = MethylSample(
            pos=self.pos[mask].astype(np.uint32),
            mC=self.mC[mask].astype(np.uint32),
            uC=self.uC[mask].astype(np.uint32),
            tnc=self.tnc[mask].astype(np.uint8)
        )
        
        return aligned_sample
    
    @classmethod
    def load_from_h5(cls, file_path: Union[str, Path], positions: Optional[np.ndarray] = None, debug: bool = False) -> MethylSample:
        """
        Load a methylation sample from an HDF5 file.
        Automatically detects the sample type and loads appropriate fields.
        Supports both structured array format and group format.

        Args:
            file_path: Path to the HDF5 file
            positions: Optional array of positions to filter to (ultra-performance optimization)
            debug: Enable debug output

        Returns:
            MethylSample instance with appropriate fields loaded (filtered to positions if specified)

        Raises:
            ImportError: If HDF5 dependencies are not available
        """
        if not HDF5_AVAILABLE:
            raise ImportError("HDF5 dependencies (h5py, hdf5plugin) not available. "
                            "Please ensure they are installed in your container.")

        file_path = Path(file_path)

        with h5py.File(file_path, "r") as f:
            # Load metadata from file-level attributes if available
            metadata = {}
            if f.attrs:
                import json
                for key, value in f.attrs.items():
                    # Try to parse JSON strings
                    if isinstance(value, (str, bytes)):
                        try:
                            if isinstance(value, bytes):
                                value = value.decode('utf-8')
                            parsed = json.loads(value)
                            metadata[key] = parsed
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            metadata[key] = value
                    else:
                        metadata[key] = value
            
            data_group = f["methylation_data"]

            # Try structured array format first (used in some datasets)
            if hasattr(data_group, 'dtype') and hasattr(data_group.dtype, 'names'):
                # For structured arrays, we need to find matching indices first (like group format)
                if positions is not None and len(positions) > 0:
                    # HDF5 hyperslice optimization for structured arrays
                    # Load positions to find matching indices, then use hyperslice on all fields
                    total_size = data_group.shape[0]
                    
                    # Load positions array (temporary - will be freed after finding indices)
                    if debug:
                        print(f"      🔍 Loading positions array ({total_size:,} positions) to find DMP matches...", flush=True)
                    
                    pos_full = np.asarray(data_group["pos"], dtype=np.uint32)
                    
                    if debug:
                        print(f"      ✅ Positions loaded, finding {len(positions):,} DMP matches using merge JOIN (both arrays sorted)...", flush=True)
                    
                    # Both arrays are sorted - use merge JOIN (O(n+m) instead of O(m*log(n)))
                    positions_sorted = np.sort(positions).astype(np.uint32)
                    
                    # Use intersect1d to find common positions (merge-like operation)
                    # This returns the values that are in both arrays and their indices
                    common_positions, pos_indices, dmp_indices = np.intersect1d(
                        pos_full, positions_sorted, 
                        assume_unique=True, return_indices=True
                    )
                    
                    # pos_indices are the indices in pos_full (HDF5 array) - these are what we need for hyperslice
                    matching_indices = pos_indices.astype(np.int64)
                    
                    if debug:
                        print(f"      ✅ Found {len(matching_indices):,} matching positions ({len(matching_indices)/len(positions)*100:.1f}% of requested DMPs)", flush=True)
                    
                    # Free positions array (no longer needed)
                    del pos_full
                    
                    if debug:
                        print(f"      ✅ Positions array freed, preparing hyperslice (structured array format)...", flush=True)
                        print(f"      🔍 Checking if we found any matches ({len(matching_indices):,} indices)...", flush=True)
                    
                    if len(matching_indices) == 0:
                        # No matching positions, return empty sample
                        empty_arrays = np.array([], dtype=np.uint32)
                        empty_tnc = np.array([], dtype=np.uint8)
                        return cls(
                            pos=empty_arrays,
                            mC=empty_arrays,
                            uC=empty_arrays,
                            tnc=empty_tnc,
                            N=None, Sx=None, Sx2=None,
                            log_x_sum=None, log_1_minus_x_sum=None
                        )
                    
                    if debug:
                        print(f"      🔄 Sorting indices for efficient hyperslice...", flush=True)
                    
                    # Ensure sorted for efficient hyperslice
                    matching_indices = np.sort(matching_indices)
                    
                    if debug:
                        print(f"      ✅ Indices sorted, using range loading (faster than fancy indexing for structured arrays)...", flush=True)
                    
                    # For structured arrays, fancy indexing (data_group[matching_indices]) is VERY slow
                    # Instead, load the range from min to max index, then filter in memory (much faster!)
                    min_idx = matching_indices[0]
                    max_idx = matching_indices[-1]
                    range_size = max_idx - min_idx + 1
                    
                    if debug:
                        print(f"      📥 Loading range [{min_idx:,} to {max_idx:,}] ({range_size:,} positions)...", flush=True)
                    
                    # Load contiguous range (fast!)
                    range_data = data_group[min_idx:max_idx+1]
                    
                    if debug:
                        print(f"      ✅ Range loaded, filtering to {len(matching_indices):,} matching positions...", flush=True)
                    
                    # Filter to matching positions (indices relative to range)
                    relative_indices = matching_indices - min_idx
                    structured_data = range_data[relative_indices]
                    
                    if debug:
                        print(f"      ✅ Filtered: loaded {len(matching_indices):,} positions (range loading is {range_size/len(matching_indices):.1f}x more than needed but much faster)", flush=True)
                else:
                    # Load all data when no positions specified
                    structured_data = data_group[:]

                # Extract position data
                pos = np.asarray(structured_data["pos"], dtype=np.uint32)
                mC = np.asarray(structured_data["mC"], dtype=np.uint32)
                uC = np.asarray(structured_data["uC"], dtype=np.uint32)
                tnc = np.asarray(structured_data["tnc"], dtype=np.uint8)

                # Initialize optional fields
                N: Optional[np.ndarray[np.uint32]] = None
                Sx: Optional[np.ndarray[np.float32]] = None
                Sx2: Optional[np.ndarray[np.float32]] = None
                log_x_sum: Optional[np.ndarray[np.float32]] = None
                log_1_minus_x_sum: Optional[np.ndarray[np.float32]] = None

                # Check for additional fields in structured array
                if "N" in structured_data.dtype.names:
                    N = np.asarray(structured_data["N"], dtype=np.uint32)
                if "Sx" in structured_data.dtype.names:
                    Sx = np.asarray(structured_data["Sx"], dtype=np.float32)
                if "Sx2" in structured_data.dtype.names:
                    Sx2 = np.asarray(structured_data["Sx2"], dtype=np.float32)
                if "log_x_sum" in structured_data.dtype.names:
                    log_x_sum = np.asarray(structured_data["log_x_sum"], dtype=np.float32)
                if "log_1_minus_x_sum" in structured_data.dtype.names:
                    log_1_minus_x_sum = np.asarray(structured_data["log_1_minus_x_sum"], dtype=np.float32)

            else:
                # Handle group format (original format)
                # Use hyperslice if positions are specified (performance optimization)
                use_hyperslice = False
                matching_indices = None
                
                if positions is not None and len(positions) > 0:
                    # HDF5 hyperslice optimization: load positions array to find matching indices,
                    # then use hyperslice on all arrays with those indices
                    # Loading positions temporarily is acceptable (small memory: ~17MB for 4.2M uint32)
                    
                    pos_dataset = data_group["pos"]
                    total_size = pos_dataset.shape[0]
                    
                    if debug:
                        print(f"      🔍 Loading positions array ({total_size:,} positions) to find DMP matches...", flush=True)
                    
                    # Load positions array (temporary - will be freed after finding indices)
                    pos_full = np.asarray(pos_dataset[:], dtype=np.uint32)
                    
                    if debug:
                        print(f"      ✅ Positions loaded, finding {len(positions):,} DMP matches using merge JOIN (both arrays sorted)...", flush=True)
                    
                    # Both arrays are sorted - use merge JOIN (O(n+m) instead of O(m*log(n)))
                    positions_sorted = np.sort(positions).astype(np.uint32)
                    
                    # Use intersect1d to find common positions (merge-like operation)
                    # This returns the values that are in both arrays and their indices
                    common_positions, pos_indices, dmp_indices = np.intersect1d(
                        pos_full, positions_sorted, 
                        assume_unique=True, return_indices=True
                    )
                    
                    # pos_indices are the indices in pos_full (HDF5 array) - these are what we need for hyperslice
                    matching_indices = pos_indices.astype(np.int64)
                    
                    if debug:
                        print(f"      ✅ Found {len(matching_indices):,} matching positions ({len(matching_indices)/len(positions)*100:.1f}% of requested DMPs)", flush=True)
                    
                    # Free positions array (no longer needed)
                    del pos_full
                    
                    if debug:
                        print(f"      ✅ Positions array freed, preparing hyperslice...", flush=True)
                    
                    if len(matching_indices) == 0:
                        # No matching positions, return empty sample
                        empty_arrays = np.array([], dtype=np.uint32)
                        empty_tnc = np.array([], dtype=np.uint8)
                        return cls(
                            pos=empty_arrays,
                            mC=empty_arrays,
                            uC=empty_arrays,
                            tnc=empty_tnc,
                            N=None, Sx=None, Sx2=None,
                            log_x_sum=None, log_1_minus_x_sum=None,
                            _metadata=metadata if metadata else None
                        )
                    
                    # Ensure sorted for efficient hyperslice (intersect1d returns sorted indices, but verify)
                    if debug:
                        print(f"      🔄 Verifying indices are valid and sorted...", flush=True)
                        print(f"      Index range: {matching_indices.min()} to {matching_indices.max()} (total_size: {total_size})", flush=True)
                    
                    # Verify indices are within bounds
                    if matching_indices.max() >= total_size:
                        raise ValueError(f"Invalid index: {matching_indices.max()} >= {total_size}")
                    
                    matching_indices = np.sort(matching_indices)  # Ensure sorted (intersect1d should already return sorted)
                    
                    if debug:
                        print(f"      ✅ Indices sorted ({len(matching_indices):,} indices), ready for hyperslice", flush=True)
                        print(f"      🎯 Using hyperslice to load {len(matching_indices):,} positions from {total_size:,} total...", flush=True)
                    
                    use_hyperslice = True
                    # Use hyperslice to load only matching indices (HDF5 filters BEFORE loading!)
                    try:
                        if debug:
                            print(f"      📥 Loading pos array via hyperslice...", flush=True)
                        pos = np.asarray(data_group["pos"][matching_indices], dtype=np.uint32)
                        
                        if debug:
                            print(f"      📥 Loading mC array via hyperslice...", flush=True)
                        mC = np.asarray(data_group["mC"][matching_indices], dtype=np.uint32)
                        
                        if debug:
                            print(f"      📥 Loading uC array via hyperslice...", flush=True)
                        uC = np.asarray(data_group["uC"][matching_indices], dtype=np.uint32)
                        
                        if debug:
                            print(f"      📥 Loading tnc array via hyperslice...", flush=True)
                        tnc = np.asarray(data_group["tnc"][matching_indices], dtype=np.uint8)
                        
                        if debug:
                            print(f"      ✅ Hyperslice complete: loaded {len(matching_indices):,} positions from {total_size:,} total", flush=True)
                    except Exception as e:
                        if debug:
                            print(f"      ❌ Error during hyperslice: {e}", flush=True)
                            print(f"      Error type: {type(e).__name__}", flush=True)
                            import traceback
                            traceback.print_exc()
                        raise
                else:
                    # Load basic fields (always present) - full load when no positions specified
                    pos = np.asarray(data_group["pos"][:], dtype=np.uint32)
                    mC = np.asarray(data_group["mC"][:], dtype=np.uint32)
                    uC = np.asarray(data_group["uC"][:], dtype=np.uint32)
                    tnc = np.asarray(data_group["tnc"][:], dtype=np.uint8)

                # Initialize optional fields
                N: Optional[np.ndarray[np.uint32]] = None
                Sx: Optional[np.ndarray[np.float32]] = None
                Sx2: Optional[np.ndarray[np.float32]] = None
                log_x_sum: Optional[np.ndarray[np.float32]] = None
                log_1_minus_x_sum: Optional[np.ndarray[np.float32]] = None

                # Check for centroid fields - use hyperslice if positions were specified
                if "N" in data_group:
                    if use_hyperslice:
                        N = np.asarray(data_group["N"][matching_indices], dtype=np.uint32)
                    else:
                        N = np.asarray(data_group["N"][:], dtype=np.uint32)

                # Check for basic centroid statistics
                if "Sx" in data_group:
                    if use_hyperslice:
                        Sx = np.asarray(data_group["Sx"][matching_indices], dtype=np.float32)
                    else:
                        Sx = np.asarray(data_group["Sx"][:], dtype=np.float32)
                if "Sx2" in data_group:
                    if use_hyperslice:
                        Sx2 = np.asarray(data_group["Sx2"][matching_indices], dtype=np.float32)
                    else:
                        Sx2 = np.asarray(data_group["Sx2"][:], dtype=np.float32)

                # Check for extended centroid statistics
                if "log_x_sum" in data_group:
                    if use_hyperslice:
                        log_x_sum = np.asarray(data_group["log_x_sum"][matching_indices], dtype=np.float32)
                    else:
                        log_x_sum = np.asarray(data_group["log_x_sum"][:], dtype=np.float32)
                if "log_1_minus_x_sum" in data_group:
                    if use_hyperslice:
                        log_1_minus_x_sum = np.asarray(data_group["log_1_minus_x_sum"][matching_indices], dtype=np.float32)
                    else:
                        log_1_minus_x_sum = np.asarray(data_group["log_1_minus_x_sum"][:], dtype=np.float32)


        # Apply exact position filtering if requested (only needed for structured array format)
        # For group format with hyperslice, positions are already filtered
        if positions is not None and not (hasattr(data_group, 'dtype') and hasattr(data_group.dtype, 'names')):
            # This is for structured array format - filter after loading
            original_count = len(pos)
            # Find indices of positions that exist in the data
            positions_set = set(positions)
            mask = np.array([p in positions_set for p in pos], dtype=bool)
            filtered_count = np.sum(mask)

            if debug:
                print(f"🎯 DMP filtering: {original_count:,} positions loaded → {filtered_count} DMP positions kept")

            if np.any(mask):
                # Filter all arrays to only include requested positions
                pos = pos[mask]
                mC = mC[mask]
                uC = uC[mask]
                tnc = tnc[mask]
                if N is not None:
                    N = N[mask]
                if Sx is not None:
                    Sx = Sx[mask]
                if Sx2 is not None:
                    Sx2 = Sx2[mask]
                if log_x_sum is not None:
                    log_x_sum = log_x_sum[mask]
                if log_1_minus_x_sum is not None:
                    log_1_minus_x_sum = log_1_minus_x_sum[mask]

                # Sort by position for efficient lookups
                sort_idx = np.argsort(pos)
                pos = pos[sort_idx]
                mC = mC[sort_idx]
                uC = uC[sort_idx]
                tnc = tnc[sort_idx]
                if N is not None:
                    N = N[sort_idx]
                if Sx is not None:
                    Sx = Sx[sort_idx]
                if Sx2 is not None:
                    Sx2 = Sx2[sort_idx]
                if log_x_sum is not None:
                    log_x_sum = log_x_sum[sort_idx]
                if log_1_minus_x_sum is not None:
                    log_1_minus_x_sum = log_1_minus_x_sum[sort_idx]
            else:
                # No matching positions found, return empty arrays
                print(f"⚠️ No DMP positions found in loaded data")
                empty_shape = (0,)
                pos = np.array([], dtype=np.uint32)
                mC = np.array([], dtype=np.uint32)
                uC = np.array([], dtype=np.uint32)
                tnc = np.array([], dtype=np.uint8)
                N = np.array([], dtype=np.uint32) if N is not None else None
                Sx = np.array([], dtype=np.float32) if Sx is not None else None
                Sx2 = np.array([], dtype=np.float32) if Sx2 is not None else None
                log_x_sum = np.array([], dtype=np.float32) if log_x_sum is not None else None
                log_1_minus_x_sum = np.array([], dtype=np.float32) if log_1_minus_x_sum is not None else None

        return cls(
            pos=pos,
            mC=mC,
            uC=uC,
            tnc=tnc,
            N=N,
            Sx=Sx,
            Sx2=Sx2,
            log_x_sum=log_x_sum,
            log_1_minus_x_sum=log_1_minus_x_sum,
            _metadata=metadata if metadata else None
        )
    
    def get_methylation_levels(self) -> np.ndarray:
        """
        Calculate methylation levels based on sample type.
        
        For samples: mC / (mC + uC)
        For centroids: Sx / N (if available), otherwise mC / (mC + uC)
        """
        if self.is_centroid and self.Sx is not None and self.N is not None:
            # Use proper statistical estimator for centroids
            return self.Sx / self.N
        else:
            # Use basic calculation for samples or centroids without Sx
            return self.mC / (self.mC + self.uC)
    
    def get_coverage(self) -> np.ndarray:
        """Get coverage (total reads) at each position."""
        return self.mC + self.uC
    
    def get_sample_count(self) -> Optional[np.ndarray]:
        """Get sample count at each position (only for centroids)."""
        return self.N
    
    def save_to_h5(self, file_path: Union[str, Path], compressed: bool = True, metadata: Optional[Dict[str, Any]] = None) -> Path:
        """
        Save MethylSample to HDF5 file.

        Args:
            file_path: Path to save the HDF5 file
            compressed: Whether to use compression (default: True)
            metadata: Optional dictionary of metadata to save as file attributes

        Returns:
            Path to the saved file

        Raises:
            ImportError: If HDF5 dependencies are not available
        """
        if not HDF5_AVAILABLE:
            raise ImportError("HDF5 dependencies (h5py, hdf5plugin) not available. "
                            "Please ensure they are installed in your container.")

        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with h5py.File(file_path, "w") as f:
            # Create methylation_data group
            data_group = f.create_group("methylation_data")
            
            # Compression settings
            compression_kwargs = {}
            if compressed:
                try:
                    import hdf5plugin
                    compression_kwargs = hdf5plugin.Zstd(clevel=9)
                except ImportError:
                    compression_kwargs = {"compression": "gzip", "compression_opts": 9}
            
            # Save basic fields (always present)
            data_group.create_dataset(
                "pos",
                data=self.pos,
                dtype=np.uint32,
                **compression_kwargs
            )
            data_group.create_dataset(
                "mC",
                data=self.mC,
                dtype=np.uint16 if self.is_centroid else np.uint32,
                **compression_kwargs
            )
            data_group.create_dataset(
                "uC",
                data=self.uC,
                dtype=np.uint16 if self.is_centroid else np.uint32,
                **compression_kwargs
            )
            data_group.create_dataset(
                "tnc",
                data=self.tnc,
                dtype=np.uint8,
                **compression_kwargs
            )
            
            # Save centroid fields if present
            if self.N is not None:
                data_group.create_dataset(
                    "N",
                    data=self.N,
                    dtype=np.uint16,
                    **compression_kwargs
                )
            
            # Save basic centroid statistics if present
            if self.Sx is not None:
                data_group.create_dataset(
                    "Sx",
                    data=self.Sx,
                    dtype=np.float32,
                    **compression_kwargs
                )
            if self.Sx2 is not None:
                data_group.create_dataset(
                    "Sx2",
                    data=self.Sx2,
                    dtype=np.float32,
                    **compression_kwargs
                )
            
            # Save extended centroid statistics if present
            if self.log_x_sum is not None:
                data_group.create_dataset(
                    "log_x_sum",
                    data=self.log_x_sum,
                    dtype=np.float32,
                    **compression_kwargs
                )
            if self.log_1_minus_x_sum is not None:
                data_group.create_dataset(
                    "log_1_minus_x_sum",
                    data=self.log_1_minus_x_sum,
                    dtype=np.float32,
                    **compression_kwargs
                )
            
            # Save metadata as file attributes if provided
            if metadata:
                for key, value in metadata.items():
                    # Handle different data types for HDF5 attributes
                    if isinstance(value, (list, tuple)):
                        # Convert list/tuple to JSON string for storage
                        if value and isinstance(value[0], str):
                            # For string lists, store as JSON
                            import json
                            f.attrs[key] = json.dumps(value)
                        else:
                            # For numeric lists, store directly
                            f.attrs[key] = value
                    elif isinstance(value, (str, int, float, bool)):
                        f.attrs[key] = value
                    elif value is None:
                        # Skip None values
                        continue
                    else:
                        # For other types, convert to string
                        import json
                        f.attrs[key] = json.dumps(value)
        
        return file_path
    
    @classmethod
    def from_centroid_data(cls, centroid_data, metadata: Optional[Dict[str, Any]] = None):
        """
        Create appropriate MethylSample subclass from centroid data.

        Args:
            centroid_data: Dictionary or structured array with centroid data
            metadata: Optional metadata dictionary

        Returns:
            MethylSample, MethylBasicCentroid, or MethylCentroid instance
        """
        # Extract data fields
        if isinstance(centroid_data, np.ndarray):
            # Handle structured array format
            data = {
                "pos": centroid_data["pos"],
                "mC": centroid_data["mC"],
                "uC": centroid_data["uC"],
                "tnc": centroid_data["tnc"],
                "N": centroid_data["N"] if "N" in centroid_data.dtype.names else None,
                "Sx": centroid_data["Sx"] if "Sx" in centroid_data.dtype.names else None,
                "Sx2": centroid_data["Sx2"] if "Sx2" in centroid_data.dtype.names else None,
                "log_x_sum": centroid_data["log_x_sum"] if "log_x_sum" in centroid_data.dtype.names else None,
                "log_1_minus_x_sum": centroid_data["log_1_minus_x_sum"] if "log_1_minus_x_sum" in centroid_data.dtype.names else None,
            }
        else:
            # Handle dictionary format
            data = {
                "pos": centroid_data["pos"],
                "mC": centroid_data["mC"],
                "uC": centroid_data["uC"],
                "tnc": centroid_data["tnc"],
                "N": centroid_data.get("N"),
                "Sx": centroid_data.get("Sx"),
                "Sx2": centroid_data.get("Sx2"),
                "log_x_sum": centroid_data.get("log_x_sum"),
                "log_1_minus_x_sum": centroid_data.get("log_1_minus_x_sum"),
            }

        # Determine appropriate class based on available data
        if data["log_x_sum"] is not None and data["log_1_minus_x_sum"] is not None:
            # Extended centroid
            return MethylCentroid(
                pos=data["pos"],
                mC=data["mC"],
                uC=data["uC"],
                tnc=data["tnc"],
                N=data["N"],
                Sx=data["Sx"],
                Sx2=data["Sx2"],
                log_x_sum=data["log_x_sum"],
                log_1_minus_x_sum=data["log_1_minus_x_sum"],
                _metadata=metadata
            )
        elif data["N"] is not None:
            # Basic centroid
            return MethylBasicCentroid(
                pos=data["pos"],
                mC=data["mC"],
                uC=data["uC"],
                tnc=data["tnc"],
                N=data["N"],
                _metadata=metadata
            )
        else:
            # Basic sample
            return MethylSample(
                pos=data["pos"],
                mC=data["mC"],
                uC=data["uC"],
                tnc=data["tnc"],
                _metadata=metadata
            )

    def to_numpy(self, extended: bool = False) -> np.ndarray:
        """
        Convert MethylSample to structured numpy array format.

        Args:
            extended: Whether to include extended centroid fields (Sx, Sx2, log_x_sum, log_1_minus_x_sum)

        Returns:
            Structured numpy array with centroid data
        """
        if extended and self.is_extended_centroid:
            # Use extended centroid dtype
            dtype = METHYL_EXTENDED_CENTROID_DTYPE
            data = np.empty(len(self.pos), dtype=dtype)
            data["pos"] = self.pos
            data["mC"] = self.mC
            data["uC"] = self.uC
            data["tnc"] = self.tnc
            data["N"] = self.N
            data["Sx"] = self.Sx
            data["Sx2"] = self.Sx2
            data["log_x_sum"] = self.log_x_sum
            data["log_1_minus_x_sum"] = self.log_1_minus_x_sum
        elif self.is_centroid:
            # Use basic centroid dtype
            dtype = METHYL_CENTROID_DTYPE
            data = np.empty(len(self.pos), dtype=dtype)
            data["pos"] = self.pos
            data["mC"] = self.mC
            data["uC"] = self.uC
            data["tnc"] = self.tnc
            data["N"] = self.N
        else:
            # Use basic sample dtype
            dtype = METHYL_SAMPLE_DTYPE
            data = np.empty(len(self.pos), dtype=dtype)
            data["pos"] = self.pos
            data["mC"] = self.mC
            data["uC"] = self.uC
            data["tnc"] = self.tnc

        return data

    @classmethod
    def from_sample_data(cls, pos: np.ndarray, mC: np.ndarray, uC: np.ndarray, tnc: np.ndarray) -> MethylSample:
        """
        Create MethylSample from basic sample data.
        
        Args:
            pos: Genomic positions
            mC: Methylated cytosine counts
            uC: Unmethylated cytosine counts
            tnc: Trinucleotide context codes
            
        Returns:
            MethylSample instance
        """
        return cls(
            pos=pos,
            mC=mC,
            uC=uC,
            tnc=tnc
        )
    
    def to_dataframe(self, mask: Optional[np.ndarray] = None) -> pd.DataFrame:
        """
        Convert MethylSample to pandas DataFrame with optional mask.
        
        Args:
            mask: Boolean mask to select subset of positions (if None, uses all)
            
        Returns:
            DataFrame with columns: pos, mC, uC, and additional fields if available
        """       
        # Apply mask if provided
        if mask is not None:
            pos = self.pos[mask]
            mC = self.mC[mask]
            uC = self.uC[mask]
            tnc = self.tnc[mask]
        else:
            pos = self.pos
            mC = self.mC
            uC = self.uC
            tnc = self.tnc
        
        # Create basic DataFrame
        data = {
            'pos': pos,
            'mC': mC,
            'uC': uC,
            'tnc': tnc
        }
        
        # Add centroid fields if available
        if self.N is not None:
            data['N'] = self.N[mask] if mask is not None else self.N
        if self.Sx is not None:
            data['Sx'] = self.Sx[mask] if mask is not None else self.Sx
        if self.Sx2 is not None:
            data['Sx2'] = self.Sx2[mask] if mask is not None else self.Sx2
        if self.log_x_sum is not None:
            data['log_x_sum'] = self.log_x_sum[mask] if mask is not None else self.log_x_sum
        if self.log_1_minus_x_sum is not None:
            data['log_1_minus_x_sum'] = self.log_1_minus_x_sum[mask] if mask is not None else self.log_1_minus_x_sum
        
        return pd.DataFrame(data)
    
    def create_position_mask(
        self, 
        positions: Optional[list] = None, 
        min_coverage: Optional[int] = None, 
        max_coverage: Optional[int] = None
    ) -> np.ndarray:
        """
        Create a boolean mask for selecting positions based on criteria.
        
        Args:
            positions: List of specific positions to include (if None, uses all)
            min_coverage: Minimum coverage threshold
            max_coverage: Maximum coverage threshold
            
        Returns:
            Boolean mask array
        """
        total_positions = len(self.pos)
        mask = np.ones(total_positions, dtype=bool)
        
        # Filter by specific positions
        if positions is not None:
            position_mask = np.isin(self.pos, positions)
            mask &= position_mask
        
        # Filter by coverage
        if min_coverage is not None or max_coverage is not None:
            coverage = self.mC + self.uC
            
            if min_coverage is not None:
                mask &= (coverage >= min_coverage)
            
            if max_coverage is not None:
                mask &= (coverage <= max_coverage)
        
        return mask
    
    def get_position_info(self) -> dict:
        """
        Get information about positions without loading all data.
        
        Returns:
            Dictionary with position information
        """
        total_positions = len(self.pos)
        
        # Get position range
        min_pos = self.pos.min()
        max_pos = self.pos.max()
        
        # Get coverage statistics
        coverage = self.mC + self.uC
        
        info = {
            'total_positions': total_positions,
            'min_position': int(min_pos),
            'max_position': int(max_pos),
            'position_range': int(max_pos - min_pos),
            'mean_coverage': float(coverage.mean()),
            'median_coverage': float(np.median(coverage)),
            'min_coverage': int(coverage.min()),
            'max_coverage': int(coverage.max()),
            'positions_with_coverage': int((coverage > 0).sum())
        }
        
        return info
    
    @staticmethod
    def list_datasets(hdf5_path: Union[str, Path]) -> list[str]:
        """List all datasets in an HDF5 file."""
        if not HDF5_AVAILABLE:
            raise ImportError("HDF5 dependencies not available. "
                            "Please ensure they are installed in your container.")

        path = Path(hdf5_path)
        datasets = []

        with h5py.File(path, 'r') as f:
            datagroup = f['methylation_data']
            for name in datagroup.keys():
                if isinstance(datagroup[name], h5py.Dataset):
                    datasets.append(name)

            return datasets


    @classmethod
    def load_multiple_chromosomes(
        cls, 
        file_patterns: list, 
        mask: Optional[np.ndarray] = None,
        verbose: bool = False
    ) -> dict[str, object]:
        """
        Load methylation data from multiple chromosome files.
        
        Args:
            file_patterns: List of file paths or glob patterns
            mask: Optional mask to apply to all files
            
        Returns:
            Dictionary mapping chromosome names to DataFrames
        """
        import glob
        
        results = {}
        
        for pattern in file_patterns:
            # Handle glob patterns
            if '*' in str(pattern):
                files = glob.glob(str(pattern))
            else:
                files = [pattern]
            
            for file_path in files:
                path = Path(file_path)
                if path.exists() and path.suffix.lower() in ['.h5', '.hdf5']:
                    # Extract chromosome info from filename
                    filename = path.stem  # Remove extension
                    
                    if '-' in filename:
                        parts = filename.split('-')
                        if len(parts) == 2:
                            chromosome = parts[0]
                        else:
                            chromosome = 'unknown'
                    else:
                        chromosome = 'unknown'
                    
                    # Load data
                    sample = cls.load_from_h5(path)
                    df = sample.to_dataframe(mask=mask)
                    results[chromosome] = df
        
        return results
    
    @classmethod
    def merge_contexts(cls, context_samples: List['MethylSample']) -> 'MethylSample':
        """
        Merge multiple MethylSample instances from different contexts (CG, CHG, CHH).
        
        Each position belongs to exactly one context, so positions from different contexts
        are mutually exclusive. This method concatenates all positions from all contexts,
        preserving each position's mC/uC/tnc from its original context.
        
        Args:
            context_samples: List of MethylSample instances from different contexts
        
        Returns:
            Merged MethylSample with all positions from all contexts combined
        
        Example:
            >>> cg_sample = MethylSample.load_from_h5("1-CG.h5")
            >>> chg_sample = MethylSample.load_from_h5("1-CHG.h5")
            >>> chh_sample = MethylSample.load_from_h5("1-CHH.h5")
            >>> merged = MethylSample.merge_contexts([cg_sample, chg_sample, chh_sample])
        """
        if len(context_samples) == 0:
            raise ValueError("At least one context sample required")
        
        if len(context_samples) == 1:
            return context_samples[0]
        
        # Collect all positions and data from all contexts
        # Since positions are mutually exclusive between contexts, we can concatenate
        all_positions = []
        all_mC = []
        all_uC = []
        all_tnc = []
        
        # Optional centroid fields (if any sample is a centroid)
        all_N = []
        all_Sx = []
        all_Sx2 = []
        all_log_x_sum = []
        all_log_1_minus_x_sum = []
        
        has_centroid_data = False
        
        for sample in context_samples:
            # Skip empty samples (contexts with no DMP positions)
            if len(sample.pos) == 0:
                continue

            # Append all data from this context
            all_positions.append(sample.pos)
            all_mC.append(sample.mC)
            all_uC.append(sample.uC)
            all_tnc.append(sample.tnc)
            
            # Handle optional centroid fields
            if sample.N is not None:
                has_centroid_data = True
                all_N.append(sample.N)
            if sample.Sx is not None:
                all_Sx.append(sample.Sx)
            if sample.Sx2 is not None:
                all_Sx2.append(sample.Sx2)
            if sample.log_x_sum is not None:
                all_log_x_sum.append(sample.log_x_sum)
            if sample.log_1_minus_x_sum is not None:
                all_log_1_minus_x_sum.append(sample.log_1_minus_x_sum)
        
        # Check if all samples were empty (after filtering)
        if len(all_positions) == 0:
            # Return an empty MethylSample
            return cls(
                pos=np.array([], dtype=np.uint32),
                mC=np.array([], dtype=np.uint32),
                uC=np.array([], dtype=np.uint32),
                tnc=np.array([], dtype=np.uint8),
                N=None,
                Sx=None,
                Sx2=None,
                log_x_sum=None,
                log_1_minus_x_sum=None
            )
        
        # Concatenate all arrays
        merged_positions = np.concatenate(all_positions).astype(np.uint32)
        merged_mC = np.concatenate(all_mC).astype(np.uint32)
        merged_uC = np.concatenate(all_uC).astype(np.uint32)
        merged_tnc = np.concatenate(all_tnc).astype(np.uint8)
        
        # Sort by position to maintain genomic order
        sort_indices = np.argsort(merged_positions)
        merged_positions = merged_positions[sort_indices]
        merged_mC = merged_mC[sort_indices]
        merged_uC = merged_uC[sort_indices]
        merged_tnc = merged_tnc[sort_indices]
        
        # Handle optional centroid fields
        merged_N = None
        merged_Sx = None
        merged_Sx2 = None
        merged_log_x_sum = None
        merged_log_1_minus_x_sum = None
        
        if has_centroid_data:
            # For centroids, we need to handle missing fields in some contexts
            # If any context has centroid data, we should merge it
            if all_N:
                merged_N = np.concatenate(all_N)[sort_indices].astype(np.uint32)
            if all_Sx:
                merged_Sx = np.concatenate(all_Sx)[sort_indices].astype(np.float32)
            if all_Sx2:
                merged_Sx2 = np.concatenate(all_Sx2)[sort_indices].astype(np.float32)
            if all_log_x_sum:
                merged_log_x_sum = np.concatenate(all_log_x_sum)[sort_indices].astype(np.float32)
            if all_log_1_minus_x_sum:
                merged_log_1_minus_x_sum = np.concatenate(all_log_1_minus_x_sum)[sort_indices].astype(np.float32)
        
        # Create merged sample
        merged_sample = cls(
            pos=merged_positions,
            mC=merged_mC,
            uC=merged_uC,
            tnc=merged_tnc,
            N=merged_N,
            Sx=merged_Sx,
            Sx2=merged_Sx2,
            log_x_sum=merged_log_x_sum,
            log_1_minus_x_sum=merged_log_1_minus_x_sum
        )
        
        return merged_sample

    def apply_mask(self, mask_or_indices: Union[np.ndarray, bool]) -> 'MethylSample':
        """
        Apply a mask or indices to slice this MethylSample efficiently.

        If boolean mask, filters positions. If indices array, selects by position.

        Args:
            mask_or_indices: Boolean mask (same length as pos) or integer indices array.

        Returns:
            New MethylSample with sliced data (views where possible).
        """
        if isinstance(mask_or_indices, np.ndarray) and mask_or_indices.dtype.kind == 'b':  # Boolean mask
            indices = np.nonzero(mask_or_indices)[0]
        else:
            indices = mask_or_indices.astype(np.intp)  # Ensure integer indices

        # Validate indices
        if len(indices) == 0:
            raise ValueError("Mask/indices resulted in empty sample.")
        if np.max(indices) >= len(self.pos):
            raise ValueError("Indices out of bounds for sample.")

        # Slice all fields (use views for efficiency)
        new_pos = self.pos[indices]
        new_mC = self.mC[indices]
        new_uC = self.uC[indices]
        new_tnc = self.tnc[indices] if self.tnc is not None else None
        new_N = self.N[indices] if self.N is not None else None
        new_Sx = self.Sx[indices] if self.Sx is not None else None
        new_Sx2 = self.Sx2[indices] if self.Sx2 is not None else None
        new_log_x_sum = self.log_x_sum[indices] if self.log_x_sum is not None else None
        new_log_1_minus_x_sum = self.log_1_minus_x_sum[indices] if self.log_1_minus_x_sum is not None else None

        # Create new instance (assumes constructor handles partial None fields)
        return type(self)(
            pos=new_pos,
            mC=new_mC,
            uC=new_uC,
            tnc=new_tnc,
            N=new_N,
            Sx=new_Sx,
            Sx2=new_Sx2,
            log_x_sum=new_log_x_sum,
            log_1_minus_x_sum=new_log_1_minus_x_sum
        )


@dataclass(slots=True)
class MethylBasicCentroid(MethylSample):
    """
    Represents a basic methylation centroid - aggregated from multiple samples.

    Adds sample count (N) and provides centroid aggregation methods.
    """
    # Centroid-specific data
    N: np.ndarray  # uint32 - sample counts per position

    # Metadata (inherited but required for dataclass ordering)
    _metadata: Optional[Dict[str, Any]]

    def __post_init__(self):
        """Validate data types after initialization."""
        if self._metadata is None:
            self._metadata = {}
        self._validate_data_types()
        self._validate_centroid_data_types()

    def _validate_centroid_data_types(self):
        """Validate centroid-specific data types."""
        assert self.N.dtype == np.uint32, f"N should be uint32, got {self.N.dtype}"
        assert len(self.N) == len(self.pos), f"N length {len(self.N)} != pos length {len(self.pos)}"

    @property
    def sample_type(self) -> str:
        """Determine the type of sample."""
        return "basic_centroid"

    @property
    def is_centroid(self) -> bool:
        """Check if this is a centroid."""
        return True

    @property
    def is_extended_centroid(self) -> bool:
        """Check if this is an extended centroid."""
        return False


@dataclass(slots=True)
class MethylCentroid(MethylBasicCentroid):
    """
    Represents an extended methylation centroid with statistical accumulators.

    Includes sums and sums-of-squares for methylation levels, plus
    logarithmic accumulators for Beta distribution parameter estimation.
    """
    # Extended centroid data
    Sx: np.ndarray          # float32 - sum of methylation levels
    Sx2: np.ndarray         # float32 - sum of squared methylation levels
    log_x_sum: np.ndarray           # float32 - sum of log(methylation_level)
    log_1_minus_x_sum: np.ndarray   # float32 - sum of log(1 - methylation_level)

    # Metadata (inherited but required for dataclass ordering)
    _metadata: Optional[Dict[str, Any]]

    # Cached statistical properties (computed on demand)
    _cached_alpha: Optional[np.ndarray] = None       # float64 - Beta distribution alpha parameter
    _cached_beta: Optional[np.ndarray] = None        # float64 - Beta distribution beta parameter
    _cached_mean: Optional[np.ndarray] = None        # float64 - expected methylation level
    _cached_variance: Optional[np.ndarray] = None    # float64 - methylation level variance
    _cached_tau: Optional[np.ndarray] = None         # float64 - total concentration (alpha + beta)

    def __post_init__(self):
        """Validate data types after initialization."""
        if self._metadata is None:
            self._metadata = {}
        self._validate_data_types()
        self._validate_centroid_data_types()
        self._validate_extended_data_types()

    def _validate_extended_data_types(self):
        """Validate extended centroid-specific data types."""
        assert self.Sx.dtype == np.float32, f"Sx should be float32, got {self.Sx.dtype}"
        assert self.Sx2.dtype == np.float32, f"Sx2 should be float32, got {self.Sx2.dtype}"
        assert self.log_x_sum.dtype == np.float32, f"log_x_sum should be float32, got {self.log_x_sum.dtype}"
        assert self.log_1_minus_x_sum.dtype == np.float32, f"log_1_minus_x_sum should be float32, got {self.log_1_minus_x_sum.dtype}"

        expected_length = len(self.pos)
        assert len(self.Sx) == expected_length, f"Sx length {len(self.Sx)} != pos length {expected_length}"
        assert len(self.Sx2) == expected_length, f"Sx2 length {len(self.Sx2)} != pos length {expected_length}"
        assert len(self.log_x_sum) == expected_length, f"log_x_sum length {len(self.log_x_sum)} != pos length {expected_length}"
        assert len(self.log_1_minus_x_sum) == expected_length, f"log_1_minus_x_sum length {len(self.log_1_minus_x_sum)} != pos length {expected_length}"

    @property
    def sample_type(self) -> str:
        """Determine the type of sample."""
        return "extended_centroid"

    @property
    def is_extended_centroid(self) -> bool:
        """Check if this is an extended centroid."""
        return True

    # Statistical properties - computed on demand
    @property
    def alpha(self) -> np.ndarray:
        """
        Beta distribution alpha parameter.

        Computed using MLE estimation for extended centroids.
        """
        if self._cached_alpha is None:
            alpha, beta = self._compute_beta_parameters()
            self._cached_alpha = alpha
            self._cached_beta = beta
        return self._cached_alpha

    @property
    def beta(self) -> np.ndarray:
        """
        Beta distribution beta parameter.

        Computed using MLE estimation for extended centroids.
        """
        if self._cached_beta is None:
            alpha, beta = self._compute_beta_parameters()
            self._cached_alpha = alpha
            self._cached_beta = beta
        return self._cached_beta

    @property
    def mean(self) -> np.ndarray:
        """
        Expected methylation level.

        Uses adaptive mean estimation based on sample size reliability:
        - Small samples (N < 20): empirical mean (Sx/N) for statistical reliability
        - Large samples (N ≥ 20): Beta distribution mean (α/(α+β)) for full distributional information
        """
        if self._cached_mean is None:
            eps = 1e-12

            # For centroids with sufficient statistics, use adaptive mean estimation
            if self.Sx is not None and self.N is not None:
                empirical_mean = self.Sx / np.maximum(self.N.astype(np.float32), eps)

                # Use empirical mean for small sample sizes (N < 20) where Beta estimation is unreliable
                small_sample_mask = self.N < 20

                if np.all(small_sample_mask):
                    # All positions have small samples - use empirical mean directly
                    final_mean = empirical_mean
                else:
                    # Mix of small and large samples
                    final_mean = empirical_mean.copy()  # Start with empirical mean

                    # For larger sample sizes (N >= 20), use Beta distribution mean
                    large_sample_mask = ~small_sample_mask
                    if np.any(large_sample_mask):
                        alpha = self.alpha
                        beta = self.beta
                        tau = alpha + beta
                        beta_mean = alpha / np.maximum(tau, eps)

                        # Use Beta mean for large samples
                        final_mean = np.where(large_sample_mask, beta_mean, final_mean)

            else:
                # Fallback to Beta distribution mean
                alpha = self.alpha
                beta = self.beta
                tau = alpha + beta
                final_mean = alpha / np.maximum(tau, eps)

            self._cached_mean = final_mean
        return self._cached_mean

    @property
    def variance(self) -> np.ndarray:
        """
        Variance of methylation level.

        Calculated as: mean * (1 - mean) / (tau + 1) where tau = alpha + beta
        This is numerically stable and equivalent to: (alpha * beta) / ((alpha + beta)^2 * (alpha + beta + 1))
        """
        if self._cached_variance is None:
            alpha = self.alpha
            beta = self.beta
            tau = alpha + beta
            eps = 1e-12
            # Numerically stable variance calculation: var = mean * (1 - mean) / (tau + 1)
            # This avoids overflow when alpha/beta are very large
            mean = alpha / np.maximum(tau, eps)
            self._cached_variance = mean * (1 - mean) / np.maximum(tau + 1, eps)
        return self._cached_variance

    @property
    def tau(self) -> np.ndarray:
        """
        Total concentration parameter of Beta distribution.

        tau = alpha + beta provides information about the reliability of
        the distribution estimate. Higher tau values indicate more reliable
        parameter estimates.
        """
        if self._cached_tau is None:
            alpha = self.alpha
            beta = self.beta
            self._cached_tau = alpha + beta
        return self._cached_tau

    @property
    def precision(self) -> np.ndarray:
        """
        Precision of methylation level estimate.

        Calculated as tau / (tau + 1), where tau = alpha + beta.
        Higher values indicate more precise estimates.
        """
        tau = self.tau
        return tau / (tau + 1)

    def clear_statistical_cache(self):
        """Clear cached statistical properties to force recomputation."""
        self._cached_alpha = None
        self._cached_beta = None
        self._cached_mean = None
        self._cached_variance = None
        self._cached_tau = None

    def get_beta_parameters(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get Beta distribution parameters (alpha, beta).

        Returns:
            Tuple of (alpha, beta) arrays
        """
        return self.alpha, self.beta

    def _compute_beta_parameters(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute Beta distribution parameters using appropriate method.

        For extended centroids, uses MLE estimation with log sums.
        """
        if not self.is_extended_centroid:
            raise ValueError("Beta parameter computation requires extended centroid data")

        n = self.N.astype(np.float32)
        log_x_sum = self.log_x_sum
        log_1mx_sum = self.log_1_minus_x_sum

        return self._estimate_beta_params_bounded_extended(n, log_x_sum, log_1mx_sum)

    def _estimate_beta_params_bounded_extended(self, n: np.ndarray, log_x_sum: np.ndarray,
                                             log_1mx_sum: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Estimate Beta distribution parameters for extended centroids with bounds checking.

        This method applies MLE but with strict bounds to prevent pathological parameter
        estimates that can occur with extreme methylation values or edge cases.

        Args:
            n: Sample counts (array)
            log_x_sum: Log sum of methylation levels
            log_1mx_sum: Log sum of (1-methylation) levels

        Returns:
            Tuple of (alpha, beta) parameter arrays
        """
        # Log-space computation to avoid underflow with very small methylation values
        # alpha = exp( (sum(log(x)) - n * log(n)) / n ) where x is methylation level
        # beta = exp( (sum(log(1-x)) - n * log(n)) / n ) where x is methylation level

        eps = 1e-12
        n_safe = np.maximum(n, eps)

        # Compute log-space estimates
        log_alpha = (log_x_sum - n * np.log(n_safe)) / n_safe
        log_beta = (log_1mx_sum - n * np.log(n_safe)) / n_safe

        # Convert from log space to linear space with bounds checking
        # Clip to reasonable ranges to prevent numerical issues
        alpha = np.clip(np.exp(log_alpha), eps, 1e6)
        beta = np.clip(np.exp(log_beta), eps, 1e6)

        # Additional validation: ensure parameters are finite and positive
        alpha = np.where(np.isfinite(alpha) & (alpha > 0), alpha, eps)
        beta = np.where(np.isfinite(beta) & (beta > 0), beta, eps)

        return alpha, beta


@dataclass(slots=True)
class DMPSample:
    """
    Represents DMP (Differentially Methylated Position) results that can be saved to HDF5 files.
    This class handles DMP-specific data structures with both group data, statistical results, and metadata.
    """
    positions: np.ndarray[np.uint32]
    mC1: np.ndarray[np.uint32]
    uC1: np.ndarray[np.uint32]
    mC2: np.ndarray[np.uint32]
    uC2: np.ndarray[np.uint32]
    p_values: np.ndarray[np.float32]
    q_values: Optional[np.ndarray[np.float32]] = None
    metadata: Optional[dict] = None
    
    def save_to_h5(self, file_path: Union[str, Path]) -> Path:
        """
        Save DMP results to HDF5 file with both MethylSample-compatible structure and DMP-specific data.
        
        Args:
            file_path: Path to save the HDF5 file
            
        Returns:
            Path to the saved file
        """
        file_path = Path(file_path)
        
        # Compression settings
        compression_kwargs = {"compression": hdf5plugin.Zstd(clevel=9)}
        
        with h5py.File(file_path, "w") as f:
            # Create MethylSample-compatible methylation_data group (using group 1 data)
            meth_group = f.create_group("methylation_data")
            
            # Store as structured array for MethylSample compatibility
            dtype = np.dtype([
                ("pos", np.uint32),
                ("mC", np.uint32),
                ("uC", np.uint32),
                ("tnc", np.uint8)
            ])
            
            # Use group 1 data for the methylation_data (for compatibility)
            data = np.zeros(len(self.positions), dtype=dtype)
            data["pos"] = self.positions
            data["mC"] = self.mC1
            data["uC"] = self.uC1
            data["tnc"] = self.tnc[0]
            
            meth_group.create_dataset(
                "data",
                data=data,
                **compression_kwargs
            )
            
            # Create DMP-specific results group
            dmp_group = f.create_group("dmp_results")
            
            # Store DMP-specific results
            dmp_group.create_dataset("positions", data=self.positions, **compression_kwargs)
            dmp_group.create_dataset("mC_group1", data=self.mC1, **compression_kwargs)
            dmp_group.create_dataset("uC_group1", data=self.uC1, **compression_kwargs)
            dmp_group.create_dataset("mC_group2", data=self.mC2, **compression_kwargs)
            dmp_group.create_dataset("uC_group2", data=self.uC2, **compression_kwargs)
            dmp_group.create_dataset("p_values", data=self.p_values, **compression_kwargs)
            
            if self.q_values is not None:
                dmp_group.create_dataset("q_values", data=self.q_values, **compression_kwargs)
            
            # Add metadata
            if self.metadata:
                for key, value in self.metadata.items():
                    dmp_group.attrs[key] = value
            
            # Mark this as a DMP results file
            f.attrs["file_type"] = "dmp_results"
            f.attrs["format_version"] = "1.0"
        
        return file_path


class DMPExporter:
    """Exporter for DMP (Differentially Methylated Positions) data to HDF5 format."""
    
    def export_to_h5(self, df, file_path: Union[str, Path], metadata: Optional[dict] = None) -> None:
        """
        Export DMP data to HDF5 with Z-standard compression.

        Args:
            df: DataFrame with DMP data
            file_path: Path to save the HDF5 file
            metadata: Optional metadata dictionary

        Raises:
            ImportError: If HDF5 dependencies are not available
        """
        if not HDF5_AVAILABLE:
            raise ImportError("HDF5 dependencies not available. "
                            "Please ensure they are installed in your container.")

        file_path = Path(file_path)

        with h5py.File(file_path, "w") as f:
            # Create group for DMP data
            dmp_group = f.create_group("dmp_data")
            
            # Add metadata
            if metadata:
                for key, value in metadata.items():
                    dmp_group.attrs[key] = value
            
            # Export each column with Z-standard compression
            for col in df.columns:
                if df[col].dtype == "object":
                    # Handle string columns
                    dt = h5py.special_dtype(vlen=str)
                    dmp_group.create_dataset(
                        col,
                        data=df[col].values,
                        dtype=dt,
                        **hdf5plugin.Zstd(clevel=9),
                    )
                else:
                    # Handle numeric columns
                    dmp_group.create_dataset(
                        col, 
                        data=df[col].values, 
                        **hdf5plugin.Zstd(clevel=9)
                    )


class DMRExporter:
    """Exporter for DMR (Differentially Methylated Regions) data to HDF5 format."""
    
    def export_to_h5(self, df, file_path: Union[str, Path], metadata: Optional[dict] = None) -> None:
        """
        Export DMR data to HDF5 with Z-standard compression.

        Args:
            df: DataFrame with DMR data
            file_path: Path to save the HDF5 file
            metadata: Optional metadata dictionary

        Raises:
            ImportError: If HDF5 dependencies are not available
        """
        if not HDF5_AVAILABLE:
            raise ImportError("HDF5 dependencies not available. "
                            "Please ensure they are installed in your container.")

        file_path = Path(file_path)

        with h5py.File(file_path, "w") as f:
            # Create group for DMR data
            dmr_group = f.create_group("dmr_data")
            
            # Add metadata
            if metadata:
                for key, value in metadata.items():
                    dmr_group.attrs[key] = value
            
            # Export each column with Z-standard compression
            for col in df.columns:
                if df[col].dtype == "object":
                    # Handle string columns
                    dt = h5py.special_dtype(vlen=str)
                    dmr_group.create_dataset(
                        col,
                        data=df[col].values,
                        dtype=dt,
                        **hdf5plugin.Zstd(clevel=9),
                    )
                else:
                    # Handle numeric columns
                    dmr_group.create_dataset(
                        col, 
                        data=df[col].values, 
                        **hdf5plugin.Zstd(clevel=9)
                    )