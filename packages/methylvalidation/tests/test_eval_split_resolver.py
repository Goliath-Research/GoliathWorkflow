from __future__ import annotations

import json
from pathlib import Path

import pytest

from methyl_validation.eval_split_resolver import resolve_eval_paths_and_labels


class _Project:
    def __init__(self, groups):
        self._groups = groups

    def get_resolved_groups(self):
        return self._groups


def test_model_mc_test_partition_is_explicit_and_disjoint(tmp_path: Path) -> None:
    project_json = tmp_path / "project.json"
    project_json.write_text("{}", encoding="utf-8")
    (tmp_path / "test_groups.json").write_text(
        json.dumps(
            [
                {"label": "control", "class_index": 0, "paths": [str(tmp_path / "T0")]},
                {"label": "disease", "class_index": 1, "paths": [str(tmp_path / "T1")]},
            ]
        ),
        encoding="utf-8",
    )

    paths, labels = resolve_eval_paths_and_labels(
        project_json,
        ["control", "disease"],
        project_loader=lambda _path: _Project(
            [
                ("control", [str(tmp_path / "S0")]),
                ("disease", [str(tmp_path / "S1")]),
            ]
        ),
        evaluation_partition="test",
    )

    assert paths == [str(tmp_path / "T0"), str(tmp_path / "T1")]
    assert labels is not None
    assert labels.tolist() == [0, 1]


def test_model_mc_test_partition_missing_or_overlapping_fails(tmp_path: Path) -> None:
    project_json = tmp_path / "project.json"
    project_json.write_text("{}", encoding="utf-8")
    loader = lambda _path: _Project([("control", [str(tmp_path / "S0")])])

    with pytest.raises(FileNotFoundError, match="requires test_groups.json"):
        resolve_eval_paths_and_labels(
            project_json,
            ["control"],
            project_loader=loader,
            evaluation_partition="test",
        )

    (tmp_path / "test_groups.json").write_text(
        json.dumps([{"label": "control", "paths": [str(tmp_path / "S0")]}]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="partitions overlap"):
        resolve_eval_paths_and_labels(
            project_json,
            ["control"],
            project_loader=loader,
            evaluation_partition="test",
        )
