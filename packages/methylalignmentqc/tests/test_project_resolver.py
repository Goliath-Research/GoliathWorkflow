"""Test project_resolver returns expected output_dir and sample_paths from project config."""

import json
import tempfile
from pathlib import Path

import pytest


def test_resolve_alignment_qc_config_output_dir_and_sample_paths():
    """resolve_alignment_qc_config returns output_dir and non-empty sample_paths from minimal project."""
    from methyl_alignment_qc.project_resolver import resolve_alignment_qc_config

    project = {
        "project_name": "TestProject",
        "output_base": "/work/output",
        "group1": {"label": "healthy", "sample_paths": ["/samples/h1", "/samples/h2"]},
        "group2": {"label": "disease", "sample_paths": ["/samples/d1"]},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(project, f)
        project_path = f.name
    try:
        config = resolve_alignment_qc_config(project_path)
        assert config.output_dir == "/work/output/alignment_qc"
        assert len(config.sample_paths) == 3
        assert "/samples/h1" in config.sample_paths
        assert "/samples/h2" in config.sample_paths
        assert "/samples/d1" in config.sample_paths
        assert config.validate_schema is True
    finally:
        Path(project_path).unlink(missing_ok=True)


def test_resolve_alignment_qc_config_step_config_validate_schema():
    """step_config.alignment_qc.validate_schema is applied."""
    from methyl_alignment_qc.project_resolver import resolve_alignment_qc_config

    project = {
        "project_name": "Test",
        "output_base": "/out",
        "group1": {"label": "g1", "sample_paths": ["/a"]},
        "group2": {"label": "g2", "sample_paths": []},
        "step_config": {"alignment_qc": {"validate_schema": False}},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(project, f)
        project_path = f.name
    try:
        config = resolve_alignment_qc_config(project_path)
        assert config.validate_schema is False
        assert config.output_dir == "/out/alignment_qc"
    finally:
        Path(project_path).unlink(missing_ok=True)
