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

