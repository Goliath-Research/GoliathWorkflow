"""
Configuration management for MethylCentroid.

This module handles configuration parsing, validation, and management
following SOLID principles with clear separation of concerns.
"""

from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
import json
from enum import Enum


class DistanceMetric(str, Enum):
    """Enumeration of available distance metrics for outlier detection."""
    JEFFREYS = "jeffreys"
    JENSEN_SHANNON = "jensen_shannon"
    WEIGHTED_JENSEN_SHANNON = "weighted_jensen_shannon"
    HELLINGER = "hellinger"
    WASSERSTEIN = "wasserstein"

    def to_factory_name(self) -> str:
        """Convert DistanceMetric enum to MethylUtils factory metric name."""
        mapping = {
            DistanceMetric.JEFFREYS: "jeffreys",
            DistanceMetric.JENSEN_SHANNON: "jensen_shannon",
            DistanceMetric.WEIGHTED_JENSEN_SHANNON: "weighted_jensen_shannon",
            DistanceMetric.HELLINGER: "hellinger",
            DistanceMetric.WASSERSTEIN: "wasserstein"
        }
        return mapping.get(self, "jensen_shannon")


class MethylCentroidConfig(BaseModel):
    """
    Pydantic configuration model for MethylCentroid parameters.

    Workflows:
    - Initial centroid creation: provide add_samples, output_dir for saving (samples=[], outliers=[])
    - After outlier removal: samples contains remaining samples, outliers contains removed samples
    - Centroid updates: provide samples (current centroid samples), add_samples/remove_samples, outliers
    - When adding new samples, previous outliers are automatically re-included for fair centroid building
    """

    # Metadata fields (saved to H5 file)
    laboratory: str = Field(..., description="Laboratory or institution name")
    disease: str = Field(..., description="Disease or condition being studied")
    group: str = Field(..., description="Sample group identifier (e.g., 'cancer', 'control')")
    batch: str = Field(..., description="Batch identifier for sample processing")
    
    # Core parameters
    chrom: str = Field(..., description="Chromosome identifier (e.g., '1', 'X')")
    ctx: str = Field(..., description="Context type (e.g., 'CG', 'CHG', 'CHH')")
    output_dir: str = Field(..., description="Directory to save centroid files")
    samples: List[str] = Field(
        default=[],
        description="List of sample paths currently in the centroid (used for updates)"
    )
    add_samples: List[str] = Field(
        default=[],
        description="Optional list of new sample paths to add incrementally"
    )
    remove_samples: List[str] = Field(
        default=[],
        description="Optional list of sample paths to remove"
    )
    outliers: List[str] = Field(
        default=[],
        description="List of sample paths that were previously identified as outliers and removed"
    )
    min_coverage: int = Field(
        default=4,
        ge=1,
        description="Minimum sum of mC and uC for a position"
    )
    max_iterations: int = Field(
        default=10,
        ge=1,
        description="Maximum outlier removal iterations"
    )
    max_iterations_percentage: float = Field(
        default=0.1,
        gt=0.0,
        le=1.0,
        description="Percentage of samples to use as maximum outlier removal iterations (overrides max_iterations if > 0)"
    )
    α: float = Field(
        default=0.05,
        gt=0.0,
        le=1.0,
        description="Significance level for outlier detection",
    )
    min_samples: int = Field(
        default=3,
        ge=1,
        description="Minimum samples required for outlier removal"
    )
    distance_metrics: Optional[List[DistanceMetric]] = Field(
        default=None,
        description="List of distance metrics to use for outlier detection (None disables outlier detection)"
    )
    min_metrics_agree: int = Field(
        default=0,
        ge=0,
        description="Minimum number of distance metrics that must agree for a sample to be considered an outlier. Set to 0 to use General Simes formula."
    )
    verbose: bool = Field(
        default=True,
        description="Enable verbose output (CSV files and charts during outlier removal)"
    )

    @field_validator('ctx')
    @classmethod
    def validate_context(cls, v):
        """Validate context is one of CG, CHG, CHH."""
        if v not in ['CG', 'CHG', 'CHH']:
            raise ValueError(f"Context must be one of CG, CHG, CHH, got {v}")
        return v

    @field_validator('chrom')
    @classmethod
    def validate_chromosome(cls, v):
        """Validate chromosome identifier."""
        if not v or not isinstance(v, str):
            raise ValueError("Chromosome must be a non-empty string")
        return v

    def get_metadata(self) -> Dict[str, Any]:
        """
        Extract metadata fields to be saved with the centroid H5 file.
        
        Note: This method provides initial metadata. The actual samples_used
        and outliers_removed will be determined during centroid creation
        based on which samples are active after outlier removal.
        
        Returns:
            Dictionary containing metadata fields
        """
        from datetime import datetime
        return {
            "laboratory": self.laboratory,
            "disease": self.disease,
            "group": self.group,
            "batch": self.batch,
            "chromosome": self.chrom,
            "context": self.ctx,
            "samples": self.samples if self.samples else self.add_samples,  # Initial samples
            "samples_used": [],  # Will be populated during save_centroid
            "outliers_removed": self.outliers,
            "creation_date": datetime.now().isoformat(),
            "min_coverage": self.min_coverage,
            "alpha": self.α,
            "distance_metrics": [str(metric.value) for metric in self.distance_metrics] if self.distance_metrics else []
        }

    def to_file(self, file_path: Path) -> None:
        """Save configuration to JSON file."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w') as f:
            json.dump(self.model_dump(), f, indent=2)

    @classmethod
    def from_file(cls, file_path: Path) -> 'MethylCentroidConfig':
        """Load configuration from JSON file."""
        with open(file_path, 'r') as f:
            data = json.load(f)
        return cls.model_validate(data)


class OutlierIterationInfo(BaseModel):
    """Pydantic model for outlier removal iteration information."""
    iteration: int = Field(..., description="Iteration number")
    p_value: float = Field(..., description="P-value of the removed outlier")
    outlier_path: str = Field(..., description="Path to the removed outlier sample")


class OutlierRemovalResults(BaseModel):
    """Pydantic model for outlier removal results."""
    iterations: List[OutlierIterationInfo] = Field(
        default_factory=list,
        description="List of iteration information"
    )
    final_centroid_path: str = Field(..., description="Path to the final centroid file")
    total_samples_removed: int = Field(
        ...,
        description="Total number of samples removed"
    )


class ProcessingConfig(BaseModel):
    """Configuration for processing parameters that may change dynamically."""

    # Memory management
    enable_caching: bool = Field(default=True, description="Enable sample caching")
    memory_limit_gb: Optional[float] = Field(default=None, description="Memory limit for operations")

    # Performance tuning
    max_workers: Optional[int] = Field(default=None, description="Maximum parallel workers")
    chunk_size_positions: Optional[int] = Field(default=None, description="Chunk size for processing")

    # GPU settings
    use_gpu: bool = Field(default=True, description="Enable GPU acceleration")
    gpu_memory_fraction: float = Field(default=0.8, description="GPU memory fraction to use")

    # Debugging and output
    enable_profiling: bool = Field(default=True, description="Enable performance profiling")
    save_intermediate: bool = Field(default=False, description="Save intermediate results")
    verbose_logging: bool = Field(default=False, description="Enable verbose logging")

    # Validation
    enable_validation: bool = Field(default=True, description="Enable centroid validation")
    enable_visualization: bool = Field(default=True, description="Enable result visualization")


class BatchProcessingConfig(BaseModel):
    """Configuration for batch processing multiple chromosome/context combinations."""

    chromosomes: List[str] = Field(default_factory=list, description="Chromosomes to process")
    contexts: List[str] = Field(default_factory=lambda: ['CG', 'CHG', 'CHH'], description="Contexts to process")
    base_config: MethylCentroidConfig = Field(..., description="Base configuration template")

    # Batch-specific settings
    parallel_combinations: int = Field(default=1, description="Number of combinations to process in parallel")
    continue_on_error: bool = Field(default=True, description="Continue processing if one combination fails")
    save_batch_summary: bool = Field(default=True, description="Save batch processing summary")

    @classmethod
    def from_file(cls, file_path: Path) -> 'BatchProcessingConfig':
        """Load batch configuration from JSON file."""
        with open(file_path, 'r') as f:
            data = json.load(f)
        return cls.model_validate(data)
