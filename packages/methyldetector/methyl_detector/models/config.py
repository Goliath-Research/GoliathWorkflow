from pathlib import Path
from typing import List, Optional, Union
from math import ceil

from pydantic import BaseModel, Field, field_validator, model_validator


class MethylDetectorConfig(BaseModel):
    """Simplified configuration for MethylDetector analysis."""

    # ----------------
    # Input/Output
    # ----------------
    chromosome: str = Field(
        ..., description="Chromosome to process (e.g., '1', 'X', '22')"
    )
    contexts: List[str] = Field(
        default=["CG", "CHG", "CHH"],
        description="List of methylation contexts to process"
    )
    centroid1_dir: Union[str, Path] = Field(
        ..., description="Directory containing centroid1 .h5 files (format: {chrom}-{context}.h5)"
    )
    centroid2_dir: Union[str, Path] = Field(
        ..., description="Directory containing centroid2 .h5 files (format: {chrom}-{context}.h5)"
    )
    
    # Backward compatibility: allow old centroid paths (optional)
    centroid1_path: Optional[Union[str, Path]] = Field(
        default=None, description="[Deprecated] Path to single centroid .h5 file (for single-context mode)"
    )
    centroid2_path: Optional[Union[str, Path]] = Field(
        default=None, description="[Deprecated] Path to single centroid .h5 file (for single-context mode)"
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

    # New calibration parameters (for trained classifier metadata)
    temperature: float = Field(
        default=1.0, ge=0.1, le=10.0,
        description="Temperature for softmax in trained classifier (1.0 = original, higher softens probabilities)"
    )
    enable_platt_calibration: bool = Field(
        default=False,
        description="Enable Platt scaling calibration on validation data during classification"
    )

    @field_validator('temperature')
    @classmethod
    def validate_temperature(cls, v):
        if v < 0.1:
            raise ValueError("Temperature must be >= 0.1")
        if v > 10.0:
            raise ValueError("Temperature must be <= 10.0")
        return v

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
    # Context Weighting
    # ----------------
    use_context_weights: bool = Field(
        default=True,
        description="Enable trimmed-mean context weighting for multi-context analysis"
    )
    trimmed_percentile: float = Field(
        default=0.10, ge=0.0, le=0.5,
        description="Percentile for trimmed mean (e.g., 0.10 = trim bottom 10% and top 10%)"
    )
    export_all_biological_dmps: bool = Field(
        default=True,
        description="Export all biologically significant DMPs instead of just minimum for target accuracy"
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
    target_balanced_accuracy: float = Field(
        default=0.95, ge=0.5, le=1.0,
        description="Target Balanced Accuracy for binary search DMP selection. Balanced Accuracy = (Sensitivity + Specificity) / 2, robust to class imbalance."
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

    # -----------------
    # Validators / Utils
    # -----------------
    @field_validator('centroid1_dir', 'centroid2_dir')
    @classmethod
    def validate_centroid_dirs(cls, v):
        if v is not None:
            path = Path(v)
            if not path.exists():
                raise ValueError(f"Centroid directory does not exist: {path}")
            if not path.is_dir():
                raise ValueError(f"Centroid path must be a directory: {path}")
        return path
    
    @field_validator('centroid1_path', 'centroid2_path')
    @classmethod
    def validate_centroid_paths(cls, v):
        if v is not None:
            path = Path(v)
            if not path.exists():
                raise ValueError(f"Centroid file does not exist: {path}")
            if path.suffix != '.h5':
                raise ValueError(f"Centroid file must be .h5 format: {path}")
        return path
    
    @field_validator('chromosome')
    @classmethod
    def validate_chromosome(cls, v):
        valid_chroms = [str(i) for i in range(1, 23)] + ['X', 'Y', 'M', 'MT']
        if v not in valid_chroms:
            raise ValueError(f"Chromosome must be one of: {valid_chroms}, got: {v}")
        return v

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
