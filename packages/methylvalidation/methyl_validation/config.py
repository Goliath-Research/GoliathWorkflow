"""
Runner config schema for Monte Carlo validation.
"""

from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class CohortCsv(BaseModel):
    """One cohort: display label (must match base project flat ``groups`` labels for K>2) and sample list CSV."""

    label: str = Field(
        ...,
        min_length=1,
        description="Cohort label: for hierarchical MC must match get_resolved_groups() (e.g. all, pca_pca1).",
    )
    csv: str = Field(..., min_length=1, description="Path to CSV of samples (same format as healthy_csv).")


class RandomForestMethodParams(BaseModel):
    n_estimators: int = Field(default=300, ge=1)
    min_samples_leaf: int = Field(default=2, ge=1)
    n_jobs: int = Field(default=-1)
    class_weight: str = Field(default="balanced_subsample")
    random_state: int = Field(default=13)


class HistGradientBoostingMethodParams(BaseModel):
    random_state: int = Field(default=13)
    learning_rate: float = Field(default=0.1, gt=0.0)
    max_iter: int = Field(default=100, ge=1)
    max_depth: Optional[int] = Field(default=None, ge=1)


class LogisticRegressionMethodParams(BaseModel):
    max_iter: int = Field(default=1000, ge=1)
    class_weight: str = Field(default="balanced")
    random_state: int = Field(default=13)
    c: float = Field(default=1.0, gt=0.0)
    solver: str = Field(default="lbfgs")
    penalty: str = Field(default="l2")


class XGBoostMethodParams(BaseModel):
    n_estimators: int = Field(default=300, ge=1)
    max_depth: int = Field(default=6, ge=1)
    learning_rate: float = Field(default=0.1, gt=0.0)
    subsample: float = Field(default=1.0, gt=0.0, le=1.0)
    colsample_bytree: float = Field(default=1.0, gt=0.0, le=1.0)
    min_child_weight: float = Field(default=1.0, gt=0.0)
    reg_lambda: float = Field(default=1.0, ge=0.0)
    random_state: int = Field(default=13)
    n_jobs: int = Field(default=-1)
    tree_method: str = Field(default="hist")
    eval_metric: str = Field(default="mlogloss")
    objective: Optional[str] = Field(default=None)
    verbosity: int = Field(default=0)


class RandomForestMethodConfig(BaseModel):
    method: Literal["random_forest"]
    params: RandomForestMethodParams = Field(default_factory=RandomForestMethodParams)


class HistGradientBoostingMethodConfig(BaseModel):
    method: Literal["hist_gradient_boosting"]
    params: HistGradientBoostingMethodParams = Field(default_factory=HistGradientBoostingMethodParams)


class LogisticRegressionMethodConfig(BaseModel):
    method: Literal["logistic_regression"]
    params: LogisticRegressionMethodParams = Field(default_factory=LogisticRegressionMethodParams)


class XGBoostMethodConfig(BaseModel):
    method: Literal["xgboost"]
    params: XGBoostMethodParams = Field(default_factory=XGBoostMethodParams)


TabularMethodConfig = Annotated[
    Union[
        RandomForestMethodConfig,
        HistGradientBoostingMethodConfig,
        LogisticRegressionMethodConfig,
        XGBoostMethodConfig,
    ],
    Field(discriminator="method"),
]


class MonteCarloConfig(BaseModel):
    """Configuration for the Monte Carlo validation runner (binary K=2 or multiclass K>=2)."""

    samples_base_path: str = Field(
        ...,
        description="Base directory for resolving sample names from CSVs (same as project samples_base_path).",
    )
    healthy_csv: Optional[str] = Field(
        default=None,
        description="Legacy: CSV listing control/healthy samples. Use with disease_csv, or use cohorts instead.",
    )
    disease_csv: Optional[str] = Field(
        default=None,
        description="Legacy: CSV listing disease samples. Use with healthy_csv, or use cohorts instead.",
    )
    cohorts: List[CohortCsv] = Field(
        default_factory=list,
        description="Ordered list of at least 2 cohorts {label, csv}. Populated from legacy healthy_csv+disease_csv when omitted.",
    )
    train_fraction: float = Field(
        ...,
        gt=0.0,
        lt=1.0,
        description="Fraction of samples used for training per cohort (e.g. 0.8).",
    )
    n_iterations: int = Field(
        ...,
        ge=1,
        description="Number of Monte Carlo iterations (e.g. 50–200).",
    )
    seed: Optional[int] = Field(
        default=None,
        description="Optional RNG seed for reproducibility.",
    )
    base_project: str = Field(
        ...,
        description="Path to an existing project JSON used as template; sample_paths overridden per run.",
    )
    output_base: str = Field(
        ...,
        description="Global output base. Runs under output_base / project_name / monte_carlo_runs / run_0001, ...",
    )
    path_remap: Optional[Dict[str, str]] = Field(
        default=None,
        description=(
            "Optional prefix remap (old -> new) for path strings in project JSON (e.g. samples_base_path, "
            "paths to cohort list files). User cohort CSVs and MV training_*.csv use basenames only; "
            "MV testing_*.csv uses absolute paths in a path column and is rewritten during --freeze when needed. "
            "Bases like samples_base_path must match the machine. "
            "Put under step_config.validation in the project JSON, or pass --path-remap OLD=NEW."
        ),
    )
    abort_on_step_failure: bool = Field(
        default=False,
        description="If True, abort all iterations when a pipeline step fails; if False, skip the iteration.",
    )
    run_stability: bool = Field(
        default=False,
        description="If True, run stability analysis on discovery DMPs after the main loop (gene stability only if enricher ran).",
    )
    stability_dmp_freq: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum frequency (across runs) for a DMP to be considered stable.",
    )
    stability_min_balanced_accuracy: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "If set, stability counts DMPs only from iterations whose validation_metrics.json "
            "balanced_accuracy is >= this value. Frequencies are over those qualifying runs only."
        ),
    )
    stability_gene_freq: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum frequency for a gene to be considered stable (only when enricher outputs exist).",
    )
    stability_dual_cutoff_enabled: bool = Field(
        default=False,
        description=(
            "If true, stability outputs both strict and relaxed stable DMP panels "
            "using score = effect_size * sqrt(frequency) with log-score elbow cutoff."
        ),
    )
    stability_relaxed_cutoff_mode: Literal["elbow_log_score", "strict_multiplier"] = Field(
        default="elbow_log_score",
        description=(
            "How to derive relaxed stability cutoff when dual-cutoff is enabled: "
            "elbow_log_score (second elbow in tail) or strict_multiplier."
        ),
    )
    stability_relaxed_multiplier: float = Field(
        default=0.5,
        gt=0.0,
        description=(
            "Multiplier applied to strict score threshold when "
            "stability_relaxed_cutoff_mode='strict_multiplier'."
        ),
    )
    stability_score_eps: float = Field(
        default=1e-12,
        gt=0.0,
        description="Small epsilon used in log(score + eps) elbow detection.",
    )
    stability_tiers_enabled: bool = Field(
        default=False,
        description=(
            "If true, write three tiered stability outputs under stability/tier_core, "
            "stability/tier_extended, stability/tier_exploratory."
        ),
    )
    stability_tier_core_freq: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Core tier threshold for frequency-based stability.",
    )
    stability_tier_extended_freq: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Extended tier threshold for frequency-based stability.",
    )
    stability_tier_exploratory_freq: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Exploratory tier threshold for frequency-based stability.",
    )
    stability_default_freeze_tier: Literal["core", "extended", "exploratory"] = Field(
        default="extended",
        description=(
            "Tier whose stable_dmps_production.csv is aliased to root stability/stable_dmps_production.csv "
            "for default --freeze behavior."
        ),
    )
    stability_featurecuts_enabled: bool = Field(
        default=False,
        description=(
            "If true, MC detector runs force classifier_dmp_selection=featurecuts_validation "
            "so stability can be computed from discriminatory classifier panels."
        ),
    )
    stability_target_balanced_accuracy: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Optional target BA for detector FeatureCuts: choose minimum top-k DMPs that reach this BA "
            "on detector validation splits."
        ),
    )
    stability_min_selected_dmps: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Optional lower bound for detector classifier panel size in FeatureCuts mode. "
            "Final selected k is max(featurecuts_k, stability_min_selected_dmps)."
        ),
    )
    run_mapper_and_enricher: bool = Field(
        default=False,
        description="If True, run methyl-mapper and methyl-enricher inside each MC iteration (optional; not used for --stability).",
    )
    skip_enricher: bool = Field(
        default=False,
        description="Skip methyl-enricher step even when run_mapper_and_enricher is true (useful when Grok API calls are too slow).",
    )
    freeze_stable_dmp_csv: Optional[str] = Field(
        default=None,
        description="Path to stable_dmps_production.csv for --freeze (default: monte_carlo_runs/stability/stable_dmps_production.csv).",
    )
    production_output_dir: Optional[str] = Field(
        default=None,
        description="Output directory for the final production run (defaults to monte_carlo_runs/production).",
    )
    predictor_only: bool = Field(
        default=False,
        description=(
            "If True, each iteration only runs methyl-predictor (no centroid/detector/classifier). "
            "Requires frozen_project_path (or default monte_carlo_runs/production/project.json) "
            "so model paths resolve to the frozen build."
        ),
    )
    frozen_project_path: Optional[str] = Field(
        default=None,
        description="project.json from --freeze production build; merged into each run for predictor_only mode.",
    )
    require_biological_review_for_model: bool = Field(
        default=False,
        description=(
            "If True, methyl-validation --model exits unless biological_review_confirmed is true "
            "(set in step_config.validation after expert review)."
        ),
    )
    biological_review_confirmed: bool = Field(
        default=False,
        description="After review, set True in step_config.validation to allow --model (classifier + predictor).",
    )
    model_backend: str = Field(
        default="ecdf",
        description=(
            "Backend for --model. "
            "'ecdf' runs methyl-classifier -> methyl-predictor (default). "
            "'tabular_sklearn' builds a ModelFeatureBundle and trains/evaluates a tabular sklearn model. "
            "'generative_hybrid' trains an encoder + class-conditional latent density model."
        ),
    )
    model_bundle_dir: Optional[str] = Field(
        default=None,
        description=(
            "Optional output directory for ModelFeatureBundle files. "
            "Default: <production_output_dir>/model_bundle."
        ),
    )
    model_weight_column: str = Field(
        default="weight",
        description=(
            "Preferred weight column from detector exports when building bundle DMP index. "
            "Falls back to effect_size or 1.0 when absent."
        ),
    )
    tabular_model_type: str = Field(
        default="random_forest",
        description=(
            "For model_backend=tabular_sklearn: "
            "random_forest | hist_gradient_boosting | logistic_regression | xgboost."
        ),
    )
    tabular_methods: Optional[List[TabularMethodConfig]] = Field(
        default=None,
        description=(
            "Optional ordered list of tabular methods with method-specific parameters. "
            "When absent, synthesized from tabular_model_type for backward compatibility."
        ),
    )
    tabular_method_selection_metric: str = Field(
        default="balanced_accuracy",
        description=(
            "When multiple tabular_methods are evaluated sequentially, select best method "
            "using this metric from validation_metrics."
        ),
    )
    tabular_method_selection_stat: str = Field(
        default="mean",
        description=(
            "Selection stat label for method ranking metadata (mean|median). "
            "Current per-run selection uses direct metric values."
        ),
    )
    tabular_max_dmps: int = Field(
        default=5000,
        ge=10,
        description="For model_backend=tabular_sklearn: cap number of DMP loci selected from bundle index.",
    )
    tabular_save_train_dataset: bool = Field(
        default=False,
        description=(
            "For model_backend=tabular_sklearn: if true, export the assembled training dataset "
            "(features + labels + sample_id) for reproducibility/auditing."
        ),
    )
    tabular_reuse_train_dataset: bool = Field(
        default=True,
        description=(
            "For model_backend=tabular_sklearn: when true and tabular_save_train_dataset is enabled, "
            "reuse a previously exported training dataset if its fingerprint matches current inputs."
        ),
    )
    tabular_train_dataset_path: Optional[str] = Field(
        default=None,
        description=(
            "Optional output file for exported tabular training dataset. "
            "When omitted and tabular_save_train_dataset=true, defaults to "
            "<model_bundle_dir>/tabular_train_dataset.parquet."
        ),
    )
    tabular_save_test_dataset: bool = Field(
        default=True,
        description=(
            "For model_backend=tabular_sklearn: when an explicit evaluation split is configured, "
            "export the assembled test/eval dataset."
        ),
    )
    tabular_test_dataset_path: Optional[str] = Field(
        default=None,
        description=(
            "Optional output file for exported tabular test/eval dataset. "
            "When omitted and tabular_save_test_dataset=true, defaults to the same directory as "
            "tabular_train_dataset_path with filename tabular_test_dataset.<ext> "
            "(or <model_bundle_dir>/tabular_test_dataset.parquet when train path is also omitted)."
        ),
    )
    feature_mode: str = Field(
        default="raw_dmp",
        description=(
            "Feature construction mode for tabular/generative backends: "
            "raw_dmp (legacy per-locus matrix with methylation fill) or "
            "observed_hybrid (observed-only aggregated features)."
        ),
    )
    observed_feature_quantiles: List[float] = Field(
        default_factory=lambda: [0.10, 0.25, 0.50, 0.75, 0.90],
        description=(
            "Quantiles used by observed_hybrid feature mode when summarizing observed methylation."
        ),
    )
    observed_feature_min_coverage: int = Field(
        default=1,
        ge=1,
        description="Minimum coverage passed to methyl extraction for observed_hybrid features.",
    )
    observed_feature_min_obs_fraction: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum observed-fraction evidence threshold for observed_hybrid predictions. "
            "Used for reporting/optional rejection in backend outputs."
        ),
    )
    observed_feature_include_dmp: bool = Field(
        default=True,
        description="Enable DMP-derived observed_hybrid features (global, quantiles, and disease comparison summaries).",
    )
    observed_feature_include_chromosome: bool = Field(
        default=True,
        description="Enable chromosome-level observed_hybrid summaries.",
    )
    observed_feature_include_dmr: bool = Field(
        default=True,
        description="Enable DMR/region-level observed_hybrid summaries.",
    )
    observed_feature_include_gene: bool = Field(
        default=True,
        description="Enable gene-level observed_hybrid summaries when gene metadata is available.",
    )
    observed_feature_dmr_window_bp: int = Field(
        default=100000,
        ge=1,
        description=(
            "Fallback DMR window size (bp) used to construct region identifiers when explicit DMR labels are missing."
        ),
    )
    observed_feature_max_dmrs: int = Field(
        default=32,
        ge=0,
        description="Maximum number of DMR regions retained in observed_hybrid schema (top-weighted).",
    )
    observed_feature_max_genes: int = Field(
        default=32,
        ge=0,
        description="Maximum number of genes retained in observed_hybrid schema (top-weighted).",
    )
    ecdf_second_stage_enabled: bool = Field(
        default=False,
        description=(
            "If true for model_backend=ecdf, train optional second-stage binary refiner "
            "using observed_hybrid features and append extra prediction columns."
        ),
    )
    covariates_path: Optional[str] = Field(
        default=None,
        description=(
            "Optional covariates sidecar (HDF5 preferred, CSV accepted). "
            "Rows should include sample identifier column for join with sample basename."
        ),
    )
    covariate_id_column: str = Field(
        default="sample_id",
        description="Column name in covariates table used to join with sample basename.",
    )
    covariate_numeric_columns: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional explicit numeric covariate columns. "
            "When omitted, numeric/categorical role is inferred."
        ),
    )
    covariate_ordinal_columns: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional explicit ordinal covariate columns (ordered categories such as low/medium/high). "
            "These are encoded as single numeric features using covariate_ordinal_maps or known defaults."
        ),
    )
    covariate_ordinal_maps: Optional[Dict[str, Dict[str, float]]] = Field(
        default=None,
        description=(
            "Optional mapping per ordinal column from raw level -> code, e.g. "
            "{'risk_band': {'low': 1, 'medium': 2, 'high': 3}}."
        ),
    )
    covariate_ordinal_unknown_value: float = Field(
        default=0.0,
        description=(
            "Fallback code used when an ordinal value is missing/unknown at train or inference time."
        ),
    )
    covariate_categorical_columns: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional explicit categorical covariate columns. "
            "Columns are one-hot encoded with frozen vocab."
        ),
    )
    covariate_missing_numeric_strategy: str = Field(
        default="mean",
        description="How numeric covariate NaNs are imputed: mean | median | zero.",
    )
    covariate_standardize_numeric: bool = Field(
        default=True,
        description="If true, z-score standardize numeric covariates using train-set statistics.",
    )
    covariates_strict_join: bool = Field(
        default=False,
        description=(
            "For covariate-aware tabular/generic paths: require every sample id to exist in "
            "covariates sidecar during train/predict."
        ),
    )
    generative_latent_dim: int = Field(
        default=16,
        ge=2,
        description="For model_backend=generative_hybrid: latent dimensionality.",
    )
    generative_kl_weight: float = Field(
        default=0.1,
        ge=0.0,
        description=(
            "For model_backend=generative_hybrid: KL-like regularization weight in hybrid loss/selection metadata."
        ),
    )
    generative_density_type: str = Field(
        default="diag_gaussian",
        description="For model_backend=generative_hybrid: latent class density family (currently diag_gaussian).",
    )
    generative_epochs: int = Field(
        default=50,
        ge=1,
        description="For model_backend=generative_hybrid: training epochs metadata/control.",
    )
    generative_batch_size: int = Field(
        default=64,
        ge=1,
        description="For model_backend=generative_hybrid: mini-batch size metadata/control.",
    )
    generative_seed: int = Field(
        default=13,
        description="For model_backend=generative_hybrid: random seed.",
    )
    generative_calibrate: bool = Field(
        default=False,
        description="For model_backend=generative_hybrid: enable probability calibration stage when available.",
    )
    generative_covariates_strict: bool = Field(
        default=True,
        description="For model_backend=generative_hybrid: require all sample IDs to exist in covariates sidecar when used.",
    )
    rollout_balanced_accuracy_drop_max: float = Field(
        default=0.005,
        ge=0.0,
        description="Dual-run promotion guard: max allowed BA drop vs baseline.",
    )
    rollout_macro_f1_drop_max: float = Field(
        default=0.005,
        ge=0.0,
        description="Dual-run promotion guard: max allowed macro-F1 drop vs baseline.",
    )
    rollout_nll_improvement_min_frac: float = Field(
        default=0.02,
        ge=0.0,
        description="Dual-run promotion target: minimum relative NLL improvement.",
    )
    rollout_brier_improvement_min_frac: float = Field(
        default=0.02,
        ge=0.0,
        description="Dual-run promotion target: minimum relative Brier improvement.",
    )
    rollout_ece_improvement_min_frac: float = Field(
        default=0.05,
        ge=0.0,
        description="Dual-run promotion target: minimum relative ECE improvement.",
    )

    # Support for step_config.validation when loading from a project JSON
    validation: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Validation/Monte Carlo settings when embedded in a project as step_config.validation.",
    )

    @model_validator(mode="before")
    @classmethod
    def _synthesize_cohorts_from_legacy(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if not data.get("tabular_methods"):
            mt = str(data.get("tabular_model_type") or "random_forest").strip().lower()
            data["tabular_methods"] = [{"method": mt, "params": {}}]
        cohorts = data.get("cohorts")
        if isinstance(cohorts, list) and len(cohorts) >= 2:
            return data
        if isinstance(cohorts, list) and len(cohorts) == 1:
            raise ValueError("cohorts must contain at least two entries")
        hc, dc = data.get("healthy_csv"), data.get("disease_csv")
        if hc and dc:
            data["cohorts"] = [
                {"label": "healthy", "csv": hc},
                {"label": "disease", "csv": dc},
            ]
        return data

    @model_validator(mode="after")
    def _require_cohorts(self) -> "MonteCarloConfig":
        if len(self.cohorts) < 2:
            raise ValueError(
                "Monte Carlo config needs at least two cohorts: set cohorts: [{label, csv}, ...] "
                "or legacy healthy_csv and disease_csv."
            )
        return self

    @model_validator(mode="after")
    def _require_tabular_methods(self) -> "MonteCarloConfig":
        if self.model_backend == "tabular_sklearn" and not self.tabular_methods:
            raise ValueError("tabular_methods must contain at least one entry")
        return self

    @field_validator("model_backend")
    @classmethod
    def _validate_model_backend(cls, value: str) -> str:
        allowed = {"ecdf", "tabular_sklearn", "generative_hybrid"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"model_backend must be one of {sorted(allowed)}")
        return normalized

    @field_validator("tabular_method_selection_metric")
    @classmethod
    def _validate_tabular_method_selection_metric(cls, value: str) -> str:
        allowed = {"balanced_accuracy", "accuracy", "macro_f1", "weighted_f1"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"tabular_method_selection_metric must be one of {sorted(allowed)}")
        return normalized

    @field_validator("tabular_method_selection_stat")
    @classmethod
    def _validate_tabular_method_selection_stat(cls, value: str) -> str:
        allowed = {"mean", "median"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"tabular_method_selection_stat must be one of {sorted(allowed)}")
        return normalized

    @field_validator("feature_mode")
    @classmethod
    def _validate_feature_mode(cls, value: str) -> str:
        allowed = {"raw_dmp", "observed_hybrid"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"feature_mode must be one of {sorted(allowed)}")
        return normalized

    @field_validator("observed_feature_quantiles")
    @classmethod
    def _validate_observed_feature_quantiles(cls, value: List[float]) -> List[float]:
        out: List[float] = []
        for q in value:
            fq = float(q)
            if 0.0 <= fq <= 1.0:
                out.append(fq)
        if not out:
            out = [0.5]
        return out

    @field_validator("generative_density_type")
    @classmethod
    def _validate_generative_density_type(cls, value: str) -> str:
        allowed = {"diag_gaussian"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"generative_density_type must be one of {sorted(allowed)}")
        return normalized

    @field_validator("covariate_missing_numeric_strategy")
    @classmethod
    def _validate_covariate_missing_numeric_strategy(cls, value: str) -> str:
        allowed = {"mean", "median", "zero"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"covariate_missing_numeric_strategy must be one of {sorted(allowed)}")
        return normalized

    @field_validator("covariate_ordinal_maps")
    @classmethod
    def _normalize_covariate_ordinal_maps(cls, value: Optional[Dict[str, Dict[str, float]]]) -> Optional[Dict[str, Dict[str, float]]]:
        if value is None:
            return None
        out: Dict[str, Dict[str, float]] = {}
        for col, mapping in value.items():
            c = str(col)
            if not isinstance(mapping, dict) or not mapping:
                raise ValueError(f"covariate_ordinal_maps[{c!r}] must be a non-empty object")
            out[c] = {str(k).strip().lower(): float(v) for k, v in mapping.items()}
        return out

    @model_validator(mode="after")
    def _validate_covariate_roles(self) -> "MonteCarloConfig":
        numeric = set(self.covariate_numeric_columns or [])
        ordinal = set(self.covariate_ordinal_columns or [])
        categorical = set(self.covariate_categorical_columns or [])
        overlap = (numeric & ordinal) | (numeric & categorical) | (ordinal & categorical)
        if overlap:
            raise ValueError(f"covariate role columns overlap across types: {sorted(overlap)}")
        if self.covariate_ordinal_maps:
            missing = sorted(set(self.covariate_ordinal_maps.keys()) - ordinal)
            if missing:
                raise ValueError(
                    "covariate_ordinal_maps has columns not listed in covariate_ordinal_columns: "
                    f"{missing}"
                )
        return self

    @model_validator(mode="after")
    def _validate_stability_tier_thresholds(self) -> "MonteCarloConfig":
        if self.stability_tiers_enabled:
            if not (
                self.stability_tier_core_freq
                >= self.stability_tier_extended_freq
                >= self.stability_tier_exploratory_freq
            ):
                raise ValueError(
                    "stability tiers require core >= extended >= exploratory frequency thresholds."
                )
        return self

    @property
    def n_cohorts(self) -> int:
        return len(self.cohorts)

    @property
    def is_binary_cohort_layout(self) -> bool:
        """True when exactly two cohorts (legacy binary MC path)."""
        return self.n_cohorts == 2

    @classmethod
    def from_json_file(cls, path: str | Path) -> "MonteCarloConfig":
        import json

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)


def assert_production_model_build_allowed(config: MonteCarloConfig) -> None:
    """Raise ValueError if --model is blocked pending biological review."""
    if config.require_biological_review_for_model and not config.biological_review_confirmed:
        raise ValueError(
            "Production model build is blocked: set step_config.validation.biological_review_confirmed "
            "to true after biological review, or set require_biological_review_for_model to false."
        )

