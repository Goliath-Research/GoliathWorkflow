# ruff: noqa: E402
# methyl_centroid.py
import sys
from pathlib import Path

# Add methylutils from monorepo to Python path (for development/direct execution)
# In monorepo: packages/methylcentroid/../methylutils/methyl_utils
methyl_utils_path = Path(__file__).parent.parent.parent / "methylutils" / "methyl_utils"
if methyl_utils_path.exists() and str(methyl_utils_path) not in sys.path:
    sys.path.insert(0, str(methyl_utils_path))

# Note: genomic_position_aligner (gpa_pkg) is now part of methylutils package
# No separate path addition needed - it's imported via methylutils

import numpy as np
from typing import List, Union, Optional, Tuple, Dict
from datetime import datetime
import json
import psutil
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from methyl_utils.core.methyl_frame import (
    # METHYL_CENTROID_DTYPE,
    # METHYL_EXTENDED_CENTROID_DTYPE,
    MethylSample,
    MethylExtendedCentroid,
)

try:
    from .config import MethylCentroidConfig, CentroidResults
except ImportError:
    try:
        from methyl_centroid.config import MethylCentroidConfig, CentroidResults
    except ImportError:
        local_pkg_root = Path(__file__).parent
        if str(local_pkg_root) not in sys.path:
            sys.path.insert(0, str(local_pkg_root))
        from config import MethylCentroidConfig, CentroidResults  # type: ignore[reportMissingImports]
try:
    from .core.sample_manager import SmartSampleCache
except ImportError:
    try:
        from methyl_centroid.core.sample_manager import SmartSampleCache
    except ImportError:
        local_pkg_root = Path(__file__).parent
        if str(local_pkg_root) not in sys.path:
            sys.path.insert(0, str(local_pkg_root))
        from core.sample_manager import SmartSampleCache  # type: ignore[reportMissingImports]
# Distance calculation functions
from methyl_utils import (
    get_methyl_dtype,
    # Memory management
    get_memory_manager,
    # Performance profiling
    get_performance_profiler,
    # Chunked processing
    ChunkedGenomicProcessor,
    # GPU detection
    is_gpu_available,
    cleanup_gpu_memory,
    # Logging
    get_logger,
)


class MethylCentroid:
    """
    Class to calculate methylation centroid for a group of samples / (chromosome, context).

    Designed for performance with large genomic datasets by using dense matrices
    and minimizing memory overhead. Processes each (chromosome, context) independently to
    optimize memory usage, with coverage-based filtering for centroids.

    Supports incremental operations for centroid updates.
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
        min_coverage: int = 4,
        min_samples: int = 1,
        max_sample_workers: Optional[int] = None,
        verbose: bool = True,
        enable_binned_stats: bool = False,
        binned_stats_bins: Optional[int] = 32,
        use_gpu: Optional[bool] = None,
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
        Initialize MethylCentroid for centroid calculation.

        Args:
            samples: Optional list of base sample directory paths containing {chrom}-{ctx}.h5 files.
                    For initial centroid creation, use add_samples instead. For updates, this contains
                    current samples in the centroid.
            chrom: Chromosome identifier (e.g., '1', 'X').
            ctx: Context type (e.g., 'CG', 'CHG', 'CHH').
            output_dir: Directory to save centroid files.
            add_samples: Optional list of sample directory paths to add (used for initial creation and updates).
            remove_samples: Optional list of sample directory paths to remove.
            min_coverage: Minimum sum of mC and uC for a position to be included.
            verbose: Enable verbose logging.

        Workflow:
            - Initial centroid creation: provide add_samples, output_dir (samples=[])
            - Centroid updates: provide samples (current centroid), add_samples/remove_samples
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
            self._original_add_samples = (
                [str(s) for s in add_samples] if add_samples else []
            )
        else:
            # If no samples provided, use add_samples as the main samples
            self.samples = (
                [Path(sample) / f"{chrom}-{ctx}.h5" for sample in add_samples]
                if add_samples
                else []
            )
            self.add_samples = []
            # Store original sample paths as strings for config reconstruction
            self._original_samples = (
                [str(s) for s in add_samples] if add_samples else []
            )
            self._original_add_samples = []

        # Handle remove samples for incremental updates
        self.remove_samples = (
            [Path(sample) / f"{chrom}-{ctx}.h5" for sample in remove_samples]
            if remove_samples
            else []
        )
        self._original_remove_samples = (
            [str(s) for s in remove_samples] if remove_samples else []
        )

        self.min_coverage = max(1, min_coverage)
        self.min_samples = max(1, int(min_samples))
        self.max_sample_workers = max_sample_workers
        self.chrom = chrom
        self.ctx = ctx
        self.output_dir = (
            Path(output_dir) if isinstance(output_dir, str) else output_dir
        )

        # Binned stats configuration (for centroid-level mixture fitting)
        self.enable_binned_stats = enable_binned_stats
        if binned_stats_bins is None:
            bins = 100
        else:
            bins = int(binned_stats_bins)
        self.binned_stats_bins = bins
        self._binned_stats = None

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
            raise OSError(
                f"Permission denied creating output directory {self.output_dir}. "
                f"Please ensure the parent directory is writable: {self.output_dir.parent}. "
                f"Original error: {e}"
            )
        except Exception as e:
            raise OSError(f"Cannot create output directory {self.output_dir}: {e}")

        # Derive centroid path from output directory and chromosome/context
        self.centroid_path = self.output_dir / f"{chrom}-{ctx}.h5"

        # Store metadata fields
        self.laboratory = laboratory
        self.disease = disease
        self.group = group
        self.batch = batch

        self.centroid: Optional[Path] = None

        # Detect GPU availability and respect explicit user choice
        gpu_available = is_gpu_available()
        self.logger.info(f"GPU available: {gpu_available}")

        self._gpu_enabled = True if use_gpu is None else bool(use_gpu)
        if not self._gpu_enabled:
            self.logger.info("GPU explicitly disabled by configuration; forcing CPU mode")

        # For large human genomes, prioritize GPU unless disabled or unavailable
        self.use_gpu = gpu_available and self._gpu_enabled
        if self.use_gpu:
            self.logger.info(
                "Using GPU acceleration for optimal performance with large genomic datasets"
            )
        else:
            self.logger.warning("GPU disabled or unavailable; using CPU processing")

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
            chunk_size_positions=chunked_params["chunk_size_positions"],
            max_workers=chunked_params["max_workers"],
            use_gpu=self.use_gpu,  # Use GPU when available for large datasets
            memory_limit_gb=chunked_params["memory_limit_gb"],
        )

        # Track active samples (those currently included in centroid calculation)
        self.active_samples: set = set()

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
    def from_config(
        cls, config: MethylCentroidConfig, verbose: bool = None
    ) -> "MethylCentroid":
        # Use config.verbose if verbose parameter is not provided, otherwise use the parameter
        verbose_value = verbose if verbose is not None else config.verbose

        return cls(
            samples=getattr(config, "samples", None),
            chrom=config.chrom,
            ctx=config.ctx,
            output_dir=config.output_dir,
            add_samples=config.add_samples,
            remove_samples=config.remove_samples,
            min_coverage=config.min_coverage,
            max_sample_workers=getattr(config, "max_sample_workers", None),
            verbose=verbose_value,
            use_gpu=getattr(config, "use_gpu", None),
            # Metadata fields
            laboratory=config.laboratory,
            disease=config.disease,
            group=config.group,
            batch=config.batch,
        )

    @classmethod
    def from_json(
        cls, json_data: str | dict, verbose: bool = False
    ) -> "MethylCentroid":
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
            "min_coverage": self.min_coverage,
            "use_gpu": self._gpu_enabled,
            "max_sample_workers": self.max_sample_workers,
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
                if hasattr(loaded_centroid, "as_extended_centroid"):
                    loaded_centroid = loaded_centroid.as_extended_centroid()
                else:
                    print(
                        f"Loaded centroid is not an extended centroid: {type(loaded_centroid)}"
                    )
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

    def add_sample(
        self, sample_index: int, is_new_sample: bool = False, sample_path: Path = None
    ) -> bool:
        # Determine which sample list to use and get the actual sample
        if sample_path is not None:
            sample = sample_path
        elif is_new_sample:
            if sample_index >= len(self.add_samples):
                print(f"Add sample index {sample_index} out of range")
                return False
            sample = self.add_samples[sample_index]
        else:
            if sample_index >= len(self.samples):
                print(f"Sample index {sample_index} out of range")
                return False
            sample = self.samples[sample_index]

        # Create a unique identifier for tracking active samples
        if sample_path is not None:
            sample_id = ("path", str(sample_path))
        else:
            sample_id = (is_new_sample, sample_index)

        if sample_id in self.active_samples:
            print(f"Sample {sample_index} (new={is_new_sample}) is already included.")
            return False

        if not sample.exists():
            print(f"Sample {sample} does not exist")
            return False

        methyl_sample = None
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

                builder = MethylCentroidBuilder(
                    min_coverage=self._min_coverage,
                    use_gpu=self.use_gpu,
                    store_extended_stats=True,
                )
                builder.add_sample(sample)
                self._centroid = builder.finalize()
                # Apply min_samples filter after builder finalizes
                if hasattr(self._centroid, "N") and len(self._centroid) > 0:
                    N_vals = (
                        np.asarray(self._centroid.N.values)
                        if hasattr(self._centroid.N, "values")
                        else np.asarray(self._centroid.N)
                    )
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

                            empty_df = pd.DataFrame(
                                {
                                    "pos": [],
                                    "mC": [],
                                    "uC": [],
                                    "tnc": [],
                                    "N": [],
                                    "Sx": [],
                                    "Sx2": [],
                                    "log_x_sum": [],
                                    "log_1_minus_x_sum": [],
                                }
                            )
                            self._centroid = MethylExtendedCentroid(
                                empty_df, self._centroid.metadata
                            )
            else:
                # Add sample to existing centroid
                self._centroid = self._centroid.add_sample(methyl_sample)

            self.active_samples.add(sample_id)
            self._print_progress()

        except Exception as e:
            print(f"Error processing {sample}: {e}")
            return False
        finally:
            if methyl_sample is not None:
                try:
                    methyl_sample.close()
                except Exception as e:
                    self.logger.debug(f"Sample cleanup failed: {e}")
            self._cleanup_gpu_after_sample()

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
        finally:
            try:
                methyl_sample.close()
            except Exception as e:
                self.logger.debug(f"Sample cleanup failed: {e}")
            self._cleanup_gpu_after_sample()

        self.active_samples.remove(index)

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
                    active_paths.append(
                        str(sample_path.parent)
                        if hasattr(sample_path, "parent")
                        else str(Path(sample_path).parent)
                    )
            else:
                # Sample from original samples list
                if sample_index < len(self.samples):
                    sample_path = self.samples[sample_index]
                    # Extract directory path (remove the H5 filename)
                    active_paths.append(
                        str(sample_path.parent)
                        if hasattr(sample_path, "parent")
                        else str(Path(sample_path).parent)
                    )
        return active_paths

    def _filter_missing_sample_files(self) -> List[Path]:
        """
        Filter out samples whose expected {chrom}-{ctx}.h5 files are missing.

        Returns:
            List of missing sample file paths.
        """
        missing_samples = [p for p in self.samples if not p.is_file()]
        missing_add_samples = [p for p in self.add_samples if not p.is_file()]
        missing = missing_samples + missing_add_samples

        if missing:
            preview = ", ".join(str(p) for p in missing[:5])
            suffix = " ..." if len(missing) > 5 else ""
            self.logger.warning(
                f"Skipping {len(missing)} missing sample files. "
                f"Examples: {preview}{suffix}"
            )

        # Keep only existing files
        self.samples = [p for p in self.samples if p.is_file()]
        self.add_samples = [p for p in self.add_samples if p.is_file()]

        return missing

    def add_samples_parallel(self):
        def load_sample_data(
            sample_path: Path,
        ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
            try:
                if not sample_path.is_file():
                    self.logger.warning(f"Sample file missing: {sample_path}")
                    return None

                from methyl_utils import MethylSample

                methyl_sample = MethylSample.load_from_h5(sample_path)
                original_sample = methyl_sample
                sample_cpu = None
                try:
                    # Ensure sample is on CPU (converts GPU arrays if needed)
                    sample_cpu = methyl_sample.to_cpu()
                    methyl_sample = sample_cpu

                    # Get underlying numpy arrays from Series properties
                    # Ensure we get actual numpy arrays, not cupy arrays or Series
                    pos_series = methyl_sample.pos
                    mC_series = methyl_sample.mC
                    uC_series = methyl_sample.uC
                    # Access tnc from DataFrame directly (no property defined)
                    tnc_series = methyl_sample._df["tnc"]

                    # Extract numpy arrays from Series
                    if hasattr(pos_series, "values"):
                        pos = np.asarray(pos_series.values, dtype=np.uint32)
                    else:
                        pos = np.asarray(pos_series, dtype=np.uint32)

                    if hasattr(mC_series, "values"):
                        mC = np.asarray(mC_series.values, dtype=np.uint32)
                    else:
                        mC = np.asarray(mC_series, dtype=np.uint32)

                    if hasattr(uC_series, "values"):
                        uC = np.asarray(uC_series.values, dtype=np.uint32)
                    else:
                        uC = np.asarray(uC_series, dtype=np.uint32)

                    if hasattr(tnc_series, "values"):
                        tnc = np.asarray(tnc_series.values, dtype=np.uint8)
                    else:
                        tnc = np.asarray(tnc_series, dtype=np.uint8)
                finally:
                    for sample_obj in (sample_cpu, original_sample):
                        if sample_obj is not None:
                            try:
                                sample_obj.close()
                            except Exception:
                                pass

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
                return None

        all_samples = self.samples + self.add_samples

        if self.ctx == "CHH":
            self.logger.info(
                "Using streaming centroid builder for CHH to reduce memory spikes"
            )
            from methyl_utils.core.centroid_builder import MethylCentroidBuilder

            builder = MethylCentroidBuilder(
                min_coverage=self._min_coverage,
                use_gpu=self.use_gpu,
                store_extended_stats=True,
            )

            for sample_idx, sample_path in enumerate(all_samples):
                if not sample_path.is_file():
                    self.logger.warning(f"Sample file missing: {sample_path}")
                    continue
                try:
                    builder.add_sample(sample_path)

                    is_new_sample = sample_idx >= len(self.samples)
                    actual_sample_idx = (
                        sample_idx - len(self.samples)
                        if is_new_sample
                        else sample_idx
                    )
                    sample_id = (is_new_sample, actual_sample_idx)
                    self.active_samples.add(sample_id)
                except Exception as e:
                    self.logger.error(
                        f"Failed to process sample {sample_path.name}: {e}"
                    )
                finally:
                    self._cleanup_gpu_after_sample()

            if builder.samples_processed == 0:
                return

            self._centroid = builder.finalize()
            # Apply min_samples filter after builder finalizes
            if hasattr(self._centroid, "N") and len(self._centroid) > 0:
                N_vals = (
                    np.asarray(self._centroid.N.values)
                    if hasattr(self._centroid.N, "values")
                    else np.asarray(self._centroid.N)
                )
                valid_mask = N_vals >= self.min_samples
                if not valid_mask.all():
                    valid_indices = np.where(valid_mask)[0]
                    if len(valid_indices) > 0:
                        self._centroid = self._centroid.apply_mask(valid_indices)
                    else:
                        from methyl_utils import MethylExtendedCentroid
                        import pandas as pd

                        empty_df = pd.DataFrame(
                            {
                                "pos": [],
                                "mC": [],
                                "uC": [],
                                "tnc": [],
                                "N": [],
                                "Sx": [],
                                "Sx2": [],
                                "log_x_sum": [],
                                "log_1_minus_x_sum": [],
                            }
                        )
                        self._centroid = MethylExtendedCentroid(
                            empty_df, self._centroid.metadata
                        )
            self.logger.info(
                f"Sample addition completed: {len(self.active_samples)} samples added"
            )
            return

        # Dynamic worker calculation based on memory and CPU
        memory_info = self.memory_manager.get_memory_usage()
        total_memory_gb = memory_info.get("total_gb", 400)
        available_memory_gb = memory_info.get("available_gb", 350)
        estimated_memory_per_sample_gb = 0.8  # Conservative estimate: 800MB per sample

        # Memory-based limit: reserve 30% of memory for processing
        memory_reserved_gb = total_memory_gb * 0.3
        max_workers_by_memory = max(
            1,
            int(
                (available_memory_gb - memory_reserved_gb)
                / estimated_memory_per_sample_gb
            ),
        )

        # CPU-based limit: use 75% of available CPUs
        cpu_count = psutil.cpu_count()
        max_workers_by_cpu = max(1, int(cpu_count * 0.75))

        # Context-based adjustment (CHH has more positions, needs more memory)
        context_multiplier = {"CG": 1.0, "CHG": 4.0, "CHH": 16.0}.get(self.ctx, 1.0)
        max_workers_by_memory = max(1, int(max_workers_by_memory / context_multiplier))

        # Final worker count
        actual_batch_size = min(
            max_workers_by_memory, max_workers_by_cpu, len(all_samples)
        )

        uncapped_batch_size = actual_batch_size
        cap = None
        cap_reason = None
        if self.max_sample_workers is not None:
            cap = self.max_sample_workers
            cap_reason = "config"
        elif self.ctx == "CHH":
            cap = 2
            cap_reason = "default for CHH"

        if cap is not None:
            actual_batch_size = min(actual_batch_size, cap)

        cap_note = ""
        if cap is not None and actual_batch_size < uncapped_batch_size:
            cap_note = f", capped at {cap}"
            if cap_reason == "default for CHH":
                cap_note += " (default for CHH)"

        self.logger.info(
            f"Using {actual_batch_size} parallel workers "
            f"(memory: {available_memory_gb:.1f}GB available, "
            f"context: {self.ctx}, multiplier: {context_multiplier:.1f}{cap_note})"
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
                methyl_sample = None
                builder = None
                try:
                    result = future.result()

                    if result is None:
                        continue

                    pos, mC, uC, tnc = result

                    # Skip empty samples
                    if len(pos) == 0:
                        # Skip debug logging during tqdm operations to avoid progress bar interference
                        continue

                    # Create MethylSample-like object for position aligner
                    # Add sample using new method
                    if self._centroid is None:
                        from methyl_utils.core.centroid_builder import (
                            MethylCentroidBuilder,
                        )

                        builder = MethylCentroidBuilder(
                            min_coverage=self._min_coverage,
                            use_gpu=self.use_gpu,
                            store_extended_stats=True,
                        )
                        builder.add_sample(sample_path)
                        self._centroid = builder.finalize()
                        # Apply min_samples filter after builder finalizes
                        if hasattr(self._centroid, "N") and len(self._centroid) > 0:
                            N_vals = (
                                np.asarray(self._centroid.N.values)
                                if hasattr(self._centroid.N, "values")
                                else np.asarray(self._centroid.N)
                            )
                            valid_mask = N_vals >= self.min_samples
                            if not valid_mask.all():
                                # Filter out positions with N < min_samples
                                # Use integer indices instead of boolean mask to avoid pandas indexing issues
                                valid_indices = np.where(valid_mask)[0]
                                if len(valid_indices) > 0:
                                    self._centroid = self._centroid.apply_mask(
                                        valid_indices
                                    )
                                else:
                                    # No valid positions, create empty centroid
                                    from methyl_utils import MethylExtendedCentroid
                                    import pandas as pd

                                    empty_df = pd.DataFrame(
                                        {
                                            "pos": [],
                                            "mC": [],
                                            "uC": [],
                                            "tnc": [],
                                            "N": [],
                                            "Sx": [],
                                            "Sx2": [],
                                            "log_x_sum": [],
                                            "log_1_minus_x_sum": [],
                                        }
                                    )
                                    self._centroid = MethylExtendedCentroid(
                                        empty_df, self._centroid.metadata
                                    )
                    else:
                        # Load the actual MethylSample and add it
                        methyl_sample = self.load_sample(sample_path)
                        self._centroid = self._centroid.add_sample(methyl_sample)
                    success = True

                    if success:
                        # Mark as active sample
                        is_new_sample = sample_idx >= len(self.samples)
                        actual_sample_idx = (
                            sample_idx - len(self.samples)
                            if is_new_sample
                            else sample_idx
                        )
                        sample_id = (is_new_sample, actual_sample_idx)
                        self.active_samples.add(sample_id)
                    else:
                        self.logger.warning(
                            f"Failed to add sample {sample_path.name} to position aligner"
                        )

                except Exception as e:
                    self.logger.error(
                        f"Failed to process sample {sample_path.name}: {e}"
                    )
                    continue
                finally:
                    if methyl_sample is not None:
                        try:
                            methyl_sample.close()
                        except Exception as e:
                            self.logger.debug(f"Sample cleanup failed: {e}")
                    if builder is not None:
                        del builder
                    self._cleanup_gpu_after_sample()

        self.logger.info(
            f"Parallel sample addition completed: {len(self.active_samples)} samples added"
        )

    def _calculate_chunked_processor_params(
        self, use_gpu: bool
    ) -> Dict[str, Union[int, float]]:
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
        system_memory_used_gb = memory_info.get("system_memory_mb", 0) / 1024
        system_memory_available_gb = system_memory_total_gb - system_memory_used_gb

        # GPU memory information
        gpu_available_gb = 0.0
        gpu_free_gb = 0.0
        if use_gpu and is_gpu_available():
            gpu_available_gb = memory_info.get("gpu_memory_gb", 0)
            gpu_free_gb = memory_info.get("gpu_free_gb", 0)

        self.logger.debug(
            f"Memory status - System: {system_memory_available_gb:.1f}GB available "
            f"({system_memory_total_gb:.1f}GB total), "
            f"GPU: {gpu_free_gb:.1f}GB free ({gpu_available_gb:.1f}GB used)"
        )

        # Use latest MethylUtils GPU-optimized chunk sizing for genome-scale processing
        # Target: 95% GPU utilization with 500M position chunks for optimal performance
        if use_gpu and gpu_free_gb >= 80.0:  # GH200 with sufficient GPU memory
            # Maximum GPU utilization: 500M positions per chunk for 6 total chunks on 3B positions
            chunk_size_positions = 500_000_000  # 500M positions
            memory_limit_gb = min(
                system_memory_available_gb * 0.8, 350.0
            )  # Use 80% of available RAM
            max_workers = 1  # Sequential processing for maximum GPU utilization

            self.logger.info(
                f"Using genome-scale GPU optimization: {chunk_size_positions:,} positions per chunk "
                f"({memory_limit_gb:.1f}GB RAM limit)"
            )

        elif use_gpu and gpu_free_gb >= 40.0:  # Other GPUs with decent memory
            # High GPU utilization: 100M positions per chunk
            chunk_size_positions = 100_000_000  # 100M positions
            memory_limit_gb = min(system_memory_available_gb * 0.7, 200.0)
            max_workers = 1

            self.logger.info(
                f"Using high GPU optimization: {chunk_size_positions:,} positions per chunk"
            )

        else:
            # Fallback to memory-optimized chunking for CPU or limited GPU
            # Dynamic chunk size calculation based on context and available memory
            context_base_chunks = {
                "CG": 50_000_000,  # 50M positions - leverage MethylUtils memory efficiency
                "CHG": 25_000_000,  # 25M positions - medium density
                "CHH": 10_000_000,  # 10M positions - high density, moderate chunks
            }

            base_chunk_size = context_base_chunks.get(
                self.ctx, 20_000_000
            )  # Default 20M

            # Memory-based chunk size adjustment using MethylUtils memory calculations
            memory_limit_gb = (
                system_memory_available_gb * 0.6
            )  # Reserve 40% for other operations

            # Calculate optimal chunk size based on memory per position estimates
            # Use estimated bytes per position from loaded samples if available, otherwise conservative default
            if (
                hasattr(self, "sample_cache")
                and self.sample_cache._estimated_bytes_per_sample is not None
            ):
                memory_per_position_kb = (
                    self.sample_cache._estimated_bytes_per_sample / 1024
                )  # Convert bytes to KB
            else:
                memory_per_position_kb = (
                    0.15  # Conservative default estimate including overhead
                )

            max_positions_by_memory = int(
                (memory_limit_gb * 1024 * 1024) / memory_per_position_kb
            )

            chunk_size_positions = min(base_chunk_size, max_positions_by_memory)
            max_workers = max(
                1, int(system_memory_available_gb / 50)
            )  # 1 worker per 50GB RAM

        # Ensure reasonable minimums and maximums
        chunk_size_positions = max(
            1_000_000, min(chunk_size_positions, 500_000_000)
        )  # 1M to 500M
        memory_limit_gb = max(
            10.0, min(memory_limit_gb, system_memory_available_gb * 0.9)
        )
        max_workers = max(1, min(max_workers, 8))  # 1-8 workers

        return {
            "chunk_size_positions": chunk_size_positions,
            "max_workers": max_workers,
            "memory_limit_gb": memory_limit_gb,
        }

    def _load_sample_for_alignment_memory_aware(
        self, sample_path: Path, sample_idx: int
    ) -> Optional["MethylSample"]:
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
            available_gb = memory_info.get("available_gb", 350)

            # If memory is getting low, clear cache to free up space
            if available_gb < 50:  # Less than 50GB available
                self.logger.debug(
                    f"Low memory detected ({available_gb:.1f}GB), clearing cache"
                )
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
                    self.logger.debug(
                        f"Sample {sample_idx}: {len(sample.pos):,} positions, "
                        f"coverage: {coverage[valid_mask].mean():.1f}"
                    )

                return sample
            else:
                self.logger.warning(
                    f"Sample {sample_path.name} has no positions with coverage"
                )
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

    def _load_sample_for_alignment_memory_aware(
        self, sample_path: Path, sample_idx: int
    ) -> Optional["MethylSample"]:
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
            available_gb = memory_info.get("available_gb", 350)

            # If memory is getting low, clear cache to free up space
            if available_gb < 50:  # Less than 50GB available
                self.logger.debug(
                    f"Low memory detected ({available_gb:.1f}GB), clearing cache"
                )
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
                    self.logger.debug(
                        f"Sample {sample_idx}: {len(sample.pos):,} positions, "
                        f"coverage: {coverage[valid_mask].mean():.1f}"
                    )

                return sample
            else:
                self.logger.warning(
                    f"Sample {sample_path.name} has no positions with coverage"
                )
                return None

        except Exception as e:
            self.logger.error(f"Failed to load sample {sample_path}: {e}")
            return None

    def _monitor_memory_during_loading(self):
        """Monitor memory usage during sample loading and take corrective actions."""
        memory_info = self.memory_manager.get_memory_usage()
        used_percent = memory_info.get("percent_used", 0)

        # If memory usage is too high, clear cache
        if used_percent > 85:
            self.logger.warning(
                f"High memory usage detected ({used_percent:.1f}%), clearing cache"
            )
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

    def save_centroid(
        self, output_dir: str, centroid_data=None, extended: bool = False
    ) -> Path:
        if centroid_data is None:
            centroid_data = self.compute_centroid(extended=extended)

        if centroid_data is None or len(centroid_data) == 0:
            print("No valid centroid data to save")
            return None

        # Get active sample paths (those currently in the centroid)
        active_sample_paths = self._get_active_sample_paths()

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
            "creation_date": datetime.now().isoformat(),  # NEW: Creation timestamp
            "min_coverage": self.min_coverage,
        }
        if self.enable_binned_stats and self._binned_stats is not None:
            metadata["binned_stats_enabled"] = True
            metadata["binned_stats_bins"] = int(self.binned_stats_bins)

        # Create MethylSample from centroid data with metadata
        # centroid_data is a structured numpy array, convert to DataFrame
        import pandas as pd
        from methyl_utils import (
            MethylSample,
            MethylBasicCentroid,
            MethylExtendedCentroid,
        )

        # Convert structured array to DataFrame
        if isinstance(centroid_data, np.ndarray) and centroid_data.dtype.names:
            # Structured array - convert field by field
            if len(centroid_data) > 0:
                df = pd.DataFrame(
                    {name: centroid_data[name] for name in centroid_data.dtype.names}
                )
            else:
                # Empty structured array - create empty DataFrame with expected columns
                df = pd.DataFrame({name: [] for name in centroid_data.dtype.names})
        else:
            # Already a DataFrame or regular array
            df = (
                pd.DataFrame(centroid_data)
                if not isinstance(centroid_data, pd.DataFrame)
                else centroid_data
            )

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

        # Attach binned stats if available
        if self.enable_binned_stats and self._binned_stats is not None:
            try:
                methyl_sample.set_binned_stats(
                    self._binned_stats["bin_edges"], self._binned_stats["bin_counts"]
                )
            except Exception as e:
                self.logger.warning(f"Failed to attach binned stats to centroid: {e}")

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
            raise OSError(
                f"Permission denied creating output directory {output_path}. "
                f"Please ensure the parent directory is writable: {output_path.parent}. "
                f"Original error: {e}"
            )
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

    def load_centroid(self, centroid_path: Union[str, Path]) -> "MethylSample":
        from methyl_utils import MethylSample

        methyl_sample = MethylSample.load_from_h5(centroid_path)

        # Ensure arrays are NumPy arrays
        # Use to_cpu() method instead of manual .get() calls
        return methyl_sample.to_cpu()

    def load_sample(
        self, sample_path: Union[str, Path], memory_map: bool = True
    ) -> "MethylSample":
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

    def _ensure_numpy_arrays(self, methyl_sample: "MethylSample") -> "MethylSample":
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

    def _cleanup_gpu_after_sample(self) -> None:
        if self.use_gpu:
            cleanup_gpu_memory()

    def calculate_centroid(self, output_dir: str, extended: bool = False) -> Path:
        print(
            f"Adding {len(self.samples) + len(self.add_samples)} samples for {self.chrom}-{self.ctx}"
        )

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
            raise OSError(
                f"Permission denied creating output directory {output_path}. "
                f"Please ensure the parent directory is writable: {output_path.parent}. "
                f"Original error: {e}"
            )
        except Exception as e:
            raise OSError(f"Cannot create output directory {output_path}: {e}")

        # Add all samples in parallel
        missing_samples = self._filter_missing_sample_files()
        if not self.samples and not self.add_samples:
            expected_suffix = f"{self.chrom}-{self.ctx}.h5"
            if missing_samples:
                preview = ", ".join(str(p) for p in missing_samples[:5])
                suffix = " ..." if len(missing_samples) > 5 else ""
                raise FileNotFoundError(
                    "No valid sample files found. "
                    f"Expected files like {expected_suffix}. "
                    f"Missing examples: {preview}{suffix}"
                )
            raise FileNotFoundError(
                f"No valid sample files found. Expected files like {expected_suffix}."
            )

        self.add_samples_parallel()

        # Check if any samples were successfully added
        if len(self.active_samples) == 0:
            raise RuntimeError(
                "Failed to compute centroid: no samples were successfully added"
            )

        # Compute and save centroid
        if self.enable_binned_stats:
            centroid = self.compute_centroid_chunked(extended=extended)
        else:
            centroid = self.compute_centroid(extended=extended)
        if centroid is None or len(centroid) == 0:
            raise RuntimeError(
                "Failed to compute centroid: no samples were successfully added"
            )

        centroid_path = self.save_centroid(output_dir, centroid, extended=extended)
        if centroid_path is None:
            raise RuntimeError("Failed to save centroid: no valid data to save")

        return centroid_path

    def compute_centroid_chunked(
        self, extended: bool = False, chunk_size_positions: int = 2_000_000
    ) -> Optional[np.ndarray]:
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
        with self.performance_profiler.profile_operation(
            "chunked_centroid_computation"
        ):
            # Use MethylUtils GPU cleanup for safe resource management
            memory_manager = get_memory_manager()

            self.logger.info(
                f"Computing centroid using chunked processing (chunk size: {chunk_size_positions:,} positions)"
            )

            # Get all unique positions across all samples
            all_positions = set()
            if self._centroid is None or len(self._centroid) == 0:
                self.logger.warning("No samples available for centroid computation")
                return None

            # Get positions from centroid
            centroid_positions = np.asarray(self._centroid.pos.values, dtype=np.uint32)
            all_positions = set(centroid_positions)

            total_positions = len(all_positions)
            self.logger.info(
                f"Found {total_positions:,} unique positions across all samples"
            )

            if total_positions == 0:
                self.logger.warning("No positions found in samples")
                return None

            # Sort positions for chunking
            sorted_positions = np.array(sorted(all_positions), dtype=np.uint32)

            # Process in chunks
            chunk_results = []
            chunk_bin_counts = []
            total_chunks = (
                total_positions + chunk_size_positions - 1
            ) // chunk_size_positions

            self.logger.info(f"Processing {total_chunks} chunks...")

            for chunk_idx in tqdm(range(total_chunks), desc="Processing chunks"):
                start_pos = chunk_idx * chunk_size_positions
                end_pos = min(start_pos + chunk_size_positions, total_positions)
                chunk_positions = sorted_positions[start_pos:end_pos]

                with self.performance_profiler.profile_operation(
                    f"chunk_{chunk_idx}_processing"
                ):
                    chunk_centroid = self._compute_centroid_for_positions(
                        chunk_positions, extended
                    )
                    if chunk_centroid is not None:
                        if self.enable_binned_stats and isinstance(
                            chunk_centroid, tuple
                        ):
                            centroid_part, bin_counts_part = chunk_centroid
                            if centroid_part is not None:
                                chunk_results.append(centroid_part)
                                chunk_bin_counts.append(bin_counts_part)
                        else:
                            chunk_results.append(chunk_centroid)

            if not chunk_results:
                self.logger.error("No chunks produced valid centroid data")
                return None

            # Combine chunk results
            self.logger.info(f"Combining {len(chunk_results)} chunk results...")
            if self.enable_binned_stats:
                combined = self._combine_chunked_centroids(
                    chunk_results, extended, bin_counts=chunk_bin_counts
                )
                if isinstance(combined, tuple):
                    final_centroid, combined_bins = combined
                    bin_edges = np.linspace(
                        0.0, 1.0, self.binned_stats_bins + 1, dtype=np.float32
                    )
                    self._binned_stats = {
                        "bin_edges": bin_edges,
                        "bin_counts": combined_bins,
                    }
                else:
                    final_centroid = combined
                    self._binned_stats = None
            else:
                final_centroid = self._combine_chunked_centroids(
                    chunk_results, extended
                )

            # Ensure GPU cleanup after chunked processing
            memory_manager.force_gpu_cleanup()

            self.logger.info("Chunked centroid computation completed")
            return final_centroid

    def _compute_centroid_for_positions(
        self, positions: np.ndarray, extended: bool = False
    ) -> Optional[np.ndarray]:
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
        mC_accum = np.zeros(len(positions), dtype=np.uint32)
        uC_accum = np.zeros(len(positions), dtype=np.uint32)
        # Always track N_accum for min_samples filtering, even for non-extended centroids
        N_accum = np.zeros(len(positions), dtype=np.uint32)

        if extended:
            Sx_accum = np.zeros(len(positions), dtype=np.float32)
            Sx2_accum = np.zeros(len(positions), dtype=np.float32)

        bin_counts = None
        if self.enable_binned_stats:
            bin_dtype = np.uint16 if sample_count < 60000 else np.uint32
            bin_counts = np.zeros(
                (len(positions), self.binned_stats_bins), dtype=bin_dtype
            )

        # Process each sample for these positions
        for sample_idx in range(sample_count):
            # Load sample directly instead of getting from aligner
            sample_path = (
                self.samples[sample_idx]
                if sample_idx < len(self.samples)
                else self.add_samples[sample_idx - len(self.samples)]
            )
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

            if extended or self.enable_binned_stats:
                # Calculate methylation level for this sample
                valid_positions = coverage > 0
                if valid_positions.any():
                    methylation_level = np.zeros(len(positions), dtype=np.float32)
                    methylation_level[valid_positions] = (
                        aligned_mC[valid_positions] / coverage[valid_positions]
                    )

                    if extended:
                        Sx_accum += methylation_level
                        Sx2_accum += methylation_level**2

                    if self.enable_binned_stats and bin_counts is not None:
                        bin_idx = np.floor(
                            methylation_level * self.binned_stats_bins
                        ).astype(np.int32)
                        bin_idx = np.clip(bin_idx, 0, self.binned_stats_bins - 1)
                        idxs = np.where(valid_positions)[0]
                        np.add.at(bin_counts, (idxs, bin_idx[idxs]), 1)

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

            centroid_data["pos"] = positions[valid_positions]
            centroid_data["mC"] = mC_accum[valid_positions]
            centroid_data["uC"] = uC_accum[valid_positions]
            centroid_data["tnc"] = np.zeros(
                np.sum(valid_positions), dtype=np.uint8
            )  # Default context
            centroid_data["N"] = N_accum[valid_positions]
            centroid_data["Sx"] = Sx_accum[valid_positions]
            centroid_data["Sx2"] = Sx2_accum[valid_positions]
            # Extended fields would be computed separately if needed

        else:
            from methyl_utils import get_methyl_dtype

            dtype = get_methyl_dtype(extended=False)
            centroid_data = np.empty(np.sum(valid_positions), dtype=dtype)

            centroid_data["pos"] = positions[valid_positions]
            centroid_data["mC"] = mC_accum[valid_positions]
            centroid_data["uC"] = uC_accum[valid_positions]
            centroid_data["tnc"] = np.zeros(
                np.sum(valid_positions), dtype=np.uint8
            )  # Default context
            # Use actual per-position N (number of samples that contributed to each position)
            centroid_data["N"] = N_accum[valid_positions]

        if self.enable_binned_stats and bin_counts is not None:
            bin_counts = bin_counts[valid_positions]
            return centroid_data, bin_counts

        return centroid_data

    def _combine_chunked_centroids(
        self,
        chunk_results: List[np.ndarray],
        extended: bool = False,
        bin_counts: Optional[List[np.ndarray]] = None,
    ) -> Optional[np.ndarray]:
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
            combined_bins = None
            if bin_counts is not None and len(bin_counts) == len(chunk_results):
                combined_bins = np.concatenate(bin_counts)

            # Sort by position
            sort_idx = np.argsort(combined_centroid["pos"])
            combined_centroid = combined_centroid[sort_idx]
            if combined_bins is not None:
                combined_bins = combined_bins[sort_idx]

            self.logger.info(f"Combined centroid: {len(combined_centroid):,} positions")
            if combined_bins is not None:
                return combined_centroid, combined_bins
            return combined_centroid

        except Exception as e:
            self.logger.error(f"Failed to combine chunked centroids: {e}")
            return None

    def _load_sample(
        self, sample_path: Path
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
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
            def sample_loader(path: Path) -> "MethylSample":
                return self.load_sample(path, memory_map=True)

            cached_sample = self.sample_cache.get(sample_path, sample_loader)
            if cached_sample is not None:
                # Ensure sample is on CPU and get numpy arrays
                cached_sample = cached_sample.to_cpu()
                # Extract sorted arrays from cached MethylSample
                pos_vals = (
                    cached_sample.pos.values
                    if hasattr(cached_sample.pos, "values")
                    else np.asarray(cached_sample.pos)
                )
                mC_vals = (
                    cached_sample.mC.values
                    if hasattr(cached_sample.mC, "values")
                    else np.asarray(cached_sample.mC)
                )
                uC_vals = (
                    cached_sample.uC.values
                    if hasattr(cached_sample.uC, "values")
                    else np.asarray(cached_sample.uC)
                )
                sort_idx = np.argsort(pos_vals)
                return (pos_vals[sort_idx], mC_vals[sort_idx], uC_vals[sort_idx])

        # Fallback: load without caching
        try:
            methyl_sample = self.load_sample(sample_path, memory_map=True)

            # Ensure sample is on CPU and get numpy arrays
            methyl_sample = methyl_sample.to_cpu()

            # Get underlying numpy arrays from Series properties
            pos_vals = (
                methyl_sample.pos.values
                if hasattr(methyl_sample.pos, "values")
                else np.asarray(methyl_sample.pos)
            )
            mC_vals = (
                methyl_sample.mC.values
                if hasattr(methyl_sample.mC, "values")
                else np.asarray(methyl_sample.mC)
            )
            uC_vals = (
                methyl_sample.uC.values
                if hasattr(methyl_sample.uC, "values")
                else np.asarray(methyl_sample.uC)
            )

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

    def process_large_sample_chunked(
        self, sample_path: Path, chunk_size: int = 1_000_000
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        self.logger.info(f"Processing large sample {sample_path.name} in chunks")

        # Create a processing function for chunks
        def process_sample_chunk(chunk_data, **kwargs):
            pos = chunk_data.get("pos", np.array([]))
            mC = chunk_data.get("mC", np.array([]))
            uC = chunk_data.get("uC", np.array([]))

            # Filter for valid positions (some coverage)
            if len(mC) > 0 and len(uC) > 0:
                coverage = mC + uC
                valid_mask = coverage >= self.min_coverage
                return {
                    "pos": pos[valid_mask],
                    "mC": mC[valid_mask],
                    "uC": uC[valid_mask],
                    "positions_processed": np.sum(valid_mask),
                }
            else:
                return {
                    "pos": np.array([], dtype=np.uint32),
                    "mC": np.array([], dtype=np.uint32),
                    "uC": np.array([], dtype=np.uint32),
                    "positions_processed": 0,
                }

        # Configure chunked processor for this sample
        self.chunked_processor.chunk_size_positions = chunk_size

        # Process the file in chunks
        results = self.chunked_processor.process_file_chunked(
            sample_path,
            process_sample_chunk,
            self.output_dir / "temp_chunks",
            cleanup_temp=True,
        )

        # Aggregate results from all chunks
        all_pos = []
        all_mC = []
        all_uC = []

        for result in results.get("chunk_results", []):
            if result.success and result.data["positions_processed"] > 0:
                all_pos.append(result.data["pos"])
                all_mC.append(result.data["mC"])
                all_uC.append(result.data["uC"])

        if all_pos:
            # Concatenate all chunks
            return (
                np.concatenate(all_pos),
                np.concatenate(all_mC),
                np.concatenate(all_uC),
            )
        else:
            # Return empty arrays if no valid data
            return (
                np.array([], dtype=np.uint32),
                np.array([], dtype=np.uint32),
                np.array([], dtype=np.uint32),
            )

    def _backup_centroid(self, centroid_path: Path) -> Path:
        """Helper for atomic operations - preserved for future use."""
        backup_path = centroid_path.with_suffix(".h5.bak")
        if centroid_path.exists():
            import shutil

            shutil.copy2(centroid_path, backup_path)
        return backup_path

    def _restore_centroid(self, centroid_path: Path, backup_path: Path):
        """Helper for atomic operations - preserved for future use."""
        if backup_path.exists():
            import shutil

            if centroid_path.exists():
                centroid_path.unlink()
            shutil.move(backup_path, centroid_path)

    def _cleanup_backup(self, backup_path: Path):
        """Helper for atomic operations - preserved for future use."""
        if backup_path.exists():
            backup_path.unlink()

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

    def _clear_sample_cache(self):
        """Clear the intelligent sample cache."""
        if hasattr(self.sample_cache, "clear"):
            cache_stats = self.sample_cache.get_stats()
            self.logger.info(
                f"Clearing sample cache: {cache_stats['cached_samples']} samples, "
                f"{cache_stats['memory_usage_mb']:.1f}MB memory"
            )
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
            "cache_stats": self.sample_cache.get_stats()
            if hasattr(self.sample_cache, "get_stats")
            else {"cached_samples": 0},
        }

    def _prepare_for_gpu_processing(self):
        memory_info = self._get_memory_usage_info()

        # If memory usage is high (>80%), clear the sample cache
        if memory_info["percent_used"] > 80:
            self.logger.info(
                "High memory usage detected, clearing sample cache for processing..."
            )
            self._clear_sample_cache()

        # GPU memory pressure handling with automatic CPU fallback
        if self._using_gpu:
            try:
                from scripts.gpu_memory_utils import GPUMemoryUtils

                if GPUMemoryUtils.is_memory_pressure_high(threshold_percent=85.0):
                    self.logger.warning(
                        "GPU memory pressure detected, attempting cleanup..."
                    )
                    GPUMemoryUtils.cleanup_gpu_memory(aggressive=True)

                    # Check if cleanup helped
                    if GPUMemoryUtils.is_memory_pressure_high(threshold_percent=90.0):
                        self.logger.warning(
                            "GPU memory pressure persists, falling back to CPU processing"
                        )
                        self._fallback_to_cpu_processing()
                        self._gpu_memory_pressure_detected = True
                    else:
                        self.logger.info("GPU memory pressure alleviated after cleanup")
            except ImportError:
                # GPU memory utilities not available, check for basic GPU memory issues
                self.logger.debug(
                    "GPU memory utilities not available, monitoring basic GPU usage"
                )
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

        self.logger.info(
            "Switching to CPU processing mode for reliability with large datasets"
        )
        self._using_gpu = False

        # Reinitialize chunked processor with dynamic CPU parameters
        try:
            cpu_params = self._calculate_chunked_processor_params(use_gpu=False)
            self.chunked_processor = ChunkedGenomicProcessor(
                chunk_size_positions=cpu_params["chunk_size_positions"],
                max_workers=cpu_params["max_workers"],
                use_gpu=False,
                memory_limit_gb=cpu_params["memory_limit_gb"],
            )

            # Clear any GPU-based caches that might cause issues
            self._clear_sample_cache()

            self.logger.info("Successfully switched chunked processing to CPU mode")
        except Exception as e:
            self.logger.error(f"Failed to switch chunked processing to CPU: {e}")
            raise RuntimeError("Cannot fallback to CPU processing") from e

    def _attempt_gpu_recovery(self):
        """Attempt to recover GPU usage if memory pressure has eased"""
        if not self._gpu_enabled or not self._gpu_available or self._using_gpu:
            return  # GPU not available or already using GPU

        try:
            # Test if GPU is available again
            import cupy as cp

            test_array = cp.zeros((100, 100), dtype=cp.float32)
            del test_array
            cp.cuda.Device(0).synchronize()

            self.logger.info(
                "GPU memory pressure appears resolved, attempting to recover GPU usage"
            )
            self._using_gpu = True

            # Reinitialize chunked processor with dynamic GPU parameters
            gpu_params = self._calculate_chunked_processor_params(use_gpu=True)
            self.chunked_processor = ChunkedGenomicProcessor(
                chunk_size_positions=gpu_params["chunk_size_positions"],
                max_workers=gpu_params["max_workers"],
                use_gpu=True,
                memory_limit_gb=gpu_params["memory_limit_gb"],
            )

            self._gpu_memory_pressure_detected = False
            self.logger.info("Successfully recovered GPU processing mode")

        except Exception as e:
            self.logger.debug(f"GPU recovery test failed, staying with CPU: {e}")
            self._using_gpu = False

    def build_centroid(self) -> CentroidResults:
        """Build centroid with comprehensive performance profiling."""
        with self.performance_profiler.profile_operation("build_centroid"):
            # Check if centroid exists
            centroid_exists = self.centroid_path.exists()

            if centroid_exists:
                print(
                    f"Centroid file exists at {self.centroid_path}, rebuilding from samples"
                )

        # Calculate extended centroid
        try:
            # Note: extended=True computes stats like standard deviation which are useful

            centroid_path = self.calculate_centroid(str(self.output_dir), extended=True)
            if centroid_path is None:
                raise RuntimeError(
                    "Failed to compute centroid: calculate_centroid returned None"
                )
        except RuntimeError as e:
            error_msg = str(e).lower()
            if (
                "no samples" in error_msg
                or "failed to compute" in error_msg
                or "failed to save" in error_msg
            ):
                # Return empty results if no samples were added
                return CentroidResults(
                    final_centroid_path="", total_samples_processed=0
                )
            raise

        # Update config with final state
        self.save_final_config()

        # Return results
        return CentroidResults(
            final_centroid_path=str(centroid_path),
            total_samples_processed=len(self.active_samples),
        )

    def save_final_config(self) -> None:
        """
        Save the configuration file with current samples.
        """
        # Get current active samples
        current_samples = []

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

        # Update the original tracking lists
        self._original_samples = current_samples
        self._original_add_samples = []  # Clear add_samples after processing

        # Save updated config
        config = self.get_config()
        config_path = self.output_dir / f"{self.chrom}-{self.ctx}_config.json"
        with open(config_path, "w") as f:
            json.dump(config.model_dump(), f, indent=2)

        print(f"Updated configuration saved to {config_path}")
        print(f"Total samples: {len(current_samples)}")

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
                    sample_pos = np.asarray(
                        methyl_sample_cpu.pos.values, dtype=np.uint32
                    )
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
            with np.errstate(divide="ignore", invalid="ignore"):
                direct_mC[valid_N] = np.where(
                    valid_N_mask,
                    direct_mC[valid_N].astype(np.float64)
                    / direct_N[valid_N].astype(np.float64),
                    0.0,
                ).astype(np.uint32)
                direct_uC[valid_N] = np.where(
                    valid_N_mask,
                    direct_uC[valid_N].astype(np.float64)
                    / direct_N[valid_N].astype(np.float64),
                    0.0,
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

    parser = argparse.ArgumentParser(description="Calculate methylation centroids")
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
        )

        # Build extended centroid with methylation statistics
        results = mc.build_centroid()
        print(f"Completed {args.chrom}-{args.ctx}")

        # Save results
        json_file_path = out_dir / f"{args.chrom}-{args.ctx}.json"
        with open(json_file_path, "w") as json_file:
            json.dump(results.model_dump(mode="json"), json_file)

        print(f"Results saved to {json_file_path}")

    else:
        # Original default mode
        data_dir = Path("/home/ubuntu/Work/output_workflows/arabidopsis")
        chroms = [str(i) for i in range(1, 6)]  # + ["X"]
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
                )
                # Build extended centroid with methylation statistics
                results = mc.build_centroid()
                print(f"Completed {chrom}-{ctx}")

                # Save configuration
                config = mc.get_config()
                with open(out_dir / f"{chrom}-{ctx}_config.json", "w") as f:
                    json.dump(config.model_dump(), f)

                combination_stats = {
                    "chromosome": chrom,
                    "context": ctx,
                    "iterations": 0,
                    "timestamp": datetime.now().isoformat(),
                }

                # Add methylation statistics if available
                # Check if centroid has methylation stats (extended centroid always has them)
                if mc._centroid is not None and isinstance(
                    mc._centroid, MethylExtendedCentroid
                ):
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

        # Save batch statistics
        batch_stats_file_path = out_dir / "batch_methylation_statistics.json"
        with open(batch_stats_file_path, "w") as f:
            json.dump(batch_stats, f, indent=2)
        print(f"\nSaved batch statistics to {batch_stats_file_path}")
        print(
            f"Batch summary: {batch_stats['combinations_processed']} combinations processed"
        )


def attach_binned_stats_to_centroid(
    centroid_path: Union[str, Path],
    bins: int = 32,
    output_dir: Optional[Union[str, Path]] = None,
    chunk_size_positions: int = 2_000_000,
    sample_dirs: Optional[List[str]] = None,
    verbose: bool = True,
) -> Path:
    """
    Attach centroid-level binned stats by reprocessing sample files.

    This reuses the existing centroid positions but recomputes statistics
    from the original samples to generate bin counts. It overwrites the
    centroid file unless output_dir is provided.
    """
    centroid_path = Path(centroid_path)
    from methyl_utils import MethylSample

    centroid = MethylSample.load_from_h5(centroid_path)
    meta = centroid.metadata or {}
    chrom = meta.get("chromosome")
    ctx = meta.get("context")
    if not chrom or not ctx:
        raise ValueError(
            "Centroid metadata missing chromosome/context; cannot attach binned stats"
        )

    if sample_dirs is None:
        sample_dirs = meta.get("samples_used", [])
    if not sample_dirs:
        raise ValueError("No sample directories available to rebuild binned stats")

    out_dir = Path(output_dir) if output_dir is not None else centroid_path.parent

    worker = MethylCentroid(
        chrom=chrom,
        ctx=ctx,
        output_dir=out_dir,
        samples=sample_dirs,
        min_coverage=int(meta.get("min_coverage", 4)),
        min_samples=int(meta.get("min_samples", 1)),
        verbose=verbose,
        enable_binned_stats=True,
        binned_stats_bins=int(bins),
        laboratory=meta.get("laboratory"),
        disease=meta.get("disease"),
        group=meta.get("group"),
        batch=meta.get("batch"),
    )

    # Use existing centroid positions for chunking
    worker._centroid = centroid
    worker.active_samples = set((False, i) for i in range(len(worker.samples)))

    centroid_data = worker.compute_centroid_chunked(
        extended=True, chunk_size_positions=chunk_size_positions
    )
    if centroid_data is None or len(centroid_data) == 0:
        raise RuntimeError("Failed to compute centroid with binned stats")

    return worker.save_centroid(str(out_dir), centroid_data, extended=True)
