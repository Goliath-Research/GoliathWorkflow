"""
Runner config schema for Monte Carlo validation.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class CohortCsv(BaseModel):
    """One cohort: display label (must match base project flat ``groups`` labels for K>2) and sample list CSV."""

    label: str = Field(
        ...,
        min_length=1,
        description="Cohort label: for hierarchical MC must match get_resolved_groups() (e.g. all, pca_pca1).",
    )
    csv: str = Field(..., min_length=1, description="Path to CSV of samples (same format as healthy_csv).")


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
        description="For model_backend=tabular_sklearn: random_forest | hist_gradient_boosting | logistic_regression.",
    )
    tabular_max_dmps: int = Field(
        default=5000,
        ge=10,
        description="For model_backend=tabular_sklearn: cap number of DMP loci selected from bundle index.",
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

    @field_validator("model_backend")
    @classmethod
    def _validate_model_backend(cls, value: str) -> str:
        allowed = {"ecdf", "tabular_sklearn", "generative_hybrid"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"model_backend must be one of {sorted(allowed)}")
        return normalized

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

