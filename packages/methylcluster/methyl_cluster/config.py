"""
Configuration management for MethylCluster.

This module handles configuration parsing and validation for HDBSCAN
clustering of methylation samples using Pydantic models.
"""

from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
import json
from enum import Enum


class ClusterMetric(str, Enum):
    """Enumeration of available distance metrics for clustering."""
    JENSEN_SHANNON = "jensen_shannon"
    HELLINGER = "hellinger"
    
    def to_factory_name(self) -> str:
        """Convert ClusterMetric enum to MethylUtils factory metric name."""
        return self.value


class MethylClusterConfig(BaseModel):
    """
    Pydantic configuration model for MethylCluster parameters.
    
    This configuration defines all parameters for clustering methylation
    samples using HDBSCAN with precomputed distance matrices.
    """
    
    # Sample specification
    samples: List[str] = Field(
        ...,
        description="List of sample directory paths"
    )
    chrom: str = Field(
        ...,
        description="Chromosome identifier (e.g., '1', 'X')"
    )
    ctx: str = Field(
        ...,
        description="Context type (CG, CHG, or CHH)"
    )
    
    # Clustering parameters
    metric: ClusterMetric = Field(
        default=ClusterMetric.JENSEN_SHANNON,
        description="Distance metric for clustering"
    )
    min_cluster_size: int = Field(
        default=5,
        ge=2,
        description="Minimum number of samples per cluster"
    )
    min_samples: Optional[int] = Field(
        default=None,
        description="HDBSCAN min_samples parameter (defaults to min_cluster_size)"
    )
    cluster_selection_epsilon: float = Field(
        default=0.0,
        ge=0.0,
        description="Distance threshold for cluster merging"
    )
    cluster_selection_method: str = Field(
        default="eom",
        description="Cluster selection method (eom or leaf)"
    )
    
    # Output configuration
    output_dir: str = Field(
        ...,
        description="Output directory for results and visualizations"
    )
    cache_distance_matrix: bool = Field(
        default=True,
        description="Cache computed distance matrix to disk"
    )
    
    # GPU settings
    use_gpu: bool = Field(
        default=True,
        description="Use GPU acceleration for distance computation"
    )
    
    @field_validator('output_dir')
    @classmethod
    def normalize_output_dir(cls, v):
        """Normalize output directory path."""
        from pathlib import Path
        return str(Path(v).resolve())
    
    @field_validator('ctx')
    @classmethod
    def validate_context(cls, v):
        """Validate context is one of the allowed types."""
        valid_contexts = ['CG', 'CHG', 'CHH']
        if v not in valid_contexts:
            raise ValueError(f"Context must be one of {valid_contexts}, got '{v}'")
        return v
    
    @field_validator('cluster_selection_method')
    @classmethod
    def validate_selection_method(cls, v):
        """Validate cluster selection method."""
        valid_methods = ['eom', 'leaf']
        if v not in valid_methods:
            raise ValueError(f"Cluster selection method must be one of {valid_methods}, got '{v}'")
        return v
    
    @field_validator('samples')
    @classmethod
    def validate_samples(cls, v):
        """Validate that at least 2 samples are provided."""
        if len(v) < 2:
            raise ValueError("At least 2 samples are required for clustering")
        return v
    
    def to_file(self, file_path: Path) -> None:
        """Save configuration to JSON file."""
        file_path = Path(file_path)
        with open(file_path, 'w') as f:
            json.dump(self.model_dump(), f, indent=2)
    
    @classmethod
    def from_file(cls, file_path: Path) -> 'MethylClusterConfig':
        """Load configuration from JSON file."""
        file_path = Path(file_path)
        with open(file_path, 'r') as f:
            data = json.load(f)
        return cls(**data)


__all__ = ['MethylClusterConfig', 'ClusterMetric']

