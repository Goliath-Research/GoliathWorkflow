"""
MethylTrainer - Train Bayesian classifiers from methylation centroids

This package provides command-line tools for training ProbabilisticBetaClassifier
models from pairs of methylation centroids.
"""

__version__ = "0.1.0"
__all__ = ["MethylTrainer", "TrainingConfig", "train_from_centroids"]

from .core.trainer_class import MethylTrainer
from .models.config import TrainingConfig
from .core.trainer import train_from_centroids

