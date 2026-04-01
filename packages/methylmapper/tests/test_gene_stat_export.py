from __future__ import annotations

import pandas as pd

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

