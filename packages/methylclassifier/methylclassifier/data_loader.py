"""
Data loading functionality for MethylClassifier
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import numpy as np


class MethylationSample(ABC):
    """
    Abstract base class for methylation samples.

    This provides a common interface for different methylation data formats.
    """

    @property
    @abstractmethod
    def positions(self) -> np.ndarray:
        """Get genomic positions."""
        pass

    @property
    @abstractmethod
    def methylation_levels(self) -> np.ndarray:
        """Get methylation levels."""
        pass

    @property
    @abstractmethod
    def coverage(self) -> np.ndarray:
        """Get coverage information."""
        pass

    @property
    @abstractmethod
    def sample_type(self) -> str:
        """Get sample type identifier."""
        pass

    @property
    @abstractmethod
    def is_centroid(self) -> bool:
        """Check if this is a centroid sample."""
        pass

    @abstractmethod
    def get_beta_parameters(self) -> Tuple[np.ndarray, np.ndarray]:
        """Get beta distribution parameters (for centroids)."""
        pass


class H5MethylationSample(MethylationSample):
    """
    H5-based methylation sample implementation.

    This implementation works with .h5 files from methyl_utils.
    """

    def __init__(self, h5_path: Path):
        self.h5_path = h5_path
        self._sample = None
        self._load_sample()

    def _load_sample(self):
        """Load the sample from H5 file."""
        try:
            # Try to import methyl_utils classes
            from methyl_utils import MethylSample
            self._sample = MethylSample.load_from_h5(self.h5_path)
        except ImportError:
            raise ImportError(
                "methyl_utils package is required for H5 file support. "
                "Please install it or use a different data format."
            )

    @property
    def positions(self) -> np.ndarray:
        """Get genomic positions."""
        return self._sample.pos

    @property
    def methylation_levels(self) -> np.ndarray:
        """Get methylation levels."""
        # Use the new get_methylation_levels() method which automatically handles different sample types
        levels = self._sample.get_methylation_levels()

        # Handle NaN values and ensure proper range
        levels = np.nan_to_num(levels, nan=0.5)
        levels = np.clip(levels, 0.0, 1.0)

        return levels

    @property
    def coverage(self) -> np.ndarray:
        """Get coverage information."""
        return self._sample.get_coverage()

    @property
    def sample_type(self) -> str:
        """Get sample type identifier."""
        return self._sample.sample_type

    @property
    def is_centroid(self) -> bool:
        """Check if this is a centroid sample."""
        return self._sample.is_centroid

    def get_beta_parameters(self) -> Tuple[np.ndarray, np.ndarray]:
        """Get beta distribution parameters (for centroids)."""
        if not self.is_centroid:
            raise ValueError("Beta parameters only available for centroid samples")

        return self._sample.get_beta_parameters()


class DataLoader:
    """
    Data loader for methylation samples.

    Handles loading samples from various sources and formats.
    """

    @staticmethod
    def load_sample(h5_path: Path) -> MethylationSample:
        """
        Load a single methylation sample from file.

        Args:
            h5_path: Path to the sample file

        Returns:
            MethylationSample instance
        """
        if h5_path.suffix.lower() == '.h5':
            return H5MethylationSample(h5_path)
        else:
            raise ValueError(f"Unsupported file format: {h5_path.suffix}")

    @staticmethod
    def load_samples_from_directory(h5_dir: Path,
                                 chrom: str = None,
                                 context: str = None) -> List[Tuple[str, MethylationSample]]:
        """
        Load all methylation samples from a directory.

        Args:
            h5_dir: Directory containing sample files
            chrom: Optional chromosome filter
            context: Optional context filter

        Returns:
            List of (sample_name, sample) tuples
        """
        samples = []
        all_h5_files = list(h5_dir.rglob("*.h5"))

        if not all_h5_files:
            raise FileNotFoundError(f"No .h5 files found in {h5_dir} or its subdirectories")

        # Filter by chromosome and context if specified
        if chrom and context:
            h5_files = DataLoader._filter_h5_files_by_chrom_context(all_h5_files, chrom, context)
            print(f"Found {len(all_h5_files)} total .h5 files, {len(h5_files)} match {chrom}-{context}")
        else:
            h5_files = all_h5_files
            print(f"Found {len(h5_files)} .h5 files")

        if not h5_files:
            filter_msg = f" matching {chrom}-{context}" if chrom and context else ""
            raise FileNotFoundError(f"No .h5 files{filter_msg} found in {h5_dir} or its subdirectories")

        for h5_file in sorted(h5_files):
            try:
                sample = DataLoader.load_sample(h5_file)
                sample_name = h5_file.parent.name  # Use parent directory name as sample identifier

                # Collect statistical information for enhanced analysis
                coverage = sample.coverage
                avg_coverage = np.mean(coverage) if len(coverage) > 0 else 0

                samples.append((sample_name, sample))

                # Provide more informative loading message
                print(f"    ✅ Loaded {sample_name} ({sample.sample_type}, avg coverage: {avg_coverage:.1f})")

            except Exception as e:
                sample_name = h5_file.parent.name
                print(f"    ❌ Failed to load {sample_name}: {e}")

        return samples

    @staticmethod
    def _filter_h5_files_by_chrom_context(h5_files: List[Path], chrom: str, context: str) -> List[Path]:
        """
        Filter .h5 files to only include those matching the specified chromosome and context.
        Expects files to be named {prefix}-{chrom}-{context}.h5 (exact chromosome match).
        """
        expected_pattern = f"{chrom}-{context}.h5"
        filtered_files = []

        for h5_file in h5_files:
            # Check if filename exactly matches the pattern
            # This prevents "11-CG.h5" from matching when chrom="1"
            if h5_file.name == expected_pattern:
                filtered_files.append(h5_file)

        return filtered_files

    @staticmethod
    def extract_sample_features(sample: MethylationSample,
                              dmp_positions: np.ndarray) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        """
        Extract DMP features from a methylation sample.

        Args:
            sample: MethylationSample instance
            dmp_positions: Array of DMP positions used by the classifier

        Returns:
            Tuple of (feature_vector, availability_mask, stats_info)
        """
        pos_to_methylation = dict(zip(sample.positions, sample.methylation_levels))

        feature_vector = []
        availability_mask = []
        missing_positions = 0

        for dmp_pos in dmp_positions:
            if dmp_pos in pos_to_methylation:
                methylation = pos_to_methylation[dmp_pos]
                methylation = np.clip(methylation, 0.0, 1.0)
                feature_vector.append(methylation)
                availability_mask.append(True)
            else:
                # Position not found in sample - use 0.5 (neutral) but mark as unavailable
                feature_vector.append(0.5)
                availability_mask.append(False)
                missing_positions += 1

        # Collect statistical information
        coverage = sample.coverage
        avg_coverage = np.mean(coverage) if len(coverage) > 0 else 0
        stats_info = {
            'avg_coverage': avg_coverage,
            'total_positions': len(sample.positions),
            'sample_type': sample.sample_type,
            'missing_positions': missing_positions,
            'dmp_coverage_pct': (len(dmp_positions) - missing_positions) / len(dmp_positions) * 100
        }

        # Add statistical properties if available (for centroids)
        if sample.is_centroid:
            try:
                alpha, beta = sample.get_beta_parameters()
                stats_info.update({
                    'avg_alpha': np.mean(alpha),
                    'avg_beta': np.mean(beta),
                    'avg_tau': np.mean(sample.tau),
                    'avg_variance': np.mean(sample.variance)
                })
            except Exception as e:
                # If statistical properties can't be computed, continue without them
                pass

        return np.array(feature_vector), np.array(availability_mask), stats_info
