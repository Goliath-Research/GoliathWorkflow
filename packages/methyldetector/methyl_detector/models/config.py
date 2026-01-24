from pathlib import Path
from typing import List, Optional, Union, Dict, Any
from math import ceil

from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum

# Import utility for extracting chromosome from filenames
try:
    from methyl_modeler.utils.file_utils import get_chromosome_context_from_filename
except ImportError:
    # Fallback if not available
    def get_chromosome_context_from_filename(filepath):
        filename = Path(filepath).stem
        if '-' in filename:
            parts = filename.split('-')
            if len(parts) >= 2:
                return {'chromosome': parts[0], 'context': parts[1]}
        return {'chromosome': 'unknown', 'context': 'unknown'}


class ClassifierType(Enum):
    BETA = "beta"
    BETA_BINOMIAL = "beta_binomial"

class MethylModelerConfig(BaseModel):
    """Simplified configuration for MethylModeler analysis."""

    # ----------------
    # Input/Output
    # ----------------
    chromosome: Union[str, List[str]] = Field(
        ..., description="Chromosome(s) to process. Can be a single chromosome (e.g., '1', 'X', '22') or a list (e.g., ['1', '2', 'X'])"
    )
    contexts: List[str] = Field(
        default=["CG"],
        description="List of methylation contexts to process (e.g., ['CG'], ['CG', 'CHG'], or ['CG', 'CHG', 'CHH']). Default is ['CG'] as it typically provides the strongest signal for most analyses."
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

    @field_validator('contexts')
    @classmethod
    def validate_contexts(cls, v):
        """Validate that contexts are valid methylation contexts."""
        valid_contexts = {"CG", "CHG", "CHH"}
        if not v:
            raise ValueError("At least one context must be specified")
        for ctx in v:
            if ctx not in valid_contexts:
                raise ValueError(f"Invalid context '{ctx}'. Valid contexts are: {valid_contexts}")
        return v

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
    trimmed_percentile_low: float = Field(
        default=0.10, ge=0.0, le=0.5,
        description="Lower percentile for trimmed mean - removes bottom X% (default: 0.10 = remove bottom 10%). Low effect_size DMPs are less informative."
    )
    trimmed_percentile_high: float = Field(
        default=0.01, ge=0.0, le=0.5,
        description="Upper percentile for trimmed mean - removes top X% (default: 0.01 = remove top 1%). High effect_size DMPs are critical for classification, so only extreme outliers are removed."
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
    
    # DMP optimization (requires real samples)
    optimize_dmps: bool = Field(
        default=False,
        description="Enable DMP count optimization using real validation samples (requires validation_mode='real' and validation samples). Uses Bayesian Optimization or FeatureCuts to find optimal DMP count."
    )
    optimization_method: str = Field(
        default="bayesian_optimization",
        description="Optimization method: 'bayesian_optimization' or 'featurecuts'. Both handle non-monotonic BA(k) functions efficiently."
    )
    featurecuts_exhaustive_search: bool = Field(
        default=True,
        description="Enable exhaustive search in FeatureCuts to find maximum Balanced Accuracy. If True, evaluates more k values and refines around best candidates. If False, uses fast logarithmic sampling (~20 candidates)."
    )
    featurecuts_max_candidates: Optional[int] = Field(
        default=None, ge=10,
        description="Maximum number of k values to evaluate in FeatureCuts exhaustive search. If None, automatically determines based on max_k (e.g., min(500, max_k) for exhaustive search). Higher values = more thorough search but slower."
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
    validation_split_ratio: float = Field(
        default=0.0, ge=0.0, le=0.9,
        description="Ratio of validation samples to hold out for testing during optimization (0.0-0.9). If 0.0, uses all samples for Platt calibration without splitting. If >0, splits into calibration and test sets to avoid overfitting during binary search/DE. Set to 0.0 if you have a separate independent test set."
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
        """Validate chromosome(s) - can be a single chromosome or a list."""
        valid_chroms = [str(i) for i in range(1, 23)] + ['X', 'Y', 'M', 'MT']
        
        # Normalize to list for internal use
        if isinstance(v, str):
            if v not in valid_chroms:
                raise ValueError(f"Chromosome must be one of: {valid_chroms}, got: {v}")
            return [v]  # Return as list for consistency
        elif isinstance(v, list):
            if not v:
                raise ValueError("Chromosome list cannot be empty")
            for chrom in v:
                if chrom not in valid_chroms:
                    raise ValueError(f"Chromosome must be one of: {valid_chroms}, got: {chrom}")
            return v
        else:
            raise ValueError(f"Chromosome must be a string or list of strings, got: {type(v)}")

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
    
    classifier_type: str = Field(
        default="beta",
        description="Classifier type. 'beta' (recommended): Uses fractions with sufficient stats. 'beta_binomial' (discouraged): For low-coverage counts only."
    )
    
    min_sample_coverage: int = Field(
        default=10, ge=1, le=100,
        description="Min coverage (mC + uC) for positions in new samples. Below this, positions are ignored in classification."
    )
    
    classifier_coverage_weighting: bool = Field(
        default=True,
        description="If True, weight LLR by sample precision (tau_s ~ coverage); False: uniform."
    )
    
    synthetic_config: Dict[str, Any] = Field(
        default={
            "realism_level": "basic",
            "avg_coverage": 30,
            "min_coverage": 5,
            "correlation_strength": 0.5,
            "variability_scale": 0.2,
            "add_missing": True
        },
        description="Configuration for synthetic data realism"
    )

    # ----------------
    # EAT Transformation (Entropy-weighted Asymmetry Transformation)
    # ----------------
    enable_eat_transform: bool = Field(
        default=False,
        description="Enable Entropy-weighted Asymmetry Transformation (EAT) preprocessing before DMP detection. EAT reweights methylation loci based on Beta distribution shape differences between healthy and cancer centroids, improving DMP selection by emphasizing biologically meaningful differences."
    )
    eat_gamma: float = Field(
        default=1.0, ge=0.0,
        description="EAT entropy damping parameter. Higher values penalize loci with similar/high entropy (indistinguishable distributions). Default 1.0 provides balanced weighting."
    )
    eat_clip_t: Optional[float] = Field(
        default=None, ge=0.0,
        description="Optional clipping threshold for EAT distortion vector T. Values outside [-clip_T, +clip_T] are clipped to prevent extreme reweighting. None = no clipping."
    )
    eat_normalization: str = Field(
        default="l2",
        description="Normalization method applied after EAT transformation: 'l1' (sum to 1), 'l2' (unit norm), 'minmax' (0-1 range), 'zscore' (mean=0, std=1), None (no normalization)"
    )
    eat_low_tau_threshold: float = Field(
        default=5.0, ge=0.0,
        description="Threshold for concentration parameter (alpha+beta) below which EAT falls back to Normal approximation. Prevents numerical issues with low-coverage positions."
    )

    @field_validator('classifier_type')
    @classmethod
    def validate_classifier_type(cls, v):
        valid_types = ["beta", "beta_binomial"]
        if v not in valid_types:
            raise ValueError(f"Invalid classifier_type: {v}. Must be one of {valid_types}.")
        return v

    @field_validator('synthetic_config')
    @classmethod
    def validate_synthetic_config(cls, v):
        realism = v.get('realism_level', 'basic')
        if realism not in ['off', 'basic', 'advanced']:
            raise ValueError("realism_level must be 'off', 'basic', or 'advanced'.")
        return v
    
    @field_validator('trimmed_percentile_low', 'trimmed_percentile_high')
    @classmethod
    def validate_trimmed_percentile(cls, v):
        if v < 0.0 or v > 0.5:
            raise ValueError("Trimmed percentiles must be between 0.0 and 0.5")
        return v

    @field_validator('eat_normalization')
    @classmethod
    def validate_eat_normalization(cls, v):
        valid_norms = ['l1', 'l2', 'minmax', 'zscore', None]
        if v not in valid_norms:
            raise ValueError(f"EAT normalization must be one of: {valid_norms}, got: {v}")
        return v
    
    @model_validator(mode='after')
    def _post_root_validate(self):
        """Post-validation: backward compatibility and additional checks."""
        # Backward compatibility for old configs using centroid1_path/centroid2_path
        if self.centroid1_path and self.centroid2_path:
            if not isinstance(self.chromosome, list) or len(self.chromosome) == 0:
                # Extract chromosome from filename (e.g., "1-CG.h5" -> "1")
                try:
                    chrom_info = get_chromosome_context_from_filename(self.centroid1_path)
                    extracted_chrom = chrom_info['chromosome']
                    if extracted_chrom != 'unknown':
                        self.chromosome = [extracted_chrom]  # Normalize to list
                except Exception:
                    if not isinstance(self.chromosome, list) or len(self.chromosome) == 0:
                        raise ValueError("Cannot infer chromosome from centroid1_path. Please specify 'chromosome' in config.")
            
            if not self.centroid1_dir:
                self.centroid1_dir = Path(self.centroid1_path).parent
            if not self.centroid2_dir:
                self.centroid2_dir = Path(self.centroid2_path).parent
            
            # Clear old paths to ensure new fields are used
            self.centroid1_path = None
            self.centroid2_path = None
        
        # Ensure chromosome is set if dirs are set but chrom is not
        if (not isinstance(self.chromosome, list) or len(self.chromosome) == 0) and self.centroid1_dir and self.contexts:
            # Try to infer from first centroid file in dir
            first_centroid_file = next(Path(self.centroid1_dir).glob(f"*-{self.contexts[0]}.h5"), None)
            if first_centroid_file:
                try:
                    chrom_info = get_chromosome_context_from_filename(first_centroid_file)
                    extracted_chrom = chrom_info['chromosome']
                    if extracted_chrom != 'unknown':
                        self.chromosome = [extracted_chrom]  # Normalize to list
                except Exception:
                    pass # Will be caught by chromosome validator if still None
        
        # Check that the sum of trimmed percentiles doesn't exceed 1.0
        if self.trimmed_percentile_low + self.trimmed_percentile_high >= 1.0:
            raise ValueError(f"Sum of trimmed_percentile_low ({self.trimmed_percentile_low}) and trimmed_percentile_high ({self.trimmed_percentile_high}) must be less than 1.0")
        
        # Ensure min_dmps_for_export is not less than 1
        if self.min_dmps_for_export < 1:
            self.min_dmps_for_export = 1
        
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
