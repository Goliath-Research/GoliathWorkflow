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

from typing import Tuple, Dict, Any, List, Union, Optional, Callable
from pathlib import Path

import numpy as np
import pandas as pd

from .beta_analytics import log_beta_binomial_pmf
from .beta_mixture import fit_beta_mixture, estimate_js_divergence
from .core.methyl_frame import MethylSample, MethylExtendedCentroid
from .gpu_detection import (
    is_gpu_available,
    get_gpu_memory_gb,
    get_gpu_device_count,
    cleanup_gpu_memory,
)
from .memory_manager import get_memory_manager, force_gpu_cleanup
from .metric_validations import validate_methylation_data
from .metrics_core import compute_bhattacharyya_distance
from .performance_profiler import (
    get_performance_profiler,
    start_performance_monitoring,
    stop_performance_monitoring,
)
from .statistical_tests import likelihood_ratio_test_beta, storey_qvalues
from methyl_utils.logging_utils import setup_module_logging
from .core.methyl_mixture_centroid import MethylBetaMixtureCentroid
logger = setup_module_logging(__name__)

# Type aliases for better type hints
ArrayLike = np.ndarray
DataFrameType = Union[pd.DataFrame, Any]  # Any for cuDF when available


# Constants
BD_CAP = 20.0  # Cap Bhattacharyya Distance to prevent overflow when converting to BC (exp(-20) ≈ 0)

# Distribution identifiers
DIST_BETA = 1
DIST_NORMAL = 2
DIST_BETA_BINOM = 3
DIST_BETA_MIXTURE = 4

# Simplified dtype for centroid comparison results
# effect_size is the single biological importance measure (computed here; MethylDetector uses as-is)
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
    ('bhattacharyya', np.float32),  # Bhattacharyya Distance (BC = exp(-bhattacharyya))
    ('dist', np.uint8),  # Distribution selection (see DIST_* constants)
    ('n1', np.uint32),
    ('n2', np.uint32),
    ('variance1', np.float32),
    ('variance2', np.float32),
    ('effect_size', np.float32),  # Biological importance: |delta_mean| / (max(overlap, min_floor) * combined_std)
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

    def __init__(
        self,
        centroid1: Optional[MethylExtendedCentroid] = None,
        centroid2: Optional[MethylExtendedCentroid] = None,
        min_coverage: int = 4,
        distribution: str = "auto",
        delta_mean_mode: str = "mean",
        overlap_mode: str = "beta",
        min_samples_normal: int = 6,
        min_samples_beta: int = 10,
        min_coverage_binom: int = 10,
        overdispersion_threshold: float = 1.5,
        enable_mixture: bool = True,
        bmm_centroid1: Any = None,
        bmm_centroid2: Any = None,
    ):
        self.centroid1 = centroid1
        self.centroid2 = centroid2
        self.common_pos = None

        if centroid1 is not None and centroid2 is not None:
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

        self.min_coverage = int(min_coverage)

        # Distribution selection parameters
        self.distribution = distribution
        self.min_samples_normal = min_samples_normal
        self.min_samples_beta = min_samples_beta
        self.min_coverage_binom = min_coverage_binom
        self.overdispersion_threshold = overdispersion_threshold
        self.enable_mixture = enable_mixture

        # Metric modes for delta_mean/overlap calculations
        self.delta_mean_mode = self._normalize_metric_mode(
            delta_mean_mode, default="mean", allowed={"mean", "beta", "normal", "auto", "legacy"}
        )
        if self.delta_mean_mode == "legacy":
            self.delta_mean_mode = "mean"
        self.overlap_mode = self._normalize_metric_mode(
            overlap_mode, default="beta", allowed={"beta", "normal", "auto", "legacy"}
        )
        if self.overlap_mode == "legacy":
            self.overlap_mode = "beta"

        # Optional Beta Mixture centroids (mask-based)
        self._bmm_input1 = bmm_centroid1
        self._bmm_input2 = bmm_centroid2
        self._bmm_map1: Optional[Dict[int, Tuple[np.ndarray, np.ndarray, np.ndarray]]] = None
        self._bmm_map2: Optional[Dict[int, Tuple[np.ndarray, np.ndarray, np.ndarray]]] = None
        self._bmm_positions_common: Optional[np.ndarray] = None

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
                # Use .loc to avoid SettingWithCopyWarning when modifying DataFrame
                cent._df.loc[zero_mask, "uC"] = 1  # Ensure mean=0, avoid div-by-zero in comparisons
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
    def load_and_align_from_samples(
        cls, centroid1, centroid2: MethylSample,
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
                # Use .loc to avoid SettingWithCopyWarning when modifying DataFrame
                cent._df.loc[zero_mask, "uC"] = 1  # Ensure mean=0, avoid div-by-zero in comparisons
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
        from methyl_utils import CONTEXT_CG, CONTEXT_CHG, CONTEXT_CHH, CONTEXT_SHIFT
        context_map = {
            "CG": CONTEXT_CG << CONTEXT_SHIFT,
            "CHG": CONTEXT_CHG << CONTEXT_SHIFT,
            "CHH": CONTEXT_CHH << CONTEXT_SHIFT
        }
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
            Tuple of (methylation_fractions_matrix, positions_array, contexts_array, context_indices_dict)
            - methylation_fractions_matrix: (n_samples, n_positions) array with NaN for missing positions
            - positions_array: (n_positions,) array of positions in column order
            - contexts_array: (n_positions,) array of context (e.g. 'CG') per column; column j is (positions_array[j], contexts_array[j])
            - context_indices_dict: Dictionary mapping context to index arrays in the full position array
        """
        from methyl_utils.core.io import load_from_h5
        from pathlib import Path
        import numpy as np
        
        # Build ordered position array and (position, context) -> column index mapping.
        # Key by (pos, ctx) so the same position in different contexts gets distinct columns.
        all_positions = []
        all_contexts = []
        position_to_index = {}  # (pos, ctx) -> column index
        context_indices_dict = {}
        
        for ctx in ["CG", "CHG", "CHH"]:
            if ctx in reference_positions:
                ctx_positions = reference_positions[ctx].astype(np.uint32)
                ctx_indices = []
                for pos in ctx_positions:
                    key = (int(pos), ctx)
                    if key not in position_to_index:
                        position_to_index[key] = len(all_positions)
                        all_positions.append(pos)
                        all_contexts.append(ctx)
                    ctx_indices.append(position_to_index[key])
                context_indices_dict[ctx] = np.array(ctx_indices, dtype=np.int64)
        
        all_positions = np.array(all_positions, dtype=np.uint32)
        all_contexts = np.array(all_contexts, dtype=object)
        n_positions = len(all_positions)
        n_samples = len(sample_paths)
        chrom_str = chromosome[0] if isinstance(chromosome, (list, tuple)) else str(chromosome)

        # Initialize result matrix with NaN
        X = np.full((n_samples, n_positions), np.nan, dtype=np.float32)
        n_missing_file = 0
        n_empty_align = 0
        n_error = 0
        first_missing_path = None
        first_ctx = next(iter(reference_positions.keys()), "CG")

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
                    h5_file = sample_path / f"{chrom_str}-{ctx}.h5"

                if not h5_file.exists():
                    if first_missing_path is None:
                        first_missing_path = h5_file
                    n_missing_file += 1
                    continue
                
                try:
                    # Load sample (full then align). Once load_from_h5(path, positions=...) is
                    # confirmed in MethylClassifier, switch to load_from_h5(h5_file, ctx_positions)
                    # to avoid loading full file and duplicate logic.
                    sample = load_from_h5(h5_file)
                    aligned = sample.align_to_positions(ctx_positions)
                    
                    if len(aligned) == 0:
                        n_empty_align += 1
                        continue

                    # Extract methylation fractions efficiently
                    mC_vals = aligned.mC.values if hasattr(aligned.mC, 'values') else np.asarray(aligned.mC)
                    uC_vals = aligned.uC.values if hasattr(aligned.uC, 'values') else np.asarray(aligned.uC)
                    pos_vals = aligned.pos.values if hasattr(aligned.pos, 'values') else np.asarray(aligned.pos)
                    
                    # Calculate methylation fractions
                    total_reads = mC_vals + uC_vals
                    with np.errstate(divide='ignore', invalid='ignore'):
                        meth_fractions = np.where(total_reads >= min_coverage, mC_vals / total_reads, np.nan)
                    
                    # Map to correct indices in result matrix using (position, context) lookup
                    for j, pos in enumerate(pos_vals):
                        key = (int(pos), ctx)
                        if key in position_to_index:
                            idx = position_to_index[key]
                            X[i, idx] = meth_fractions[j]
                            
                except Exception as e:
                    logger.debug(f"Failed to process {h5_file}: {e}")
                    n_error += 1
                    continue

        n_with_data = int(np.sum(~np.isnan(X).all(axis=1)))
        if n_with_data == 0 and sample_paths:
            logger.warning(
                "Validation extraction: 0 samples had data. Each path must be a directory containing "
                "%s-%s.h5 (or a path to that .h5 file). Example expected path: %s",
                chrom_str, first_ctx, first_missing_path
            )
            if n_missing_file > 0:
                logger.warning(
                    "  %s path(s) had no such file. Check that validation sample directories contain "
                    "%s-%s.h5 for this chromosome/context.",
                    n_missing_file, chrom_str, first_ctx
                )
            if n_empty_align > 0:
                logger.warning("  %s H5 file(s) existed but had no overlapping positions with the DMP list.", n_empty_align)
            if n_error > 0:
                logger.warning("  %s H5 file(s) raised an error on load/align (see debug log).", n_error)

        return X, all_positions, all_contexts, context_indices_dict

    def _init_cpu_backend(self):
        """Initialize CPU backend."""
        self.cp = None
        self.xp = np
        self.to_cpu = lambda a: a
        logger.info("CPU backend initialized")

    @staticmethod
    def _normalize_metric_mode(value: Optional[str], default: str, allowed: set[str]) -> str:
        if value is None:
            return default
        mode = str(value).strip().lower()
        if mode not in allowed:
            logger.warning(
                f"Unrecognized metric mode '{value}', falling back to '{default}'"
            )
            return default
        return mode

    def _get_centroid_context(self, centroid: MethylSample) -> Optional[str]:
        meta = getattr(centroid, "metadata", None) or getattr(centroid, "_metadata", None)
        if isinstance(meta, dict):
            ctx = meta.get("context")
            if ctx:
                return str(ctx)
        return None

    def _load_bmm_centroid(self, source: Any):
        if source is None:
            return None
        try:
            from methyl_utils.core.methyl_mixture_centroid import MethylBetaMixtureCentroid
        except Exception:
            return None
        if isinstance(source, MethylBetaMixtureCentroid):
            return source
        try:
            path = Path(source)
            if path.exists():
                return MethylBetaMixtureCentroid.from_json(path)
        except Exception:
            return None
        return None

    def _build_bmm_map(
        self,
        bmm_centroid: Any,
        context: Optional[str] = None,
    ) -> Optional[Dict[int, Tuple[np.ndarray, np.ndarray, np.ndarray]]]:
        if bmm_centroid is None:
            return None
        df = bmm_centroid.df if hasattr(bmm_centroid, "df") else None
        if df is None or len(df) == 0:
            return None
        if context and "context" in df.columns:
            df = df[df["context"] == context]
        if hasattr(bmm_centroid, "mask") and bmm_centroid.mask is not None and not bmm_centroid.mask.empty:
            mask_df = bmm_centroid.mask
            if context and "context" in mask_df.columns:
                mask_df = mask_df[mask_df["context"] == context]
            mask_positions = set(mask_df["position"].astype(np.uint32).tolist())
            df = df[df["position"].astype(np.uint32).isin(mask_positions)]
        if df.empty:
            return None

        bmm_map: Dict[int, Tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        for row in df.itertuples(index=False):
            pos = int(getattr(row, "position"))
            weights = getattr(row, "weights", None)
            alphas = getattr(row, "alphas", None)
            betas = getattr(row, "betas", None)
            if not weights or not alphas or not betas:
                continue
            try:
                w = np.asarray(weights, dtype=float)
                a = np.asarray(alphas, dtype=float)
                b = np.asarray(betas, dtype=float)
            except Exception:
                continue
            if len(w) == 0 or len(w) != len(a) or len(w) != len(b):
                continue
            if not np.all(np.isfinite(w)) or not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
                continue
            if np.sum(w) <= 0:
                continue
            bmm_map[pos] = (w, a, b)

        return bmm_map if bmm_map else None

    def _prepare_bmm_maps(self, centroid1: MethylSample, centroid2: MethylSample) -> None:
        ctx = self._get_centroid_context(centroid1) or self._get_centroid_context(centroid2)
        bmm1 = self._load_bmm_centroid(self._bmm_input1)
        bmm2 = self._load_bmm_centroid(self._bmm_input2)
        self._bmm_map1 = self._build_bmm_map(bmm1, context=ctx)
        self._bmm_map2 = self._build_bmm_map(bmm2, context=ctx)
        if self._bmm_map1 is not None and self._bmm_map2 is not None:
            keys1 = np.fromiter(self._bmm_map1.keys(), dtype=np.uint32)
            keys2 = np.fromiter(self._bmm_map2.keys(), dtype=np.uint32)
            if len(keys1) > 0 and len(keys2) > 0:
                self._bmm_positions_common = np.intersect1d(keys1, keys2)
            else:
                self._bmm_positions_common = None
        else:
            self._bmm_positions_common = None

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

            # Prepare optional BMM maps (mask-based mixtures)
            if self.enable_mixture:
                self._prepare_bmm_maps(centroid1, centroid2)

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

            # Compute Bhattacharyya Distance (beta-mode only; auto/normal handled in batch)
            if self.overlap_mode == "beta":
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

        # Filter by minimum sample count (N) per position so positions with too few samples are excluded (min_N_pct semantics)
        if hasattr(centroid1, 'N') and centroid1.N is not None and hasattr(centroid2, 'N') and centroid2.N is not None:
            N1_vals = centroid1.N.values if hasattr(centroid1.N, 'values') else np.asarray(centroid1.N)
            N2_vals = centroid2.N.values if hasattr(centroid2.N, 'values') else np.asarray(centroid2.N)
            # Align by position so N1[i] and N2[i] refer to the same position (positions assumed sorted)
            idx1 = np.searchsorted(pos1_vals, common_positions, side='left')
            idx2 = np.searchsorted(pos2_vals, common_positions, side='left')
            N1_common = N1_vals[idx1]
            N2_common = N2_vals[idx2]
            # Require min(N1, N2) >= min_coverage (min_coverage = effective_min_N from min_N_pct in MethylDetector)
            min_N_both = np.minimum(N1_common.astype(np.int64), N2_common.astype(np.int64))
            coverage_mask = min_N_both >= self.min_coverage
            common_positions = common_positions[coverage_mask]
        elif hasattr(centroid1, 'mC') and hasattr(centroid1, 'uC') and hasattr(centroid2, 'mC') and hasattr(centroid2, 'uC'):
            # Fallback when N is not available: filter by total read coverage (mC+uC)
            c1_mask = np.isin(pos1_vals, common_positions)
            c2_mask = np.isin(pos2_vals, common_positions)
            mC1_vals = centroid1.mC.values if hasattr(centroid1.mC, 'values') else np.asarray(centroid1.mC)
            uC1_vals = centroid1.uC.values if hasattr(centroid1.uC, 'values') else np.asarray(centroid1.uC)
            mC2_vals = centroid2.mC.values if hasattr(centroid2.mC, 'values') else np.asarray(centroid2.mC)
            uC2_vals = centroid2.uC.values if hasattr(centroid2.uC, 'values') else np.asarray(centroid2.uC)
            c1_coverage = mC1_vals[c1_mask] + uC1_vals[c1_mask]
            c2_coverage = mC2_vals[c2_mask] + uC2_vals[c2_mask]
            coverage_mask = (c1_coverage + c2_coverage) >= self.min_coverage
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

        # Optional stats for distribution selection
        Sx1 = centroid1.Sx[indices1].astype(np.float32)
        Sx2_vals = centroid2.Sx[indices2].astype(np.float32)
        Sx2_1 = centroid1.Sx2[indices1].astype(np.float32)
        Sx2_2 = centroid2.Sx2[indices2].astype(np.float32)

        # Normal-distribution moments (used for normal-mode metrics)
        mean_normal1 = Sx1 / np.maximum(N1, 1.0)
        mean_normal2 = Sx2_vals / np.maximum(N2, 1.0)
        var_normal1 = np.maximum(
            Sx2_1 - (Sx1**2 / np.maximum(N1, 1.0)), 1e-12
        ) / np.maximum(N1 - 1, 1)
        var_normal2 = np.maximum(
            Sx2_2 - (Sx2_vals**2 / np.maximum(N2, 1.0)), 1e-12
        ) / np.maximum(N2 - 1, 1)

        # Coverage statistics for Beta-Binomial selection
        sum_cov1 = None
        sum_cov2 = None
        if getattr(centroid1, "sum_cov", None) is not None and getattr(centroid2, "sum_cov", None) is not None:
            sum_cov1 = centroid1.sum_cov[indices1].astype(np.float64)
            sum_cov2 = centroid2.sum_cov[indices2].astype(np.float64)
        else:
            # Fallback: approximate using average counts * N
            sum_cov1 = (centroid1.mC[indices1].astype(np.float64) + centroid1.uC[indices1].astype(np.float64)) * N1
            sum_cov2 = (centroid2.mC[indices2].astype(np.float64) + centroid2.uC[indices2].astype(np.float64)) * N2

        sum_cov2_1 = None
        sum_cov2_2 = None
        if getattr(centroid1, "sum_cov2", None) is not None and getattr(centroid2, "sum_cov2", None) is not None:
            sum_cov2_1 = centroid1.sum_cov2[indices1].astype(np.float64)
            sum_cov2_2 = centroid2.sum_cov2[indices2].astype(np.float64)

        # Distribution selection masks
        dist_mode = (self.distribution or "auto").lower()
        use_normal_mask = np.zeros(len(positions), dtype=bool)
        use_beta_binom_mask = np.zeros(len(positions), dtype=bool)
        use_mixture_mask = np.zeros(len(positions), dtype=bool)
        force_mixture = dist_mode == "beta_mixture"

        if dist_mode == "normal":
            use_normal_mask[:] = True
        elif dist_mode == "beta_binomial":
            use_beta_binom_mask[:] = True
        elif dist_mode == "beta":
            pass
        else:
            # Auto selection
            use_normal_mask = (N1 < self.min_samples_normal) | (N2 < self.min_samples_normal)

            # Coverage-based Beta-Binomial selection (low coverage or overdispersion)
            mean_cov1 = sum_cov1 / np.maximum(N1, 1.0)
            mean_cov2 = sum_cov2 / np.maximum(N2, 1.0)

            overdisp1 = np.zeros_like(mean_cov1, dtype=np.float64)
            overdisp2 = np.zeros_like(mean_cov2, dtype=np.float64)
            if sum_cov2_1 is not None and sum_cov2_2 is not None:
                var_cov1 = np.maximum(sum_cov2_1 / np.maximum(N1, 1.0) - mean_cov1**2, 0.0)
                var_cov2 = np.maximum(sum_cov2_2 / np.maximum(N2, 1.0) - mean_cov2**2, 0.0)
                overdisp1 = var_cov1 / np.maximum(mean_cov1, 1e-6)
                overdisp2 = var_cov2 / np.maximum(mean_cov2, 1e-6)

            use_beta_binom_mask = (
                (mean_cov1 < self.min_coverage_binom)
                | (mean_cov2 < self.min_coverage_binom)
                | (overdisp1 > self.overdispersion_threshold)
                | (overdisp2 > self.overdispersion_threshold)
            )

            # Mixture selection if mixture params are present
            if self.enable_mixture:
                if self._bmm_positions_common is not None:
                    use_mixture_mask = (
                        np.isin(positions, self._bmm_positions_common)
                        & (N1 >= self.min_samples_beta)
                        & (N2 >= self.min_samples_beta)
                    )
                else:
                    required_mix_cols = {"mix_w1", "mix_w2", "mix_w3", "mix_a1", "mix_a2", "mix_a3", "mix_b1", "mix_b2", "mix_b3"}
                    if required_mix_cols.issubset(set(centroid1._df.columns)) and required_mix_cols.issubset(set(centroid2._df.columns)):
                        wsum1 = centroid1._df["mix_w1"].values[indices1] + centroid1._df["mix_w2"].values[indices1] + centroid1._df["mix_w3"].values[indices1]
                        wsum2 = centroid2._df["mix_w1"].values[indices2] + centroid2._df["mix_w2"].values[indices2] + centroid2._df["mix_w3"].values[indices2]
                        use_mixture_mask = (wsum1 > 0) & (wsum2 > 0) & (N1 >= self.min_samples_beta) & (N2 >= self.min_samples_beta)

        if force_mixture and self.enable_mixture:
            if self._bmm_positions_common is not None:
                use_mixture_mask = np.isin(positions, self._bmm_positions_common)
            else:
                # Fallback to mix columns if present
                required_mix_cols = {"mix_w1", "mix_w2", "mix_w3", "mix_a1", "mix_a2", "mix_a3", "mix_b1", "mix_b2", "mix_b3"}
                if required_mix_cols.issubset(set(centroid1._df.columns)) and required_mix_cols.issubset(set(centroid2._df.columns)):
                    wsum1 = centroid1._df["mix_w1"].values[indices1] + centroid1._df["mix_w2"].values[indices1] + centroid1._df["mix_w3"].values[indices1]
                    wsum2 = centroid2._df["mix_w1"].values[indices2] + centroid2._df["mix_w2"].values[indices2] + centroid2._df["mix_w3"].values[indices2]
                    use_mixture_mask = (wsum1 > 0) & (wsum2 > 0)

        use_beta_mask = ~(use_normal_mask | use_beta_binom_mask | use_mixture_mask)

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

        # Compute Beta p-values for all positions (used as default/fallback)
        lrt_result = likelihood_ratio_test_beta(
            centroid1_batch, centroid2_batch, use_gpu=self.gpu_available
        )

        if lrt_result is None:
            logger.warning("LRT returned None, using fallback values")
            p_values_beta = np.ones(len(positions), dtype=np.float32)
        else:
            _, p_values_beta = lrt_result
            p_values_beta = p_values_beta.astype(np.float32)

        p_values = np.ones(len(positions), dtype=np.float32)
        dist_ids = np.full(len(positions), DIST_BETA, dtype=np.uint8)

        # Normal distribution test for small-sample positions
        if np.any(use_normal_mask):
            from scipy.stats import norm
            se_diff = np.sqrt(
                var_normal1 / np.maximum(N1, 1.0)
                + var_normal2 / np.maximum(N2, 1.0)
            )
            z_stat = (mean1 - mean2) / np.maximum(se_diff, 1e-12)
            p_norm = 2 * (1 - norm.cdf(np.abs(z_stat)))
            p_values[use_normal_mask] = p_norm[use_normal_mask].astype(np.float32)
            dist_ids[use_normal_mask] = DIST_NORMAL

        # Beta-Binomial test using aggregated counts (if selected)
        if np.any(use_beta_binom_mask):
            from scipy.stats import chi2
            from methyl_utils.statistical_tests import _estimate_beta_params_bounded
            # Use BB params from count-based MoM when available (discrete model)
            has_bb1 = getattr(centroid1, "alpha_bb", None) is not None
            has_bb2 = getattr(centroid2, "alpha_bb", None) is not None
            if has_bb1 and has_bb2:
                bb_a1 = centroid1.alpha_bb[indices1].astype(np.float32)
                bb_b1 = centroid1.beta_bb[indices1].astype(np.float32)
                bb_a2 = centroid2.alpha_bb[indices2].astype(np.float32)
                bb_b2 = centroid2.beta_bb[indices2].astype(np.float32)
            else:
                bb_a1, bb_b1 = alpha1, beta1
                bb_a2, bb_b2 = alpha2, beta2
            # Use available sum counts or fallback to averages * N
            if getattr(centroid1, "sum_mC", None) is not None and getattr(centroid2, "sum_mC", None) is not None:
                k1 = centroid1.sum_mC[indices1].astype(np.float64)
                k2 = centroid2.sum_mC[indices2].astype(np.float64)
            else:
                k1 = centroid1.mC[indices1].astype(np.float64) * N1
                k2 = centroid2.mC[indices2].astype(np.float64) * N2

            n1 = sum_cov1.astype(np.float64)
            n2 = sum_cov2.astype(np.float64)

            # Pooled beta params from combined log sums (null model)
            N0 = N1 + N2
            log_x_sum0 = log_x_sum1 + log_x_sum2
            log_1mx_sum0 = log_1mx_sum1 + log_1mx_sum2
            alpha0, beta0 = _estimate_beta_params_bounded(N0, log_x_sum0, log_1mx_sum0)

            ll1 = log_beta_binomial_pmf(k1, n1, bb_a1, bb_b1, use_gpu=self.gpu_available)
            ll2 = log_beta_binomial_pmf(k2, n2, bb_a2, bb_b2, use_gpu=self.gpu_available)
            ll0_1 = log_beta_binomial_pmf(k1, n1, alpha0, beta0, use_gpu=self.gpu_available)
            ll0_2 = log_beta_binomial_pmf(k2, n2, alpha0, beta0, use_gpu=self.gpu_available)
            llr = 2.0 * ((ll1 + ll2) - (ll0_1 + ll0_2))
            llr = np.maximum(llr, 0.0)
            p_bb = chi2.sf(llr, df=2)
            p_values[use_beta_binom_mask] = p_bb[use_beta_binom_mask].astype(np.float32)
            dist_ids[use_beta_binom_mask] = DIST_BETA_BINOM

        # Beta mixture handling (optional, if mixture params are stored)
        if np.any(use_mixture_mask):
            try:
                from methyl_utils.beta_mixture import mixture_logpdf, _resolve_backend, _to_numpy
            except ImportError:
                from .beta_mixture import mixture_logpdf, _resolve_backend, _to_numpy

            xp, betaln_fn, _ = _resolve_backend(self.gpu_available)

            # Default to beta p-values unless mixture computation succeeds
            p_values[use_mixture_mask] = p_values_beta[use_mixture_mask]
            dist_ids[use_mixture_mask] = DIST_BETA_MIXTURE

            mixture_indices = np.where(use_mixture_mask)[0]

            if self._bmm_map1 is not None and self._bmm_map2 is not None:
                for idx in mixture_indices:
                    pos = int(positions[idx])
                    entry1 = self._bmm_map1.get(pos)
                    entry2 = self._bmm_map2.get(pos)
                    if entry1 is None or entry2 is None:
                        continue
                    w1, a1m, b1m = entry1
                    w2, a2m, b2m = entry2
                    if np.sum(w1) <= 0 or np.sum(w2) <= 0:
                        continue
                    w1 = w1 / np.sum(w1)
                    w2 = w2 / np.sum(w2)
                    try:
                        log_m1 = mixture_logpdf(
                            xp.asarray([mean1[idx]]),
                            xp.asarray(w1),
                            xp.asarray(a1m),
                            xp.asarray(b1m),
                            xp=xp,
                            betaln_fn=betaln_fn,
                        )
                        log_m2 = mixture_logpdf(
                            xp.asarray([mean1[idx]]),
                            xp.asarray(w2),
                            xp.asarray(a2m),
                            xp.asarray(b2m),
                            xp=xp,
                            betaln_fn=betaln_fn,
                        )
                        llr = 2.0 * (float(_to_numpy(log_m1)) - float(_to_numpy(log_m2)))
                        llr = max(llr, 0.0)
                        from scipy.stats import chi2
                        p_values[idx] = chi2.sf(llr, df=2)
                    except Exception:
                        continue
            else:
                mix_w1 = centroid1._df["mix_w1"].values[indices1]
                mix_w2 = centroid1._df["mix_w2"].values[indices1]
                mix_w3 = centroid1._df["mix_w3"].values[indices1]
                mix_a1 = centroid1._df["mix_a1"].values[indices1]
                mix_a2 = centroid1._df["mix_a2"].values[indices1]
                mix_a3 = centroid1._df["mix_a3"].values[indices1]
                mix_b1 = centroid1._df["mix_b1"].values[indices1]
                mix_b2 = centroid1._df["mix_b2"].values[indices1]
                mix_b3 = centroid1._df["mix_b3"].values[indices1]

                mix2_w1 = centroid2._df["mix_w1"].values[indices2]
                mix2_w2 = centroid2._df["mix_w2"].values[indices2]
                mix2_w3 = centroid2._df["mix_w3"].values[indices2]
                mix2_a1 = centroid2._df["mix_a1"].values[indices2]
                mix2_a2 = centroid2._df["mix_a2"].values[indices2]
                mix2_a3 = centroid2._df["mix_a3"].values[indices2]
                mix2_b1 = centroid2._df["mix_b1"].values[indices2]
                mix2_b2 = centroid2._df["mix_b2"].values[indices2]
                mix2_b3 = centroid2._df["mix_b3"].values[indices2]

                for idx in mixture_indices:
                    w1 = np.asarray([mix_w1[idx], mix_w2[idx], mix_w3[idx]], dtype=float)
                    a1m = np.asarray([mix_a1[idx], mix_a2[idx], mix_a3[idx]], dtype=float)
                    b1m = np.asarray([mix_b1[idx], mix_b2[idx], mix_b3[idx]], dtype=float)
                    w2 = np.asarray([mix2_w1[idx], mix2_w2[idx], mix2_w3[idx]], dtype=float)
                    a2m = np.asarray([mix2_a1[idx], mix2_a2[idx], mix2_a3[idx]], dtype=float)
                    b2m = np.asarray([mix2_b1[idx], mix2_b2[idx], mix2_b3[idx]], dtype=float)

                    if np.sum(w1) <= 0 or np.sum(w2) <= 0:
                        continue
                    w1 = w1 / np.sum(w1)
                    w2 = w2 / np.sum(w2)

                    try:
                        log_m1 = mixture_logpdf(
                            xp.asarray([mean1[idx]]),
                            xp.asarray(w1),
                            xp.asarray(a1m),
                            xp.asarray(b1m),
                            xp=xp,
                            betaln_fn=betaln_fn,
                        )
                        log_m2 = mixture_logpdf(
                            xp.asarray([mean1[idx]]),
                            xp.asarray(w2),
                            xp.asarray(a2m),
                            xp.asarray(b2m),
                            xp=xp,
                            betaln_fn=betaln_fn,
                        )
                        llr = 2.0 * (float(_to_numpy(log_m1)) - float(_to_numpy(log_m2)))
                        llr = max(llr, 0.0)
                        from scipy.stats import chi2
                        p_values[idx] = chi2.sf(llr, df=2)
                    except Exception:
                        continue

        # Fill beta default for remaining positions
        if np.any(use_beta_mask):
            p_values[use_beta_mask] = p_values_beta[use_beta_mask]
            dist_ids[use_beta_mask] = DIST_BETA

        # Metric calculations for output (delta_mean + overlap)
        eps = 1e-12
        tau1 = alpha1 + beta1
        tau2 = alpha2 + beta2
        mean_beta1 = alpha1 / np.maximum(tau1, eps)
        mean_beta2 = alpha2 / np.maximum(tau2, eps)

        def _bhattacharyya_normal(mu1: np.ndarray, var1: np.ndarray,
                                  mu2: np.ndarray, var2: np.ndarray) -> np.ndarray:
            var1 = np.maximum(var1, eps)
            var2 = np.maximum(var2, eps)
            sigma_sum = var1 + var2
            denom = 2.0 * np.sqrt(var1 * var2)
            term1 = 0.5 * np.log(np.maximum(sigma_sum, eps) / np.maximum(denom, eps))
            term2 = 0.25 * ((mu1 - mu2) ** 2 / np.maximum(sigma_sum, eps))
            return term1 + term2

        mix_mean1 = mix_mean2 = None
        mix_var1 = mix_var2 = None
        mixture_indices = None
        if np.any(use_mixture_mask) and self.enable_mixture:
            mixture_indices = np.where(use_mixture_mask)[0]
            if self._bmm_map1 is not None and self._bmm_map2 is not None:
                mix_mean1 = np.full(len(mixture_indices), np.nan, dtype=np.float32)
                mix_mean2 = np.full(len(mixture_indices), np.nan, dtype=np.float32)
                mix_var1 = np.full(len(mixture_indices), np.nan, dtype=np.float32)
                mix_var2 = np.full(len(mixture_indices), np.nan, dtype=np.float32)
                for j, idx in enumerate(mixture_indices):
                    pos = int(positions[idx])
                    entry1 = self._bmm_map1.get(pos)
                    entry2 = self._bmm_map2.get(pos)
                    if entry1 is None or entry2 is None:
                        continue
                    w1, a1m, b1m = entry1
                    w2, a2m, b2m = entry2
                    if np.sum(w1) <= 0 or np.sum(w2) <= 0:
                        continue
                    w1 = w1 / np.sum(w1)
                    w2 = w2 / np.sum(w2)
                    a1m = np.asarray(a1m, dtype=np.float64)
                    b1m = np.asarray(b1m, dtype=np.float64)
                    a2m = np.asarray(a2m, dtype=np.float64)
                    b2m = np.asarray(b2m, dtype=np.float64)
                    mean1_comp = a1m / np.maximum(a1m + b1m, eps)
                    mean2_comp = a2m / np.maximum(a2m + b2m, eps)
                    var1_comp = (a1m * b1m) / np.maximum((a1m + b1m) ** 2 * (a1m + b1m + 1), eps)
                    var2_comp = (a2m * b2m) / np.maximum((a2m + b2m) ** 2 * (a2m + b2m + 1), eps)
                    mix_mean1[j] = float(np.sum(w1 * mean1_comp))
                    mix_mean2[j] = float(np.sum(w2 * mean2_comp))
                    mix_var1[j] = float(np.sum(w1 * (var1_comp + mean1_comp ** 2)) - mix_mean1[j] ** 2)
                    mix_var2[j] = float(np.sum(w2 * (var2_comp + mean2_comp ** 2)) - mix_mean2[j] ** 2)
            else:
                required_mix_cols = {
                    "mix_w1", "mix_w2", "mix_w3",
                    "mix_a1", "mix_a2", "mix_a3",
                    "mix_b1", "mix_b2", "mix_b3",
                }
                if required_mix_cols.issubset(set(centroid1._df.columns)) and required_mix_cols.issubset(set(centroid2._df.columns)):
                    idx1 = indices1[mixture_indices]
                    idx2 = indices2[mixture_indices]
                    w1 = centroid1._df["mix_w1"].values[idx1]
                    w2 = centroid1._df["mix_w2"].values[idx1]
                    w3 = centroid1._df["mix_w3"].values[idx1]
                    a1m = centroid1._df["mix_a1"].values[idx1]
                    a2m = centroid1._df["mix_a2"].values[idx1]
                    a3m = centroid1._df["mix_a3"].values[idx1]
                    b1m = centroid1._df["mix_b1"].values[idx1]
                    b2m = centroid1._df["mix_b2"].values[idx1]
                    b3m = centroid1._df["mix_b3"].values[idx1]

                    w1b = centroid2._df["mix_w1"].values[idx2]
                    w2b = centroid2._df["mix_w2"].values[idx2]
                    w3b = centroid2._df["mix_w3"].values[idx2]
                    a1b = centroid2._df["mix_a1"].values[idx2]
                    a2b = centroid2._df["mix_a2"].values[idx2]
                    a3b = centroid2._df["mix_a3"].values[idx2]
                    b1b = centroid2._df["mix_b1"].values[idx2]
                    b2b = centroid2._df["mix_b2"].values[idx2]
                    b3b = centroid2._df["mix_b3"].values[idx2]

                    wsum1 = w1 + w2 + w3
                    wsum2 = w1b + w2b + w3b
                    mean1_comp1 = a1m / np.maximum(a1m + b1m, eps)
                    mean1_comp2 = a2m / np.maximum(a2m + b2m, eps)
                    mean1_comp3 = a3m / np.maximum(a3m + b3m, eps)
                    mean2_comp1 = a1b / np.maximum(a1b + b1b, eps)
                    mean2_comp2 = a2b / np.maximum(a2b + b2b, eps)
                    mean2_comp3 = a3b / np.maximum(a3b + b3b, eps)

                    var1_comp1 = (a1m * b1m) / np.maximum((a1m + b1m) ** 2 * (a1m + b1m + 1), eps)
                    var1_comp2 = (a2m * b2m) / np.maximum((a2m + b2m) ** 2 * (a2m + b2m + 1), eps)
                    var1_comp3 = (a3m * b3m) / np.maximum((a3m + b3m) ** 2 * (a3m + b3m + 1), eps)
                    var2_comp1 = (a1b * b1b) / np.maximum((a1b + b1b) ** 2 * (a1b + b1b + 1), eps)
                    var2_comp2 = (a2b * b2b) / np.maximum((a2b + b2b) ** 2 * (a2b + b2b + 1), eps)
                    var2_comp3 = (a3b * b3b) / np.maximum((a3b + b3b) ** 2 * (a3b + b3b + 1), eps)

                    mix_mean1 = (w1 * mean1_comp1 + w2 * mean1_comp2 + w3 * mean1_comp3) / np.maximum(wsum1, eps)
                    mix_mean2 = (w1b * mean2_comp1 + w2b * mean2_comp2 + w3b * mean2_comp3) / np.maximum(wsum2, eps)
                    mix_var1 = (w1 * (var1_comp1 + mean1_comp1 ** 2) +
                                w2 * (var1_comp2 + mean1_comp2 ** 2) +
                                w3 * (var1_comp3 + mean1_comp3 ** 2)) / np.maximum(wsum1, eps) - mix_mean1 ** 2
                    mix_var2 = (w1b * (var2_comp1 + mean2_comp1 ** 2) +
                                w2b * (var2_comp2 + mean2_comp2 ** 2) +
                                w3b * (var2_comp3 + mean2_comp3 ** 2)) / np.maximum(wsum2, eps) - mix_mean2 ** 2

        delta_mode = (self.delta_mean_mode or "mean").lower()
        mean1_out = mean1
        mean2_out = mean2
        if delta_mode == "beta":
            mean1_out = mean_beta1
            mean2_out = mean_beta2
        elif delta_mode == "normal":
            mean1_out = mean_normal1
            mean2_out = mean_normal2
        elif delta_mode == "auto":
            mean1_out = mean_beta1.copy()
            mean2_out = mean_beta2.copy()
            if np.any(use_normal_mask):
                mean1_out[use_normal_mask] = mean_normal1[use_normal_mask]
                mean2_out[use_normal_mask] = mean_normal2[use_normal_mask]
            if mix_mean1 is not None and mix_mean2 is not None and mixture_indices is not None:
                mix_valid = np.isfinite(mix_mean1) & np.isfinite(mix_mean2)
                if np.any(mix_valid):
                    mix_idx = mixture_indices[mix_valid]
                    mean1_out[mix_idx] = mix_mean1[mix_valid]
                    mean2_out[mix_idx] = mix_mean2[mix_valid]

        delta_mean = np.abs(mean1_out - mean2_out)

        # Per-position variance for the chosen distribution (for export and power)
        eps = 1e-12
        tau1 = alpha1.astype(np.float64) + beta1.astype(np.float64)
        tau2 = alpha2.astype(np.float64) + beta2.astype(np.float64)
        var_beta1 = (alpha1.astype(np.float64) * beta1.astype(np.float64)) / np.maximum(tau1 ** 2 * (tau1 + 1), eps)
        var_beta2 = (alpha2.astype(np.float64) * beta2.astype(np.float64)) / np.maximum(tau2 ** 2 * (tau2 + 1), eps)
        variance1_out = var_beta1.astype(np.float32)
        variance2_out = var_beta2.astype(np.float32)
        if delta_mode == "normal" or (delta_mode == "auto" and np.any(use_normal_mask)):
            variance1_out[use_normal_mask] = var_normal1[use_normal_mask]
            variance2_out[use_normal_mask] = var_normal2[use_normal_mask]
        if mix_var1 is not None and mix_var2 is not None and mixture_indices is not None:
            mix_valid = np.isfinite(mix_var1) & np.isfinite(mix_var2)
            if np.any(mix_valid):
                variance1_out[mixture_indices[mix_valid]] = np.asarray(mix_var1[mix_valid], dtype=np.float32)
                variance2_out[mixture_indices[mix_valid]] = np.asarray(mix_var2[mix_valid], dtype=np.float32)

        bhattacharyya = None
        overlap_mode = (self.overlap_mode or "beta").lower()
        if overlap_mode in {"auto", "normal"}:
            normal_bd = _bhattacharyya_normal(mean_normal1, var_normal1, mean_normal2, var_normal2)
            if overlap_mode == "normal":
                bhattacharyya = normal_bd.astype(np.float32)
            else:
                beta_bd = compute_bhattacharyya_distance(
                    alpha1, beta1, alpha2, beta2, use_gpu=self.gpu_available
                ).astype(np.float32)
                bhattacharyya = beta_bd
                if np.any(use_normal_mask):
                    bhattacharyya[use_normal_mask] = normal_bd[use_normal_mask].astype(np.float32)
                if mix_var1 is not None and mix_var2 is not None and mixture_indices is not None:
                    mix_valid = np.isfinite(mix_var1) & np.isfinite(mix_var2) & np.isfinite(mix_mean1) & np.isfinite(mix_mean2)
                    if np.any(mix_valid):
                        mix_bd = _bhattacharyya_normal(
                            mix_mean1[mix_valid], mix_var1[mix_valid],
                            mix_mean2[mix_valid], mix_var2[mix_valid]
                        ).astype(np.float32)
                        bhattacharyya[mixture_indices[mix_valid]] = mix_bd

        # Fill results array directly (vectorized assignment)
        results_view['position'] = positions.astype(np.uint32)
        results_view['p_value'] = p_values
        results_view['q_value'] = p_values  # Will be updated by FDR correction
        results_view['alpha1'] = alpha1.astype(np.float64)
        results_view['beta1'] = beta1.astype(np.float64)
        results_view['alpha2'] = alpha2.astype(np.float64)
        results_view['beta2'] = beta2.astype(np.float64)
        results_view['mean1'] = mean1_out.astype(np.float32)
        results_view['mean2'] = mean2_out.astype(np.float32)
        results_view['delta_mean'] = delta_mean.astype(np.float32)
        if bhattacharyya is not None:
            results_view['bhattacharyya'] = bhattacharyya.astype(np.float32)
        else:
            results_view['bhattacharyya'] = np.zeros(len(positions), dtype=np.float32)  # Will be computed later
        results_view['dist'] = dist_ids
        results_view['n1'] = N1.astype(np.uint32)
        results_view['n2'] = N2.astype(np.uint32)
        results_view['variance1'] = variance1_out
        results_view['variance2'] = variance2_out

        # effect_size: single biological importance measure (MethylDetector uses as-is)
        if bhattacharyya is not None:
            bc_values = np.exp(-np.clip(bhattacharyya.astype(np.float64), 0.0, BD_CAP))
        else:
            bc_values = np.ones(len(positions), dtype=np.float64) * 0.5
        effect_sizes = self.compute_effect_sizes(
            alpha1, beta1, alpha2, beta2,
            delta_mean.astype(np.float64),
            bc_values,
            min_overlap_floor=0.01,
            variance_reliability=True,
        )
        results_view['effect_size'] = effect_sizes

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

        # Get Beta parameters using MethylExtendedCentroid properties
        alpha1, beta1 = centroid1.alpha.values, centroid1.beta.values
        alpha2, beta2 = centroid2.alpha.values, centroid2.beta.values

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

            # Use MethylSample's mean and calculate variance from Beta parameters for Beta comparison
            beta_mean1 = float(centroid1.mean[valid_positions1].mean())
            # Beta distribution variance: αβ/((α+β)²(α+β+1))
            alpha1_valid = centroid1.alpha.values[valid_positions1]
            beta1_valid = centroid1.beta.values[valid_positions1]
            beta_var1 = float(((alpha1_valid * beta1_valid) / ((alpha1_valid + beta1_valid)**2 * (alpha1_valid + beta1_valid + 1))).mean())

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

            # Use MethylSample's mean and calculate variance from Beta parameters for Beta comparison
            beta_mean2 = float(centroid2.mean[valid_positions2].mean())
            # Beta distribution variance: αβ/((α+β)²(α+β+1))
            alpha2_valid = centroid2.alpha.values[valid_positions2]
            beta2_valid = centroid2.beta.values[valid_positions2]
            beta_var2 = float(((alpha2_valid * beta2_valid) / ((alpha2_valid + beta2_valid)**2 * (alpha2_valid + beta2_valid + 1))).mean())

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
    def compute_effect_sizes_altA(
        alpha1: np.ndarray,
        beta1: np.ndarray,
        alpha2: np.ndarray,
        beta2: np.ndarray,
        delta_mean: np.ndarray,
        bc_values: np.ndarray,
        numerical_epsilon: float = 1e-6,
        variance_reliability: bool = True,
        bc_nan_fill: float = 0.5,
    ) -> np.ndarray:
        """
        Compute effect size (single biological importance measure) using Alternative A.

        Alternative A replaces dividing by overlap (BC) with multiplying by a bounded
        separation weight (1 - BC), avoiding blow-ups when BC -> 0.

            effect_size = |delta_mean| * (1 - BC) / (combined_std + numerical_epsilon)

        Optionally multiplied by variance reliability:
            var_factor = 1 / (1 + max_var / 0.05)

        Notes:
        - BC (Bhattacharyya coefficient) is assumed in [0, 1], where 0 = no overlap, 1 = complete overlap.
        - This keeps the “less overlap → higher score” behavior, but caps it naturally.

        Args:
            alpha1, beta1: Beta parameters for centroid 1 (fitted across individuals)
            alpha2, beta2: Beta parameters for centroid 2 (fitted across individuals)
            delta_mean: Difference in means (can be signed; absolute value is used)
            bc_values: Bhattacharyya coefficient (overlap), 0 = no overlap, 1 = complete overlap
            numerical_epsilon: Small value to prevent division by zero
            variance_reliability: If True, penalize high variance (noisy positions)
            bc_nan_fill: Value to fill NaN BCs before clipping (default 0.5)

        Returns:
            Array of effect size values (unnormalized, for downstream weighting)
        """
        eps = 1e-12

        # Concentrations
        tau1 = alpha1 + beta1
        tau2 = alpha2 + beta2

        # Means (mainly needed for variance; keep consistent with your original)
        mean1 = alpha1 / np.maximum(tau1, eps)
        mean2 = alpha2 / np.maximum(tau2, eps)

        # Beta variance
        var1 = mean1 * (1.0 - mean1) / np.maximum(tau1 + 1.0, eps)
        var2 = mean2 * (1.0 - mean2) / np.maximum(tau2 + 1.0, eps)

        # Combined std (your original structure)
        combined_std = np.sqrt(var1 + var2)
        combined_std = np.maximum(combined_std, numerical_epsilon)

        # BC safety and bounded separability weight
        bc_safe = np.clip(np.nan_to_num(bc_values, nan=bc_nan_fill), 0.0, 1.0)
        sep_weight = 1.0 - bc_safe  # 0..1, higher = less overlap

        # Core Alternative A effect size
        denom = combined_std + numerical_epsilon
        raw_effect_size = (np.abs(delta_mean) * sep_weight) / denom

        # Optional reliability penalty (kept exactly as your original)
        if variance_reliability:
            max_var = np.maximum(var1, var2)
            var_factor = 1.0 / (1.0 + max_var / 0.05)
            raw_effect_size = raw_effect_size * var_factor

        # Final cleanup (kept consistent with your original)
        effect_sizes = np.maximum(raw_effect_size, 1e-8)
        effect_sizes = np.nan_to_num(effect_sizes, nan=0.0)
        return effect_sizes.astype(np.float32)

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

    @staticmethod
    def resolve_validation_samples(
        config_samples: Optional[Union[str, List[str]]],
        centroid_dir: Optional[str],
        chromosome: str,
        contexts: Optional[List[str]] = None,
        centroid_name: str = "centroid",
    ) -> List[str]:
        """
        Resolve validation sample paths from config or centroid metadata.

        Args:
            config_samples: "use_metadata", list of paths, or None
            centroid_dir: Directory containing centroid H5 files
            chromosome: Chromosome identifier
            contexts: List of contexts (uses first if provided)
            centroid_name: Name for logging
        """
        if isinstance(config_samples, list):
            logger.debug(f"Using {len(config_samples)} validation samples from config for {centroid_name}")
            return config_samples

        if config_samples != "use_metadata":
            return []

        if not centroid_dir:
            logger.warning(f"No centroid_dir provided for {centroid_name}; cannot read metadata samples")
            return []

        try:
            ctx = contexts[0] if contexts else "CG"
            centroid_path = Path(centroid_dir) / f"{chromosome}-{ctx}.h5"
            if not centroid_path.exists():
                logger.warning(f"Centroid file not found: {centroid_path}")
                return []

            centroid = MethylSample.load_from_h5(str(centroid_path))
            if centroid.metadata:
                samples = centroid.samples
                if samples:
                    logger.info(f"✅ Loaded {len(samples)} validation samples from {centroid_name} metadata")
                    return samples
                logger.warning(
                    f"No sample paths found in {centroid_name} metadata "
                    "(checked 'sample_paths' and 'samples_used')"
                )
            else:
                logger.warning(f"No metadata in {centroid_name} centroid")
        except Exception as e:
            logger.warning(f"Failed to read validation samples from {centroid_name} metadata: {e}")

        return []

    @staticmethod
    def load_binned_counts_from_centroids(
        dmps_df: pd.DataFrame,
        centroid1_dir: str,
        centroid2_dir: str,
        chromosome: str,
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """
        Load per-position bin counts from centroid H5 files for given DMPs.

        Returns:
            (bin_edges, counts1, counts2) or None if not available.
        """
        if dmps_df is None or dmps_df.empty:
            return None
        if "context" not in dmps_df.columns:
            dmps_df = dmps_df.copy()
            dmps_df["context"] = "CG"

        try:
            import h5py
        except Exception:
            return None

        counts1 = None
        counts2 = None
        bin_edges_ref = None

        for ctx in np.unique(dmps_df["context"].values):
            ctx_mask = dmps_df["context"].values == ctx
            ctx_positions = dmps_df.loc[ctx_mask, "position"].values.astype(np.uint32)
            if len(ctx_positions) == 0:
                continue

            c1_path = Path(centroid1_dir) / f"{chromosome}-{ctx}.h5"
            c2_path = Path(centroid2_dir) / f"{chromosome}-{ctx}.h5"
            if not c1_path.exists() or not c2_path.exists():
                return None

            try:
                with h5py.File(c1_path, "r") as f1, h5py.File(c2_path, "r") as f2:
                    if "binned_stats" not in f1 or "binned_stats" not in f2:
                        return None
                    be1 = np.asarray(f1["binned_stats"]["bin_edges"][:], dtype=np.float32)
                    be2 = np.asarray(f2["binned_stats"]["bin_edges"][:], dtype=np.float32)
                    if be1.shape != be2.shape or not np.allclose(be1, be2):
                        logger.warning(f"Binned bin_edges mismatch for context {ctx}; falling back to samples")
                        return None

                    if bin_edges_ref is None:
                        bin_edges_ref = be1
                        n_bins = len(bin_edges_ref) - 1
                        counts1 = np.zeros((len(dmps_df), n_bins), dtype=np.int32)
                        counts2 = np.zeros((len(dmps_df), n_bins), dtype=np.int32)
                    else:
                        if len(be1) != len(bin_edges_ref):
                            logger.warning(f"Binned bins mismatch for context {ctx}; falling back to samples")
                            return None

                    pos1 = np.asarray(f1["methylation_data"]["pos"][:], dtype=np.uint32)
                    pos2 = np.asarray(f2["methylation_data"]["pos"][:], dtype=np.uint32)
                    idx1 = np.searchsorted(pos1, ctx_positions)
                    idx2 = np.searchsorted(pos2, ctx_positions)
                    valid1 = (idx1 < len(pos1)) & (pos1[idx1] == ctx_positions)
                    valid2 = (idx2 < len(pos2)) & (pos2[idx2] == ctx_positions)
                    valid = valid1 & valid2
                    if not np.any(valid):
                        continue

                    bc1 = f1["binned_stats"]["bin_counts"][idx1[valid]]
                    bc2 = f2["binned_stats"]["bin_counts"][idx2[valid]]
                    global_idx = np.where(ctx_mask)[0][valid]
                    counts1[global_idx] = bc1
                    counts2[global_idx] = bc2
            except Exception:
                return None

        if bin_edges_ref is None:
            return None
        return bin_edges_ref, counts1, counts2

    def refine_dmps_with_bmm(
        self,
        dmps_df: pd.DataFrame,
        centroid1_dir: str,
        centroid2_dir: str,
        chromosome: str,
        class1_paths: Optional[List[str]] = None,
        class2_paths: Optional[List[str]] = None,
        contexts: Optional[List[str]] = None,
        bmm_config: Optional[Dict[str, Any]] = None,
        load_validation_samples_fn: Optional[Callable[..., Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]]] = None,
    ) -> Tuple[pd.DataFrame, Optional[MethylBetaMixtureCentroid], Optional[MethylBetaMixtureCentroid], Optional[Dict[Tuple[int, str], Dict[str, Any]]], Optional[Dict[str, Any]]]:
        """
        Refine DMPs using per-position Beta Mixture Models (BMMs).

        Returns:
            (merged_df, bmm_centroid_c1, bmm_centroid_c2, bmm_records_map, bmm_summary)
        """
        if dmps_df is None or dmps_df.empty:
            return dmps_df, None, None, None, None

        cfg = bmm_config or {}
        df = dmps_df.copy()
        if "context" not in df.columns:
            df["context"] = "CG"

        if "bhattacharyya_coefficient" not in df.columns and "overlap" not in df.columns:
            if "bhattacharyya" in df.columns:
                df["bhattacharyya_coefficient"] = np.exp(-np.clip(df["bhattacharyya"].values, 0, 50))

        overlap_col = "bhattacharyya_coefficient" if "bhattacharyya_coefficient" in df.columns else \
            ("overlap" if "overlap" in df.columns else None)

        rank_col = "importance" if "importance" in df.columns else \
            ("effect_size" if "effect_size" in df.columns else "delta_mean")

        df_sorted = df.sort_values(rank_col, ascending=False)
        total_candidates = len(df_sorted)
        max_dmps = min(int(cfg.get("bmm_refine_max_dmps", total_candidates)), total_candidates)
        max_fraction = cfg.get("bmm_refine_max_fraction")
        if max_fraction is not None:
            frac_cap = int(np.ceil(total_candidates * float(max_fraction)))
            if frac_cap > 0:
                max_dmps = min(max_dmps, frac_cap)
        max_dmps = max(1, max_dmps) if total_candidates > 0 else 0
        subset_df = df_sorted.iloc[:max_dmps].copy()
        logger.info(
            f"BMM evaluation cap: {max_dmps:,}/{total_candidates:,} "
            f"(max_dmps={cfg.get('bmm_refine_max_dmps', max_dmps)}, "
            f"max_fraction={max_fraction})"
        )

        use_metadata_samples = bool(cfg.get("bmm_refine_use_metadata_samples", True))
        class1_paths = class1_paths or []
        class2_paths = class2_paths or []
        if not class1_paths and use_metadata_samples:
            class1_paths = self.resolve_validation_samples(
                "use_metadata",
                centroid1_dir,
                chromosome,
                contexts=contexts,
                centroid_name="centroid1",
            )
        if not class2_paths and use_metadata_samples:
            class2_paths = self.resolve_validation_samples(
                "use_metadata",
                centroid2_dir,
                chromosome,
                contexts=contexts,
                centroid_name="centroid2",
            )

        use_binned = bool(cfg.get("bmm_refine_use_binned_stats", True))
        bin_count = cfg.get("bmm_refine_bin_count", 32)
        if bin_count is None:
            n_total = max(len(class1_paths) + len(class2_paths), 1)
            bin_count = int(np.clip(round(np.sqrt(n_total) * 6), 32, 100))
        bin_edges = np.linspace(0.0, 1.0, int(bin_count) + 1, dtype=np.float32)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0

        binned_counts = None
        if use_binned:
            binned_counts = self.load_binned_counts_from_centroids(
                subset_df, centroid1_dir, centroid2_dir, chromosome
            )
            if binned_counts is not None:
                bin_edges, counts1_all, counts2_all = binned_counts
                bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
                bin_count = len(bin_edges) - 1

        if binned_counts is None:
            if not class1_paths or not class2_paths:
                logger.warning("BMM refinement skipped: no validation sample paths available")
                df["bmm_status"] = "skipped_no_samples"
                return df, None, None, None

            max_samples_per_group = int(cfg.get("bmm_refine_max_samples_per_group", 50))
            if len(class1_paths) > max_samples_per_group:
                class1_paths = class1_paths[:max_samples_per_group]
            if len(class2_paths) > max_samples_per_group:
                class2_paths = class2_paths[:max_samples_per_group]

        X = y = None
        if binned_counts is None:
            if load_validation_samples_fn is None:
                logger.warning("BMM refinement skipped: no validation sample loader provided")
                df["bmm_status"] = "skipped_no_loader"
                return df, None, None, None
            val_data = load_validation_samples_fn(subset_df, class1_paths, class2_paths, allow_mock=False)
            if val_data is None:
                logger.warning("BMM refinement skipped: unable to load validation samples")
                df["bmm_status"] = "skipped_load_failed"
                return df, None, None, None
            X, y, val_positions, val_contexts = val_data
            if X.shape[1] != len(subset_df):
                logger.warning("BMM refinement skipped: validation matrix does not align with DMP subset")
                df["bmm_status"] = "skipped_alignment_mismatch"
                return df, None, None, None

        bmm_records = []
        bmm_source = "centroid_bins" if binned_counts is not None else "samples"
        min_samples = int(cfg.get("bmm_refine_min_samples_per_group", 10))
        use_gpu = bool(cfg.get("bmm_refine_use_gpu", True))
        if use_gpu and not self.gpu_available:
            logger.info("BMM GPU requested but not available; using CPU")
            use_gpu = False
        if use_gpu:
            logger.info("BMM GPU acceleration enabled")

        max_components = int(cfg.get("bmm_refine_max_components", 3))
        mc_samples = int(cfg.get("bmm_refine_mc_samples", 200))
        skip_delta = float(cfg.get("bmm_refine_skip_delta_mean", 0.4))
        skip_overlap = float(cfg.get("bmm_refine_skip_overlap", 0.2))
        random_state = cfg.get("random_state")

        for j, row in subset_df.reset_index(drop=False).iterrows():
            pos = int(row["position"])
            ctx = row.get("context", "CG")
            delta_mean = float(row.get("delta_mean", 0.0))
            overlap = float(row[overlap_col]) if overlap_col and np.isfinite(row.get(overlap_col, np.nan)) else None
            if binned_counts is not None:
                counts1 = counts1_all[j]
                counts2 = counts2_all[j]
                n1 = int(np.sum(counts1))
                n2 = int(np.sum(counts2))
            else:
                vals_healthy = X[y == 0, j]
                vals_cancer = X[y == 1, j]
                vals_healthy = vals_healthy[np.isfinite(vals_healthy)]
                vals_cancer = vals_cancer[np.isfinite(vals_cancer)]
                n1 = int(len(vals_healthy))
                n2 = int(len(vals_cancer))

            if n1 < min_samples or n2 < min_samples:
                bmm_records.append({
                    "position": pos,
                    "context": ctx,
                    "k1": 1,
                    "k2": 1,
                    "weights1": [1.0],
                    "alphas1": [],
                    "betas1": [],
                    "weights2": [1.0],
                    "alphas2": [],
                    "betas2": [],
                    "n1": n1,
                    "n2": n2,
                    "bmm_js": np.nan,
                    "bmm_p_value": np.nan,
                    "bmm_llr": np.nan,
                    "bmm_df": np.nan,
                    "bmm_bin_count": int(bin_count),
                    "bmm_source": bmm_source,
                    "status": "skipped_insufficient_samples",
                })
                continue

            if abs(delta_mean) >= skip_delta:
                bmm_records.append({
                    "position": pos,
                    "context": ctx,
                    "k1": 1,
                    "k2": 1,
                    "weights1": [1.0],
                    "alphas1": [],
                    "betas1": [],
                    "weights2": [1.0],
                    "alphas2": [],
                    "betas2": [],
                    "n1": n1,
                    "n2": n2,
                    "bmm_js": np.nan,
                    "bmm_p_value": np.nan,
                    "bmm_llr": np.nan,
                    "bmm_df": np.nan,
                    "bmm_bin_count": int(bin_count),
                    "bmm_source": bmm_source,
                    "status": "skipped_obvious_delta",
                })
                continue
            if overlap is not None and overlap <= skip_overlap:
                bmm_records.append({
                    "position": pos,
                    "context": ctx,
                    "k1": 1,
                    "k2": 1,
                    "weights1": [1.0],
                    "alphas1": [],
                    "betas1": [],
                    "weights2": [1.0],
                    "alphas2": [],
                    "betas2": [],
                    "n1": n1,
                    "n2": n2,
                    "bmm_js": np.nan,
                    "bmm_p_value": np.nan,
                    "bmm_llr": np.nan,
                    "bmm_df": np.nan,
                    "bmm_bin_count": int(bin_count),
                    "bmm_source": bmm_source,
                    "status": "skipped_obvious_overlap",
                })
                continue

            try:
                if binned_counts is not None:
                    fit1 = fit_beta_mixture(
                        bin_centers,
                        weights=counts1,
                        max_components=max_components,
                        random_state=random_state,
                        use_gpu=use_gpu
                    )
                    fit2 = fit_beta_mixture(
                        bin_centers,
                        weights=counts2,
                        max_components=max_components,
                        random_state=random_state,
                        use_gpu=use_gpu
                    )
                    pooled_counts = counts1 + counts2
                    fit0 = fit_beta_mixture(
                        bin_centers,
                        weights=pooled_counts,
                        max_components=max_components,
                        random_state=random_state,
                        use_gpu=use_gpu
                    )
                else:
                    fit1 = fit_beta_mixture(
                        vals_healthy,
                        max_components=max_components,
                        random_state=random_state,
                        use_gpu=use_gpu
                    )
                    fit2 = fit_beta_mixture(
                        vals_cancer,
                        max_components=max_components,
                        random_state=random_state,
                        use_gpu=use_gpu
                    )
                    pooled_vals = np.concatenate([vals_healthy, vals_cancer])
                    fit0 = fit_beta_mixture(
                        pooled_vals,
                        max_components=max_components,
                        random_state=random_state,
                        use_gpu=use_gpu
                    )
            except Exception as e:
                bmm_records.append({
                    "position": pos,
                    "context": ctx,
                    "k1": 1,
                    "k2": 1,
                    "weights1": [],
                    "alphas1": [],
                    "betas1": [],
                    "weights2": [],
                    "alphas2": [],
                    "betas2": [],
                    "n1": n1,
                    "n2": n2,
                    "bmm_js": np.nan,
                    "bmm_p_value": np.nan,
                    "bmm_llr": np.nan,
                    "bmm_df": np.nan,
                    "bmm_bin_count": int(bin_count),
                    "bmm_source": bmm_source,
                    "status": f"error_fit: {e}",
                })
                continue

            js = estimate_js_divergence(
                fit1["weights"], fit1["alphas"], fit1["betas"],
                fit2["weights"], fit2["alphas"], fit2["betas"],
                n_samples=mc_samples,
                random_state=random_state,
                use_gpu=use_gpu
            )

            def _param_count(k):
                return (k - 1) + 2 * k

            ll1 = fit1.get("loglik", np.nan)
            ll2 = fit2.get("loglik", np.nan)
            ll0 = fit0.get("loglik", np.nan)
            if np.isfinite(ll1) and np.isfinite(ll2) and np.isfinite(ll0):
                llr = 2.0 * ((ll1 + ll2) - ll0)
                df_llr = max(_param_count(int(fit1["k"])) + _param_count(int(fit2["k"])) - _param_count(int(fit0["k"])), 1)
                try:
                    from scipy.stats import chi2
                    bmm_p = float(1.0 - chi2.cdf(llr, df_llr)) if llr >= 0 else 1.0
                except Exception:
                    bmm_p = np.nan
            else:
                llr = np.nan
                df_llr = np.nan
                bmm_p = np.nan

            status = "fit"
            bmm_records.append({
                "position": pos,
                "context": ctx,
                "k1": int(fit1["k"]),
                "k2": int(fit2["k"]),
                "weights1": fit1["weights"].tolist(),
                "alphas1": fit1["alphas"].tolist(),
                "betas1": fit1["betas"].tolist(),
                "weights2": fit2["weights"].tolist(),
                "alphas2": fit2["alphas"].tolist(),
                "betas2": fit2["betas"].tolist(),
                "n1": n1,
                "n2": n2,
                "bmm_js": js,
                "bmm_p_value": bmm_p,
                "bmm_llr": llr,
                "bmm_df": df_llr,
                "bmm_bin_count": int(bin_count),
                "bmm_source": bmm_source,
                "status": status,
            })

        mask_df = subset_df[["position", "context"]].copy()
        bmm_records_map = {
            (int(r["position"]), r.get("context", "CG")): r for r in bmm_records
        }

        base_metadata = {
            "chromosome": chromosome,
            "contexts": list(np.unique(subset_df["context"].values)),
            "source": "centroid_pair_bmm_refine",
        }

        records_c1 = [
            {
                "position": r["position"],
                "context": r["context"],
                "k": r["k1"],
                "weights": r["weights1"],
                "alphas": r["alphas1"],
                "betas": r["betas1"],
                "n_samples": r["n1"],
                "converged": True,
                "bic": np.nan,
                "loglik": np.nan,
                "status": r["status"],
            }
            for r in bmm_records
        ]
        records_c2 = [
            {
                "position": r["position"],
                "context": r["context"],
                "k": r["k2"],
                "weights": r["weights2"],
                "alphas": r["alphas2"],
                "betas": r["betas2"],
                "n_samples": r["n2"],
                "converged": True,
                "bic": np.nan,
                "loglik": np.nan,
                "status": r["status"],
            }
            for r in bmm_records
        ]

        bmm_centroid_c1 = MethylBetaMixtureCentroid.from_records(
            records_c1,
            mask=mask_df,
            metadata={**base_metadata, "group": "centroid1", "class_index": 0},
        )
        bmm_centroid_c2 = MethylBetaMixtureCentroid.from_records(
            records_c2,
            mask=mask_df,
            metadata={**base_metadata, "group": "centroid2", "class_index": 1},
        )

        bmm_df = pd.DataFrame(bmm_records)
        merged = df.merge(bmm_df, on=["position", "context"], how="left")
        merged["bmm_status"] = merged["status"].fillna("not_evaluated")
        merged = merged.drop(columns=["status"])

        replace_p = bool(cfg.get("bmm_refine_replace_p_value", False))
        recompute_q = bool(cfg.get("bmm_refine_recompute_q", True))
        replaced_count = 0
        if replace_p and "bmm_p_value" in merged.columns:
            if "p_value_lrt" not in merged.columns:
                merged["p_value_lrt"] = merged["p_value"]
            if "q_value_lrt" not in merged.columns and "q_value" in merged.columns:
                merged["q_value_lrt"] = merged["q_value"]

            fit_mask = (merged["bmm_status"] == "fit") & merged["bmm_p_value"].notna()
            merged.loc[fit_mask, "p_value"] = merged.loc[fit_mask, "bmm_p_value"]
            replaced_count = int(np.sum(fit_mask))

            if recompute_q and "p_value" in merged.columns:
                try:
                    q_vals, _ = storey_qvalues(merged["p_value"].values)
                    merged["q_value"] = q_vals.astype(np.float32)
                except Exception as e:
                    logger.warning(f"Failed to recompute q-values after BMM p-value replace: {e}")

        filtered_out = 0
        if cfg.get("bmm_refine_mode", "annotate") == "filter":
            filter_metric = cfg.get("bmm_refine_filter_metric", "js")
            before_len = len(merged)
            if filter_metric == "p_value" and "bmm_p_value" in merged.columns:
                p = merged["bmm_p_value"]
                keep = (merged["bmm_status"] != "fit") | (p.isna()) | (p <= cfg.get("bmm_refine_pvalue_threshold", 0.05))
                merged = merged[keep].reset_index(drop=True)
            else:
                js = merged["bmm_js"]
                keep = (merged["bmm_status"] != "fit") | (js.isna()) | (js >= cfg.get("bmm_refine_js_threshold", 0.05))
                merged = merged[keep].reset_index(drop=True)
            filtered_out = before_len - len(merged)

        status_counts: Dict[str, int] = {}
        for rec in bmm_records:
            status = rec.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        bmm_summary = {
            "evaluated": int(len(subset_df)),
            "total_candidates": int(total_candidates),
            "source": bmm_source,
            "bin_count": int(bin_count),
            "min_samples": int(min_samples),
            "fit": int(status_counts.get("fit", 0)),
            "skipped_insufficient_samples": int(status_counts.get("skipped_insufficient_samples", 0)),
            "skipped_obvious_delta": int(status_counts.get("skipped_obvious_delta", 0)),
            "skipped_obvious_overlap": int(status_counts.get("skipped_obvious_overlap", 0)),
            "p_value_replaced": int(replaced_count),
            "filtered_out": int(filtered_out),
            "filter_metric": cfg.get("bmm_refine_filter_metric", "js"),
            "filter_pvalue_threshold": float(cfg.get("bmm_refine_pvalue_threshold", 0.05)),
            "filter_js_threshold": float(cfg.get("bmm_refine_js_threshold", 0.05)),
            "max_dmps": int(max_dmps),
            "max_fraction": cfg.get("bmm_refine_max_fraction"),
        }

        return merged, bmm_centroid_c1, bmm_centroid_c2, bmm_records_map, bmm_summary

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
