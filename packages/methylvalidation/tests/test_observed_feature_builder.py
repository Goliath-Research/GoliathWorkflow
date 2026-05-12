from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from methyl_validation import observed_feature_builder


def _fake_extract_complete(sample_paths, reference_positions, chromosome, min_coverage=1):
    del chromosome, min_coverage
    rows = []
    ctxs = []
    poss = []
    for ctx in sorted(reference_positions.keys()):
        for p in list(np.asarray(reference_positions[ctx], dtype=np.uint32)):
            ctxs.append(ctx)
            poss.append(int(p))
    for s in sample_paths:
        sid = Path(str(s)).name
        if sid in {"S1", "S2"}:
            vals = [0.10, 0.20, 0.30, 0.40]
        else:
            vals = [0.70, 0.80, 0.90, 0.95]
        rows.append(vals[: len(poss)])
    X = np.asarray(rows, dtype=np.float32)
    return (
        X,
        np.asarray(poss, dtype=np.uint32),
        np.asarray(ctxs, dtype=object),
        {"CG": np.arange(len(poss), dtype=np.uint32)},
    )


def _fake_extract_missing(sample_paths, reference_positions, chromosome, min_coverage=1):
    del chromosome, min_coverage
    # Return only one locus even if more were requested to simulate partial observation.
    pos = np.asarray([int(np.asarray(reference_positions["CG"])[0])], dtype=np.uint32)
    ctx = np.asarray(["CG"], dtype=object)
    X = np.asarray([[0.25], [0.75]], dtype=np.float32)
    return X, pos, ctx, {"CG": np.arange(1, dtype=np.uint32)}


def _dmp_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "chromosome": ["1", "1", "2", "2"],
            "context": ["CG", "CG", "CG", "CG"],
            "position": [100, 120, 200, 220],
            "weight": [1.0, 0.8, 0.7, 0.5],
            "effect_size": [1.0, 0.8, 0.7, 0.5],
        }
    )


def _derive_anchors(sample_paths, y, class_names, dmp_df):
    return observed_feature_builder.derive_observed_hybrid_anchors(
        sample_paths=sample_paths,
        sample_class_indices=y,
        class_names=class_names,
        dmp_df=dmp_df,
        min_coverage=1,
    )


def test_observed_feature_schema_is_deterministic(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_complete,
    )
    sample_paths = ["/tmp/S1", "/tmp/S2", "/tmp/S3", "/tmp/S4"]
    y = [0, 0, 1, 1]
    class_names = ["healthy", "cancer"]
    dmp_df = _dmp_df()
    anchors = _derive_anchors(sample_paths, y, class_names, dmp_df)

    feat_a = observed_feature_builder.build_observed_hybrid_feature_table(
        sample_paths,
        dmp_df,
        healthy_reference_vector=anchors.healthy_reference_vector,
        cancer_reference_vector=anchors.cancer_reference_vector,
        healthy_class_label=anchors.healthy_class_label,
        cancer_class_labels=anchors.cancer_class_labels,
        anchor_strategy=anchors.anchor_strategy,
        expected_feature_order_fingerprint=anchors.feature_order_fingerprint,
    )
    feat_b = observed_feature_builder.build_observed_hybrid_feature_table(
        sample_paths,
        dmp_df.sample(frac=1.0, random_state=13).reset_index(drop=True),
        healthy_reference_vector=anchors.healthy_reference_vector,
        cancer_reference_vector=anchors.cancer_reference_vector,
        healthy_class_label=anchors.healthy_class_label,
        cancer_class_labels=anchors.cancer_class_labels,
        anchor_strategy=anchors.anchor_strategy,
        expected_feature_order_fingerprint=anchors.feature_order_fingerprint,
    )
    assert feat_a.feature_names == feat_b.feature_names
    assert feat_a.report["schema_fingerprint"] == feat_b.report["schema_fingerprint"]
    assert feat_a.X.shape == feat_b.X.shape


def test_observed_feature_builder_keeps_missing_loci_as_nan(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_missing,
    )
    sample_paths = ["/tmp/S1", "/tmp/S2"]
    y = [0, 1]
    class_names = ["healthy", "cancer"]
    dmp_df = pd.DataFrame(
        {
            "chromosome": ["1", "1", "1"],
            "context": ["CG", "CG", "CG"],
            "position": [100, 120, 140],
            "weight": [1.0, 1.0, 1.0],
            "effect_size": [1.0, 1.0, 1.0],
        }
    )
    anchors = _derive_anchors(sample_paths, y, class_names, dmp_df)
    feat = observed_feature_builder.build_observed_hybrid_feature_table(
        sample_paths,
        dmp_df,
        healthy_reference_vector=anchors.healthy_reference_vector,
        cancer_reference_vector=anchors.cancer_reference_vector,
        healthy_class_label=anchors.healthy_class_label,
        cancer_class_labels=anchors.cancer_class_labels,
        anchor_strategy=anchors.anchor_strategy,
        expected_feature_order_fingerprint=anchors.feature_order_fingerprint,
    )
    obs_idx = feat.feature_names.index("obs_fraction")
    total_idx = feat.feature_names.index("n_total_dmps")
    assert np.allclose(feat.X[:, obs_idx], np.asarray([1.0 / 3.0, 1.0 / 3.0], dtype=np.float32), atol=1e-5)
    assert np.allclose(feat.X[:, total_idx], np.asarray([3.0, 3.0], dtype=np.float32), atol=1e-6)


def test_verify_feature_schema_raises_on_mismatch():
    with pytest.raises(ValueError, match="schema mismatch"):
        observed_feature_builder.verify_feature_schema(
            ["a", "b", "c"],
            ["a", "x", "c"],
            context="unit-test",
        )


def test_observed_feature_builder_requires_effect_size(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_complete,
    )
    sample_paths = ["/tmp/S1", "/tmp/S2", "/tmp/S3", "/tmp/S4"]
    y = [0, 0, 1, 1]
    class_names = ["healthy", "cancer"]
    dmp_df = _dmp_df().drop(columns=["effect_size"])

    with pytest.raises(ValueError, match="effect_size"):
        _derive_anchors(sample_paths, y, class_names, dmp_df)


def test_observed_feature_builder_includes_fixed_schema_and_centroid_metrics(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_complete,
    )
    sample_paths = ["/tmp/S1", "/tmp/S2", "/tmp/S3", "/tmp/S4"]
    y = [0, 0, 1, 1]
    class_names = ["healthy", "cancer"]
    dmp_df = _dmp_df()
    anchors = _derive_anchors(sample_paths, y, class_names, dmp_df)
    feat = observed_feature_builder.build_observed_hybrid_feature_table(
        sample_paths,
        dmp_df,
        healthy_reference_vector=anchors.healthy_reference_vector,
        cancer_reference_vector=anchors.cancer_reference_vector,
        healthy_class_label=anchors.healthy_class_label,
        cancer_class_labels=anchors.cancer_class_labels,
        anchor_strategy=anchors.anchor_strategy,
        expected_feature_order_fingerprint=anchors.feature_order_fingerprint,
    )

    expected_names = {
        "dmp_global_weighted_mean",
        "dmp_global_weighted_std",
        "dmp_global_weighted_abs_shift_from_half",
        "dmp_global_quantile_q10",
        "dmp_global_quantile_q50",
        "dmp_global_quantile_q90",
        "global_mean_dev_from_healthy",
        "global_mean_dev_from_cancer",
        "methylation_progression_score",
        "js_distance_to_healthy_centroid",
        "js_distance_to_cancer_centroid",
        "cosine_similarity_to_healthy_centroid",
        "cosine_similarity_to_cancer_centroid",
        "fraction_dmps_closer_to_cancer_centroid",
        "weighted_fraction_dmps_closer_to_cancer_centroid",
        "fraction_dmps_closer_to_healthy_centroid",
        "weighted_fraction_dmps_closer_to_healthy_centroid",
        "mean_abs_distance_margin",
        "dmp_global_skewness",
        "dmp_global_kurtosis",
        "avg_chrom_dev_from_healthy_centroid",
        "obs_fraction",
        "obs_weight_fraction",
        "n_obs_dmps",
        "n_total_dmps",
    }
    assert expected_names.issubset(set(feat.feature_names))

    js_h_idx = feat.feature_names.index("js_distance_to_healthy_centroid")
    js_c_idx = feat.feature_names.index("js_distance_to_cancer_centroid")
    cos_h_idx = feat.feature_names.index("cosine_similarity_to_healthy_centroid")
    cos_c_idx = feat.feature_names.index("cosine_similarity_to_cancer_centroid")
    frac_idx = feat.feature_names.index("fraction_dmps_closer_to_cancer_centroid")
    weighted_frac_idx = feat.feature_names.index(
        "weighted_fraction_dmps_closer_to_cancer_centroid"
    )
    healthy_frac_idx = feat.feature_names.index("fraction_dmps_closer_to_healthy_centroid")
    weighted_healthy_frac_idx = feat.feature_names.index(
        "weighted_fraction_dmps_closer_to_healthy_centroid"
    )
    margin_idx = feat.feature_names.index("mean_abs_distance_margin")
    prog_idx = feat.feature_names.index("methylation_progression_score")
    dev_h_idx = feat.feature_names.index("global_mean_dev_from_healthy")

    # First sample is healthy-like and should be closer to healthy anchor.
    assert float(feat.X[0, js_h_idx]) < float(feat.X[0, js_c_idx])
    assert float(feat.X[0, cos_h_idx]) > float(feat.X[0, cos_c_idx])
    assert float(feat.X[0, frac_idx]) <= 0.5
    assert float(feat.X[0, weighted_frac_idx]) <= 0.5
    assert float(feat.X[0, healthy_frac_idx]) >= 0.5
    assert float(feat.X[0, weighted_healthy_frac_idx]) >= 0.5
    assert float(feat.X[0, margin_idx]) < 0.0

    # Cancer-like sample should move towards cancer anchor.
    assert float(feat.X[2, js_c_idx]) < float(feat.X[2, js_h_idx])
    assert float(feat.X[2, frac_idx]) >= 0.5
    assert float(feat.X[2, weighted_frac_idx]) >= 0.5
    assert float(feat.X[2, healthy_frac_idx]) <= 0.5
    assert float(feat.X[2, weighted_healthy_frac_idx]) <= 0.5
    assert float(feat.X[2, margin_idx]) > 0.0

    # Progression should increase with higher methylation profiles in this synthetic setup.
    assert float(feat.X[2, prog_idx]) > float(feat.X[0, prog_idx])
    assert np.all((feat.X[:, prog_idx] >= 0.0) & (feat.X[:, prog_idx] <= 1.0))
    assert float(feat.X[0, dev_h_idx]) <= float(feat.X[2, dev_h_idx])
