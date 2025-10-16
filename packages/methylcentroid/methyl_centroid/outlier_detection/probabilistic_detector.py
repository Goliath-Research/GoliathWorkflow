"""
Probabilistic Outlier Detector using Beta distributions.

This module implements outlier detection using probabilistic modeling
with the ProbabilisticBetaClassifier from MethylUtils.
"""

from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from .base_detector import BaseOutlierDetector, OutlierDetectionResult, DistanceCalculator
from ..config import DistanceMetric
from methyl_utils import ProbabilisticBetaClassifier


class ProbabilisticOutlierDetector(BaseOutlierDetector):
    """
    Outlier detector using probabilistic Beta distribution modeling.

    This detector uses advanced statistical modeling to identify outliers
    when there are sufficient samples for reliable inference (≥20 samples).
    """

    def __init__(self, distance_metrics: List[DistanceMetric], config: Dict[str, Any]):
        """
        Initialize the probabilistic outlier detector.

        Args:
            distance_metrics: List of distance metrics to use
            config: Configuration parameters
        """
        super().__init__(distance_metrics, config)
        self.distance_calculator = DistanceCalculator(distance_metrics)
        self.min_samples_for_classifier = config.get('min_samples_for_classifier', 20)

    def detect_outlier(self,
                      active_sample_paths: List[Path],
                      active_sample_indices: List[Tuple[bool, int]]) -> OutlierDetectionResult:
        """
        Detect outliers using probabilistic Beta distribution modeling.

        Args:
            active_sample_paths: Paths to active samples
            active_sample_indices: Indices of active samples

        Returns:
            OutlierDetectionResult with detection details
        """
        self._validate_inputs(active_sample_paths, active_sample_indices)

        if len(active_sample_paths) < self.min_samples_for_classifier:
            raise ValueError(f"Insufficient samples for probabilistic detection: "
                           f"{len(active_sample_paths)} < {self.min_samples_for_classifier}")

        self.logger.debug("Computing distance matrix for probabilistic outlier detection...")

        # Calculate distances for all samples using the first configured metric
        primary_metric = self.distance_metrics[0]
        distances = self._calculate_distances_parallel(active_sample_paths, primary_metric)

        if len(distances) < 5:  # Need minimum valid samples
            raise ValueError(f"Insufficient valid distance calculations: {len(distances)}")

        distances = np.array(distances)
        valid_samples = list(zip(active_sample_paths, active_sample_indices))

        # Initialize and fit the probabilistic classifier
        try:
            classifier = ProbabilisticBetaClassifier()

            # Fit on the distance distribution
            classifier.fit_from_distances(distances)

            # Get outlier probabilities for all samples
            outlier_probs = classifier.predict_outlier_probabilities(distances)

            # Find the sample with highest outlier probability
            max_prob_idx = np.argmax(outlier_probs)
            max_prob = outlier_probs[max_prob_idx]

            # Convert probability to p-value (lower p-value = more significant outlier)
            p_value = 1.0 - max_prob

            selected_sample_path, selected_sample_id = valid_samples[max_prob_idx]

            self.logger.debug(f"Probabilistic outlier detection: {selected_sample_path.name} "
                            f"(outlier_prob={max_prob:.3f}, p_value={p_value:.6f})")

            # Create metadata
            metadata = {
                'algorithm': 'probabilistic_beta_classifier',
                'classifier_type': 'ProbabilisticBetaClassifier',
                'distance_metric': primary_metric.value,
                'total_samples': len(distances),
                'outlier_probability': float(max_prob),
                'mean_distance': float(np.mean(distances)),
                'std_distance': float(np.std(distances)),
                'min_distance': float(np.min(distances)),
                'max_distance': float(np.max(distances))
            }

            return OutlierDetectionResult(
                outlier_path=selected_sample_path,
                sample_id=selected_sample_id,
                p_value=float(p_value),
                confidence_score=float(max_prob),
                metadata=metadata
            )

        except Exception as e:
            self.logger.error(f"ProbabilisticBetaClassifier failed: {e}")
            raise

    def is_suitable(self, num_samples: int) -> bool:
        """
        Check if probabilistic detection is suitable for the sample size.

        Args:
            num_samples: Number of samples to analyze

        Returns:
            True if probabilistic detection is appropriate
        """
        return num_samples >= self.min_samples_for_classifier

    def get_algorithm_name(self) -> str:
        """Get the name of the outlier detection algorithm."""
        return "ProbabilisticBetaClassifier"

    def _calculate_distances_parallel(self,
                                   sample_paths: List[Path],
                                   distance_metric: DistanceMetric) -> List[float]:
        """
        Calculate distances for all samples in parallel.

        Args:
            sample_paths: List of sample file paths
            distance_metric: Distance metric to use

        Returns:
            List of distance values
        """
        distances = []

        # For probabilistic detection, we use single-threaded processing
        # to ensure consistent results and avoid race conditions
        for sample_path in tqdm(sample_paths, desc=f"Calculating {distance_metric.value} distances", leave=False):
            distance = self.distance_calculator.calculate_sample_distance(sample_path, distance_metric)
            if distance is not None and np.isfinite(distance):
                distances.append(distance)
            else:
                # Use a default distance for failed calculations
                distances.append(0.5)

        return distances
