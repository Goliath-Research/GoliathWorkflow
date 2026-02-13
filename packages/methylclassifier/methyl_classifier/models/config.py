from pydantic import Field, field_validator, model_validator
from typing import Optional, Dict, Literal
from pathlib import Path
from pydantic import BaseModel

WeightMethod = Literal["config", "effect_size", "linear_fitted", "logistic_fitted", "elasticnet_fitted"]
WeightFitRegularization = Literal["none", "ridge", "lasso", "l1", "l2"]


class ClassifierConfig(BaseModel):
    # Model path (can be file or directory for multi-chromosome mode)
    model_path: Optional[str] = Field(
        default=None,
        description="Path to trained classifier model (.pkl file) or directory containing classifier-{chrom}.pkl files"
    )
    # Multi-chromosome parameters
    model_dir: Optional[str] = Field(
        default=None,
        description="Path to directory containing classifier-{chrom}.pkl files (alternative to model_path)"
    )
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
    weight_method: Optional[WeightMethod] = Field(
        default=None,
        description="How to obtain chromosome weights: 'config', 'effect_size', 'linear_fitted', 'logistic_fitted', or 'elasticnet_fitted'. If None, inferred: config when chromosome_weights set, else effect_size."
    )
    weight_fit_regularization: Optional[WeightFitRegularization] = Field(
        default="none",
        description="For linear_fitted: 'none', 'ridge', 'lasso'. For logistic_fitted: 'none', 'l1', 'l2'. For elasticnet_fitted: ignored (uses l1_ratio)."
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
    # Prediction parameters
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

    # Output configuration
    chromosome_matrix_path: Optional[str] = Field(
        default=None,
        description="Optional output CSV file for chromosome probability matrix (samples × chromosomes)"
    )
    project_name: Optional[str] = Field(
        default=None,
        description="Project name for saving the classifier as <project_name>-classifier.pkl and sample list as <project_name>-samples.txt (or .csv). Used when save_classifier_path or samples_list_export_path are not set."
    )
    save_classifier_path: Optional[str] = Field(
        default=None,
        description="Path to save the final classifier as .pkl after classification. If null and project_name is set, saves to <output_dir>/<project_name>-classifier.pkl."
    )
    samples_list_export_path: Optional[str] = Field(
        default=None,
        description="Path to export the list of sample folders (.txt or .csv). If null and project_name is set, exports to <output_dir>/<project_name>-samples.txt."
    )

    @field_validator('temperature')
    @classmethod
    def validate_temperature(cls, v):
        if v < 0.1:
            raise ValueError("Temperature must be >= 0.1")
        if v > 10.0:
            raise ValueError("Temperature must be <= 10.0")
        return v
    
    @field_validator('trimmed_percentile_low', 'trimmed_percentile_high')
    @classmethod
    def validate_trimmed_percentile(cls, v):
        if v < 0.0 or v > 0.5:
            raise ValueError("Trimmed percentiles must be between 0.0 and 0.5")
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

    @model_validator(mode='after')
    def validate_trimmed_percentile_sum(self):
        # Check that the sum doesn't exceed 1.0 (would trim everything)
        if self.trimmed_percentile_low + self.trimmed_percentile_high >= 1.0:
            raise ValueError(f"Sum of trimmed_percentile_low ({self.trimmed_percentile_low}) and trimmed_percentile_high ({self.trimmed_percentile_high}) must be less than 1.0")
        return self
    
    class Config:
        """Pydantic config."""
        protected_namespaces = ()  # Allow 'model_' prefix
