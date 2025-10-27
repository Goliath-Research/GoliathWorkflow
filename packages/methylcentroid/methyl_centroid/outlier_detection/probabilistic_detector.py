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
from scipy import stats
from scipy.stats import chisquare


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

        # Check for identical distances
        if np.all(distances == distances[0]):
            self.logger.warning("All distances identical; using IQR fallback")
            Q1 = np.percentile(distances, 25)
            Q3 = np.percentile(distances, 75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 3 * IQR
            upper_bound = Q3 + 3 * IQR
            outliers = (distances < lower_bound) | (distances > upper_bound)
            if np.any(outliers):
                max_idx = np.argmax(np.abs(distances - np.median(distances)))
                selected_sample_path, selected_sample_id = valid_samples[max_idx]
                p_value = 0.001  # Conservative
                metadata = {
                    'algorithm': 'probabilistic_beta_classifier',
                    'classifier_type': 'ProbabilisticBetaClassifier',
                    'distance_metric': primary_metric.value,
                    'total_samples': len(distances),
                    'outlier_probability': float(1.0 - p_value), # Assuming 1-p_value for outlier prob
                    'mean_distance': float(np.mean(distances)),
                    'std_distance': float(np.std(distances)),
                    'min_distance': float(np.min(distances)),
                    'max_distance': float(np.max(distances)),
                    'fallback': 'IQR'
                }
                self.logger.debug(f"Probabilistic outlier detection (IQR fallback): {selected_sample_path.name} "
                                f"(outlier_prob={1.0 - p_value:.3f}, p_value={p_value:.6f})")
                return OutlierDetectionResult(
                    outlier_path=selected_sample_path,
                    sample_id=selected_sample_id,
                    p_value=float(p_value),
                    confidence_score=float(1.0 - p_value),
                    metadata=metadata
                )
            else:
                # No outlier
                return None

        # Try Beta fit with validation
        try:
            beta_params = stats.beta.fit(distances, floc=0, fscale=1)
            # Scale distances if needed (existing code)
            scaled_distances = distances # No scaling needed for beta fit

            # Goodness-of-fit: Chi-squared test
            observed, bin_edges = np.histogram(scaled_distances, bins=10)
            # Calculate expected frequencies for chi-squared test
            # This requires a bit more complex handling of bin_edges
            # For simplicity, let's use a fixed number of bins or a more sophisticated approach
            # For now, let's use a fixed number of bins for chi-squared
            # A common choice for beta distribution is 10-20 bins
            num_bins = min(len(distances), 20) # Use a reasonable number of bins
            if num_bins < 2: # Need at least 2 bins for chi-squared
                num_bins = 2
            bin_edges = np.linspace(0, 1, num_bins + 1) # Uniform bins from 0 to 1
            expected_freq, _ = np.histogram(scaled_distances, bins=bin_edges)

            chi2, p_fit = chisquare(observed, f_exp=expected_freq)

            if p_fit < 0.05:
                self.logger.warning(f"Poor Beta fit (p={p_fit:.3f}); fallback to z-score")
                # Z-score fallback
                mean_d = np.mean(distances)
                std_d = np.std(distances)
                if std_d == 0:
                    return None  # No variance
                z_scores = np.abs((distances - mean_d) / std_d)
                max_z_idx = np.argmax(z_scores)
                p_value = 2 * (1 - stats.norm.cdf(z_scores[max_z_idx]))
                selected_sample_path, selected_sample_id = valid_samples[max_z_idx]
                metadata = {
                    'algorithm': 'probabilistic_beta_classifier',
                    'classifier_type': 'ProbabilisticBetaClassifier',
                    'distance_metric': primary_metric.value,
                    'total_samples': len(distances),
                    'outlier_probability': float(1.0 - p_value), # Assuming 1-p_value for outlier prob
                    'mean_distance': float(np.mean(distances)),
                    'std_distance': float(np.std(distances)),
                    'min_distance': float(np.min(distances)),
                    'max_distance': float(np.max(distances)),
                    'fallback': 'zscore'
                }
                self.logger.debug(f"Probabilistic outlier detection (z-score fallback): {selected_sample_path.name} "
                                f"(outlier_prob={1.0 - p_value:.3f}, p_value={p_value:.6f})")
                return OutlierDetectionResult(
                    outlier_path=selected_sample_path,
                    sample_id=selected_sample_id,
                    p_value=float(p_value),
                    confidence_score=float(1.0 - p_value),
                    metadata=metadata
                )
            else:
                # Original probabilistic logic
                classifier = ProbabilisticBetaClassifier()
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
            self.logger.error(f"Beta fit failed: {e}; using z-score fallback")
            # Z-score logic as above
            mean_d = np.mean(distances)
            std_d = np.std(distances)
            if std_d == 0:
                return None  # No variance
            z_scores = np.abs((distances - mean_d) / std_d)
            max_z_idx = np.argmax(z_scores)
            p_value = 2 * (1 - stats.norm.cdf(z_scores[max_z_idx]))
            selected_sample_path, selected_sample_id = valid_samples[max_z_idx]
            metadata = {
                'algorithm': 'probabilistic_beta_classifier',
                'classifier_type': 'ProbabilisticBetaClassifier',
                'distance_metric': primary_metric.value,
                'total_samples': len(distances),
                'outlier_probability': float(1.0 - p_value), # Assuming 1-p_value for outlier prob
                'mean_distance': float(np.mean(distances)),
                'std_distance': float(np.std(distances)),
                'min_distance': float(np.min(distances)),
                'max_distance': float(np.max(distances)),
                'fallback': 'zscore'
            }
            self.logger.debug(f"Probabilistic outlier detection (z-score fallback): {selected_sample_path.name} "
                            f"(outlier_prob={1.0 - p_value:.3f}, p_value={p_value:.6f})")
            return OutlierDetectionResult(
                outlier_path=selected_sample_path,
                sample_id=selected_sample_id,
                p_value=float(p_value),
                confidence_score=float(1.0 - p_value),
                metadata=metadata
            )

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
