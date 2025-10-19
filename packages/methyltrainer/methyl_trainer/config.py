"""
Configuration management for MethylTrainer
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict

from methyl_utils import FilterConfig


@dataclass
class TrainingConfig:
    """Complete configuration for model training."""
    
    # Input files
    centroid1_path: str
    centroid2_path: str
    output_path: str
    
    # Optional identifiers
    centroid1_name: Optional[str] = None
    centroid2_name: Optional[str] = None
    chromosome: Optional[str] = None
    context: Optional[str] = None
    
    # Comparison configuration
    min_coverage: int = 10
    
    # Filter configuration (basic)
    max_q_value: float = 0.05
    min_delta_mean: float = 0.1
    max_overlap: float = 0.6
    min_jeffreys_divergence: Optional[float] = 0.3
    min_auc: Optional[float] = 0.6
    max_dmps: Optional[int] = 1000
    sort_by: str = "jeffreys_divergence"
    
    # Advanced filtering configuration (from MethylDetector)
    alpha: float = 0.05
    min_N_pct: float = 0.1
    max_bc: float = 0.6
    gamma: float = 1.5
    min_effect_size: Optional[float] = None
    biological_filters: bool = True
    
    # Binary search configuration
    target_auc: float = 0.95
    min_selected_dmps: Optional[int] = None
    min_dmps_for_export: int = 1000
    
    # Validation-accuracy optimization (requires real validation samples)
    optimize_for_validation_accuracy: bool = False  # Enable accuracy-based optimization after AUC search
    
    # Differential Evolution optimization parameters
    de_max_iterations: int = 50  # Max iterations for differential evolution
    de_population_size: int = 15  # Population size (default: 15 for 1D problem)
    de_tolerance: float = 0.001  # Stop if improvement < 0.1% accuracy
    
    
    # Validation configuration
    validation_mode: str = "synthetic"  # "synthetic" or "real"
    centroid1_validation_samples: Optional[List[str]] = None
    centroid2_validation_samples: Optional[List[str]] = None
    n_validation_samples: int = 100
    
    # GPU configuration
    use_gpu: bool = True
    random_state: int = 42
    
    # Output options
    verbose: bool = True
    
    def to_filter_config(self) -> FilterConfig:
        """Convert to FilterConfig for BayesianClassifierTrainer."""
        return FilterConfig(
            max_q_value=self.max_q_value,
            min_delta_mean=self.min_delta_mean,
            max_overlap=self.max_overlap,
            min_jeffreys_divergence=self.min_jeffreys_divergence,
            min_auc=self.min_auc,
            max_dmps=self.max_dmps,
            sort_by=self.sort_by
        )
    
    @classmethod
    def from_json(cls, path: Path) -> "TrainingConfig":
        """Load configuration from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)
        return cls(**data)
    
    def to_json(self, path: Path) -> None:
        """Save configuration to JSON file."""
        with open(path, 'w') as f:
            json.dump(asdict(self), f, indent=2)


def load_config_from_file(config_path: Path) -> TrainingConfig:
    """
    Load training configuration from JSON file.
    
    Args:
        config_path: Path to JSON configuration file
    
    Returns:
        TrainingConfig object
    """
    return TrainingConfig.from_json(config_path)


def create_default_config(
    centroid1_path: str,
    centroid2_path: str,
    output_path: str,
    **kwargs
) -> TrainingConfig:
    """
    Create a default training configuration.
    
    Args:
        centroid1_path: Path to first centroid
        centroid2_path: Path to second centroid
        output_path: Path for output model
        **kwargs: Additional configuration options
    
    Returns:
        TrainingConfig object
    """
    return TrainingConfig(
        centroid1_path=centroid1_path,
        centroid2_path=centroid2_path,
        output_path=output_path,
        **kwargs
    )

