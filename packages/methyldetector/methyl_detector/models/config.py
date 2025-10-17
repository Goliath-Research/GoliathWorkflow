from pathlib import Path
from typing import List, Optional, Union
from math import ceil

from pydantic import BaseModel, Field, field_validator, model_validator


class MethylDetectorConfig(BaseModel):
    """Simplified configuration for MethylDetector analysis."""

    # ----------------
    # Input/Output
    # ----------------
    centroid1_path: Union[str, Path] = Field(
        ..., description="Path to first extended centroid .h5 file"
    )
    centroid2_path: Union[str, Path] = Field(
        ..., description="Path to second extended centroid .h5 file"
    )
    output_dir: Optional[Union[str, Path]] = Field(
        default=None, description="Output directory for results"
    )

    # ----------------
    # Statistical Filter
    # ----------------
    alpha: float = Field(
        default=0.05, ge=0.0, le=1.0,
        description="Significance level for statistical tests (q-value threshold)"
    )

    # ----------------
    # Coverage Filter
    # ----------------
    min_N_pct: float = Field(
        default=0.10, ge=0.0, le=1.0,
        description="Minimum fraction of samples that must cover a position (e.g., 0.10 = 10%)"
    )
    min_N_abs: Optional[int] = Field(
        default=None, ge=1,
        description="Absolute minimum sample count per position (optional, min_N_pct takes precedence)"
    )

    # ----------------
    # Biological Filters
    # ----------------
    min_delta_mean: float = Field(
        default=0.2, ge=0.0, le=1.0,
        description="Minimum absolute delta mean (|mean1 - mean2|) for biological significance"
    )
    max_bc: Optional[float] = Field(
        default=0.6, ge=0.0, le=1.0,
        description="Maximum Bhattacharyya Coefficient (overlap) allowed. BC ranges 0-1 where 0=no overlap (perfect separation), 1=complete overlap. Lower values = stricter filtering. Example: 0.6 means 'keep only DMPs with ≤60% overlap'"
    )
    min_effect_size: Optional[float] = Field(
        default=None, ge=0.0,
        description="Minimum effect size threshold for filtering. Effect size = |delta_mu / var_delta_mu| * (1 - BC)^gamma. None = no effect size filtering"
    )
    gamma: float = Field(
        default=1.5, ge=1.0, le=2.0,
        description="Exponent for overlap penalty in effect_size calculation. Higher values = stronger penalty for overlapping distributions"
    )
    biological_filters: List[str] = Field(
        default=["delta_mean", "bhattacharyya"],
        description="List of biological filters to apply: 'delta_mean' filters by effect size, 'bhattacharyya' filters by distribution separation (Bhattacharyya Distance)"
    )

    # ----------------
    # DMP Selection
    # ----------------
    min_selected_dmps: Optional[int] = Field(
        default=None, ge=1,
        description="Minimum number of DMPs to select via binary search (None = auto-determine)"
    )
    min_dmps_for_export: int = Field(
        default=1000, ge=1,
        description="Minimum number of DMPs to export to CSV, even if binary search finds fewer DMPs are sufficient. Ensures enough DMPs for gene mapping and downstream analysis"
    )
    target_auc: float = Field(
        default=0.95, ge=0.5, le=1.0,
        description="Target AUC for binary search DMP selection"
    )
    n_validation_samples: int = Field(
        default=100, ge=10,
        description="Number of synthetic samples per class to generate for classifier validation (from Beta distributions)"
    )
    
    # Validation-accuracy optimization (requires real samples)
    optimize_for_validation_accuracy: bool = Field(
        default=False,
        description="Enable accuracy-based DMP optimization using real validation samples (requires validation_mode='real' and validation samples). Uses binary search to find minimum k that achieves maximum accuracy."
    )
    validation_search_max_k: Optional[int] = Field(
        default=None, ge=1,
        description="Maximum k to test during validation optimization (default: all available DMPs). Algorithm tests this k first to find best achievable accuracy, then binary searches for minimum k."
    )
    
    # Improved algorithm parameters (analytical approach)
    target_fpr: float = Field(
        default=0.01, ge=0.0, le=1.0,
        description="Target false positive rate for analytical DMP selection (default 1%)"
    )
    target_fnr: float = Field(
        default=0.01, ge=0.0, le=1.0,
        description="Target false negative rate for analytical DMP selection (default 1%)"
    )
    rank_gamma: float = Field(
        default=1.0, ge=0.0, le=5.0,
        description="Exponent for (1-BC) term in precision-weighted ranking: score = (|Δμ|/√var) × (1-BC)^γ. Higher values increase penalty for overlapping distributions"
    )
    var_pool: str = Field(
        default="sum",
        description="Variance pooling method for precision-weighted scoring: 'sum' (default), 'max', or 'harmonic'"
    )
    prior_cancer: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Prior probability for cancer/disease class in Bayesian classification"
    )
    prior_healthy: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Prior probability for healthy/control class in Bayesian classification"
    )
    centroid1_label: str = Field(
        default="cancer",
        description="Class label for centroid1: 'cancer' or 'healthy'. Determines which Beta parameters represent which class."
    )
    centroid2_label: str = Field(
        default="healthy",
        description="Class label for centroid2: 'cancer' or 'healthy'. Must be opposite of centroid1_label."
    )
    
    # ----------------
    # Validation Configuration
    # ----------------
    validation_mode: str = Field(
        default="synthetic",
        description="Validation mode: 'synthetic' (generate from Beta distributions) or 'real' (use actual samples)"
    )
    centroid1_validation_samples: Optional[Union[str, List[str]]] = Field(
        default=None,
        description="Validation samples for centroid1. Can be 'use_metadata' to read from centroid metadata, or list of sample directory paths"
    )
    centroid2_validation_samples: Optional[Union[str, List[str]]] = Field(
        default=None,
        description="Validation samples for centroid2. Can be 'use_metadata' to read from centroid metadata, or list of sample directory paths"
    )
    
    # ----------------
    # System Settings
    # ----------------
    random_state: Optional[int] = Field(
        default=42,
        description="Random seed for reproducible results"
    )
    use_gpu: bool = Field(
        default=True,
        description="Whether to use GPU acceleration"
    )
    eps: float = Field(
        default=1e-6, gt=0,
        description="Epsilon for numerical stability in variance calculations (prevents division by zero in effect_size = |delta_mu / var_delta_mu|)"
    )

    # ----------------
    # Output Options
    # ----------------
    verbose: bool = Field(
        default=False,
        description="Enable verbose logging and progress reporting"
    )
    generate_histograms: bool = Field(
        default=False,
        description="Generate interactive HTML histograms for filter statistics"
    )

    # -----------------
    # Validators / Utils
    # -----------------
    @field_validator('centroid1_path', 'centroid2_path')
    @classmethod
    def validate_centroid_paths(cls, v):
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Centroid file does not exist: {path}")
        if path.suffix != '.h5':
            raise ValueError(f"Centroid file must be .h5 format: {path}")
        return path

    @field_validator('output_dir')
    @classmethod
    def validate_output_dir(cls, v):
        if v is not None:
            path = Path(v)
            if not str(path):
                raise ValueError("Output directory cannot be empty")
        return v

    @field_validator('biological_filters')
    @classmethod
    def validate_biological_filters(cls, v):
        valid_filters = ['delta_mean', 'bhattacharyya']
        for f in v:
            if f not in valid_filters:
                raise ValueError(f"Biological filter must be one of: {valid_filters}, got: {f}")
        return v
    
    @field_validator('validation_mode')
    @classmethod
    def validate_validation_mode(cls, v):
        valid_modes = ['synthetic', 'real']
        if v not in valid_modes:
            raise ValueError(f"Validation mode must be one of: {valid_modes}, got: {v}")
        return v
    
    @field_validator('var_pool')
    @classmethod
    def validate_var_pool(cls, v):
        valid_methods = ['sum', 'max', 'harmonic']
        if v not in valid_methods:
            raise ValueError(f"var_pool must be one of: {valid_methods}, got: {v}")
        return v
    
    @field_validator('centroid1_label', 'centroid2_label')
    @classmethod
    def validate_centroid_labels(cls, v):
        """Validate centroid class labels."""
        valid_labels = ['cancer', 'healthy']
        v_lower = v.lower()
        if v_lower not in valid_labels:
            raise ValueError(f"Centroid label must be one of: {valid_labels}, got: {v}")
        return v_lower

    @model_validator(mode='after')
    def validate_config(self):
        """Validate configuration consistency."""
        # Ensure priors sum to 1.0
        if abs(self.prior_cancer + self.prior_healthy - 1.0) > 1e-6:
            raise ValueError(f"Priors must sum to 1.0, got: {self.prior_cancer} + {self.prior_healthy} = {self.prior_cancer + self.prior_healthy}")
        
        # Ensure centroid labels are different
        if self.centroid1_label == self.centroid2_label:
            raise ValueError(f"centroid1_label and centroid2_label must be different, both are '{self.centroid1_label}'")
        
        return self

    # ---------------
    # Helper Methods
    # ---------------
    def effective_min_N(self, cohort_size: int) -> int:
        """
        Compute the effective absolute min-N for a position given the cohort size.
        Percentage gate takes precedence; absolute fallback retained for back-compat.
        """
        pct = max(0.0, min(1.0, float(self.min_N_pct)))
        n_from_pct = ceil(pct * cohort_size)
        if self.min_N_abs is not None:
            return max(n_from_pct, int(self.min_N_abs))
        return n_from_pct
