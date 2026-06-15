"""Smoke and compile tests for the PCa1-5 CG workflow check bundle."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

CHECK_ROOT = Path(__file__).resolve().parent
REPO_ROOT = CHECK_ROOT.parents[3]


def _run_check_pipeline(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(CHECK_ROOT / "check_pipeline.py"), *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=str(REPO_ROOT))


@pytest.mark.parametrize(
    "program_name",
    [
        "pca1_5_mc_stability.program.json",
        "pca1_5_mc_stability_smoke.program.json",
        "pca1_5_freeze.program.json",
        "pca1_5_model.program.json",
        "pca1_5_full_lifecycle.program.json",
    ],
)
def test_pca1_5_programs_compile(program_name: str) -> None:
    project = CHECK_ROOT / "configs" / "project_Healthy_vs_PCa1-5-CG_smoke.json"
    if program_name == "pca1_5_mc_stability.program.json":
        project = CHECK_ROOT / "configs" / "project_Healthy_vs_PCa1-5-CG.json"
    proc = _run_check_pipeline(
        "--project",
        str(project),
        "--program",
        str(CHECK_ROOT / "configs" / program_name),
        "--write-spec",
        str(CHECK_ROOT / "compiled" / program_name.replace(".program.json", "")),
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_smoke_project_has_explicit_cohorts() -> None:
    raw = json.loads((CHECK_ROOT / "configs" / "project_Healthy_vs_PCa1-5-CG.json").read_text())
    cohorts = raw.get("step_config", {}).get("validation", {}).get("cohorts")
    assert isinstance(cohorts, list)
    assert len(cohorts) == 6
    labels = [c["label"] for c in cohorts]
    assert labels == ["all", "PCa_PCa1", "PCa_PCa2", "PCa_PCa3", "PCa_PCa4", "PCa_PCa5"]


def test_mc_stability_program_has_centroid_incremental_actions() -> None:
    spec_path = CHECK_ROOT / "compiled" / "compiled_workflow.json"
    if not spec_path.is_file():
        _run_check_pipeline()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    centroid_nodes = [
        n for n in spec.get("nodes", []) if n.get("action_name") == "pipeline.centroid"
    ]
    assert centroid_nodes
    template = centroid_nodes[0]["input_template"]
    assert "addSamples" in template
    assert "removeSamples" in template
