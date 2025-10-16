"""
MethylCentroid - Advanced Methylation Centroid Calculation with Outlier Detection

A modular, high-performance package for calculating methylation centroids from genomic data,
following SOLID principles with clean separation of concerns.

Features:
- Intelligent sample caching with memory management
- Multiple outlier detection algorithms (probabilistic, multi-metric, single-metric)
- Dynamic memory-aware parallel processing
- Chunked processing for large genomic datasets
- Comprehensive performance profiling and monitoring
"""

from .config import MethylCentroidConfig, OutlierRemovalResults
from .core import MethylCentroid
from .core.sample_manager import SampleManager
from .outlier_detection.detector_factory import OutlierDetectorFactory

__version__ = "2.0.0"
__all__ = [
    "MethylCentroid",
    "MethylCentroidConfig",
    "OutlierRemovalResults",
    "SampleManager",
    "OutlierDetectorFactory"
] 