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
        base = 0.2 if sid.endswith("1") else 0.8
        rows.append([base for _ in poss])
    X = np.asarray(rows, dtype=np.float32)
    return (
        X,
        np.asarray(poss, dtype=np.uint32),
        np.asarray(ctxs, dtype=object),
        {"CG": np.arange(len(poss), dtype=np.uint32)},
    )


def test_observed_feature_schema_is_deterministic(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_complete,
    )
    sample_paths = ["/tmp/S1", "/tmp/S2"]
    dmp_df = pd.DataFrame(
        {
            "chromosome": ["2", "1", "1", "2"],
            "context": ["CG", "CHG", "CG", "CG"],
            "position": [200, 120, 100, 220],
            "weight": [0.8, 0.6, 1.0, 0.4],
            "effect_size": [0.8, 0.6, 1.0, 0.4],
        }
    )
    feat_a = observed_feature_builder.build_observed_hybrid_feature_table(sample_paths, dmp_df)
    feat_b = observed_feature_builder.build_observed_hybrid_feature_table(
        sample_paths, dmp_df.sample(frac=1.0, random_state=13).reset_index(drop=True)
    )
    assert feat_a.feature_names == feat_b.feature_names
    assert feat_a.report["schema_fingerprint"] == feat_b.report["schema_fingerprint"]
    assert feat_a.X.shape == feat_b.X.shape


def test_observed_feature_builder_keeps_missing_loci_as_nan(monkeypatch):
    def _fake_extract_missing(sample_paths, reference_positions, chromosome, min_coverage=1):
        del chromosome, min_coverage
        # Return only one locus even if more were requested to simulate partial observation.
        pos = np.asarray([int(np.asarray(reference_positions["CG"])[0])], dtype=np.uint32)
        ctx = np.asarray(["CG"], dtype=object)
        X = np.asarray([[0.25], [0.75]], dtype=np.float32)
        return X, pos, ctx, {"CG": np.arange(1, dtype=np.uint32)}

    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_missing,
    )
    dmp_df = pd.DataFrame(
        {
            "chromosome": ["1", "1", "1"],
            "context": ["CG", "CG", "CG"],
            "position": [100, 120, 140],
            "weight": [1.0, 1.0, 1.0],
            "effect_size": [1.0, 1.0, 1.0],
        }
    )
    feat = observed_feature_builder.build_observed_hybrid_feature_table(["/tmp/S1", "/tmp/S2"], dmp_df)
    obs_idx = feat.feature_names.index("obs_fraction")
    total_idx = feat.feature_names.index("n_total_dmps")
    # One observed out of three total loci.
    assert np.allclose(feat.X[:, obs_idx], np.asarray([1.0 / 3.0, 1.0 / 3.0], dtype=np.float32), atol=1e-5)
    assert np.allclose(feat.X[:, total_idx], np.asarray([3.0, 3.0], dtype=np.float32), atol=1e-6)


def test_verify_feature_schema_raises_on_mismatch():
    with pytest.raises(ValueError, match="schema mismatch"):
        observed_feature_builder.verify_feature_schema(
            ["a", "b", "c"],
            ["a", "x", "c"],
            context="unit-test",
        )


def test_observed_feature_builder_adds_disease_dmr_gene_families(monkeypatch):
    monkeypatch.setattr(
        observed_feature_builder.MethylCentroidPair,
        "extract_methylation_fractions",
        _fake_extract_complete,
    )
    dmp_df = pd.DataFrame(
        {
            "comparison_label": ["healthy_vs_pca1", "healthy_vs_pca2", "healthy_vs_pca1", "healthy_vs_pca2"],
            "chromosome": ["1", "1", "2", "2"],
            "context": ["CG", "CG", "CG", "CG"],
            "position": [100, 120, 220, 260],
            "weight": [1.0, 0.9, 0.8, 0.7],
            "effect_size": [1.0, 0.9, 0.8, 0.7],
            "gene_name": ["TP53", "BRCA1", "TP53", "MYC"],
            "dmr_region": ["R1", "R2", "R1", "R3"],
        }
    )
    feat = observed_feature_builder.build_observed_hybrid_feature_table(
        ["/tmp/S1", "/tmp/S2"],
        dmp_df,
        max_dmr_features=2,
        max_gene_features=2,
    )
    assert "disease_healthy_vs_pca1_weighted_mean" in feat.feature_names
    assert "dmr_R1_weighted_mean" in feat.feature_names
    assert "gene_TP53_weighted_mean" in feat.feature_names
    assert feat.report["feature_families"]["dmr"] is True
    assert feat.report["feature_families"]["gene"] is True
    assert len(feat.report["selected_dmrs"]) == 2
    assert len(feat.report["selected_genes"]) == 2
