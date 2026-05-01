from __future__ import annotations

import pandas as pd

from methyl_enricher.enricher import EnrichmentAnalyzer


def test_gene_feature_score_is_used_as_default_weight_without_recompute():
    analyzer = EnrichmentAnalyzer(libraries=["GO_Biological_Process_2023"])
    df = pd.DataFrame(
        {
            "gene_name": ["G1"],
            "hits_promoter": [1],
            "hits_exon": [2],
            "hits_intron": [3],
            "hits_gene_body": [4],
            "hits_terminator": [5],
            "gene_feature_score": [42.5],
            "total_weight": [999.0],
        }
    )
    out = analyzer._apply_csv_filters(df)
    row = out.iloc[0]
    assert "feature_weight_score" not in out.columns
    assert analyzer._gene_weight_from_row(row) == 42.5


def test_hits_filter_removes_rows_without_any_hits():
    analyzer = EnrichmentAnalyzer(libraries=["GO_Biological_Process_2023"])
    df = pd.DataFrame(
        {
            "gene_name": ["G1", "G2"],
            "hits_promoter": [0, 1],
            "hits_exon": [0, 0],
            "hits_intron": [0, 0],
            "hits_gene_body": [0, 0],
            "hits_terminator": [0, 0],
        }
    )
    out = analyzer._apply_csv_filters(df)
    assert out["gene_name"].tolist() == ["G2"]
