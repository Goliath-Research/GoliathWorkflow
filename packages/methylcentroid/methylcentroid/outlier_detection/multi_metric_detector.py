"""
Multi-Metric Outlier Detector.

This module implements consensus-based outlier detection using
multiple distance metrics (placeholder - would contain the
multi-metric logic from the monolithic file).
"""

from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path
import numpy as np

from .base_detector import BaseOutlierDetector, OutlierDetectionResult, DistanceCalculator
from ..config import DistanceMetric


class MultiMetricOutlierDetector(BaseOutlierDetector):
    """
    Multi-metric consensus outlier detector.

    This detector combines multiple distance metrics for robust outlier detection,
    requiring consensus among metrics for classification.
    """

    def __init__(self, distance_metrics: List[DistanceMetric], config: Dict[str, Any]):
        """
        Initialize the multi-metric outlier detector.

        Args:
            distance_metrics: List of distance metrics to use
            config: Configuration parameters
        """
        super().__init__(distance_metrics, config)
        self.distance_calculator = DistanceCalculator(distance_metrics)
        self.min_metrics_agree = config.get('min_metrics_agree', 1)

    def detect_outlier(self,
                      active_sample_paths: List[Path],
                      active_sample_indices: List[Tuple[bool, int]]) -> OutlierDetectionResult:
        """
        Detect outliers using multi-metric consensus approach.

        Args:
            active_sample_paths: Paths to active samples
            active_sample_indices: Indices of active samples

        Returns:
            OutlierDetectionResult with detection details
        """
        self._validate_inputs(active_sample_paths, active_sample_indices)

        if len(self.distance_metrics) < 2:
            raise ValueError("Multi-metric detection requires at least 2 distance metrics")

        # Calculate distances for all metrics
        all_distances = {}
        all_p_values = {}

        for metric in self.distance_metrics:
            distances = self._calculate_distances(active_sample_paths, metric)
            p_values = self._calculate_p_values(distances)

            all_distances[metric] = distances
            all_p_values[metric] = p_values

        # Find consensus outliers
        consensus_result = self._find_consensus_outlier(
            all_p_values, active_sample_paths, active_sample_indices
        )

        return consensus_result

    def is_suitable(self, num_samples: int) -> bool:
        """
        Check if multi-metric detection is suitable.

        Args:
            num_samples: Number of samples to analyze

        Returns:
            True if multiple metrics are available and sufficient samples
        """
        return (len(self.distance_metrics) > 1 and
                num_samples >= self.config.get('min_samples', 3))

    def get_algorithm_name(self) -> str:
        """Get the name of the outlier detection algorithm."""
        return "MultiMetricConsensus"

    def _calculate_distances(self, sample_paths: List[Path], metric: DistanceMetric) -> List[float]:
        """Calculate distances for all samples using a specific metric."""
        distances = []

        for sample_path in sample_paths:
            distance = self.distance_calculator.calculate_sample_distance(sample_path, metric)
            if distance is not None and np.isfinite(distance):
                distances.append(distance)
            else:
                distances.append(0.5)  # Default distance

        return distances

    def _calculate_p_values(self, distances: List[float]) -> List[float]:
        """Calculate p-values for distance distribution."""
        distances_array = np.array(distances)
        mean_dist = np.mean(distances_array)
        std_dist = np.std(distances_array)

        if std_dist > 0:
            # Z-score based p-values
            from scipy.stats import norm
            z_scores = (distances_array - mean_dist) / std_dist
            p_values = 1 - norm.cdf(z_scores)
        else:
            # All distances identical
            p_values = np.full_like(distances_array, 0.5)

        return p_values.tolist()

    def _find_consensus_outlier(self,
                               all_p_values: Dict[DistanceMetric, List[float]],
                               sample_paths: List[Path],
                               sample_indices: List[Tuple[bool, int]]) -> OutlierDetectionResult:
        """
        Find outlier based on consensus across multiple metrics.

        Args:
            all_p_values: P-values for each metric
            sample_paths: Sample file paths
            sample_indices: Sample indices

        Returns:
            OutlierDetectionResult with consensus result
        """
        num_samples = len(sample_paths)
        consensus_votes = np.zeros(num_samples)

        # Count votes for each sample across metrics
        for metric, p_values in all_p_values.items():
            # Vote for samples that are outliers (p < α)
            alpha = self.config.get('alpha', 0.05)
            votes = np.array(p_values) < alpha
            consensus_votes += votes.astype(int)

        # Find samples that meet the consensus threshold
        qualified_mask = consensus_votes >= self.min_metrics_agree

        if not np.any(qualified_mask):
            # No consensus outliers found
            return OutlierDetectionResult(
                outlier_path=None,
                sample_id=None,
                p_value=1.0,
                metadata={'consensus': False, 'reason': 'no_consensus'}
            )

        # Among qualified outliers, find the one with strongest consensus
        qualified_indices = np.where(qualified_mask)[0]
        best_idx = qualified_indices[np.argmax(consensus_votes[qualified_indices])]

        # Calculate combined p-value (most conservative across metrics)
        combined_p_value = max(p_values[best_idx] for p_values in all_p_values.values())

        metadata = {
            'algorithm': 'multi_metric_consensus',
            'total_metrics': len(self.distance_metrics),
            'min_metrics_agree': self.min_metrics_agree,
            'consensus_votes': int(consensus_votes[best_idx]),
            'metrics': [m.value for m in self.distance_metrics]
        }

        return OutlierDetectionResult(
            outlier_path=sample_paths[best_idx],
            sample_id=sample_indices[best_idx],
            p_value=float(combined_p_value),
            metadata=metadata
        )
