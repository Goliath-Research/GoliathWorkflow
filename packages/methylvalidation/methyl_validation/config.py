"""
Runner config schema for Monte Carlo validation.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


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
        description="Optional path remap dict (from -> to) for resolving sample paths; or reuse from base_project.",
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

