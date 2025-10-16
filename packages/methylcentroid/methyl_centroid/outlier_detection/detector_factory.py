"""
Factory pattern for creating outlier detection algorithms.

This module implements the Factory pattern to create appropriate outlier detectors
based on sample size and configuration, following SOLID principles.
"""

from typing import List, Dict, Any, Optional
from .base_detector import BaseOutlierDetector
from .probabilistic_detector import ProbabilisticOutlierDetector
from .single_metric_detector import SingleMetricOutlierDetector
from .multi_metric_detector import MultiMetricOutlierDetector
from ..config import DistanceMetric


class OutlierDetectorFactory:
    """
    Factory for creating outlier detection algorithms.

    This factory selects the most appropriate outlier detection algorithm
    based on sample size, configuration, and available methods.
    """

    # Default configuration for different detector types
    DEFAULT_CONFIGS = {
        'probabilistic': {
            'min_samples_for_classifier': 20,
            'min_samples': 10
        },
        'multi_metric': {
            'min_metrics_agree': 1,
            'min_samples': 3
        },
        'single_metric': {
            'min_samples': 3
        }
    }

    @staticmethod
    def create_detector(distance_metrics: List[DistanceMetric],
                       num_samples: int,
                       config: Optional[Dict[str, Any]] = None) -> BaseOutlierDetector:
        """
        Create the most appropriate outlier detector for the given parameters.

        Args:
            distance_metrics: List of distance metrics to use
            num_samples: Number of samples available
            config: Optional configuration overrides

        Returns:
            Configured outlier detector instance

        Raises:
            ValueError: If no suitable detector can be created
        """
        # Merge provided config with defaults
        final_config = OutlierDetectorFactory._merge_configs(config)

        # Determine the best detector based on sample size and metrics
        if num_samples >= final_config.get('min_samples_for_classifier', 20):
            # Use probabilistic detection for large sample sets
            detector_config = {**final_config, **OutlierDetectorFactory.DEFAULT_CONFIGS['probabilistic']}
            return ProbabilisticOutlierDetector(distance_metrics, detector_config)

        elif len(distance_metrics) > 1:
            # Use multi-metric detection for multiple metrics
            detector_config = {**final_config, **OutlierDetectorFactory.DEFAULT_CONFIGS['multi_metric']}
            return MultiMetricOutlierDetector(distance_metrics, detector_config)

        else:
            # Use single metric detection as fallback
            detector_config = {**final_config, **OutlierDetectorFactory.DEFAULT_CONFIGS['single_metric']}
            return SingleMetricOutlierDetector(distance_metrics, detector_config)

    @staticmethod
    def create_specific_detector(detector_type: str,
                               distance_metrics: List[DistanceMetric],
                               config: Optional[Dict[str, Any]] = None) -> BaseOutlierDetector:
        """
        Create a specific type of outlier detector.

        Args:
            detector_type: Type of detector ('probabilistic', 'multi_metric', 'single_metric')
            distance_metrics: List of distance metrics to use
            config: Optional configuration overrides

        Returns:
            Configured outlier detector instance

        Raises:
            ValueError: If detector type is not supported
        """
        # Merge provided config with defaults
        final_config = OutlierDetectorFactory._merge_configs(config)

        if detector_type == 'probabilistic':
            detector_config = {**final_config, **OutlierDetectorFactory.DEFAULT_CONFIGS['probabilistic']}
            return ProbabilisticOutlierDetector(distance_metrics, detector_config)

        elif detector_type == 'multi_metric':
            detector_config = {**final_config, **OutlierDetectorFactory.DEFAULT_CONFIGS['multi_metric']}
            return MultiMetricOutlierDetector(distance_metrics, detector_config)

        elif detector_type == 'single_metric':
            detector_config = {**final_config, **OutlierDetectorFactory.DEFAULT_CONFIGS['single_metric']}
            return SingleMetricOutlierDetector(distance_metrics, detector_config)

        else:
            raise ValueError(f"Unsupported detector type: {detector_type}")

    @staticmethod
    def get_available_detectors() -> List[str]:
        """Get list of available detector types."""
        return ['probabilistic', 'multi_metric', 'single_metric']

    @staticmethod
    def get_detector_info(detector_type: str) -> Dict[str, Any]:
        """
        Get information about a specific detector type.

        Args:
            detector_type: Type of detector

        Returns:
            Dictionary with detector information
        """
        info_map = {
            'probabilistic': {
                'name': 'Probabilistic Beta Classifier',
                'description': 'Uses advanced statistical modeling with Beta distributions',
                'min_samples': 20,
                'best_for': 'Large sample sets (≥20 samples)',
                'strengths': ['Statistical rigor', 'Handles complex distributions', 'High accuracy']
            },
            'multi_metric': {
                'name': 'Multi-Metric Consensus',
                'description': 'Combines multiple distance metrics for robust detection',
                'min_samples': 3,
                'best_for': 'Medium sample sets with multiple metrics',
                'strengths': ['Robust to metric choice', 'Handles different data types']
            },
            'single_metric': {
                'name': 'Single Metric Detection',
                'description': 'Uses statistical modeling with a single distance metric',
                'min_samples': 3,
                'best_for': 'Small to medium sample sets',
                'strengths': ['Simple and fast', 'Good for basic outlier detection']
            }
        }

        return info_map.get(detector_type, {})

    @staticmethod
    def _merge_configs(user_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge user configuration with default settings.

        Args:
            user_config: User-provided configuration

        Returns:
            Merged configuration dictionary
        """
        default_config = {
            'min_samples': 3,
            'min_samples_for_classifier': 20,
            'min_metrics_agree': 1,
            'alpha': 0.05,
            'max_iterations': 10,
            'enable_validation': True,
            'enable_visualization': True
        }

        if user_config:
            default_config.update(user_config)

        return default_config
