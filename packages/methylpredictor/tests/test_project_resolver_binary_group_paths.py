from __future__ import annotations

import json
from pathlib import Path

import pytest

from methyl_predictor.project_resolver import resolve_predictor_config


def _write_binary_project(tmp_path: Path, predictor_cfg: dict) -> Path:
    project_path = tmp_path / "project.json"
    project_path.write_text(
        json.dumps(
            {
                "project_name": "BinaryCompat",
                "output_base": str(tmp_path / "out"),
                "samples_base_path": str(tmp_path / "samples"),
                "controls": {
                    "label": "controls",
                    "groups": [{"label": "healthy", "sample_paths": ["C_TRAIN_1"]}],
                },
                "diseases": {
                    "label": "diseases",
                    "groups": [{"label": "pca", "sample_paths": ["D_TRAIN_1"]}],
                },
                "comparisons": [{"control_group": "healthy", "disease_group": "pca"}],
                "step_config": {"predictor": predictor_cfg},
            }
        ),
        encoding="utf-8",
    )
    return project_path


def test_binary_resolver_accepts_group_paths_train_holdout(tmp_path: Path) -> None:
    project_path = _write_binary_project(
        tmp_path,
        predictor_cfg={
            "train_group_paths": [
                {"label": "healthy", "class_index": 0, "paths": ["/x/TR_C1", "/x/TR_C2"]},
                {"label": "pca", "class_index": 1, "paths": ["/x/TR_D1"]},
            ],
            "holdout_group_paths": [
                {"label": "healthy", "class_index": 0, "paths": ["/x/HO_C1"]},
                {"label": "pca", "class_index": 1, "paths": ["/x/HO_D1", "/x/HO_D2"]},
            ],
        },
    )
    cfg = resolve_predictor_config(project_path)
    assert cfg.test_control_paths == []
    assert cfg.test_disease_paths == []
    assert cfg.train_control_paths == ["/x/TR_C1", "/x/TR_C2"]
    assert cfg.train_disease_paths == ["/x/TR_D1"]
    assert cfg.holdout_control_paths == ["/x/HO_C1"]
    assert cfg.holdout_disease_paths == ["/x/HO_D1", "/x/HO_D2"]


def test_binary_resolver_rejects_group_paths_with_non_binary_class_index(tmp_path: Path) -> None:
    project_path = _write_binary_project(
        tmp_path,
        predictor_cfg={
            "holdout_group_paths": [
                {"label": "healthy", "class_index": 0, "paths": ["/x/HO_C1"]},
                {"label": "other", "class_index": 2, "paths": ["/x/HO_X1"]},
            ]
        },
    )
    with pytest.raises(ValueError, match="class_index 0/1"):
        resolve_predictor_config(project_path)


def test_binary_resolver_rejects_group_paths_missing_class_index(tmp_path: Path) -> None:
    project_path = _write_binary_project(
        tmp_path,
        predictor_cfg={
            "holdout_group_paths": [
                {"label": "healthy", "paths": ["/x/HO_C1"]},
                {"label": "pca", "class_index": 1, "paths": ["/x/HO_D1"]},
            ]
        },
    )
    with pytest.raises(ValueError, match="requires explicit class_index"):
        resolve_predictor_config(project_path)


def test_binary_resolver_rejects_empty_holdout_group_paths(tmp_path: Path) -> None:
    project_path = _write_binary_project(
        tmp_path,
        predictor_cfg={
            "holdout_group_paths": [
                {"label": "healthy", "class_index": 0, "paths": []},
                {"label": "pca", "class_index": 1, "paths": []},
            ]
        },
    )
    with pytest.raises(ValueError, match="contains no sample paths"):
        resolve_predictor_config(project_path)
