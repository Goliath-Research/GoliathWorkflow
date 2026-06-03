from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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


def test_range_loading_expands_loci_beyond_frozen_dmps(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder,
        "_resolve_sample_context_h5",
        lambda sample_path, chromosome, context: Path("/tmp/fake.h5"),
    )
    monkeypatch.setattr(
        observed_feature_builder,
        "load_from_h5",
        lambda path: SimpleNamespace(df=pd.DataFrame({"pos": [95, 100, 110, 500]})),
    )
    base = pd.DataFrame(
        {
            "comparison_label": ["healthy_vs_pca1"],
            "chromosome": ["1"],
            "context": ["CG"],
            "position": [100],
            "effect_size": [0.4],
            "gene_name": ["GENE_A"],
            "feature_type": ["promoter"],
        }
    )
    ranges = pd.DataFrame(
        {
            "comparison_label": ["healthy_vs_pca1"],
            "gene_name": ["GENE_A"],
            "chromosome": ["1"],
            "feature_type": ["promoter"],
            "feature_start": [90],
            "feature_end": [120],
            "feature_effect_compound": [0.8],
        }
    )
    expanded = observed_feature_builder._expand_loci_df_from_gene_ranges(
        sample_paths=["/tmp/S1"],
        base_dmp_df=base,
        gene_feature_ranges_df=ranges,
    )
    assert sorted(set(expanded["position"].astype(int).tolist())) == [95, 100, 110]


def test_anchor_and_feature_table_do_not_diverge_for_dmp_family_with_range_loading(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder,
        "_resolve_sample_context_h5",
        lambda sample_path, chromosome, context: Path("/tmp/fake.h5"),
    )
    monkeypatch.setattr(
        observed_feature_builder,
        "load_from_h5",
        lambda path: SimpleNamespace(df=pd.DataFrame({"pos": [95, 100, 110, 500]})),
    )
    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_complete,
    )

    sample_paths = ["/tmp/S1", "/tmp/S2", "/tmp/S3", "/tmp/S4"]
    y = [0, 0, 1, 1]
    class_names = ["healthy", "cancer"]
    dmp_df = pd.DataFrame(
        {
            "comparison_label": ["healthy_vs_cancer"],
            "chromosome": ["1"],
            "context": ["CG"],
            "position": [100],
            "effect_size": [0.4],
            "gene_name": ["GENE_A"],
            "feature_type": ["promoter"],
        }
    )
    fixed_gene_features_df = pd.DataFrame(
        {
            "comparison_label": ["healthy_vs_cancer"],
            "gene_name": ["GENE_A"],
            "chromosome": ["1"],
            "feature_type": ["promoter"],
            "feature_start": [90],
            "feature_end": [120],
            "feature_effect_compound": [0.8],
        }
    )

    anchors = observed_feature_builder.derive_observed_hybrid_anchors(
        sample_paths=sample_paths,
        sample_class_indices=y,
        class_names=class_names,
        dmp_df=dmp_df,
        min_coverage=1,
        feature_family_set="dmp",
        gene_feature_loading="range",
        fixed_gene_features_df=fixed_gene_features_df,
    )
    # This should not raise due to reference length mismatch / fingerprint mismatch.
    feat = observed_feature_builder.build_observed_hybrid_feature_table(
        sample_paths,
        dmp_df,
        healthy_reference_vector=anchors.healthy_reference_vector,
        cancer_reference_vector=anchors.cancer_reference_vector,
        healthy_class_label=anchors.healthy_class_label,
        cancer_class_labels=anchors.cancer_class_labels,
        anchor_strategy=anchors.anchor_strategy,
        expected_feature_order_fingerprint=anchors.feature_order_fingerprint,
        feature_family_set="dmp",
        gene_feature_loading="range",
        fixed_gene_features_df=fixed_gene_features_df,
    )
    assert feat.X.shape[0] == len(sample_paths)


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
        "max_weighted_directional_score",
        "weighted_directional_agreement__cancer",
        "weighted_cosine_similarity_to_cancer_centroid__cancer",
        "weighted_centroid_contrast_score",
        "obs_fraction",
        "n_obs_dmps",
        "n_total_dmps",
        "weighted_healthy_tail_evidence__cancer",
    }
    assert expected_names.issubset(set(feat.feature_names))
    removed_names = {
        "weighted_mean_abs_distance_margin",
        "weighted_obs_fraction",
        "weighted_fraction_dmps_closer_to_cancer_centroid__cancer",
        "weighted_mean_abs_error_to_cancer_centroid__cancer",
    }
    assert removed_names.isdisjoint(set(feat.feature_names))
    for quality_name in ("obs_fraction", "n_obs_dmps", "n_total_dmps"):
        assert quality_name in feat.feature_names
        assert quality_name in feat.quality_feature_names
        assert quality_name not in feat.training_feature_names

    wcontrast_idx = feat.feature_names.index("weighted_centroid_contrast_score")
    max_wds_idx = feat.feature_names.index("max_weighted_directional_score")
    wda_idx = feat.feature_names.index("weighted_directional_agreement__cancer")
    tail_e_idx = feat.feature_names.index("weighted_healthy_tail_evidence__cancer")

    # First sample is healthy-like and should be closer to healthy anchor.
    assert float(feat.X[0, wcontrast_idx]) < 0.0
    assert float(feat.X[0, max_wds_idx]) < 0.0
    assert float(feat.X[0, wda_idx]) < 0.5
    assert not np.isfinite(float(feat.X[0, tail_e_idx]))

    # Cancer-like sample should move towards cancer anchor.
    assert float(feat.X[2, wcontrast_idx]) > 0.0
    assert float(feat.X[2, max_wds_idx]) > 0.0
    assert float(feat.X[2, wda_idx]) > 0.5
    assert not np.isfinite(float(feat.X[2, tail_e_idx]))

    profile = feat.report.get("feature_profile") or {}
    assert profile.get("schema_version") == observed_feature_builder.HYBRID_FEATURE_SCHEMA_VERSION
    assert profile.get("n_training_features") == len(feat.training_feature_names)
    assert profile.get("n_quality_features") == len(feat.quality_feature_names)


def test_observed_feature_builder_histogram_tail_features_multiclass_names(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_complete,
    )
    sample_paths = ["/tmp/S1", "/tmp/S2", "/tmp/S3", "/tmp/S4", "/tmp/S5", "/tmp/S6"]
    y = [0, 0, 1, 1, 2, 2]
    class_names = ["healthy", "pca1", "pca2"]
    dmp_df = _dmp_df()
    anchors = _derive_anchors(sample_paths, y, class_names, dmp_df)
    feat = observed_feature_builder.build_observed_hybrid_feature_table(
        sample_paths,
        dmp_df,
        healthy_reference_vector=anchors.healthy_reference_vector,
        cancer_reference_vector=anchors.cancer_reference_vector,
        per_cancer_reference_vectors=anchors.per_cancer_reference_vectors,
        healthy_class_label=anchors.healthy_class_label,
        cancer_class_labels=anchors.cancer_class_labels,
        anchor_strategy=anchors.anchor_strategy,
        expected_feature_order_fingerprint=anchors.feature_order_fingerprint,
    )
    assert "weighted_healthy_tail_evidence__pca1" in feat.feature_names
    assert "weighted_directional_agreement__pca1" in feat.feature_names
    assert "weighted_cosine_similarity_to_cancer_centroid__pca1" in feat.feature_names
    assert "weighted_healthy_tail_evidence__pca2" in feat.feature_names
    assert "weighted_directional_agreement__pca2" in feat.feature_names
    assert "weighted_cosine_similarity_to_cancer_centroid__pca2" in feat.feature_names
    assert "weighted_mean_abs_error_to_cancer_centroid__pca1" not in feat.feature_names
    assert "weighted_fraction_dmps_closer_to_cancer_centroid__pca1" not in feat.feature_names
    assert "weighted_mean_abs_error_to_cancer_centroid__pca2" not in feat.feature_names
    assert "weighted_fraction_dmps_closer_to_cancer_centroid__pca2" not in feat.feature_names


def test_observed_feature_builder_histogram_tail_features_behaviors(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_complete,
    )

    def _fake_load_binned_counts(dmps_df, centroid1_dir, centroid2_dir, chromosome):
        del chromosome
        n = len(dmps_df)
        bin_edges = np.asarray([0.0, 0.5, 1.0], dtype=np.float64)
        healthy = np.zeros((n, 2), dtype=np.int32)
        cancer = np.zeros((n, 2), dtype=np.int32)
        healthy[:, 0] = 10
        healthy[:, 1] = 90
        if str(centroid2_dir).endswith("cancer"):
            cancer[:, 0] = 5
            cancer[:, 1] = 95
        else:
            cancer[:, 0] = 50
            cancer[:, 1] = 50
        return bin_edges, healthy, cancer

    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "load_binned_counts_from_centroids",
        staticmethod(_fake_load_binned_counts),
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
        per_cancer_reference_vectors=anchors.per_cancer_reference_vectors,
        healthy_class_label=anchors.healthy_class_label,
        cancer_class_labels=anchors.cancer_class_labels,
        anchor_strategy=anchors.anchor_strategy,
        expected_feature_order_fingerprint=anchors.feature_order_fingerprint,
        centroid_dir_by_class_label={"healthy": "/tmp/healthy", "cancer": "/tmp/cancer"},
        hist_eps=1e-6,
        hist_alpha=0.5,
        hist_evidence_clip_cap=5.0,
        hist_tail_agreement_threshold=0.10,
    )
    idx_e = feat.feature_names.index("weighted_healthy_tail_evidence__cancer")
    assert float(feat.X[0, idx_e]) < float(feat.X[2, idx_e])
    assert float(feat.X[2, idx_e]) <= 5.0


def test_observed_feature_builder_histogram_tail_features_nan_when_invalid(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_complete,
    )

    def _fake_load_zero_counts(dmps_df, centroid1_dir, centroid2_dir, chromosome):
        del centroid1_dir, centroid2_dir, chromosome
        n = len(dmps_df)
        bin_edges = np.asarray([0.0, 0.5, 1.0], dtype=np.float64)
        healthy = np.zeros((n, 2), dtype=np.int32)
        cancer = np.zeros((n, 2), dtype=np.int32)
        return bin_edges, healthy, cancer

    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "load_binned_counts_from_centroids",
        staticmethod(_fake_load_zero_counts),
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
        per_cancer_reference_vectors=anchors.per_cancer_reference_vectors,
        healthy_class_label=anchors.healthy_class_label,
        cancer_class_labels=anchors.cancer_class_labels,
        anchor_strategy=anchors.anchor_strategy,
        expected_feature_order_fingerprint=anchors.feature_order_fingerprint,
        centroid_dir_by_class_label={"healthy": "/tmp/healthy", "cancer": "/tmp/cancer"},
    )
    idx_e = feat.feature_names.index("weighted_healthy_tail_evidence__cancer")
    assert not np.isfinite(float(feat.X[0, idx_e]))


def _dmp_df_with_mapped_features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "chromosome": ["1", "1", "1", "1"],
            "context": ["CG", "CG", "CG", "CG"],
            "position": [100, 120, 200, 220],
            "weight": [1.0, 2.0, 0.5, 0.7],
            "effect_size": [1.0, -2.0, 0.5, 0.7],
            "gene_name": ["G1", "G1", "G2", "unknown"],
            "feature_type": ["promoter", "exon", "intron", "promoter"],
        }
    )


def test_observed_feature_builder_gene_family_uses_dynamic_mapped_keys(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_complete,
    )
    sample_paths = ["/tmp/S1", "/tmp/S2", "/tmp/S3", "/tmp/S4"]
    y = [0, 0, 1, 1]
    class_names = ["healthy", "cancer"]
    dmp_df = _dmp_df_with_mapped_features()
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
        feature_family_set="gene",
    )
    assert feat.feature_names == ["gene::G1", "gene::G2"]
    g1_idx = feat.feature_names.index("gene::G1")
    g2_idx = feat.feature_names.index("gene::G2")
    # S1 values from _fake_extract_complete: [0.10, 0.20, 0.30, 0.40]
    # centered: [-0.4, -0.3, -0.2, -0.1]
    # G1: (1*-0.4 + -2*-0.3) / (1+2) = 0.066666...
    # G2: (0.5*-0.2)/(0.5) = -0.2
    assert float(feat.X[0, g1_idx]) == pytest.approx(0.0666666667, rel=1e-5, abs=1e-6)
    assert float(feat.X[0, g2_idx]) == pytest.approx(-0.2, rel=1e-5, abs=1e-6)
    # S3 values from _fake_extract_complete: [0.70, 0.80, 0.90, 0.95]
    # centered: [0.2, 0.3, 0.4, 0.45]
    # G1: (1*0.2 + -2*0.3) / 3 = -0.133333...
    # G2: (0.5*0.4)/(0.5) = 0.4
    assert float(feat.X[2, g1_idx]) == pytest.approx(-0.1333333333, rel=1e-5, abs=1e-6)
    assert float(feat.X[2, g2_idx]) == pytest.approx(0.4, rel=1e-5, abs=1e-6)
    assert feat.report["raw_mapped_feature_formula"] == "signed_weighted_centered_beta"
    assert feat.report["raw_mapped_feature_counts"]["gene"] == 2


def test_observed_feature_builder_structural_family_uses_mapped_combinations(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_complete,
    )
    sample_paths = ["/tmp/S1", "/tmp/S2", "/tmp/S3", "/tmp/S4"]
    y = [0, 0, 1, 1]
    class_names = ["healthy", "cancer"]
    dmp_df = _dmp_df_with_mapped_features()
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
        feature_family_set="structural",
    )
    assert feat.feature_names == [
        "struct::G1::exon",
        "struct::G1::promoter",
        "struct::G2::intron",
    ]
    # S1 centered locus values are [-0.4, -0.3, -0.2, -0.1]
    assert float(feat.X[0, feat.feature_names.index("struct::G1::promoter")]) == pytest.approx(
        -0.4, rel=1e-5, abs=1e-6
    )
    assert float(feat.X[0, feat.feature_names.index("struct::G1::exon")]) == pytest.approx(
        0.3, rel=1e-5, abs=1e-6
    )
    assert float(feat.X[0, feat.feature_names.index("struct::G2::intron")]) == pytest.approx(
        -0.2, rel=1e-5, abs=1e-6
    )
    assert feat.report["raw_mapped_feature_counts"]["structural"] == 3


def test_observed_feature_builder_dynamic_schema_is_deterministic(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_complete,
    )
    sample_paths = ["/tmp/S1", "/tmp/S2", "/tmp/S3", "/tmp/S4"]
    y = [0, 0, 1, 1]
    class_names = ["healthy", "cancer"]
    dmp_df = _dmp_df_with_mapped_features()
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
        feature_family_set="dmp+gene",
    )
    feat_b = observed_feature_builder.build_observed_hybrid_feature_table(
        sample_paths,
        dmp_df.sample(frac=1.0, random_state=11).reset_index(drop=True),
        healthy_reference_vector=anchors.healthy_reference_vector,
        cancer_reference_vector=anchors.cancer_reference_vector,
        healthy_class_label=anchors.healthy_class_label,
        cancer_class_labels=anchors.cancer_class_labels,
        anchor_strategy=anchors.anchor_strategy,
        expected_feature_order_fingerprint=anchors.feature_order_fingerprint,
        feature_family_set="dmp+gene",
    )
    assert feat_a.feature_names == feat_b.feature_names
    assert feat_a.report["schema_fingerprint"] == feat_b.report["schema_fingerprint"]


def test_family_flags_gene_scored_tokens():
    assert observed_feature_builder._family_flags("gene_scored") == (False, False, False, True)
    assert observed_feature_builder._family_flags("dmp+gene_scored") == (True, False, False, True)
    assert observed_feature_builder._family_flags("hybrid-all") == (True, True, True, False)


def test_gene_scored_feature_names_and_fingerprint():
    from methyl_validation.gene_scored_features import (
        compute_gene_directional_score_matrix,
        compute_region_directional_score_matrix,
        gene_scored_feature_column,
        prepare_gene_scored_panels,
        region_directional_feature_column,
    )

    dmp_df = pd.DataFrame(
        {
            "comparison_label": ["cmp_a", "cmp_a", "cmp_a", "cmp_b", "cmp_b"],
            "chromosome": ["1", "1", "1", "1", "1"],
            "context": ["CG", "CG", "CG", "CG", "CG"],
            "position": [100, 120, 200, 100, 120],
            "effect_size": [1.0, -1.0, 0.5, 1.0, -1.0],
            "gene_name": ["G1", "G1", "G2", "G1", "G1"],
            "feature_type": ["promoter", "exon", "intron", "promoter", "exon"],
            "region_weight": [1.0, 1.0, 1.0, 1.0, 1.0],
        }
    )
    frozen_panel = pd.DataFrame(
        {
            "comparison_label": ["cmp_a", "cmp_a", "cmp_a"],
            "gene_name": ["G1", "G2", "G3"],
            "gene_support_n": [2, 2, 1],
            "gene_importance": [1.0, 0.5, 0.9],
        }
    )
    names = observed_feature_builder.observed_hybrid_feature_names(
        feature_family_set="gene_scored",
        dmp_df=dmp_df,
        frozen_gene_panel_df=frozen_panel,
    )
    assert names == [
        "gene_directional_score__cmp_a",
        "region_directional_score__cmp_a__promoter",
        "region_directional_score__cmp_a__exon",
        "region_directional_score__cmp_a__intron",
    ]
    assert "gene::" not in names[0]

    fp_a = observed_feature_builder.observed_hybrid_schema_fingerprint(
        feature_family_set="gene_scored",
        dmp_df=dmp_df,
        frozen_gene_panel_df=frozen_panel,
        gene_scored_min_support_n=2,
    )
    fp_b = observed_feature_builder.observed_hybrid_schema_fingerprint(
        feature_family_set="gene_scored",
        dmp_df=dmp_df,
        frozen_gene_panel_df=frozen_panel,
        gene_scored_min_support_n=3,
    )
    fp_c = observed_feature_builder.observed_hybrid_schema_fingerprint(
        feature_family_set="gene_scored",
        dmp_df=dmp_df,
        frozen_gene_panel_df=frozen_panel,
        gene_scored_min_support_n=2,
        region_directional_region_types=["promoter", "exon"],
    )
    assert fp_a != fp_b
    assert fp_a != fp_c

    feature_order = [("1", "CG", 100), ("1", "CG", 120), ("1", "CG", 200)]
    X_raw = np.asarray([[0.10, 0.20, 0.30]], dtype=np.float64)
    panels = prepare_gene_scored_panels(frozen_panel, min_support_n=2)
    scores = compute_gene_directional_score_matrix(
        X_raw,
        feature_order,
        dmp_df,
        panels,
        ["cmp_a"],
        use_region_weight=True,
        gene_weight_mode="importance_x_sqrt_support",
    )
    assert scores.shape == (1, 1)
    assert float(scores[0, 0]) == pytest.approx(-0.1, rel=1e-5, abs=1e-6)
    region_matrix, region_specs = compute_region_directional_score_matrix(
        X_raw,
        feature_order,
        dmp_df,
        ["cmp_a", "cmp_b"],
        ["promoter", "exon"],
        min_loci=1,
        use_region_weight=True,
    )
    assert region_specs == [
        ("cmp_a", "promoter"),
        ("cmp_a", "exon"),
        ("cmp_b", "promoter"),
        ("cmp_b", "exon"),
    ]
    promo_idx = region_specs.index(("cmp_a", "promoter"))
    exon_idx = region_specs.index(("cmp_a", "exon"))
    assert float(region_matrix[0, promo_idx]) == pytest.approx(-0.4, rel=1e-5, abs=1e-6)
    assert float(region_matrix[0, exon_idx]) == pytest.approx(0.3, rel=1e-5, abs=1e-6)
    assert gene_scored_feature_column("cmp_a") == "gene_directional_score__cmp_a"
    assert region_directional_feature_column("cmp_a", "promoter") == "region_directional_score__cmp_a__promoter"


def test_compute_region_directional_score_matrix_hand_calculation():
    from methyl_validation.gene_scored_features import compute_region_directional_score_matrix

    dmp_df = pd.DataFrame(
        {
            "comparison_label": ["cmp_a", "cmp_a"],
            "chromosome": ["1", "1"],
            "context": ["CG", "CG"],
            "position": [100, 120],
            "effect_size": [1.0, -1.0],
            "feature_type": ["promoter", "promoter"],
            "region_weight": [1.0, 1.0],
        }
    )
    feature_order = [("1", "CG", 100), ("1", "CG", 120)]
    X_raw = np.asarray([[0.10, 0.20]], dtype=np.float64)
    matrix, specs = compute_region_directional_score_matrix(
        X_raw,
        feature_order,
        dmp_df,
        ["cmp_a"],
        ["promoter"],
        min_loci=1,
        use_region_weight=True,
    )
    assert specs == [("cmp_a", "promoter")]
    assert float(matrix[0, 0]) == pytest.approx(-0.05, rel=1e-5, abs=1e-6)


def _fake_extract_gene_scored(sample_paths, reference_positions, chromosome, min_coverage=1):
    del chromosome, min_coverage
    poss = []
    ctxs = []
    for ctx in sorted(reference_positions.keys()):
        for p in list(np.asarray(reference_positions[ctx], dtype=np.uint32)):
            ctxs.append(ctx)
            poss.append(int(p))
    rows = []
    for s in sample_paths:
        sid = Path(str(s)).name
        if sid in {"S1", "S2"}:
            vals = [0.10, 0.20, 0.30]
        else:
            vals = [0.70, 0.80, 0.90]
        rows.append(vals[: len(poss)])
    X = np.asarray(rows, dtype=np.float32)
    return (
        X,
        np.asarray(poss, dtype=np.uint32),
        np.asarray(ctxs, dtype=object),
        {"CG": np.arange(len(poss), dtype=np.uint32)},
    )


def test_observed_feature_builder_gene_scored_family(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_gene_scored,
    )
    dmp_df = pd.DataFrame(
        {
            "comparison_label": ["cmp_a", "cmp_a", "cmp_a"],
            "chromosome": ["1", "1", "1"],
            "context": ["CG", "CG", "CG"],
            "position": [100, 120, 200],
            "weight": [1.0, 1.0, 1.0],
            "effect_size": [1.0, -1.0, 0.5],
            "gene_name": ["G1", "G1", "G2"],
            "feature_type": ["promoter", "exon", "intron"],
        }
    )
    frozen_panel = pd.DataFrame(
        {
            "comparison_label": ["cmp_a", "cmp_a"],
            "gene_name": ["G1", "G2"],
            "gene_support_n": [2, 2],
            "gene_importance": [1.0, 0.5],
        }
    )
    sample_paths = ["/tmp/S1", "/tmp/S2", "/tmp/S3", "/tmp/S4"]
    y = [0, 0, 1, 1]
    class_names = ["healthy", "cancer"]
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
        feature_family_set="gene_scored",
        frozen_gene_panel_df=frozen_panel,
        gene_scored_min_support_n=2,
    )
    assert "gene_directional_score__cmp_a" in feat.feature_names
    assert "region_directional_score__cmp_a__promoter" in feat.feature_names
    assert not any(str(n).startswith("gene::") for n in feat.feature_names)
    gene_col = feat.feature_names.index("gene_directional_score__cmp_a")
    promo_col = feat.feature_names.index("region_directional_score__cmp_a__promoter")
    assert float(feat.X[0, gene_col]) == pytest.approx(-0.1, rel=1e-5, abs=1e-6)
    assert float(feat.X[0, promo_col]) == pytest.approx(-0.4, rel=1e-5, abs=1e-6)
    assert feat.report["feature_families"]["gene_scored"] is True
    assert feat.report["feature_families"]["gene"] is False


def test_observed_feature_builder_dmp_plus_gene_scored_includes_both_families(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_gene_scored,
    )
    dmp_df = pd.DataFrame(
        {
            "comparison_label": ["cmp_a", "cmp_a", "cmp_a"],
            "chromosome": ["1", "1", "1"],
            "context": ["CG", "CG", "CG"],
            "position": [100, 120, 200],
            "weight": [1.0, 1.0, 1.0],
            "effect_size": [1.0, -1.0, 0.5],
            "gene_name": ["G1", "G1", "G2"],
            "feature_type": ["promoter", "exon", "intron"],
        }
    )
    frozen_panel = pd.DataFrame(
        {
            "comparison_label": ["cmp_a", "cmp_a"],
            "gene_name": ["G1", "G2"],
            "gene_support_n": [2, 2],
            "gene_importance": [1.0, 0.5],
        }
    )
    sample_paths = ["/tmp/S1", "/tmp/S2"]
    y = [0, 1]
    class_names = ["healthy", "cancer"]
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
        feature_family_set="dmp+gene_scored",
        frozen_gene_panel_df=frozen_panel,
    )
    assert "max_weighted_directional_score" in feat.feature_names
    assert "gene_directional_score__cmp_a" in feat.feature_names
    assert not any(str(n).startswith("gene::") for n in feat.feature_names)
    assert "weighted_mean_abs_distance_margin" not in feat.feature_names
    assert "obs_fraction" in feat.feature_names
    assert "obs_fraction" not in feat.training_feature_names
    assert len(feat.training_feature_names) + len(feat.quality_feature_names) == len(feat.feature_names)
