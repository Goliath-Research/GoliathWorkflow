"""Tests for ResolvedProject materialization."""

from __future__ import annotations

from pathlib import Path

import pytest

from methyl_domain.helpers import build_resolved_project


def test_build_resolved_project_from_smoke_project(tmp_path: Path) -> None:
    project_path = (
        Path(__file__).resolve().parents[3]
        / "workflow_engine"
        / "domain"
        / "checks"
        / "buffy_healthy_vs_pca"
        / "configs"
        / "project_Buffy_healthy_vs_PCa.json"
    )
    if not project_path.is_file():
        pytest.skip(f"smoke project missing: {project_path}")

    resolved = build_resolved_project(project_path)
    assert resolved.projectPath.endswith("project_Buffy_healthy_vs_PCa.json")
    assert resolved.groups
    assert resolved.comparisons
    cmp = resolved.comparisons[0]
    assert cmp.detectOutDir
    assert cmp.mapperOutDir
    assert cmp.enricherOutDir
    assert isinstance(cmp.controlSamplePaths, list)
    assert isinstance(cmp.diseaseSamplePaths, list)
