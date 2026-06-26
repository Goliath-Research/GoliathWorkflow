"""Tests for ValidationPipeline Monte Carlo planner."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from methyl_validation.workflow_planner import ValidationPlanRequest, plan_validation_context


def _write_minimal_binary_project(tmp_path: Path) -> Path:
    samples = tmp_path / "samples"
    samples.mkdir()
    (samples / "H1").mkdir()
    (samples / "H2").mkdir()
    (samples / "D1").mkdir()
    (samples / "D2").mkdir()
    healthy = tmp_path / "healthy.csv"
    disease = tmp_path / "disease.csv"
    healthy.write_text("sample\nH1\nH2\n", encoding="utf-8")
    disease.write_text("sample\nD1\nD2\n", encoding="utf-8")
    profile_path = tmp_path / "test_mc.profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "pipelineProfile": "test_mc",
                "actionConfig": {
                    "validation": {
                        "n_iterations": 2,
                        "train_fraction": 0.5,
                        "seed": 7,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    os.environ["METHYL_PROFILE"] = str(profile_path)
    payload = {
        "project_name": "demo_mc",
        "output_base": str(tmp_path / "work"),
        "samples_base_path": str(samples),
        "controls": {
            "label": "healthy",
            "groups": [{"label": "healthy", "sample_paths": [str(healthy)]}],
        },
        "diseases": {
            "label": "disease",
            "groups": [{"label": "disease", "sample_paths": [str(disease)]}],
        },
        "comparisons": [
            {
                "label": "healthy_vs_disease",
                "control_group": "healthy",
                "disease_group": "disease",
            }
        ],
    }
    project_json = tmp_path / "project.json"
    project_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return project_json


def test_plan_validation_context_materializes_iterations(tmp_path: Path) -> None:
    project_json = _write_minimal_binary_project(tmp_path)
    context = plan_validation_context(
        ValidationPlanRequest(
            projectPath=str(project_json),
            featureIterations=2,
            qualityIterations=0,
        )
    )
    assert len(context["iterations"]) == 2
    assert context["iterations"][0]["phase"] == "feature"
    assert context["iterations"][0]["runId"] == "feature_run_0001"
    assert context["iterations"][0]["$type"] == "StratifiedCohortDraw"
    assert context["iterations"][0]["groups"]
    assert context["iterations"][0]["groups"][0]["$type"] == "MethylGroup"
    assert "taskConfig" in context["iterations"][0]
    run_project = Path(context["iterations"][0]["projectPath"])
    assert run_project.is_file()
    assert context["projectPath"].endswith("demo_mc")


def test_plan_validation_context_requires_validation_block(tmp_path: Path) -> None:
    project_json = tmp_path / "project.json"
    project_json.write_text(
        json.dumps(
            {
                "project_name": "x",
                "output_base": str(tmp_path),
                "group1": {"label": "a", "sample_paths": ["/a"]},
                "group2": {"label": "b", "sample_paths": ["/b"]},
            }
        ),
        encoding="utf-8",
    )
    os.environ.pop("METHYL_PROFILE", None)
    with pytest.raises(ValueError, match="validation action config"):
        plan_validation_context({"projectPath": str(project_json), "featureIterations": 1})


def test_plan_validation_context_resume_includes_monte_carlo_runs_root(tmp_path: Path) -> None:
    project_json = _write_minimal_binary_project(tmp_path)
    plan_validation_context(
        ValidationPlanRequest(
            projectPath=str(project_json),
            featureIterations=1,
            qualityIterations=0,
        )
    )
    resumed = plan_validation_context(
        ValidationPlanRequest(
            projectPath=str(project_json),
            featureIterations=1,
            qualityIterations=0,
            overwrite=False,
        )
    )
    task_config = resumed["iterations"][0]["taskConfig"]
    assert "monteCarloRunsRoot" in task_config
    assert Path(task_config["monteCarloRunsRoot"]).is_dir()
