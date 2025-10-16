"""
Single Metric Outlier Detector.

This module implements traditional statistical outlier detection
using a single distance metric (placeholder - would contain
the original outlier detection logic from the monolithic file).
"""

from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path
import numpy as np

from .base_detector import BaseOutlierDetector, OutlierDetectionResult, DistanceCalculator
from ..config import DistanceMetric


class SingleMetricOutlierDetector(BaseOutlierDetector):
    """
    Traditional outlier detector using single distance metric.

    This detector uses statistical modeling with a single distance metric
    for outlier detection, suitable for small to medium sample sets.
    """

    def __init__(self, distance_metrics: List[DistanceMetric], config: Dict[str, Any]):
        """
        Initialize the single metric outlier detector.

        Args:
            distance_metrics: List of distance metrics (uses only the first)
            config: Configuration parameters
        """
        super().__init__(distance_metrics, config)
        self.distance_calculator = DistanceCalculator(distance_metrics)

    def detect_outlier(self,
                      active_sample_paths: List[Path],
                      active_sample_indices: List[Tuple[bool, int]]) -> OutlierDetectionResult:
        """
        Detect outliers using single metric statistical analysis.

        Args:
            active_sample_paths: Paths to active samples
            active_sample_indices: Indices of active samples

        Returns:
            OutlierDetectionResult with detection details
        """
        self._validate_inputs(active_sample_paths, active_sample_indices)

        # Calculate distances using the first (and only) metric
        primary_metric = self.distance_metrics[0]
        distances = self._calculate_distances(active_sample_paths, primary_metric)

        if len(distances) == 0:
            raise ValueError("No valid distances calculated")

        # Perform statistical outlier detection
        outlier_result = self._perform_statistical_outlier_detection(
            distances, active_sample_paths, active_sample_indices
        )

        return outlier_result

    def is_suitable(self, num_samples: int) -> bool:
        """
        Check if single metric detection is suitable.

        Args:
            num_samples: Number of samples to analyze

        Returns:
            True - single metric detection is always suitable as fallback
        """
        return num_samples >= self.config.get('min_samples', 3)

    def get_algorithm_name(self) -> str:
        """Get the name of the outlier detection algorithm."""
        return "SingleMetric"

    def _calculate_distances(self, sample_paths: List[Path], metric: DistanceMetric) -> List[float]:
        """
        Calculate distances for all samples.

        Args:
            sample_paths: List of sample file paths
            metric: Distance metric to use

        Returns:
            List of distance values
        """
        distances = []

        for sample_path in sample_paths:
            distance = self.distance_calculator.calculate_sample_distance(sample_path, metric)
            if distance is not None and np.isfinite(distance):
                distances.append(distance)
            else:
                distances.append(0.5)  # Default distance

        return distances

    def _perform_statistical_outlier_detection(self,
                                            distances: List[float],
                                            sample_paths: List[Path],
                                            sample_indices: List[Tuple[bool, int]]) -> OutlierDetectionResult:
        """
        Perform statistical outlier detection.

        Args:
            distances: Distance values for all samples
            sample_paths: Sample file paths
            sample_indices: Sample indices

        Returns:
            OutlierDetectionResult
        """
        distances_array = np.array(distances)

        # Find the sample with maximum distance (most extreme outlier)
        max_distance_idx = np.argmax(distances_array)
        max_distance = distances_array[max_distance_idx]

        # Calculate statistical significance (simplified)
        mean_distance = np.mean(distances_array)
        std_distance = np.std(distances_array)

        if std_distance > 0:
            # Z-score based p-value approximation
            z_score = (max_distance - mean_distance) / std_distance
            # Approximate p-value using normal distribution
            from scipy.stats import norm
            p_value = 1 - norm.cdf(z_score)
        else:
            p_value = 0.0  # All distances identical

        # Create result
        metadata = {
            'algorithm': 'single_metric_statistical',
            'distance_metric': self.distance_metrics[0].value,
            'total_samples': len(distances),
            'mean_distance': float(mean_distance),
            'std_distance': float(std_distance),
            'max_distance': float(max_distance)
        }

        return OutlierDetectionResult(
            outlier_path=sample_paths[max_distance_idx],
            sample_id=sample_indices[max_distance_idx],
            p_value=float(p_value),
            metadata=metadata
        )
