from pathlib import Path
from typing import List, Literal, Optional, Union, Dict, Any
from math import ceil

from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum

# Import utility for extracting chromosome from filenames
try:
    from methyl_detector.utils.file_utils import get_chromosome_context_from_filename  # type: ignore[import-not-found]
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


class FilterFunnelRangeSpec(BaseModel):
    """Range and step for sweeping one biological filter (min, min+step, ... up to max)."""
    min: float = Field(..., description="Minimum value (inclusive)")
    max: float = Field(..., description="Maximum value (inclusive)")
    step: float = Field(..., gt=0, description="Step between values")

    @model_validator(mode="after")
    def min_le_max(self):
        if self.min > self.max:
            raise ValueError("min must be <= max")
        return self


class FilterFunnelExplore(BaseModel):
    """
    Optional exploration: sweep biological filters and write filter_funnel.csv.
    Mode: one_at_a_time (vary each filter over its range, others fixed) or full_grid (all combinations).
    """
    mode: Literal["one_at_a_time", "full_grid"] = Field(
        default="one_at_a_time",
        description="one_at_a_time: vary each filter over its range with others fixed. full_grid: all combinations of the three value lists."
    )
    min_delta_mean: Optional[FilterFunnelRangeSpec] = Field(
        default=None,
        description="Range/step for min_delta_mean (values in [0,1], e.g. 0.1 = 10%% methylation change)"
    )
    max_overlap: Optional[FilterFunnelRangeSpec] = Field(
        default=None,
        description="Range/step for max_overlap (values in [0,1])"
    )
    min_effect_size: Optional[FilterFunnelRangeSpec] = Field(
        default=None,
        description="Range/step for min_effect_size (values >= 0)"
    )


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

    optimize_dmps: bool = Field(
        default=True,
        description="Enable DMP subset optimization via validation BA"
    )

    validation_mode: str = Field(
        default="real",
        description="Validation mode: 'real' (prefer real samples from config or centroid metadata samples_used; fall back to synthetic if none available), 'synthetic' (skip real, use synthetic only)."
    )


    n_validation_samples: Optional[int] = Field(
        default=None,
        description="Number of synthetic validation samples per class. Only used when validation is synthetic (fallback or validation_mode='synthetic'). Ignored when real samples are provided via centroid1_validation_samples / centroid2_validation_samples or use_metadata."
    )

    validation_split_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of validation data held out for test (rest for calibration). 0 = no split, use all real validation samples for BA (default). Set e.g. 0.2 for a holdout when you want train/test separation."
    )

    centroid1_validation_samples: Optional[Union[str, List[str]]] = Field(
        default=None,
        description="Validation sample paths for centroid1: list of paths, 'use_metadata', or None. If None and validation_mode is 'real', centroid metadata (samples_used) is used by default; if no real data is available, synthetic samples are used."
    )
    centroid2_validation_samples: Optional[Union[str, List[str]]] = Field(
        default=None,
        description="Validation sample paths for centroid2: list of paths, 'use_metadata', or None. If None and validation_mode is 'real', centroid metadata (samples_used) is used by default; if no real data is available, synthetic samples are used."
    )

    target_balanced_accuracy: float = Field(
        default=0.99,
        ge=0.5, le=1.0,
        description="Target/max BA for optimization (finds peak BA)"
    )

    optimization_method: str = Field(
        default="featurecuts",
        description="DMP subset optimization: 'featurecuts' (coarse+refinement), 'bayesian_optimization', or 'binary_search'. Try binary_search or bayesian_optimization if featurecuts gives BA≈0.5."
    )

    random_state: int = Field(
        default=42,
        ge=0,
        description="Random seed for reproducibility"
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
    # Biological Filter (effect_size from MethylCentroidPair: |delta_mean|/(overlap*combined_std))
    # ----------------
    delta_mean_mode: str = Field(
        default="mean",
        description="How to compute mean/delta_mean for biological filtering: mean (centroid mean), beta (alpha/beta), normal (Sx/N), auto (per-distribution)"
    )
    overlap_mode: str = Field(
        default="beta",
        description="How to compute overlap for biological filtering: beta (Bhattacharyya distance between Beta), normal (Normal BD), auto (per-distribution)"
    )
    distribution: str = Field(
        default="auto",
        description="Per-position distribution for DMP testing: auto (choose by coverage/overdispersion), beta, normal, beta_binomial, beta_mixture. Auto uses Beta-Binomial for low/ variable coverage, Beta otherwise."
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

    @field_validator('n_validation_samples')
    def validate_n_validation(cls, v):
        if v is not None and v < 10:
            raise ValueError("n_validation_samples must be >=10 or None")
        return v

    @field_validator('contexts', mode='before')
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

    @field_validator('temperature', mode='before')
    @classmethod
    def validate_temperature(cls, v):
        if v < 0.1:
            raise ValueError("Temperature must be >= 0.1")
        if v > 10.0:
            raise ValueError("Temperature must be <= 10.0")
        return v

    @field_validator('bmm_refine_mode', mode='before')
    @classmethod
    def validate_bmm_refine_mode(cls, v):
        valid = {"annotate", "filter"}
        if v not in valid:
            raise ValueError(f"Invalid bmm_refine_mode '{v}'. Valid options: {valid}")
        return v

    @field_validator('bmm_refine_filter_metric', mode='before')
    @classmethod
    def validate_bmm_refine_filter_metric(cls, v):
        valid = {"p_value", "js"}
        if v not in valid:
            raise ValueError(f"Invalid bmm_refine_filter_metric '{v}'. Valid options: {valid}")
        return v

    min_effect_size: Optional[float] = Field(
        default=None, ge=0.0,
        description="Minimum effect_size for biological filter. Keep DMPs with effect_size >= min_effect_size. Set null to disable. effect_size is computed by MethylCentroidPair (|delta_mean|/(overlap*combined_std))."
    )
    min_delta_mean: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Minimum absolute methylation difference for biological filter. Keep DMPs with |delta_mean| >= min_delta_mean (e.g. 0.1 = 10%% change). Set null to disable. Easy to interpret for biologists."
    )
    max_overlap: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Maximum overlap (Bhattacharyya coefficient, 0–1) for biological filter. Keep DMPs with overlap <= max_overlap (low overlap = good separation). Set null to disable. Easy to interpret for biologists."
    )

    # ----------------
    # Filter funnel exploration (sweep biological filters, write JSON)
    # ----------------
    filter_funnel_explore: Optional[FilterFunnelExplore] = Field(
        default=None,
        description="Optional. Sweep biological filter values over range/step and write filter_funnel.csv (n_statistical_dmps, min_delta_mean, max_overlap, min_effect_size, n_biological_dmps). One run; no large DMP CSV. Set to null to disable."
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

    # ----------------
    # BMM Refinement (Detector Stage)
    # ----------------
    bmm_refine_enabled: bool = Field(
        default=False,
        description="Enable Beta Mixture Model refinement at detector stage (uses real samples if available)"
    )
    bmm_refine_mode: str = Field(
        default="filter",
        description="BMM refinement mode: 'annotate' (add BMM stats only) or 'filter' (drop weak mixture separations)"
    )
    bmm_refine_filter_metric: str = Field(
        default="p_value",
        description="Metric used for BMM filtering: 'p_value' or 'js'"
    )
    bmm_refine_pvalue_threshold: float = Field(
        default=0.05, ge=0.0, le=1.0,
        description="P-value threshold for BMM filtering when metric is 'p_value'"
    )
    bmm_refine_replace_p_value: bool = Field(
        default=True,
        description="If True, replace p_value with BMM-derived p_value (preserving original in p_value_lrt)"
    )
    bmm_refine_recompute_q: bool = Field(
        default=True,
        description="If True, recompute q_value after replacing p_value"
    )
    bmm_refine_max_dmps: int = Field(
        default=200000, ge=100,
        description="Maximum number of DMPs to evaluate with BMM (top by effect_size/importance)"
    )
    bmm_refine_max_fraction: Optional[float] = Field(
        default=0.02, ge=0.0, le=1.0,
        description="Optional fraction cap for BMM evaluation (e.g., 0.02 = top 2% of biological DMPs)"
    )
    bmm_refine_max_samples_per_group: int = Field(
        default=50, ge=5,
        description="Maximum samples per group to use for BMM fitting (subsampled for speed)"
    )
    bmm_refine_min_samples_per_group: int = Field(
        default=10, ge=3,
        description="Minimum samples per group required to fit BMM for a position"
    )
    bmm_refine_max_components: int = Field(
        default=3, ge=1, le=3,
        description="Maximum mixture components to fit per position"
    )
    bmm_refine_use_gpu: bool = Field(
        default=True,
        description="Use GPU for BMM EM when available"
    )
    bmm_refine_js_threshold: float = Field(
        default=0.05, ge=0.0,
        description="Minimum Jensen-Shannon divergence to retain a DMP when filtering"
    )
    bmm_refine_skip_delta_mean: float = Field(
        default=0.4, ge=0.0, le=1.0,
        description="Skip BMM fitting when |delta_mean| exceeds this threshold (obvious separation)"
    )
    bmm_refine_skip_overlap: float = Field(
        default=0.2, ge=0.0, le=1.0,
        description="Skip BMM fitting when Bhattacharyya overlap ≤ this threshold (obvious separation)"
    )
    bmm_refine_mc_samples: int = Field(
        default=200, ge=50,
        description="Monte Carlo samples for mixture JS divergence estimate"
    )
    bmm_refine_use_binned_stats: bool = Field(
        default=True,
        description="Use binned methylation values (counts per bin) for faster BMM fitting"
    )
    bmm_refine_bin_count: Optional[int] = Field(
        default=32, ge=10,
        description="Number of bins for binned stats. If None, uses a heuristic based on sample count."
    )
    bmm_refine_use_metadata_samples: bool = Field(
        default=True,
        description="If validation sample paths are not provided, try centroid metadata ('samples_used')"
    )

    
    # ----------------
    # Debug / Logging
    # ----------------
    debug: bool = Field(
        default=False,
        description="Enable debug output (e.g. classifier predict_proba in centroid self-check, extra validation logs)."
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
    export_sample_size_estimate: bool = Field(
        default=False,
        description="If True, add n_estimated_per_group column to DMP CSV: sample size per group needed for target_power (two-sample t-test, Cohen's d from delta_mean and combined variance)."
    )
    target_power: float = Field(
        default=0.8, ge=0.5, le=0.999,
        description="Target power (1 - type II error) for sample size estimation when export_sample_size_estimate is True (e.g. 0.8 = 80%% power)."
    )

    # -----------------
    # Validators / Utils
    # -----------------
    @field_validator('centroid1_dir', 'centroid2_dir', mode='before')
    @classmethod
    def validate_centroid_dirs(cls, v):
        if v is not None:
            path = Path(v)
            if not path.exists():
                raise ValueError(
                    f"Centroid directory does not exist: {path}. "
                    "If using a project JSON from another machine or path, run with "
                    "--output-base /path/to/local/output so centroid and detection paths are resolved under that directory."
                )
            if not path.is_dir():
                raise ValueError(f"Centroid path must be a directory: {path}")
        return path
    
    @field_validator('centroid1_path', 'centroid2_path', mode='before')
    @classmethod
    def validate_centroid_paths(cls, v):
        if v is not None:
            path = Path(v)
            if not path.exists():
                raise ValueError(f"Centroid file does not exist: {path}")
            if path.suffix != '.h5':
                raise ValueError(f"Centroid file must be .h5 format: {path}")
        return path
    
    @field_validator('chromosome', mode='before')
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

    @field_validator('output_dir', mode='before')
    @classmethod
    def validate_output_dir(cls, v):
        if v is not None:
            path = Path(v)
            if not str(path):
                raise ValueError("Output directory cannot be empty")
        return v

    @field_validator('delta_mean_mode', mode='before')
    @classmethod
    def validate_delta_mean_mode(cls, v):
        valid = {"mean", "beta", "normal", "auto", "legacy"}
        if v not in valid:
            raise ValueError(f"delta_mean_mode must be one of: {sorted(valid)}, got: {v}")
        return v

    @field_validator('overlap_mode', mode='before')
    @classmethod
    def validate_overlap_mode(cls, v):
        valid = {"beta", "normal", "auto", "legacy"}
        if v not in valid:
            raise ValueError(f"overlap_mode must be one of: {sorted(valid)}, got: {v}")
        return v

    @field_validator('distribution', mode='before')
    @classmethod
    def validate_distribution(cls, v):
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return "auto"
        valid = {"auto", "beta", "normal", "beta_binomial", "beta_mixture"}
        vnorm = str(v).strip().lower()
        if vnorm not in valid:
            raise ValueError(f"distribution must be one of: {sorted(valid)}, got: {v}")
        return vnorm

    # @field_validator('validation_mode', mode='before')
    # @classmethod
    # def validate_validation_mode(cls, v):
    #     valid_modes = ['synthetic', 'real']
    #     if v not in valid_modes:
    #         raise ValueError(f"Validation mode must be one of: {valid_modes}, got: {v}")
    #     return v
    
    classifier_type: str = Field(
        default="beta",
        description="Classifier type. 'beta' (recommended): Uses fractions with sufficient stats. 'beta_binomial' (discouraged): For low-coverage counts only."
    )
    
    min_sample_coverage: int = Field(
        default=10, ge=1, le=100,
        description="Min coverage (mC + uC) for positions in new samples. Below this, positions are ignored in classification. Use a lower value (e.g. 4) when centroids were built with high min_coverage (e.g. 10) but patient samples have lower coverage."
    )
    
    validation_min_coverage: int = Field(
        default=4, ge=1, le=100,
        description="Min coverage when extracting methylation from validation/centroid samples. Use a value lower than the centroid's min_coverage (e.g. 4 if centroid used 10) so validation samples contribute values at more positions and better match lower-coverage patient data."
    )

    min_validation_coverage_per_position: int = Field(
        default=1, ge=1, le=100,
        description="Minimum number of validation samples that must cover a position for it to be kept in calibration/test. Used to drop positions with too few non-NaN values so BA has signal."
    )

    featurecuts_exhaustive_search: bool = Field(
        default=True,
        description="When optimization_method is 'featurecuts', use exhaustive search over k. If False, use a coarser search."
    )
    featurecuts_max_candidates: Optional[int] = Field(
        default=None, ge=1,
        description="When optimization_method is 'featurecuts', maximum number of k candidates to evaluate. None = no limit."
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

    @field_validator('classifier_type', mode='before')
    @classmethod
    def validate_classifier_type(cls, v):
        valid_types = ["beta", "beta_binomial"]
        if v not in valid_types:
            raise ValueError(f"Invalid classifier_type: {v}. Must be one of {valid_types}.")
        return v

    @field_validator('synthetic_config', mode='before')
    @classmethod
    def validate_synthetic_config(cls, v):
        realism = v.get('realism_level', 'basic')
        if realism not in ['off', 'basic', 'advanced']:
            raise ValueError("realism_level must be 'off', 'basic', or 'advanced'.")
        return v
    
    @field_validator('trimmed_percentile_low', 'trimmed_percentile_high', mode='before')
    @classmethod
    def validate_trimmed_percentile(cls, v):
        if v < 0.0 or v > 0.5:
            raise ValueError("Trimmed percentiles must be between 0.0 and 0.5")
        return v

    @field_validator('eat_normalization', mode='before')
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
