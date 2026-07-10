"""Tests for SaMD study scaffold and manifest validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from admin.study_init import build_manifest, write_study
from admin.study_validate import validate_manifest


def test_build_manifest_binary():
    m = build_manifest(
        project_name="Healthy_vs_Disease",
        study_id="example",
        output_root=Path("/work/projects"),
        analyte="buffy_coat",
        stages=None,
        intended_use="test",
    )
    assert m["project_name"] == "Healthy_vs_Disease"
    assert m["regulatory"]["allow_clinical_performance_claims"] is False
    assert "locked_test" in m["validation_partitions"]
    assert m["diseases"]["groups"][0]["sample_paths"][0].endswith("disease.csv")


def test_build_manifest_staged():
    m = build_manifest(
        project_name="Healthy_vs_Stages",
        study_id="example",
        output_root=Path("/work/projects"),
        analyte="cfdna",
        stages=3,
        intended_use="test",
    )
    stages = m["diseases"]["groups"][0]["stages"]
    assert len(stages) == 3
    assert m["progression_labels"] == ["disease_stage1", "disease_stage2", "disease_stage3"]


def test_write_study_creates_layout(tmp_path: Path):
    manifest_path = write_study(
        study_id="demo",
        name="Healthy_vs_Disease",
        analyte="buffy_coat",
        stages=None,
        output_root=tmp_path,
        intended_use="demo",
        force=False,
    )
    assert manifest_path.is_file()
    assert (tmp_path / "demo" / "data" / "healthy.csv").is_file()
    assert (tmp_path / "demo" / "configs" / "README.md").is_file()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["regulatory"]["stage"] == "expanded_development"


def test_enrichment_requires_locked_test():
    project = {
        "regulatory": {"stage": "internal_validation", "allow_clinical_performance_claims": False},
        "validation_partitions": {"locked_test": [], "pivotal_validation": []},
    }
    errs = validate_manifest(project, pipeline_profile="samd_holdout_enrichment")
    assert any("locked_test" in e for e in errs)


def test_pivotal_requires_pivotal_partition():
    project = {
        "regulatory": {"stage": "pivotal_validation", "allow_clinical_performance_claims": False},
        "validation_partitions": {
            "locked_test": ["a"],
            "pivotal_validation": [],
        },
    }
    errs = validate_manifest(project, pipeline_profile="samd_pivotal")
    assert any("pivotal_validation" in e for e in errs)


def test_claims_blocked_before_pivotal():
    project = {
        "regulatory": {
            "stage": "expanded_development",
            "allow_clinical_performance_claims": True,
        },
        "validation_partitions": {},
    }
    errs = validate_manifest(project, pipeline_profile="samd_research")
    assert any("allow_clinical_performance_claims" in e for e in errs)


def test_ok_enrichment_with_holdout():
    project = {
        "regulatory": {"stage": "internal_validation", "allow_clinical_performance_claims": False},
        "validation_partitions": {
            "locked_test": ["H1", "D1"],
            "pivotal_validation": [],
            "development_train": ["H2"],
        },
    }
    assert validate_manifest(project, pipeline_profile="samd_holdout_enrichment") == []


def test_overlap_detected():
    project = {
        "regulatory": {"stage": "pivotal_validation", "allow_clinical_performance_claims": False},
        "validation_partitions": {
            "locked_test": ["X1"],
            "pivotal_validation": ["X1"],
        },
    }
    errs = validate_manifest(project, pipeline_profile="samd_pivotal")
    assert any("overlap" in e for e in errs)
