"""Resolve extraction QC config from a pipeline project."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

from methyl_utils import load_project

from .models.config import DEFAULT_EXPECTED_CHROMOSOMES, ExtractionQCConfig, ExtractionQCGuardrailConfig


def resolve_extraction_qc_config(
    project_path: Union[str, Path],
    *,
    sample_paths: Optional[List[str]] = None,
) -> ExtractionQCConfig:
    project = load_project(project_path)
    resolved = project.get_resolved_groups()
    default_paths: List[str] = []
    for _, group_paths in resolved:
        default_paths.extend(group_paths)

    step_cfg = project.get_step_config("extraction_qc") or {}
    guardrail_cfg = ExtractionQCGuardrailConfig()
    if isinstance(step_cfg.get("guardrails"), dict):
        guardrail_cfg = ExtractionQCGuardrailConfig.model_validate(step_cfg["guardrails"])

    chromosomes = list(getattr(project, "chromosomes", None) or DEFAULT_EXPECTED_CHROMOSOMES)
    if step_cfg.get("expected_chromosomes"):
        chromosomes = [str(item) for item in step_cfg["expected_chromosomes"]]

    paths = sample_paths if sample_paths is not None else default_paths
    if step_cfg.get("sample_paths"):
        paths = [str(item) for item in step_cfg["sample_paths"]]

    return ExtractionQCConfig(
        guardrails=guardrail_cfg,
        expected_chromosomes=chromosomes,
        sample_paths=paths,
    )
