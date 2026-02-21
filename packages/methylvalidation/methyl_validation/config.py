"""
Runner config schema for Monte Carlo validation.
"""

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field, model_validator


class MonteCarloConfig(BaseModel):
    """Configuration for the Monte Carlo validation runner."""

    samples_base_path: str = Field(
        ...,
        description="Base directory for resolving sample names from CSVs (same as project samples_base_path).",
    )
    healthy_csv: str = Field(
        ...,
        description="Path to CSV listing healthy samples (one column, e.g. 'sample').",
    )
    disease_csv: str = Field(
        ...,
        description="Path to CSV listing diseased samples (same format).",
    )
    train_fraction: float = Field(
        ...,
        gt=0.0,
        lt=1.0,
        description="Fraction of samples used for training (e.g. 0.8); same fraction applied to both classes.",
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
        description="Path to an existing project JSON used as template; only control/disease sample_paths and output_base/project_name are overridden per run.",
    )
    output_base: str = Field(
        ...,
        description="Global output base (same as pipeline/base project output_base, e.g. /work/.../all-prostate). "
        "Runs are created under output_base / project_name / monte_carlo_runs / run_0001, run_0002, ... "
        "so the layout matches the pipeline: output_base/project_name/centroids|detections|... for a single run, "
        "and output_base/project_name/monte_carlo_runs/run_id/centroids|detections|... for Monte Carlo.",
    )
    path_remap: Optional[Dict[str, str]] = Field(
        default=None,
        description="Optional path remap dict (from -> to) for resolving sample paths; or reuse from base_project.",
    )
    abort_on_step_failure: bool = Field(
        default=False,
        description="If True, abort all iterations when a pipeline step fails; if False, skip the iteration and continue.",
    )

    @model_validator(mode="after")
    def check_train_fraction(self) -> "MonteCarloConfig":
        if not (0 < self.train_fraction < 1):
            raise ValueError("train_fraction must be strictly between 0 and 1")
        return self

    @classmethod
    def from_json_file(cls, path: str | Path) -> "MonteCarloConfig":
        import json
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)
