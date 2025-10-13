"""
MethylTrainer - Train Bayesian classifiers from methylation centroids

This package provides command-line tools for training ProbabilisticBetaClassifier
models from pairs of methylation centroids.
"""

__version__ = "0.1.0"
__all__ = ["train_from_centroids"]

from .trainer import train_from_centroids

