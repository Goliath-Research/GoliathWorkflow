"""
MethylCentroidPair: ECDF-first comparison of two methylation centroids.

This module owns the low-level per-position comparison used by MethylDetector:
coverage filtering, statistical gating, approximate overlap from bin counts, and
the initial effect-size signal that is later rescored with continuous ECDF overlap.
"""

from typing import Tuple, Dict, Any, List, Union, Optional, Callable
from pathlib import Path

import numpy as np
import pandas as pd

from .beta_mixture import fit_beta_mixture, estimate_js_divergence
from .core.methyl_frame import MethylSample, MethylCentroid
from .gpu_detection import (
    is_gpu_available,
    get_gpu_memory_gb,
    get_gpu_device_count,
    cleanup_gpu_memory,
)
from .memory_manager import get_memory_manager, force_gpu_cleanup
from .metric_validations import validate_methylation_data
from .performance_profiler import (
    get_performance_profiler,
    start_performance_monitoring,
    stop_performance_monitoring,
)
from .statistical_tests import (
    storey_qvalues,
    discrete_overlap_from_bin_counts,
    mann_whitney_from_bin_counts,
    dl_heterogeneity,
    effect_size_from_components,
)
from methyl_utils.logging_utils import setup_module_logging
from .core.methyl_mixture_centroid import MethylBetaMixtureCentroid
logger = setup_module_logging(__name__)

# Type aliases for better type hints
ArrayLike = np.ndarray
DataFrameType = Union[pd.DataFrame, Any]  # Any for cuDF when available


# Constants
BD_CAP = 20.0  # Cap Bhattacharyya Distance to prevent overflow when converting to BC (exp(-20) ≈ 0)

# ECDF is the only supported centroid-comparison distribution.
DIST_ECDF = 5

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
    ('delta_mean', np.float32),           # |mean1 - mean2| — unsigned magnitude
    ('delta_sign', np.int8),              # sign(mean1 - mean2): +1 = hypermethylated in group1, -1 = hypo
    ('bhattacharyya', np.float32),        # Bhattacharyya Distance (BC = exp(-bhattacharyya))
    ('dist', np.uint8),                   # Distribution selection (see DIST_* constants)
    ('n1', np.uint32),
    ('n2', np.uint32),
    ('variance1', np.float32),
    ('variance2', np.float32),
    ('tau2_1', np.float32),               # Between-sample heterogeneity estimate, group 1
    ('tau2_2', np.float32),               # Between-sample heterogeneity estimate, group 2
    ('effect_size', np.float32),          # Initial biological importance (overwritten by continuous ECDF stage)
    ('overlap_approx', np.float32),       # Discrete overlap from bin counts (NaN when binned_stats not available)
])


class MethylCentroidPair:
    """
    ECDF-first mathematical comparison engine for two methylation centroids.

    The runtime path is intentionally narrow:
    - centroids must provide matching `binned_stats`
    - overlap approximation comes from discrete bin-count overlap
    - the statistical gate defaults to histogram-derived Mann-Whitney
    - the returned `effect_size` is an approximate, pre-ECDF score

    MethylDetector later recomputes the final overlap/effect_size on the reduced
    DMP set using continuous ECDF views.
    """

    def __init__(
        self,
        centroid1: Optional[MethylCentroid] = None,
        centroid2: Optional[MethylCentroid] = None,
        min_coverage: int = 4,
        ecdf_ks_grid_size: int = 256,
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
        self.ecdf_ks_grid_size = int(ecdf_ks_grid_size)

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

        # Validate centroids (assume is_centroid checks N, Sx, etc.)
        if not centroid1.is_centroid or not centroid2.is_centroid:
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

        # Clamp zero-coverage (avoids div-by-zero in comparisons)
        for cent in [aligned1, aligned2]:
            n_clamped = cent.clamp_zero_coverage()
            if n_clamped > 0:
                logger.debug(f"Clamped {n_clamped} zero-coverage positions in centroid")

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
        if not centroid1.is_centroid or not centroid2.is_centroid:
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

        # Clamp zero-coverage (avoids div-by-zero in comparisons)
        for cent in [aligned1, aligned2]:
            n_clamped = cent.clamp_zero_coverage()
            if n_clamped > 0:
                logger.debug(f"Clamped {n_clamped} zero-coverage positions in centroid")

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
    ) -> MethylCentroid:
        """
        Create an empty extended centroid for use as a reference/alignment template.

        Args:
            positions: Genomic positions to include
            context: Methylation context (CG, CHG, CHH)
            min_coverage: Minimum coverage threshold

        Returns:
            MethylCentroid with zero-filled data
        """
        from methyl_utils.core.methyl_frame import MethylCentroid
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
            "uC": np.ones(n_positions, dtype=np.uint32) * min_coverage,
            "tnc": dummy_tnc,
            "N": np.ones(n_positions, dtype=np.uint32),
            "Sx": np.zeros(n_positions, dtype=np.float32),
            "Sx2": np.zeros(n_positions, dtype=np.float32),
        })
        return MethylCentroid(df, metadata={"context": context})

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
        # Use reference_positions key order so column order matches caller's DMP/centroid list
        # (e.g. detector uses np.unique(dmp_contexts) → same order as config.contexts).
        all_positions = []
        all_contexts = []
        position_to_index = {}  # (pos, ctx) -> column index
        context_indices_dict = {}
        
        for ctx in reference_positions.keys():
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
                    sample = load_from_h5(h5_file, positions=ctx_positions)
                    
                    if len(sample) == 0:
                        n_empty_align += 1
                        continue

                    # Extract methylation fractions efficiently
                    mC_vals = sample.mC.values if hasattr(sample.mC, 'values') else np.asarray(sample.mC)
                    uC_vals = sample.uC.values if hasattr(sample.uC, 'values') else np.asarray(sample.uC)
                    pos_vals = sample.pos.values if hasattr(sample.pos, 'values') else np.asarray(sample.pos)
                    
                    # Calculate methylation fractions
                    total_reads = mC_vals + uC_vals
                    with np.errstate(divide='ignore', invalid='ignore'):
                        meth_fractions = np.where(total_reads >= min_coverage, mC_vals / total_reads, np.nan)
                    
                    mapped_indices = np.asarray(
                        [position_to_index.get((int(pos), ctx), -1) for pos in pos_vals],
                        dtype=np.int64,
                    )
                    valid = mapped_indices >= 0
                    if np.any(valid):
                        X[i, mapped_indices[valid]] = meth_fractions[valid]
                            
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

    def compare_centroids(
        self,
        centroid1: MethylSample,
        centroid2: MethylSample,
        position_subset: Optional[np.ndarray] = None,
    ) -> pd.DataFrame:
        """
        Compare two centroids and return statistical results as DataFrame.

        Args:
            centroid1: First methylation centroid (extended centroid required).
            centroid2: Second methylation centroid (extended centroid required).
            position_subset: Optional array of genomic positions to restrict the
                comparison to.  Must be a sorted subset of the positions common to
                both centroids.  When provided the statistical test, FDR correction,
                and all downstream stages run only on these positions.  Pass this to
                avoid computing the expensive statistical gate on positions that are certain
                to fail the downstream biological filter (e.g. all positions with
                |delta_mean| < threshold).

        Returns:
            pandas DataFrame with columns: position, p_value, q_value,
            alpha1, beta1, alpha2, beta2, mean1, mean2, delta_mean,
            overlap_approx, tau2_1, tau2_2, and effect_size.
        """
        start_performance_monitoring()

        try:
            # Validate inputs
            self._validate_centroids(centroid1, centroid2)

            # Align centroids (find common positions)
            common_positions = self._align_centroids(centroid1, centroid2)

            # Optional early reduction: restrict to caller-provided position subset
            if position_subset is not None and len(position_subset) > 0:
                common_positions = np.intersect1d(common_positions, position_subset)
                logger.info(
                    f"Position subset applied: {len(common_positions):,} positions "
                    f"(from {len(position_subset):,} requested)"
                )

            if len(common_positions) == 0:
                logger.warning("No common positions found between centroids")
                return pd.DataFrame()  # Empty DataFrame

            logger.info(
                "Comparing centroids at %s common positions using histogram-derived Mann-Whitney U",
                f"{len(common_positions):,}",
            )

            # Perform statistical analysis and overlap approximation.
            results_array = self._compute_statistics(centroid1, centroid2, common_positions)

            # Apply FDR correction
            results_array = self._apply_fdr_correction(results_array)

            logger.info(f"Comparison complete: {len(results_array)} positions analyzed")

            # Always return as DataFrame
            return pd.DataFrame(results_array)

        finally:
            stop_performance_monitoring()

    def _validate_centroids(self, centroid1: MethylSample, centroid2: MethylSample) -> None:
        """Validate that centroids are suitable for comparison."""
        if not (centroid1.is_centroid and centroid2.is_centroid):
            raise ValueError(
                "MethylCentroidPair requires extended centroids. "
                f"Centroid1 is_centroid: {centroid1.is_centroid}, "
                f"Centroid2 is_centroid: {centroid2.is_centroid}"
            )

        # Use MethylUtils validation on the methylation proportions
        # MethylSample.mean contains the proper methylation proportions (0-1)
        validate_methylation_data(centroid1.mean, centroid1.N)
        validate_methylation_data(centroid2.mean, centroid2.N)

        binned1 = centroid1.binned_stats
        binned2 = centroid2.binned_stats
        if not binned1 or "bin_edges" not in binned1 or "bin_counts" not in binned1:
            raise ValueError(
                "MethylCentroidPair requires centroid1 with binned_stats (bin_edges, bin_counts)"
            )
        if not binned2 or "bin_edges" not in binned2 or "bin_counts" not in binned2:
            raise ValueError(
                "MethylCentroidPair requires centroid2 with binned_stats (bin_edges, bin_counts)"
            )
        edges1 = np.asarray(binned1["bin_edges"], dtype=np.float64)
        edges2 = np.asarray(binned2["bin_edges"], dtype=np.float64)
        if edges1.shape != edges2.shape or not np.allclose(edges1, edges2):
            raise ValueError(
                "MethylCentroidPair requires matching ECDF bin_edges in both centroids"
            )

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
        elif hasattr(centroid1, "coverage") and hasattr(centroid2, "coverage"):
            # Fallback: filter by total coverage (e.g. c.coverage >= min_coverage)
            c1_mask = np.isin(pos1_vals, common_positions)
            c2_mask = np.isin(pos2_vals, common_positions)
            cov1 = centroid1.coverage.values if hasattr(centroid1.coverage, "values") else np.asarray(centroid1.coverage)
            cov2 = centroid2.coverage.values if hasattr(centroid2.coverage, "values") else np.asarray(centroid2.coverage)
            c1_coverage = cov1[c1_mask]
            c2_coverage = cov2[c2_mask]
            coverage_mask = (c1_coverage >= self.min_coverage) & (c2_coverage >= self.min_coverage)
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
            data_structure="centroid",
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
        """Process a batch of positions using the ECDF-only centroid comparison path."""

        pos1 = np.asarray(centroid1.pos.values, dtype=np.uint32)
        pos2 = np.asarray(centroid2.pos.values, dtype=np.uint32)
        indices1 = np.searchsorted(pos1, positions)
        indices2 = np.searchsorted(pos2, positions)

        alpha1_all = np.asarray(centroid1.alpha, dtype=np.float64)
        beta1_all = np.asarray(centroid1.beta, dtype=np.float64)
        alpha2_all = np.asarray(centroid2.alpha, dtype=np.float64)
        beta2_all = np.asarray(centroid2.beta, dtype=np.float64)
        N1_all = np.asarray(centroid1.N, dtype=np.float64)
        N2_all = np.asarray(centroid2.N, dtype=np.float64)
        Sx1_all = np.asarray(centroid1.Sx, dtype=np.float64)
        Sx2_all = np.asarray(centroid2.Sx, dtype=np.float64)
        Sx2_1_all = np.asarray(centroid1.Sx2, dtype=np.float64)
        Sx2_2_all = np.asarray(centroid2.Sx2, dtype=np.float64)
        Sm1_all = np.asarray(centroid1.Sm, dtype=np.float64)
        Su1_all = np.asarray(centroid1.Su, dtype=np.float64)
        Swx2_1_all = np.asarray(centroid1.Swx2, dtype=np.float64)
        Sc2_1_all = np.asarray(centroid1.Sc2, dtype=np.float64)
        Sm2_all = np.asarray(centroid2.Sm, dtype=np.float64)
        Su2_all = np.asarray(centroid2.Su, dtype=np.float64)
        Swx2_2_all = np.asarray(centroid2.Swx2, dtype=np.float64)
        Sc2_2_all = np.asarray(centroid2.Sc2, dtype=np.float64)
        mean1_all = np.asarray(centroid1.mean, dtype=np.float64)
        mean2_all = np.asarray(centroid2.mean, dtype=np.float64)

        alpha1 = alpha1_all[indices1]
        beta1 = beta1_all[indices1]
        alpha2 = alpha2_all[indices2]
        beta2 = beta2_all[indices2]
        N1 = N1_all[indices1]
        N2 = N2_all[indices2]
        Sx1 = Sx1_all[indices1]
        Sx2_vals = Sx2_all[indices2]
        Sx2_1 = Sx2_1_all[indices1]
        Sx2_2 = Sx2_2_all[indices2]
        Sm1 = Sm1_all[indices1]
        Su1 = Su1_all[indices1]
        Swx2_1 = Swx2_1_all[indices1]
        Sc2_1 = Sc2_1_all[indices1]
        Sm2 = Sm2_all[indices2]
        Su2 = Su2_all[indices2]
        Swx2_2 = Swx2_2_all[indices2]
        Sc2_2 = Sc2_2_all[indices2]
        mean1 = mean1_all[indices1]
        mean2 = mean2_all[indices2]

        variance1 = np.maximum(
            (Sx2_1 - (Sx1 ** 2) / np.maximum(N1, 1.0)) / np.maximum(N1 - 1.0, 1.0),
            1e-12,
        )
        variance2 = np.maximum(
            (Sx2_2 - (Sx2_vals ** 2) / np.maximum(N2, 1.0)) / np.maximum(N2 - 1.0, 1.0),
            1e-12,
        )

        bs1 = centroid1.binned_stats
        bs2 = centroid2.binned_stats
        bc1_batch = np.asarray(bs1["bin_counts"], dtype=np.float64)[indices1]
        bc2_batch = np.asarray(bs2["bin_counts"], dtype=np.float64)[indices2]
        bin_edges = np.asarray(bs1["bin_edges"], dtype=np.float64)
        
        from .statistical_tests import ecdf_bhattacharyya_trapezoidal_from_bin_counts
        
        overlap_approx = np.asarray(
            ecdf_bhattacharyya_trapezoidal_from_bin_counts(
                bc1_batch, bc2_batch, bin_edges, grid_size=256, use_gpu=self.gpu_available
            ),
            dtype=np.float64,
        )
        overlap_safe = np.clip(overlap_approx, 1e-10, 1.0)
        bhattacharyya = (-np.log(overlap_safe)).astype(np.float32)

        signed_delta = mean1 - mean2
        delta_mean = np.abs(signed_delta)

        stat_result = mann_whitney_from_bin_counts(
            bc1_batch,
            bc2_batch,
            n1=N1,
            n2=N2,
        )
        p_values = np.asarray(stat_result["p_value"], dtype=np.float32)

        tau2_1 = dl_heterogeneity(
            Sm=Sm1,
            Su=Su1,
            Swx2=Swx2_1,
            Sc2=Sc2_1,
            N=N1,
        )["tau2"]
        tau2_2 = dl_heterogeneity(
            Sm=Sm2,
            Su=Su2,
            Swx2=Swx2_2,
            Sc2=Sc2_2,
            N=N2,
        )["tau2"]

        effect_size = effect_size_from_components(
            delta_mean=delta_mean,
            overlap=overlap_safe,
            var1=variance1,
            var2=variance2,
            lambda_var=2.0,
        )["effect_size"]

        pos_safe = np.nan_to_num(
            np.asarray(positions, dtype=np.float64),
            nan=0,
            posinf=0,
            neginf=0,
        )
        results_view["position"] = np.clip(
            pos_safe, 0, np.iinfo(np.uint32).max
        ).astype(np.uint32)
        results_view["p_value"] = p_values
        results_view["q_value"] = p_values
        results_view["alpha1"] = alpha1.astype(np.float64)
        results_view["beta1"] = beta1.astype(np.float64)
        results_view["alpha2"] = alpha2.astype(np.float64)
        results_view["beta2"] = beta2.astype(np.float64)
        results_view["mean1"] = mean1.astype(np.float32)
        results_view["mean2"] = mean2.astype(np.float32)
        results_view["delta_mean"] = delta_mean.astype(np.float32)
        results_view["delta_sign"] = np.sign(signed_delta).astype(np.int8)
        results_view["bhattacharyya"] = bhattacharyya
        results_view["dist"] = np.full(len(positions), DIST_ECDF, dtype=np.uint8)
        results_view["n1"] = np.clip(N1, 0, np.iinfo(np.uint32).max).astype(np.uint32)
        results_view["n2"] = np.clip(N2, 0, np.iinfo(np.uint32).max).astype(np.uint32)
        results_view["variance1"] = variance1.astype(np.float32)
        results_view["variance2"] = variance2.astype(np.float32)
        results_view["tau2_1"] = np.asarray(tau2_1, dtype=np.float32)
        results_view["tau2_2"] = np.asarray(tau2_2, dtype=np.float32)
        results_view["effect_size"] = np.asarray(effect_size, dtype=np.float32)
        results_view["overlap_approx"] = overlap_approx.astype(np.float32)

    def _apply_fdr_correction(self, results_array: np.ndarray) -> np.ndarray:
        """Apply two-stage BH FDR correction, with Storey fallback if unavailable."""
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
        Return basic centroid statistics (no distribution validation).
        Correct group classification is checked by the classifier centroid self-check
        when running the pipeline.
        """
        if not centroid1.is_centroid or not centroid2.is_centroid:
            return {"error": "Both centroids must be extended centroids"}

        try:
            centroid1, centroid2, common_pos = MethylCentroidPair.load_and_align_from_samples(centroid1, centroid2)
        except ValueError as e:
            return {"error": f"Failed to align centroids: {e}"}

        N1, N2 = centroid1.N, centroid2.N
        mean1 = np.asarray(centroid1.mean, dtype=np.float64)
        mean2 = np.asarray(centroid2.mean, dtype=np.float64)
        # Per-position variance: (Sx2 - Sx²/N) / (N-1)
        Sx1, Sx2_1 = np.asarray(centroid1.Sx.values, dtype=np.float64), np.asarray(centroid1.Sx2.values, dtype=np.float64)
        Sx2, Sx2_2 = np.asarray(centroid2.Sx.values, dtype=np.float64), np.asarray(centroid2.Sx2.values, dtype=np.float64)
        var1 = np.maximum((Sx2_1 - (Sx1 ** 2) / np.maximum(N1, 1)) / np.maximum(N1 - 1, 1), 1e-12)
        var2 = np.maximum((Sx2_2 - (Sx2 ** 2) / np.maximum(N2, 1)) / np.maximum(N2 - 1, 1), 1e-12)
        has_ecdf1 = bool(centroid1.binned_stats and "bin_edges" in centroid1.binned_stats and "bin_counts" in centroid1.binned_stats)
        has_ecdf2 = bool(centroid2.binned_stats and "bin_edges" in centroid2.binned_stats and "bin_counts" in centroid2.binned_stats)

        position_diffs = np.abs(mean1 - mean2)
        n_positions = len(position_diffs)
        trim_bottom = int(0.10 * n_positions)
        if trim_bottom < n_positions:
            sorted_diffs = np.sort(position_diffs)
            trimmed_mean_diff = float(np.mean(sorted_diffs[trim_bottom:]))
        else:
            trimmed_mean_diff = float(np.abs(mean1.mean() - mean2.mean()))

        return {
            "centroid1": {
                "n_positions": len(mean1),
                "mean_median": float(np.median(mean1)),
                "mean_mean": float(np.mean(mean1)),
                "variance_median": float(np.median(var1)),
                "variance_mean": float(np.mean(var1)),
                "sample_stats": {"min_N": int(N1.min()), "max_N": int(N1.max()), "mean_N": float(N1.mean()), "std_N": float(N1.std())},
                "has_ecdf": has_ecdf1,
            },
            "centroid2": {
                "n_positions": len(mean2),
                "mean_median": float(np.median(mean2)),
                "mean_mean": float(np.mean(mean2)),
                "variance_median": float(np.median(var2)),
                "variance_mean": float(np.mean(var2)),
                "sample_stats": {"min_N": int(N2.min()), "max_N": int(N2.max()), "mean_N": float(N2.mean()), "std_N": float(N2.std())},
                "has_ecdf": has_ecdf2,
            },
            "group_separation": trimmed_mean_diff,
            "separation_stats": {
                "mean_diff": float(np.mean(position_diffs)),
                "median_diff": float(np.median(position_diffs)),
                "min_diff": float(np.min(position_diffs)),
                "max_diff": float(np.max(position_diffs)),
            },
        }

    def compute_effect_sizes(
        self,
        alpha1: np.ndarray,
        beta1: np.ndarray,
        alpha2: np.ndarray,
        beta2: np.ndarray,
        delta_mean: np.ndarray,
        bc_values: np.ndarray,
        min_overlap_floor: float = 0.01,
        variance_reliability: bool = True,
    ) -> np.ndarray:
        """Compute the canonical effect_size from overlap and separate variances."""
        bc_safe = np.maximum(bc_values.astype(np.float64), min_overlap_floor)
        return self.compute_effect_sizes_altA(
            alpha1, beta1, alpha2, beta2,
            delta_mean.astype(np.float64),
            bc_safe,
            variance_reliability=variance_reliability,
        )

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
        """Legacy entry point redirected to the canonical effect_size formula."""
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

        bc_safe = np.clip(np.nan_to_num(bc_values, nan=bc_nan_fill), 0.0, 1.0)
        lambda_var = 2.0 if variance_reliability else 0.0
        effect_sizes = effect_size_from_components(
            delta_mean=delta_mean,
            overlap=bc_safe,
            var1=var1,
            var2=var2,
            lambda_var=lambda_var,
        )["effect_size"]
        effect_sizes = np.nan_to_num(effect_sizes, nan=0.0, posinf=0.0, neginf=0.0)
        return np.asarray(effect_sizes, dtype=np.float32)

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
                    md1 = f1.get("methylation_data")
                    md2 = f2.get("methylation_data")
                    if not (isinstance(md1, h5py.Group) and isinstance(md2, h5py.Group)):
                        return None
                    if "bins" not in md1.attrs or "bin_counts" not in md1 or "bins" not in md2.attrs or "bin_counts" not in md2:
                        return None
                    bins1 = int(md1.attrs["bins"])
                    bins2 = int(md2.attrs["bins"])
                    if bins1 != bins2 or bins1 <= 0:
                        logger.warning(f"Binned bins mismatch for context {ctx}; falling back to samples")
                        return None
                    n_bins = bins1
                    if bin_edges_ref is None:
                        bin_edges_ref = np.linspace(0, 1, n_bins + 1, dtype=np.float64)
                        counts1 = np.zeros((len(dmps_df), n_bins), dtype=np.int32)
                        counts2 = np.zeros((len(dmps_df), n_bins), dtype=np.int32)
                    else:
                        if n_bins != len(bin_edges_ref) - 1:
                            logger.warning(f"Binned bins mismatch for context {ctx}; falling back to samples")
                            return None

                    pos1 = np.asarray(md1["pos"][:], dtype=np.uint32)
                    pos2 = np.asarray(md2["pos"][:], dtype=np.uint32)
                    idx1 = np.searchsorted(pos1, ctx_positions)
                    idx2 = np.searchsorted(pos2, ctx_positions)
                    valid1 = (idx1 < len(pos1)) & (pos1[idx1] == ctx_positions)
                    valid2 = (idx2 < len(pos2)) & (pos2[idx2] == ctx_positions)
                    valid = valid1 & valid2
                    if not np.any(valid):
                        continue

                    bc1 = np.asarray(md1["bin_counts"][idx1[valid]])
                    bc2 = np.asarray(md2["bin_counts"][idx2[valid]])
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

    def cleanup(self):
        """Clean up resources."""
        if self.gpu_available:
            force_gpu_cleanup()
            cleanup_gpu_memory()
        logger.info("MethylCentroidPair cleanup completed")
