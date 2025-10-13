#!/usr/bin/env python3
"""
Smart centroid comparison program with integrated GPU acceleration.

This program combines the robust structure of smart_compare_centroids.py with the
GPU-accelerated batch processing from gpu.py. It loads two extended centroid .h5 files
and performs likelihood ratio tests for each position to determine if the methylation
distributions are significantly different.

Key features:
- GPU-accelerated batch processing for large datasets
- Normal approximation for well-behaved Beta distributions (faster)
- Intelligent fallback strategies for numerical issues
- Seamless CPU/GPU switching based on availability
- Maintains all edge case handling from the original
- FDR correction and global significance analysis
- Binary export in Parquet and HDF5 formats for DMP and DMR data

Progress Tracking Solutions:
- Solution 1: Thread-safe counter with lock (implemented)
- Solution 2: Shared progress bar object (alternative)
  class SharedProgressBar:
      def __init__(self, total, desc="Processing"):
          self.pbar = tqdm(total=total, desc=desc, unit="pos")
          self.lock = threading.Lock()

      def update(self, n=1):
          with self.lock:
              self.pbar.update(n)

      def close(self):
          self.pbar.close()

Author: AI Assistant
Date: 2025
"""

import numpy as np
from pathlib import Path
from typing import Tuple, Optional, Dict, List
import logging
from scipy.special import gammaln, psi, polygamma
from scipy.stats import chi2, norm as cpu_norm
import time
from tqdm import tqdm  # type: ignore
import json
from dataclasses import dataclass

# Removed multiprocessing imports - not needed for GPU-bound operations
from scipy.optimize import root_scalar
from math import sqrt

# threading import removed - not needed without multiprocessing
import signal
import atexit
import sys

# Import FDR analysis functions
from methyl_utils.statistical_tests import (
    storey_qvalues,
    stouffer_global_p,
)
from methyl_utils.genomic_utils import (
    group_significant_positions,
)
from methyl_utils.metrics_core import get_sample_beta_mom

# Import utility function for extracting chromosome and context from filename
from ..utils.file_utils import get_chromosome_context_from_filename
# Import sample handler for proper SRP compliance
from ..utils.sample_handler import CentroidPairHandler

# Import directly from MethylUtils
from methyl_utils.gpu_detection import (
    is_gpu_available, 
    is_cupyx_scipy_special_available,
    cleanup_gpu_memory
)

# Global flag to track if cleanup handlers are already registered
_global_cleanup_handlers_registered = False

def register_global_cleanup_handlers():
    """Register global cleanup handlers if not already registered."""
    global _global_cleanup_handlers_registered
    if not _global_cleanup_handlers_registered:
        atexit.register(cleanup_gpu_memory)
        _global_cleanup_handlers_registered = True
        return True
    return False

def are_global_cleanup_handlers_registered():
    """Check if global cleanup handlers are already registered."""
    return _global_cleanup_handlers_registered

# GPU availability flags
GPU_AVAILABLE = is_gpu_available()
CUPYX_SCIPY_SPECIAL_AVAILABLE = is_cupyx_scipy_special_available()

# Import GPU libraries and define functions if available
if GPU_AVAILABLE and CUPYX_SCIPY_SPECIAL_AVAILABLE:
    try:
        import cupy as cp
        import cupyx.scipy.special as sp
        
        print("GPU acceleration available with CuPy")
        print("GPU initialization successful")

        # Define GPU-compatible functions
        gpu_digamma = sp.digamma

        # Import GPU statistical functions from methyl_utils
        from methyl_utils.gpu_utils import gpu_trigamma, gpu_chi2_sf_df2, gpu_norm_cdf
        gpu_gammaln = sp.gammaln
        gpu_erfc = sp.erfc
            
    except Exception as e:
        print(f"GPU initialization failed: {e}")
        GPU_AVAILABLE = False
else:
    GPU_AVAILABLE = False
    print("GPU acceleration not available, using CPU")

# Configure logging - use module-level logger without basicConfig to avoid conflicts
logger = logging.getLogger(__name__)

@dataclass
class SmartLRTResult:
    """Result of a smart likelihood ratio test for a single position."""

    position: int
    test_statistic: float
    p_value: float
    method: str  # "NormalApprox" or "LRT"
    mean1: float
    mean2: float
    variance1: float
    variance2: float
    alpha1: Optional[float] = None
    beta1: Optional[float] = None
    alpha2: Optional[float] = None
    beta2: Optional[float] = None
    alpha_combined: Optional[float] = None
    beta_combined: Optional[float] = None
    n1: int = 0
    n2: int = 0
    significant: bool = False
    significance_level: float = 0.05
    fallback_used: bool = False
    # New fields for FDR analysis
    q_value: Optional[float] = None  # FDR-corrected p-value
    global_significant: bool = False  # Significance after Stouffer's method


@dataclass
class ComparisonData:
    """Efficient typed data structure for comparison results with NumPy arrays."""

    positions: np.ndarray  # int32
    test_statistics: np.ndarray  # float32
    p_values: np.ndarray  # float32
    q_values: np.ndarray  # float32
    methods: np.ndarray  # object (string array)
    mean1: np.ndarray  # float32
    mean2: np.ndarray  # float32
    variance1: np.ndarray  # float32
    variance2: np.ndarray  # float32
    alpha1: np.ndarray  # float32
    beta1: np.ndarray  # float32
    alpha2: np.ndarray  # float32
    beta2: np.ndarray  # float32
    alpha_combined: np.ndarray  # float32
    beta_combined: np.ndarray  # float32
    n1: np.ndarray  # int32
    n2: np.ndarray  # int32
    significant: np.ndarray  # bool
    fallback_used: np.ndarray  # bool
    global_significant: np.ndarray  # bool

    def __post_init__(self):
        """Ensure all arrays have the same length and proper dtypes."""
        n = len(self.positions)
        assert all(
            len(arr) == n
            for arr in [
                self.test_statistics,
                self.p_values,
                self.q_values,
                self.methods,
                self.mean1,
                self.mean2,
                self.variance1,
                self.variance2,
                self.alpha1,
                self.beta1,
                self.alpha2,
                self.beta2,
                self.alpha_combined,
                self.beta_combined,
                self.n1,
                self.n2,
                self.significant,
                self.fallback_used,
                self.global_significant,
            ]
        )

        # Convert to efficient dtypes
        self.positions = self.positions.astype(np.int32)
        self.test_statistics = self.test_statistics.astype(np.float32)
        self.p_values = self.p_values.astype(np.float32)
        self.q_values = self.q_values.astype(np.float32)
        self.mean1 = self.mean1.astype(np.float32)
        self.mean2 = self.mean2.astype(np.float32)
        self.variance1 = self.variance1.astype(np.float32)
        self.variance2 = self.variance2.astype(np.float32)
        self.alpha1 = self.alpha1.astype(np.float32)
        self.beta1 = self.beta1.astype(np.float32)
        self.alpha2 = self.alpha2.astype(np.float32)
        self.beta2 = self.beta2.astype(np.float32)
        self.alpha_combined = self.alpha_combined.astype(np.float32)
        self.beta_combined = self.beta_combined.astype(np.float32)
        self.n1 = self.n1.astype(np.int32)
        self.n2 = self.n2.astype(np.int32)
        self.significant = self.significant.astype(bool)
        self.fallback_used = self.fallback_used.astype(bool)
        self.global_significant = self.global_significant.astype(bool)

    @property
    def n_comparisons(self) -> int:
        """Number of comparisons."""
        return len(self.positions)

    @property
    def significant_mask(self) -> np.ndarray:
        """Boolean mask for significant comparisons."""
        return self.significant

    @property
    def delta_means(self) -> np.ndarray:
        """Calculate delta means (|mean1 - mean2|)."""
        return np.abs(self.mean1 - self.mean2).astype(np.float32)

    def to_dmp_data(self):
        """Convert to DMPData format for DMPFilter."""
        from .dmp_filter import DMPData

        return DMPData(
            positions=self.positions,
            p_values=self.p_values,
            q_values=self.q_values,
            mean1=self.mean1,
            mean2=self.mean2,
            alpha1=self.alpha1,
            beta1=self.beta1,
            alpha2=self.alpha2,
            beta2=self.beta2,
            variance1=self.variance1,
            variance2=self.variance2,
        )

    def to_smart_lrt_results(self) -> List[SmartLRTResult]:
        """Convert to list of SmartLRTResult objects for backward compatibility."""
        results = []
        for i in range(self.n_comparisons):
            result = SmartLRTResult(
                position=int(self.positions[i]),
                test_statistic=float(self.test_statistics[i]),
                p_value=float(self.p_values[i]),
                method=str(self.methods[i]),
                mean1=float(self.mean1[i]),
                mean2=float(self.mean2[i]),
                variance1=float(self.variance1[i]),
                variance2=float(self.variance2[i]),
                alpha1=float(self.alpha1[i]),
                beta1=float(self.beta1[i]),
                alpha2=float(self.alpha2[i]),
                beta2=float(self.beta2[i]),
                alpha_combined=float(self.alpha_combined[i]),
                beta_combined=float(self.beta_combined[i]),
                n1=int(self.n1[i]),
                n2=int(self.n2[i]),
                significant=bool(self.significant[i]),
                fallback_used=bool(self.fallback_used[i]),
                q_value=float(self.q_values[i]),
                global_significant=bool(self.global_significant[i]),
            )
            results.append(result)
        return results


class FDRAnalyzer:
    """
    FDR analysis wrapper that integrates methylation_fdr_analysis functions
    with GPU support and enhanced reporting capabilities.
    """

    def __init__(self, use_gpu: bool = True, output_dir: Optional[Path] = None):
        self.use_gpu = use_gpu and GPU_AVAILABLE
        self.output_dir = output_dir

    def compute_qvalues(
        self, p_values: np.ndarray, output_prefix: str
    ) -> Tuple[np.ndarray, float]:
        """
        Apply Storey's FDR correction to p-values.

        Args:
            p_values: Array of p-values
            output_prefix: Prefix for output files

        Returns:
            Tuple of (q_values, pi0_estimate)
        """
        try:
            # Generate pi0 plot if output directory is specified
            plot_path = None
            if self.output_dir:
                plot_path = str(self.output_dir / f"{output_prefix}_pi0_vs_lambda.html")

            # Try FDR correction with plotting first
            try:
                q_values, pi0 = storey_qvalues(
                    p_values,
                    plot_pi0=(plot_path is not None),
                    plot_path=plot_path or "pi0_vs_lambda.html",
                    plot_title=f"Storey's Pi0 vs Lambda - {output_prefix}",
                )
                logger.info(f"FDR correction applied: pi0={pi0:.3f}")
                if plot_path:
                    logger.info(f"Pi0 plot saved to: {plot_path}")

            except Exception as plot_error:
                logger.warning(
                    f"FDR plotting failed: {plot_error}, retrying without plotting"
                )
                # Retry without plotting
                q_values, pi0 = storey_qvalues(
                    p_values,
                    plot_pi0=False,
                    plot_path=plot_path or "pi0_vs_lambda.html",
                    plot_title=f"Storey's Pi0 vs Lambda - {output_prefix}",
                )
                logger.info(f"FDR correction applied (no plot): pi0={pi0:.3f}")

            return q_values, pi0

        except Exception as e:
            logger.warning(f"FDR correction failed: {e}, using uncorrected p-values")
            return p_values, 1.0

    def compute_global_significance(
        self, 
        p_values: np.ndarray, 
        weights: Optional[np.ndarray] = None
    ) -> Tuple[float, float, bool]:
        """
        Compute global significance using Stouffer's method.

        Args:
            p_values: Array of p-values
            weights: Optional weights for Stouffer's method

        Returns:
            Tuple of (global_p_value, z_score, is_significant)
        """
        try:
            global_p, z_score = stouffer_global_p(p_values, weights)
            logger.info(f"Global significance (Stouffer): p={global_p:.6f}, z-score={z_score:.6f}")

            return (global_p, z_score, True)

        except Exception as e:
            logger.warning(f"Global significance computation failed: {e}")
            return (1.0, 0.0, False)

    def group_significant_regions(
        self, results: List[SmartLRTResult], q_threshold: float = 0.05
    ) -> List[Tuple[int, int]]:
        """
        Group significant positions into regions.

        Args:
            results: List of SmartLRTResult objects
            q_threshold: Q-value threshold for significance

        Returns:
            List of (start_position, end_position) tuples
        """
        positions = np.array(
            [r.position for r in results if r.q_value and r.q_value <= q_threshold]
        )
        q_values = np.array(
            [r.q_value for r in results if r.q_value and r.q_value <= q_threshold]
        )

        if len(positions) == 0:
            return []

        return group_significant_positions(positions, q_values, threshold=q_threshold)


class SmartCentroidComparator:
    """
    Smart centroid comparator with GPU acceleration and FDR analysis.

    This class performs statistical comparisons between two extended centroids
    using likelihood ratio tests and normal approximations, with optional
    FDR correction and global significance analysis.
    """

    def __init__(
        self,
        centroid1_path: Path,
        centroid2_path: Path,
        output_dir: Path,
        significance_level: float = 0.05,
        use_gpu: bool = True,
        batch_size: int = 1000000,  # Default large batch size, will be optimized based on GPU memory
        # n_jobs parameter removed - multiprocessing not beneficial for GPU operations
        normal_approx_threshold: int = 30,
        min_beta_params: float = 2.0,
        use_mle_threshold: float = 0.1,
        min_n_for_mle: int = 10,
        max_newton_iters: int = 50,
        newton_tol: float = 1e-6,
        min_N: int = 10,  # Minimum sample size for reliable p-value calculation
        # New FDR analysis parameters
        apply_fdr_correction: bool = True,
        fdr_method: str = "storey",  # "storey" or "benjamini_hochberg"
        stouffer_weights: Optional[np.ndarray] = None,
        global_significance_threshold: float = 0.05,
        # DMP filtering parameters
        apply_dmp_filtering: bool = False,
        dmp_filter_method: str = "combined",
        min_overlap: float = 0.6,
        min_delta_mean: float = 0.1,
        min_jeffreys_divergence: float = 0.3,
        min_cohen_d: float = 0.5,
        min_auc: float = 0.6,
        max_selected_dmps: int = 1000,
        # Minimum subset selection parameters
        target_auc: float = 0.95,
        use_gpu_selection: bool = True,
        selection_metric: str = "auc",
        target_youden: float = 0.9,
        selection_algorithm: str = "auto",
        time_budget_seconds: int = 300,
    ):
        """
        Initialize the smart centroid comparator.

        Args:
            centroid1_path: Path to first extended centroid .h5 file
            centroid2_path: Path to second extended centroid .h5 file
            output_dir: Directory to save results
            significance_level: Alpha level for significance testing
            use_gpu: Whether to use GPU acceleration (if available)
            batch_size: Number of positions to process in each batch (will be optimized based on available GPU memory)
            # n_jobs parameter removed - multiprocessing not beneficial for GPU operations
            normal_approx_threshold: Minimum sample size for normal approximation
            min_beta_params: Minimum alpha/beta values for normal approximation
            use_mle_threshold: Threshold for when to use MLE in hybrid mode
            min_n_for_mle: Minimum sample size to consider MLE in hybrid mode
            max_newton_iters: Maximum iterations for Newton's method in GPU MLE
            newton_tol: Convergence tolerance for Newton's method
        """
        self.centroid1_path = Path(centroid1_path)
        self.centroid2_path = Path(centroid2_path)
        self.output_dir = Path(output_dir)
        self.significance_level = significance_level
        self.use_gpu = use_gpu and GPU_AVAILABLE

        # Much larger batch size for GPU efficiency - use available memory more aggressively
        if self.use_gpu:
            # For GPU, use much larger batches to minimize the number of batches
            # This will be overridden by memory estimation in fully vectorized mode
            self.batch_size = max(batch_size, 1000000)  # 1M positions per batch
        else:
            self.batch_size = batch_size

        # n_jobs removed - multiprocessing not beneficial for GPU operations
        self.normal_approx_threshold = normal_approx_threshold
        self.min_beta_params = min_beta_params
        self.use_mle_threshold = use_mle_threshold
        self.min_n_for_mle = min_n_for_mle
        self.max_newton_iters = max_newton_iters
        self.newton_tol = newton_tol
        self.min_N = min_N  # Minimum sample size for reliable p-value calculation

        # Validate inputs
        self._validate_inputs()

        # Load centroid data
        self.centroid1_data = self._load_centroid_data(self.centroid1_path)
        self.centroid2_data = self._load_centroid_data(self.centroid2_path)

        # Create position maps for fast lookup
        self.pos1_to_idx = {
            pos: idx for idx, pos in enumerate(self.centroid1_data["pos"])
        }
        self.pos2_to_idx = {
            pos: idx for idx, pos in enumerate(self.centroid2_data["pos"])
        }

        # Find common positions
        self.common_positions = self._find_common_positions()

        # Filter out positions with invalid data using fast lookup
        progress_iter = tqdm(
            self.common_positions, desc="Filtering valid positions", unit="pos"
        )
        valid_positions = []
        total_common = len(self.common_positions)
        insufficient_sample_count = 0
        for _, pos in enumerate(progress_iter):
            if pos in self.pos1_to_idx and pos in self.pos2_to_idx:
                idx1 = self.pos1_to_idx[pos]
                idx2 = self.pos2_to_idx[pos]

                # Extract all required values
                n1 = self.centroid1_data["N"][idx1]
                n2 = self.centroid2_data["N"][idx2]

                # Check for insufficient sample sizes
                if n1 < self.min_N or n2 < self.min_N:
                    insufficient_sample_count += 1
                    continue
                mC1 = self.centroid1_data["mC"][idx1]
                mC2 = self.centroid2_data["mC"][idx2]
                uC1 = self.centroid1_data["uC"][idx1]
                uC2 = self.centroid2_data["uC"][idx2]
                Sx1 = self.centroid1_data["Sx"][idx1]
                Sx2 = self.centroid2_data["Sx"][idx2]
                Sx21 = self.centroid1_data["Sx2"][idx1]
                Sx22 = self.centroid2_data["Sx2"][idx2]
                log_x_sum1 = self.centroid1_data["log_x_sum"][idx1]
                log_x_sum2 = self.centroid2_data["log_x_sum"][idx2]
                log_1_minus_x_sum1 = self.centroid1_data["log_1_minus_x_sum"][idx1]
                log_1_minus_x_sum2 = self.centroid2_data["log_1_minus_x_sum"][idx2]

                # Check all values are valid (not None, not NaN, not inf)
                def is_valid_value(val):
                    return val is not None and np.isfinite(val)

                if (
                    n1 > 0
                    and n2 > 0
                    and is_valid_value(mC1)
                    and is_valid_value(mC2)
                    and is_valid_value(uC1)
                    and is_valid_value(uC2)
                    and is_valid_value(Sx1)
                    and is_valid_value(Sx2)
                    and is_valid_value(Sx21)
                    and is_valid_value(Sx22)
                    and is_valid_value(log_x_sum1)
                    and is_valid_value(log_x_sum2)
                    and is_valid_value(log_1_minus_x_sum1)
                    and is_valid_value(log_1_minus_x_sum2)
                    and mC1 >= 0
                    and mC2 >= 0  # mC and uC should be non-negative
                    and uC1 >= 0
                    and uC2 >= 0
                ):
                    valid_positions.append(pos)

        self.common_positions = np.array(valid_positions, dtype=np.uint32)
        self.insufficient_sample_count = insufficient_sample_count
        logger.debug(
            f"Found {len(self.common_positions)} valid positions out of {total_common} common positions"
        )
        logger.debug(
            f"Filtered out {insufficient_sample_count} positions with insufficient sample sizes (min_N={self.min_N})"
        )

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize FDR analyzer
        self.fdr_analyzer = FDRAnalyzer(use_gpu=use_gpu, output_dir=output_dir)
        self.apply_fdr_correction = apply_fdr_correction
        self.fdr_method = fdr_method
        self.stouffer_weights = stouffer_weights
        self.global_significance_threshold = global_significance_threshold

        # DMP filtering parameters
        self.apply_dmp_filtering = apply_dmp_filtering
        self.dmp_filter_method = dmp_filter_method
        self.min_overlap = min_overlap
        self.min_delta_mean = min_delta_mean
        self.min_jeffreys_divergence = min_jeffreys_divergence
        self.min_cohen_d = min_cohen_d
        self.min_auc = min_auc
        self.max_selected_dmps = max_selected_dmps
        
        # Minimum subset selection parameters
        self.target_auc = target_auc
        self.use_gpu_selection = use_gpu_selection
        self.selection_metric = selection_metric
        self.target_youden = target_youden
        self.selection_algorithm = selection_algorithm
        self.time_budget_seconds = time_budget_seconds

        # Set up signal handling for graceful cleanup (only if not already set up globally)
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful GPU cleanup on interruption.
        Only sets up handlers if global handlers are not already registered."""
        
        # Check if global cleanup handlers are already registered
        if are_global_cleanup_handlers_registered():
            logger.debug("Using global GPU cleanup handlers")
            return
        
        # Only set up class-level handlers if no global handlers exist
        def signal_handler(signum, frame):
            signal_name = (
                signal.Signals(signum).name
                if hasattr(signal.Signals, signum)
                else str(signum)
            )
            print(
                f"\n🚨 Class-level signal handler: Received {signal_name} ({signum}), cleaning up GPU memory..."
            )
            cleanup_gpu_memory()
            print("🔄 Exiting gracefully...")
            exit(1)

        def exception_handler(exc_type, exc_value, exc_traceback):
            """Handle uncaught exceptions with GPU cleanup."""
            print(f"\n💥 Class-level exception handler: {exc_type.__name__}: {exc_value}")
            cleanup_gpu_memory()
            print("🔄 Exiting due to exception...")

        # Register signal handlers for all common interruption signals
        signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # Termination signal
        signal.signal(signal.SIGHUP, signal_handler)  # Hangup signal
        signal.signal(signal.SIGQUIT, signal_handler)  # Quit signal
        signal.signal(signal.SIGABRT, signal_handler)  # Abort signal

        # Set up exception handler for uncaught exceptions
        sys.excepthook = exception_handler
        
        # Register atexit cleanup
        register_global_cleanup_handlers()

        logger.debug("🛡️  Class-level signal handlers and exception handlers registered for GPU cleanup")

    def _validate_inputs(self):
        """Validate input files exist and are extended centroids."""
        if not self.centroid1_path.exists():
            raise FileNotFoundError(f"Centroid 1 not found: {self.centroid1_path}")
        if not self.centroid2_path.exists():
            raise FileNotFoundError(f"Centroid 2 not found: {self.centroid2_path}")

        # Use CentroidPairHandler for proper SRP compliance
        pair_handler = CentroidPairHandler(self.centroid1_path, self.centroid2_path)
        pair_handler.validate_both_extended()

    def _load_centroid_data(self, centroid_path: Path) -> Dict[str, np.ndarray]:
        """Load extended centroid data using MethylSample for SRP compliance."""
        logger.debug(f"Loading centroid data from {centroid_path}")
        from ..utils.sample_handler import CentroidHandler
        handler = CentroidHandler(centroid_path)
        return handler.get_data_dict()

    def _find_common_positions(self) -> np.ndarray:
        """Find positions that exist in both centroids."""
        pos1 = set(self.centroid1_data["pos"])
        pos2 = set(self.centroid2_data["pos"])
        common = pos1.intersection(pos2)
        return np.array(sorted(common), dtype=np.uint32)

    def _beta_mom_estimate(
        self, n: float, Sx: float, Sx2: float
    ) -> Tuple[float, float]:
        """Method of Moments estimator for Beta parameters using MethylUtils."""
        if n <= 1:
            return 1.0, 1.0
        # Convert to MethylUtils interface: m = methylation level = Sx/n, n = coverage
        m = Sx / n
        alpha, beta = get_sample_beta_mom(np.array([m]), np.array([n]), use_gpu=False)
        return float(alpha[0]), float(beta[0])

    def _beta_mom_vectorized_gpu(self, n, Sx, Sx2):
        """Vectorized Method of Moments estimator for GPU using MethylUtils."""
        # Convert to MethylUtils interface: m = methylation level = Sx/n, n = coverage
        m = Sx / n
        return get_sample_beta_mom(m, n, use_gpu=True)

    def _beta_mle_from_suffstats(
        self, n: float, log_x_sum: float, log_1_minus_x_sum: float
    ) -> Tuple[float, float]:
        """Maximum Likelihood estimator for Beta parameters using root-finding."""
        if n <= 0:
            return 1.0, 1.0

        # Check for None or invalid values
        if (
            log_x_sum is None
            or log_1_minus_x_sum is None
            or not np.isfinite(log_x_sum)
            or not np.isfinite(log_1_minus_x_sum)
        ):
            return 1.0, 1.0

        avg_log_x = log_x_sum / n
        avg_log_1mx = log_1_minus_x_sum / n

        # Check for extreme cases that cause numerical instability
        if abs(avg_log_x) > 10 or abs(avg_log_1mx) > 10:
            return 1.0, 1.0

        def inv_psi(y):
            if y >= -2.22:
                x0 = np.exp(y) + 0.5
            else:
                x0 = -1.0 / (y + psi(1))
            x = x0
            for _ in range(5):
                x = x - (psi(x) - y) / polygamma(1, x)
                if x <= 0:
                    x = 1e-6
            return x if x > 0 else 1e-6

        try:

            def f_for_beta(q):
                diff = avg_log_x - avg_log_1mx
                alpha_est = inv_psi(psi(q) + diff)
                return psi(q) - psi(alpha_est + q) - avg_log_1mx

            sol = root_scalar(
                f_for_beta, bracket=[1e-6, 1e3], method="bisect", maxiter=50
            )
            if not sol.converged:
                return self._beta_mom_estimate(n, np.exp(avg_log_x) * n, None)

            beta_hat = sol.root
            alpha_hat = inv_psi(psi(beta_hat) + (avg_log_x - avg_log_1mx))

            if alpha_hat <= 0 or beta_hat <= 0:
                raise ValueError("MLE solution out of bounds")

            return float(alpha_hat), float(beta_hat)
        except Exception:
            # Fallback to uniform distribution for failed MLE
            return 1.0, 1.0

    def _inv_digamma_vectorized(self, y, iters=5):
        """Vectorized inverse digamma for GPU."""
        # Initial guess
        x = cp.where(y >= -2.22, cp.exp(y) + 0.5, -1.0 / (y + gpu_digamma(1.0)))
        x = cp.maximum(x, 1e-6)
        for _ in range(iters):
            psi_x = gpu_digamma(x)
            tri_x = gpu_trigamma(x)
            x = x - (psi_x - y) / tri_x
            x = cp.maximum(x, 1e-6)
        return x

    def _beta_mle_vectorized_gpu(self, n, log_x_sum, log_1_minus_x_sum):
        """Vectorized MLE for Beta parameters on GPU using Newton's method."""
        avg_log_x = log_x_sum / n
        avg_log_1mx = log_1_minus_x_sum / n
        diff = avg_log_x - avg_log_1mx

        # Initialize beta (q)
        q = cp.ones_like(n, dtype=cp.float64)

        for _ in range(self.max_newton_iters):
            psi_q = gpu_digamma(q)
            alpha = self._inv_digamma_vectorized(psi_q + diff)
            g = psi_q - gpu_digamma(alpha + q) - avg_log_1mx

            # Derivative
            tri_q = gpu_trigamma(q)
            tri_alpha = gpu_trigamma(alpha)
            tri_alpha_q = gpu_trigamma(alpha + q)
            alpha_deriv = tri_q / tri_alpha
            g_deriv = tri_q - tri_alpha_q * (alpha_deriv + 1)

            # Newton step
            step = g / g_deriv
            q_new = q - step
            q_new = cp.maximum(q_new, 1e-6)

            # Check convergence
            converged = cp.abs(step) < self.newton_tol
            if cp.all(converged):
                break
            q = q_new

        alpha = self._inv_digamma_vectorized(gpu_digamma(q) + diff)
        alpha = cp.maximum(alpha, 1e-6)
        q = cp.maximum(q, 1e-6)
        return alpha, q

    def _beta_loglik(
        self,
        alpha: float,
        beta: float,
        n: float,
        log_x_sum: float,
        log_1_minus_x_sum: float,
    ) -> float:
        """Calculate log-likelihood of data given Beta(alpha,beta) using sufficient statistics."""
        if alpha <= 0 or beta <= 0:
            return -np.inf
        gamma_term = gammaln(alpha + beta) - gammaln(alpha) - gammaln(beta)
        ll = n * gamma_term + (alpha - 1) * log_x_sum + (beta - 1) * log_1_minus_x_sum
        return ll

    def _beta_loglik_vectorized_gpu(self, alpha, beta, n, log_x_sum, log_1_minus_x_sum):
        """Vectorized log-likelihood for GPU."""
        gamma_term = gpu_gammaln(alpha + beta) - gpu_gammaln(alpha) - gpu_gammaln(beta)
        ll = n * gamma_term + (alpha - 1) * log_x_sum + (beta - 1) * log_1_minus_x_sum
        return ll

    def _compute_lrt_statistic(self, ll1, ll2, ll0, use_gpu=False):
        """
        Compute Likelihood Ratio Test statistic and p-value.

        Args:
            ll1: Log-likelihood under model 1 (separate distributions)
            ll2: Log-likelihood under model 2 (separate distributions)
            ll0: Log-likelihood under null model (combined distribution)
            use_gpu: Whether inputs are GPU arrays

        Returns:
            Tuple of (test_statistic, p_value)
        """
        if use_gpu:
            lrt_stat = 2 * ((ll1 + ll2) - ll0)
            lrt_stat = cp.maximum(lrt_stat, 0)
            p_val = gpu_chi2_sf_df2(lrt_stat)
        else:
            lrt_stat = 2 * ((ll1 + ll2) - ll0)
            if lrt_stat < 0:
                lrt_stat = 0.0
            p_val = chi2.sf(lrt_stat, df=2)
        return lrt_stat, p_val

    def _should_use_normal_approximation(
        self,
        n1: int,
        n2: int,
        alpha1: float,
        beta1: float,
        alpha2: float,
        beta2: float,
        mean1: float,
        mean2: float,
    ) -> bool:
        """Determine if normal approximation is appropriate for this position."""
        # Check sample size requirements
        if n1 < self.normal_approx_threshold or n2 < self.normal_approx_threshold:
            return False

        # Check Beta parameter requirements
        if (
            alpha1 < self.min_beta_params
            or beta1 < self.min_beta_params
            or alpha2 < self.min_beta_params
            or beta2 < self.min_beta_params
        ):
            return False

        # Check for extreme means (avoid skewed edge cases)
        if mean1 < 0.1 or mean1 > 0.9 or mean2 < 0.1 or mean2 > 0.9:
            return False

        return True

    def _perform_smart_test_single_position(self, pos: int) -> Optional[SmartLRTResult]:
        """Perform smart likelihood ratio test for a single position."""
        try:
            idx1 = self.pos1_to_idx[pos]
            idx2 = self.pos2_to_idx[pos]

            # Extract statistics
            n1 = self.centroid1_data["N"][idx1]
            n2 = self.centroid2_data["N"][idx2]
            Sx1 = self.centroid1_data["Sx"][idx1]
            Sx2 = self.centroid2_data["Sx"][idx2]
            Sx21 = self.centroid1_data["Sx2"][idx1]
            Sx22 = self.centroid2_data["Sx2"][idx2]
            log_x_sum1 = self.centroid1_data["log_x_sum"][idx1]
            log_x_sum2 = self.centroid2_data["log_x_sum"][idx2]
            log_1_minus_x_sum1 = self.centroid1_data["log_1_minus_x_sum"][idx1]
            log_1_minus_x_sum2 = self.centroid2_data["log_1_minus_x_sum"][idx2]

            # Convert scalar values to CPU for comparisons to avoid CuPy implicit conversion errors
            n1_val = float(n1.get()) if hasattr(n1, 'get') else float(n1)
            n2_val = float(n2.get()) if hasattr(n2, 'get') else float(n2)

            # Skip positions with insufficient sample sizes for reliable p-value calculation
            if n1_val < self.min_N or n2_val < self.min_N:
                return None

            # Skip positions with no data or invalid values
            if n1_val <= 0 or n2_val <= 0:
                return None

            # Check for None or NaN values in the statistics
            if (
                Sx1 is None
                or Sx2 is None
                or not np.isfinite(Sx1)
                or not np.isfinite(Sx2)
                or not np.isfinite(Sx21)
                or not np.isfinite(Sx22)
                or log_x_sum1 is None
                or log_x_sum2 is None
                or log_1_minus_x_sum1 is None
                or log_1_minus_x_sum2 is None
                or not np.isfinite(log_x_sum1)
                or not np.isfinite(log_x_sum2)
                or not np.isfinite(log_1_minus_x_sum1)
                or not np.isfinite(log_1_minus_x_sum2)
            ):
                return None

            # Calculate means and variances
            mean1 = Sx1 / n1
            mean2 = Sx2 / n2
            var1 = (Sx21 - (Sx1**2) / n1) / (n1 - 1) if n1_val > 1 else 0.0
            var2 = (Sx22 - (Sx2**2) / n2) / (n2 - 1) if n2_val > 1 else 0.0

            # Estimate Beta parameters using MoM (fast)
            alpha1, beta1 = self._beta_mom_estimate(n1, Sx1, Sx21)
            alpha2, beta2 = self._beta_mom_estimate(n2, Sx2, Sx22)

            # Decide which test to use
            use_normal = self._should_use_normal_approximation(
                n1_val, n2_val, alpha1, beta1, alpha2, beta2, mean1, mean2
            )

            if use_normal:
                # **Normal approximation (z-test) - faster for well-behaved cases**
                se = sqrt(var1 / n1 + var2 / n2 + 1e-12)
                z_stat = 0.0
                p_val = 1.0
                if se > 0:
                    z_stat = (mean1 - mean2) / se
                    p_val = 2 * (1 - cpu_norm.cdf(abs(z_stat)))

                return SmartLRTResult(
                    position=pos,
                    test_statistic=z_stat,
                    p_value=p_val,
                    method="NormalApprox",
                    mean1=mean1,
                    mean2=mean2,
                    variance1=var1,
                    variance2=var2,
                    n1=n1,
                    n2=n2,
                    significant=p_val < self.significance_level,
                    significance_level=self.significance_level,
                )
            else:
                # **Full LRT using Beta MLEs - more accurate for complex cases**
                # Get MLE parameters for each sample
                alpha1_mle, beta1_mle = self._beta_mle_from_suffstats(
                    n1, log_x_sum1, log_1_minus_x_sum1
                )
                alpha2_mle, beta2_mle = self._beta_mle_from_suffstats(
                    n2, log_x_sum2, log_1_minus_x_sum2
                )

                # Combined data stats
                n_comb = n1 + n2
                log_x_sum_comb = log_x_sum1 + log_x_sum2
                log_1_minus_x_sum_comb = log_1_minus_x_sum1 + log_1_minus_x_sum2

                # MLE for combined data under H0
                alpha_comb, beta_comb = self._beta_mle_from_suffstats(
                    n_comb, log_x_sum_comb, log_1_minus_x_sum_comb
                )

                # Compute log-likelihoods
                ll1 = self._beta_loglik(
                    alpha1_mle, beta1_mle, n1, log_x_sum1, log_1_minus_x_sum1
                )
                ll2 = self._beta_loglik(
                    alpha2_mle, beta2_mle, n2, log_x_sum2, log_1_minus_x_sum2
                )
                ll0 = self._beta_loglik(
                    alpha_comb,
                    beta_comb,
                    n_comb,
                    log_x_sum_comb,
                    log_1_minus_x_sum_comb,
                )

                # Check if MLE failed and fallback to MoM
                fallback_used = False
                if not np.isfinite(ll1) or not np.isfinite(ll2) or not np.isfinite(ll0):
                    fallback_used = True
                    alpha1_mle, beta1_mle = alpha1, beta1
                    alpha2_mle, beta2_mle = alpha2, beta2

                    # Recompute combined via MoM
                    combined_mean = (Sx1 + Sx2) / (n1 + n2)

                    combined_var = (
                        ((Sx21 + Sx22) - (Sx1 + Sx2) ** 2 / (n1 + n2))
                        / ((n1 + n2) - 1)
                        if (n1_val + n2_val) > 1
                        else 0
                    )

                    if combined_var <= 0 or combined_var >= combined_mean * (
                        1 - combined_mean
                    ):
                        alpha_comb, beta_comb = 1.0, 1.0
                    else:
                        common = combined_mean * (1 - combined_mean) / combined_var - 1
                        alpha_comb = combined_mean * common
                        beta_comb = (1 - combined_mean) * common

                    # Recompute log-likelihoods with MoM params
                    ll1 = self._beta_loglik(
                        alpha1_mle, beta1_mle, n1, log_x_sum1, log_1_minus_x_sum1
                    )
                    ll2 = self._beta_loglik(
                        alpha2_mle, beta2_mle, n2, log_x_sum2, log_1_minus_x_sum2
                    )
                    ll0 = self._beta_loglik(
                        alpha_comb,
                        beta_comb,
                        n_comb,
                        log_x_sum_comb,
                        log_1_minus_x_sum_comb,
                    )

                # LRT statistic and p-value
                lrt_stat, p_val = self._compute_lrt_statistic(ll1, ll2, ll0, use_gpu=False)

                return SmartLRTResult(
                    position=pos,
                    test_statistic=lrt_stat,
                    p_value=p_val,
                    method="LRT",
                    mean1=mean1,
                    mean2=mean2,
                    variance1=var1,
                    variance2=var2,
                    alpha1=alpha1_mle,
                    beta1=beta1_mle,
                    alpha2=alpha2_mle,
                    beta2=beta2_mle,
                    alpha_combined=alpha_comb,
                    beta_combined=beta_comb,
                    n1=n1,
                    n2=n2,
                    significant=p_val < self.significance_level,
                    significance_level=self.significance_level,
                    fallback_used=fallback_used,
                )

        except Exception as e:
            logger.warning(f"Error processing position {pos}: {e}")
            return None

    def _process_batch_cpu(
        self, positions: np.ndarray
    ) -> List[Optional[SmartLRTResult]]:
        """Process a batch of positions using CPU."""
        results = []
        for pos in positions:
            result = self._perform_smart_test_single_position(pos)
            results.append(result)
        return results

    def _process_batch_gpu(
        self, positions: np.ndarray
    ) -> List[Optional[SmartLRTResult]]:
        """Process a batch of positions using GPU acceleration with CuPy."""
        if not GPU_AVAILABLE or len(positions) == 0:
            return self._process_batch_cpu(positions)

        try:
            # Get indices for all positions in the batch
            batch_indices1 = np.array([self.pos1_to_idx[pos] for pos in positions])
            batch_indices2 = np.array([self.pos2_to_idx[pos] for pos in positions])

            # Extract data for batch and move to GPU
            def gather_gpu(key, indices, data):
                return cp.array(data[key][indices], dtype=cp.float64)

            n1 = gather_gpu("N", batch_indices1, self.centroid1_data)
            n2 = gather_gpu("N", batch_indices2, self.centroid2_data)
            Sx1 = gather_gpu("Sx", batch_indices1, self.centroid1_data)
            Sx2 = gather_gpu("Sx", batch_indices2, self.centroid2_data)
            Sx21 = gather_gpu("Sx2", batch_indices1, self.centroid1_data)
            Sx22 = gather_gpu("Sx2", batch_indices2, self.centroid2_data)
            log_x_sum1 = gather_gpu("log_x_sum", batch_indices1, self.centroid1_data)
            log_x_sum2 = gather_gpu("log_x_sum", batch_indices2, self.centroid2_data)
            log_1mx_sum1 = gather_gpu(
                "log_1_minus_x_sum", batch_indices1, self.centroid1_data
            )
            log_1mx_sum2 = gather_gpu(
                "log_1_minus_x_sum", batch_indices2, self.centroid2_data
            )

            # Compute means and variances
            mean1 = Sx1 / n1
            mean2 = Sx2 / n2
            var1 = (Sx21 - (Sx1**2) / n1) / cp.maximum(n1 - 1, 1)
            var2 = (Sx22 - (Sx2**2) / n2) / cp.maximum(n2 - 1, 1)

            # MoM estimates
            alpha1_mom, beta1_mom = self._beta_mom_vectorized_gpu(n1, Sx1, Sx21)
            alpha2_mom, beta2_mom = self._beta_mom_vectorized_gpu(n2, Sx2, Sx22)

            # Decide which positions use normal approximation
            use_normal = (
                (n1 >= self.normal_approx_threshold)
                & (n2 >= self.normal_approx_threshold)
                & (alpha1_mom >= self.min_beta_params)
                & (beta1_mom >= self.min_beta_params)
                & (alpha2_mom >= self.min_beta_params)
                & (beta2_mom >= self.min_beta_params)
                & (mean1 > 0.1)
                & (mean1 < 0.9)
                & (mean2 > 0.1)
                & (mean2 < 0.9)
            )

            results = []

            # Convert GPU arrays to CPU for all positions
            mean1_cpu = cp.asnumpy(mean1)
            mean2_cpu = cp.asnumpy(mean2)
            var1_cpu = cp.asnumpy(var1)
            var2_cpu = cp.asnumpy(var2)
            n1_cpu = cp.asnumpy(n1)
            n2_cpu = cp.asnumpy(n2)

            # Process normal approximation cases
            has_normal = bool(cp.any(use_normal))
            if has_normal:
                normal_mask = use_normal
                normal_indices = cp.where(normal_mask)[0]

                # Vectorized z-test computation
                se = cp.sqrt(
                    var1[normal_mask] / n1[normal_mask]
                    + var2[normal_mask] / n2[normal_mask]
                    + 1e-12
                )
                z_stat = (mean1[normal_mask] - mean2[normal_mask]) / se
                p_val = 2 * (1 - gpu_norm_cdf(cp.abs(z_stat)))

                # Convert back to CPU and create results
                normal_indices_cpu = cp.asnumpy(normal_indices)
                z_stat_cpu = cp.asnumpy(z_stat)
                p_val_cpu = cp.asnumpy(p_val)

                for i, idx in enumerate(normal_indices_cpu):
                    result = SmartLRTResult(
                        position=positions[idx],
                        test_statistic=float(z_stat_cpu[i]),
                        p_value=float(p_val_cpu[i]),
                        method="NormalApprox",
                        mean1=float(mean1_cpu[idx]),
                        mean2=float(mean2_cpu[idx]),
                        variance1=float(var1_cpu[idx]),
                        variance2=float(var2_cpu[idx]),
                        n1=int(n1_cpu[idx]),
                        n2=int(n2_cpu[idx]),
                        significant=float(p_val_cpu[i]) < self.significance_level,
                        significance_level=self.significance_level,
                    )
                    results.append((idx, result))

            # Process LRT cases
            lrt_mask = ~use_normal
            has_lrt = bool(cp.any(lrt_mask))
            if has_lrt:
                lrt_indices = cp.where(lrt_mask)[0]

                # Subset data for LRT
                n1_lrt = n1[lrt_mask]
                n2_lrt = n2[lrt_mask]
                log_x_sum1_lrt = log_x_sum1[lrt_mask]
                log_x_sum2_lrt = log_x_sum2[lrt_mask]
                log_1mx_sum1_lrt = log_1mx_sum1[lrt_mask]
                log_1mx_sum2_lrt = log_1mx_sum2[lrt_mask]

                # MLE for both groups
                alpha1_mle, beta1_mle = self._beta_mle_vectorized_gpu(
                    n1_lrt, log_x_sum1_lrt, log_1mx_sum1_lrt
                )
                alpha2_mle, beta2_mle = self._beta_mle_vectorized_gpu(
                    n2_lrt, log_x_sum2_lrt, log_1mx_sum2_lrt
                )

                # Combined data
                n_comb = n1_lrt + n2_lrt
                log_x_sum_comb = log_x_sum1_lrt + log_x_sum2_lrt
                log_1mx_sum_comb = log_1mx_sum1_lrt + log_1mx_sum2_lrt
                alpha_comb, beta_comb = self._beta_mle_vectorized_gpu(
                    n_comb, log_x_sum_comb, log_1mx_sum_comb
                )

                # Compute log-likelihoods
                ll1 = self._beta_loglik_vectorized_gpu(
                    alpha1_mle, beta1_mle, n1_lrt, log_x_sum1_lrt, log_1mx_sum1_lrt
                )
                ll2 = self._beta_loglik_vectorized_gpu(
                    alpha2_mle, beta2_mle, n2_lrt, log_x_sum2_lrt, log_1mx_sum2_lrt
                )
                ll0 = self._beta_loglik_vectorized_gpu(
                    alpha_comb, beta_comb, n_comb, log_x_sum_comb, log_1mx_sum_comb
                )

                # Check for invalid likelihoods and fallback to MoM
                invalid_ll = ~cp.isfinite(ll1 + ll2 + ll0)
                has_invalid = bool(cp.any(invalid_ll))
                fallback_indices = (
                    cp.where(invalid_ll)[0] if has_invalid else cp.array([])
                )

                if has_invalid:
                    # Fallback to MoM for invalid cases
                    alpha1_mle[invalid_ll] = alpha1_mom[lrt_mask][invalid_ll]
                    beta1_mle[invalid_ll] = beta1_mom[lrt_mask][invalid_ll]
                    alpha2_mle[invalid_ll] = alpha2_mom[lrt_mask][invalid_ll]
                    beta2_mle[invalid_ll] = beta2_mom[lrt_mask][invalid_ll]

                    # Combined MoM
                    Sx_comb = Sx1[lrt_mask][invalid_ll] + Sx2[lrt_mask][invalid_ll]
                    Sx2_comb = (
                        Sx21[lrt_mask][invalid_ll] + Sx22[lrt_mask][invalid_ll]
                    )
                    alpha_comb_mom, beta_comb_mom = self._beta_mom_vectorized_gpu(
                        n_comb[invalid_ll], Sx_comb, Sx2_comb
                    )
                    alpha_comb[invalid_ll] = alpha_comb_mom
                    beta_comb[invalid_ll] = beta_comb_mom

                    # Recompute likelihoods
                    ll1[invalid_ll] = self._beta_loglik_vectorized_gpu(
                        alpha1_mle[invalid_ll],
                        beta1_mle[invalid_ll],
                        n1_lrt[invalid_ll],
                        log_x_sum1_lrt[invalid_ll],
                        log_1mx_sum1_lrt[invalid_ll],
                    )
                    ll2[invalid_ll] = self._beta_loglik_vectorized_gpu(
                        alpha2_mle[invalid_ll],
                        beta2_mle[invalid_ll],
                        n2_lrt[invalid_ll],
                        log_x_sum2_lrt[invalid_ll],
                        log_1mx_sum2_lrt[invalid_ll],
                    )
                    ll0[invalid_ll] = self._beta_loglik_vectorized_gpu(
                        alpha_comb[invalid_ll],
                        beta_comb[invalid_ll],
                        n_comb[invalid_ll],
                        log_x_sum_comb[invalid_ll],
                        log_1mx_sum_comb[invalid_ll],
                    )

                # LRT statistic and p-value
                lrt_stat, p_val = self._compute_lrt_statistic(ll1, ll2, ll0, use_gpu=True)

                # Convert to CPU and create results
                lrt_indices_cpu = cp.asnumpy(lrt_indices)
                lrt_stat_cpu = cp.asnumpy(lrt_stat)
                p_val_cpu = cp.asnumpy(p_val)
                alpha1_cpu = cp.asnumpy(alpha1_mle)
                beta1_cpu = cp.asnumpy(beta1_mle)
                alpha2_cpu = cp.asnumpy(alpha2_mle)
                beta2_cpu = cp.asnumpy(beta2_mle)
                alpha_comb_cpu = cp.asnumpy(alpha_comb)
                beta_comb_cpu = cp.asnumpy(beta_comb)
                fallback_indices_cpu = (
                    cp.asnumpy(fallback_indices) if fallback_indices.size > 0 else []
                )

                for i, idx in enumerate(lrt_indices_cpu):
                    result = SmartLRTResult(
                        position=positions[idx],
                        test_statistic=float(lrt_stat_cpu[i]),
                        p_value=float(p_val_cpu[i]),
                        method="LRT",
                        mean1=float(mean1_cpu[idx]),
                        mean2=float(mean2_cpu[idx]),
                        variance1=float(var1_cpu[idx]),
                        variance2=float(var2_cpu[idx]),
                        alpha1=float(alpha1_cpu[i]),
                        beta1=float(beta1_cpu[i]),
                        alpha2=float(alpha2_cpu[i]),
                        beta2=float(beta2_cpu[i]),
                        alpha_combined=float(alpha_comb_cpu[i]),
                        beta_combined=float(beta_comb_cpu[i]),
                        n1=int(n1_cpu[idx]),
                        n2=int(n2_cpu[idx]),
                        significant=float(p_val_cpu[i]) < self.significance_level,
                        significance_level=self.significance_level,
                        fallback_used=(i in fallback_indices_cpu)
                        if len(fallback_indices_cpu) > 0
                        else False,
                    )
                    results.append((idx, result))

            # Sort results by original position order
            results.sort(key=lambda x: x[0])
            return [r[1] for r in results]

        except Exception as e:
            logger.warning(f"GPU processing failed, falling back to CPU: {e}")
            return self._process_batch_cpu(positions)

    def _apply_fdr_analysis_vectorized(
        self, comparison_data: ComparisonData, output_prefix: str
    ) -> Tuple[np.ndarray, float, float, float, bool]:
        """
        Apply FDR correction and compute global significance using vectorized operations.

        Returns:
            Tuple of (q_values, pi0_estimate, global_p_value, z_score, global_significant)
        """
        if not self.apply_fdr_correction:
            # Return uncorrected values - use raw p-values for Stouffer's method
            q_values = comparison_data.p_values.copy()
            pi0 = 1.0
            global_p, z_score, global_significant = (
                self.fdr_analyzer.compute_global_significance(
                    comparison_data.p_values, self.stouffer_weights
                )
            )
            return q_values, pi0, global_p, z_score, global_significant

        # Apply FDR correction
        logger.info("Starting FDR correction...")
        q_values, pi0 = self.fdr_analyzer.compute_qvalues(
            comparison_data.p_values, output_prefix
        )
        logger.info("FDR correction completed")

        # Compute global significance using q-values when FDR correction is enabled
        global_p, z_score, _ = self.fdr_analyzer.compute_global_significance(
            q_values, self.stouffer_weights
        )
        global_significant = global_p <= self.global_significance_threshold

        return q_values, pi0, global_p, z_score, global_significant

    def _apply_fdr_analysis(
        self, all_results: List[SmartLRTResult], output_prefix: str
    ) -> Tuple[np.ndarray, float, float, float, bool]:
        """
        Apply FDR correction and compute global significance.
        Kept for backward compatibility.

        Returns:
            Tuple of (q_values, pi0_estimate, global_p_value, z_score, global_significant)
        """
        if not self.apply_fdr_correction:
            # Return uncorrected values - use raw p-values for Stouffer's method
            p_values = np.array([r.p_value for r in all_results if r is not None])
            q_values = p_values.copy()
            pi0 = 1.0
            global_p, z_score, global_significant = (
                self.fdr_analyzer.compute_global_significance(
                    p_values, self.stouffer_weights
                )
            )
            return q_values, pi0, global_p, z_score, global_significant

        # Extract p-values for FDR correction
        p_values = np.array([r.p_value for r in all_results if r is not None])

        # Apply FDR correction
        logger.info("Starting FDR correction...")
        q_values, pi0 = self.fdr_analyzer.compute_qvalues(p_values, output_prefix)
        logger.info("FDR correction completed")

        # Compute global significance using q-values when FDR correction is enabled
        global_p, z_score, _ = self.fdr_analyzer.compute_global_significance(
            q_values, self.stouffer_weights
        )
        global_significant = global_p <= self.global_significance_threshold

        return q_values, pi0, global_p, z_score, global_significant

    def _update_results_with_fdr(
        self,
        all_results: List[SmartLRTResult],
        q_values: np.ndarray,
        global_p: float,
        global_significant: bool,
    ):
        """Update SmartLRTResult objects with FDR analysis results."""
        for i, result in enumerate(all_results):
            if result is not None:
                result.q_value = q_values[i]
                result.significant = result.q_value <= self.significance_level
                result.global_significant = global_significant

    def _group_significant_regions_vectorized(
        self, comparison_data: ComparisonData
    ) -> List[Tuple[int, int]]:
        """Group significant positions into regions using vectorized operations."""
        if comparison_data.n_comparisons == 0:
            return []

        # Get significant positions
        significant_mask = comparison_data.significant
        if not np.any(significant_mask):
            return []

        significant_positions = comparison_data.positions[significant_mask]

        # Sort positions
        sorted_positions = np.sort(significant_positions)

        if len(sorted_positions) == 0:
            return []

        # Find gaps using vectorized operations
        diffs = np.diff(sorted_positions)
        gap_indices = np.where(diffs > 1)[0]

        regions = []
        start_idx = 0

        for gap_idx in gap_indices:
            # End current region
            regions.append(
                (int(sorted_positions[start_idx]), int(sorted_positions[gap_idx]))
            )
            start_idx = gap_idx + 1

        # Add final region
        regions.append((int(sorted_positions[start_idx]), int(sorted_positions[-1])))

        return regions

    def _group_significant_regions(
        self, all_results: List[SmartLRTResult]
    ) -> List[Tuple[int, int]]:
        """Group significant positions into regions.
        Kept for backward compatibility."""
        if not all_results:
            return []

        # Sort by position
        sorted_results = sorted(all_results, key=lambda x: x.position)

        regions = []
        if not sorted_results:
            return regions

        start_pos = sorted_results[0].position
        prev_pos = start_pos

        for result in sorted_results[1:]:
            if result.position != prev_pos + 1:
                # Gap found, end current region
                regions.append((start_pos, prev_pos))
                start_pos = result.position
            prev_pos = result.position

        # Add final region
        regions.append((start_pos, prev_pos))

        return regions

    def _convert_to_comparison_data(
        self, all_results: List[SmartLRTResult]
    ) -> ComparisonData:
        """Convert list of SmartLRTResult objects to efficient ComparisonData structure."""
        n_results = len(all_results)

        # Initialize arrays
        positions = np.zeros(n_results, dtype=np.int32)
        test_statistics = np.zeros(n_results, dtype=np.float32)
        p_values = np.zeros(n_results, dtype=np.float32)
        q_values = np.zeros(n_results, dtype=np.float32)
        methods = np.empty(n_results, dtype=object)
        mean1 = np.zeros(n_results, dtype=np.float32)
        mean2 = np.zeros(n_results, dtype=np.float32)
        variance1 = np.zeros(n_results, dtype=np.float32)
        variance2 = np.zeros(n_results, dtype=np.float32)
        alpha1 = np.zeros(n_results, dtype=np.float32)
        beta1 = np.zeros(n_results, dtype=np.float32)
        alpha2 = np.zeros(n_results, dtype=np.float32)
        beta2 = np.zeros(n_results, dtype=np.float32)
        alpha_combined = np.zeros(n_results, dtype=np.float32)
        beta_combined = np.zeros(n_results, dtype=np.float32)
        n1 = np.zeros(n_results, dtype=np.int32)
        n2 = np.zeros(n_results, dtype=np.int32)
        significant = np.zeros(n_results, dtype=bool)
        fallback_used = np.zeros(n_results, dtype=bool)
        global_significant = np.zeros(n_results, dtype=bool)

        for i, result in enumerate(all_results):
            positions[i] = result.position
            test_statistics[i] = result.test_statistic
            p_values[i] = result.p_value
            q_values[i] = result.q_value or result.p_value
            methods[i] = result.method
            mean1[i] = result.mean1
            mean2[i] = result.mean2
            variance1[i] = result.variance1
            variance2[i] = result.variance2
            alpha1[i] = result.alpha1 or 0.0
            beta1[i] = result.beta1 or 0.0
            alpha2[i] = result.alpha2 or 0.0
            beta2[i] = result.beta2 or 0.0
            alpha_combined[i] = result.alpha_combined or 0.0
            beta_combined[i] = result.beta_combined or 0.0
            n1[i] = result.n1
            n2[i] = result.n2
            significant[i] = result.significant
            fallback_used[i] = result.fallback_used
            global_significant[i] = result.global_significant

        return ComparisonData(
            positions=positions,
            test_statistics=test_statistics,
            p_values=p_values,
            q_values=q_values,
            methods=methods,
            mean1=mean1,
            mean2=mean2,
            variance1=variance1,
            variance2=variance2,
            alpha1=alpha1,
            beta1=beta1,
            alpha2=alpha2,
            beta2=beta2,
            alpha_combined=alpha_combined,
            beta_combined=beta_combined,
            n1=n1,
            n2=n2,
            significant=significant,
            fallback_used=fallback_used,
            global_significant=global_significant,
        )

    def compare_centroids_vectorized(
        self, output_prefix: str = "smart_centroid_comparison"
    ) -> Dict[str, any]:
        """
        Compare all positions between the two centroids using truly vectorized operations.

        Args:
            output_prefix: Prefix for output files

        Returns:
            Dictionary containing comparison results and statistics
        """
        logger.debug(
            f"Starting vectorized centroid comparison with {len(self.common_positions)} positions"
        )
        start_time = time.time()

        # Try fully vectorized processing first
        if self.use_gpu and GPU_AVAILABLE:
            try:
                logger.debug("🚀 Attempting fully vectorized GPU processing...")
                logger.debug(f"GPU available: {GPU_AVAILABLE}, use_gpu: {self.use_gpu}")
                return self._compare_centroids_fully_vectorized_gpu(
                    output_prefix, start_time
                )
            except MemoryError as e:
                logger.warning(
                    f"❌ Insufficient GPU memory for full vectorization: {e}"
                )
                logger.info("Falling back to batched processing...")
                # Clear GPU memory before falling back
                try:
                    import cupy as cp

                    cp.get_default_memory_pool().free_all_blocks()
                    logger.info("GPU memory cleared")
                except Exception as e:
                    logger.warning(f"GPU memory cleanup failed: {e}")
            except Exception as e:
                logger.warning(
                    f"❌ Fully vectorized GPU processing failed: {e}, falling back to batched processing"
                )
                logger.warning(f"Error type: {type(e).__name__}")
                import traceback

                logger.warning(f"Traceback: {traceback.format_exc()}")
                # Clear GPU memory before falling back
                try:
                    import cupy as cp

                    cp.get_default_memory_pool().free_all_blocks()
                    logger.info("GPU memory cleared")
                except Exception as e:
                    logger.warning(f"GPU memory cleanup failed: {e}")
        else:
            logger.info(
                f"⚠️  Skipping fully vectorized GPU processing. GPU_AVAILABLE: {GPU_AVAILABLE}, use_gpu: {self.use_gpu}"
            )

        # Fallback to batched processing
        logger.debug(
            f"Processing all {len(self.common_positions)} valid positions in batches..."
        )
        all_results = []
        normal_approx_count = 0
        lrt_count = 0
        fallback_count = 0

        # Calculate optimal batch size based on available memory for batched processing
        if self.use_gpu:
            try:
                import cupy as cp

                mempool = cp.get_default_memory_pool()
                available_memory_gb = mempool.free_bytes() / (1024**3)
                if available_memory_gb == 0:
                    # Fallback to pynvml or assume large memory
                    try:
                        import pynvml

                        pynvml.nvmlInit()
                        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                        available_memory_gb = mem_info.free / (1024**3)
                    except Exception as e:
                        logger.warning(f"Could not calculate available memory: {e}")
                        available_memory_gb = 95  # Assume 95GB for GH200

                # Use 80% of available memory for batched processing
                # Each position needs ~68 bytes, so calculate optimal batch size
                bytes_per_position = 68
                optimal_batch_size = int(
                    (available_memory_gb * 0.8 * 1024**3) / bytes_per_position
                )
                optimal_batch_size = max(
                    optimal_batch_size, 100000
                )  # Minimum 100K positions
                optimal_batch_size = min(
                    optimal_batch_size, len(self.common_positions)
                )  # Don't exceed total positions

                logger.info(
                    f"Using optimal batch size: {optimal_batch_size:,} positions (based on {available_memory_gb:.1f}GB available)"
                )
                self.batch_size = optimal_batch_size
            except Exception as e:
                logger.warning(f"Could not calculate optimal batch size: {e}")
                logger.warning("Could not calculate optimal batch size, using default")

        n_batches = (
            len(self.common_positions) + self.batch_size - 1
        ) // self.batch_size

        logger.debug(
            f"Processing {len(self.common_positions):,} positions in {n_batches} batches of {self.batch_size:,} positions each"
        )

        # Process all batches sequentially for better GPU utilization
        # Multiprocessing is not beneficial for GPU-bound operations
        total_positions = len(self.common_positions)

        # Create progress bar
        pbar = tqdm(total=total_positions, desc="Processing positions", unit="pos")

        for batch_idx in range(n_batches):
            start_idx = batch_idx * self.batch_size
            end_idx = min(start_idx + self.batch_size, len(self.common_positions))
            batch_positions = self.common_positions[start_idx:end_idx]

            # Process batch
            if self.use_gpu:
                batch_results = self._process_batch_gpu(batch_positions)
            else:
                batch_results = self._process_batch_cpu(batch_positions)

            # Update progress
            positions_processed = len([r for r in batch_results if r is not None])
            pbar.update(positions_processed)

            for result in batch_results:
                if result is not None:
                    all_results.append(result)

                    # Count method usage
                    if result.method == "NormalApprox":
                        normal_approx_count += 1
                    else:
                        lrt_count += 1
                        if result.fallback_used:
                            fallback_count += 1

        # Close progress bar
        pbar.close()
        logger.debug(f"Processed {positions_processed} positions")
        logger.debug(f"Processed {len(all_results)} results")

        # Convert to efficient data structure
        logger.debug("Converting results to efficient data structure...")
        comparison_data = self._convert_to_comparison_data(all_results)

        total_positions = comparison_data.n_comparisons
        significant_mask = comparison_data.significant_mask
        significant_count = np.sum(significant_mask)
        significant_fraction = (
            significant_count / total_positions if total_positions > 0 else 0
        )

        # Apply FDR analysis
        q_values, pi0, global_p, z_score, global_significant = (
            self._apply_fdr_analysis_vectorized(comparison_data, output_prefix)
        )

        # Update comparison data with FDR analysis
        comparison_data.q_values = q_values
        comparison_data.significant = q_values <= self.significance_level
        comparison_data.global_significant = np.full(
            total_positions, global_significant, dtype=bool
        )

        # Recalculate significant count based on q-values
        significant_count = np.sum(comparison_data.significant)
        significant_fraction = (
            significant_count / total_positions if total_positions > 0 else 0
        )

        # Group significant regions
        significant_regions = self._group_significant_regions_vectorized(
            comparison_data
        )

        statistics = {
            "total_positions": total_positions,
            "significant_positions": significant_count,
            "significant_fraction": significant_fraction,
            "normal_approximation_count": normal_approx_count,
            "lrt_count": lrt_count,
            "fallback_to_mom_count": fallback_count,
            "insufficient_sample_count": getattr(self, "insufficient_sample_count", 0),
            "min_N": self.min_N,
            "mean_p_value": float(np.mean(comparison_data.p_values)),
            "median_p_value": float(np.median(comparison_data.p_values)),
            "mean_test_statistic": float(np.mean(comparison_data.test_statistics)),
            "median_test_statistic": float(np.median(comparison_data.test_statistics)),
            "min_p_value": float(np.min(comparison_data.p_values)),
            "max_p_value": float(np.max(comparison_data.p_values)),
            "processing_time_seconds": time.time() - start_time,
            "gpu_used": self.use_gpu,
            # FDR analysis results
            "q_values_applied": self.apply_fdr_correction,
            "fdr_method": self.fdr_method,
            "pi0_estimate": pi0,
            "global_p_value": global_p,
            "global_z_score": z_score,
            "global_significant": global_significant,
            "global_significance_threshold": self.global_significance_threshold,
            "significant_regions_count": len(significant_regions),
            "significant_regions": significant_regions,
            "mean_q_value": float(np.mean(q_values)),
            "median_q_value": float(np.median(q_values)),
            "min_q_value": float(np.min(q_values)),
            "max_q_value": float(np.max(q_values)),
        }

        logger.info(
            f"Vectorized comparison completed in {statistics['processing_time_seconds']:.2f} seconds"
        )
        logger.info(
            f"Found {significant_count} significant positions out of {total_positions} ({significant_fraction:.2%})"
        )
        logger.info(
            f"Method usage: {normal_approx_count} normal approx, {lrt_count} LRT ({fallback_count} fallbacks)"
        )
        logger.info(
            f"FDR analysis completed: pi0={pi0:.3f}, global_p={global_p:.6f}, z-score={z_score:.6f}, global_significant={global_significant}"
        )
        logger.info(f"Found {len(significant_regions)} significant regions")

        print("\n=== VECTORIZED COMPARISON COMPLETED ===")
        print(f"Total positions processed: {total_positions}")
        print(f"Significant positions found: {significant_count}")
        print(f"Significant fraction: {significant_fraction:.2%}")
        print(
            f"Positions filtered (insufficient samples): {getattr(self, 'insufficient_sample_count', 0)}"
        )
        print(
            f"Normal approximation used: {normal_approx_count} ({normal_approx_count / total_positions:.1%})"
        )
        print(f"LRT used: {lrt_count} ({lrt_count / total_positions:.1%})")
        print(f"MoM fallbacks: {fallback_count}")
        print(f"Processing time: {statistics['processing_time_seconds']:.2f} seconds")
        print(f"GPU acceleration: {'Yes' if self.use_gpu else 'No'}")
        if self.apply_fdr_correction:
            print(f"FDR correction applied: pi0={pi0:.3f}")
            print(
                f"Global significance (Stouffer): p={global_p:.6f}, z-score={z_score:.6f}, significant={global_significant}"
            )
            print(f"Significant regions: {len(significant_regions)}")

        # Apply DMP filtering if requested
        biological_dmps = []
        filtering_stats = None

        if hasattr(self, "apply_dmp_filtering") and self.apply_dmp_filtering:
            logger.info("Applying DMP filtering to significant results...")
            try:
                from methyl_detector.core.dmp_filter import DMPFilter

                dmp_filter = DMPFilter(
                    min_overlap=getattr(self, "min_overlap", 0.6),
                    min_Δμ=getattr(self, "min_delta_mean", 0.1),
                    min_JD=getattr(self, "min_jeffreys_divergence", 0.3),
                    min_cohen_d=getattr(self, "min_cohen_d", 0.5),
                    min_auc=getattr(self, "min_auc", 0.6),
                    max_selected_dmps=getattr(self, "max_selected_dmps", 1000),
                    selection_method=getattr(self, "dmp_filter_method", "combined"),
                    use_gpu=False,
                )

                # Use the efficient data structure directly
                from .dmp_filter import DMPData

                # Filter to only significant positions
                significant_mask = comparison_data.significant
                filtered_dmp_data = DMPData(
                    positions=comparison_data.positions[significant_mask],
                    p_values=comparison_data.p_values[significant_mask],
                    q_values=comparison_data.q_values[significant_mask],
                    mean1=comparison_data.mean1[significant_mask],
                    mean2=comparison_data.mean2[significant_mask],
                    alpha1=comparison_data.alpha1[significant_mask],
                    beta1=comparison_data.beta1[significant_mask],
                    alpha2=comparison_data.alpha2[significant_mask],
                    beta2=comparison_data.beta2[significant_mask],
                    variance1=comparison_data.variance1[significant_mask],
                    variance2=comparison_data.variance2[significant_mask],
                )

                # Use vectorized filtering with export - pass DMPData directly
                # This will calculate metrics once and export before filtering
                biological_dmps = dmp_filter.filter_dmps_vectorized(
                    filtered_dmp_data,
                    export_prefix=output_prefix,
                    export_dir=self.output_dir
                )
                logger.info(
                    f"DMP filtering completed: {np.sum(significant_mask)} -> {len(biological_dmps)} DMPs"
                )
                
                # Apply minimum subset selection using advanced adaptive method
                if len(biological_dmps) > 0:
                    try:
                        from methyl_detector.core.advanced_selector import select_optimal_subset_adaptive
                        
                        # Get selection parameters from instance attributes
                        target_auc = self.target_auc
                        use_gpu_selection = self.use_gpu_selection
                        selection_metric = self.selection_metric
                        target_youden = self.target_youden
                        
                        selection_result = select_optimal_subset_adaptive(
                            biological_dmps,
                            target_auc=target_auc,
                            use_gpu=use_gpu_selection,
                            metric=selection_metric,
                            target_youden=target_youden,
                            algorithm=self.selection_algorithm,
                            time_budget=self.time_budget_seconds
                        )
                        
                        # Update biological_dmps to only include selected subset
                        selected_indices = selection_result["selected_local_idxs"]
                        biological_dmps = [biological_dmps[i] for i in selected_indices]
                        
                        # Mark selected DMPs
                        for i, dmp in enumerate(biological_dmps):
                            dmp.selected = True
                            dmp.selection_reason = f"Minimum subset selection (k={len(selected_indices)})"
                        
                        logger.info(
                            f"Minimum subset selection completed: {len(selected_indices)} DMPs selected "
                            f"(target {selection_metric}={target_auc if selection_metric == 'auc' else target_youden})"
                        )
                        
                        # Store selection statistics
                        filtering_stats = {
                            "filtered_dmps": len(biological_dmps),
                            "selection_result": selection_result,
                            "target_auc": target_auc,
                            "target_youden": target_youden,
                            "selection_metric": selection_metric
                        }
                        
                    except Exception as e:
                        logger.warning(f"Minimum subset selection failed: {e}")
                        # Continue with all filtered DMPs
                        filtering_stats = {"selection_error": str(e)}
                else:
                    filtering_stats = {"filtered_dmps": 0}

            except Exception as e:
                logger.error(f"DMP filtering failed: {e}")
                # Fall back to significant results
                significant_results = comparison_data.to_smart_lrt_results()
                biological_dmps = [r for r in significant_results if r.significant]
                filtering_stats = {"error": str(e)}

        result_dict = {
            "statistics": statistics,
            "comparison_data": comparison_data,
            "all_results": comparison_data.to_smart_lrt_results(),  # For backward compatibility
            "significant_results": [
                r for r in comparison_data.to_smart_lrt_results() if r.significant
            ],
            "significant_regions": significant_regions,
        }

        if biological_dmps:
            result_dict["biological_dmps"] = biological_dmps
            result_dict["filtering_stats"] = filtering_stats

        return result_dict

    def compare_centroids(
        self, output_prefix: str = "smart_centroid_comparison"
    ) -> Dict[str, any]:
        """
        Compare all positions between the two centroids using smart methods.
        Uses vectorized implementation for better performance.

        Args:
            output_prefix: Prefix for output files

        Returns:
            Dictionary containing comparison results and statistics
        """
        # Use vectorized implementation for better performance
        return self.compare_centroids_vectorized(output_prefix)

    def _compare_centroids_fully_vectorized_gpu(
        self, output_prefix: str, start_time: float
    ) -> Dict[str, any]:
        """
        Fully vectorized GPU processing for centroid comparison.
        Processes all positions simultaneously on GPU.
        """
        import cupy as cp

        # Get all position indices
        all_positions = self.common_positions
        n_positions = len(all_positions)

        # Estimate GPU memory requirements
        logger.debug(
            f"Estimating GPU memory requirements for {n_positions:,} positions..."
        )

        # Estimate memory per position (more accurate calculation)
        # Each position needs: positions, p_values, q_values, means, vars, alphas, betas, etc.
        # More detailed calculation:
        # - Input data: N, Sx, Sx2, log_x_sum, log_1_minus_x_sum (5 arrays per group * 2 groups = 10 arrays)
        # - Computed data: means, vars, alphas, betas, test_stats, p_values, methods (7 arrays)
        # - Total: ~17 float32 arrays per position = 68 bytes per position
        bytes_per_position = 17 * 4  # 17 float32 values * 4 bytes each
        estimated_memory_gb = (n_positions * bytes_per_position) / (1024**3)

        # Get available GPU memory - prioritize pynvml over CuPy memory pool
        available_memory_gb = None
        try:
            # Try pynvml first (more reliable than CuPy memory pool)
            import pynvml

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            available_memory_gb = mem_info.free / (1024**3)
            total_memory_gb = mem_info.total / (1024**3)
            logger.debug(
                f"GPU memory (via pynvml): {available_memory_gb:.1f}GB available / {total_memory_gb:.1f}GB total"
            )
        except Exception as e:
            logger.warning(f"Could not get GPU memory via pynvml: {e}")
            # Fallback to CuPy memory pool
            try:
                mempool = cp.get_default_memory_pool()
                available_memory_gb = mempool.free_bytes() / (1024**3)
                total_memory_gb = mempool.total_bytes() / (1024**3)
                logger.info(
                    f"GPU memory (via CuPy): {available_memory_gb:.1f}GB available / {total_memory_gb:.1f}GB total"
                )

                # If memory pool shows 0, assume we have enough memory
                if available_memory_gb == 0:
                    logger.warning(
                        "CuPy memory pool shows 0GB, assuming 90GB available for GH200"
                    )
                    available_memory_gb = 90
            except Exception as e2:
                logger.warning(f"Could not estimate GPU memory via CuPy: {e2}")
                # Final fallback: assume we have enough memory for GH200
                available_memory_gb = 90
                logger.info(
                    f"Assuming {available_memory_gb:.1f}GB available for memory estimation"
                )

        logger.debug(f"Estimated memory needed: {estimated_memory_gb:.1f}GB")

        # Check if we have enough memory (aggressive utilization for dedicated tasks)
        # Use 95% of available memory since each task can use all GPU resources
        if available_memory_gb and estimated_memory_gb > available_memory_gb * 0.95:
            logger.warning(
                f"Insufficient GPU memory for full vectorization. Estimated: {estimated_memory_gb:.1f}GB, Available: {available_memory_gb:.1f}GB (95% threshold)"
            )
            raise MemoryError("Insufficient GPU memory for full vectorization")
        else:
            logger.debug(
                f"✅ Sufficient GPU memory for full vectorization. Estimated: {estimated_memory_gb:.1f}GB, Available: {available_memory_gb:.1f}GB (using 95% threshold)"
            )

        logger.debug("Loading all data to GPU for vectorized processing...")

        # Get indices for all positions
        logger.debug("Creating position index arrays...")
        batch_indices1 = np.array([self.pos1_to_idx[pos] for pos in all_positions])
        batch_indices2 = np.array([self.pos2_to_idx[pos] for pos in all_positions])
        logger.debug(f"Created index arrays: {len(batch_indices1)} positions")

        # Load all data to GPU at once with memory optimization
        def load_to_gpu(key, indices, data, dtype=cp.float32):
            """Load data to GPU with optimized memory usage."""
            return cp.array(data[key][indices], dtype=dtype)

        # Move all data to GPU with optimized memory usage
        # Use float32 instead of float64 to save memory
        logger.debug("Loading data arrays to GPU...")
        n1_gpu = load_to_gpu("N", batch_indices1, self.centroid1_data, cp.float32)
        logger.debug("Loaded n1_gpu")
        n2_gpu = load_to_gpu("N", batch_indices2, self.centroid2_data, cp.float32)
        logger.debug("Loaded n2_gpu")
        Sx1_gpu = load_to_gpu("Sx", batch_indices1, self.centroid1_data, cp.float32)
        logger.debug("Loaded Sx1_gpu")
        Sx2_gpu = load_to_gpu("Sx", batch_indices2, self.centroid2_data, cp.float32)
        logger.debug("Loaded Sx2_gpu")
        Sx21_gpu = load_to_gpu("Sx2", batch_indices1, self.centroid1_data, cp.float32)
        logger.debug("Loaded Sx21_gpu")
        Sx22_gpu = load_to_gpu("Sx2", batch_indices2, self.centroid2_data, cp.float32)
        logger.debug("Loaded Sx22_gpu")
        log_x_sum1_gpu = load_to_gpu(
            "log_x_sum", batch_indices1, self.centroid1_data, cp.float32
        )
        logger.debug("Loaded log_x_sum1_gpu")
        log_x_sum2_gpu = load_to_gpu(
            "log_x_sum", batch_indices2, self.centroid2_data, cp.float32
        )
        logger.debug("Loaded log_x_sum2_gpu")
        log_1mx_sum1_gpu = load_to_gpu(
            "log_1_minus_x_sum", batch_indices1, self.centroid1_data, cp.float32
        )
        logger.debug("Loaded log_1mx_sum1_gpu")
        log_1mx_sum2_gpu = load_to_gpu(
            "log_1_minus_x_sum", batch_indices2, self.centroid2_data, cp.float32
        )
        logger.debug("Loaded log_1mx_sum2_gpu")

        logger.debug("Computing means and variances...")

        # Compute means and variances
        mean1_gpu = Sx1_gpu / n1_gpu
        mean2_gpu = Sx2_gpu / n2_gpu
        var1_gpu = (Sx21_gpu - (Sx1_gpu**2) / n1_gpu) / cp.maximum(n1_gpu - 1, 1)
        var2_gpu = (Sx22_gpu - (Sx2_gpu**2) / n2_gpu) / cp.maximum(n2_gpu - 1, 1)

        # MoM estimates
        alpha1_mom_gpu, beta1_mom_gpu = self._beta_mom_vectorized_gpu(
            n1_gpu, Sx1_gpu, Sx21_gpu
        )
        alpha2_mom_gpu, beta2_mom_gpu = self._beta_mom_vectorized_gpu(
            n2_gpu, Sx2_gpu, Sx22_gpu
        )

        logger.debug("Determining which positions use normal approximation...")

        # Decide which positions use normal approximation
        use_normal_gpu = (
            (n1_gpu >= self.normal_approx_threshold)
            & (n2_gpu >= self.normal_approx_threshold)
            & (alpha1_mom_gpu >= self.min_beta_params)
            & (beta1_mom_gpu >= self.min_beta_params)
            & (alpha2_mom_gpu >= self.min_beta_params)
            & (beta2_mom_gpu >= self.min_beta_params)
            & (mean1_gpu > 0.1)
            & (mean1_gpu < 0.9)
            & (mean2_gpu > 0.1)
            & (mean2_gpu < 0.9)
        )

        # Initialize result arrays
        test_statistics_gpu = cp.zeros(n_positions, dtype=cp.float32)
        p_values_gpu = cp.zeros(n_positions, dtype=cp.float32)
        # Use integer encoding for methods instead of strings (0=LRT, 1=NormalApprox)
        methods_gpu = cp.zeros(n_positions, dtype=cp.int32)
        alpha1_gpu = cp.zeros(n_positions, dtype=cp.float32)
        beta1_gpu = cp.zeros(n_positions, dtype=cp.float32)
        alpha2_gpu = cp.zeros(n_positions, dtype=cp.float32)
        beta2_gpu = cp.zeros(n_positions, dtype=cp.float32)
        alpha_combined_gpu = cp.zeros(n_positions, dtype=cp.float32)
        beta_combined_gpu = cp.zeros(n_positions, dtype=cp.float32)
        fallback_used_gpu = cp.zeros(n_positions, dtype=bool)

        # Process normal approximation cases
        normal_mask = use_normal_gpu
        if cp.any(normal_mask):
            logger.debug(
                f"Processing {cp.sum(normal_mask)} positions with normal approximation..."
            )

            # Vectorized z-test computation
            se_gpu = cp.sqrt(
                var1_gpu[normal_mask] / n1_gpu[normal_mask]
                + var2_gpu[normal_mask] / n2_gpu[normal_mask]
                + 1e-12
            )
            z_stat_gpu = (mean1_gpu[normal_mask] - mean2_gpu[normal_mask]) / se_gpu
            p_val_gpu = 2 * (1 - gpu_norm_cdf(cp.abs(z_stat_gpu)))

            # Store results
            test_statistics_gpu[normal_mask] = z_stat_gpu
            p_values_gpu[normal_mask] = p_val_gpu
            methods_gpu[normal_mask] = 1  # 1 = NormalApprox

        # Process LRT cases
        lrt_mask = ~use_normal_gpu
        if cp.any(lrt_mask):
            logger.debug(f"Processing {cp.sum(lrt_mask)} positions with LRT...")

            # Subset data for LRT
            n1_lrt_gpu = n1_gpu[lrt_mask]
            n2_lrt_gpu = n2_gpu[lrt_mask]
            log_x_sum1_lrt_gpu = log_x_sum1_gpu[lrt_mask]
            log_x_sum2_lrt_gpu = log_x_sum2_gpu[lrt_mask]
            log_1mx_sum1_lrt_gpu = log_1mx_sum1_gpu[lrt_mask]
            log_1mx_sum2_lrt_gpu = log_1mx_sum2_gpu[lrt_mask]

            # MLE for both groups
            alpha1_mle_gpu, beta1_mle_gpu = self._beta_mle_vectorized_gpu(
                n1_lrt_gpu, log_x_sum1_lrt_gpu, log_1mx_sum1_lrt_gpu
            )
            alpha2_mle_gpu, beta2_mle_gpu = self._beta_mle_vectorized_gpu(
                n2_lrt_gpu, log_x_sum2_lrt_gpu, log_1mx_sum2_lrt_gpu
            )

            # Combined data
            n_comb_gpu = n1_lrt_gpu + n2_lrt_gpu
            log_x_sum_comb_gpu = log_x_sum1_lrt_gpu + log_x_sum2_lrt_gpu
            log_1mx_sum_comb_gpu = log_1mx_sum1_lrt_gpu + log_1mx_sum2_lrt_gpu
            alpha_comb_gpu, beta_comb_gpu = self._beta_mle_vectorized_gpu(
                n_comb_gpu, log_x_sum_comb_gpu, log_1mx_sum_comb_gpu
            )

            # Compute log-likelihoods
            ll1_gpu = self._beta_loglik_vectorized_gpu(
                alpha1_mle_gpu,
                beta1_mle_gpu,
                n1_lrt_gpu,
                log_x_sum1_lrt_gpu,
                log_1mx_sum1_lrt_gpu,
            )
            ll2_gpu = self._beta_loglik_vectorized_gpu(
                alpha2_mle_gpu,
                beta2_mle_gpu,
                n2_lrt_gpu,
                log_x_sum2_lrt_gpu,
                log_1mx_sum2_lrt_gpu,
            )
            ll0_gpu = self._beta_loglik_vectorized_gpu(
                alpha_comb_gpu,
                beta_comb_gpu,
                n_comb_gpu,
                log_x_sum_comb_gpu,
                log_1mx_sum_comb_gpu,
            )

            # Check for invalid likelihoods and fallback to MoM
            invalid_ll = ~cp.isfinite(ll1_gpu + ll2_gpu + ll0_gpu)
            if cp.any(invalid_ll):
                logger.info(
                    f"Falling back to MoM for {cp.sum(invalid_ll)} positions with invalid likelihoods..."
                )

                # Fallback to MoM for invalid cases
                alpha1_mle_gpu[invalid_ll] = alpha1_mom_gpu[lrt_mask][invalid_ll]
                beta1_mle_gpu[invalid_ll] = beta1_mom_gpu[lrt_mask][invalid_ll]
                alpha2_mle_gpu[invalid_ll] = alpha2_mom_gpu[lrt_mask][invalid_ll]
                beta2_mle_gpu[invalid_ll] = beta2_mom_gpu[lrt_mask][invalid_ll]

                # Combined MoM
                Sx_comb_gpu = (
                    Sx1_gpu[lrt_mask][invalid_ll] + Sx2_gpu[lrt_mask][invalid_ll]
                )
                Sx2_comb_gpu = (
                    Sx21_gpu[lrt_mask][invalid_ll] + Sx22_gpu[lrt_mask][invalid_ll]
                )
                alpha_comb_mom_gpu, beta_comb_mom_gpu = self._beta_mom_vectorized_gpu(
                    n_comb_gpu[invalid_ll], Sx_comb_gpu, Sx2_comb_gpu
                )
                alpha_comb_gpu[invalid_ll] = alpha_comb_mom_gpu
                beta_comb_gpu[invalid_ll] = beta_comb_mom_gpu

                # Recompute likelihoods
                ll1_gpu[invalid_ll] = self._beta_loglik_vectorized_gpu(
                    alpha1_mle_gpu[invalid_ll],
                    beta1_mle_gpu[invalid_ll],
                    n1_lrt_gpu[invalid_ll],
                    log_x_sum1_lrt_gpu[invalid_ll],
                    log_1mx_sum1_lrt_gpu[invalid_ll],
                )
                ll2_gpu[invalid_ll] = self._beta_loglik_vectorized_gpu(
                    alpha2_mle_gpu[invalid_ll],
                    beta2_mle_gpu[invalid_ll],
                    n2_lrt_gpu[invalid_ll],
                    log_x_sum2_lrt_gpu[invalid_ll],
                    log_1mx_sum2_lrt_gpu[invalid_ll],
                )
                ll0_gpu[invalid_ll] = self._beta_loglik_vectorized_gpu(
                    alpha_comb_gpu[invalid_ll],
                    beta_comb_gpu[invalid_ll],
                    n_comb_gpu[invalid_ll],
                    log_x_sum_comb_gpu[invalid_ll],
                    log_1mx_sum_comb_gpu[invalid_ll],
                )

                # Mark fallback used
                fallback_used_gpu[lrt_mask] = invalid_ll

            # LRT statistic and p-value
            lrt_stat_gpu, p_val_gpu = self._compute_lrt_statistic(ll1_gpu, ll2_gpu, ll0_gpu, use_gpu=True)

            # Store results
            test_statistics_gpu[lrt_mask] = lrt_stat_gpu
            p_values_gpu[lrt_mask] = p_val_gpu
            alpha1_gpu[lrt_mask] = alpha1_mle_gpu
            beta1_gpu[lrt_mask] = beta1_mle_gpu
            alpha2_gpu[lrt_mask] = alpha2_mle_gpu
            beta2_gpu[lrt_mask] = beta2_mle_gpu
            alpha_combined_gpu[lrt_mask] = alpha_comb_gpu
            beta_combined_gpu[lrt_mask] = beta_comb_gpu

        logger.info("Converting results back to CPU...")

        # Convert all results back to CPU
        all_results = []
        for i in range(n_positions):
            # Convert method integer back to string
            method_int = int(cp.asnumpy(methods_gpu[i]))
            method_str = "NormalApprox" if method_int == 1 else "LRT"

            result = SmartLRTResult(
                position=int(all_positions[i]),
                test_statistic=float(cp.asnumpy(test_statistics_gpu[i])),
                p_value=float(cp.asnumpy(p_values_gpu[i])),
                method=method_str,
                mean1=float(cp.asnumpy(mean1_gpu[i])),
                mean2=float(cp.asnumpy(mean2_gpu[i])),
                variance1=float(cp.asnumpy(var1_gpu[i])),
                variance2=float(cp.asnumpy(var2_gpu[i])),
                alpha1=float(cp.asnumpy(alpha1_gpu[i])),
                beta1=float(cp.asnumpy(beta1_gpu[i])),
                alpha2=float(cp.asnumpy(alpha2_gpu[i])),
                beta2=float(cp.asnumpy(beta2_gpu[i])),
                alpha_combined=float(cp.asnumpy(alpha_combined_gpu[i])),
                beta_combined=float(cp.asnumpy(beta_combined_gpu[i])),
                n1=int(cp.asnumpy(n1_gpu[i])),
                n2=int(cp.asnumpy(n2_gpu[i])),
                significant=float(cp.asnumpy(p_values_gpu[i]))
                < self.significance_level,
                significance_level=self.significance_level,
                fallback_used=bool(cp.asnumpy(fallback_used_gpu[i])),
            )
            all_results.append(result)

        # Count method usage
        normal_approx_count = int(cp.sum(use_normal_gpu))
        lrt_count = int(cp.sum(~use_normal_gpu))
        fallback_count = int(cp.sum(fallback_used_gpu))

        # Clear GPU memory
        try:
            cp.get_default_memory_pool().free_all_blocks()
            logger.info("GPU memory cleared after processing")
        except Exception as e:
            logger.warning(f"GPU memory cleanup failed: {e}")
            
        # Continue with the rest of the processing
        return self._finish_comparison_processing(
            all_results,
            normal_approx_count,
            lrt_count,
            fallback_count,
            output_prefix,
            start_time,
        )

    def _finish_comparison_processing(
        self,
        all_results,
        normal_approx_count,
        lrt_count,
        fallback_count,
        output_prefix,
        start_time,
    ):
        """Finish the comparison processing with FDR analysis and result formatting."""
        # Convert to efficient data structure
        logger.info("Converting results to efficient data structure...")
        comparison_data = self._convert_to_comparison_data(all_results)

        total_positions = comparison_data.n_comparisons
        significant_mask = comparison_data.significant_mask
        significant_count = np.sum(significant_mask)
        significant_fraction = (
            significant_count / total_positions if total_positions > 0 else 0
        )

        # Apply FDR analysis
        q_values, pi0, global_p, z_score, global_significant = (
            self._apply_fdr_analysis_vectorized(comparison_data, output_prefix)
        )

        # Update comparison data with FDR analysis
        comparison_data.q_values = q_values
        comparison_data.significant = q_values <= self.significance_level
        comparison_data.global_significant = np.full(
            total_positions, global_significant, dtype=bool
        )

        # Recalculate significant count based on q-values
        significant_count = np.sum(comparison_data.significant)
        significant_fraction = (
            significant_count / total_positions if total_positions > 0 else 0
        )

        # Group significant regions
        significant_regions = self._group_significant_regions_vectorized(
            comparison_data
        )

        statistics = {
            "total_positions": total_positions,
            "significant_positions": significant_count,
            "significant_fraction": significant_fraction,
            "normal_approximation_count": normal_approx_count,
            "lrt_count": lrt_count,
            "fallback_to_mom_count": fallback_count,
            "insufficient_sample_count": getattr(self, "insufficient_sample_count", 0),
            "min_N": self.min_N,
            "mean_p_value": float(np.mean(comparison_data.p_values)),
            "median_p_value": float(np.median(comparison_data.p_values)),
            "mean_test_statistic": float(np.mean(comparison_data.test_statistics)),
            "median_test_statistic": float(np.median(comparison_data.test_statistics)),
            "min_p_value": float(np.min(comparison_data.p_values)),
            "max_p_value": float(np.max(comparison_data.p_values)),
            "processing_time_seconds": time.time() - start_time,
            "gpu_used": self.use_gpu,
            # FDR analysis results
            "q_values_applied": self.apply_fdr_correction,
            "fdr_method": self.fdr_method,
            "pi0_estimate": pi0,
            "global_p_value": global_p,
            "global_z_score": z_score,
            "global_significant": global_significant,
            "global_significance_threshold": self.global_significance_threshold,
            "significant_regions_count": len(significant_regions),
            "significant_regions": significant_regions,
            "mean_q_value": float(np.mean(q_values)),
            "median_q_value": float(np.median(q_values)),
            "min_q_value": float(np.min(q_values)),
            "max_q_value": float(np.max(q_values)),
        }

        logger.info(
            f"Vectorized comparison completed in {statistics['processing_time_seconds']:.2f} seconds"
        )
        logger.info(
            f"Found {significant_count} significant positions out of {total_positions} ({significant_fraction:.2%})"
        )
        logger.info(
            f"Method usage: {normal_approx_count} normal approx, {lrt_count} LRT ({fallback_count} fallbacks)"
        )
        logger.info(
            f"FDR analysis completed: pi0={pi0:.3f}, global_p={global_p:.6f}, z-score={z_score:.6f}, global_significant={global_significant}"
        )
        logger.info(f"Found {len(significant_regions)} significant regions")

        print("\n=== VECTORIZED COMPARISON COMPLETED ===")
        print(f"Total positions processed: {total_positions}")
        print(f"Significant positions found: {significant_count}")
        print(f"Significant fraction: {significant_fraction:.2%}")
        print(
            f"Positions filtered (insufficient samples): {getattr(self, 'insufficient_sample_count', 0)}"
        )
        print(
            f"Normal approximation used: {normal_approx_count} ({normal_approx_count / total_positions:.1%})"
        )
        print(f"LRT used: {lrt_count} ({lrt_count / total_positions:.1%})")
        print(f"MoM fallbacks: {fallback_count}")
        print(f"Processing time: {statistics['processing_time_seconds']:.2f} seconds")
        print(f"GPU acceleration: {'Yes' if self.use_gpu else 'No'}")
        if self.apply_fdr_correction:
            print(f"FDR correction applied: pi0={pi0:.3f}")
            print(
                f"Global significance (Stouffer): p={global_p:.6f}, z-score={z_score:.6f}, significant={global_significant}"
            )
            print(f"Significant regions: {len(significant_regions)}")

        # Apply DMP filtering if requested
        biological_dmps = []
        filtering_stats = None

        if hasattr(self, "apply_dmp_filtering") and self.apply_dmp_filtering:
            logger.info("Applying DMP filtering to significant results...")
            try:
                from methyl_detector.core.dmp_filter import DMPFilter

                dmp_filter = DMPFilter(
                    min_overlap=getattr(self, "min_overlap", 0.6),
                    min_Δμ=getattr(self, "min_delta_mean", 0.1),
                    min_JD=getattr(self, "min_jeffreys_divergence", 0.3),
                    min_cohen_d=getattr(self, "min_cohen_d", 0.5),
                    min_auc=getattr(self, "min_auc", 0.6),
                    max_selected_dmps=getattr(self, "max_selected_dmps", 1000),
                    selection_method=getattr(self, "dmp_filter_method", "combined"),
                    use_gpu=False,
                )

                # Use the efficient data structure directly
                from .dmp_filter import DMPData

                # Filter to only significant positions
                significant_mask = comparison_data.significant
                filtered_dmp_data = DMPData(
                    positions=comparison_data.positions[significant_mask],
                    p_values=comparison_data.p_values[significant_mask],
                    q_values=comparison_data.q_values[significant_mask],
                    mean1=comparison_data.mean1[significant_mask],
                    mean2=comparison_data.mean2[significant_mask],
                    alpha1=comparison_data.alpha1[significant_mask],
                    beta1=comparison_data.beta1[significant_mask],
                    alpha2=comparison_data.alpha2[significant_mask],
                    beta2=comparison_data.beta2[significant_mask],
                    variance1=comparison_data.variance1[significant_mask],
                    variance2=comparison_data.variance2[significant_mask],
                )

                # Use vectorized filtering with export - pass DMPData directly
                # This will calculate metrics once and export before filtering
                biological_dmps = dmp_filter.filter_dmps_vectorized(
                    filtered_dmp_data,
                    export_prefix=output_prefix,
                    export_dir=self.output_dir
                )
                logger.info(
                    f"DMP filtering completed: {np.sum(significant_mask)} -> {len(biological_dmps)} DMPs"
                )
                
                # Apply minimum subset selection using advanced adaptive method
                if len(biological_dmps) > 0:
                    try:
                        from methyl_detector.core.advanced_selector import select_optimal_subset_adaptive
                        
                        # Get selection parameters from instance attributes
                        target_auc = self.target_auc
                        use_gpu_selection = self.use_gpu_selection
                        selection_metric = self.selection_metric
                        target_youden = self.target_youden
                        
                        selection_result = select_optimal_subset_adaptive(
                            biological_dmps,
                            target_auc=target_auc,
                            use_gpu=use_gpu_selection,
                            metric=selection_metric,
                            target_youden=target_youden,
                            algorithm=self.selection_algorithm,
                            time_budget=self.time_budget_seconds
                        )
                        
                        # Update biological_dmps to only include selected subset
                        selected_indices = selection_result["selected_local_idxs"]
                        biological_dmps = [biological_dmps[i] for i in selected_indices]
                        
                        # Mark selected DMPs
                        for i, dmp in enumerate(biological_dmps):
                            dmp.selected = True
                            dmp.selection_reason = f"Minimum subset selection (k={len(selected_indices)})"
                        
                        logger.info(
                            f"Minimum subset selection completed: {len(selected_indices)} DMPs selected "
                            f"(target {selection_metric}={target_auc if selection_metric == 'auc' else target_youden})"
                        )
                        
                        # Store selection statistics
                        filtering_stats = {
                            "filtered_dmps": len(biological_dmps),
                            "selection_result": selection_result,
                            "target_auc": target_auc,
                            "target_youden": target_youden,
                            "selection_metric": selection_metric
                        }
                        
                    except Exception as e:
                        logger.warning(f"Minimum subset selection failed: {e}")
                        # Continue with all filtered DMPs
                        filtering_stats = {"selection_error": str(e)}
                else:
                    filtering_stats = {"filtered_dmps": 0}

            except Exception as e:
                logger.error(f"DMP filtering failed: {e}")
                # Fall back to significant results
                significant_results = comparison_data.to_smart_lrt_results()
                biological_dmps = [r for r in significant_results if r.significant]
                filtering_stats = {"error": str(e)}

        result_dict = {
            "statistics": statistics,
            "comparison_data": comparison_data,
            "all_results": comparison_data.to_smart_lrt_results(),  # For backward compatibility
            "significant_results": [
                r for r in comparison_data.to_smart_lrt_results() if r.significant
            ],
            "significant_regions": significant_regions,
        }

        if biological_dmps:
            result_dict["biological_dmps"] = biological_dmps
            result_dict["filtering_stats"] = filtering_stats

        return result_dict

    def _export_dmp_data_binary(
        self, results: Dict[str, any], output_prefix: str
    ) -> None:
        """
        Export DMP (Differentially Methylated Positions) data in binary formats.

        Args:
            results: Comparison results dictionary
            output_prefix: Output file prefix
        """
        if not results.get("significant_results"):
            logger.info("No significant results to export in binary format")
            return

        # Extract chromosome and context from centroid filename
        chrom_info = get_chromosome_context_from_filename(self.centroid1_path)
        chromosome = chrom_info["chromosome"]
        context = chrom_info["context"]

        # Create base filename for DMP data
        dmp_base = f"{chromosome}-{context}-dmp"

        # Convert results to pandas DataFrame for easier export
        try:
            import pandas as pd

            # Prepare data for export
            dmp_data = []
            for result in results["significant_results"]:
                dmp_data.append(
                    {
                        "position": result.position,
                        "test_statistic": result.test_statistic,
                        "p_value": result.p_value,
                        "q_value": result.q_value or 1.0,
                        "method": result.method,
                        "mean1": result.mean1,
                        "mean2": result.mean2,
                        "variance1": result.variance1,
                        "variance2": result.variance2,
                        "alpha1": result.alpha1 or 0.0,
                        "beta1": result.beta1 or 0.0,
                        "alpha2": result.alpha2 or 0.0,
                        "beta2": result.beta2 or 0.0,
                        "alpha_combined": result.alpha_combined or 0.0,
                        "beta_combined": result.beta_combined or 0.0,
                        "n1": result.n1,
                        "n2": result.n2,
                        "significant": result.significant,
                        "fallback_used": result.fallback_used,
                        "global_significant": result.global_significant,
                    }
                )

            df = pd.DataFrame(dmp_data)

            # Export to Parquet
            try:
                parquet_file = self.output_dir / f"{dmp_base}.parquet"
                df.to_parquet(parquet_file, index=False, compression="snappy")
                logger.info(f"DMP data exported to Parquet: {parquet_file}")
            except Exception as e:
                logger.warning(f"Failed to export DMP data to Parquet: {e}")

            # Export to HDF5 using methyl_utils abstraction
            try:
                from methyl_utils import DMPExporter
                
                h5_file = self.output_dir / f"{dmp_base}.h5"
                metadata = {
                    "chromosome": chromosome,
                    "context": context,
                    "total_positions": len(df),
                    "export_timestamp": time.time(),
                    "export_format": "hdf5_with_zstandard"
                }
                
                exporter = DMPExporter()
                exporter.export_to_h5(df, h5_file, metadata)
                
                logger.info(
                    f"DMP data exported to HDF5 with Z-standard compression: {h5_file}"
                )
            except ImportError:
                logger.warning(
                    "DMPExporter not found in methyl_utils. "
                    "Please implement DMPExporter class in methyl_utils for HDF5 export functionality."
                )
            except Exception as e:
                logger.warning(f"Failed to export DMP data to HDF5: {e}")

        except ImportError:
            logger.warning("pandas not available, skipping binary export")
        except Exception as e:
            logger.error(f"Error during DMP binary export: {e}")

    def _export_dmr_data_binary(
        self, results: Dict[str, any], output_prefix: str
    ) -> None:
        """
        Export DMR (Differentially Methylated Regions) data in binary formats.

        Args:
            results: Comparison results dictionary
            output_prefix: Output file prefix
        """
        if not results.get("significant_regions"):
            logger.info("No significant regions to export in binary format")
            return

        # Extract chromosome and context from centroid filename
        chrom_info = get_chromosome_context_from_filename(self.centroid1_path)
        chromosome = chrom_info["chromosome"]
        context = chrom_info["context"]

        # Create base filename for DMR data
        dmr_base = f"{chromosome}-{context}-dmr"

        try:
            import pandas as pd

            # Prepare DMR data
            dmr_data = []
            for start, end in results["significant_regions"]:
                region_size = end - start + 1
                dmr_data.append(
                    {
                        "start_position": start,
                        "end_position": end,
                        "region_size": region_size,
                        "chromosome": chromosome,
                        "context": context,
                    }
                )

            df = pd.DataFrame(dmr_data)

            # Export to Parquet
            try:
                parquet_file = self.output_dir / f"{dmr_base}.parquet"
                df.to_parquet(parquet_file, index=False, compression="snappy")
                logger.info(f"DMR data exported to Parquet: {parquet_file}")
            except Exception as e:
                logger.warning(f"Failed to export DMR data to Parquet: {e}")

            # Export to HDF5 using methyl_utils abstraction
            try:
                from methyl_utils import DMRExporter
                
                h5_file = self.output_dir / f"{dmr_base}.h5"
                metadata = {
                    "chromosome": chromosome,
                    "context": context,
                    "total_regions": len(df),
                    "export_timestamp": time.time(),
                    "export_format": "hdf5_with_zstandard"
                }
                
                exporter = DMRExporter()
                exporter.export_to_h5(df, h5_file, metadata)
                
                logger.info(
                    f"DMR data exported to HDF5 with Z-standard compression: {h5_file}"
                )
            except ImportError:
                logger.warning(
                    "DMRExporter not found in methyl_utils. "
                    "Please implement DMRExporter class in methyl_utils for HDF5 export functionality."
                )
            except Exception as e:
                logger.warning(f"Failed to export DMR data to HDF5: {e}")

        except ImportError:
            logger.warning("pandas not available, skipping binary export")
        except Exception as e:
            logger.error(f"Error during DMR binary export: {e}")

    def save_results(
        self, results: Dict[str, any], output_prefix: str = "smart_centroid_comparison"
    ):
        """Save comparison results to files."""
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        stats_file = self.output_dir / f"{output_prefix}_statistics.json"
        try:
            # Convert statistics to JSON-serializable format
            serializable_stats = {}
            for key, value in results["statistics"].items():
                try:
                    if hasattr(value, "item"):  # numpy scalars
                        serializable_stats[key] = value.item()
                    elif isinstance(value, np.ndarray):
                        serializable_stats[key] = value.tolist()
                    elif (
                        isinstance(value, list)
                        and len(value) > 0
                        and isinstance(value[0], tuple)
                    ):
                        # Convert tuples to lists for JSON serialization
                        serializable_stats[key] = [list(item) for item in value]
                    elif isinstance(value, bool):
                        # Ensure boolean values are properly serialized
                        serializable_stats[key] = value
                    elif isinstance(value, (int, float, str)):
                        serializable_stats[key] = value
                    else:
                        # Convert any other types to string
                        serializable_stats[key] = str(value)
                except Exception as e:
                    logger.warning(
                        f"Failed to serialize {key}: {type(value)} = {value}, error: {e}"
                    )
                    serializable_stats[key] = str(value)

            # Custom JSON encoder to handle numpy types
            class NumpyEncoder(json.JSONEncoder):
                def default(self, obj):
                    if hasattr(obj, "item"):
                        return obj.item()
                    elif isinstance(obj, np.ndarray):
                        return obj.tolist()
                    elif isinstance(obj, (np.integer, np.floating)):
                        return obj.item()
                    return super().default(obj)

            with open(stats_file, "w") as f:
                json.dump(serializable_stats, f, indent=2, cls=NumpyEncoder)
        except PermissionError:
            # Fallback to current directory if permission denied
            fallback_dir = Path.cwd() / "smart_comparison_results"
            fallback_dir.mkdir(exist_ok=True)
            stats_file = fallback_dir / f"{output_prefix}_statistics.json"
            with open(stats_file, "w") as f:
                json.dump(serializable_stats, f, indent=2, cls=NumpyEncoder)
            print(
                f"Permission denied for {self.output_dir}, saved to {fallback_dir} instead"
            )

        if results["significant_results"]:
            significant_file = (
                self.output_dir / f"{output_prefix}_significant_positions.csv"
            )
            try:
                with open(significant_file, "w") as f:
                    f.write(
                        "position,test_statistic,p_value,q_value,method,mean1,mean2,variance1,variance2,"
                        "alpha1,beta1,alpha2,beta2,alpha_combined,beta_combined,n1,n2,significant,fallback_used\n"
                    )
                    for result in results["significant_results"]:
                        f.write(
                            f"{result.position},{result.test_statistic:.6f},{result.p_value:.6f},"
                            f"{result.q_value or 1.0:.6f},{result.method},{result.mean1:.6f},{result.mean2:.6f},"
                            f"{result.variance1:.6f},{result.variance2:.6f},"
                            f"{result.alpha1 or 0:.6f},{result.beta1 or 0:.6f},"
                            f"{result.alpha2 or 0:.6f},{result.beta2 or 0:.6f},"
                            f"{result.alpha_combined or 0:.6f},{result.beta_combined or 0:.6f},"
                            f"{result.n1},{result.n2},{result.significant},{result.fallback_used}\n"
                        )
            except PermissionError:
                # Fallback to current directory if permission denied
                fallback_dir = Path.cwd() / "smart_comparison_results"
                fallback_dir.mkdir(exist_ok=True)
                significant_file = (
                    fallback_dir / f"{output_prefix}_significant_positions.csv"
                )
                with open(significant_file, "w") as f:
                    f.write(
                        "position,test_statistic,p_value,q_value,method,mean1,mean2,variance1,variance2,"
                        "alpha1,beta1,alpha2,beta2,alpha_combined,beta_combined,n1,n2,significant,fallback_used\n"
                    )
                    for result in results["significant_results"]:
                        f.write(
                            f"{result.position},{result.test_statistic:.6f},{result.p_value:.6f},"
                            f"{result.q_value or 1.0:.6f},{result.method},{result.mean1:.6f},{result.mean2:.6f},"
                            f"{result.variance1:.6f},{result.variance2:.6f},"
                            f"{result.alpha1 or 0:.6f},{result.beta1 or 0:.6f},"
                            f"{result.alpha2 or 0:.6f},{result.beta2 or 0:.6f},"
                            f"{result.alpha_combined or 0:.6f},{result.beta_combined or 0:.6f},"
                            f"{result.n1},{result.n2},{result.significant},{result.fallback_used}\n"
                        )
                print(
                    f"Permission denied for {self.output_dir}, saved to {fallback_dir} instead"
                )

        # Add significant regions file
        if results.get("significant_regions"):
            regions_file = self.output_dir / f"{output_prefix}_significant_regions.csv"
            try:
                with open(regions_file, "w") as f:
                    f.write("start_position,end_position,region_size\n")
                    for start, end in results["significant_regions"]:
                        f.write(f"{start},{end},{end - start + 1}\n")
            except PermissionError:
                # Fallback to current directory if permission denied
                fallback_dir = Path.cwd() / "smart_comparison_results"
                fallback_dir.mkdir(exist_ok=True)
                regions_file = fallback_dir / f"{output_prefix}_significant_regions.csv"
                with open(regions_file, "w") as f:
                    f.write("start_position,end_position,region_size\n")
                    for start, end in results["significant_regions"]:
                        f.write(f"{start},{end},{end - start + 1}\n")
                print(
                    f"Permission denied for {self.output_dir}, saved to {fallback_dir} instead"
                )

        summary_file = self.output_dir / f"{output_prefix}_summary.txt"
        try:
            with open(summary_file, "w") as f:
                f.write("Smart Centroid Comparison Summary\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Centroid 1: {self.centroid1_path}\n")
                f.write(f"Centroid 2: {self.centroid2_path}\n")
                f.write(
                    f"Total positions compared: {results['statistics']['total_positions']}\n"
                )
                f.write(
                    f"Significant positions: {results['statistics']['significant_positions']}\n"
                )
                f.write(
                    f"Significant fraction: {results['statistics']['significant_fraction']:.2%}\n"
                )
                f.write(
                    f"Normal approximation used: {results['statistics']['normal_approximation_count']}\n"
                )
                f.write(f"LRT used: {results['statistics']['lrt_count']}\n")
                f.write(
                    f"MoM fallbacks: {results['statistics']['fallback_to_mom_count']}\n"
                )

                # FDR analysis results
                if results["statistics"].get("q_values_applied"):
                    f.write("\nFDR Analysis Results:\n")
                    f.write(f"  FDR method: {results['statistics']['fdr_method']}\n")
                    f.write(
                        f"  Pi0 estimate: {results['statistics']['pi0_estimate']:.3f}\n"
                    )
                    f.write(
                        f"  Global p-value (Stouffer): {results['statistics']['global_p_value']:.6f}\n"
                    )
                    f.write(
                        f"  Global significant: {results['statistics']['global_significant']}\n"
                    )
                    f.write(
                        f"  Global threshold: {results['statistics']['global_significance_threshold']}\n"
                    )
                    f.write(
                        f"  Mean q-value: {results['statistics']['mean_q_value']:.6f}\n"
                    )
                    f.write(
                        f"  Median q-value: {results['statistics']['median_q_value']:.6f}\n"
                    )
                    f.write(
                        f"  Significant regions: {results['statistics']['significant_regions_count']}\n"
                    )

                f.write("\nPerformance:\n")
                f.write(
                    f"  Processing time: {results['statistics']['processing_time_seconds']:.2f} seconds\n"
                )
                f.write(
                    f"  GPU acceleration: {'Yes' if results['statistics']['gpu_used'] else 'No'}\n"
                )
                f.write(f"  Significance level: {self.significance_level}\n")
        except PermissionError:
            # Fallback to current directory if permission denied
            fallback_dir = Path.cwd() / "smart_comparison_results"
            fallback_dir.mkdir(exist_ok=True)
            summary_file = fallback_dir / f"{output_prefix}_summary.txt"
            with open(summary_file, "w") as f:
                f.write("Smart Centroid Comparison Summary\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Centroid 1: {self.centroid1_path}\n")
                f.write(f"Centroid 2: {self.centroid2_path}\n")
                f.write(
                    f"Total positions compared: {results['statistics']['total_positions']}\n"
                )
                f.write(
                    f"Significant positions: {results['statistics']['significant_positions']}\n"
                )
                f.write(
                    f"Significant fraction: {results['statistics']['significant_fraction']:.2%}\n"
                )
                f.write(
                    f"Normal approximation used: {results['statistics']['normal_approximation_count']}\n"
                )
                f.write(f"LRT used: {results['statistics']['lrt_count']}\n")
                f.write(
                    f"MoM fallbacks: {results['statistics']['fallback_to_mom_count']}\n"
                )

                # FDR analysis results
                if results["statistics"].get("q_values_applied"):
                    f.write("\nFDR Analysis Results:\n")
                    f.write(f"  FDR method: {results['statistics']['fdr_method']}\n")
                    f.write(
                        f"  Pi0 estimate: {results['statistics']['pi0_estimate']:.3f}\n"
                    )
                    f.write(
                        f"  Global p-value (Stouffer): {results['statistics']['global_p_value']:.6f}\n"
                    )
                    f.write(
                        f"  Global significant: {results['statistics']['global_significant']}\n"
                    )
                    f.write(
                        f"  Global threshold: {results['statistics']['global_significance_threshold']}\n"
                    )
                    f.write(
                        f"  Mean q-value: {results['statistics']['mean_q_value']:.6f}\n"
                    )
                    f.write(
                        f"  Median q-value: {results['statistics']['median_q_value']:.6f}\n"
                    )
                    f.write(
                        f"  Significant regions: {results['statistics']['significant_regions_count']}\n"
                    )

                f.write("\nPerformance:\n")
                f.write(
                    f"  Processing time: {results['statistics']['processing_time_seconds']:.2f} seconds\n"
                )
                f.write(
                    f"  GPU acceleration: {'Yes' if results['statistics']['gpu_used'] else 'No'}\n"
                )
                f.write(f"  Significance level: {self.significance_level}\n")
            print(
                f"Permission denied for {self.output_dir}, saved to {fallback_dir} instead"
            )

        # Export binary formats for DMP and DMR data
        self._export_dmp_data_binary(results, output_prefix)
        self._export_dmr_data_binary(results, output_prefix)

        # Save biological DMPs if DMP filtering was applied
        if "biological_dmps" in results and results["biological_dmps"]:
            biological_file = self.output_dir / f"{output_prefix}_biological_dmps.csv"
            try:
                with open(biological_file, "w") as f:
                    f.write(
                        "position,p_value,q_value,mean1,mean2,selected,distribution_overlap,delta_mean,jeffreys_divergence,cohen_d,auc_score,alpha1,beta1,alpha2,beta2,selection_reason\n"
                    )
                    for dmp in results["biological_dmps"]:
                        f.write(
                            f"{dmp.position},{dmp.p_value},{dmp.q_value or 'N/A'},{dmp.mean1},{dmp.mean2},{dmp.selected},{dmp.distribution_overlap or 'N/A'},{dmp.Δμ},{dmp.JD or 'N/A'},{dmp.cohen_d or 'N/A'},{dmp.auc_score or 'N/A'},{dmp.alpha1},{dmp.beta1},{dmp.alpha2},{dmp.beta2},{dmp.selection_reason}\n"
                        )
                logger.info(f"Biological DMPs: {biological_file}")
            except PermissionError:
                fallback_dir = Path.cwd() / "smart_comparison_results"
                fallback_dir.mkdir(exist_ok=True)
                biological_file = fallback_dir / f"{output_prefix}_biological_dmps.csv"
                with open(biological_file, "w") as f:
                    f.write(
                        "position,p_value,q_value,mean1,mean2,selected,distribution_overlap,delta_mean,jeffreys_divergence,cohen_d,auc_score,alpha1,beta1,alpha2,beta2,selection_reason\n"
                    )
                    for dmp in results["biological_dmps"]:
                        f.write(
                            f"{dmp.position},{dmp.p_value},{dmp.q_value or 'N/A'},{dmp.mean1},{dmp.mean2},{dmp.selected},{dmp.distribution_overlap or 'N/A'},{dmp.Δμ},{dmp.JD or 'N/A'},{dmp.cohen_d or 'N/A'},{dmp.auc_score or 'N/A'},{dmp.alpha1},{dmp.beta1},{dmp.alpha2},{dmp.beta2},{dmp.selection_reason}\n"
                        )
                print(
                    f"Permission denied for {self.output_dir}, biological DMPs saved to {biological_file}"
                )

        logger.info(f"Results saved to {self.output_dir}")
        logger.info(f"Statistics: {stats_file}")
        if results["significant_results"]:
            logger.info(f"Significant positions: {significant_file}")
        logger.info(f"Summary: {summary_file}")


def main():
    """Main function to run smart centroid comparison."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Smart comparison of two extended centroids with GPU acceleration"
    )
    parser.add_argument(
        "--centroid1",
        type=str,
        help="Path to first extended centroid .h5 file",
        default="/home/ubuntu/Work/output_workflows/arabidopsis/centroids/WT/1-CG.h5",
    )
    parser.add_argument(
        "--centroid2",
        type=str,
        help="Path to second extended centroid .h5 file",
        default="/home/ubuntu/Work/output_workflows/arabidopsis/centroids/msh1/1-CG.h5",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Output directory for results",
        default="/home/ubuntu/Work/output_workflows/arabidopsis/centroids/WT-msh1/1",
    )
    parser.add_argument(
        "--significance-level",
        type=float,
        default=0.05,
        help="Significance level (default: 0.05)",
    )
    parser.add_argument(
        "--no-gpu", action="store_true", help="Disable GPU acceleration"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10000,
        help="Batch size for processing (default: 10000, auto-adjusted for GPU)",
    )
    # --n-jobs argument removed - multiprocessing not beneficial for GPU operations
    parser.add_argument(
        "--normal-approx-threshold",
        type=int,
        default=30,
        help="Minimum sample size for normal approximation (default: 30)",
    )
    parser.add_argument(
        "--min-beta-params",
        type=float,
        default=2.0,
        help="Minimum alpha/beta values for normal approximation (default: 2.0)",
    )

    args = parser.parse_args()

    comparator = SmartCentroidComparator(
        centroid1_path=args.centroid1,
        centroid2_path=args.centroid2,
        output_dir=args.output_dir,
        significance_level=args.significance_level,
        use_gpu=not args.no_gpu,
        batch_size=args.batch_size,
        normal_approx_threshold=args.normal_approx_threshold,
        min_beta_params=args.min_beta_params,
    )

    results = comparator.compare_centroids()
    comparator.save_results(results)

    print("\nSmart Comparison Summary:")
    print(f"Total positions: {results['statistics']['total_positions']}")
    print(f"Significant positions: {results['statistics']['significant_positions']}")
    print(f"Significant fraction: {results['statistics']['significant_fraction']:.2%}")
    print(
        f"Normal approximation: {results['statistics']['normal_approximation_count']}"
    )
    print(f"LRT method: {results['statistics']['lrt_count']}")
    print(f"MoM fallbacks: {results['statistics']['fallback_to_mom_count']}")
    print(
        f"Processing time: {results['statistics']['processing_time_seconds']:.2f} seconds"
    )
    print(f"Results saved to: {args.output_dir}")


if __name__ == "__main__":
    main()
