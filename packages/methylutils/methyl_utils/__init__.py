"""
MethylUtils - Advanced Genome-Scale Methylation Analysis

A comprehensive Python package for high-performance methylation data analysis,
optimized for processing human genomes with billions of positions on NVIDIA GH200 hardware.

The package is organized into specialized modules:

Core Analysis Modules:
- metrics_core: Core metric computation functions for Beta distributions
- metrics_factory: Factory pattern for metric management and dispatch
- statistical_tests: Statistical testing functions (FDR correction, meta-analysis)
- genomic_utils: Genomic utility functions (region grouping, position manipulation)

Performance Optimization Modules:
- memory_manager: Advanced memory management for genome-scale processing
- chunked_processor: Intelligent chunking for large genomic datasets
- performance_profiler: Real-time monitoring and bottleneck analysis

Infrastructure Modules:
- gpu_detection: Comprehensive GPU detection and capability assessment
- gpu_utils: GPU/CPU backend utilities and array management
- logging_utils: Centralized logging configuration and utilities
- metric_validations: Input validation functions for all metric computations

Integrated Components:
- position_aligner: Genomic Position Aligner for sample alignment
- models: Pydantic models for structured methylation analysis results
- methyl_sample: Core methylation data structures with HDF5 support
- probabilistic_beta_classifier: Bayesian classifier using Beta distributions for sample classification

Key Features:
- 🚀 Automatic GPU acceleration (NVIDIA GH200 optimized with 96GB memory)
- 🧬 Genome-scale processing (handles 3B+ positions efficiently)
- 📊 Advanced statistical metrics (7 distance measures for Beta distributions)
- 🧠 Intelligent memory management (chunking, memory mapping, pooling)
- ⚡ Parallel processing (multi-threaded I/O, multiprocessing)
- 📈 Real-time performance monitoring and optimization
- 🐳 Container-ready with dependency fallbacks
- 🔧 Factory pattern for extensible metric computation
- ✅ Comprehensive input validation and error handling
- 💾 Memory-efficient operations with in-place computations
- 🔒 Type-safe interfaces with full type hints

Performance Targets:
- Processing Speed: >1M positions/second on GH200
- Memory Efficiency: <80% GPU memory utilization
- I/O Throughput: >500MB/s read/write
- Human Genome Processing: ~4 hours on GH200

Usage Examples:
    # Basic usage
    from methyl_utils import auto_compute_distance  # PositionAligner deprecated

    # Genome-scale processing
    from methyl_utils import ChunkedGenomicProcessor, process_genome_file_chunked

    # Performance monitoring
    from methyl_utils import start_performance_monitoring, get_performance_report

For detailed documentation, see documentation.html
"""

from .gpu_detection import (
    is_gpu_available,
    is_cupy_available,
    is_cudf_available,
    is_cupyx_scipy_available,
    is_cupyx_scipy_integrate_available,
    is_cupyx_scipy_special_available,
    is_cupyx_scipy_stats_available,
    get_gpu_memory_gb,
    get_gpu_device_count,
    get_gpu_state,
    get_gpu_error_message,
    get_cupy,
    cleanup_gpu_memory,
    reset_gpu_state,
    print_gpu_status,
    get_gpu_capabilities,
    create_gpu_array,
    to_cpu_array,
    get_memory_info,
    compare_implementations
)

from .logging_utils import (
    setup_logging,
    setup_module_logging,
    get_logger,
    PerformanceLogger
)

from .core.methyl_frame import (
    MethylFrame,
    MethylSample,
    MethylExtendedCentroid,
    compute_coverage_outlier_flags,
)
MethylCentroid = MethylExtendedCentroid
MethylBetaCentroid = MethylExtendedCentroid

# Import I/O functions
from .core.io import (
    load_from_h5,
    load_pos_from_h5,
    estimate_n_cap_from_sample_path,
    estimate_n_cap_from_sample_path_with_log,
)

# Legacy exports from old methyl_sample.py (for backward compatibility during migration)
# Legacy imports - these are now defined directly below
# try:
#     from .methyl_sample import (
#         TNCBits,
#         METHYL_SAMPLE_DTYPE,
#         METHYL_CENTROID_DTYPE,
#         METHYL_EXTENDED_CENTROID_DTYPE,
#         MethylSampleDtype,
#         MethylCentroidDtype,
#         MethylExtendedCentroidDtype,
#         get_methyl_dtype,
#         DMPSample,
#         DMPExporter,
#         DMRExporter,
#     )
# except ImportError:
#     # All definitions are now provided directly below
#     pass

# Define dtypes and classes that were previously in methyl_sample.py
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union, Tuple, Dict, Any, List
import numpy as np

# Import HDF5 dependencies - these should be available in the container
try:
    import hdf5plugin   # noqa: F401 - Must be imported before h5py
    import h5py
    HDF5_AVAILABLE = True
except ImportError:
    HDF5_AVAILABLE = False
    h5py = None
    hdf5plugin = None

# ---------- Bit layout (LSB-first) ----------
# Byte layout: bits 0..4 = tnc (5 bits), bits 5..6 = context (2 bits), bit 7 = strand (1 bit)
TNC_MASK     = 0b1_1111      # 5 bits
CONTEXT_MASK = 0b11          # 2 bits
STRAND_MASK  = 0b1           # 1 bit
CONTEXT_SHIFT = 5
STRAND_SHIFT  = 7

# ---------- Context Constants ----------
CONTEXT_CG = 0
CONTEXT_CHG = 1
CONTEXT_CHH = 2
CONTEXT_UNKNOWN = 3

CONTEXT_NAMES = {
    CONTEXT_CG: 'CG',
    CONTEXT_CHG: 'CHG',
    CONTEXT_CHH: 'CHH',
    CONTEXT_UNKNOWN: 'UNKNOWN'
}

STRAND_POSITIVE = 0
STRAND_NEGATIVE = 1

STRAND_SYMBOLS = {
    STRAND_POSITIVE: '+',
    STRAND_NEGATIVE: '-'
}

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

# Single data-driven centroid dtype (pos, mC, uC, tnc, N, Sx, Sx2 only)
METHYL_CENTROID_DTYPE_EXTENDED = [
    ("pos", np.uint32),
    ("mC", np.uint32),
    ("uC", np.uint32),
    ("tnc", np.uint8),
    ("N", np.uint32),
    ("Sx", np.float32),
    ("Sx2", np.float32),
]
# Backward-compat alias
METHYL_EXTENDED_ONLY_DTYPE = METHYL_CENTROID_DTYPE_EXTENDED

# Type aliases for better type hints (compatible with older Python versions)
MethylSampleDtype = np.ndarray
MethylCentroidDtype = np.ndarray
MethylExtendedCentroidDtype = np.ndarray

def get_methyl_dtype(extended: bool = False) -> list:
    """
    Get the appropriate methylation dtype (sample or centroid).

    Args:
        extended: If True, return centroid dtype with N, Sx, Sx2

    Returns:
        List of (field_name, dtype) tuples for numpy structured array
    """
    if extended:
        return METHYL_CENTROID_DTYPE_EXTENDED
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

# TNC nucleotide encoding constants (matching C code)
TNC_A = 0
TNC_C = 1
TNC_G = 2
TNC_T = 3
TNC_N = 4

def encode_nucleotide(n: str) -> int:
    """Encode a nucleotide character to TNC value (matching C code)."""
    n = n.upper()
    if n == 'A':
        return TNC_A
    elif n == 'C':
        return TNC_C
    elif n == 'G':
        return TNC_G
    elif n == 'T':
        return TNC_T
    else:
        return TNC_N

def decode_nucleotide(n: int) -> str:
    """Decode a TNC value to nucleotide character (matching C code)."""
    if n == TNC_A:
        return 'A'
    elif n == TNC_C:
        return 'C'
    elif n == TNC_G:
        return 'G'
    elif n == TNC_T:
        return 'T'
    else:
        return 'N'

@dataclass(slots=True)
class TNCBits:
    """Holds the 3 bitfields and knows how to pack/unpack to a single byte."""
    tnc: int       # 0..31 - trinucleotide code
    context: int   # 0..3 - context (CG=0, CHG=1, CHH=2, UNKNOWN=3)
    strand: int    # 0..1 - strand (positive=0, negative=1)

    def to_byte(self) -> int:
        """Pack the bitfields into a single byte."""
        return _pack_tnc_byte(self.tnc, self.context, self.strand)

    @classmethod
    def from_byte(cls, b: int) -> "TNCBits":
        """Unpack a byte into TNC bitfields."""
        tnc, context, strand = _unpack_tnc_byte(b)
        return cls(tnc=tnc, context=context, strand=strand)

    # ---------- Properties for easier access ----------

    @property
    def context_name(self) -> str:
        """Get the context as a human-readable string ('CG', 'CHG', 'CHH', 'UNKNOWN')."""
        return CONTEXT_NAMES.get(self.context, 'UNKNOWN')

    @property
    def strand_symbol(self) -> str:
        """Get the strand as a symbol ('+' or '-')."""
        return STRAND_SYMBOLS.get(self.strand, '?')

    @property
    def trinucleotide(self) -> str:
        """Get the trinucleotide sequence (e.g., 'CCG', 'CHG', 'CHH')."""
        return self.decode_trinucleotide()

    @property
    def nucleotide_2(self) -> str:
        """Get the second nucleotide in the trinucleotide."""
        n2 = (self.tnc // 5) % 4  # 0-3
        return decode_nucleotide(n2)

    @property
    def nucleotide_3(self) -> str:
        """Get the third nucleotide in the trinucleotide."""
        n3 = self.tnc % 5  # 0-4
        return decode_nucleotide(n3)

    # ---------- Methods ----------

    def decode_trinucleotide(self) -> str:
        """
        Decode the trinucleotide context from the TNC value.

        Returns trinucleotides of the form C[N2][N3] where C is the methylated cytosine.
        """
        return f"C{self.nucleotide_2}{self.nucleotide_3}"

    def encode_trinucleotide(self, trinuc: str) -> None:
        """
        Encode a trinucleotide string to TNC value.

        Expects trinucleotides of the form C[N2][N3].
        """
        if len(trinuc) != 3 or trinuc[0].upper() != 'C':
            raise ValueError(f"Invalid trinucleotide format: {trinuc}. Expected C[N2][N3]")

        n2 = encode_nucleotide(trinuc[1])
        n3 = encode_nucleotide(trinuc[2])

        if n2 > 3:
            raise ValueError(f"Invalid second nucleotide: {trinuc[1]}")

        self.tnc = n2 * 5 + n3  # tnc = n2 * 5 + n3

    def __str__(self) -> str:
        """String representation showing all decoded information."""
        return f"TNCBits(tnc={self.tnc}, context={self.context_name}, strand={self.strand_symbol}, trinuc={self.trinucleotide})"

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
            data["tnc"] = 0  # Default tnc value

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
# Note: MethylSample utility properties (position_count, memory_usage_mb, bytes_per_position,
# coverage_stats, methylation_stats) are available as instance properties

# Import from new modular architecture
from .metrics_core import (
    DistanceCalculator,
    compute_jeffreys_divergence,
    compute_beta_llr_moments,
    compute_distribution_overlap,
    compute_kl_divergence,
    compute_bhattacharyya_distance,
    compute_hellinger_distance,
    compute_wasserstein_distance,
    compute_jensen_shannon_distance,
    compute_weighted_jensen_shannon_distance,
    compute_entropy,
    compute_sample_centroid_jsd,
    get_sample_beta_mom
)

from .metrics_factory import (
    MetricFactory,
    get_metric_factory,
    auto_compute_distance
)

from .statistical_tests import (
    storey_qvalues,
    stouffer_global_p,
    beta_loglikelihood,
    beta_mle_estimation,
    beta_mom_estimation,
    likelihood_ratio_test_beta,
    aggregate_pvalues_fisher,
    aggregate_pvalues_stouffer,
    aggregate_pvalues_lancaster,
    aggregate_pvalues_tippett,
    aggregate_pvalues_edgington,
    aggregate_pvalues_mudholkar_george,
    aggregate_pvalues_simes,
    PVALUE_AGGREGATION_METHODS,
    discrete_overlap_from_bin_counts,
    welch_d_fast_overlap_approx,
    welch_d_ks_overlap,
)

from .genomic_utils import (
    group_significant_positions
)

# Import utility modules for advanced usage
from .gpu_utils import (
    _prepare_arrays_for_backend,
    _ensure_cpu_output
)

from .metric_validations import (
    validate_beta_parameters,
    validate_array_shapes,
    validate_methylation_data,
    validate_weights,
    validate_sample_data
)

# Import Phase 2: Performance Optimization components
from .memory_manager import (
    MemoryManager,
    get_memory_manager,
    memory_usage_monitor,
    check_memory_limits,
    get_memory_usage,
    force_gpu_cleanup,
    create_shared_memory_array,
    attach_shared_memory_array,
    cleanup_shared_memory_array,
    is_shared_memory_array
)

from .chunked_processor import (
    ChunkedGenomicProcessor,
    ChunkInfo,
    ProcessingResult,
    process_genome_file_chunked,
    create_genome_statistics_processor
)


from .performance_profiler import (
    PerformanceProfiler,
    PerformanceMetrics,
    get_performance_profiler,
    start_performance_monitoring,
    stop_performance_monitoring,
    get_performance_report,
    profile_performance
)

# PositionAligner has been deprecated - use MethylExtendedCentroid.add_sample()/remove_sample() instead
# from .position_aligner import PositionAligner, align_multiple_samples
from .models import (
    PositionMethylationStats,
    GroupMethylationStats,
    AlignmentStats,
    MethylationAnalysisResults,
    create_analysis_results
)

# Import Beta-Binomial Classifier (for multi-context analysis)
from .beta_binomial_classifier import BetaBinomialClassifier

# Import MethylCentroidPair for centroid comparison
from .methyl_centroid_pair import MethylCentroidPair

# Import Bayesian Classifier Trainer
from .bayesian_classifier_trainer import (
    BayesianClassifierTrainer,
    FilterConfig,
    train_classifier_from_centroids
)

# Import Beta Analytics (improved algorithm functions)
from .beta_analytics import (
    compute_per_site_llr_stats,
    compute_precision_weighted_score,
    compute_bhattacharyya_coefficient,
    beta_log_pdf,
    compute_beta_mean,
    compute_beta_variance,
    log_beta_binomial_pmf,
)

from .beta_classifier import BetaClassifier

# Beta Mixture Model utilities
from .beta_mixture import (
    fit_beta_mixture,
    estimate_js_divergence,
    mixture_logpdf,
)

# Backward compatibility
from .beta_classifier import ProbabilisticBetaClassifier
from .multi_class_beta_classifier import MultiClassBetaMixtureClassifier

# Import EAT (Entropy-weighted Asymmetry Transformation) functions
from .transformations import (
    compute_eat_T,
    apply_eat_transform,
    eat_transform_from_betas,
    validate_eat_methylation_data
)

# Beta Mixture centroid container
from .core.methyl_mixture_centroid import MethylBetaMixtureCentroid

# Distribution views and probability helpers
from .core.distribution_views import (
    get_distribution_view,
    log_probability_sample_given_centroid,
    overlap_between_centroids,
    CountsView,
    NormalView,
    BetaView,
    BetaBinomialView,
    BMMView,
)
from .core.methyl_distribution_utils import clip_beta_params_for_bounds
from .ecdf_fit import (
    ecdf_vs_theoretical_ks,
    ecdf_vs_theoretical_ks_pvalue,
    compare_ecdf_to_theoretical_at_positions,
)
from .pipeline_config import (
    ProjectConfig,
    GroupConfig,
    ControlDiseaseSide,
    ComparisonSpec,
    SubclusterRequest,
    DerivedPaths,
    load_project,
)

# Add ClassifierFactory if it exists
try:
    from .classifier_factory import ClassifierFactory
except ImportError:
    pass

__version__ = "1.0.0"
__all__ = [
    # GPU detection functions
    "is_gpu_available",
    "is_cupy_available", 
    "is_cudf_available",
    "is_cupyx_scipy_available",
    "is_cupyx_scipy_integrate_available",
    "is_cupyx_scipy_special_available",
    "is_cupyx_scipy_stats_available",
    "get_gpu_memory_gb",
    "get_gpu_device_count",
    "get_gpu_state",
    "get_gpu_error_message",
    "get_cupy",
    "cleanup_gpu_memory",
    "reset_gpu_state",
    "print_gpu_status",
    "get_gpu_capabilities",
    "create_gpu_array",
    "to_cpu_array",
    "get_memory_info",
    "compare_implementations",
    # Logging functions
    "setup_logging",
    "setup_module_logging",
    "get_logger",
    "PerformanceLogger",
    # Methylation sample functions
    "MethylFrame",
    "MethylSample",
    "MethylExtendedCentroid",
    "compute_coverage_outlier_flags",
    "MethylBetaMixtureCentroid",
    "get_distribution_view",
    "log_probability_sample_given_centroid",
    "overlap_between_centroids",
    "CountsView",
    "NormalView",
    "BetaView",
    "BetaBinomialView",
    "BMMView",
    "clip_beta_params_for_bounds",
    "ecdf_vs_theoretical_ks",
    "ecdf_vs_theoretical_ks_pvalue",
    "compare_ecdf_to_theoretical_at_positions",
    "MethylCentroid",  # Alias for MethylExtendedCentroid
    "MethylBetaCentroid",  # Alias for MethylExtendedCentroid
    "load_from_h5",
    "load_pos_from_h5",
    "estimate_n_cap_from_sample_path",
    "estimate_n_cap_from_sample_path_with_log",
    "TNCBits",
    "encode_nucleotide",
    "decode_nucleotide",
    # Context constants
    "CONTEXT_CG",
    "CONTEXT_CHG",
    "CONTEXT_CHH",
    "CONTEXT_UNKNOWN",
    "CONTEXT_NAMES",
    # Strand constants
    "STRAND_POSITIVE",
    "STRAND_NEGATIVE",
    "STRAND_SYMBOLS",
    "METHYL_SAMPLE_DTYPE",
    "METHYL_CENTROID_DTYPE",
    "METHYL_EXTENDED_ONLY_DTYPE",
    "METHYL_CENTROID_DTYPE_EXTENDED",
    "MethylSampleDtype",
    "MethylCentroidDtype",
    "MethylExtendedCentroidDtype",
    "get_methyl_dtype",
    "DMPSample",
    "DMPExporter",
    "DMRExporter",
    "DMPSample",
    "DMPExporter",
    "DMRExporter",
    # Core metric functions
    "DistanceCalculator",
    "compute_jeffreys_divergence",
    "compute_beta_llr_moments",
    "compute_distribution_overlap",
    "compute_kl_divergence",
    "compute_bhattacharyya_distance",
    "compute_hellinger_distance",
    "compute_wasserstein_distance",
    "compute_jensen_shannon_distance",
    "compute_weighted_jensen_shannon_distance",
    "compute_entropy",
    "compute_sample_centroid_jsd",
    "get_sample_beta_mom",
    # Beta analytics functions (improved algorithm)
    "compute_per_site_llr_stats",
    "compute_precision_weighted_score",
    "compute_bhattacharyya_coefficient",
    "beta_log_pdf",
    "compute_beta_mean",
    "compute_beta_variance",
    "log_beta_binomial_pmf",
    # Beta mixture utilities
    "fit_beta_mixture",
    "estimate_js_divergence",
    "mixture_logpdf",
    # Factory functions
    "MetricFactory",
    "get_metric_factory",
    "auto_compute_distance",
    # Statistical test functions
    "storey_qvalues",
    "stouffer_global_p",
    "beta_loglikelihood",
    "beta_mle_estimation",
    "likelihood_ratio_test_beta",
    # Genomic utilities
    "group_significant_positions",
    # GPU utilities
    "_prepare_arrays_for_backend",
    "_ensure_cpu_output",
    # Validation functions
    "validate_beta_parameters",
    "validate_array_shapes",
    "validate_methylation_data",
    "validate_weights",
    "validate_sample_data",
    # Phase 2: Performance Optimization
    "MemoryManager",
    "get_memory_manager",
    "memory_usage_monitor",
    "check_memory_limits",
    "get_memory_usage",
    "force_gpu_cleanup",
    "ChunkedGenomicProcessor",
    "ChunkInfo",
    "ProcessingResult",
    "process_genome_file_chunked",
    "create_genome_statistics_processor",
    "PerformanceProfiler",
    "PerformanceMetrics",
    "get_performance_profiler",
    "start_performance_monitoring",
    "stop_performance_monitoring",
    "get_performance_report",
    "profile_performance",
    # PositionAligner deprecated - use MethylExtendedCentroid methods instead
    # "PositionAligner",
    # "align_multiple_samples",
    "PositionMethylationStats",
    "GroupMethylationStats",
    "AlignmentStats",
    "MethylationAnalysisResults",
    "create_analysis_results",
    # Probabilistic Beta Classifier
    "ProbabilisticBetaClassifier",
    "MultiClassBetaMixtureClassifier",
    "create_classifier_from_results",
    # Beta-Binomial Classifier (multi-context)
    "BetaBinomialClassifier",
    # MethylCentroidPair for centroid comparison
    "MethylCentroidPair",
    # Bayesian Classifier Trainer
    "BayesianClassifierTrainer",
    "FilterConfig",
    "train_classifier_from_centroids",
    # P-value aggregation methods
    "aggregate_pvalues_fisher",
    "aggregate_pvalues_stouffer",
    "aggregate_pvalues_lancaster",
    "aggregate_pvalues_tippett",
    "aggregate_pvalues_edgington",
    "aggregate_pvalues_mudholkar_george",
    "aggregate_pvalues_simes",
    "PVALUE_AGGREGATION_METHODS",
    "discrete_overlap_from_bin_counts",
    "welch_d_fast_overlap_approx",
    "welch_d_ks_overlap",
    'BetaClassifier',
    'ClassifierFactory',  # if added
    # EAT transformation functions
    'compute_eat_T',
    'apply_eat_transform',
    'eat_transform_from_betas',
    'validate_eat_methylation_data',
    # Pipeline project config (chained workflows)
    "ProjectConfig",
    "GroupConfig",
    "ControlDiseaseSide",
    "ComparisonSpec",
    "SubclusterRequest",
    "DerivedPaths",
    "load_project",
]
