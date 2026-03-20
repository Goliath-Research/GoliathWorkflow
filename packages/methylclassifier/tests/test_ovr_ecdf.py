"""OvR ECDF: union DMP construction, fusion, MethylClassifier load + predict_proba."""

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from methyl_classifier.core.multiclass_ovr import (
    build_union_dmp_dataframe,
    fuse_ovr_binary_probas,
)
from methyl_classifier.core.classifier import MethylClassifier
from methyl_classifier.models.config import ClassifierConfig


def _write_min_detector_pkl(path: Path, position: int, chrom: str = "1") -> None:
    ecdf = _tiny_ecdf(np.array([position], dtype=np.uint32))
    df = pd.DataFrame({"chromosome": [chrom], "position": [int(position)]})
    pkg = {"classifier": ecdf, "dmpDF": df, "metadata": {}}
    with open(path, "wb") as f:
        pickle.dump(pkg, f, protocol=pickle.HIGHEST_PROTOCOL)
from methyl_classifier.utils.ovr_bundle import build_ecdf_ovr_package


def _tiny_ecdf(positions: np.ndarray) -> "ECDFClassifier":
    from methyl_utils.ecdf_classifier import ECDFClassifier

    n_dmps = int(positions.shape[0])
    n_bins = 4
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_counts_c1 = np.ones((n_dmps, n_bins), dtype=np.float64)
    bin_counts_c2 = np.ones((n_dmps, n_bins), dtype=np.float64) * 1.5
    weights = np.ones(n_dmps, dtype=np.float64)
    directions = np.ones(n_dmps, dtype=np.int8)
    return ECDFClassifier(
        positions, bin_edges, bin_counts_c1, bin_counts_c2, weights, directions
    )


def test_build_union_dmp_overlapping_columns():
    """Three binaries with overlap: union width and per-model column maps."""
    e0 = _tiny_ecdf(np.array([100], dtype=np.uint32))
    e1 = _tiny_ecdf(np.array([100, 200], dtype=np.uint32))
    e2 = _tiny_ecdf(np.array([50], dtype=np.uint32))
    entries = [
        {
            "ecdf": e0,
            "dmp_df": pd.DataFrame({"chromosome": ["1"], "position": [100]}),
        },
        {
            "ecdf": e1,
            "dmp_df": pd.DataFrame({"chromosome": ["1", "1"], "position": [100, 200]}),
        },
        {
            "ecdf": e2,
            "dmp_df": pd.DataFrame({"chromosome": ["2"], "position": [50]}),
        },
    ]
    union_df, col_idx = build_union_dmp_dataframe(entries)
    assert len(union_df) == 3
    assert [int(x) for x in col_idx[0]] == [0]
    assert [int(x) for x in col_idx[1]] == [0, 1]
    assert [int(x) for x in col_idx[2]] == [2]


def test_fuse_ovr_binary_probas_rows_sum_to_one():
    n = 5
    p1 = np.tile([0.2, 0.8], (n, 1))
    p2 = np.tile([0.6, 0.4], (n, 1))
    p3 = np.tile([0.5, 0.5], (n, 1))
    out = fuse_ovr_binary_probas([p1, p2, p3])
    assert out.shape == (n, 3)
    np.testing.assert_allclose(out.sum(axis=1), 1.0, rtol=1e-5)


def test_methyl_classifier_ovr_pkl_predict_proba_shape(tmp_path, monkeypatch, capsys):
    """Load ecdf_one_vs_rest PKL: (n, K) probas, approximately stochastic rows."""
    monkeypatch.setattr("methyl_classifier.core.classifier.sys.exit", lambda *_: pytest.fail("sys.exit"))

    entries = [
        {
            "ecdf": _tiny_ecdf(np.array([10], dtype=np.uint32)),
            "dmp_df": pd.DataFrame({"chromosome": ["1"], "position": [10]}),
        },
        {
            "ecdf": _tiny_ecdf(np.array([20], dtype=np.uint32)),
            "dmp_df": pd.DataFrame({"chromosome": ["1"], "position": [20]}),
        },
        {
            "ecdf": _tiny_ecdf(np.array([10], dtype=np.uint32)),
            "dmp_df": pd.DataFrame({"chromosome": ["2"], "position": [10]}),
        },
    ]
    pkg = build_ecdf_ovr_package(entries, ["c0", "c1", "c2"])
    pkl_path = tmp_path / "ovr.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump(pkg, f, protocol=pickle.HIGHEST_PROTOCOL)

    clf = MethylClassifier(ClassifierConfig(model_path=str(pkl_path)))
    assert clf._ovr_mode and clf.n_classes == 3
    assert len(clf.dmp_positions_df) == 3  # (1,10), (1,20), (2,10)

    X = np.array([[0.5, 0.5, 0.5]], dtype=np.float64)
    m = np.ones((1, 3), dtype=bool)
    proba = clf.predict_proba(X, m)
    assert proba.shape == (1, 3)
    np.testing.assert_allclose(proba.sum(axis=1), 1.0, rtol=1e-4)


def test_methyl_classifier_ovr_save_writes_ecdf_one_vs_rest_dict(tmp_path, monkeypatch):
    """Saving OvR MethylClassifier writes portable dict PKL reloadable via load_classifier."""
    monkeypatch.setattr("methyl_classifier.core.classifier.sys.exit", lambda *_: pytest.fail("sys.exit"))

    entries = [
        {
            "ecdf": _tiny_ecdf(np.array([10], dtype=np.uint32)),
            "dmp_df": pd.DataFrame({"chromosome": ["1"], "position": [10]}),
        },
        {
            "ecdf": _tiny_ecdf(np.array([20], dtype=np.uint32)),
            "dmp_df": pd.DataFrame({"chromosome": ["1"], "position": [20]}),
        },
    ]
    pkg = build_ecdf_ovr_package(entries, ["a", "b"])
    pkl_path = tmp_path / "ovr_in.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump(pkg, f, protocol=pickle.HIGHEST_PROTOCOL)

    clf = MethylClassifier(ClassifierConfig(model_path=str(pkl_path)))
    out_path = tmp_path / "saved.pkl"
    clf.save(out_path)
    with open(out_path, "rb") as f:
        dumped = pickle.load(f)
    assert isinstance(dumped, dict)
    assert dumped.get("classifier_type") == "ecdf_one_vs_rest"
    clf2 = MethylClassifier(ClassifierConfig(model_path=str(out_path)))
    assert clf2._ovr_mode and clf2.n_classes == 2


def test_classifier_config_ovr_binary_paths_assembles_without_model_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("methyl_classifier.core.classifier.sys.exit", lambda *_: pytest.fail("sys.exit"))
    p1 = tmp_path / "c0.pkl"
    p2 = tmp_path / "c1.pkl"
    _write_min_detector_pkl(p1, 100)
    _write_min_detector_pkl(p2, 200)
    clf = MethylClassifier(
        ClassifierConfig(
            ovr_binary_model_paths=[str(p1), str(p2)],
            ovr_class_names=["c0", "c1"],
        )
    )
    assert clf._ovr_mode and clf.n_classes == 2
    assert len(clf.dmp_positions_df) == 2


def test_export_ovr_pkl_helpers_match_cli_bundle(tmp_path, monkeypatch):
    """CLI export path helpers produce the same portable PKL as an OvR save."""
    monkeypatch.setattr("methyl_classifier.core.classifier.sys.exit", lambda *_: pytest.fail("sys.exit"))
    from methyl_classifier.cli.main import (
        _export_ovr_pkl_from_config,
        _resolve_ovr_export_output_path,
    )
    from methyl_classifier.models.config_schema import ClassificationConfig

    p0 = tmp_path / "b0.pkl"
    p1 = tmp_path / "b1.pkl"
    _write_min_detector_pkl(p0, 100)
    _write_min_detector_pkl(p1, 200)

    cfg = ClassificationConfig(
        ovr_binary_model_paths=[str(p0), str(p1)],
        ovr_class_names=["c0", "c1"],
        save_classifier_path=str(tmp_path / "from_config.pkl"),
    )
    assert _resolve_ovr_export_output_path(cfg, None) == tmp_path / "from_config.pkl"
    assert _resolve_ovr_export_output_path(cfg, str(tmp_path / "explicit.pkl")) == tmp_path / "explicit.pkl"

    _export_ovr_pkl_from_config(cfg, tmp_path / "from_config.pkl")
    with open(tmp_path / "from_config.pkl", "rb") as f:
        dumped = pickle.load(f)
    assert isinstance(dumped, dict)
    assert dumped.get("classifier_type") == "ecdf_one_vs_rest"
    clf2 = MethylClassifier(ClassifierConfig(model_path=str(tmp_path / "from_config.pkl")))
    assert clf2._ovr_mode and clf2.n_classes == 2


def test_classifier_step_dict_has_ovr_sources():
    from methyl_classifier.project_resolver import classifier_step_dict_has_ovr_sources

    assert not classifier_step_dict_has_ovr_sources({})
    assert not classifier_step_dict_has_ovr_sources({"ovr_binary_model_paths": ["only_one"]})
    assert classifier_step_dict_has_ovr_sources({"ovr_binary_model_paths": ["a", "b"]})
    assert classifier_step_dict_has_ovr_sources(
        {"ovr_detection_dirs": ["/x", "/y"]}
    )
    assert classifier_step_dict_has_ovr_sources(
        {"ovr_binary_pickles_from_comparisons": True}
    )


def test_expand_ovr_paths_from_healthy_pca_project_comparisons():
    """Paths follow detections/<control>/<disease>/basename from project comparisons."""
    from pathlib import Path

    from methyl_utils import load_project

    from methyl_classifier.project_resolver import (
        expand_ovr_paths_from_comparisons,
        resolve_classifier_config,
    )

    repo = Path(__file__).resolve().parents[3]
    proj_path = repo / "configs" / "project_Healthy_vs_PCa1-4.json"
    if not proj_path.exists():
        pytest.skip("repo configs/project_Healthy_vs_PCa1-4.json not present")
    project = load_project(proj_path)
    bn = "classifier-1-CG,CHG,CHH.pkl"
    root = Path(project.get_project_root())
    dedicated = root / "detections" / "one_vs_rest" / "all" / bn
    if dedicated.is_file():
        paths, names = expand_ovr_paths_from_comparisons(project, unified_basename=bn)
    else:
        with pytest.warns(UserWarning, match="pairwise detector"):
            paths, names = expand_ovr_paths_from_comparisons(project, unified_basename=bn)
    assert names == ["all", "pca1", "pca2", "pca3", "pca4"]
    if dedicated.is_file():
        assert Path(paths[0]) == dedicated
    else:
        assert Path(paths[0]) == root / "detections" / "all" / "pca1" / bn
    for dis in ("pca1", "pca2", "pca3", "pca4"):
        assert (root / "detections" / "all" / dis / bn) == Path(paths[names.index(dis)])

    cfg = resolve_classifier_config(proj_path)
    assert cfg.ovr_binary_model_paths == paths
    assert cfg.ovr_class_names == names
    assert cfg.save_classifier_path.replace("\\", "/").endswith(
        "/classifiers/all/classifier_all_Healthy_vs_PCa1-4.pkl"
    )
