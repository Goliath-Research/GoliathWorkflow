"""Tests for sample prep lifecycle gateway helper."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REST = Path(__file__).resolve().parents[1] / "rest"
_VALIDATION = Path(__file__).resolve().parents[1].parent / "packages" / "methylvalidation"
for _p in (_REST, _VALIDATION):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from sample_lifecycle import start_sample_prep  # noqa: E402


def _minimal_project(tmp_path: Path) -> Path:
    project = {
        "project_name": "prep_test",
        "output_base": str(tmp_path / "out"),
        "samples_base_path": str(tmp_path / "samples"),
        "chromosomes": ["21"],
        "controls": {
            "label": "healthy",
            "groups": [{"label": "all", "sample_paths": []}],
        },
        "diseases": {
            "label": "cancer",
            "groups": [{"label": "PCa", "sample_paths": []}],
        },
        "step_config": {"alignment_qc": {"genome_fasta": "/work/ref.fa"}},
    }
    path = tmp_path / "project.json"
    path.write_text(json.dumps(project), encoding="utf-8")
    return path


def test_start_sample_prep_plans_context_and_starts_instance(tmp_path: Path) -> None:
    project_path = _minimal_project(tmp_path)
    created: dict = {}
    started: list[int] = []

    def fake_create_instance(_dsn: str, version_id: int, context: dict) -> int:
        created["version_id"] = version_id
        created["context"] = context
        return 42

    def fake_start(_dsn: str, instance_id: int) -> None:
        started.append(instance_id)

    payload = start_sample_prep(
        "dsn",
        {
            "projectPath": str(project_path),
            "workflow_version_id": 7,
            "samples": [{"sampleId": "S1", "fastqSourceUri": "s3://b/S1/"}],
        },
        create_workflow_definition=MagicMock(),
        create_workflow_instance=fake_create_instance,
        start_workflow_instance=fake_start,
    )

    assert payload["instance_id"] == 42
    assert payload["workflow_version_id"] == 7
    assert payload["n_samples"] == 1
    assert created["context"]["samples"][0]["sampleId"] == "S1"
    assert started == [42]


def test_start_sample_prep_requires_project_path() -> None:
    with pytest.raises(ValueError, match="projectPath"):
        start_sample_prep(
            "dsn",
            {"samples": [{"sampleId": "S1"}]},
            create_workflow_definition=MagicMock(),
            create_workflow_instance=MagicMock(),
            start_workflow_instance=MagicMock(),
        )
