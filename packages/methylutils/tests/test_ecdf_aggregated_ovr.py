from __future__ import annotations

import numpy as np
import pandas as pd

from methyl_utils.ecdf_aggregated_ovr import (
    AGGREGATED_ECDF_OVR_TYPE,
    build_effect_size_feature_weights,
    predict_aggregated_ecdf_ovr_proba,
    train_aggregated_ecdf_ovr_package,
)


def _toy_dmp_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "effect_size": [0.2, -0.4, 0.8, -1.1, 0.6],
            "gene_name": ["A", "A", "B", "unknown", "C"],
            "feature_type": ["promoter", "exon", "intron", "gene_body", "terminator"],
        }
    )


def test_train_and_predict_aggregated_package_roundtrip() -> None:
    X = np.asarray(
        [
            [0.2, 0.1, 0.8],
            [0.3, 0.2, 0.7],
            [0.8, 0.7, 0.2],
            [0.9, 0.8, 0.1],
        ],
        dtype=np.float64,
    )
    y = np.asarray([0, 0, 1, 1], dtype=np.int32)
    feature_names = ["gene_obs_fraction", "struct_promoter_obs_fraction", "max_weighted_directional_score"]
    weights = build_effect_size_feature_weights(_toy_dmp_df(), feature_names)

    pkg = train_aggregated_ecdf_ovr_package(
        X,
        y,
        class_names=["healthy", "disease"],
        feature_names=feature_names,
        feature_weights=weights,
        feature_family_set="gene",
        feature_mode="observed_hybrid",
        n_bins=32,
        temperature=1.0,
    )
    assert pkg["classifier_type"] == AGGREGATED_ECDF_OVR_TYPE
    assert pkg["feature_schema"]["feature_names"] == feature_names
    assert len(pkg["binary_models"]) == 2

    probs, evidence = predict_aggregated_ecdf_ovr_proba(pkg, X)
    assert probs.shape == (4, 2)
    assert evidence.shape == (4, 2)
    np.testing.assert_allclose(np.sum(probs, axis=1), np.ones((4,)), rtol=1e-6, atol=1e-6)
    pred = np.argmax(probs, axis=1)
    assert set(pred.tolist()) <= {0, 1}
