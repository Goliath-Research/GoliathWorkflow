"""Binary --test-control/--test-disease must apply to comparison projects with multiclass PKL (methyl-validation)."""

from pathlib import Path
from unittest.mock import MagicMock

from methyl_predictor.models.config import PredictorConfig
from methyl_predictor.project_resolver import _apply_binary_cli_paths_to_multiclass_config


def test_apply_binary_cli_paths_replaces_multiclass_test_groups(tmp_path: Path) -> None:
    c1 = tmp_path / "s_ctrl"
    d1 = tmp_path / "s_dis"
    c1.mkdir()
    d1.mkdir()
    cfg = PredictorConfig(
        model_path=str(tmp_path / "m.pkl"),
        output_dir=str(tmp_path / "out"),
        test_group_paths=[
            {"label": "train_a", "paths": ["/should/not/use"]},
        ],
    )
    spec = MagicMock()
    spec.control_group = "all"
    spec.disease_group = "pca"
    project = MagicMock()
    project.get_comparisons.return_value = [spec]
    project.path_remap = None

    _apply_binary_cli_paths_to_multiclass_config(
        cfg,
        project,
        [str(c1.resolve())],
        [str(d1.resolve())],
        str(tmp_path),
        tmp_path / "proj.json",
        None,
    )
    assert cfg.test_group_paths is not None
    assert len(cfg.test_group_paths) == 2
    assert cfg.test_group_paths[0]["label"] == "all"
    assert cfg.test_group_paths[0]["paths"] == [str(c1.resolve())]
    assert cfg.test_group_paths[1]["label"] == "pca"
    assert cfg.test_group_paths[1]["paths"] == [str(d1.resolve())]
    assert cfg.test_group_paths[0]["class_index"] == 0
    assert cfg.test_group_paths[1]["class_index"] == 1
    assert len(cfg.sample_lineage) == 2
