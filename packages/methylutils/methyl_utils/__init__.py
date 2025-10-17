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
    from methyl_utils import auto_compute_distance, PositionAligner

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

from .methyl_sample import (
    MethylSample,
    TNCBits,
    METHYL_SAMPLE_DTYPE,
    METHYL_CENTROID_DTYPE,
    METHYL_EXTENDED_CENTROID_DTYPE,
    MethylSampleDtype,
    MethylCentroidDtype,
    MethylExtendedCentroidDtype,
    get_methyl_dtype,
    DMPSample,
    DMPExporter,
    DMRExporter
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
    PVALUE_AGGREGATION_METHODS
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

# Import GPA (Genomic Position Aligner) components
from .position_aligner import PositionAligner, align_multiple_samples
from .models import (
    PositionMethylationStats,
    GroupMethylationStats,
    AlignmentStats,
    MethylationAnalysisResults,
    create_analysis_results
)

# Import Probabilistic Beta Classifier
from .probabilistic_beta_classifier import (
    ProbabilisticBetaClassifier,
    create_classifier_from_results
)

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
    compute_beta_variance
)

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
    "MethylSample",
    "TNCBits",
    "METHYL_SAMPLE_DTYPE",
    "METHYL_CENTROID_DTYPE",
    "METHYL_EXTENDED_CENTROID_DTYPE",
    "MethylSampleDtype",
    "MethylCentroidDtype",
    "MethylExtendedCentroidDtype",
    "get_methyl_dtype",
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
    # GPA (Genomic Position Aligner) functions
    "PositionAligner",
    "align_multiple_samples",
    "PositionMethylationStats",
    "GroupMethylationStats",
    "AlignmentStats",
    "MethylationAnalysisResults",
    "create_analysis_results",
    # Probabilistic Beta Classifier
    "ProbabilisticBetaClassifier",
    "create_classifier_from_results",
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
    "PVALUE_AGGREGATION_METHODS"
]
