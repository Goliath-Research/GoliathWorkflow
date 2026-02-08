"""
Configuration schema for MethylClassifier CLI
"""

from pathlib import Path
from typing import Optional, Dict, List, Union
from pydantic import BaseModel, Field, field_validator


class ClassificationConfig(BaseModel):
    """Configuration for sample classification."""
    
    # Model path (can be file or directory)
    model_path: Optional[str] = Field(
        default=None,
        description="Path to trained classifier model (.pkl file) or directory containing classifier-{chrom}.pkl files"
    )
    model_dir: Optional[str] = Field(
        default=None,
        description="Path to directory containing classifier-{chrom}.pkl files (alternative to model_path)"
    )
    input_path: Optional[str] = Field(
        default=None,
        description="Path to input .h5 file or directory containing .h5 files (alternative to samples list)"
    )
    samples: Optional[List[str]] = Field(
        default=None,
        description="List of sample directory paths. Each directory should contain {chrom}-CG.h5, {chrom}-CHG.h5, {chrom}-CHH.h5 files. Contexts will be merged. (alternative to input_path)"
    )
    # Centroid validation: run classifier on samples used to build centroids (expect centroid1→class0, centroid2→class1)
    centroid1_dir: Optional[str] = Field(
        default=None,
        description="Path to centroid1 output directory (H5 files). Sample list is read from each file's 'samples_used' metadata (union across files). Use with centroid2_dir."
    )
    centroid2_dir: Optional[str] = Field(
        default=None,
        description="Path to centroid2 output directory (H5 files). Sample list is read from each file's 'samples_used' metadata (union across files). Use with centroid1_dir."
    )
    centroid_sample_root: Optional[str] = Field(
        default=None,
        description="When reading samples_used from centroid H5 metadata, remap each path to <centroid_sample_root>/<basename(path)>. Use when data moved to NAS so metadata still has old paths. Ignored if centroid_path_remap is set."
    )
    centroid_path_remap: Optional[Dict[str, str]] = Field(
        default=None,
        description="Prefix replacement for paths from centroid metadata: {\"old_prefix\": \"new_prefix\", ...}. Longest matching key is replaced so relative paths are preserved. Use when samples live under a different base (e.g. NAS). Overrides centroid_sample_root."
    )
    centroid1_sample_paths: Optional[List[str]] = Field(
        default=None,
        description="Explicit list of sample directories for centroid1 (class 0). Overrides centroid1_dir if set. Use with centroid2_sample_paths."
    )
    centroid2_sample_paths: Optional[List[str]] = Field(
        default=None,
        description="Explicit list of sample directories for centroid2 (class 1). Overrides centroid2_dir if set. Use with centroid1_sample_paths."
    )

    # Optional
    output_path: Optional[str] = Field(
        default=None,
        description="Optional output CSV file for classification results"
    )
    chromosome_matrix_path: Optional[str] = Field(
        default=None,
        description="Optional output CSV file for chromosome probability matrix (samples × chromosomes)"
    )

    debug: bool = Field(
        default=False,
        description="Enable debug output"
    )
    
    no_filter: bool = Field(
        default=False,
        description="Process all .h5 files without chromosome/context filtering"
    )
    
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )

    # New calibration parameters
    temperature: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Temperature for softmax in prediction"
    )
    enable_platt_calibration: bool = Field(
        default=False,
        description="Enable Platt scaling calibration on validation data"
    )
    
    # Multi-chromosome parameters
    trimmed_percentile_low: float = Field(
        default=0.10,
        ge=0.0,
        le=0.5,
        description="Lower percentile for trimmed mean effect_size calculation - removes bottom X% (default: 0.10 = remove bottom 10%)"
    )
    trimmed_percentile_high: float = Field(
        default=0.01,
        ge=0.0,
        le=0.5,
        description="Upper percentile for trimmed mean effect_size calculation - removes top X% (default: 0.01 = remove top 1%). High effect_size DMPs are important for classification, so only remove outliers."
    )
    chromosome_weights: Optional[Dict[str, float]] = Field(
        default=None,
        description="Predefined chromosome weights (bypasses trimmed-mean calculation). Dict format: {'1': 0.5, '2': 0.3, ...}"
    )

    @field_validator('temperature')
    @classmethod
    def validate_temperature(cls, v):
        """Validate temperature bounds."""
        if v < 0.1:
            raise ValueError("Temperature must be >= 0.1")
        if v > 10.0:
            raise ValueError("Temperature must be <= 10.0")
        return v
    
    def model_post_init(self, __context):
        """Validate that at least one input source is provided."""
        has_centroid_dirs = bool(self.centroid1_dir and self.centroid2_dir)
        has_centroid_lists = (
            self.centroid1_sample_paths and self.centroid2_sample_paths
            and len(self.centroid1_sample_paths) > 0 and len(self.centroid2_sample_paths) > 0
        )
        if not self.input_path and not self.samples and not has_centroid_dirs and not has_centroid_lists:
            raise ValueError(
                "Provide one of: 'input_path', 'samples', "
                "both 'centroid1_dir' and 'centroid2_dir', or both 'centroid1_sample_paths' and 'centroid2_sample_paths'"
            )
    
    class Config:
        """Pydantic config."""
        protected_namespaces = ()  # Allow 'model_' prefix
        json_schema_extra = {
            "example": {
                "model_path": "models/classifier-chr1-CG.pkl",
                "input_path": "samples/",
                "output_path": "results/classification_results.csv",
                "debug": False,
                "no_filter": False,
                "log_level": "INFO"
            }
        }
    
    @classmethod
    def from_json(cls, config_path: Path) -> "ClassificationConfig":
        """Load configuration from JSON file."""
        import json
        with open(config_path, 'r') as f:
            data = json.load(f)
        return cls(**data)
    
    def to_json(self, output_path: Path) -> None:
        """Save configuration to JSON file."""
        import json
        with open(output_path, 'w') as f:
            json.dump(self.model_dump(), f, indent=2)

