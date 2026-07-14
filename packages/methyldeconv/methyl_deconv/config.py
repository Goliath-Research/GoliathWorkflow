"""Pydantic step config for pipeline.cell_deconvolution (resolved via actionConfig)."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CellDeconvStepConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    output_dir: Optional[str] = Field(
        default=None,
        description="Output directory; default {project_root}/cell_fractions.",
    )
    seed_basis_path: Optional[str] = Field(
        default=None,
        description=(
            "Path to FlowSorted/IDOL seed basis JSON (markers × cell-type betas). "
            "Operator-set per site/profile; defaults to packaged flowsorted_blood_epic_idol_v1.json."
        ),
    )
    contexts: Optional[List[Literal["CG", "CHG", "CHH"]]] = Field(
        default=None,
        description=(
            "Methylation contexts to read from sample H5. "
            "Required in site/profile actionConfig.cell_deconvolution (no code default)."
        ),
    )
    marker_min_coverage: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Minimum coverage at a marker CpG for inclusion in Y. "
            "Required in site/profile actionConfig.cell_deconvolution (no code default)."
        ),
    )
    min_marker_fraction: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum fraction of seed markers observed (with coverage) required to emit Ω; "
            "below this, proportions are NaN. "
            "Required in site/profile actionConfig.cell_deconvolution (no code default)."
        ),
    )
    use_gpu: Optional[bool] = Field(
        default=None,
        description=(
            "Prefer MethylUtils CuPy/GPU backend when available (honors METHYL_DISABLE_GPU). "
            "Operator-set per profile/site; same pattern as centroid use_gpu."
        ),
    )
    sample_id_column: str = Field(
        default="sample_id",
        description="Column name for sample identifier in cell_fractions.csv.",
    )
