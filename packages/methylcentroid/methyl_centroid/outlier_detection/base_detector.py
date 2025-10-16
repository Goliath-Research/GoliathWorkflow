"""
Base classes and interfaces for outlier detection.

This module defines the abstract base classes and interfaces for outlier detection
algorithms, following SOLID principles with clear separation of concerns.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path
import numpy as np

from ..config import DistanceMetric


class OutlierDetectionResult:
    """Container for outlier detection results."""

    def __init__(self,
                 outlier_path: Optional[Path],
                 sample_id: Optional[Tuple[bool, int]],
                 p_value: float,
                 confidence_score: Optional[float] = None,
                 metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize outlier detection result.

        Args:
            outlier_path: Path to the detected outlier sample
            sample_id: Identifier for the outlier sample (is_new, index)
            p_value: Statistical significance of the outlier detection
            confidence_score: Optional confidence score (0-1)
            metadata: Additional metadata about the detection
        """
        self.outlier_path = outlier_path
        self.sample_id = sample_id
        self.p_value = p_value
        self.confidence_score = confidence_score
        self.metadata = metadata or {}

    def is_significant(self, alpha: float = 0.05) -> bool:
        """Check if the outlier is statistically significant."""
        return self.p_value < alpha


class BaseOutlierDetector(ABC):
    """
    Abstract base class for outlier detection algorithms.

    This class defines the interface that all outlier detection implementations
    must follow, enabling polymorphism and easy extension.
    """

    def __init__(self, distance_metrics: List[DistanceMetric], config: Dict[str, Any]):
        """
        Initialize the outlier detector.

        Args:
            distance_metrics: List of distance metrics to use
            config: Configuration parameters for the detector
        """
        self.distance_metrics = distance_metrics
        self.config = config
        self.logger = self._setup_logger()

    @abstractmethod
    def detect_outlier(self,
                      active_sample_paths: List[Path],
                      active_sample_indices: List[Tuple[bool, int]]) -> OutlierDetectionResult:
        """
        Detect the most extreme outlier from a set of samples.

        Args:
            active_sample_paths: Paths to active samples
            active_sample_indices: Indices of active samples

        Returns:
            OutlierDetectionResult with detection details
        """
        pass

    @abstractmethod
    def is_suitable(self, num_samples: int) -> bool:
        """
        Check if this detector is suitable for the given number of samples.

        Args:
            num_samples: Number of samples to analyze

        Returns:
            True if this detector is appropriate for the sample size
        """
        pass

    @abstractmethod
    def get_algorithm_name(self) -> str:
        """Get the name of the outlier detection algorithm."""
        pass

    def _setup_logger(self):
        """Setup logger for the detector."""
        import logging
        return logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def _validate_inputs(self, sample_paths: List[Path], sample_indices: List[Tuple[bool, int]]):
        """Validate input parameters."""
        if not sample_paths:
            raise ValueError("No sample paths provided")

        if len(sample_paths) != len(sample_indices):
            raise ValueError("Sample paths and indices must have the same length")

        if len(sample_paths) < self.config.get('min_samples', 3):
            raise ValueError(f"Insufficient samples: {len(sample_paths)} < {self.config.get('min_samples', 3)}")


class DistanceCalculator:
    """
    Utility class for calculating distances between samples.

    This class handles the common distance calculation logic used by
    different outlier detection algorithms.
    """

    def __init__(self, distance_metrics: List[DistanceMetric]):
        """
        Initialize the distance calculator.

        Args:
            distance_metrics: List of distance metrics to use
        """
        self.distance_metrics = distance_metrics

    def calculate_sample_distance(self, sample_path: Path, distance_metric: DistanceMetric) -> Optional[float]:
        """
        Calculate distance for a single sample using the specified metric.

        Args:
            sample_path: Path to the sample file
            distance_metric: Distance metric to use

        Returns:
            Distance value or None if calculation fails
        """
        try:
            from methyl_utils import MethylSample

            # Load sample
            sample_obj = MethylSample.load_from_h5(sample_path)

            # Get sample data aligned to centroid
            # This would typically be done by the position aligner
            # For now, return a placeholder distance
            return 0.5  # Placeholder

        except Exception as e:
            print(f"Error calculating distance for {sample_path}: {e}")
            return None

    def calculate_distances_for_metric(self,
                                     sample_paths: List[Path],
                                     distance_metric: DistanceMetric) -> np.ndarray:
        """
        Calculate distances for all samples using a specific metric.

        Args:
            sample_paths: List of sample file paths
            distance_metric: Distance metric to use

        Returns:
            Array of distance values
        """
        distances = []

        for sample_path in sample_paths:
            distance = self.calculate_sample_distance(sample_path, distance_metric)
            if distance is not None:
                distances.append(distance)
            else:
                distances.append(0.0)  # Default distance for failed calculations

        return np.array(distances)
