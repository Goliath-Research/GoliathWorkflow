"""
Outlier Detection Algorithms.

This package contains various outlier detection algorithms following
the Strategy pattern for clean, extensible implementations.
"""

from .base_detector import BaseOutlierDetector, OutlierDetectionResult
from .probabilistic_detector import ProbabilisticOutlierDetector
from .detector_factory import OutlierDetectorFactory

__all__ = [
    "BaseOutlierDetector",
    "OutlierDetectionResult",
    "ProbabilisticOutlierDetector",
    "OutlierDetectorFactory"
]
