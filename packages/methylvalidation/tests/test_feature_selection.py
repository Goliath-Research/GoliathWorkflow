from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from methyl_validation.feature_selection import (
    _feature_family_from_name,
    normalize_runtime_feature_selection_config,
    run_feature_selection_artifacts,
    select_training_features,
)


def test_feature_family_from_name_recognizes_gene_scored_columns():
    assert _feature_family_from_name("gene_directional_score__cmp_a") == "gene_scored"
    assert _feature_family_from_name("region_directional_score__cmp_a__promoter") == "gene_scored"


def test_select_training_features_respects_cap_and_returns_indices():
    X = np.asarray(
        [
            [0.1, 0.2, 0.9, 0.8],
            [0.2, 0.1, 0.8, 0.7],
            [0.8, 0.9, 0.2, 0.1],
            [0.7, 0.8, 0.1, 0.2],
        ],
        dtype=np.float32,
    )
    y = np.asarray([0, 0, 1, 1], dtype=np.int32)
    feature_names = ["1:100:CG", "1:120:CG", "gene::TP53", "struct::TP53::promoter"]
    cfg = normalize_runtime_feature_selection_config(
        {"enabled": True, "max_features_total": 2, "feature_families": ["dmp", "gene", "structural"]}
    )
    out = select_training_features(X, y, feature_names, cfg)
    assert out["report"]["enabled"] is True
    assert len(out["selected_indices"]) <= 2
    assert all(0 <= int(i) < len(feature_names) for i in out["selected_indices"])


def test_run_feature_selection_artifacts_writes_manifest_and_tables(tmp_path: Path):
    production_dir = tmp_path / "production"
    production_dir.mkdir(parents=True)
    bundle_dir = production_dir / "model_bundle"
    bundle_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "chromosome": ["1", "1"],
            "position": [100, 120],
            "context": ["CG", "CG"],
            "effect_size": [0.9, 0.3],
        }
    ).to_csv(production_dir / "stable_dmps_genomewide.csv", index=False)
    pd.DataFrame(
        {
            "comparison_label": ["healthy_vs_pca1", "healthy_vs_pca1"],
            "chromosome": ["1", "1"],
            "position": [100, 120],
            "context": ["CG", "CG"],
            "gene_name": ["TP53", "MYC"],
            "effect_size": [0.9, 0.3],
        }
    ).to_csv(bundle_dir / "mapper_dmp_annotations.csv", index=False)
    pd.DataFrame(
        {
            "comparison_label": ["healthy_vs_pca1", "healthy_vs_pca1"],
            "gene_name": ["TP53", "MYC"],
            "gene_importance": [2.0, 1.0],
        }
    ).to_csv(bundle_dir / "frozen_genes_production.csv", index=False)
    pd.DataFrame(
        {
            "comparison_label": ["healthy_vs_pca1"],
            "gene_name": ["TP53"],
            "chromosome": ["1"],
            "feature_type": ["promoter"],
            "feature_start": [90],
            "feature_end": [130],
            "n_dmps_in_feature": [2],
            "feature_effect_compound": [1.2],
        }
    ).to_csv(bundle_dir / "frozen_gene_features.csv", index=False)

    out = run_feature_selection_artifacts(
        production_dir=production_dir,
        config_payload={"enabled": True, "max_features_total": 5},
        training_partition_ids=["S1", "S2"],
    )
    manifest_path = Path(out["manifest_path"])
    assert manifest_path.is_file()
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["schema_version"] == "feature_selection_v1"
    assert manifest["counts"]["selected_features_total"] >= 1
    assert Path(out["selected_dmps_path"]).is_file()
    assert Path(out["selected_features_path"]).is_file()
