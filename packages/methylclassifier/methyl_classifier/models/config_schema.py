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
    # N-group / multiclass: when set, use multiclass builder with these classes instead of binary centroid1/centroid2
    centroid_dirs: Optional[List[str]] = Field(
        default=None,
        description="List of centroid directories for N-class (one per class). When len > 2, use with multiclass_class_names and a DMP CSV to build a multiclass model."
    )
    multiclass_class_names: Optional[List[str]] = Field(
        default=None,
        description="Class names for multiclass (same order as centroid_dirs). Used when centroid_dirs has more than 2 entries."
    )
    ovr_binary_model_paths: Optional[List[str]] = Field(
        default=None,
        description="K>=2 MethylDetector PKL paths (OvR order). Assembles ecdf_one_vs_rest at runtime; omit model_dir when set.",
    )
    ovr_detection_dirs: Optional[List[str]] = Field(
        default=None,
        description="K>=2 directories with exactly one classifier*.pkl each (OvR order). Alternative to ovr_binary_model_paths.",
    )
    ovr_class_names: Optional[List[str]] = Field(
        default=None,
        description="Optional override for OvR class names; defaults to multiclass_class_names when multiclass.",
    )
    expected_classes: Optional[List[int]] = Field(
        default=None,
        description="Optional list of expected class index per sample (for validation report). Set when samples are built from centroid_dirs."
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
    project_name: Optional[str] = Field(
        default=None,
        description="Project name for saving classifier as <project_name>-classifier.pkl and sample list. Used when save_classifier_path or samples_list_export_path are not set."
    )
    save_classifier_path: Optional[str] = Field(
        default=None,
        description="Path to save the final classifier .pkl after classification. If null and project_name set, uses <output_dir>/<project_name>-classifier.pkl."
    )
    samples_list_export_path: Optional[str] = Field(
        default=None,
        description="Path to export the list of sample folders (.txt or .csv). If null and project_name set, uses <output_dir>/<project_name>-samples.txt."
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
    weight_method: Optional[str] = Field(
        default=None,
        description="How to obtain chromosome weights: 'config', 'effect_size', or 'linear_fitted'. If None, inferred from chromosome_weights."
    )
    weight_fit_regularization: Optional[str] = Field(
        default="none",
        description="For weight_method='linear_fitted': 'none', 'ridge', or 'lasso'."
    )
    weight_fit_alpha: float = Field(
        default=1.0,
        ge=0.0,
        description="Regularization strength for fitted weights (inverse of C for logistic)."
    )
    weight_fit_l1_ratio: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="For weight_method='elasticnet_fitted': balance L1/L2 (0=ridge-like, 1=lasso-like)."
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

    @field_validator('weight_method')
    @classmethod
    def validate_weight_method(cls, v):
        if v is not None and v not in ("config", "effect_size", "linear_fitted", "logistic_fitted", "elasticnet_fitted"):
            raise ValueError("weight_method must be one of: config, effect_size, linear_fitted, logistic_fitted, elasticnet_fitted")
        return v

    @field_validator('weight_fit_regularization')
    @classmethod
    def validate_weight_fit_regularization(cls, v):
        if v is not None and v not in ("none", "ridge", "lasso", "l1", "l2"):
            raise ValueError("weight_fit_regularization must be one of: none, ridge, lasso, l1, l2")
        return v
    
    def model_post_init(self, __context):
        """Validate that at least one input source is provided."""
        has_centroid_dirs = bool(self.centroid1_dir and self.centroid2_dir)
        has_centroid_lists = (
            self.centroid1_sample_paths and self.centroid2_sample_paths
            and len(self.centroid1_sample_paths) > 0 and len(self.centroid2_sample_paths) > 0
        )
        has_multiclass = bool(
            self.centroid_dirs and len(self.centroid_dirs) >= 2
            and self.multiclass_class_names and len(self.multiclass_class_names) == len(self.centroid_dirs)
        )
        has_ovr_sources = bool(
            (self.ovr_binary_model_paths and len(self.ovr_binary_model_paths) >= 2)
            or (self.ovr_detection_dirs and len(self.ovr_detection_dirs) >= 2)
        )
        if (
            not self.input_path
            and not self.samples
            and not has_centroid_dirs
            and not has_centroid_lists
            and not has_multiclass
            and not has_ovr_sources
        ):
            raise ValueError(
                "Provide one of: 'input_path', 'samples', "
                "both 'centroid1_dir' and 'centroid2_dir', both 'centroid1_sample_paths' and 'centroid2_sample_paths', "
                "'centroid_dirs' with 'multiclass_class_names' (same length), "
                "or ovr_binary_model_paths / ovr_detection_dirs (each length >= 2)."
            )
        if has_multiclass:
            has_model = bool(self.model_dir or self.model_path) or has_ovr_sources
            if not has_model:
                raise ValueError(
                    "Multiclass centroid validation requires model_dir, model_path, "
                    "ovr_binary_model_paths (>=2), or ovr_detection_dirs (>=2)."
                )
            if has_ovr_sources:
                n_p = len(self.ovr_binary_model_paths or [])
                n_d = len(self.ovr_detection_dirs or [])
                k_ovr = n_p if n_p >= 2 else n_d
                names = self.ovr_class_names or self.multiclass_class_names
                if not names or len(names) != k_ovr:
                    raise ValueError(
                        f"OvR class list must have length {k_ovr} (use ovr_class_names or multiclass_class_names)"
                    )
                if len(self.centroid_dirs or []) != k_ovr:
                    raise ValueError(
                        "centroid_dirs length must match OvR source count (K) when using OvR auto-build"
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

