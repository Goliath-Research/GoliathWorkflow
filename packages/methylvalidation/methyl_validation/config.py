"""
Runner config schema for Monte Carlo validation.
"""

from pathlib import Path
from typing import Annotated, Any, ClassVar, Dict, FrozenSet, List, Literal, Optional, Type, Union, cast, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator, model_validator
from pydantic_core import PydanticUndefined


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

DEFAULT_MAPPER_GENE_COLUMNS: List[str] = [
    "gene_importance",
    "gene_effect_signed_wsum",
    "gene_direction",
    "gene_effect_abs_wsum",
    "gene_support_n",
    "gene_score",
    "mean_effect_size",
    "gene_effect_compound",
    "gene_feature_effect_compound",
]


class BackendSharedParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_bundle_dir: Optional[str] = Field(default=None)
    model_weight_column: str = Field(default="effect_size")
    tabular_max_dmps: Optional[int] = Field(
        default=None,
        ge=0,
        description="Optional cap for loci retained from model bundle. null/0 means keep all stable DMPs.",
    )

    feature_mode: str = Field(default="raw_dmp")
    feature_family_set: str = Field(default="dmp_scored")
    gene_feature_loading: str = Field(
        default="frozen",
        description=(
            "For observed_hybrid gene-family features: "
            "frozen (use only frozen DMP loci) or range (expand to all loci inside frozen gene-feature ranges)."
        ),
    )
    mapper_gene_columns: List[str] = Field(default_factory=lambda: list(DEFAULT_MAPPER_GENE_COLUMNS))
    observed_feature_quantiles: List[float] = Field(default_factory=lambda: [0.10, 0.25, 0.50, 0.75, 0.90])
    observed_feature_min_coverage: int = Field(default=1, ge=1)
    observed_feature_min_obs_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    observed_feature_include_dmp: bool = Field(default=True)
    observed_feature_include_chromosome: bool = Field(default=True)
    observed_feature_include_dmr: bool = Field(default=True)
    observed_feature_include_gene: bool = Field(default=True)
    observed_feature_dmr_window_bp: int = Field(default=100000, ge=1)
    observed_feature_max_dmrs: int = Field(default=32, ge=0)
    observed_feature_max_genes: int = Field(default=32, ge=0)
    observed_hist_eps: float = Field(default=1e-6, gt=0.0)
    observed_hist_alpha: float = Field(default=0.5, ge=0.0)
    observed_hist_evidence_clip_cap: float = Field(default=5.0, ge=0.0)
    observed_hist_tail_agreement_threshold: float = Field(default=0.10, ge=0.0, le=1.0)
    gene_scored_min_support_n: int = Field(
        default=2,
        ge=1,
        description=(
            "Minimum gene_support_n for a gene to enter the gene_scored comparison panel "
            "(feature_family_set gene_scored or dmp_scored+gene_scored)."
        ),
    )
    gene_scored_use_region_weight: bool = Field(
        default=True,
        description="Multiply per-locus weights by region_weight when building gene_directional_score features.",
    )
    gene_scored_gene_weight: str = Field(
        default="importance_x_sqrt_support",
        description=(
            "Gene-level weighting when pooling to gene_directional_score: "
            "importance_x_sqrt_support or importance_only."
        ),
    )
    gene_scored_ordered_comparison_labels: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional override for gene_scored progression order. When null, order is taken from "
            "step_config.progression.ordered_comparison_labels or project get_ordered_comparison_labels()."
        ),
    )
    gene_scored_contrast_pairs: Optional[List[List[str]]] = Field(
        default=None,
        description=(
            "Optional extra directional contrast pairs [[left, right], ...]; emits "
            "gene_directional_contrast__{left}__{right} = score(right)-score(left). "
            "Auto extreme pair added when K>=2 unless already listed."
        ),
    )
    structural_scored_min_support_n: int = Field(
        default=2,
        ge=1,
        description=(
            "Minimum n_dmps_in_feature for a gene-feature row to enter the structural_scored panel "
            "(feature_family_set structural_scored or dmp_scored+structural_scored)."
        ),
    )
    structural_scored_use_region_weight: bool = Field(
        default=True,
        description="Multiply per-locus weights by region_weight when building structural_directional_score features.",
    )
    structural_scored_weight: str = Field(
        default="compound_x_sqrt_support",
        description=(
            "Gene-feature weighting when pooling to structural_directional_score: "
            "compound_x_sqrt_support or compound_only."
        ),
    )
    structural_scored_ordered_comparison_labels: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional override for structural_scored progression order. When null, order is taken from "
            "step_config.progression.ordered_comparison_labels or project get_ordered_comparison_labels()."
        ),
    )
    structural_scored_contrast_pairs: Optional[List[List[str]]] = Field(
        default=None,
        description=(
            "Optional extra directional contrast pairs [[left, right], ...] per region type; emits "
            "structural_directional_contrast__{left}__{right}__{region}. "
            "Auto extreme pair added when K>=2 unless already listed."
        ),
    )
    region_directional_region_types: List[str] = Field(
        default_factory=lambda: ["promoter", "exon", "intron", "gene_body", "terminator"],
        description=(
            "Structural region types considered when building structural_scored features "
            "(feature_family_set structural_scored or dmp_scored+structural_scored)."
        ),
    )
    region_directional_min_loci: int = Field(
        default=1,
        ge=1,
        description=(
            "Minimum panel loci in the classifier DMP index required to emit structural_scored "
            "columns for a (comparison, region) pair."
        ),
    )
    mapper_annotation_collapse_mode: str = Field(
        default="priority",
        description=(
            "How to collapse multi-feature mapper intersections to one row per locus in "
            "mapper_dmp_annotations.csv: priority (promoter>exon>intron>gene_body>terminator) "
            "or weight (legacy highest combined_weight wins)."
        ),
    )
    mapper_annotation_unknown_fallback: Optional[str] = Field(
        default="gene_body",
        description=(
            "Parent feature bucket assigned to classifier loci with unknown or missing "
            "feature_type after mapper merge. Set null to leave unknown loci uncovered."
        ),
    )
    observed_feature_quality_columns: List[str] = Field(
        default_factory=lambda: ["obs_fraction", "n_obs_dmps", "n_total_dmps"],
        description=(
            "Observed-hybrid columns computed and exported but excluded from model training."
        ),
    )

    covariates_path: Optional[str] = Field(default=None)
    covariate_id_column: str = Field(default="sample_id")
    covariate_numeric_columns: Optional[List[str]] = Field(default=None)
    covariate_ordinal_columns: Optional[List[str]] = Field(default=None)
    covariate_ordinal_maps: Optional[Dict[str, Dict[str, float]]] = Field(default=None)
    covariate_ordinal_unknown_value: float = Field(default=0.0)
    covariate_categorical_columns: Optional[List[str]] = Field(default=None)
    covariate_missing_numeric_strategy: str = Field(default="mean")
    covariate_standardize_numeric: bool = Field(default=True)
    covariates_strict_join: bool = Field(default=False)

    @field_validator("feature_mode")
    @classmethod
    def _validate_feature_mode(cls, value: str) -> str:
        allowed = {"raw_dmp", "raw_gene", "observed_hybrid"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"feature_mode must be one of {sorted(allowed)}")
        return normalized

    @field_validator("feature_family_set")
    @classmethod
    def _validate_feature_family_set(cls, value: str) -> str:
        from .observed_feature_builder import normalize_feature_family_set

        return normalize_feature_family_set(value)

    @field_validator("gene_feature_loading")
    @classmethod
    def _validate_gene_feature_loading(cls, value: str) -> str:
        allowed = {"frozen", "range"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"gene_feature_loading must be one of {sorted(allowed)}")
        return normalized

    @field_validator("gene_scored_gene_weight")
    @classmethod
    def _validate_gene_scored_gene_weight_profile(cls, value: str) -> str:
        allowed = {"importance_x_sqrt_support", "importance_only"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"gene_scored_gene_weight must be one of {sorted(allowed)}")
        return normalized

    @field_validator("gene_scored_contrast_pairs")
    @classmethod
    def _validate_gene_scored_contrast_pairs_profile(
        cls, value: Optional[List[List[str]]]
    ) -> Optional[List[List[str]]]:
        if value is None:
            return None
        from .gene_scored_features import normalize_gene_scored_contrast_pairs

        return [[left, right] for left, right in normalize_gene_scored_contrast_pairs(value)]

    @field_validator("structural_scored_weight")
    @classmethod
    def _validate_structural_scored_weight(cls, value: str) -> str:
        allowed = {"compound_x_sqrt_support", "compound_only"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"structural_scored_weight must be one of {sorted(allowed)}")
        return normalized

    @field_validator("structural_scored_contrast_pairs")
    @classmethod
    def _validate_structural_scored_contrast_pairs(
        cls, value: Optional[List[List[str]]]
    ) -> Optional[List[List[str]]]:
        if value is None:
            return None
        from .structural_scored_features import normalize_structural_scored_contrast_pairs

        return [[left, right] for left, right in normalize_structural_scored_contrast_pairs(value)]

    @field_validator("region_directional_region_types")
    @classmethod
    def _validate_region_directional_region_types(cls, value: List[str]) -> List[str]:
        from .gene_scored_features import DEFAULT_REGION_DIRECTIONAL_TYPES, _normalize_structural_feature

        if not value:
            return list(DEFAULT_REGION_DIRECTIONAL_TYPES)
        out: List[str] = []
        for raw in value:
            token = _normalize_structural_feature(raw)
            if token == "unknown":
                raise ValueError(f"Unknown region_directional_region_type: {raw!r}")
            if token not in out:
                out.append(token)
        if not out:
            raise ValueError("region_directional_region_types cannot be empty")
        return out

    @field_validator("mapper_annotation_collapse_mode")
    @classmethod
    def _validate_mapper_annotation_collapse_mode(cls, value: str) -> str:
        token = str(value or "priority").strip().lower()
        if token not in {"priority", "weight"}:
            raise ValueError("mapper_annotation_collapse_mode must be 'priority' or 'weight'")
        return token

    @field_validator("mapper_annotation_unknown_fallback")
    @classmethod
    def _validate_mapper_annotation_unknown_fallback(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        from .gene_scored_features import _normalize_structural_feature

        token = _normalize_structural_feature(value)
        if token == "unknown":
            raise ValueError(f"Invalid mapper_annotation_unknown_fallback: {value!r}")
        return token

    @field_validator("mapper_gene_columns")
    @classmethod
    def _validate_mapper_gene_columns(cls, value: List[str]) -> List[str]:
        cleaned: List[str] = []
        seen: set[str] = set()
        for raw in value:
            token = str(raw).strip()
            if not token:
                continue
            if token in seen:
                continue
            seen.add(token)
            cleaned.append(token)
        return cleaned

    @field_validator("observed_feature_quantiles")
    @classmethod
    def _validate_observed_feature_quantiles(cls, value: List[float]) -> List[float]:
        out: List[float] = []
        for q in value:
            fq = float(q)
            if 0.0 <= fq <= 1.0:
                out.append(fq)
        return out or [0.5]

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
    def _normalize_covariate_ordinal_maps(
        cls, value: Optional[Dict[str, Dict[str, float]]]
    ) -> Optional[Dict[str, Dict[str, float]]]:
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
    def _validate_covariate_roles(self) -> "BackendSharedParams":
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


class EcdfBackendParams(BackendSharedParams):
    model_config = ConfigDict(extra="forbid")
    ecdf_second_stage_enabled: bool = Field(default=False)
    ecdf_aggregated_enabled: Optional[bool] = Field(
        default=None,
        description=(
            "When true, train/use aggregated observed-hybrid ECDF OvR package (experimental). "
            "When null/false, aggregated mode is disabled."
        ),
    )
    ecdf_aggregated_n_bins: int = Field(
        default=100,
        ge=8,
        le=512,
        description="Histogram bin count per feature for aggregated ECDF heads.",
    )


class TabularBackendParams(BackendSharedParams):
    model_config = ConfigDict(extra="forbid")
    tabular_model_type: str = Field(default="random_forest")
    tabular_methods: List[TabularMethodConfig] = Field(
        default_factory=lambda: cast(
            List[TabularMethodConfig],
            [RandomForestMethodConfig(method="random_forest")],
        )
    )
    tabular_method_selection_metric: str = Field(default="balanced_accuracy")
    tabular_method_selection_stat: str = Field(default="mean")
    tabular_save_train_dataset: bool = Field(default=True)
    tabular_reuse_train_dataset: bool = Field(default=True)
    tabular_train_dataset_path: Optional[str] = Field(default=None)
    tabular_save_test_dataset: bool = Field(default=True)
    tabular_test_dataset_path: Optional[str] = Field(default=None)

    @field_validator("tabular_methods")
    @classmethod
    def _validate_non_empty_methods(cls, value: List[TabularMethodConfig]) -> List[TabularMethodConfig]:
        if not value:
            raise ValueError("tabular_methods must contain at least one entry")
        return value

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


class GenerativeBackendParams(BackendSharedParams):
    model_config = ConfigDict(extra="forbid")
    generative_latent_dim: int = Field(default=16, ge=2)
    generative_kl_weight: float = Field(default=0.1, ge=0.0)
    generative_density_type: str = Field(default="diag_gaussian")
    generative_epochs: int = Field(default=50, ge=1)
    generative_batch_size: int = Field(default=64, ge=1)
    generative_seed: int = Field(default=13)
    generative_calibrate: bool = Field(default=False)
    generative_covariates_strict: bool = Field(default=True)

    @field_validator("generative_density_type")
    @classmethod
    def _validate_generative_density_type(cls, value: str) -> str:
        allowed = {"diag_gaussian"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"generative_density_type must be one of {sorted(allowed)}")
        return normalized


class EcdfBackendProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(default=True)
    params: EcdfBackendParams = Field(default_factory=EcdfBackendParams)


class TabularBackendProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(default=False)
    params: TabularBackendParams = Field(default_factory=TabularBackendParams)


class GenerativeBackendProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(default=False)
    params: GenerativeBackendParams = Field(default_factory=GenerativeBackendParams)


class BackendProfilesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ecdf: EcdfBackendProfile = Field(default_factory=EcdfBackendProfile)
    tabular_sklearn: TabularBackendProfile = Field(default_factory=TabularBackendProfile)
    generative_hybrid: GenerativeBackendProfile = Field(default_factory=GenerativeBackendProfile)


class ValidationPartitionContract(BaseModel):
    """Named dataset partitions for lifecycle-stage evidence contracts."""

    model_config = ConfigDict(extra="forbid")

    development_train: List[str] = Field(
        default_factory=list,
        description="Sample paths for model development/training partition.",
    )
    internal_validation: List[str] = Field(
        default_factory=list,
        description="Sample paths for internal model selection/validation partition.",
    )
    locked_test: List[str] = Field(
        default_factory=list,
        description="Sample paths reserved as locked test (never used for tuning).",
    )
    pivotal_validation: List[str] = Field(
        default_factory=list,
        description="Sample paths reserved for pivotal/clinical validation.",
    )
    post_market_monitoring: List[str] = Field(
        default_factory=list,
        description="Optional sample paths used for post-market monitoring analyses.",
    )
    independence_keys: List[str] = Field(
        default_factory=lambda: ["sample_id"],
        description=(
            "Metadata keys that must remain independent across partitions when available "
            "(e.g., sample_id, patient_id, site_id, batch)."
        ),
    )

    @model_validator(mode="after")
    def _validate_no_cross_partition_overlap(self) -> "ValidationPartitionContract":
        role_to_ids: Dict[str, set[str]] = {}
        for role in (
            "development_train",
            "internal_validation",
            "locked_test",
            "pivotal_validation",
            "post_market_monitoring",
        ):
            vals = getattr(self, role, []) or []
            role_to_ids[role] = {str(Path(v).name) for v in vals if str(v).strip()}
        overlaps: List[str] = []
        roles = list(role_to_ids.keys())
        for i in range(len(roles)):
            for j in range(i + 1, len(roles)):
                a, b = roles[i], roles[j]
                inter = sorted(role_to_ids[a] & role_to_ids[b])
                if inter:
                    overlaps.append(f"{a}∩{b}={inter[:5]}")
        if overlaps:
            raise ValueError(
                "validation_partitions contain overlapping sample IDs across named partitions: "
                + "; ".join(overlaps)
            )
        return self


class RegulatoryLifecycleConfig(BaseModel):
    """Explicit product-lifecycle framing and claim boundary metadata."""

    model_config = ConfigDict(extra="forbid")

    stage: str = Field(
        default="feasibility",
        description="Current product lifecycle stage for evidence framing.",
    )
    intended_use_summary: Optional[str] = Field(
        default=None,
        description="Short intended-use statement for reports.",
    )
    target_population: Optional[str] = Field(default=None)
    sample_type: Optional[str] = Field(default=None)
    primary_analyte: Optional[str] = Field(
        default=None,
        description=(
            "Primary biological analyte for interpretation framing "
            "(e.g., buffy_coat, cfdna, combined)."
        ),
    )
    model_training_analyte: Optional[str] = Field(
        default=None,
        description=(
            "Analyte matrix used for stability/freeze/classifier training on this project. "
            "Defaults to primary_analyte when omitted. Set to cfdna for plasma/cfDNA retrain paths."
        ),
    )
    reference_standard: Optional[str] = Field(default=None)
    claim_boundary: Optional[str] = Field(
        default=None,
        description=(
            "Explicit statement of allowed claims at this stage "
            "(e.g. feasibility-only, no final clinical claims)."
        ),
    )
    allow_clinical_performance_claims: bool = Field(
        default=False,
        description="Whether FDA-facing clinical performance claims are allowed at this stage.",
    )
    auto_apply_analyte_profile: Optional[bool] = Field(
        default=None,
        description=(
            "When true (default when primary_analyte is set), merge analyte-specific "
            "step_config defaults (fragmentomics, CIS-BP, bisulfite QC, etc.). Set false to opt out."
        ),
    )

    @model_validator(mode="after")
    def _validate_stage_claim_alignment(self) -> "RegulatoryLifecycleConfig":
        allowed_stages = {
            "feasibility",
            "expanded_development",
            "internal_validation",
            "model_freeze",
            "pivotal_validation",
            "fda_submission",
            "post_market",
        }
        stage = str(self.stage).strip().lower()
        if stage not in allowed_stages:
            raise ValueError(f"regulatory.stage must be one of {sorted(allowed_stages)}")
        self.stage = stage
        if stage in {"feasibility", "expanded_development", "internal_validation", "model_freeze"}:
            if self.allow_clinical_performance_claims:
                raise ValueError(
                    "allow_clinical_performance_claims=true is not allowed before pivotal_validation stage."
                )
        return self

    @field_validator("primary_analyte", "model_training_analyte")
    @classmethod
    def _normalize_primary_analyte(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = "_".join(value.strip().lower().replace("-", " ").split())
        if cleaned in {"plasma", "plasma_cfdna", "cf_dna", "cell_free_dna"}:
            return "cfdna"
        return cleaned or None


class MonteCarloConfig(BaseModel):
    """Configuration for the Monte Carlo validation runner (binary K=2 or multiclass K>=2)."""

    model_config = ConfigDict(extra="forbid")

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
    regulatory: RegulatoryLifecycleConfig = Field(
        default_factory=RegulatoryLifecycleConfig,
        description="Lifecycle-stage framing and claim-boundary metadata for FDA-oriented reporting.",
    )
    validation_partitions: Optional[ValidationPartitionContract] = Field(
        default=None,
        description="Optional named partition contract (development/internal/locked/pivotal/post-market).",
    )
    subgroup_columns: List[str] = Field(
        default_factory=list,
        description=(
            "Optional metadata columns for subgroup reporting in clinical performance reports "
            "(e.g., sex, age_bin, site_id, race_ethnicity)."
        ),
    )
    min_sensitivity_lcb: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional minimum lower confidence bound acceptance criterion for sensitivity.",
    )
    min_specificity_lcb: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional minimum lower confidence bound acceptance criterion for specificity.",
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
    stability_early_stop_enabled: bool = Field(
        default=False,
        description=(
            "If true, evaluate convergence of stable DMP panels during the MC loop "
            "and stop early when convergence thresholds hold for the configured patience."
        ),
    )
    stability_min_iterations: int = Field(
        default=20,
        ge=1,
        description=(
            "Minimum number of qualifying runs required before stability convergence checks can trigger."
        ),
    )
    stability_convergence_window: int = Field(
        default=5,
        ge=1,
        description=(
            "Window size (in qualifying runs) for comparing stable panels S_k vs S_(k-window)."
        ),
    )
    stability_convergence_jaccard: float = Field(
        default=0.98,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum Jaccard similarity required between current and lagged stable DMP panels."
        ),
    )
    stability_convergence_max_size_delta: float = Field(
        default=0.02,
        ge=0.0,
        le=1.0,
        description=(
            "Maximum allowed relative panel-size change between current and lagged stable DMP panels."
        ),
    )
    stability_convergence_patience: int = Field(
        default=3,
        ge=1,
        description=(
            "Number of consecutive convergence checkpoints that must pass before stopping early."
        ),
    )
    stability_gene_freq: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum frequency for a gene to be considered stable. "
            "When stability_gene_featurecuts_enabled, counts genes from per-run classifier gene panels."
        ),
    )
    stability_gene_featurecuts_enabled: bool = Field(
        default=False,
        description=(
            "If true, each MC iteration runs methyl-mapper then gene FeatureCuts (ECDF OvR k-search) "
            "after detector, and stability aggregates stable genes from genes-classifier exports."
        ),
    )
    stability_min_selected_genes: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Optional lower bound for gene classifier panel size in gene FeatureCuts mode. "
            "Final selected k is max(featurecuts_k, stability_min_selected_genes)."
        ),
    )
    stability_gene_featurecuts_max_dmps: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Optional genome-wide cap on classifier DMP loci used for MC gene FeatureCuts "
            "(after deduplication). When unset, all FeatureCuts classifier exports are used "
            "(typically ~min_selected_dmps per chromosome × number of chromosomes)."
        ),
    )
    freeze_stable_gene_csv: Optional[str] = Field(
        default=None,
        description=(
            "Path to stable_genes_production.csv for freeze gene-axis wiring "
            "(default: monte_carlo_runs/stability/stable_genes_production.csv when present)."
        ),
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
            "Deprecated alias for stability_min_core_dmps when that field is unset. "
            "Does not widen mapper exports; use stability_classifier_export_margin_* instead."
        ),
    )
    stability_min_core_dmps: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Optional small guardrail on detector k_core during MC FeatureCuts "
            "(passed to detector min_core_dmps)."
        ),
    )
    stability_classifier_export_margin_pct: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="MC detector override: extended classifier CSV margin as a fraction above k_core.",
    )
    stability_classifier_export_margin_abs: Optional[int] = Field(
        default=None,
        ge=0,
        description="MC detector override: extra top-ranked DMPs in extended classifier CSV beyond k_core.",
    )
    stability_classifier_export_max_dmps: Optional[int] = Field(
        default=None,
        ge=1,
        description="MC detector override: per-chromosome cap on extended classifier CSV size.",
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
    freeze_min_dmps_per_feature: int = Field(
        default=1,
        ge=1,
        description=(
            "Minimum number of unique frozen DMPs required for a gene-feature segment "
            "to be included in freeze-time fixed_gene_features output."
        ),
    )
    freeze_gene_importance_min: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=(
            "Optional lower bound on gene_importance when building freeze-time fixed_gene_panel."
        ),
    )
    freeze_top_genes: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Optional cap per comparison for top-ranked genes in freeze-time fixed_gene_panel."
        ),
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
    require_complete_enricher: bool = Field(
        default=False,
        description=(
            "If True, readiness audit treats incomplete enricher_completeness.json as no_go "
            "(not only a warning)."
        ),
    )
    enforce_training_analyte_match: bool = Field(
        default=False,
        description=(
            "If True, --model fails when step_config.validation.regulatory training analyte "
            "does not match locked_model_spec.json (blocks buffy-trained model on cfDNA projects)."
        ),
    )
    backend_profiles: BackendProfilesConfig = Field(
        default_factory=BackendProfilesConfig,
        description=(
            "Typed backend profile registry. Runtime backend config is resolved exclusively from this field."
        ),
    )
    model_backend: str = Field(
        default="ecdf",
        description=(
            "Runtime backend selector used by CLI mode execution. "
            "Project JSON must not define this key directly; use backend_profiles + CLI override semantics."
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
        default="effect_size",
        description=(
            "Legacy compatibility field. Model bundle weighting is canonicalized to detector "
            "effect_size for tabular/generative backends."
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
    tabular_max_dmps: Optional[int] = Field(
        default=None,
        ge=0,
        description=(
            "For model_backend=tabular_sklearn: optional cap on number of loci selected from bundle index. "
            "Set null or 0 to keep all stable DMPs."
        ),
    )
    tabular_save_train_dataset: bool = Field(
        default=True,
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
    feature_family_set: str = Field(
        default="dmp_scored",
        description=(
            "For feature_mode=observed_hybrid, controls active feature families: "
            "dmp_scored | gene | structural | gene_scored | dmp_scored+gene | "
            "dmp_scored+structural | dmp_scored+gene_scored | hybrid-all. "
            "Legacy aliases (dmp, dmp+gene_scored, etc.) are accepted and normalized."
        ),
    )
    gene_feature_loading: str = Field(
        default="frozen",
        description=(
            "For feature_mode=observed_hybrid with gene family features, controls locus loading: "
            "frozen (exact frozen DMP loci) or range (all loci in frozen gene-feature ranges)."
        ),
    )
    mapper_gene_columns: List[str] = Field(
        default_factory=lambda: list(DEFAULT_MAPPER_GENE_COLUMNS),
        description=(
            "Per-gene columns to carry from mapper all-gene_name-combined.csv into "
            "mapper_dmp_annotations.csv and model bundle mapped-locus rows. "
            "Set [] to disable this join."
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
    observed_hist_eps: float = Field(
        default=1e-6,
        gt=0.0,
        description="Observed-hybrid histogram ECDF epsilon for boundary clamp and log safety.",
    )
    observed_hist_alpha: float = Field(
        default=0.5,
        ge=0.0,
        description="Observed-hybrid histogram additive smoothing alpha applied to bin counts.",
    )
    observed_hist_evidence_clip_cap: float = Field(
        default=5.0,
        ge=0.0,
        description="Observed-hybrid cap for per-locus tail/outlier evidence prior to weighted averaging.",
    )
    observed_hist_tail_agreement_threshold: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Observed-hybrid threshold for cancer-direction tail agreement indicator.",
    )
    gene_scored_min_support_n: int = Field(
        default=2,
        ge=1,
        description=(
            "Minimum gene_support_n for a gene to enter the gene_scored comparison panel "
            "(feature_family_set gene_scored or dmp_scored+gene_scored)."
        ),
    )
    gene_scored_use_region_weight: bool = Field(
        default=True,
        description="Multiply per-locus weights by region_weight when building gene_directional_score features.",
    )
    gene_scored_gene_weight: str = Field(
        default="importance_x_sqrt_support",
        description=(
            "Gene-level weighting when pooling to gene_directional_score: "
            "importance_x_sqrt_support or importance_only."
        ),
    )
    gene_scored_ordered_comparison_labels: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional override for gene_scored progression order. When null, order is taken from "
            "step_config.progression.ordered_comparison_labels or project get_ordered_comparison_labels()."
        ),
    )
    gene_scored_contrast_pairs: Optional[List[List[str]]] = Field(
        default=None,
        description=(
            "Optional extra directional contrast pairs [[left, right], ...]; emits "
            "gene_directional_contrast__{left}__{right} = score(right)-score(left). "
            "Auto extreme pair added when K>=2 unless already listed."
        ),
    )
    structural_scored_min_support_n: int = Field(
        default=2,
        ge=1,
        description=(
            "Minimum n_dmps_in_feature for a gene-feature row to enter the structural_scored panel "
            "(feature_family_set structural_scored or dmp_scored+structural_scored)."
        ),
    )
    structural_scored_use_region_weight: bool = Field(
        default=True,
        description="Multiply per-locus weights by region_weight when building structural_directional_score features.",
    )
    structural_scored_weight: str = Field(
        default="compound_x_sqrt_support",
        description=(
            "Gene-feature weighting when pooling to structural_directional_score: "
            "compound_x_sqrt_support or compound_only."
        ),
    )
    structural_scored_ordered_comparison_labels: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional override for structural_scored progression order. When null, order is taken from "
            "step_config.progression.ordered_comparison_labels or project get_ordered_comparison_labels()."
        ),
    )
    structural_scored_contrast_pairs: Optional[List[List[str]]] = Field(
        default=None,
        description=(
            "Optional extra directional contrast pairs [[left, right], ...] per region type; emits "
            "structural_directional_contrast__{left}__{right}__{region}. "
            "Auto extreme pair added when K>=2 unless already listed."
        ),
    )
    region_directional_region_types: List[str] = Field(
        default_factory=lambda: ["promoter", "exon", "intron", "gene_body", "terminator"],
        description=(
            "Structural region types considered when building structural_scored features "
            "(feature_family_set structural_scored or dmp_scored+structural_scored)."
        ),
    )
    region_directional_min_loci: int = Field(
        default=1,
        ge=1,
        description=(
            "Minimum panel loci in the classifier DMP index required to emit structural_scored "
            "columns for a (comparison, region) pair."
        ),
    )
    mapper_annotation_collapse_mode: str = Field(
        default="priority",
        description=(
            "How to collapse multi-feature mapper intersections to one row per locus in "
            "mapper_dmp_annotations.csv: priority (promoter>exon>intron>gene_body>terminator) "
            "or weight (legacy highest combined_weight wins)."
        ),
    )
    mapper_annotation_unknown_fallback: Optional[str] = Field(
        default="gene_body",
        description=(
            "Parent feature bucket assigned to classifier loci with unknown or missing "
            "feature_type after mapper merge. Set null to leave unknown loci uncovered."
        ),
    )
    observed_feature_quality_columns: List[str] = Field(
        default_factory=lambda: ["obs_fraction", "n_obs_dmps", "n_total_dmps"],
        description=(
            "Observed-hybrid columns computed and exported but excluded from model training."
        ),
    )
    ecdf_second_stage_enabled: bool = Field(
        default=False,
        description=(
            "If true for model_backend=ecdf, train optional second-stage binary refiner "
            "using observed_hybrid features and append extra prediction columns."
        ),
    )
    ecdf_aggregated_enabled: Optional[bool] = Field(
        default=None,
        description=(
            "If set for model_backend=ecdf, force enable/disable aggregated observed-hybrid ECDF OvR. "
            "When null/false, aggregated mode is disabled (use raw_dmp or raw_gene instead)."
        ),
    )
    ecdf_aggregated_n_bins: int = Field(
        default=100,
        ge=8,
        le=512,
        description="Histogram bin count per feature for aggregated ECDF OvR heads.",
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

    _LEGACY_BACKEND_KEYS: ClassVar[FrozenSet[str]] = frozenset(
        {
            "model_backend",
            "model_bundle_dir",
            "model_weight_column",
            "tabular_model_type",
            "tabular_methods",
            "tabular_method_selection_metric",
            "tabular_method_selection_stat",
            "tabular_max_dmps",
            "tabular_save_train_dataset",
            "tabular_reuse_train_dataset",
            "tabular_train_dataset_path",
            "tabular_save_test_dataset",
            "tabular_test_dataset_path",
            "feature_mode",
            "feature_family_set",
            "gene_feature_loading",
            "mapper_gene_columns",
            "observed_feature_quantiles",
            "observed_feature_min_coverage",
            "observed_feature_min_obs_fraction",
            "observed_feature_include_dmp",
            "observed_feature_include_chromosome",
            "observed_feature_include_dmr",
            "observed_feature_include_gene",
            "observed_feature_dmr_window_bp",
            "observed_feature_max_dmrs",
            "observed_feature_max_genes",
            "observed_hist_eps",
            "observed_hist_alpha",
            "observed_hist_evidence_clip_cap",
            "observed_hist_tail_agreement_threshold",
            "gene_scored_min_support_n",
            "gene_scored_use_region_weight",
            "gene_scored_gene_weight",
            "gene_scored_ordered_comparison_labels",
            "gene_scored_contrast_pairs",
            "structural_scored_min_support_n",
            "structural_scored_use_region_weight",
            "structural_scored_weight",
            "structural_scored_ordered_comparison_labels",
            "structural_scored_contrast_pairs",
            "region_directional_region_types",
            "region_directional_min_loci",
            "mapper_annotation_collapse_mode",
            "mapper_annotation_unknown_fallback",
            "observed_feature_quality_columns",
            "ecdf_second_stage_enabled",
            "covariates_path",
            "covariate_id_column",
            "covariate_numeric_columns",
            "covariate_ordinal_columns",
            "covariate_ordinal_maps",
            "covariate_ordinal_unknown_value",
            "covariate_categorical_columns",
            "covariate_missing_numeric_strategy",
            "covariate_standardize_numeric",
            "covariates_strict_join",
            "generative_latent_dim",
            "generative_kl_weight",
            "generative_density_type",
            "generative_epochs",
            "generative_batch_size",
            "generative_seed",
            "generative_calibrate",
            "generative_covariates_strict",
        }
    )

    @model_validator(mode="before")
    @classmethod
    def _synthesize_cohorts_from_legacy(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        legacy_backend_keys = sorted(k for k in cls._LEGACY_BACKEND_KEYS if k in data)
        if legacy_backend_keys:
            raise ValueError(
                "Legacy backend config keys are no longer supported. "
                "Use step_config.validation.backend_profiles instead. "
                f"Found: {legacy_backend_keys}"
            )
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
        if not self.get_enabled_backends():
            raise ValueError("At least one backend profile must have enabled=true.")
        if self.model_backend not in {"ecdf", "tabular_sklearn", "generative_hybrid"}:
            self.model_backend = self.get_enabled_backends()[0]
        if self.model_backend not in self.get_enabled_backends():
            self.model_backend = self.get_enabled_backends()[0]
        if self.model_backend == "tabular_sklearn" and not self.backend_profiles.tabular_sklearn.params.tabular_methods:
            raise ValueError("backend_profiles.tabular_sklearn.params.tabular_methods must contain at least one entry")
        self._sync_runtime_backend_fields()
        return self

    def get_enabled_backends(self) -> List[str]:
        enabled: List[str] = []
        if self.backend_profiles.ecdf.enabled:
            enabled.append("ecdf")
        if self.backend_profiles.tabular_sklearn.enabled:
            enabled.append("tabular_sklearn")
        if self.backend_profiles.generative_hybrid.enabled:
            enabled.append("generative_hybrid")
        return enabled

    def get_backend_params(
        self, backend_name: str
    ) -> Union[EcdfBackendParams, TabularBackendParams, GenerativeBackendParams]:
        backend = str(backend_name).strip().lower()
        if backend == "ecdf":
            return self.backend_profiles.ecdf.params
        if backend == "tabular_sklearn":
            return self.backend_profiles.tabular_sklearn.params
        if backend == "generative_hybrid":
            return self.backend_profiles.generative_hybrid.params
        raise ValueError(f"Unknown backend: {backend_name}")

    def with_backend_selection(self, backend_name: str) -> "MonteCarloConfig":
        backend = str(backend_name).strip().lower()
        if backend not in {"ecdf", "tabular_sklearn", "generative_hybrid"}:
            raise ValueError(f"Unknown backend: {backend_name}")
        updated = self.model_copy(update={"model_backend": backend})
        updated._sync_runtime_backend_fields()
        return updated

    def _sync_runtime_backend_fields(self) -> None:
        params = self.get_backend_params(self.model_backend)
        shared_fields = [
            "model_bundle_dir",
            "model_weight_column",
            "tabular_max_dmps",
            "feature_mode",
            "feature_family_set",
            "gene_feature_loading",
            "mapper_gene_columns",
            "observed_feature_quantiles",
            "observed_feature_min_coverage",
            "observed_feature_min_obs_fraction",
            "observed_feature_include_dmp",
            "observed_feature_include_chromosome",
            "observed_feature_include_dmr",
            "observed_feature_include_gene",
            "observed_feature_dmr_window_bp",
            "observed_feature_max_dmrs",
            "observed_feature_max_genes",
            "observed_hist_eps",
            "observed_hist_alpha",
            "observed_hist_evidence_clip_cap",
            "observed_hist_tail_agreement_threshold",
            "gene_scored_min_support_n",
            "gene_scored_use_region_weight",
            "gene_scored_gene_weight",
            "gene_scored_ordered_comparison_labels",
            "gene_scored_contrast_pairs",
            "structural_scored_min_support_n",
            "structural_scored_use_region_weight",
            "structural_scored_weight",
            "structural_scored_ordered_comparison_labels",
            "structural_scored_contrast_pairs",
            "region_directional_region_types",
            "region_directional_min_loci",
            "mapper_annotation_collapse_mode",
            "mapper_annotation_unknown_fallback",
            "observed_feature_quality_columns",
            "covariates_path",
            "covariate_id_column",
            "covariate_numeric_columns",
            "covariate_ordinal_columns",
            "covariate_ordinal_maps",
            "covariate_ordinal_unknown_value",
            "covariate_categorical_columns",
            "covariate_missing_numeric_strategy",
            "covariate_standardize_numeric",
            "covariates_strict_join",
        ]
        for field_name in shared_fields:
            setattr(self, field_name, getattr(params, field_name))
        self.ecdf_second_stage_enabled = bool(
            self.backend_profiles.ecdf.params.ecdf_second_stage_enabled
        )
        self.ecdf_aggregated_enabled = self.backend_profiles.ecdf.params.ecdf_aggregated_enabled
        self.ecdf_aggregated_n_bins = int(self.backend_profiles.ecdf.params.ecdf_aggregated_n_bins)
        tab_params = self.backend_profiles.tabular_sklearn.params
        self.tabular_model_type = tab_params.tabular_model_type
        self.tabular_methods = tab_params.tabular_methods
        self.tabular_method_selection_metric = tab_params.tabular_method_selection_metric
        self.tabular_method_selection_stat = tab_params.tabular_method_selection_stat
        self.tabular_save_train_dataset = bool(tab_params.tabular_save_train_dataset)
        self.tabular_reuse_train_dataset = bool(tab_params.tabular_reuse_train_dataset)
        self.tabular_train_dataset_path = tab_params.tabular_train_dataset_path
        self.tabular_save_test_dataset = bool(tab_params.tabular_save_test_dataset)
        self.tabular_test_dataset_path = tab_params.tabular_test_dataset_path
        gen_params = self.backend_profiles.generative_hybrid.params
        self.generative_latent_dim = int(gen_params.generative_latent_dim)
        self.generative_kl_weight = float(gen_params.generative_kl_weight)
        self.generative_density_type = str(gen_params.generative_density_type)
        self.generative_epochs = int(gen_params.generative_epochs)
        self.generative_batch_size = int(gen_params.generative_batch_size)
        self.generative_seed = int(gen_params.generative_seed)
        self.generative_calibrate = bool(gen_params.generative_calibrate)
        self.generative_covariates_strict = bool(gen_params.generative_covariates_strict)

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
        allowed = {"raw_dmp", "raw_gene", "observed_hybrid"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"feature_mode must be one of {sorted(allowed)}")
        return normalized

    @field_validator("feature_family_set")
    @classmethod
    def _validate_feature_family_set(cls, value: str) -> str:
        from .observed_feature_builder import normalize_feature_family_set

        return normalize_feature_family_set(value)

    @field_validator("gene_feature_loading")
    @classmethod
    def _validate_gene_feature_loading(cls, value: str) -> str:
        allowed = {"frozen", "range"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"gene_feature_loading must be one of {sorted(allowed)}")
        return normalized

    @field_validator("gene_scored_gene_weight")
    @classmethod
    def _validate_gene_scored_gene_weight_profile(cls, value: str) -> str:
        allowed = {"importance_x_sqrt_support", "importance_only"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"gene_scored_gene_weight must be one of {sorted(allowed)}")
        return normalized

    @field_validator("gene_scored_contrast_pairs")
    @classmethod
    def _validate_gene_scored_contrast_pairs_profile(
        cls, value: Optional[List[List[str]]]
    ) -> Optional[List[List[str]]]:
        if value is None:
            return None
        from .gene_scored_features import normalize_gene_scored_contrast_pairs

        return [[left, right] for left, right in normalize_gene_scored_contrast_pairs(value)]

    @field_validator("structural_scored_weight")
    @classmethod
    def _validate_structural_scored_weight(cls, value: str) -> str:
        allowed = {"compound_x_sqrt_support", "compound_only"}
        normalized = str(value).strip().lower()
        if normalized not in allowed:
            raise ValueError(f"structural_scored_weight must be one of {sorted(allowed)}")
        return normalized

    @field_validator("structural_scored_contrast_pairs")
    @classmethod
    def _validate_structural_scored_contrast_pairs(
        cls, value: Optional[List[List[str]]]
    ) -> Optional[List[List[str]]]:
        if value is None:
            return None
        from .structural_scored_features import normalize_structural_scored_contrast_pairs

        return [[left, right] for left, right in normalize_structural_scored_contrast_pairs(value)]

    @field_validator("region_directional_region_types")
    @classmethod
    def _validate_region_directional_region_types(cls, value: List[str]) -> List[str]:
        from .gene_scored_features import DEFAULT_REGION_DIRECTIONAL_TYPES, _normalize_structural_feature

        if not value:
            return list(DEFAULT_REGION_DIRECTIONAL_TYPES)
        out: List[str] = []
        for raw in value:
            token = _normalize_structural_feature(raw)
            if token == "unknown":
                raise ValueError(f"Unknown region_directional_region_type: {raw!r}")
            if token not in out:
                out.append(token)
        if not out:
            raise ValueError("region_directional_region_types cannot be empty")
        return out

    @field_validator("mapper_annotation_collapse_mode")
    @classmethod
    def _validate_mapper_annotation_collapse_mode(cls, value: str) -> str:
        token = str(value or "priority").strip().lower()
        if token not in {"priority", "weight"}:
            raise ValueError("mapper_annotation_collapse_mode must be 'priority' or 'weight'")
        return token

    @field_validator("mapper_annotation_unknown_fallback")
    @classmethod
    def _validate_mapper_annotation_unknown_fallback(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        from .gene_scored_features import _normalize_structural_feature

        token = _normalize_structural_feature(value)
        if token == "unknown":
            raise ValueError(f"Invalid mapper_annotation_unknown_fallback: {value!r}")
        return token

    @field_validator("mapper_gene_columns")
    @classmethod
    def _validate_mapper_gene_columns(cls, value: List[str]) -> List[str]:
        cleaned: List[str] = []
        seen: set[str] = set()
        for raw in value:
            token = str(raw).strip()
            if not token:
                continue
            if token in seen:
                continue
            seen.add(token)
            cleaned.append(token)
        return cleaned

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

    @model_validator(mode="after")
    def _validate_stability_early_stop(self) -> "MonteCarloConfig":
        if self.stability_early_stop_enabled:
            if self.stability_min_iterations > self.n_iterations:
                raise ValueError(
                    "stability_min_iterations must be <= n_iterations when stability_early_stop_enabled=true."
                )
            if self.stability_convergence_window >= self.stability_min_iterations:
                raise ValueError(
                    "stability_convergence_window must be smaller than stability_min_iterations when stability_early_stop_enabled=true."
                )
        return self

    @field_validator("subgroup_columns")
    @classmethod
    def _normalize_subgroup_columns(cls, value: List[str]) -> List[str]:
        out: List[str] = []
        seen: set[str] = set()
        for raw in value:
            token = str(raw).strip()
            if not token:
                continue
            if token in seen:
                continue
            seen.add(token)
            out.append(token)
        return out

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


# Fields injected from the parent project (or CLI) when loading step_config.validation.
_VALIDATION_STEP_EXCLUDE: FrozenSet[str] = frozenset(
    {
        "samples_base_path",
        "base_project",
        "output_base",
        "cohorts",
        "healthy_csv",
        "disease_csv",
        "validation",
    }
)


def _optionalize_annotation(annotation: Any) -> Any:
    if annotation is Any:
        return Optional[Any]
    origin = get_origin(annotation)
    if origin is Union:
        if type(None) in get_args(annotation):
            return annotation
    return annotation | None


def _constraints_from_field_metadata(metadata: Any) -> Dict[str, Any]:
    """
    Map Pydantic v2 ``FieldInfo.metadata`` (``annotated_types.*`` instances) to ``Field()`` kwargs.

    Dict-shaped metadata entries are still supported for forward compatibility.
    """
    try:
        import annotated_types as at
    except ImportError:  # pragma: no cover
        at = None

    out: Dict[str, Any] = {}
    for item in metadata or []:
        if at is not None:
            if isinstance(item, at.Ge):
                out["ge"] = item.ge
                continue
            if isinstance(item, at.Gt):
                out["gt"] = item.gt
                continue
            if isinstance(item, at.Le):
                out["le"] = item.le
                continue
            if isinstance(item, at.Lt):
                out["lt"] = item.lt
                continue
            if isinstance(item, at.MinLen):
                out["min_length"] = item.min_length
                continue
            if isinstance(item, at.MaxLen):
                out["max_length"] = item.max_length
                continue
            if isinstance(item, at.MultipleOf):
                out["multiple_of"] = item.multiple_of
                continue
        if isinstance(item, dict):
            for key, value in item.items():
                if key in {
                    "ge",
                    "le",
                    "gt",
                    "lt",
                    "multiple_of",
                    "min_length",
                    "max_length",
                    "pattern",
                    "strict",
                    "allow_inf_nan",
                }:
                    out[key] = value
    return out


def _validation_step_field_kwargs(field: Any) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {}
    if field.description:
        kwargs["description"] = field.description
    if field.default is not PydanticUndefined:
        kwargs["default"] = field.default
    elif field.default_factory is not None:
        kwargs["default_factory"] = field.default_factory
    else:
        kwargs["default"] = None
    kwargs.update(_constraints_from_field_metadata(field.metadata))
    return kwargs


def build_validation_step_config() -> Type[BaseModel]:
    """Build the embeddable validation step model (all fields optional for project JSON)."""
    fields: Dict[str, Any] = {}
    for name, info in MonteCarloConfig.model_fields.items():
        if name in _VALIDATION_STEP_EXCLUDE:
            continue
        fields[name] = (
            _optionalize_annotation(info.annotation),
            Field(**_validation_step_field_kwargs(info)),
        )
    return create_model(
        "ValidationStepConfig",
        __config__=ConfigDict(extra="ignore"),
        **fields,
    )


ValidationStepConfig = build_validation_step_config()

