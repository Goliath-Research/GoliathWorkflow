# methyl_centroid.py
import sys
import os
from pathlib import Path

# Add methylutils from monorepo to Python path (for development/direct execution)
# In monorepo: packages/methylcentroid/../methylutils/methyl_utils
methyl_utils_path = Path(__file__).parent.parent.parent / "methylutils" / "methyl_utils"
if methyl_utils_path.exists() and str(methyl_utils_path) not in sys.path:
    sys.path.insert(0, str(methyl_utils_path))

# Note: genomic_position_aligner (gpa_pkg) is now part of methylutils package
# No separate path addition needed - it's imported via methylutils

import numpy as np
from pathlib import Path
from typing import List, Union, Optional, Tuple, Dict, OrderedDict
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum
import json
import psutil
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict
from methyl_utils.core.methyl_frame import (
    #METHYL_CENTROID_DTYPE, 
    #METHYL_EXTENDED_CENTROID_DTYPE, 
    MethylSample,
    MethylExtendedCentroid,
)
# Distance calculation functions
from methyl_utils import (
    auto_compute_distance,
    get_sample_beta_mom,
    get_methyl_dtype,
    # Memory management
    get_memory_manager,
    # Performance profiling
    get_performance_profiler,
    start_performance_monitoring,
    # Chunked processing
    ChunkedGenomicProcessor,
    process_genome_file_chunked,
    # GPU detection
    is_gpu_available,
    # Logging
    get_logger
)

# Setup logging using MethylUtils
import logging

class DistanceMetric(str, Enum):
    """Enumeration of available distance metrics for outlier detection."""
    JEFFREYS = "jeffreys"
    JENSEN_SHANNON = "jensen_shannon"
    WEIGHTED_JENSEN_SHANNON = "weighted_jensen_shannon"
    HELLINGER = "hellinger"
    WASSERSTEIN = "wasserstein"

    def to_factory_name(self) -> str:
        """
        Convert DistanceMetric enum to MethylUtils factory metric name.

        Returns:
            String name used by MetricFactory
        """
        mapping = {
            DistanceMetric.JEFFREYS: "jeffreys",
            DistanceMetric.JENSEN_SHANNON: "jensen_shannon",
            DistanceMetric.WEIGHTED_JENSEN_SHANNON: "weighted_jensen_shannon",
            DistanceMetric.HELLINGER: "hellinger",
            DistanceMetric.WASSERSTEIN: "wasserstein"
        }
        return mapping.get(self, "jensen_shannon")  # Default fallback

class SmartSampleCache:
    """
    Intelligent sample cache with memory management and LRU eviction.

    This cache automatically manages memory usage and evicts least recently used
    samples when memory limits are approached.
    """

    def __init__(self, memory_manager, max_memory_gb: float = None):
        """
        Initialize the smart sample cache.

        Args:
            memory_manager: MethylUtils memory manager instance
            max_memory_gb: Maximum memory to use for caching (None = auto-detect)
        """
        self.memory_manager = memory_manager
        self.cache: OrderedDict[Path, 'MethylSample'] = OrderedDict()
        self.memory_usage_mb: Dict[Path, float] = {}

        # Set memory limit based on available memory
        if max_memory_gb is None:
            memory_info = memory_manager.get_memory_usage()
            total_memory_gb = memory_info.get('total_gb', 400)  # Default to 400GB
            # Use 70% of available memory for caching
            self.max_memory_gb = total_memory_gb * 0.7
        else:
            self.max_memory_gb = max_memory_gb

        # Cache size optimization based on sample properties
        self._estimated_bytes_per_sample = None  # Will be set when first sample is loaded

        self.total_cached_memory_mb = 0.0

    def get(self, sample_path: Path, loader_func: callable = None) -> Optional['MethylSample']:
        """
        Get a sample from cache, loading it if not present.

        Args:
            sample_path: Path to the sample
            loader_func: Function to load sample if not in cache

        Returns:
            MethylSample instance or None if loading fails
        """
        # Check if in cache
        if sample_path in self.cache:
            # Move to end (most recently used)
            self.cache.move_to_end(sample_path)
            return self.cache[sample_path]

        # Not in cache, load if loader provided
        if loader_func:
            try:
                sample = loader_func(sample_path)
                if sample:
                    self._add_to_cache(sample_path, sample)
                return sample
            except Exception:
                return None

        return None

    def _add_to_cache(self, sample_path: Path, sample: 'MethylSample'):
        """
        Add sample to cache with memory management using MethylSample properties.

        Args:
            sample_path: Path to the sample
            sample: MethylSample instance
        """
        # Calculate memory usage using MethylSample property
        memory_mb = sample.memory_usage_mb

        # Update estimated bytes per sample for future cache sizing decisions
        if self._estimated_bytes_per_sample is None:
            self._estimated_bytes_per_sample = sample.bytes_per_position
        else:
            # Update running average
            self._estimated_bytes_per_sample = (
                self._estimated_bytes_per_sample + sample.bytes_per_position
            ) / 2

        # Check if we need to evict before adding
        while self.total_cached_memory_mb + memory_mb > self.max_memory_gb * 1024:
            if not self._evict_lru():
                break  # Can't evict more

        # Add to cache
        self.cache[sample_path] = sample
        self.memory_usage_mb[sample_path] = memory_mb
        self.total_cached_memory_mb += memory_mb

    def _calculate_sample_memory_usage(self, sample: 'MethylSample') -> float:
        """Calculate memory usage of a MethylSample in MB using the sample's built-in property."""
        return sample.memory_usage_mb

    def _evict_lru(self) -> bool:
        """Evict least recently used sample. Returns True if eviction occurred."""
        if not self.cache:
            return False

        # Get LRU item
        lru_path, lru_sample = self.cache.popitem(last=False)  # FIFO order

        # Update memory tracking
        if lru_path in self.memory_usage_mb:
            self.total_cached_memory_mb -= self.memory_usage_mb[lru_path]
            del self.memory_usage_mb[lru_path]

        return True

    def clear(self):
        """Clear all cached samples."""
        self.cache.clear()
        self.memory_usage_mb.clear()
        self.total_cached_memory_mb = 0.0

    def get_stats(self) -> Dict:
        """Get cache statistics including sample property estimates."""
        stats = {
            'cached_samples': len(self.cache),
            'memory_usage_mb': self.total_cached_memory_mb,
            'memory_limit_gb': self.max_memory_gb,
            'memory_usage_percent': (self.total_cached_memory_mb / (self.max_memory_gb * 1024)) * 100,
            'estimated_bytes_per_sample': self._estimated_bytes_per_sample
        }

        # Add GPU memory estimates if we have sample size information
        if self._estimated_bytes_per_sample is not None:
            gpu_memory_gb = self.memory_manager.gpu_memory_limit_gb
            gpu_memory_bytes = gpu_memory_gb * 1024 * 1024 * 1024

            # Estimate how many samples can fit in GPU memory
            # Conservative estimate: use 80% of GPU memory for samples
            available_gpu_bytes = gpu_memory_bytes * 0.8
            estimated_samples_in_gpu = int(available_gpu_bytes / (self._estimated_bytes_per_sample * 1000000))  # Convert MB to bytes

            stats.update({
                'estimated_samples_per_gpu_batch': max(1, estimated_samples_in_gpu),
                'gpu_memory_available_gb': gpu_memory_gb,
                'sample_size_bytes_per_position': self._estimated_bytes_per_sample
            })

        return stats


class MethylCentroidConfig(BaseModel):
    """
    Pydantic configuration model for MethylCentroid parameters.

    Workflows:
    - Initial centroid creation: provide add_samples, output_dir for saving (samples=[], outliers=[])
    - After outlier removal: samples contains remaining samples, outliers contains removed samples
    - Centroid updates: provide samples (current centroid samples), add_samples/remove_samples, outliers
    - When adding new samples, previous outliers are automatically re-included for fair centroid building
    """

    chrom: str = Field(..., description="Chromosome identifier (e.g., '1', 'X')")
    ctx: str = Field(..., description="Context type (e.g., 'CG', 'CHG', 'CHH')")
    output_dir: str = Field(..., description="Directory to save centroid files")
    samples: List[str] = Field(
        default=[],
        description="List of sample paths currently in the centroid (used for updates)"
    )
    add_samples: List[str] = Field(
        default=[],
        description="Optional list of new sample paths to add incrementally"
    )
    remove_samples: List[str] = Field(
        default=[],
        description="Optional list of sample paths to remove"
    )
    outliers: List[str] = Field(
        default=[],
        description="List of sample paths that were previously identified as outliers and removed"
    )
    min_coverage: int = Field(
        default=4, 
        ge=1, 
        description="Minimum sum of mC and uC for a position"
    )
    max_iterations: int = Field(
        default=10, 
        ge=1, 
        description="Maximum outlier removal iterations"
    )
    max_iterations_percentage: float = Field(
        default=0.1,
        gt=0.0,
        le=1.0,
        description="Percentage of samples to use as maximum outlier removal iterations (overrides max_iterations if > 0)"
    )
    α: float = Field(
        default=0.05,
        gt=0.0,
        le=1.0,
        description="Significance level for outlier detection",
    )
    min_samples: int = Field(
        default=3, 
        ge=1, 
        description="Minimum samples required for outlier removal"
    )
    distance_metrics: Optional[List[DistanceMetric]] = Field(
        default=None,
        description="List of distance metrics to use for outlier detection (None disables outlier detection)"
    )
    min_metrics_agree: int = Field(
        default=0,
        ge=0,
        description="Minimum number of distance metrics that must agree for a sample to be considered an outlier. Set to 0 to use General Simes formula."
    )

class OutlierIterationInfo(BaseModel):
    """
    Pydantic model for outlier removal iteration information.
    """
    iteration: int = Field(..., description="Iteration number")
    p_value: float = Field(..., description="P-value of the removed outlier")
    outlier_path: str = Field(..., description="Path to the removed outlier sample")

class OutlierRemovalResults(BaseModel):
    """
    Pydantic model for outlier removal results.
    """
    iterations: List[OutlierIterationInfo] = Field(
        default_factory=list, 
        description="List of iteration information"
    )
    final_centroid_path: str = Field(..., description="Path to the final centroid file")
    total_samples_removed: int = Field(
        ..., 
        description="Total number of samples removed"
    )

class MethylCentroid:
    """
    Class to calculate methylation centroid for a group of samples / (chromosome, context).

    Designed for performance with large genomic datasets by using dense matrices
    and minimizing memory overhead. Processes each (chromosome, context) independently to
    optimize memory usage, with coverage-based filtering for centroids.

    Supports incremental operations for centroid updates and outlier detection workflows.
    Uses MethylUtils for optimized distance calculations, GPU acceleration, and memory management.

    Workflows:
    - Initial centroid creation: provide samples in output_dir
    - Centroid updates: provide add_samples/remove_samples to modify existing centroid

    The centroid represents the average of mC and uC values across all samples:
    - centroid.mC = sum(all sample.mC) / sample_count
    - centroid.uC = sum(all sample.uC) / sample_count
    - sample_count = number of samples that contributed to the centroid (parameter-based)
    - Centroid structure is similar to a sample (pos, mC, uC, tnc)
    """

    def __init__(
        self,
        chrom: str,
        ctx: str,
        output_dir: Path,
        samples: List[str] = None,
        add_samples: List[str] = None,
        remove_samples: List[str] = None,
        outliers: List[str] = None,
        min_coverage: int = 4,
        max_iterations: int = 10,
        max_iterations_percentage: float = 0.1,
        α: float = 0.05,
        min_samples: int = 3,
        distance_metrics: Optional[List[DistanceMetric]] = None,
        min_metrics_agree: int = 1,
        verbose: bool = True,
        # Metadata fields
        laboratory: str = None,
        disease: str = None,
        group: str = None,
        batch: str = None,
    ):
        from contextlib import contextmanager
        import logging

        @contextmanager
        def tqdm_logging_disabled():
            """Context manager to temporarily disable debug logging during tqdm operations."""
            if not self.verbose:
                # Only disable debug logging if not in verbose mode
                original_level = self.logger.level
                self.logger.setLevel(logging.INFO)
                try:
                    yield
                finally:
                    self.logger.setLevel(original_level)
            else:
                yield

        self.tqdm_logging_disabled = tqdm_logging_disabled
        """
        Initialize MethylCentroid for centroid calculation and outlier detection.

        Args:
            samples: Optional list of base sample directory paths containing {chrom}-{ctx}.h5 files.
                    For initial centroid creation, use add_samples instead. For updates, this contains
                    current samples in the centroid.
            chrom: Chromosome identifier (e.g., '1', 'X').
            ctx: Context type (e.g., 'CG', 'CHG', 'CHH').
            output_dir: Directory to save centroid files.
            add_samples: Optional list of sample directory paths to add (used for initial creation and updates).
            remove_samples: Optional list of sample directory paths to remove.
            outliers: Optional list of sample directory paths that were previously identified as outliers.
                    These will be automatically re-included when adding new samples for fair centroid building.
            min_coverage: Minimum sum of mC and uC for a position to be included.
            max_iterations: Maximum outlier removal iterations.
            max_iterations_percentage: Percentage of samples for max iterations (overrides max_iterations if > 0).
            α: Significance level for outlier detection.
            min_samples: Minimum samples required for outlier removal.
            distance_metrics: List of distance metrics to use for outlier detection.
            min_metrics_agree: Minimum number of distance metrics that must agree for outlier detection.
            verbose: Enable verbose logging.

        Workflow:
            - Initial centroid creation: provide add_samples, output_dir (samples=[], outliers=[])
            - After outlier removal: samples contains remaining samples, outliers contains removed samples
            - Centroid updates: provide samples (current centroid), add_samples/remove_samples, outliers
            - When adding new samples, previous outliers are automatically re-included for fair building
        """

        # Setup logging using MethylUtils
        self.verbose = verbose
        self.logger = get_logger(__name__, verbose=verbose)
        
        # Convert to Path objects with chromosome-context file
        if samples:
            self.samples = [Path(sample) / f"{chrom}-{ctx}.h5" for sample in samples]
            self.add_samples = (
                [Path(sample) / f"{chrom}-{ctx}.h5" for sample in add_samples]
                if add_samples
                else []
            )
            # Store original sample paths as strings for config reconstruction
            self._original_samples = [str(s) for s in samples]
            self._original_add_samples = [str(s) for s in add_samples] if add_samples else []
        else:
            # If no samples provided, use add_samples as the main samples
            self.samples = (
                [Path(sample) / f"{chrom}-{ctx}.h5" for sample in add_samples]
                if add_samples
                else []
            )
            self.add_samples = []
            # Store original sample paths as strings for config reconstruction
            self._original_samples = [str(s) for s in add_samples] if add_samples else []
            self._original_add_samples = []

        # Handle remove samples for incremental updates
        self.remove_samples = (
            [Path(sample) / f"{chrom}-{ctx}.h5" for sample in remove_samples]
            if remove_samples
            else []
        )
        self._original_remove_samples = [str(s) for s in remove_samples] if remove_samples else []

        # Handle outliers for re-inclusion during updates
        self.outliers = (
            [Path(outlier) / f"{chrom}-{ctx}.h5" for outlier in outliers]
            if outliers
            else []
        )
        self._original_outliers = [str(s) for s in outliers] if outliers else []
        self.min_coverage = max(1, min_coverage)
        self.chrom = chrom
        self.ctx = ctx
        self.output_dir = (Path(output_dir) if isinstance(output_dir, str) else output_dir)

        # Ensure output directory exists from the start
        try:
            # First ensure parent directories exist
            self.output_dir.parent.mkdir(parents=True, exist_ok=True)
            # Then create the target directory
            self.output_dir.mkdir(exist_ok=True)
            # Verify directory was actually created
            if not self.output_dir.exists():
                raise OSError(f"Failed to create output directory: {self.output_dir}")
            # Note: os.access may not work correctly in container environments
        except PermissionError as e:
            raise OSError(f"Permission denied creating output directory {self.output_dir}. "
                         f"Please ensure the parent directory is writable: {self.output_dir.parent}. "
                         f"Original error: {e}")
        except Exception as e:
            raise OSError(f"Cannot create output directory {self.output_dir}: {e}")

        # Derive centroid path from output directory and chromosome/context
        self.centroid_path = self.output_dir / f"{chrom}-{ctx}.h5"

        # Calculate max_iterations based on percentage if provided
        total_samples = len(self.samples) + len(self.add_samples)
        if max_iterations_percentage > 0:
            # Use percentage-based calculation, truncated down
            self.max_iterations = max(1, int(max_iterations_percentage * total_samples))
        else:
            self.max_iterations = max_iterations

        self.max_iterations_percentage = max_iterations_percentage
        self.α = α
        self.min_samples = min_samples
        
        # Store metadata fields
        self.laboratory = laboratory
        self.disease = disease
        self.group = group
        self.batch = batch
        
        # Initialize distance metrics; None/empty disables outlier detection
        self.distance_metrics = distance_metrics or []
        self.min_metrics_agree = min_metrics_agree
        
        self.centroid: Optional[Path] = None

        # Detect GPU availability and prioritize GPU acceleration for large datasets
        gpu_available = is_gpu_available()
        self.logger.info(f"GPU available: {gpu_available}")

        # For large human genomes, prioritize GPU; for smaller datasets like Arabidopsis, use CPU if GPU fails
        self.use_gpu = gpu_available
        if gpu_available:
            self.logger.info("Using GPU acceleration for optimal performance with large genomic datasets")
        else:
            self.logger.warning("GPU not available, falling back to CPU processing")

        # Initialize centroid accumulator (will be created when first sample is added)
        self._centroid: Optional[MethylExtendedCentroid] = None
        self._min_coverage = min_coverage

        # Initialize memory manager from MethylUtils
        self.memory_manager = get_memory_manager()

        # Initialize performance profiler from MethylUtils
        self.performance_profiler = get_performance_profiler()

        # Initialize chunked processor with dynamic memory-aware parameters
        chunked_params = self._calculate_chunked_processor_params(self.use_gpu)
        self.chunked_processor = ChunkedGenomicProcessor(
            chunk_size_positions=chunked_params['chunk_size_positions'],
            max_workers=chunked_params['max_workers'],
            use_gpu=self.use_gpu,  # Use GPU when available for large datasets
            memory_limit_gb=chunked_params['memory_limit_gb']
        )

        # Track active samples (those currently included in centroid calculation)
        self.active_samples: set = set()

        # Track outlier samples (those removed from centroid calculation)
        self.outlier_samples: set = set()

        # Progress bar for sample addition
        self.progress_bar: Optional[tqdm] = None

        # Iteration counter for histogram naming
        self.current_iteration: int = 0
        self.sample_cache = SmartSampleCache(self.memory_manager)
        self._cache_enabled = True  # Flag to control caching behavior

        # GPU usage tracking and fallback management
        self._gpu_available = gpu_available
        self._using_gpu = self.use_gpu
        self._gpu_memory_pressure_detected = False

        for sample in self.samples + self.add_samples:
            if not sample.exists():
                print(f"Warning: Sample {sample} does not exist")

    @classmethod
    def from_config(cls, config: MethylCentroidConfig, verbose: bool = None) -> "MethylCentroid":
        # Use config.verbose if verbose parameter is not provided, otherwise use the parameter
        verbose_value = verbose if verbose is not None else config.verbose

        return cls(
            samples=getattr(config, 'samples', None),
            chrom=config.chrom,
            ctx=config.ctx,
            output_dir=config.output_dir,
            add_samples=config.add_samples,
            remove_samples=config.remove_samples,
            outliers=config.outliers,
            min_coverage=config.min_coverage,
            max_iterations=config.max_iterations,
            max_iterations_percentage=config.max_iterations_percentage,
            α=config.α,
            min_samples=config.min_samples,
            distance_metrics=config.distance_metrics,
            min_metrics_agree=config.min_metrics_agree,
            verbose=verbose_value,
            # Metadata fields
            laboratory=config.laboratory,
            disease=config.disease,
            group=config.group,
            batch=config.batch,
        )

    @classmethod
    def from_json(cls, json_data: str | dict, verbose: bool = False) -> "MethylCentroid":

        config = MethylCentroidConfig.model_validate(json_data)
        return cls.from_config(config, verbose=verbose)

    def get_config(self) -> MethylCentroidConfig:

        config_dict = {
            "chrom": self.chrom,
            "ctx": self.ctx,
            "output_dir": str(self.output_dir),
            "samples": self._original_samples,
            "add_samples": self._original_add_samples,
            "remove_samples": self._original_remove_samples,
            "outliers": self._original_outliers,
            "min_coverage": self.min_coverage,
            "max_iterations": self.max_iterations,
            "max_iterations_percentage": self.max_iterations_percentage,
            "α": self.α,
            "min_samples": self.min_samples,
            "distance_metrics": self.distance_metrics,
            "min_metrics_agree": self.min_metrics_agree,
            # Metadata fields
            "laboratory": self.laboratory,
            "disease": self.disease,
            "group": self.group,
            "batch": self.batch,
        }

        return MethylCentroidConfig(**config_dict)

    def _print_progress(self):

        if self.progress_bar is None:
            total = len(self.samples) + len(self.add_samples)
            self.progress_bar = tqdm(total=total, desc="Adding samples", unit="sample")

        # Simply increment by 1 for each sample processed
        self.progress_bar.update(1)

        # Close progress bar if complete
        if self.progress_bar.n >= self.progress_bar.total:
            self.progress_bar.close()
            self.progress_bar = None

    def _load_existing_centroid_state(self, centroid_path: Path) -> bool:

        if not centroid_path.exists():
            print(f"Centroid file not found: {centroid_path}")
            return False
        try:
            # Load the centroid as MethylExtendedCentroid
            from methyl_utils.core.io import load_from_h5
            loaded_centroid = load_from_h5(centroid_path)
            
            # Ensure it's an extended centroid
            if not isinstance(loaded_centroid, MethylExtendedCentroid):
                # Try to convert if it's a basic centroid or sample
                if hasattr(loaded_centroid, 'as_extended_centroid'):
                    loaded_centroid = loaded_centroid.as_extended_centroid()
                else:
                    print(f"Loaded centroid is not an extended centroid: {type(loaded_centroid)}")
                    return False
            
            self._centroid = loaded_centroid

            # Mark original samples as active
            for i in range(len(self.samples)):
                self.active_samples.add((False, i))

            # Store centroid reference
            self.centroid = centroid_path

            print(f"Loaded existing centroid state from {centroid_path}")
            return True
        except Exception as e:
            print(f"Error loading existing centroid state: {e}")
            import traceback
            traceback.print_exc()
            return False

    def add_sample(self, sample_index: int, is_new_sample: bool = False, sample_path: Path = None) -> bool:

        # Determine which sample list to use and get the actual sample
        if sample_path is not None:
            # Using a specific sample path (e.g., for re-adding outliers)
            sample = sample_path
            # For outliers, we treat them as additional samples
            index = len(self.samples) + len(self.add_samples) + sample_index
        elif is_new_sample:
            if sample_index >= len(self.add_samples):
                print(f"Add sample index {sample_index} out of range")
                return False
            sample = self.add_samples[sample_index]
            # Adjust index for tnc_data array (add samples come after original samples)
            index = len(self.samples) + sample_index
        else:
            if sample_index >= len(self.samples):
                print(f"Sample index {sample_index} out of range")
                return False
            sample = self.samples[sample_index]
            index = sample_index

        # Create a unique identifier for tracking active samples
        if sample_path is not None:
            # For outliers, use a special identifier
            sample_id = ("outlier", sample_index)
        else:
            sample_id = (is_new_sample, sample_index)

        if sample_id in self.active_samples:
            print(f"Sample {sample_index} (new={is_new_sample}) is already included.")
            return False

        if not sample.exists():
            print(f"Sample {sample} does not exist")
            return False

        try:
            methyl_sample = self.load_sample(sample)
            
            if len(methyl_sample.pos) == 0:
                print(f"Sample {sample} has no valid positions")
                return False

            # Add the sample to centroid using new method
            if self._centroid is None:
                # Create initial centroid from first sample
                # Use MethylCentroidBuilder for proper initialization
                from methyl_utils.core.centroid_builder import MethylCentroidBuilder
                builder = MethylCentroidBuilder(min_coverage=self._min_coverage, use_gpu=self.use_gpu)
                builder.add_sample(sample_path)
                self._centroid = builder.finalize()
                # Apply min_samples filter after builder finalizes
                if hasattr(self._centroid, 'N') and len(self._centroid) > 0:
                    N_vals = np.asarray(self._centroid.N.values) if hasattr(self._centroid.N, 'values') else np.asarray(self._centroid.N)
                    valid_mask = N_vals >= self.min_samples
                    if not valid_mask.all():
                        # Filter out positions with N < min_samples
                        # Use integer indices instead of boolean mask to avoid pandas indexing issues
                        valid_indices = np.where(valid_mask)[0]
                        if len(valid_indices) > 0:
                            self._centroid = self._centroid.apply_mask(valid_indices)
                        else:
                            # No valid positions, create empty centroid
                            from methyl_utils import MethylExtendedCentroid
                            import pandas as pd
                            empty_df = pd.DataFrame({
                                'pos': [], 'mC': [], 'uC': [], 'tnc': [],
                                'N': [], 'Sx': [], 'Sx2': [], 'log_x_sum': [], 'log_1_minus_x_sum': []
                            })
                            self._centroid = MethylExtendedCentroid(empty_df, self._centroid.metadata)
            else:
                # Add sample to existing centroid
                self._centroid = self._centroid.add_sample(methyl_sample)

            self.active_samples.add(sample_id)
            self._print_progress()

        except Exception as e:
            print(f"Error processing {sample}: {e}")
            return False

        return True

    def remove_sample(self, sample_index: int, is_new_sample: bool = False):

        index = (is_new_sample, sample_index)
        if index not in self.active_samples:
            return

        sample_path = (
            self.add_samples[sample_index]
            if is_new_sample
            else self.samples[sample_index]
        )

        methyl_sample = self.load_sample(sample_path)

        # Remove sample from centroid
        if self._centroid is None:
            raise RuntimeError("Cannot remove sample: no centroid exists")
        
        try:
            self._centroid = self._centroid.remove_sample(methyl_sample)
        except ValueError as e:
            raise RuntimeError(f"Failed to remove sample: {e}")

        self.active_samples.remove(index)
        self.outlier_samples.add(index)

    def _get_active_sample_paths(self) -> list:
        """
        Get the paths of all samples currently active in the centroid.
        
        Returns:
            List of sample directory paths (as strings)
        """
        active_paths = []
        for is_new_sample, sample_index in sorted(self.active_samples):
            if is_new_sample:
                # Sample from add_samples list
                if sample_index < len(self.add_samples):
                    sample_path = self.add_samples[sample_index]
                    # Extract directory path (remove the H5 filename)
                    active_paths.append(str(sample_path.parent) if hasattr(sample_path, 'parent') else str(Path(sample_path).parent))
            else:
                # Sample from original samples list
                if sample_index < len(self.samples):
                    sample_path = self.samples[sample_index]
                    # Extract directory path (remove the H5 filename)
                    active_paths.append(str(sample_path.parent) if hasattr(sample_path, 'parent') else str(Path(sample_path).parent))
        return active_paths

    def add_samples_parallel(self):

        def load_sample_data(sample_path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    
            try:
                from methyl_utils import MethylSample
                methyl_sample = MethylSample.load_from_h5(sample_path)

                # Ensure sample is on CPU (converts GPU arrays if needed)
                methyl_sample = methyl_sample.to_cpu()

                # Get underlying numpy arrays from Series properties
                # Ensure we get actual numpy arrays, not cupy arrays or Series
                pos_series = methyl_sample.pos
                mC_series = methyl_sample.mC
                uC_series = methyl_sample.uC
                # Access tnc from DataFrame directly (no property defined)
                tnc_series = methyl_sample._df["tnc"]
                
                # Extract numpy arrays from Series
                if hasattr(pos_series, 'values'):
                    pos = np.asarray(pos_series.values, dtype=np.uint32)
                else:
                    pos = np.asarray(pos_series, dtype=np.uint32)
                    
                if hasattr(mC_series, 'values'):
                    mC = np.asarray(mC_series.values, dtype=np.uint32)
                else:
                    mC = np.asarray(mC_series, dtype=np.uint32)
                    
                if hasattr(uC_series, 'values'):
                    uC = np.asarray(uC_series.values, dtype=np.uint32)
                else:
                    uC = np.asarray(uC_series, dtype=np.uint32)
                    
                if hasattr(tnc_series, 'values'):
                    tnc = np.asarray(tnc_series.values, dtype=np.uint8)
                else:
                    tnc = np.asarray(tnc_series, dtype=np.uint8)

                # Filter out positions with no coverage to reduce memory usage
                coverage = mC + uC
                valid_mask = coverage > 0

                if np.any(valid_mask):
                    # Filter arrays (already numpy arrays from .values above)
                    filtered_pos = pos[valid_mask]
                    filtered_mC = mC[valid_mask]
                    filtered_uC = uC[valid_mask]
                    filtered_tnc = tnc[valid_mask]

                    return (
                        filtered_pos,
                        filtered_mC,
                        filtered_uC,
                        filtered_tnc,
                    )
                else:
                    return (
                        np.array([], dtype=np.uint32),
                        np.array([], dtype=np.uint32),
                        np.array([], dtype=np.uint32),
                        np.array([], dtype=np.uint8),
                    )
            except Exception as e:
                import traceback
                print(f"Error loading sample {sample_path}: {e}")
                print(f"Traceback: {traceback.format_exc()}")
                return (
                    np.array([], dtype=np.uint32),
                    np.array([], dtype=np.uint32),
                    np.array([], dtype=np.uint32),
                    np.array([], dtype=np.uint8),
                )

        all_samples = self.samples + self.add_samples

        # Dynamic worker calculation based on memory and CPU
        memory_info = self.memory_manager.get_memory_usage()
        total_memory_gb = memory_info.get('total_gb', 400)
        available_memory_gb = memory_info.get('available_gb', 350)
        estimated_memory_per_sample_gb = 0.8  # Conservative estimate: 800MB per sample

        # Memory-based limit: reserve 30% of memory for processing
        memory_reserved_gb = total_memory_gb * 0.3
        max_workers_by_memory = max(1, int((available_memory_gb - memory_reserved_gb) / estimated_memory_per_sample_gb))

        # CPU-based limit: use 75% of available CPUs
        cpu_count = psutil.cpu_count()
        max_workers_by_cpu = max(1, int(cpu_count * 0.75))

        # Context-based adjustment (CHH has more positions, needs more memory)
        context_multiplier = {'CG': 1.0, 'CHG': 4.0, 'CHH': 16.0}.get(self.ctx, 1.0)
        max_workers_by_memory = max(1, int(max_workers_by_memory / context_multiplier))

        # Final worker count
        actual_batch_size = min(max_workers_by_memory, max_workers_by_cpu, len(all_samples))

        self.logger.info(
            f"Using {actual_batch_size} parallel workers "
            f"(memory: {available_memory_gb:.1f}GB available, "
            f"context: {self.ctx}, multiplier: {context_multiplier:.1f})"
        )

        # Load samples in parallel batches
        with ThreadPoolExecutor(max_workers=actual_batch_size) as executor:
            # Submit all sample loading tasks
            future_to_sample = {}
            for i, sample_path in enumerate(all_samples):
                future = executor.submit(load_sample_data, sample_path)
                future_to_sample[future] = (i, sample_path)

            # Process completed tasks and add samples to position aligner
            for future in as_completed(future_to_sample):
                sample_idx, sample_path = future_to_sample[future]
                try:
                    pos, mC, uC, tnc = future.result()

                    # Skip empty samples
                    if len(pos) == 0:
                        # Skip debug logging during tqdm operations to avoid progress bar interference
                        continue

                    # Create MethylSample-like object for position aligner
                    # Add sample using new method
                    if self._centroid is None:
                        from methyl_utils.core.centroid_builder import MethylCentroidBuilder
                        builder = MethylCentroidBuilder(min_coverage=self._min_coverage, use_gpu=self.use_gpu)
                        builder.add_sample(sample_path)
                        self._centroid = builder.finalize()
                        # Apply min_samples filter after builder finalizes
                        if hasattr(self._centroid, 'N') and len(self._centroid) > 0:
                            N_vals = np.asarray(self._centroid.N.values) if hasattr(self._centroid.N, 'values') else np.asarray(self._centroid.N)
                            valid_mask = N_vals >= self.min_samples
                            if not valid_mask.all():
                                # Filter out positions with N < min_samples
                                # Use integer indices instead of boolean mask to avoid pandas indexing issues
                                valid_indices = np.where(valid_mask)[0]
                                if len(valid_indices) > 0:
                                    self._centroid = self._centroid.apply_mask(valid_indices)
                                else:
                                    # No valid positions, create empty centroid
                                    from methyl_utils import MethylExtendedCentroid
                                    import pandas as pd
                                    empty_df = pd.DataFrame({
                                        'pos': [], 'mC': [], 'uC': [], 'tnc': [],
                                        'N': [], 'Sx': [], 'Sx2': [], 'log_x_sum': [], 'log_1_minus_x_sum': []
                                    })
                                    self._centroid = MethylExtendedCentroid(empty_df, self._centroid.metadata)
                    else:
                        # Load the actual MethylSample and add it
                        methyl_sample = self.load_sample(sample_path)
                        self._centroid = self._centroid.add_sample(methyl_sample)
                    success = True

                    if success:
                        # Mark as active sample
                        is_new_sample = sample_idx >= len(self.samples)
                        actual_sample_idx = sample_idx - len(self.samples) if is_new_sample else sample_idx
                        sample_id = (is_new_sample, actual_sample_idx)
                        self.active_samples.add(sample_id)
                    else:
                        self.logger.warning(f"Failed to add sample {sample_path.name} to position aligner")

                except Exception as e:
                    self.logger.error(f"Failed to process sample {sample_path.name}: {e}")
                    continue

        self.logger.info(f"Parallel sample addition completed: {len(self.active_samples)} samples added")

    def _calculate_chunked_processor_params(self, use_gpu: bool) -> Dict[str, Union[int, float]]:
        """
        Dynamically calculate optimal ChunkedGenomicProcessor parameters based on available resources.
        Uses latest MethylUtils GPU optimizations for maximum performance on GH200.

        Args:
            use_gpu: Whether GPU acceleration is enabled

        Returns:
            Dictionary with chunk_size_positions, max_workers, and memory_limit_gb
        """
        from methyl_utils import get_memory_usage, is_gpu_available

        # Get current memory usage from MethylUtils
        memory_info = get_memory_usage()

        # Extract available memory (accounting for current usage)
        system_memory_total_gb = self.memory_manager.system_memory_limit_gb
        system_memory_used_gb = memory_info.get('system_memory_mb', 0) / 1024
        system_memory_available_gb = system_memory_total_gb - system_memory_used_gb

        # GPU memory information
        gpu_available_gb = 0.0
        gpu_free_gb = 0.0
        if use_gpu and is_gpu_available():
            gpu_available_gb = memory_info.get('gpu_memory_gb', 0)
            gpu_free_gb = memory_info.get('gpu_free_gb', 0)

        self.logger.debug(f"Memory status - System: {system_memory_available_gb:.1f}GB available "
                         f"({system_memory_total_gb:.1f}GB total), "
                         f"GPU: {gpu_free_gb:.1f}GB free ({gpu_available_gb:.1f}GB used)")

        # Use latest MethylUtils GPU-optimized chunk sizing for genome-scale processing
        # Target: 95% GPU utilization with 500M position chunks for optimal performance
        if use_gpu and gpu_free_gb >= 80.0:  # GH200 with sufficient GPU memory
            # Maximum GPU utilization: 500M positions per chunk for 6 total chunks on 3B positions
            chunk_size_positions = 500_000_000  # 500M positions
            memory_limit_gb = min(system_memory_available_gb * 0.8, 350.0)  # Use 80% of available RAM
            max_workers = 1  # Sequential processing for maximum GPU utilization

            self.logger.info(f"Using genome-scale GPU optimization: {chunk_size_positions:,} positions per chunk "
                           f"({memory_limit_gb:.1f}GB RAM limit)")

        elif use_gpu and gpu_free_gb >= 40.0:  # Other GPUs with decent memory
            # High GPU utilization: 100M positions per chunk
            chunk_size_positions = 100_000_000  # 100M positions
            memory_limit_gb = min(system_memory_available_gb * 0.7, 200.0)
            max_workers = 1

            self.logger.info(f"Using high GPU optimization: {chunk_size_positions:,} positions per chunk")

        else:
            # Fallback to memory-optimized chunking for CPU or limited GPU
            # Dynamic chunk size calculation based on context and available memory
            context_base_chunks = {
                'CG': 50_000_000,   # 50M positions - leverage MethylUtils memory efficiency
                'CHG': 25_000_000,  # 25M positions - medium density
                'CHH': 10_000_000   # 10M positions - high density, moderate chunks
            }

            base_chunk_size = context_base_chunks.get(self.ctx, 20_000_000)  # Default 20M

            # Memory-based chunk size adjustment using MethylUtils memory calculations
            memory_limit_gb = system_memory_available_gb * 0.6  # Reserve 40% for other operations

            # Calculate optimal chunk size based on memory per position estimates
            # Use estimated bytes per position from loaded samples if available, otherwise conservative default
            if hasattr(self, 'sample_cache') and self.sample_cache._estimated_bytes_per_sample is not None:
                memory_per_position_kb = self.sample_cache._estimated_bytes_per_sample / 1024  # Convert bytes to KB
            else:
                memory_per_position_kb = 0.15  # Conservative default estimate including overhead

            max_positions_by_memory = int((memory_limit_gb * 1024 * 1024) / memory_per_position_kb)

            chunk_size_positions = min(base_chunk_size, max_positions_by_memory)
            max_workers = max(1, int(system_memory_available_gb / 50))  # 1 worker per 50GB RAM

        # Ensure reasonable minimums and maximums
        chunk_size_positions = max(1_000_000, min(chunk_size_positions, 500_000_000))  # 1M to 500M
        memory_limit_gb = max(10.0, min(memory_limit_gb, system_memory_available_gb * 0.9))
        max_workers = max(1, min(max_workers, 8))  # 1-8 workers

        return {
            'chunk_size_positions': chunk_size_positions,
            'max_workers': max_workers,
            'memory_limit_gb': memory_limit_gb
        }

    def _load_sample_for_alignment_memory_aware(self, sample_path: Path, sample_idx: int) -> Optional['MethylSample']:
        """
        Load a sample for alignment with memory-aware caching.

        Args:
            sample_path: Path to the sample file
            sample_idx: Index of the sample for tracking

        Returns:
            MethylSample instance or None if loading fails
        """
        try:
            # Check memory before loading
            memory_info = self.memory_manager.get_memory_usage()
            available_gb = memory_info.get('available_gb', 350)

            # If memory is getting low, clear cache to free up space
            if available_gb < 50:  # Less than 50GB available
                self.logger.debug(f"Low memory detected ({available_gb:.1f}GB), clearing cache")
                self._clear_sample_cache()

            # Load sample with memory mapping for large files
            sample = self.load_sample(sample_path, memory_map=True)

            if sample is None or len(sample.pos) == 0:
                self.logger.warning(f"Sample {sample_path.name} has no valid data")
                return None

            # Filter positions with coverage to reduce memory usage
            coverage = sample.get_coverage()
            valid_mask = coverage > 0

            if np.any(valid_mask):
                # Create filtered sample
                filtered_sample = sample.create_aligned_sample(valid_mask.astype(bool))
                sample = filtered_sample

                # Log sample statistics for first few samples (only in verbose mode to avoid tqdm interference)
                if sample_idx < 5 and self.verbose:
                    self.logger.debug(f"Sample {sample_idx}: {len(sample.pos):,} positions, "
                                    f"coverage: {coverage[valid_mask].mean():.1f}")

                return sample
            else:
                self.logger.warning(f"Sample {sample_path.name} has no positions with coverage")
                return None

        except Exception as e:
            self.logger.error(f"Failed to load sample {sample_path}: {e}")
            return None

    @property
    def cache_enabled(self) -> bool:
        
        return self._cache_enabled
    
    @cache_enabled.setter
    def cache_enabled(self, value: bool) -> None:

        if not isinstance(value, bool):
            raise TypeError("cache_enabled must be a boolean")

        self._cache_enabled = value

        if not value:
            # Clear cache when disabling
            self._clear_sample_cache()
            self.logger.info("Sample caching disabled")
        else:
            self.logger.info("Sample caching enabled")

    def _load_sample_for_alignment_memory_aware(self, sample_path: Path, sample_idx: int) -> Optional['MethylSample']:
        """
        Load a sample for alignment with memory-aware caching.

        Args:
            sample_path: Path to the sample file
            sample_idx: Index of the sample for tracking

        Returns:
            MethylSample instance or None if loading fails
        """
        try:
            # Check memory before loading
            memory_info = self.memory_manager.get_memory_usage()
            available_gb = memory_info.get('available_gb', 350)

            # If memory is getting low, clear cache to free up space
            if available_gb < 50:  # Less than 50GB available
                self.logger.debug(f"Low memory detected ({available_gb:.1f}GB), clearing cache")
                self._clear_sample_cache()

            # Load sample with memory mapping for large files
            sample = self.load_sample(sample_path, memory_map=True)

            if sample is None or len(sample.pos) == 0:
                self.logger.warning(f"Sample {sample_path.name} has no valid data")
                return None

            # Filter positions with coverage to reduce memory usage
            coverage = sample.get_coverage()
            valid_mask = coverage > 0

            if np.any(valid_mask):
                # Create filtered sample
                filtered_sample = sample.create_aligned_sample(valid_mask.astype(bool))
                sample = filtered_sample

                # Log sample statistics for first few samples (only in verbose mode to avoid tqdm interference)
                if sample_idx < 5 and self.verbose:
                    self.logger.debug(f"Sample {sample_idx}: {len(sample.pos):,} positions, "
                                    f"coverage: {coverage[valid_mask].mean():.1f}")

                return sample
            else:
                self.logger.warning(f"Sample {sample_path.name} has no positions with coverage")
                return None

        except Exception as e:
            self.logger.error(f"Failed to load sample {sample_path}: {e}")
            return None

    def _monitor_memory_during_loading(self):
        """Monitor memory usage during sample loading and take corrective actions."""
        memory_info = self.memory_manager.get_memory_usage()
        used_percent = memory_info.get('percent_used', 0)

        # If memory usage is too high, clear cache
        if used_percent > 85:
            self.logger.warning(f"High memory usage detected ({used_percent:.1f}%), clearing cache")
            self._clear_sample_cache()

        # Force garbage collection periodically
        import gc
        collected = gc.collect()
        if collected > 0:
            self.logger.debug(f"Garbage collection freed {collected} objects")

    def compute_centroid(self, extended: bool = False):

        if self._centroid is None or len(self._centroid) == 0:
            print("No samples added")
            return np.array([], dtype=get_methyl_dtype(extended))

        if extended:
            # Get centroid as MethylExtendedCentroid
            centroid_sample = self._centroid

            # Convert to numpy array format for saving
            centroid_data = centroid_sample.to_numpy(extended=True)
            return centroid_data
        else:
            # Get centroid and convert to basic format
            centroid_sample = self._centroid

            # Convert to numpy array format for saving (basic format)
            centroid_data = centroid_sample.to_numpy(extended=False)
            return centroid_data

    def save_centroid(self,
        output_dir: str,
        centroid_data=None,
        extended: bool = False
    ) -> Path:

        if centroid_data is None:
            centroid_data = self.compute_centroid(extended=extended)

        if centroid_data is None or len(centroid_data) == 0:
            print("No valid centroid data to save")
            return None

        # Get active sample paths (those currently in the centroid)
        active_sample_paths = self._get_active_sample_paths()
        
        # Get outlier sample paths (those removed during outlier detection)
        # outliers are stored as Path objects to H5 files, so extract parent directories
        outlier_paths = [str(p.parent) if hasattr(p, 'parent') else str(Path(p).parent) 
                        for p in self.outliers] if self.outliers else []

        # Prepare metadata for H5 file
        from datetime import datetime
        metadata = {
            "laboratory": self.laboratory,
            "disease": self.disease,
            "group": self.group,
            "batch": self.batch,
            "chromosome": self.chrom,
            "context": self.ctx,
            "samples_used": active_sample_paths,  # NEW: Active samples in centroid
            "outliers_removed": outlier_paths,     # NEW: Samples removed as outliers
            "creation_date": datetime.now().isoformat(),  # NEW: Creation timestamp
            "min_coverage": self.min_coverage,
            "min_samples": self.min_samples,  # NEW: Minimum samples per position filter
            "alpha": self.α,
            "distance_metrics": [str(m.value) for m in self.distance_metrics],
            "max_iterations": self.max_iterations,
        }

        # Create MethylSample from centroid data with metadata
        # centroid_data is a structured numpy array, convert to DataFrame
        import pandas as pd
        from methyl_utils import MethylSample, MethylBasicCentroid, MethylExtendedCentroid
        
        # Convert structured array to DataFrame
        if isinstance(centroid_data, np.ndarray) and centroid_data.dtype.names:
            # Structured array - convert field by field
            if len(centroid_data) > 0:
                df = pd.DataFrame({name: centroid_data[name] for name in centroid_data.dtype.names})
            else:
                # Empty structured array - create empty DataFrame with expected columns
                df = pd.DataFrame({name: [] for name in centroid_data.dtype.names})
        else:
            # Already a DataFrame or regular array
            df = pd.DataFrame(centroid_data) if not isinstance(centroid_data, pd.DataFrame) else centroid_data
        
        # Apply min_samples filter before saving (safety check)
        if len(df) > 0 and hasattr(df, 'columns') and "N" in df.columns:
            # Filter out positions where N < min_samples
            before_filter = len(df)
            df = df[df['N'] >= self.min_samples].copy()
            after_filter = len(df)
            if before_filter > after_filter:
                if hasattr(self, 'logger') and self.logger is not None:
                    self.logger.warning(
                        f"Filtered out {before_filter - after_filter} positions with N < {self.min_samples} "
                        f"({before_filter} -> {after_filter} positions)"
                    )
                else:
                    print(f"Warning: Filtered out {before_filter - after_filter} positions with N < {self.min_samples}")
            if len(df) == 0:
                error_msg = f"No valid positions after filtering by min_samples={self.min_samples}"
                if hasattr(self, 'logger') and self.logger is not None:
                    self.logger.error("No positions remain after min_samples filter!")
                raise ValueError(error_msg)
        
        # Determine which class to use based on available columns
        if "N" in df.columns:
            if set(MethylExtendedCentroid._required_stats).issubset(df.columns):
                methyl_sample = MethylExtendedCentroid(df, metadata=metadata)
            else:
                methyl_sample = MethylBasicCentroid(df, metadata=metadata)
        else:
            methyl_sample = MethylSample(df, metadata=metadata)

        # Set metadata on the sample before saving
        methyl_sample.metadata = metadata
        
        # Save using MethylSample
        output_path = Path(output_dir)

        # Ensure output directory exists with robust error handling
        try:
            # First ensure parent directories exist
            output_path.parent.mkdir(parents=True, exist_ok=True)
            # Then create the target directory
            output_path.mkdir(exist_ok=True)
            # Verify directory was actually created and is writable
            if not output_path.exists():
                raise OSError(f"Failed to create output directory: {output_path}")
            # Note: os.access may not work correctly in container environments,
            # so we'll rely on the mkdir success and existence check
        except PermissionError as e:
            # Provide more specific error for permission issues
            raise OSError(f"Permission denied creating output directory {output_path}. "
                         f"Please ensure the parent directory is writable: {output_path.parent}. "
                         f"Original error: {e}")
        except Exception as e:
            raise OSError(f"Cannot create output directory {output_path}: {e}")

        filename = f"{self.chrom}-{self.ctx}.h5"
        centroid_path = output_path / filename

        # Save centroid (metadata already embedded in MethylSample)
        # Metadata is already set on methyl_sample.metadata, just save
        methyl_sample.save_to_h5(centroid_path, compressed=True)

        # Store reference to centroid
        self.centroid = centroid_path

        return self.centroid
    
    
    def load_centroid(self, centroid_path: Union[str, Path]) -> 'MethylSample':

        from methyl_utils import MethylSample
        methyl_sample = MethylSample.load_from_h5(centroid_path)

        # Ensure arrays are NumPy arrays
        # Use to_cpu() method instead of manual .get() calls
        return methyl_sample.to_cpu()

    def load_sample(self, sample_path: Union[str, Path], memory_map: bool = True) -> 'MethylSample':
        """
        Load sample with optimized memory management.

        Args:
            sample_path: Path to the sample file
            memory_map: Whether to use memory mapping for large files

        Returns:
            MethylSample instance
        """
        from methyl_utils import MethylSample

        # Use memory mapping for large files to reduce memory footprint
        sample_path_obj = Path(sample_path)
        file_size_gb = sample_path_obj.stat().st_size / (1024**3)

        # Use memory mapping for files > 1GB or when explicitly requested
        use_memory_map = memory_map and file_size_gb > 1.0

        try:
            # Load sample
            methyl_sample = MethylSample.load_from_h5(sample_path)
            if use_memory_map:
                self.logger.debug(f"Loaded {sample_path} ({file_size_gb:.1f}GB)")

            # Convert from CuPy to NumPy if needed (MethylSample structure is trusted)
            methyl_sample = self._ensure_numpy_arrays(methyl_sample)

            # Pre-compute and cache statistical properties if this is a centroid
            if methyl_sample.is_centroid and len(methyl_sample.pos) > 1000:
                # Cache statistical properties to avoid recomputation
                _ = methyl_sample.mean  # Trigger computation and caching
                _ = methyl_sample.variance
                _ = methyl_sample.precision

            return methyl_sample

        except Exception as e:
            self.logger.error(f"Failed to load sample {sample_path}: {e}")
            raise

    def _ensure_numpy_arrays(self, methyl_sample: 'MethylSample') -> 'MethylSample':
        """
        Convert MethylSample arrays from CuPy to NumPy if needed.

        MethylSample properties return Series (pandas/cudf), so we use to_cpu()
        to handle both GPU->CPU conversion and Series->numpy array conversion.

        Args:
            methyl_sample: MethylSample instance

        Returns:
            MethylSample with NumPy arrays (converted from CuPy if needed)
        """
        # Use to_cpu() method which handles both GPU->CPU and Series->numpy conversion
        return methyl_sample.to_cpu()

    def calculate_centroid(self, output_dir: str, extended: bool = False) -> Path:

        print(f"Adding {len(self.samples) + len(self.add_samples)} samples for {self.chrom}-{self.ctx}")

        # Ensure output directory exists before processing
        output_path = Path(output_dir)
        try:
            # First ensure parent directories exist
            output_path.parent.mkdir(parents=True, exist_ok=True)
            # Then create the target directory
            output_path.mkdir(exist_ok=True)
            # Verify directory was actually created
            if not output_path.exists():
                raise OSError(f"Failed to create output directory: {output_path}")
            # Note: os.access may not work correctly in container environments
        except PermissionError as e:
            raise OSError(f"Permission denied creating output directory {output_path}. "
                         f"Please ensure the parent directory is writable: {output_path.parent}. "
                         f"Original error: {e}")
        except Exception as e:
            raise OSError(f"Cannot create output directory {output_path}: {e}")

        # Add all samples in parallel
        self.add_samples_parallel()

        # Check if any samples were successfully added
        if len(self.active_samples) == 0:
            raise RuntimeError("Failed to compute centroid: no samples were successfully added")

        # Compute and save centroid
        centroid = self.compute_centroid(extended=extended)
        if centroid is None or len(centroid) == 0:
            raise RuntimeError("Failed to compute centroid: no samples were successfully added")

        centroid_path = self.save_centroid(output_dir, centroid, extended=extended)
        if centroid_path is None:
            raise RuntimeError("Failed to save centroid: no valid data to save")
        
        return centroid_path

    def compute_centroid_chunked(self, extended: bool = False, chunk_size_positions: int = 2_000_000) -> Optional[np.ndarray]:
        """
        Compute centroid using chunked processing for memory efficiency.

        This method processes the genome in chunks to handle very large datasets
        that exceed available memory, especially for chromosome 1 contexts with
        tens of millions of positions. Now uses MethylUtils GPU optimizations.

        Args:
            extended: Whether to compute extended centroid with statistics
            chunk_size_positions: Number of positions to process per chunk

        Returns:
            Centroid data as numpy array, or None if computation fails
        """
        with self.performance_profiler.profile_operation("chunked_centroid_computation"):
            # Use MethylUtils GPU cleanup for safe resource management
            memory_manager = get_memory_manager()

            self.logger.info(f"Computing centroid using chunked processing (chunk size: {chunk_size_positions:,} positions)")

            # Get all unique positions across all samples
            all_positions = set()
            if self._centroid is None or len(self._centroid) == 0:
                self.logger.warning("No samples available for centroid computation")
                return None

            # Get positions from centroid
            centroid_positions = np.asarray(self._centroid.pos.values, dtype=np.uint32)
            all_positions = set(centroid_positions)

            total_positions = len(all_positions)
            self.logger.info(f"Found {total_positions:,} unique positions across all samples")

            if total_positions == 0:
                self.logger.warning("No positions found in samples")
                return None

            # Sort positions for chunking
            sorted_positions = np.array(sorted(all_positions), dtype=np.uint32)

            # Process in chunks
            chunk_results = []
            total_chunks = (total_positions + chunk_size_positions - 1) // chunk_size_positions

            self.logger.info(f"Processing {total_chunks} chunks...")

            for chunk_idx in tqdm(range(total_chunks), desc="Processing chunks"):
                start_pos = chunk_idx * chunk_size_positions
                end_pos = min(start_pos + chunk_size_positions, total_positions)
                chunk_positions = sorted_positions[start_pos:end_pos]

                with self.performance_profiler.profile_operation(f"chunk_{chunk_idx}_processing"):
                    chunk_centroid = self._compute_centroid_for_positions(chunk_positions, extended)
                    if chunk_centroid is not None:
                        chunk_results.append(chunk_centroid)

            if not chunk_results:
                self.logger.error("No chunks produced valid centroid data")
                return None

            # Combine chunk results
            self.logger.info(f"Combining {len(chunk_results)} chunk results...")
            final_centroid = self._combine_chunked_centroids(chunk_results, extended)

            # Ensure GPU cleanup after chunked processing
            memory_manager.force_gpu_cleanup()

            self.logger.info("Chunked centroid computation completed")
            return final_centroid

    def _compute_centroid_for_positions(self, positions: np.ndarray, extended: bool = False) -> Optional[np.ndarray]:
        """
        Compute centroid for a specific set of positions.

        Args:
            positions: Array of genomic positions
            extended: Whether to compute extended statistics

        Returns:
            Centroid data for these positions, or None if no data
        """
        sample_count = len(self.active_samples) if self._centroid is not None else 0
        if sample_count == 0:
            return None

        # Initialize arrays for accumulation
        pos_accum = []
        mC_accum = np.zeros(len(positions), dtype=np.uint32)
        uC_accum = np.zeros(len(positions), dtype=np.uint32)
        # Always track N_accum for min_samples filtering, even for non-extended centroids
        N_accum = np.zeros(len(positions), dtype=np.uint32)

        if extended:
            Sx_accum = np.zeros(len(positions), dtype=np.float32)
            Sx2_accum = np.zeros(len(positions), dtype=np.float32)

        # Process each sample for these positions
        for sample_idx in range(sample_count):
            # Load sample directly instead of getting from aligner
            sample_path = self.samples[sample_idx] if sample_idx < len(self.samples) else self.add_samples[sample_idx - len(self.samples)]
            sample_data_obj = self.load_sample(sample_path)
            
            # Align sample to target positions
            aligned_sample = sample_data_obj.align_to_positions(positions)
            if len(aligned_sample) == 0:
                continue
            
            # Convert to CPU first to ensure numpy arrays
            aligned_sample_cpu = aligned_sample.to_cpu()
            aligned_mC = np.asarray(aligned_sample_cpu.mC.values, dtype=np.uint32)
            aligned_uC = np.asarray(aligned_sample_cpu.uC.values, dtype=np.uint32)

            # Accumulate
            mC_accum += aligned_mC
            uC_accum += aligned_uC
            
            # Track per-position sample count (N) for min_samples filtering
            coverage = aligned_mC + aligned_uC
            N_accum += (coverage > 0).astype(np.uint32)
            
            if extended:
                # Calculate methylation level for this sample
                valid_positions = coverage > 0
                if valid_positions.any():
                    methylation_level = np.zeros(len(positions), dtype=np.float32)
                    methylation_level[valid_positions] = aligned_mC[valid_positions] / coverage[valid_positions]

                    Sx_accum += methylation_level
                    Sx2_accum += methylation_level ** 2

        # Filter positions with sufficient coverage
        total_coverage = mC_accum + uC_accum
        valid_positions = total_coverage >= self.min_coverage

        # Apply min_samples filter - filter out positions where N < min_samples
        valid_positions = valid_positions & (N_accum >= self.min_samples)

        if not valid_positions.any():
            return None

        # Create centroid data
        if extended:
            from methyl_utils import get_methyl_dtype
            dtype = get_methyl_dtype(extended=True)
            centroid_data = np.empty(np.sum(valid_positions), dtype=dtype)

            centroid_data['pos'] = positions[valid_positions]
            centroid_data['mC'] = mC_accum[valid_positions]
            centroid_data['uC'] = uC_accum[valid_positions]
            centroid_data['tnc'] = np.zeros(np.sum(valid_positions), dtype=np.uint8)  # Default context
            centroid_data['N'] = N_accum[valid_positions]
            centroid_data['Sx'] = Sx_accum[valid_positions]
            centroid_data['Sx2'] = Sx2_accum[valid_positions]
            # Extended fields would be computed separately if needed

        else:
            from methyl_utils import get_methyl_dtype
            dtype = get_methyl_dtype(extended=False)
            centroid_data = np.empty(np.sum(valid_positions), dtype=dtype)

            centroid_data['pos'] = positions[valid_positions]
            centroid_data['mC'] = mC_accum[valid_positions]
            centroid_data['uC'] = uC_accum[valid_positions]
            centroid_data['tnc'] = np.zeros(np.sum(valid_positions), dtype=np.uint8)  # Default context
            # Use actual per-position N (number of samples that contributed to each position)
            centroid_data['N'] = N_accum[valid_positions]

        return centroid_data

    def _combine_chunked_centroids(self, chunk_results: List[np.ndarray], extended: bool = False) -> Optional[np.ndarray]:
        """
        Combine centroid results from multiple chunks.

        Args:
            chunk_results: List of centroid arrays from chunks
            extended: Whether the centroids are extended

        Returns:
            Combined centroid array
        """
        if not chunk_results:
            return None

        # Concatenate all chunks
        try:
            combined_centroid = np.concatenate(chunk_results)

            # Sort by position
            sort_idx = np.argsort(combined_centroid['pos'])
            combined_centroid = combined_centroid[sort_idx]

            self.logger.info(f"Combined centroid: {len(combined_centroid):,} positions")
            return combined_centroid

        except Exception as e:
            self.logger.error(f"Failed to combine chunked centroids: {e}")
            return None

    def _load_sample(self, sample_path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Load sample with intelligent caching and memory management.

        Args:
            sample_path: Path to the sample file

        Returns:
            Tuple of (pos, mC, uC) arrays
        """
        # Use intelligent cache if enabled
        if self.cache_enabled:
            # Define loader function for cache
            def sample_loader(path: Path) -> 'MethylSample':
                return self.load_sample(path, memory_map=True)

            cached_sample = self.sample_cache.get(sample_path, sample_loader)
            if cached_sample is not None:
                # Ensure sample is on CPU and get numpy arrays
                cached_sample = cached_sample.to_cpu()
                # Extract sorted arrays from cached MethylSample
                pos_vals = cached_sample.pos.values if hasattr(cached_sample.pos, 'values') else np.asarray(cached_sample.pos)
                mC_vals = cached_sample.mC.values if hasattr(cached_sample.mC, 'values') else np.asarray(cached_sample.mC)
                uC_vals = cached_sample.uC.values if hasattr(cached_sample.uC, 'values') else np.asarray(cached_sample.uC)
                sort_idx = np.argsort(pos_vals)
                return (
                    pos_vals[sort_idx],
                    mC_vals[sort_idx],
                    uC_vals[sort_idx]
                )

        # Fallback: load without caching
        try:
            methyl_sample = self.load_sample(sample_path, memory_map=True)
            
            # Ensure sample is on CPU and get numpy arrays
            methyl_sample = methyl_sample.to_cpu()
            
            # Get underlying numpy arrays from Series properties
            pos_vals = methyl_sample.pos.values if hasattr(methyl_sample.pos, 'values') else np.asarray(methyl_sample.pos)
            mC_vals = methyl_sample.mC.values if hasattr(methyl_sample.mC, 'values') else np.asarray(methyl_sample.mC)
            uC_vals = methyl_sample.uC.values if hasattr(methyl_sample.uC, 'values') else np.asarray(methyl_sample.uC)

            # Sort by position
            sort_idx = np.argsort(pos_vals)
            sorted_pos = pos_vals[sort_idx]
            sorted_mC = mC_vals[sort_idx]
            sorted_uC = uC_vals[sort_idx]

            return sorted_pos, sorted_mC, sorted_uC

        except Exception as e:
            self.logger.error(f"Error loading sample {sample_path}: {e}")
            # Return empty arrays on error
            return (
                np.array([], dtype=np.uint32),
                np.array([], dtype=np.uint32),
                np.array([], dtype=np.uint32),
            )


    def process_large_sample_chunked(self, sample_path: Path, chunk_size: int = 1_000_000) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:

        self.logger.info(f"Processing large sample {sample_path.name} in chunks")

        # Create a processing function for chunks
        def process_sample_chunk(chunk_data, **kwargs):
    
            pos = chunk_data.get('pos', np.array([]))
            mC = chunk_data.get('mC', np.array([]))
            uC = chunk_data.get('uC', np.array([]))

            # Filter for valid positions (some coverage)
            if len(mC) > 0 and len(uC) > 0:
                coverage = mC + uC
                valid_mask = coverage >= self.min_coverage
                return {
                    'pos': pos[valid_mask],
                    'mC': mC[valid_mask],
                    'uC': uC[valid_mask],
                    'positions_processed': np.sum(valid_mask)
                }
            else:
                return {
                    'pos': np.array([], dtype=np.uint32),
                    'mC': np.array([], dtype=np.uint32),
                    'uC': np.array([], dtype=np.uint32),
                    'positions_processed': 0
                }

        # Configure chunked processor for this sample
        self.chunked_processor.chunk_size_positions = chunk_size

        # Process the file in chunks
        results = self.chunked_processor.process_file_chunked(
            sample_path,
            process_sample_chunk,
            self.output_dir / "temp_chunks",
            cleanup_temp=True
        )

        # Aggregate results from all chunks
        all_pos = []
        all_mC = []
        all_uC = []

        for result in results.get('chunk_results', []):
            if result.success and result.data['positions_processed'] > 0:
                all_pos.append(result.data['pos'])
                all_mC.append(result.data['mC'])
                all_uC.append(result.data['uC'])

        if all_pos:
            # Concatenate all chunks
            return (
                np.concatenate(all_pos),
                np.concatenate(all_mC),
                np.concatenate(all_uC)
            )
        else:
            # Return empty arrays if no valid data
            return (
                np.array([], dtype=np.uint32),
                np.array([], dtype=np.uint32),
                np.array([], dtype=np.uint32)
            )

       

    def find_most_extreme_outlier_multi_metric(self) -> Tuple[Optional[Path], Tuple[bool, int], float]:

        # Only consider active samples (those still in the centroid calculation)
        active_sample_paths: List[Path] = []
        active_sample_indices: List[Tuple[bool, int]] = []

        for sample_id in self.active_samples:
            is_new_sample: bool
            sample_index: int
            is_new_sample, sample_index = sample_id
            sample_path: Path = (
                self.add_samples[sample_index]
                if is_new_sample
                else self.samples[sample_index]
            )
            active_sample_paths.append(sample_path)
            active_sample_indices.append(sample_id)

        if len(active_sample_paths) == 0:
            return None, (False, 0), 0.0

        # Calculate distances for all metrics and all samples
        sample_distances, sample_p_values = self._calculate_all_metrics(active_sample_paths)

        # Export CSV with multi-metric distance results (always, regardless of outlier detection)
        self._export_multi_metric_distance_csv(active_sample_paths, sample_distances, sample_p_values)

        # Handle outlier detection based on min_metrics_agree setting
        if self.min_metrics_agree == 0:
            # Use General Simes formula for combining p-values
            simes_p_values = []
            for idx in range(len(active_sample_paths)):
                # Collect p-values for this sample across all metrics
                sample_p_vals = [sample_p_values[metric][idx] for metric in self.distance_metrics]
                # Calculate Simes combined p-value
                simes_p = self._calculate_simes_p_value(sample_p_vals)
                simes_p_values.append(simes_p)

            simes_p_values = np.array(simes_p_values)

            # Find samples that are outliers according to Simes p-value < α
            qualified_outliers = simes_p_values < self.α

            if not np.any(qualified_outliers):
                # No samples qualify as outliers
                return None, (False, 0), 0.0

            # Find the most extreme outlier (lowest Simes p-value)
            qualified_indices = np.where(qualified_outliers)[0]
            most_extreme_idx = qualified_indices[np.argmin(simes_p_values[qualified_indices])]
            most_extreme_p_value = simes_p_values[most_extreme_idx]

        else:
            # Use consensus approach: require min_metrics_agree metrics to agree
            outlier_votes = np.zeros(len(active_sample_paths))

            for metric in self.distance_metrics:
                p_values = sample_p_values[metric]
                # Count samples that are outliers (p-value < α) for this metric
                outlier_mask = p_values < self.α
                outlier_votes += outlier_mask.astype(int)

            # Find samples that have enough votes to be considered outliers
            qualified_outliers = outlier_votes >= self.min_metrics_agree

            if not np.any(qualified_outliers):
                # No samples qualify as outliers
                return None, (False, 0), 0.0

            # Among qualified outliers, find the one with the lowest combined p-value
            # (most extreme outlier)
            qualified_indices = np.where(qualified_outliers)[0]

            # Calculate combined p-values for qualified samples
            combined_p_values = []
            for idx in qualified_indices:
                # Use the minimum p-value across all metrics (most conservative)
                min_p_value = min(sample_p_values[metric][idx] for metric in self.distance_metrics)
                combined_p_values.append(min_p_value)

            # Find the most extreme outlier among qualified samples (lowest p-value)
            most_extreme_idx = qualified_indices[np.argmin(combined_p_values)]
            most_extreme_p_value = combined_p_values[np.argmin(combined_p_values)]
        
        # Print information about the multi-metric analysis
        print(f"Iteration {self.current_iteration}: Multi-metric outlier analysis")
        print(f"  Metrics used: {[m.value for m in self.distance_metrics]}")

        if self.min_metrics_agree == 0:
            print("  Method: General Simes formula")
            print(f"  Qualified outliers: {np.sum(qualified_outliers)}/{len(active_sample_paths)} (Simes p-value < {self.α})")
            print(f"  Most extreme outlier: {active_sample_paths[most_extreme_idx]}")
            print(f"  Simes p-value: {most_extreme_p_value:.6f}")
        else:
            print(f"  Method: Consensus (min {self.min_metrics_agree} metrics agree)")
            print(f"  Min metrics required: {self.min_metrics_agree}")
            print(f"  Qualified outliers: {np.sum(qualified_outliers)}/{len(active_sample_paths)}")
            print(f"  Most extreme outlier: {active_sample_paths[most_extreme_idx]}")
            print(f"  Combined p-value: {most_extreme_p_value:.6f}")
        
        # Print individual metric results for the selected outlier
        for metric in self.distance_metrics:
            p_val = sample_p_values[metric][most_extreme_idx]
            dist_val = sample_distances[metric][most_extreme_idx]
            print(f"    {metric.value}: distance={dist_val:.6f}, p-value={p_val:.6f}")

        # Generate histogram for the primary metric (first in the list)
        if self.distance_metrics:
            primary_metric = self.distance_metrics[0]
            primary_distances = sample_distances[primary_metric]
            primary_p_values = sample_p_values[primary_metric]
            
            # Calculate statistics for the primary metric
            μ = float(np.nanmean(primary_distances))
            σ = float(np.nanstd(primary_distances))
            obs_value = float(primary_distances[most_extreme_idx])
            
            # Determine which distribution was used for p-value calculation
            from scipy.stats import norm, beta
            
            try:
                if σ > 0 and 0 < μ < 1:
                    # Try Beta distribution first
                    beta_a = μ * μ * (1 - μ) / (σ * σ) - μ
                    beta_b = beta_a * (1 - μ) / μ
                    
                    if beta_a > 0 and beta_b > 0:
                        # Use method of moments
                        beta_loglik = np.sum(beta.logpdf(primary_distances, beta_a, beta_b, loc=0, scale=1))
                        normal_loglik = np.sum(norm.logpdf(primary_distances, μ, σ))
                        
                        beta_aic = 2 * 2 - 2 * beta_loglik
                        normal_aic = 2 * 2 - 2 * normal_loglik
                        
                        use_beta = beta_aic < normal_aic
                    else:
                        use_beta = False
                else:
                    use_beta = False
                    
                if use_beta:
                    fitted_dist = "beta"
                    fitted_par1 = beta_a
                    fitted_par2 = beta_b
                else:
                    fitted_dist = "normal"
                    fitted_par1 = μ
                    fitted_par2 = σ
                    
            except Exception:
                fitted_dist = "normal"
                fitted_par1 = μ
                fitted_par2 = σ
            

            # Generate histogram for the primary metric
            self._save_distance_histogram(
                primary_distances,
                fitted_dist,
                fitted_par1,
                fitted_par2,
                obs_value,
                most_extreme_p_value,
                sample=str(active_sample_paths[most_extreme_idx]),
                metric=primary_metric,
            )

        return active_sample_paths[most_extreme_idx], active_sample_indices[most_extreme_idx], most_extreme_p_value

    def _calculate_all_metrics(self, active_sample_paths: List[Path]) -> Tuple[Dict[DistanceMetric, np.ndarray], Dict[DistanceMetric, np.ndarray]]:

        sample_distances = {}  # metric -> list of distances for each sample
        sample_p_values = {}   # metric -> list of p-values for each sample
        
        for metric in self.distance_metrics:
            distances = self._calculate_distances_for_metric(active_sample_paths, metric)
            p_values = self._calculate_p_values_for_distances(distances, metric)
            sample_distances[metric] = distances
            sample_p_values[metric] = p_values
            
        return sample_distances, sample_p_values

    def _calculate_distances_for_metric(self, sample_paths: List[Path], metric: DistanceMetric) -> np.ndarray:

        def calculate_sample_distance(sample_path: Path) -> float:

            try:
                # Load MethylSample once and reuse it
                sample_obj = self.load_sample(sample_path)

                # Align sample to centroid positions
                if self._centroid is None:
                    return 0.0
                
                centroid_positions = np.asarray(self._centroid.pos.values, dtype=np.uint32)
                aligned_sample = sample_obj.align_to_positions(centroid_positions)
                
                if len(aligned_sample) == 0:
                    return 0.0  # No common positions

                # Get aligned data - ensure we convert to CPU numpy arrays
                aligned_sample_cpu = aligned_sample.to_cpu()
                sample_mC = np.asarray(aligned_sample_cpu.mC.values, dtype=np.uint32)
                sample_uC = np.asarray(aligned_sample_cpu.uC.values, dtype=np.uint32)
                common_pos = np.asarray(aligned_sample_cpu.pos.values, dtype=np.uint32)

                # Get centroid as MethylSample and valid positions
                centroid_sample = self._centroid
                if centroid_sample is None:
                    return None
                # Get valid positions (those with coverage >= min_coverage)
                centroid_sample_cpu = centroid_sample.to_cpu()
                coverage = np.asarray(centroid_sample_cpu.coverage.values, dtype=np.uint32)
                valid_mask = coverage >= self._min_coverage
                
                # Convert pos.values to numpy array before indexing
                pos_values = np.asarray(centroid_sample_cpu.pos.values, dtype=np.uint32)
                valid_pos = pos_values[valid_mask]

                # Find indices of common positions in the centroid sample
                centroid_pos_values = pos_values
                common_indices = np.searchsorted(centroid_pos_values, common_pos)
                
                # Verify indices are valid (positions match exactly and within bounds)
                valid_idx_mask = (common_indices < len(centroid_pos_values))
                if np.any(valid_idx_mask):
                    # Check position matches for valid indices
                    position_matches = centroid_pos_values[common_indices[valid_idx_mask]] == common_pos[valid_idx_mask]
                    valid_indices_mask = np.zeros(len(common_indices), dtype=bool)
                    valid_indices_mask[valid_idx_mask] = position_matches
                else:
                    valid_indices_mask = np.zeros(len(common_indices), dtype=bool)
                
                if not np.any(valid_indices_mask):
                    return 0.0  # No valid common positions
                
                # Extract centroid data only for common positions with valid indices
                # Convert to numpy arrays before indexing to avoid pandas indexing issues
                N_values = np.asarray(centroid_sample_cpu.N.values, dtype=np.uint32)
                Sx_values = np.asarray(centroid_sample_cpu.Sx.values, dtype=np.float32)
                
                # Only use valid indices - ensure they're numpy integers
                valid_common_indices = np.asarray(common_indices[valid_indices_mask], dtype=np.int64)
                common_centroid_N = N_values[valid_common_indices]
                common_Sx = Sx_values[valid_common_indices]
                
                # Also filter sample arrays to match
                sample_mC = sample_mC[valid_indices_mask]
                sample_uC = sample_uC[valid_indices_mask]

                # Calculate centroid methylation levels for common positions only
                # Use np.where instead of np.divide with where parameter for CuPy compatibility
                with np.errstate(divide='ignore', invalid='ignore'):
                    centroid_methylation = np.where(
                        common_centroid_N > 0,
                        common_Sx.astype(np.float64) / common_centroid_N.astype(np.float64),
                        0.0
                    ).astype(np.float32)

                # Calculate sample methylation levels
                sample_total = sample_mC + sample_uC
                with np.errstate(divide='ignore', invalid='ignore'):
                    sample_methylation = np.where(
                        sample_total > 0,
                        sample_mC.astype(np.float64) / sample_total.astype(np.float64),
                        0.0
                    ).astype(np.float32)

                # Clip both methylation levels to valid range [0, 1]
                centroid_methylation = np.clip(centroid_methylation, 0.0, 1.0)
                sample_methylation = np.clip(sample_methylation, 0.0, 1.0)

                # Debug: Check array shapes
                if sample_methylation.shape != centroid_methylation.shape:
                    print(f"Shape mismatch in {sample_path}:")
                    print(f"  Centroid shape: {centroid_methylation.shape}")
                    print(f"  Sample shape: {sample_methylation.shape}")
                    print(f"  Common positions: {len(sample_mC)}")
                    return 0.0                  # Skip this sample due to shape mismatch

                # Convert methylation probabilities to Beta distribution parameters
                a1, b1 = get_sample_beta_mom(sample_methylation, sample_total)
                a2, b2 = get_sample_beta_mom(centroid_methylation, common_centroid_N)

                # Calculate distance using MethylUtils auto_compute_distance
                distance = auto_compute_distance(a1, b1, a2, b2, metric=metric.to_factory_name())

                # Handle NaN and infinite values that can occur when distance cannot be meaningfully computed
                # Filter out invalid values and compute mean of valid distances
                valid_distances = distance[np.isfinite(distance) & ~np.isnan(distance)]
                if len(valid_distances) == 0:
                    # No valid distances - return a large distance value to indicate dissimilarity
                    return 1.0

                mean_distance = float(np.mean(valid_distances))
                if np.isnan(mean_distance) or np.isinf(mean_distance):
                    # Fallback in case mean is still invalid
                    return 1.0

                return mean_distance
            except Exception as e:
                # Check if this is a GPU memory error and we should fallback to CPU
                error_msg = str(e).lower()
                if self._using_gpu and ('out of memory' in error_msg or 'cuda' in error_msg or 'gpu' in error_msg):
                    self.logger.warning(f"GPU memory error in distance calculation: {e}")
                    self._fallback_to_cpu_processing()
                    # Retry with CPU (this will be handled by the calling context)
                    return None  # Signal to retry
                else:
                    print(f"Error calculating {metric.value} distance for {sample_path}: {e}")
                    return 0.0

        # Try processing all samples at once first for maximum performance
        # Only fall back to batching if GPU memory issues occur
        distances = []
        retry_samples = []
        gpu_memory_issue = False

        try:
            # Attempt to process all samples at once for maximum performance
            self.logger.debug(f"Attempting to process all {len(sample_paths)} samples at once for maximum performance")

            for sample_path in tqdm(sample_paths, desc=f"Calculating {metric.value} distances", leave=True):
                distance = calculate_sample_distance(sample_path)

                # Handle GPU memory errors by falling back to CPU and retrying
                if distance is None:  # GPU memory error occurred
                    gpu_memory_issue = True
                    retry_samples.append(sample_path)
                    self.logger.warning(f"GPU memory issue detected, will retry in batches")
                    break
                else:
                    distances.append(distance)

        except Exception as e:
            gpu_memory_issue = True
            self.logger.warning(f"Error during bulk processing, falling back to batching: {e}")

        # If GPU memory issues occurred, retry failed samples in optimized batches
        if gpu_memory_issue and retry_samples:
            self.logger.info(f"Processing {len(retry_samples)} samples in optimized batches due to GPU memory constraints")

            # Use larger batches than the conservative 5-sample limit for better performance
            batch_size = min(15, max(5, len(retry_samples) // 4))  # Adaptive batch sizing

            for i in range(0, len(retry_samples), batch_size):
                batch_paths = retry_samples[i:i + batch_size]

                # Force GPU memory cleanup between batches
                if hasattr(self, 'memory_manager'):
                    self.memory_manager.force_gpu_cleanup()

                for sample_path in tqdm(batch_paths, desc=f"Calculating {metric.value} distances (batch {i//batch_size + 1})", leave=True):
                    distance = calculate_sample_distance(sample_path)
                    if distance is not None:
                        distances.append(distance)

        # Retry failed samples with CPU if we fell back
        if retry_samples and not self._using_gpu:
            self.logger.info(f"Retrying {len(retry_samples)} samples with CPU processing")
            for sample_path in tqdm(retry_samples, desc=f"Retrying {metric.value} distances with CPU", leave=True):
                distance = calculate_sample_distance(sample_path)
                if distance is not None:
                    distances.append(distance)

        return np.array(distances)

    def _calculate_p_values_for_distances(self, distances: np.ndarray[float], metric: DistanceMetric) -> np.ndarray[float]:

        if len(distances) == 0:
            return np.array([])

        from scipy.stats import norm, beta

        μ: float = float(np.nanmean(distances))
        σ: float = float(np.nanstd(distances))

        # Handle case where all distances are the same (no variation)
        if σ == 0 or np.isnan(σ):
            # When there's no variation, check if the distances represent extreme values
            if μ >= 0.9:  # Close to maximum distance (1.0 for most metrics)
                # All samples have maximum distance - they are all extreme outliers
                return np.full_like(distances, 1e-10, dtype=float)  # Very small p-values
            elif μ <= 0.1:  # Close to minimum distance (0.0)
                # All samples are very similar to centroid - none are outliers
                return np.full_like(distances, 0.8, dtype=float)  # Large p-values
            else:
                # Moderate distances with no variation - cannot determine outliers
                return np.full_like(distances, 0.5, dtype=float)

        # Statistical distribution analysis
        try:          
            if σ > 0 and 0 < μ < 1:
                beta_a = None
                beta_b = None
                
                # Method of moments estimation for Beta parameters
                beta_a = μ * μ * (1 - μ) / (σ * σ) - μ
                beta_b = beta_a * (1 - μ) / μ
                
                # Check if parameters are valid
                if beta_a <= 0 or beta_b <= 0:
                    beta_a = None
                    beta_b = None
                
                # Fallback to MLE if method of moments failed
                if beta_a is None or beta_b is None:
                    try:
                        # Use expensive but robust MLE fitting as fallback
                        beta_params = beta.fit(distances, floc=0, fscale=1)
                        beta_a, beta_b, _, _ = beta_params
                    except Exception:
                        # Final fallback to simple estimation
                        beta_a = 2.0
                        beta_b = 2.0

                # Use Beta distribution for p-value if it fits better (based on AIC)
                beta_loglik = np.sum(beta.logpdf(distances, beta_a, beta_b, loc=0, scale=1))
                normal_loglik = np.sum(norm.logpdf(distances, μ, σ))

                # AIC comparison (lower AIC = better fit)
                beta_aic = 2 * 2 - 2 * beta_loglik  # 2 parameters for Beta
                normal_aic = 2 * 2 - 2 * normal_loglik  # 2 parameters for Normal

                use_beta = beta_aic < normal_aic and beta_a > 0 and beta_b > 0

                if use_beta:
                    # Use Beta distribution for p-value calculation
                    p_values = 1 - beta.cdf(distances, beta_a, beta_b, loc=0, scale=1)
                    p_values = np.clip(p_values, 0.0, 1.0)  # Ensure bounded [0,1]
                else:
                    # Use Normal distribution when Beta fitting is not appropriate
                    p_values = 1 - norm.cdf(distances, μ, σ) if σ > 0 else np.ones_like(distances)
                    p_values = np.clip(p_values, 0.0, 1.0)  # Ensure bounded [0,1]
            else:
                # When Beta fitting is not appropriate (e.g., μ not in [0,1] or σ = 0)
                # use Normal distribution
                if σ > 0:
                    p_values = 1 - norm.cdf(distances, μ, σ)
                else:
                    # When σ = 0, all distances are the same
                    # If all distances are at the maximum possible value, p-value should be 0
                    # If all distances are at the minimum possible value, p-value should be 1
                    if μ >= 0.99:  # Close to maximum (e.g., Hellinger = 1.0)
                        p_values = np.zeros_like(distances)
                    elif μ <= 0.01:  # Close to minimum (e.g., Hellinger = 0.0)
                        p_values = np.ones_like(distances)
                    else:
                        # For intermediate values, use uniform distribution
                        p_values = np.full_like(distances, 0.5)
                p_values = np.clip(p_values, 0.0, 1.0)  # Ensure bounded [0,1]

        except Exception as e:
            # Fallback to Normal distribution if Beta fitting fails
            print(f"  Beta fitting failed for {metric.value} ({e}), using Normal distribution")
            if σ > 0:
                p_values = 1 - norm.cdf(distances, μ, σ)
            else:
                # When σ = 0, all distances are the same
                if μ >= 0.99:  # Close to maximum (e.g., Hellinger = 1.0)
                    p_values = np.zeros_like(distances)
                elif μ <= 0.01:  # Close to minimum (e.g., Hellinger = 0.0)
                    p_values = np.ones_like(distances)
                else:
                    # For intermediate values, use uniform distribution
                    p_values = np.full_like(distances, 0.5)
            p_values = np.clip(p_values, 0.0, 1.0)  # Ensure bounded [0,1]

        return p_values

    def _calculate_simes_p_value(self, p_values: List[float]) -> float:
        """
        Calculate the combined p-value using the General Simes formula.

        The Simes test combines multiple p-values by taking:
        p_simes = min_{i=1 to k} (k * p_{(i)} / i)

        where p_{(i)} is the i-th smallest p-value in the set of k p-values.

        Args:
            p_values: List of p-values to combine

        Returns:
            Combined p-value using Simes method
        """
        if not p_values:
            return 1.0

        # Remove any NaN or invalid p-values
        valid_p_values = [p for p in p_values if not np.isnan(p) and 0 <= p <= 1]

        if not valid_p_values:
            return 1.0

        k = len(valid_p_values)
        if k == 1:
            return valid_p_values[0]

        # Sort p-values in ascending order (p_{(1)} <= p_{(2)} <= ... <= p_{(k)})
        sorted_p_values = sorted(valid_p_values)

        # Calculate Simes combined p-value: min_{i=1 to k} (k * p_{(i)} / i)
        simes_values = [k * sorted_p_values[i] / (i + 1) for i in range(k)]
        p_simes = min(simes_values)

        # Ensure the result is bounded [0, 1]
        return min(max(p_simes, 0.0), 1.0)

    def find_most_extreme_outlier(self) -> Tuple[Optional[Path], Tuple[bool, int], float]:

        # Use multi-metric approach if multiple metrics are configured or General Simes is requested
        if len(self.distance_metrics) > 1 or self.min_metrics_agree != 1:
            return self.find_most_extreme_outlier_multi_metric()

        # Use advanced statistical outlier detection for single metric with sufficient samples
        if total_samples >= 10:  # Need enough samples for statistical reliability
            try:
                return self._find_most_extreme_outlier_advanced_statistical()
            except Exception as e:
                self.logger.warning(f"Advanced statistical outlier detection failed, falling back: {e}")

        # Use probabilistic outlier detection for sufficient sample sizes (>=20)
        # since methylation data often follows Beta distributions better than normal
        total_samples = len(self.active_samples)
        min_samples_for_probabilistic = 20  # Minimum samples for reliable probabilistic modeling

        if total_samples >= min_samples_for_probabilistic:
            try:
                return self._find_most_extreme_outlier_probabilistic()
            except Exception as e:
                self.logger.warning(f"Probabilistic outlier detection failed, falling back to statistical method: {e}")
                # Fall back to statistical method

        # Use statistical outlier detection for moderate sample sizes (>=5)
        min_samples_for_stats = 5  # Minimum samples for reliable statistical outlier detection

        if total_samples >= min_samples_for_stats:
            try:
                return self._find_most_extreme_outlier_statistical()
            except Exception as e:
                self.logger.warning(f"Statistical outlier detection failed, falling back to simple method: {e}")
                # Fall back to simple max distance method

        # Fall back to single-metric approach for backward compatibility
        return self._find_most_extreme_outlier_single_metric()

    def _find_most_extreme_outlier_advanced_statistical(self) -> Tuple[Optional[Path], Tuple[bool, int], float]:
        """
        Find the most extreme outlier using advanced statistical methods from MethylUtils.

        This method leverages MethylUtils statistical testing functions for more robust
        outlier detection, including p-value aggregation and advanced distribution fitting.
        """
        # Only consider active samples
        active_sample_paths: List[Path] = []
        active_sample_indices: List[Tuple[bool, int]] = []

        for sample_id in self.active_samples:
            is_new_sample, sample_index = sample_id
            sample_path = (
                self.add_samples[sample_index]
                if is_new_sample
                else self.samples[sample_index]
            )
            active_sample_paths.append(sample_path)
            active_sample_indices.append(sample_id)

        # Calculate distances for all samples using the configured metric
        distances = []
        valid_samples = []

        for sample_path, sample_id in zip(active_sample_paths, active_sample_indices):
            try:
                # Calculate distance using the configured metric
                distance = self._calculate_sample_distance_for_outlier_detection(sample_path)
                if distance is not None and np.isfinite(distance):
                    distances.append(distance)
                    valid_samples.append((sample_path, sample_id))
                # Skip debug logging during tqdm operations to avoid progress bar interference
            except Exception as e:
                # Skip debug logging during tqdm operations to avoid progress bar interference
                continue

        if len(distances) < 5:  # Need minimum valid samples
            raise ValueError(f"Insufficient valid distance calculations: {len(distances)}")

        distances = np.array(distances)

        # Use MethylUtils statistical testing for robust outlier detection
        from methyl_utils import storey_qvalues, aggregate_pvalues_stouffer

        # Fit normal distribution to distances
        from scipy import stats
        norm_params = stats.norm.fit(distances)
        z_scores = (distances - norm_params[0]) / norm_params[1]

        # Calculate p-values (two-tailed test for outliers)
        p_values = 2 * (1 - stats.norm.cdf(np.abs(z_scores)))

        # Apply q-value correction for multiple testing
        q_values = storey_qvalues(p_values)

        # Aggregate p-values using Stouffer's method for more robust outlier detection
        if len(q_values) > 1:
            try:
                # Use Stouffer's method to combine evidence across different statistical tests
                combined_p = aggregate_pvalues_stouffer(q_values)
                # Find sample with most significant combined p-value
                most_extreme_idx = np.argmin(combined_p)
                significance_score = 1.0 - combined_p[most_extreme_idx]
            except Exception:
                # Fallback to minimum q-value if aggregation fails
                most_extreme_idx = np.argmin(q_values)
                significance_score = 1.0 - q_values[most_extreme_idx]
        else:
            most_extreme_idx = 0
            significance_score = 1.0 - q_values[0]

        selected_sample_path, selected_sample_id = valid_samples[most_extreme_idx]

            # Skip debug logging during tqdm operations to avoid progress bar interference

        return selected_sample_path, selected_sample_id, significance_score

    def _find_most_extreme_outlier_probabilistic(self) -> Tuple[Optional[Path], Tuple[bool, int], float]:
        """
        Find the most extreme outlier using probabilistic Beta distribution modeling.

        This method fits a Beta distribution to the distance distribution and identifies
        outliers based on their deviation from the fitted model. This is more appropriate
        for methylation data which often follows Beta distributions.
        """
        # Only consider active samples
        active_sample_paths: List[Path] = []
        active_sample_indices: List[Tuple[bool, int]] = []

        for sample_id in self.active_samples:
            is_new_sample, sample_index = sample_id
            sample_path = (
                self.add_samples[sample_index]
                if is_new_sample
                else self.samples[sample_index]
            )
            active_sample_paths.append(sample_path)
            active_sample_indices.append(sample_id)

        # Get distances for all active samples
        distances = []
        valid_samples = []

        for sample_path, sample_id in zip(active_sample_paths, active_sample_indices):
            try:
                # Calculate distance using the configured metric
                distance = self._calculate_sample_distance_for_outlier_detection(sample_path)
                if distance is not None and np.isfinite(distance):
                    distances.append(distance)
                    valid_samples.append((sample_path, sample_id))
                # Skip debug logging during tqdm operations to avoid progress bar interference
            except Exception as e:
                # Skip debug logging during tqdm operations to avoid progress bar interference
                continue

        if len(distances) < 5:  # Need minimum valid samples
            raise ValueError(f"Insufficient valid distance calculations: {len(distances)}")

        distances = np.array(distances)

        # Try probabilistic Beta distribution modeling
        try:
            from scipy import stats

            # Clip distances to valid Beta range [0, 1] (Beta distribution is defined on (0,1))
            # Scale distances to [0, 1] range for Beta fitting
            dist_min, dist_max = np.min(distances), np.max(distances)
            if dist_max > dist_min:
                # Scale to [0.001, 0.999] to avoid boundary issues with Beta distribution
                scaled_distances = 0.001 + 0.998 * (distances - dist_min) / (dist_max - dist_min)
            else:
                # All distances are the same
                scaled_distances = np.full_like(distances, 0.5)

            # Fit Beta distribution to the scaled distances
            try:
                beta_params = stats.beta.fit(scaled_distances, floc=0, fscale=1)
                alpha_param, beta_param = beta_params[0], beta_params[1]

                # Calculate log-likelihood of the Beta fit
                log_likelihood_beta = np.sum(stats.beta.logpdf(scaled_distances, alpha_param, beta_param))

                # Also fit normal distribution for comparison
                norm_params = stats.norm.fit(distances)
                log_likelihood_norm = np.sum(stats.norm.logpdf(distances, *norm_params))

                # Use Beta-based outlier detection if Beta fit is significantly better
                # (or if we can't fit normal well)
                use_beta = (log_likelihood_beta > log_likelihood_norm + 2) or np.isnan(log_likelihood_norm)

                if use_beta:
                    # Calculate p-values using Beta CDF
                    # For outlier detection, we want extreme values (very small or very large distances)
                    # So we use two-tailed p-values
                    cdf_values = stats.beta.cdf(scaled_distances, alpha_param, beta_param)
                    p_values = 2 * np.minimum(cdf_values, 1 - cdf_values)  # Two-tailed p-values

                    # Skip debug logging during tqdm operations to avoid progress bar interference
                else:
                    # Fall back to normal distribution
                    z_scores = (distances - norm_params[0]) / norm_params[1]
                    p_values = 2 * (1 - stats.norm.cdf(np.abs(z_scores)))  # Two-tailed p-values

                    # Skip debug logging during tqdm operations to avoid progress bar interference

            except Exception as e:
                # If Beta fitting fails, fall back to normal distribution
                # Skip debug logging during tqdm operations to avoid progress bar interference
                norm_params = stats.norm.fit(distances)
                z_scores = (distances - norm_params[0]) / norm_params[1]
                p_values = 2 * (1 - stats.norm.cdf(np.abs(z_scores)))  # Two-tailed p-values

            # Find the sample with the smallest p-value (most significant outlier)
            min_p_idx = np.argmin(p_values)
            min_p_value = p_values[min_p_idx]

            selected_sample_path, selected_sample_id = valid_samples[min_p_idx]

            # Convert p-value to confidence score (higher confidence = more significant outlier)
            confidence = 1.0 - min_p_value

            # Skip debug logging during tqdm operations to avoid progress bar interference

            return selected_sample_path, selected_sample_id, confidence

        except Exception as e:
            self.logger.error(f"Probabilistic outlier detection failed: {e}")
            raise

    def _find_most_extreme_outlier_statistical(self) -> Tuple[Optional[Path], Tuple[bool, int], float]:
        """
        Find the most extreme outlier using statistical methods.

        This method uses statistical outlier detection based on distance distributions
        when there are sufficient samples for reliable statistical inference.
        """
        # Only consider active samples
        active_sample_paths: List[Path] = []
        active_sample_indices: List[Tuple[bool, int]] = []

        for sample_id in self.active_samples:
            is_new_sample, sample_index = sample_id
            sample_path = (
                self.add_samples[sample_index]
                if is_new_sample
                else self.samples[sample_index]
            )
            active_sample_paths.append(sample_path)
            active_sample_indices.append(sample_id)

        # Collect distance data for all samples
        # Skip debug logging during tqdm operations to avoid progress bar interference

        distances = []
        valid_samples = []

        for sample_path, sample_id in zip(active_sample_paths, active_sample_indices):
            try:
                # Calculate distance using the configured metric
                distance = self._calculate_sample_distance_for_outlier_detection(sample_path)
                if distance is not None and np.isfinite(distance):
                    distances.append(distance)
                    valid_samples.append((sample_path, sample_id))
                # Skip debug logging during tqdm operations to avoid progress bar interference
            except Exception as e:
                # Skip debug logging during tqdm operations to avoid progress bar interference
                continue

        if len(distances) < 5:  # Need minimum valid samples
            raise ValueError(f"Insufficient valid distance calculations: {len(distances)}")

        distances = np.array(distances)

        # Use statistical outlier detection based on modified Z-score
        try:
            # Calculate median and MAD (Median Absolute Deviation)
            median_dist = np.median(distances)
            mad_dist = np.median(np.abs(distances - median_dist))

            # Avoid division by zero
            if mad_dist == 0:
                mad_dist = np.std(distances) + 1e-10

            # Calculate modified Z-scores
            modified_z_scores = 0.6745 * (distances - median_dist) / mad_dist

            # Find the sample with the highest absolute Z-score (most extreme outlier)
            abs_z_scores = np.abs(modified_z_scores)
            max_z_idx = np.argmax(abs_z_scores)
            max_z_score = abs_z_scores[max_z_idx]

            selected_sample_path, selected_sample_id = valid_samples[max_z_idx]

            # Calculate confidence based on the Z-score magnitude
            # Z-score > 3.5 is typically considered extreme outlier
            confidence = min(max_z_score / 3.5, 1.0)

            # Return the Z-score as the outlier measure
            outlier_score = modified_z_scores[max_z_idx]

            # Skip debug logging during tqdm operations to avoid progress bar interference

            return selected_sample_path, selected_sample_id, confidence

        except Exception as e:
            self.logger.error(f"Statistical outlier detection failed: {e}")
            raise

    def _calculate_sample_distance_for_outlier_detection(self, sample_path: Path) -> Optional[float]:
        """
        Calculate distance for a single sample using optimized methods.

        Returns:
            Distance value or None if calculation fails
        """
        try:
            # Load MethylSample once and reuse it
            sample_obj = self.load_sample(sample_path)

            # Align sample to centroid positions
            if self._centroid is None:
                return None
            
            centroid_positions = np.asarray(self._centroid.pos.values, dtype=np.uint32)
            aligned_sample = sample_obj.align_to_positions(centroid_positions)
            
            if len(aligned_sample) == 0:
                return None  # No common positions

            # Get centroid
            centroid_sample = self._centroid
            if centroid_sample is None:
                return None
            
            # Common positions are already in aligned_sample
            common_pos = np.asarray(aligned_sample.pos.values, dtype=np.uint32)
            
            # Get sample data from aligned_sample
            sample_mC = np.asarray(aligned_sample.mC.values, dtype=np.uint32)
            sample_uC = np.asarray(aligned_sample.uC.values, dtype=np.uint32)

            # Align centroid to common positions
            aligned_centroid = centroid_sample.align_to_positions(common_pos)
            if len(aligned_centroid) == 0:
                return None
            
            common_centroid_N = np.asarray(aligned_centroid.N.values, dtype=np.uint32)
            common_Sx = np.asarray(aligned_centroid.Sx.values, dtype=np.float32)

            # Calculate centroid methylation levels
            # Use np.where instead of np.divide with where parameter for CuPy compatibility
            with np.errstate(divide='ignore', invalid='ignore'):
                centroid_methylation = np.where(
                    common_centroid_N > 0,
                    common_Sx.astype(np.float64) / common_centroid_N.astype(np.float64),
                    0.0
                ).astype(np.float32)

            # Calculate sample methylation levels
            sample_total = sample_mC + sample_uC
            with np.errstate(divide='ignore', invalid='ignore'):
                sample_methylation = np.where(
                    sample_total > 0,
                    sample_mC.astype(np.float64) / sample_total.astype(np.float64),
                    0.0
                ).astype(np.float32)

            # Clip to valid range [0, 1]
            centroid_methylation = np.clip(centroid_methylation, 0.0, 1.0)
            sample_methylation = np.clip(sample_methylation, 0.0, 1.0)

            if sample_methylation.shape != centroid_methylation.shape:
                return None  # Shape mismatch

            # Calculate distance using MethylUtils distance metrics for proper statistical analysis
            # Use Jensen-Shannon divergence as primary metric (best for methylation Beta distributions)
            from methyl_utils import auto_compute_distance, get_sample_beta_mom

            # Calculate Beta distribution parameters for both centroid and sample
            a1, b1 = get_sample_beta_mom(sample_methylation, sample_total)
            a2, b2 = get_sample_beta_mom(centroid_methylation, common_centroid_N)

            # Use Jensen-Shannon divergence (optimal for methylation data)
            distance = auto_compute_distance(a1, b1, a2, b2, metric="jensen_shannon")

            return float(distance) if np.isfinite(distance) else None

        except Exception as e:
            # Skip debug logging during tqdm operations to avoid progress bar interference
            return None

    def _find_most_extreme_outlier_single_metric(self) -> Tuple[Optional[Path], Tuple[bool, int], float]:

        # Only consider active samples (those still in the centroid calculation)
        active_sample_paths: List[Path] = []
        active_sample_indices: List[Tuple[bool, int]] = []

        for sample_id in self.active_samples:
            is_new_sample: bool
            sample_index: int
            is_new_sample, sample_index = sample_id
            sample_path: Path = (
                self.add_samples[sample_index]
                if is_new_sample
                else self.samples[sample_index]
            )
            active_sample_paths.append(sample_path)
            active_sample_indices.append(sample_id)

        if len(active_sample_paths) == 0:
            return None, (False, 0), 0.0

        # Try processing all samples at once first for maximum performance
        # Only fall back to batching if GPU memory issues occur
        dists = []
        gpu_memory_issue = False

        try:
            # Attempt to process all samples at once for maximum performance
            self.logger.debug(f"Attempting to process all {len(active_sample_paths)} samples at once for maximum performance")

            for sample_path in tqdm(active_sample_paths, desc=f"Calculating {metric_name} distances", leave=True):
                distance = self._calculate_sample_distance_for_outlier_detection(sample_path)
                if distance is None:  # GPU memory error
                    gpu_memory_issue = True
                    self.logger.warning(f"GPU memory issue detected, falling back to batching")
                    break
                dists.append(distance)

        except Exception as e:
            gpu_memory_issue = True
            self.logger.warning(f"Error during bulk processing, falling back to batching: {e}")

        # If GPU memory issues occurred, retry with optimized batching
        if gpu_memory_issue:
            self.logger.info(f"Processing remaining samples in optimized batches due to GPU memory constraints")

            # Clear any partial results and start over with batching
            dists = []
            batch_size = min(15, max(5, len(active_sample_paths) // 4))  # Adaptive batch sizing

            for i in range(0, len(active_sample_paths), batch_size):
                batch_paths = active_sample_paths[i:i + batch_size]

                # Force GPU memory cleanup between batches
                if hasattr(self, 'memory_manager'):
                    self.memory_manager.force_gpu_cleanup()

                for sample_path in tqdm(batch_paths, desc=f"Calculating {metric_name} distances (batch {i//batch_size + 1})", leave=True):
                    distance = self._calculate_sample_distance_for_outlier_detection(sample_path)
                    dists.append(distance)

        dists_array: np.ndarray = np.array(dists)

        if len(dists_array) == 0:
            return None, (False, 0), 0.0

        # Export CSV with distance metrics (always, regardless of outlier detection)
        self._export_distance_metrics_csv(active_sample_paths, dists_array)

        obs_value: float = float(np.max(dists_array))
        out_index: int = int(np.argmax(dists_array))

        from scipy.stats import norm, beta

        μ: float = float(np.nanmean(dists_array))
        σ: float = float(np.nanstd(dists_array))

        # Fit both Normal and Beta distributions
        try:
            # Fast Beta parameter estimation using method of moments
            # Convert Normal parameters to Beta parameters using known relationships
            # For Beta distribution: μ = α/(α+β), σ² = (αβ)/((α+β)²(α+β+1))
            # Solving: α = μ²(1-μ)/σ² - μ, β = α(1-μ)/μ
            
            # Try method of moments estimation first (much faster)
            beta_a = None
            beta_b = None
            
            if σ > 0 and 0 < μ < 1:
                # Method of moments estimation for Beta parameters
                beta_a = μ * μ * (1 - μ) / (σ * σ) - μ
                beta_b = beta_a * (1 - μ) / μ
                
                # Check if parameters are valid
                if beta_a > 0 and beta_b > 0:
                    # Success - use method of moments
                    pass
                else:
                    # Invalid parameters - fall back to MLE
                    beta_a = None
                    beta_b = None
            
            # Fallback to MLE if method of moments failed
            if beta_a is None or beta_b is None:
                try:
                    # Use expensive but robust MLE fitting as fallback
                    beta_params = beta.fit(dists_array, floc=0, fscale=1)
                    beta_a, beta_b, _, _ = beta_params
                except Exception:
                    # Final fallback to simple estimation
                    beta_a = 2.0
                    beta_b = 2.0

            # Use Beta distribution for p-value if it fits better (based on AIC)
            beta_loglik = np.sum(beta.logpdf(dists_array, beta_a, beta_b, loc=0, scale=1))
            normal_loglik = np.sum(norm.logpdf(dists_array, μ, σ))

            # AIC comparison (lower AIC = better fit)
            beta_aic = 2 * 2 - 2 * beta_loglik  # 2 parameters for Beta
            normal_aic = 2 * 2 - 2 * normal_loglik  # 2 parameters for Normal

            use_beta = beta_aic < normal_aic and beta_a > 0 and beta_b > 0

            if use_beta:
                # Use Beta distribution for p-value calculation
                p_value: float = (1 - beta.cdf(obs_value, beta_a, beta_b, loc=0, scale=1)) if obs_value < 1.0 else 0.0
                print(f"  Using Beta distribution (a={beta_a:.2f}, b={beta_b:.2f}) for p-value calculation")
            else:
                # Use Normal distribution (fallback/default)
                p_value: float = (1 - norm.cdf(obs_value, μ, σ)) if σ > 0 else 0.0
                print(f"  Using Normal distribution (μ={μ:.3f}, σ={σ:.3f}) for p-value calculation")

        except Exception as e:
            # Fallback to Normal distribution if Beta fitting fails
            print(f"  Beta fitting failed ({e}), using Normal distribution")
            p_value: float = (1 - norm.cdf(obs_value, μ, σ)) if σ > 0 else 0.0

        # Print p-value information
        print(f"Iteration {self.current_iteration}: Most extreme outlier p-value = {p_value:.6f}")
        # Print the sample selected as most extreme outlier
        print(f"  Most extreme outlier: {active_sample_paths[out_index]}")
        print(f"  Distance statistics: μ = {μ:.6f}, σ = {σ:.6f}")
        print(f"  Observed extreme distance = {obs_value:.6f}")
        print(f"  Threshold (α) = {self.α:.6f}")

        # Generate and save histogram, including the sample in the subtitle
        # Pass the distribution that was actually used for p-value calculation
        if 'use_beta' in locals() and use_beta:
            fitted_dist = "beta"
            fitted_par1 = beta_a
            fitted_par2 = beta_b
        else:
            fitted_dist = "normal"
            fitted_par1 = μ
            fitted_par2 = σ

        self._save_distance_histogram(
            dists_array,
            fitted_dist,
            fitted_par1,
            fitted_par2,
            obs_value,
            p_value,
            sample=str(active_sample_paths[out_index]),
            metric=self.distance_metrics[0] if self.distance_metrics else None,
        )

        actual_sample_id: Tuple[bool, int] = active_sample_indices[out_index]
        return active_sample_paths[out_index], actual_sample_id, p_value

    def _export_distance_metrics_csv(
        self,
        active_sample_paths: List[Path],
        dists_array: np.ndarray,
    ) -> None:
        # Add this check at the beginning
        if not self.verbose:
            return
        
        try:
            import pandas as pd
            
            # Create output directory if it doesn't exist
            # Ensure output directory exists with robust error handling
            try:
                # First ensure parent directories exist
                self.output_dir.parent.mkdir(parents=True, exist_ok=True)
                # Then create the target directory
                self.output_dir.mkdir(exist_ok=True)
                # Verify directory was actually created
                if not self.output_dir.exists():
                    raise OSError(f"Failed to create output directory: {self.output_dir}")
                # Note: os.access may not work correctly in container environments
            except PermissionError as e:
                raise OSError(f"Permission denied creating output directory {self.output_dir}. "
                             f"Please ensure the parent directory is writable: {self.output_dir.parent}. "
                             f"Original error: {e}")
            except Exception as e:
                raise OSError(f"Cannot create output directory {self.output_dir}: {e}")
            
            # Create filename with iteration number
            filename = f"{self.chrom}-{self.ctx}-{self.current_iteration}.csv"
            csv_path = self.output_dir / filename
            
            # Prepare data for CSV
            data = []
            for i, sample_path in enumerate(active_sample_paths):
                sample = str(active_sample_paths[i])  # Convert Path to string
                sample_name = Path(sample).parent.name if sample else "unknown"  # Get parent directory name
                distance_value = dists_array[i]
                
                data.append({
                    'sample_name': sample_name,
                    'distance_value': distance_value,
                    'iteration': self.current_iteration,
                    'metric': self.distance_metrics[0].value if self.distance_metrics else 'unknown',
                })
            
            # Create DataFrame and save to CSV
            df = pd.DataFrame(data)
            df.to_csv(csv_path, index=False)
            
            self.logger.info(f"Exported distance metrics to {csv_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to export distance metrics CSV: {e}")

    def _export_multi_metric_distance_csv(
        self,
        active_sample_paths: List[Path],
        sample_distances: Dict[DistanceMetric, np.ndarray],
        sample_p_values: Dict[DistanceMetric, np.ndarray],
    ) -> None:
        # Add this check at the beginning
        if not self.verbose:
            return
        
        try:
            import pandas as pd
            
            # Create output directory if it doesn't exist
            # Ensure output directory exists with robust error handling
            try:
                # First ensure parent directories exist
                self.output_dir.parent.mkdir(parents=True, exist_ok=True)
                # Then create the target directory
                self.output_dir.mkdir(exist_ok=True)
                # Verify directory was actually created
                if not self.output_dir.exists():
                    raise OSError(f"Failed to create output directory: {self.output_dir}")
                # Note: os.access may not work correctly in container environments
            except PermissionError as e:
                raise OSError(f"Permission denied creating output directory {self.output_dir}. "
                             f"Please ensure the parent directory is writable: {self.output_dir.parent}. "
                             f"Original error: {e}")
            except Exception as e:
                raise OSError(f"Cannot create output directory {self.output_dir}: {e}")
            
            # Create filename with iteration number
            filename = f"{self.chrom}-{self.ctx}-{self.current_iteration}.csv"
            csv_path = self.output_dir / filename
            
            # Prepare data for CSV
            data = []
            for i, sample_path in enumerate(active_sample_paths):
                sample = str(active_sample_paths[i])  # Convert Path to string
                sample_name = Path(sample).parent.name if sample else "unknown"  # Get parent directory name
                
                # Create row with all metrics
                row = {
                    'sample_name': sample_name,
                    'iteration': self.current_iteration,
                }
                
                # Add distance and p-value for each metric
                for metric in self.distance_metrics:
                    row[f'{metric.value}_distance'] = sample_distances[metric][i]
                    row[f'{metric.value}_p_value'] = sample_p_values[metric][i]
                
                data.append(row)
            
            # Create DataFrame and save to CSV
            df = pd.DataFrame(data)
            df.to_csv(csv_path, index=False)
            
            self.logger.info(f"Exported multi-metric distance results to {csv_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to export multi-metric distance CSV: {e}")

    def _save_distance_histogram(
        self,
        dists: np.ndarray,
        fitted_dist: str,
        fitted_par1: float,
        fitted_par2: float,
        obs_value: float,
        p_value: float,
        sample: str,
        metric: DistanceMetric = None,
    ) -> None:
        # Add this check at the beginning
        if not self.verbose:
            return

        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            from scipy.stats import norm, gaussian_kde, beta

            # Create subplot with secondary y-axis for better layout
            fig = make_subplots(rows=1, cols=1, specs=[[{"secondary_y": False}]])

            # Calculate histogram data
            hist_bins = min(20, len(dists) // 2)
            hist_values, bin_edges = np.histogram(dists, bins=hist_bins, density=True)
            bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

            # Add histogram
            fig.add_trace(
                go.Bar(
                    x=bin_centers,
                    y=hist_values,
                    name="Histogram",
                    marker_color="skyblue",
                    opacity=0.7,
                    hovertemplate="<b>Histogram</b><br>"
                    + "Distance: %{x:.3f}<br>"
                    + "Density: %{y:.4f}<br>"
                    + "<extra></extra>",
                ),
                row=1,
                col=1,
            )

            # Calculate and add KDE
            kde = gaussian_kde(dists)
            x_kde = np.linspace(dists.min(), dists.max(), 200)
            y_kde = kde(x_kde)

            fig.add_trace(
                go.Scatter(
                    x=x_kde,
                    y=y_kde,
                    mode="lines",
                    name="KDE",
                    line=dict(color="green", width=2),
                    hovertemplate="<b>KDE</b><br>"
                    + "Distance: %{x:.3f}<br>"
                    + "Density: %{y:.4f}<br>"
                    + "<extra></extra>",
                ),
                row=1,
                col=1,
            )

            # Add fitted distribution curve (the one actually used for p-value calculation)
            if fitted_dist == "beta":
                # Plot Beta distribution (the fitted distribution used for testing)
                x_fitted = np.linspace(0.001, 0.999, 200)  # Avoid boundary issues
                y_fitted = beta.pdf(x_fitted, fitted_par1, fitted_par2, loc=0, scale=1)

                fig.add_trace(
                    go.Scatter(
                        x=x_fitted,
                        y=y_fitted,
                        mode="lines",
                        name=f"Beta(α={fitted_par1:.2f}, β={fitted_par2:.2f}) [FITTED]",
                        line=dict(color="red", width=3),
                        hovertemplate="<b>Fitted Beta Distribution</b><br>"
                        + "Distance: %{x:.3f}<br>"
                        + "Density: %{y:.4f}<br>"
                        + "<extra></extra>",
                    ),
                    row=1,
                    col=1,
                )

                # Also plot Normal distribution for comparison
                data_mean = np.mean(dists)
                data_std = np.std(dists)
                x_norm = np.linspace(data_mean - 4 * data_std, data_mean + 4 * data_std, 200)
                y_norm = norm.pdf(x_norm, data_mean, data_std)

                fig.add_trace(
                    go.Scatter(
                        x=x_norm,
                        y=y_norm,
                        mode="lines",
                        name=f"Normal(μ={data_mean:.3f}, σ={data_std:.3f})",
                        line=dict(color="blue", width=2, dash="dot"),
                        hovertemplate="<b>Normal Distribution</b><br>"
                        + "Distance: %{x:.3f}<br>"
                        + "Density: %{y:.4f}<br>"
                        + "<extra></extra>",
                    ),
                    row=1,
                    col=1,
                )

            else:  # fitted_dist == "normal"
                # Plot Normal distribution (the fitted distribution used for testing)
                x_fitted = np.linspace(fitted_par1 - 4 * fitted_par2, fitted_par1 + 4 * fitted_par2, 200)
                y_fitted = norm.pdf(x_fitted, fitted_par1, fitted_par2)

                fig.add_trace(
                    go.Scatter(
                        x=x_fitted,
                        y=y_fitted,
                        mode="lines",
                        name=f"Normal(μ={fitted_par1:.3f}, σ={fitted_par2:.3f}) [FITTED]",
                        line=dict(color="red", width=3),
                        hovertemplate="<b>Fitted Normal Distribution</b><br>"
                        + "Distance: %{x:.3f}<br>"
                        + "Density: %{y:.4f}<br>"
                        + "<extra></extra>",
                    ),
                    row=1,
                    col=1,
                )

                # Also plot Beta distribution for comparison
                try:
                    beta_params = beta.fit(dists, floc=0, fscale=1)
                    beta_a, beta_b, _, _ = beta_params

                    # Only plot Beta if parameters are reasonable
                    if beta_a > 0 and beta_b > 0 and beta_a < 100 and beta_b < 100:
                        x_beta = np.linspace(0.001, 0.999, 200)  # Avoid boundary issues
                        y_beta = beta.pdf(x_beta, beta_a, beta_b, loc=0, scale=1)

                        fig.add_trace(
                            go.Scatter(
                                x=x_beta,
                                y=y_beta,
                                mode="lines",
                                name=f"Beta(a={beta_a:.2f}, b={beta_b:.2f})",
                                line=dict(color="purple", width=2, dash="dot"),
                                hovertemplate="<b>Beta Distribution</b><br>"
                                + "Distance: %{x:.3f}<br>"
                                + "Density: %{y:.4f}<br>"
                                + "<extra></extra>",
                            ),
                            row=1,
                            col=1,
                        )
                except Exception:
                    # Skip Beta plotting if fitting fails
                    pass

            # Add vertical line for observed extreme value (without automatic annotation)
            fig.add_vline(x=obs_value, line_dash="dash", line_color="orange")

            # Update layout
            fig.update_layout(
                title=dict(
                    text=f"Distance Distribution - Iteration {self.current_iteration}<br><sub>p-value = {p_value:.6f} | n = {len(dists)} | {sample}</sub>",
                    x=0.5,
                    xanchor="center",
                    font=dict(size=16),
                ),
                xaxis_title={
                    DistanceMetric.JEFFREYS: "Jeffreys Divergence",
                    DistanceMetric.JENSEN_SHANNON: "Jensen-Shannon Distance",
                    DistanceMetric.WEIGHTED_JENSEN_SHANNON: "Weighted Jensen-Shannon Distance",
                    DistanceMetric.HELLINGER: "Hellinger Distance"
                }.get(metric, "Distance"),
                yaxis_title="Density",
                showlegend=True,
                hovermode="x unified",
                legend=dict(
                    yanchor="middle",
                    y=0.5,
                    xanchor="left",
                    x=1.02,
                    bgcolor="rgba(255, 255, 255, 0.9)",
                    bordercolor="black",
                    borderwidth=1,
                    font=dict(size=12),
                ),
            )

            # Update axes
            fig.update_xaxes(gridcolor="lightgray", gridwidth=0.5)
            fig.update_yaxes(gridcolor="lightgray", gridwidth=0.5)

            # Extract sample name from the sample path for filename
            sample_name = Path(sample).parent.name if sample else "unknown"

            # Save the interactive plot as HTML
            hist_path: Path = (
                self.output_dir
                / f"{self.chrom}-{self.ctx}-hist-{self.current_iteration + 1}-{sample_name}.html"
            )
            fig.write_html(hist_path, include_plotlyjs=True)

            print(f"  Interactive histogram saved: {hist_path}")

        except ImportError:
            print("  Warning: plotly not available, skipping histogram generation")
        except Exception as e:
            print(f"  Warning: Error generating histogram: {e}")

    def _backup_centroid(self, centroid_path: Path) -> Path:

        backup_path = centroid_path.with_suffix(".h5.bak")
        if centroid_path.exists():
            import shutil

            shutil.copy2(centroid_path, backup_path)
        return backup_path

    def _restore_centroid(self, centroid_path: Path, backup_path: Path):

        if backup_path.exists():
            import shutil

            if centroid_path.exists():
                centroid_path.unlink()
            shutil.move(backup_path, centroid_path)

    def _cleanup_backup(self, backup_path: Path):

        if backup_path.exists():
            backup_path.unlink()

    def _precache_all_samples(self):

        self.logger.info("Pre-caching sample data for faster outlier detection...")

        # Get all active sample paths (remove duplicates)
        active_sample_paths = []
        seen_paths = set()
        for sample_id in self.active_samples:
            is_new_sample, sample_index = sample_id
            sample_path = (
                self.add_samples[sample_index]
                if is_new_sample
                else self.samples[sample_index]
            )
            if sample_path not in seen_paths:
                active_sample_paths.append(sample_path)
                seen_paths.add(sample_path)

        if not active_sample_paths:
            self.logger.warning("No samples to pre-cache.")
            return

        # Memory management parameters
        memory_info = psutil.virtual_memory()
        total_memory_gb = memory_info.total / (1024**3)
        available_memory_gb = memory_info.available / (1024**3)
        
        # Use 80-90% of available memory for caching (reserve 10-20% for GPU operations)
        cache_memory_target_gb = available_memory_gb * 0.85  # 85% of available memory
        cache_memory_limit_gb = min(cache_memory_target_gb, total_memory_gb * 0.8)  # Cap at 80% of total memory
        
        self.logger.info(f"Memory status: {total_memory_gb:.1f}GB total, {available_memory_gb:.1f}GB available")
        self.logger.info(f"Target cache memory: {cache_memory_limit_gb:.1f}GB ({cache_memory_limit_gb/available_memory_gb*100:.1f}% of available)")

        # Load samples with memory monitoring
        def load_and_cache_sample(sample_path: Path):
    
            try:
                # Check current memory usage before loading
                current_memory_gb = psutil.virtual_memory().used / (1024**3)
                if current_memory_gb > total_memory_gb * 0.9:  # Stop if using >90% of total memory
                    self.logger.warning(f"Memory usage too high ({current_memory_gb:.1f}GB), stopping pre-caching")
                    return None
                
                # Load the sample
                result = self._load_sample(sample_path)
                
                if result is not None:
                    # Calculate actual memory usage from the loaded data
                    pos, mC, uC = result
                    sample_memory_mb = (pos.nbytes + mC.nbytes + uC.nbytes) / (1024 * 1024)
                    return result, sample_memory_mb
                
                return None, 0
            except Exception as e:
                self.logger.error(f"Error pre-caching {sample_path}: {e}")
                return None, 0

        # Load samples sequentially to better control memory usage
        # This allows us to monitor memory usage and stop if needed
        cached_count = 0
        total_memory_used_mb = 0
        
        for sample_path in tqdm(active_sample_paths, desc="Pre-caching samples"):
            # Check if we should continue based on memory usage
            current_memory_gb = psutil.virtual_memory().used / (1024**3)
            if current_memory_gb > total_memory_gb * 0.9:  # Stop if using >90% of total memory
                self.logger.warning(f"Memory usage limit reached ({current_memory_gb:.1f}GB), stopping pre-caching")
                self.logger.info(f"Successfully cached {cached_count}/{len(active_sample_paths)} samples")
                break
            
            # Load the sample
            result, sample_memory_mb = load_and_cache_sample(sample_path)
            if result is not None:
                cached_count += 1
                total_memory_used_mb += sample_memory_mb
                
                # Check if we're approaching our memory limit
                if total_memory_used_mb > cache_memory_limit_gb * 1024:
                    self.logger.warning(f"Cache memory limit reached ({total_memory_used_mb/1024:.1f}GB), stopping pre-caching")
                    break

        self.logger.info(f"Pre-caching completed: {cached_count}/{len(active_sample_paths)} samples cached")
        self.logger.info(f"Total memory used for caching: {total_memory_used_mb/1024:.1f}GB")
        
        # Final memory status
        final_memory_gb = psutil.virtual_memory().used / (1024**3)
        self.logger.info(f"Final memory usage: {final_memory_gb:.1f}GB ({final_memory_gb/total_memory_gb*100:.1f}% of total memory)")

    def _clear_sample_cache(self):
        """Clear the intelligent sample cache."""
        if hasattr(self.sample_cache, 'clear'):
            cache_stats = self.sample_cache.get_stats()
            self.logger.info(f"Clearing sample cache: {cache_stats['cached_samples']} samples, "
                           f"{cache_stats['memory_usage_mb']:.1f}MB memory")
            self.sample_cache.clear()

            # Force garbage collection
            import gc
            gc.collect()
            
            # Report memory after clearing
            memory_after_gb = psutil.virtual_memory().used / (1024**3)
            self.logger.info(f"Memory after cache clear: {memory_after_gb:.1f}GB")

    def _get_memory_usage_info(self) -> dict:
        
        memory_info = self.memory_manager.get_memory_usage()
        return {
            "total_gb": memory_info.get("total_gb", 0),
            "available_gb": memory_info.get("available_gb", 0),
            "used_gb": memory_info.get("used_gb", 0),
            "percent_used": memory_info.get("percent_used", 0),
            "cache_stats": self.sample_cache.get_stats() if hasattr(self.sample_cache, 'get_stats') else {"cached_samples": 0}
        }

    def _prepare_for_gpu_processing(self):

        memory_info = self._get_memory_usage_info()

        # If memory usage is high (>80%), clear the sample cache
        if memory_info["percent_used"] > 80:
            self.logger.info("High memory usage detected, clearing sample cache for processing...")
            self._clear_sample_cache()

        # GPU memory pressure handling with automatic CPU fallback
        if self._using_gpu:
            try:
                from scripts.gpu_memory_utils import GPUMemoryUtils
                if GPUMemoryUtils.is_memory_pressure_high(threshold_percent=85.0):
                    self.logger.warning("GPU memory pressure detected, attempting cleanup...")
                    GPUMemoryUtils.cleanup_gpu_memory(aggressive=True)

                    # Check if cleanup helped
                    if GPUMemoryUtils.is_memory_pressure_high(threshold_percent=90.0):
                        self.logger.warning("GPU memory pressure persists, falling back to CPU processing")
                        self._fallback_to_cpu_processing()
                        self._gpu_memory_pressure_detected = True
                    else:
                        self.logger.info("GPU memory pressure alleviated after cleanup")
            except ImportError:
                # GPU memory utilities not available, check for basic GPU memory issues
                self.logger.debug("GPU memory utilities not available, monitoring basic GPU usage")
                self._check_gpu_memory_fallback()
        else:
            self.logger.debug("Using CPU processing mode")

    def _check_gpu_memory_fallback(self):
        """Basic GPU memory monitoring when advanced utilities aren't available"""
        try:
            import cupy as cp
            # Check if we can allocate a small test array
            test_array = cp.zeros((1000, 1000), dtype=cp.float32)
            del test_array
            cp.cuda.Device(0).synchronize()  # Force sync to catch any pending errors
        except Exception as e:
            self.logger.warning(f"GPU memory test failed: {e}")
            self._fallback_to_cpu_processing()
            self._gpu_memory_pressure_detected = True

    def _fallback_to_cpu_processing(self):
        """Switch from GPU to CPU processing mode"""
        if not self._using_gpu:
            return  # Already using CPU

        self.logger.info("Switching to CPU processing mode for reliability with large datasets")
        self._using_gpu = False

        # Reinitialize chunked processor with dynamic CPU parameters
        try:
            cpu_params = self._calculate_chunked_processor_params(use_gpu=False)
            self.chunked_processor = ChunkedGenomicProcessor(
                chunk_size_positions=cpu_params['chunk_size_positions'],
                max_workers=cpu_params['max_workers'],
                use_gpu=False,
                memory_limit_gb=cpu_params['memory_limit_gb']
            )

            # Clear any GPU-based caches that might cause issues
            self._clear_sample_cache()

            self.logger.info("Successfully switched chunked processing to CPU mode")
        except Exception as e:
            self.logger.error(f"Failed to switch chunked processing to CPU: {e}")
            raise RuntimeError("Cannot fallback to CPU processing") from e

    def _attempt_gpu_recovery(self):
        """Attempt to recover GPU usage if memory pressure has eased"""
        if not self._gpu_available or self._using_gpu:
            return  # GPU not available or already using GPU

        try:
            # Test if GPU is available again
            import cupy as cp
            test_array = cp.zeros((100, 100), dtype=cp.float32)
            del test_array
            cp.cuda.Device(0).synchronize()

            self.logger.info("GPU memory pressure appears resolved, attempting to recover GPU usage")
            self._using_gpu = True

            # Reinitialize chunked processor with dynamic GPU parameters
            gpu_params = self._calculate_chunked_processor_params(use_gpu=True)
            self.chunked_processor = ChunkedGenomicProcessor(
                chunk_size_positions=gpu_params['chunk_size_positions'],
                max_workers=gpu_params['max_workers'],
                use_gpu=True,
                memory_limit_gb=gpu_params['memory_limit_gb']
            )

            self._gpu_memory_pressure_detected = False
            self.logger.info("Successfully recovered GPU processing mode")

        except Exception as e:
            self.logger.debug(f"GPU recovery test failed, staying with CPU: {e}")
            self._using_gpu = False

    def remove_outliers(self) -> OutlierRemovalResults:
        """Remove outliers with comprehensive performance profiling and GPU resource management."""
        # Short-circuit when outlier detection is disabled
        if not self.distance_metrics:
            return OutlierRemovalResults(
                iterations=[],
                final_centroid_path=str(self.centroid_path) if self.centroid_path else "",
                total_samples_removed=0,
            )

        with self.performance_profiler.profile_operation("outlier_removal"):
            # Use MethylUtils GPU cleanup for safe resource management
            memory_manager = get_memory_manager()

            results = OutlierRemovalResults(
                iterations=[],
                final_centroid_path="",
                total_samples_removed=0
            )

            # Pre-cache all samples for faster outlier detection
            self._precache_all_samples()

            # Prepare for processing (GPU/CPU based on availability and memory)
            self._prepare_for_gpu_processing()

            # Log processing mode
            processing_mode = "GPU" if self._using_gpu else "CPU"
            self.logger.info(f"Starting outlier removal using {processing_mode} processing mode")

            self.current_iteration = 0

            while (
                self.current_iteration < self.max_iterations
                and len(self.active_samples) > self.min_samples
            ):
                # Periodically attempt GPU recovery if we had memory pressure
                if self._gpu_memory_pressure_detected and self.current_iteration % 3 == 0:
                    self._attempt_gpu_recovery()
                    processing_mode = "GPU" if self._using_gpu else "CPU"
                    self.logger.debug(f"Iteration {self.current_iteration}: Using {processing_mode} processing mode")

                try:
                    outlier_path, outlier_id, p_value = self.find_most_extreme_outlier()
                except Exception as e:
                    print(f"Error in outlier detection for iteration {self.current_iteration}: {e}")
                    print(f"  Outlier ID: {outlier_id if 'outlier_id' in locals() else 'unknown'}")
                    break

                if outlier_path is None:
                    break

                if p_value > self.α:
                    print(f"Iteration {self.current_iteration}: No significant outliers found (p-value = {p_value:.6f})")
                    break

                # Remove the outlier
                is_new_sample, sample_index = outlier_id
                self.remove_sample(sample_index, is_new_sample=is_new_sample)

                # Save iteration info
                iteration_info = OutlierIterationInfo(
                    iteration=self.current_iteration,
                    p_value=p_value,
                    outlier_path=str(outlier_path),
                )
                results.iterations.append(iteration_info)
                results.total_samples_removed += 1

                print(
                    f"Iteration {self.current_iteration}: Removed outlier {sample_index} (new={is_new_sample}) ({outlier_path.name})"
                )

                # Save current state
                centroid_path = self.save_centroid(self.output_dir, extended=True)
                results.final_centroid_path = str(centroid_path)

                self.current_iteration += 1

            print(
                f"Outlier removal completed. Removed {results.total_samples_removed} samples."
            )

            # Clear cache to free memory and ensure GPU cleanup
            self.sample_cache.clear()
            memory_manager.force_gpu_cleanup()

            return results

    def build_centroid(self) -> OutlierRemovalResults:
        """Build centroid with comprehensive performance profiling."""
        with self.performance_profiler.profile_operation("build_centroid"):
            # For outlier removal to work properly, we need to rebuild from individual samples
            # rather than loading pre-computed centroids, since outlier removal requires
            # the ability to remove individual samples from the position aligner.

            # Check if centroid exists and we have samples to work with
            centroid_exists = self.centroid_path.exists()

            if centroid_exists:
                print(f"Centroid file exists at {self.centroid_path}, but rebuilding from samples for outlier removal")

            # Always rebuild from samples for proper outlier removal capability
            print("Rebuilding centroid from individual samples")

        # Calculate initial extended centroid
        try:
            centroid_path = self.calculate_centroid(str(self.output_dir), extended=True)
            if centroid_path is None:
                raise RuntimeError("Failed to compute centroid: calculate_centroid returned None")
        except RuntimeError as e:
            error_msg = str(e).lower()
            if "no samples" in error_msg or "failed to compute" in error_msg or "failed to save" in error_msg:
                # Return empty results if no samples were added
                results = OutlierRemovalResults(
                    iterations=[],
                    final_centroid_path="",
                    total_samples_removed=0
                )
                return results
            raise

        # Cache aligned data for all active samples after initial build
        for sample_id in self.active_samples:
            is_new_sample, sample_index = sample_id
            sample_path = (
                self.add_samples[sample_index]
                if is_new_sample
                else self.samples[sample_index]
            )
            # Align and cache - let SmartSampleCache handle loading
            self.sample_cache.get(sample_path, lambda: self._load_sample(sample_path))  

        # Remove outliers using stored parameters
        results = self.remove_outliers()
        # Convert Path to string for final_centroid_path
        results.final_centroid_path = str(centroid_path) if centroid_path is not None else ""

        # Update config with new samples and outliers after initial outlier removal
        self._update_config_after_outlier_removal(results)

        return results

    def _update_config_after_outlier_removal(self, results: OutlierRemovalResults) -> None:
        """
        Update the configuration file after outlier removal to reflect current samples and outliers.
        """
        # Get current active samples
        current_samples = []
        current_outliers = []

        # Collect remaining samples (those still active)
        for sample_id in self.active_samples:
            if isinstance(sample_id, tuple) and len(sample_id) == 2:
                is_new_sample, sample_index = sample_id
                if is_new_sample:
                    sample_path = self.add_samples[sample_index]
                else:
                    sample_path = self.samples[sample_index]
                # Convert to directory path (remove chrom-ctx.h5 suffix)
                sample_dir = str(sample_path.parent)
                current_samples.append(sample_dir)

        # Collect outliers that were removed
        for outlier_id in self.outlier_samples:
            is_new_sample, sample_index = outlier_id
            if is_new_sample:
                sample_path = self.add_samples[sample_index]
            else:
                sample_path = self.samples[sample_index]
            # Convert to directory path (remove chrom-ctx.h5 suffix)
            sample_dir = str(sample_path.parent)
            current_outliers.append(sample_dir)

        # Update the original tracking lists
        self._original_samples = current_samples
        self._original_outliers = current_outliers
        self._original_add_samples = []  # Clear add_samples after processing

        # Save updated config
        config = self.get_config()
        config_path = self.output_dir / f"{self.chrom}-{self.ctx}_config.json"
        with open(config_path, "w") as f:
            json.dump(config.model_dump(), f, indent=2)

        print(f"Updated configuration saved to {config_path}")
        print(f"Current samples: {len(current_samples)}, Outliers: {len(current_outliers)}")

    def validate_centroid_calculation(self) -> bool:

        if self._centroid is None or len(self._centroid) == 0:
            print("No centroid data available for validation")
            return False

        # Get valid positions from centroid (coverage >= min_coverage)
        if self._centroid is None:
            return False
        # Convert to CPU first to ensure numpy arrays
        centroid_cpu = self._centroid.to_cpu()
        coverage = np.asarray(centroid_cpu.coverage.values, dtype=np.uint32)
        valid_mask = coverage >= self._min_coverage
        # Convert to numpy arrays before indexing to avoid pandas indexing issues
        pos_values = np.asarray(centroid_cpu.pos.values, dtype=np.uint32)
        mC_values = np.asarray(centroid_cpu.mC.values, dtype=np.uint32)
        uC_values = np.asarray(centroid_cpu.uC.values, dtype=np.uint32)
        N_values = np.asarray(centroid_cpu.N.values, dtype=np.uint32)
        
        valid_pos = pos_values[valid_mask]
        centroid_mC = mC_values[valid_mask]
        centroid_uC = uC_values[valid_mask]
        centroid_N = N_values[valid_mask]

        if len(valid_pos) == 0:
            print("No valid positions for validation")
            return False

        # Calculate direct average for comparison using N per position
        direct_mC = np.zeros_like(centroid_mC, dtype=float)
        direct_uC = np.zeros_like(centroid_uC, dtype=float)
        direct_N = np.zeros_like(centroid_N, dtype=int)

        for sample_id in self.active_samples:
            is_new_sample, sample_index = sample_id
            sample_path = (
                self.add_samples[sample_index]
                if is_new_sample
                else self.samples[sample_index]
            )

            if sample_path.exists():
                try:
                    from methyl_utils import MethylSample
                    methyl_sample = MethylSample.load_from_h5(sample_path)

                    # Ensure arrays are NumPy arrays for validation operations
                    # Convert to CPU first to ensure numpy arrays
                    methyl_sample_cpu = methyl_sample.to_cpu()
                    sample_pos = np.asarray(methyl_sample_cpu.pos.values, dtype=np.uint32)
                    sample_mC = np.asarray(methyl_sample_cpu.mC.values, dtype=np.uint32)
                    sample_uC = np.asarray(methyl_sample_cpu.uC.values, dtype=np.uint32)

                    # Find common positions
                    common_pos, sample_idx, valid_idx = np.intersect1d(
                        sample_pos, valid_pos, return_indices=True
                    )

                    if len(common_pos) > 0:
                        direct_mC[valid_idx] += sample_mC[sample_idx]
                        direct_uC[valid_idx] += sample_uC[sample_idx]
                        direct_N[valid_idx] += 1

                except Exception as e:
                    print(f"Warning: Could not read sample {sample_path}: {e}")
                    continue

        # Calculate averages using N per position
        valid_N = direct_N > 0
        if np.any(valid_N):
            # Use np.where instead of np.divide with where parameter for CuPy compatibility
            valid_N_mask = direct_N[valid_N] > 0
            with np.errstate(divide='ignore', invalid='ignore'):
                direct_mC[valid_N] = np.where(
                    valid_N_mask,
                    direct_mC[valid_N].astype(np.float64) / direct_N[valid_N].astype(np.float64),
                    0.0
                ).astype(np.uint32)
                direct_uC[valid_N] = np.where(
                    valid_N_mask,
                    direct_uC[valid_N].astype(np.float64) / direct_N[valid_N].astype(np.float64),
                    0.0
                ).astype(np.uint32)

            # Compare with centroid calculation
            mC_diff = np.abs(centroid_mC[valid_N] - direct_mC[valid_N])
            uC_diff = np.abs(centroid_uC[valid_N] - direct_uC[valid_N])
            N_diff = np.abs(centroid_N[valid_N] - direct_N[valid_N])

            max_mC_diff = np.max(mC_diff)
            max_uC_diff = np.max(uC_diff)
            max_N_diff = np.max(N_diff)

            print(
                f"Centroid validation - Max mC difference: {max_mC_diff}, Max uC difference: {max_uC_diff}, Max N difference: {max_N_diff}"
            )

            # Allow small floating point differences (increased tolerance for integer division rounding)
            tolerance = 1.0  # Allow 1 unit difference due to integer division rounding
            if max_mC_diff < tolerance and max_uC_diff < tolerance and max_N_diff == 0:
                print("Centroid calculation validation PASSED")
                return True
            else:
                print("Centroid calculation validation FAILED")
                return False
        else:
            print("No valid samples found for validation")
            return False

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Calculate methylation centroids with outlier removal"
    )
    parser.add_argument(
        "--data-dir", type=str, help="Data directory containing sample files"
    )
    parser.add_argument("--csv-file", type=str, help="CSV file with sample paths")
    parser.add_argument("--output-dir", type=str, help="Output directory for centroids")
    parser.add_argument("--chrom", type=str, default="1", help="Chromosome to process")
    parser.add_argument(
        "--ctx", type=str, default="CG", help="Context to process (CG, CHG, CHH)"
    )
    parser.add_argument(
        "--min-coverage", type=int, default=4, help="Minimum coverage threshold"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum outlier removal iterations",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        help="Significance level for outlier detection",
    )
    parser.add_argument(
        "--min-samples", type=int, default=3, help="Minimum samples required"
    )

    args = parser.parse_args()

    # Use command line args if provided, otherwise use original defaults
    if args.data_dir and args.csv_file and args.output_dir:
        # Command line mode
        data_dir = Path(args.data_dir)
        csv_file = Path(args.csv_file)
        out_dir = Path(args.output_dir)

        with open(csv_file, "r") as f:
            samples = [data_dir / line.strip() for line in f if line.strip()]

        print(f"Processing {args.chrom}-{args.ctx}...")
        print(f"Found {len(samples)} samples")

        mc = MethylCentroid(
            samples=samples,
            chrom=args.chrom,
            ctx=args.ctx,
            output_dir=out_dir,
            min_coverage=args.min_coverage,
            max_iterations=args.max_iterations,
            α=args.alpha,
            min_samples=args.min_samples,
        )

        # Build extended centroid with methylation statistics
        results = mc.build_centroid()
        print(
            f"Completed {args.chrom}-{args.ctx}: {results.total_samples_removed} outliers removed"
        )

        # Save outlier removal results
        json_file_path = out_dir / f"{args.chrom}-{args.ctx}.json"
        with open(json_file_path, "w") as json_file:
            json.dump(results.model_dump(mode="json"), json_file)

        print(f"Results saved to {json_file_path}")

    else:
        # Original default mode
        data_dir = Path("/home/ubuntu/Work/output_workflows/arabidopsis")
        chroms = [str(i) for i in range(1, 6)] # + ["X"]
        ctxs = ["CG", "CHG", "CHH"]
        csv_file = Path("/home/ubuntu/MethylCentroid/data/msh1drm2.csv")
        out_dir = data_dir / "centroids" / csv_file.stem

        with open(csv_file, "r") as f:
            samples = [data_dir / line.strip() for line in f if line.strip()]

        # Collect all batch statistics
        batch_stats = {
            "timestamp": datetime.now().isoformat(),
            "batch_id": f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "total_combinations": len(chroms) * len(ctxs),
            "combinations_processed": 0,
            "total_outliers_removed": 0,
            "chromosomes": chroms,
            "contexts": ctxs,
            "individual_results": [],
            "summary": {
                "total_samples": len(samples),
                "data_directory": str(data_dir),
                "csv_file": str(csv_file),
                "output_directory": str(out_dir),
            },
        }

        # Process all chromosome/context combinations
        for chrom in chroms:
            for ctx in ctxs:
                print(f"\nProcessing {chrom}-{ctx}...")
                mc = MethylCentroid(
                    samples=samples,
                    chrom=chrom,
                    ctx=ctx,
                    output_dir=out_dir,
                    min_coverage=4,
                    max_iterations=10,  # fallback default
                    max_iterations_percentage=0.1,  # 10% of samples
                    α=0.05,
                    min_samples=3,
                )
                # Build extended centroid with methylation statistics
                results = mc.build_centroid()
                print(f"Completed {chrom}-{ctx}: {results.total_samples_removed} outliers removed")

                # Save configuration
                config = mc.get_config()
                with open(out_dir / f"{chrom}-{ctx}_config.json", "w") as f:
                    json.dump(config.model_dump(), f)

                # Save outlier removal results
                json_file_path = out_dir / f"{chrom}-{ctx}.json"
                with open(json_file_path, "w") as json_file:
                    json.dump(results.model_dump(mode="json"), json_file)

                # Collect statistics for batch report
                # Extract outlier sample names from results
                outlier_samples_list = []
                for iteration in results.iterations:
                    # Extract just the sample name from the full path
                    outlier_path = Path(iteration.outlier_path)
                    # Get the sample directory name
                    sample_name = (outlier_path.parent.name)  
                    outlier_samples_list.append(
                        {
                            "sample": sample_name,
                            "file": outlier_path.name,
                            "iteration": iteration.iteration,
                            "p_value": iteration.p_value,
                        }
                    )

                combination_stats = {
                    "chromosome": chrom,
                    "context": ctx,
                    "outliers_removed": results.total_samples_removed,
                    "outlier_samples": outlier_samples_list,
                    "final_samples": len(mc.active_samples),
                    "centroid_path": str(results.final_centroid_path),
                    "iterations": len(results.iterations),
                    "timestamp": datetime.now().isoformat(),
                }

                # Add methylation statistics if available
                # Check if centroid has methylation stats (extended centroid always has them)
                if mc._centroid is not None and isinstance(mc._centroid, MethylExtendedCentroid):
                    # Create alignment stats from centroid
                    # Note: These methods may need to be implemented differently
                    # For now, skip stats collection as it's not critical
                    alignment_stats = None
                    group_stats = None

                    combination_stats["methylation_stats"] = {
                        "alignment_stats": alignment_stats.model_dump(),
                        "group_stats": group_stats.model_dump()
                        if group_stats
                        else None,
                    }

                    # Save individual group-level methylation statistics
                    stats_file_path = out_dir / f"{chrom}-{ctx}_methylation_stats.json"

                    # Extract outlier sample names from results
                    outlier_samples = []
                    for iteration in results.iterations:
                        # Get the full path
                        outlier_path = Path(iteration.outlier_path)

                        outlier_samples.append(
                            {
                                "sample": (outlier_path.parent.name),
                                "file": outlier_path.name,
                                "iteration": iteration.iteration,
                                "p_value": iteration.p_value,
                            }
                        )

                    simplified_stats = {
                        "timestamp": datetime.now().isoformat(),
                        "analysis_id": f"{chrom}-{ctx}_analysis",
                        "chromosome": chrom,
                        "context": ctx,
                        "alignment_stats": alignment_stats.model_dump(),
                        "group_stats": group_stats.model_dump()
                        if group_stats
                        else None,
                        "metadata": {
                            "total_samples": len(samples),
                            "final_samples": len(mc.active_samples),
                            "outliers_removed": results.total_samples_removed,
                            "outlier_samples": outlier_samples,
                            "centroid_type": "extended",
                        },
                    }

                    with open(stats_file_path, "w") as f:
                        json.dump(simplified_stats, f, indent=2)
                    print(
                        f"Saved group-level methylation statistics to {stats_file_path}"
                    )

                batch_stats["individual_results"].append(combination_stats)
                batch_stats["combinations_processed"] += 1
                batch_stats["total_outliers_removed"] += results.total_samples_removed

        # Save batch statistics
        batch_stats_file_path = out_dir / "batch_methylation_statistics.json"
        with open(batch_stats_file_path, "w") as f:
            json.dump(batch_stats, f, indent=2)
        print(f"\nSaved batch statistics to {batch_stats_file_path}")
        print(f"Batch summary: {batch_stats['combinations_processed']} combinations processed, {batch_stats['total_outliers_removed']} total outliers removed")
