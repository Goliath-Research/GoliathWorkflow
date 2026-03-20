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
from methyl_classifier.models.config import ClassifierConfig
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

    from methyl_classifier.core.classifier import MethylClassifier

    clf = MethylClassifier(ClassifierConfig(model_path=str(pkl_path)))
    assert clf._ovr_mode and clf.n_classes == 3
    assert len(clf.dmp_positions_df) == 3  # (1,10), (1,20), (2,10)

    X = np.array([[0.5, 0.5, 0.5]], dtype=np.float64)
    m = np.ones((1, 3), dtype=bool)
    proba = clf.predict_proba(X, m)
    assert proba.shape == (1, 3)
    np.testing.assert_allclose(proba.sum(axis=1), 1.0, rtol=1e-4)
