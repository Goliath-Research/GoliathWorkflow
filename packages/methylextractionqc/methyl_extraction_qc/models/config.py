"""Configuration for extraction QC guardrails."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_EXPECTED_CHROMOSOMES: List[str] = [str(i) for i in range(1, 23)] + ["X", "Y"]


class ExtractionQCGuardrailConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_cpg_weighted_mean_coverage: float = 10.0
    max_chh_methylation_level: float = 0.02
    max_chg_methylation_level: float = 0.02
    min_autosomal_coverage_uniformity_ratio: float = 0.5
    max_discard_fraction: float = 0.9


class ExtractionQCConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guardrails: ExtractionQCGuardrailConfig = Field(default_factory=ExtractionQCGuardrailConfig)
    expected_chromosomes: List[str] = Field(default_factory=lambda: list(DEFAULT_EXPECTED_CHROMOSOMES))
    sample_paths: List[str] = Field(default_factory=list)
