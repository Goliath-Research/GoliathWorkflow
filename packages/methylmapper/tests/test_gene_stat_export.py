from __future__ import annotations

import pandas as pd
import pytest

from methyl_mapper.bedtools_mapper import BedtoolsMapper


def test_aggregate_by_feature_exports_gene_p_and_q_columns_with_q_only_input():
    mapper = BedtoolsMapper.__new__(BedtoolsMapper)
    mapper.storey_lambda = None

    intersect_df = pd.DataFrame(
        {
            "gene_name": ["G1", "G1", "G2", "G2"],
            "dmp_name": ["d1", "d2", "d3", "d4"],
            "weight": [1.0, 2.0, 1.5, 2.5],
            "q_value": [0.01, 0.02, 0.05, 0.10],
            "delta_mean": [0.2, -0.3, 0.1, -0.2],
        }
    )

    grouped = BedtoolsMapper.aggregate_by_feature(mapper, intersect_df, group_by="gene_name")
    assert "gene_p_value" in grouped.columns
    assert "gene_q_value" in grouped.columns
    assert grouped["gene_p_value"].notna().any()


def test_aggregate_by_feature_exports_frequency_weighted_gene_score():
    mapper = BedtoolsMapper.__new__(BedtoolsMapper)
    mapper.storey_lambda = None

    intersect_df = pd.DataFrame(
        {
            "gene_name": ["G1", "G1", "G2"],
            "dmp_name": ["d1", "d2", "d3"],
            "weight": [1.0, 1.0, 1.0],
            "effect_size": [0.5, -0.2, 0.3],
            "frequency": [0.8, 0.6, 1.2],
            "region_weight": [2.0, 1.0, 0.5],
        }
    )

    grouped = BedtoolsMapper.aggregate_by_feature(mapper, intersect_df, group_by="gene_name")
    assert "gene_score" in grouped.columns
    scores = dict(zip(grouped["gene_name"], grouped["gene_score"]))
    assert scores["G1"] == pytest.approx((0.5 * 0.8 * 2.0) + (0.2 * 0.6 * 1.0))
    assert scores["G2"] == pytest.approx(0.3 * 1.2 * 0.5)


def test_aggregate_by_feature_uses_exclusive_feature_priority_for_hits_and_score():
    mapper = BedtoolsMapper.__new__(BedtoolsMapper)
    mapper.storey_lambda = None

    intersect_df = pd.DataFrame(
        {
            "gene_name": ["G1", "G1", "G1"],
            "dmp_name": ["d1", "d1", "d2"],
            "feature_type": ["gene_body", "exon", "intron"],
            "weight": [1.0, 1.0, 1.0],
            "effect_size": [0.5, 0.5, 0.4],
            "frequency": [0.8, 0.8, 0.9],
            "region_weight": [1.0, 1.5, 0.7],
        }
    )

    grouped = BedtoolsMapper.aggregate_by_feature(mapper, intersect_df, group_by="gene_name")
    row = grouped.iloc[0]
    assert row["hits_exon"] == 1
    assert row["hits_intron"] == 1
    assert row["hits_gene_body"] == 0
    assert row["gene_feature_score"] == pytest.approx((1 * 1.5) + (1 * 0.7))
    assert row["gene_score"] == pytest.approx((0.5 * 0.8 * 1.5) + (0.4 * 0.9 * 0.7))


def test_aggregate_by_feature_rejects_invalid_stability_frequency_values():
    mapper = BedtoolsMapper.__new__(BedtoolsMapper)
    mapper.storey_lambda = None

    intersect_df = pd.DataFrame(
        {
            "gene_name": ["G1"],
            "dmp_name": ["d1"],
            "feature_type": ["promoter"],
            "weight": [1.0],
            "effect_size": [0.5],
            "frequency": [1.2],
            "count": [12],
            "n_runs": [10],
            "region_weight": [2.0],
        }
    )

    with pytest.raises(ValueError, match="Invalid stability frequency values"):
        BedtoolsMapper.aggregate_by_feature(mapper, intersect_df, group_by="gene_name")

