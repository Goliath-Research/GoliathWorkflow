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


def test_aggregate_by_feature_exports_feature_effect_sizes_and_weighted_gene_importance():
    mapper = BedtoolsMapper.__new__(BedtoolsMapper)
    mapper.storey_lambda = None
    mapper.w_promoter = 2.0
    mapper.w_terminator = 0.5
    mapper.w_gene_body = 1.0
    mapper.w_exon = 1.5
    mapper.w_intron = 0.7

    intersect_df = pd.DataFrame(
        {
            "gene_name": ["G1", "G1", "G1", "G2"],
            "dmp_name": ["d1", "d2", "d3", "d4"],
            "feature_type": ["exon", "exon", "promoter", "intron"],
            "feature_start": [10, 10, 1, 20],
            "feature_end": [20, 20, 5, 30],
            "weight": [1.0, 1.0, 1.0, 1.0],
            "effect_size": [0.5, -0.2, 0.4, -0.3],
            "frequency": [1.0, 1.0, 1.0, 1.0],
            "region_weight": [1.5, 1.5, 2.0, 0.7],
        }
    )

    grouped = BedtoolsMapper.aggregate_by_feature(mapper, intersect_df, group_by="gene_name")
    row_g1 = grouped[grouped["gene_name"] == "G1"].iloc[0]
    # Exon directionalization: raw=0.7, signed=0.3 => balance=3/7 => effect=0.3
    assert row_g1["effect_size_exon"] == pytest.approx(0.3)
    assert row_g1["direction_exon"] == pytest.approx(1.0)
    # Segment-first: one exon segment keeps unit balance after segment-level penalty.
    assert row_g1["direction_balance_exon"] == pytest.approx(1.0)
    # Promoter has coherent positive direction.
    assert row_g1["effect_size_promoter"] == pytest.approx(0.4)
    assert row_g1["direction_promoter"] == pytest.approx(1.0)
    # Weighted whole-gene canonical importance.
    assert row_g1["gene_feature_importance"] == pytest.approx((2.0 * 0.4) + (1.5 * 0.3))
    assert row_g1["gene_effect_abs_wmean"] == pytest.approx(0.37)
    assert row_g1["gene_direction_coherence"] == pytest.approx(1.25 / 1.85)
    assert row_g1["gene_effect_compound_v1"] == pytest.approx(0.25)
    assert row_g1["gene_importance"] == pytest.approx(row_g1["gene_effect_compound_v1"])


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
    assert row["effect_size_gene_body"] == pytest.approx(0.0)


def test_aggregate_by_feature_segment_first_exon_scoring_penalizes_conflicting_segments():
    mapper = BedtoolsMapper.__new__(BedtoolsMapper)
    mapper.storey_lambda = None
    mapper.w_promoter = 2.0
    mapper.w_terminator = 0.5
    mapper.w_gene_body = 1.0
    mapper.w_exon = 1.5
    mapper.w_intron = 0.7

    intersect_df = pd.DataFrame(
        {
            "gene_name": ["G1", "G1", "G1"],
            "dmp_name": ["d1", "d2", "d3"],
            "feature_type": ["exon", "exon", "exon"],
            "feature_start": [10, 10, 100],
            "feature_end": [20, 20, 120],
            "weight": [1.0, 1.0, 1.0],
            "effect_size": [0.6, -0.2, -0.5],
        }
    )

    grouped = BedtoolsMapper.aggregate_by_feature(mapper, intersect_df, group_by="gene_name")
    row = grouped.iloc[0]
    # Segment 1 (10-20): raw=0.8, signed=0.4 => seg_effect=0.4, dir=+1
    # Segment 2 (100-120): raw=0.5, signed=-0.5 => seg_effect=0.5, dir=-1
    # Feature aggregate: raw=0.9, signed=-0.1 => balance=1/9, effect=0.1, dir=-1
    assert row["effect_size_exon"] == pytest.approx(0.1, abs=1e-12)
    assert row["direction_exon"] == pytest.approx(-1.0)
    assert row["direction_balance_exon"] == pytest.approx(1.0 / 9.0)


def test_aggregate_by_feature_sorts_by_canonical_gene_importance_desc():
    mapper = BedtoolsMapper.__new__(BedtoolsMapper)
    mapper.storey_lambda = None
    mapper.w_promoter = 2.0
    mapper.w_terminator = 0.5
    mapper.w_gene_body = 1.0
    mapper.w_exon = 1.5
    mapper.w_intron = 0.7

    intersect_df = pd.DataFrame(
        {
            "gene_name": ["G_low", "G_high"],
            "dmp_name": ["d1", "d2"],
            "feature_type": ["promoter", "promoter"],
            "feature_start": [1, 1],
            "feature_end": [10, 10],
            "weight": [1.0, 1.0],
            "effect_size": [0.1, 0.4],
        }
    )

    grouped = BedtoolsMapper.aggregate_by_feature(mapper, intersect_df, group_by="gene_name")
    assert grouped.iloc[0]["gene_name"] == "G_high"
    assert grouped.iloc[0]["gene_importance"] > grouped.iloc[1]["gene_importance"]


def test_aggregate_by_feature_exports_compound_v1_columns():
    mapper = BedtoolsMapper.__new__(BedtoolsMapper)
    mapper.storey_lambda = None
    mapper.w_promoter = 2.0
    mapper.w_terminator = 0.5
    mapper.w_gene_body = 1.0
    mapper.w_exon = 1.5
    mapper.w_intron = 0.7

    intersect_df = pd.DataFrame(
        {
            "gene_name": ["G1", "G1", "G1"],
            "dmp_name": ["d1", "d2", "d3"],
            "feature_type": ["promoter", "exon", "intron"],
            "feature_start": [1, 10, 30],
            "feature_end": [5, 20, 40],
            "weight": [1.0, 1.0, 1.0],
            "effect_size": [0.6, 0.2, 0.1],
            "delta_mean": [0.6, 0.2, 0.1],
            "frequency": [1.0, 0.8, 0.9],
            "region_weight": [2.0, 1.5, 0.7],
        }
    )

    grouped = BedtoolsMapper.aggregate_by_feature(mapper, intersect_df, group_by="gene_name")
    row = grouped.iloc[0]
    assert "gene_effect_abs_wmean" in grouped.columns
    assert "gene_effect_abs_wsum" in grouped.columns
    assert "gene_direction_coherence" in grouped.columns
    assert "gene_support_n" in grouped.columns
    assert "gene_support_freq" in grouped.columns
    assert "gene_effect_compound_v1" in grouped.columns
    assert "gene_feature_effect_compound_v1" in grouped.columns
    assert row["gene_support_n"] == 3
    assert row["gene_effect_compound_v1"] > 0.0


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


def test_aggregate_by_feature_rolls_up_non_exposed_detailed_features_to_parent_buckets():
    mapper = BedtoolsMapper.__new__(BedtoolsMapper)
    mapper.storey_lambda = None
    mapper._explicit_feature_labels = set()
    mapper.w_promoter = 2.0
    mapper.w_terminator = 0.5
    mapper.w_gene_body = 1.0
    mapper.w_exon = 1.5
    mapper.w_intron = 0.7

    intersect_df = pd.DataFrame(
        {
            "gene_name": ["G1", "G1"],
            "dmp_name": ["d1", "d2"],
            "feature_type": ["CDS", "five_prime_UTR"],
            "feature_start": [10, 30],
            "feature_end": [20, 40],
            "weight": [1.0, 1.0],
            "effect_size": [0.6, 0.2],
            "frequency": [1.0, 1.0],
            "region_weight": [1.5, 1.5],
        }
    )

    grouped = BedtoolsMapper.aggregate_by_feature(mapper, intersect_df, group_by="gene_name")
    row = grouped.iloc[0]
    assert row["hits_exon"] == 2
    assert row["effect_size_exon"] == pytest.approx(0.8)
    assert row["gene_score"] == pytest.approx((0.6 * 1.0 * 1.5) + (0.2 * 1.0 * 1.5))


def test_aggregate_by_feature_rolls_up_transcript_to_gene_body_when_not_exposed():
    mapper = BedtoolsMapper.__new__(BedtoolsMapper)
    mapper.storey_lambda = None
    mapper._explicit_feature_labels = set()
    mapper.w_promoter = 2.0
    mapper.w_terminator = 0.5
    mapper.w_gene_body = 1.0
    mapper.w_exon = 1.5
    mapper.w_intron = 0.7

    intersect_df = pd.DataFrame(
        {
            "gene_name": ["G2"],
            "dmp_name": ["d10"],
            "feature_type": ["transcript"],
            "weight": [1.0],
            "effect_size": [0.4],
            "frequency": [1.0],
            "region_weight": [1.0],
        }
    )

    grouped = BedtoolsMapper.aggregate_by_feature(mapper, intersect_df, group_by="gene_name")
    row = grouped.iloc[0]
    assert row["hits_gene_body"] == 1
    assert row["effect_size_gene_body"] == pytest.approx(0.4)


def test_aggregate_by_feature_preserves_explicit_detailed_feature_label_for_identity():
    mapper = BedtoolsMapper.__new__(BedtoolsMapper)
    mapper.storey_lambda = None
    mapper._explicit_feature_labels = {"cds"}
    mapper.w_promoter = 2.0
    mapper.w_terminator = 0.5
    mapper.w_gene_body = 1.0
    mapper.w_exon = 1.5
    mapper.w_intron = 0.7

    # group_by=feature_type validates that explicit detailed labels stay visible as output identity.
    intersect_df = pd.DataFrame(
        {
            "feature_type": ["CDS"],
            "gene_name": ["G1"],
            "dmp_name": ["d1"],
            "weight": [1.0],
            "effect_size": [0.6],
            "frequency": [1.0],
            "region_weight": [1.5],
        }
    )

    grouped = BedtoolsMapper.aggregate_by_feature(mapper, intersect_df, group_by="feature_type")
    assert grouped.iloc[0]["feature_type"] == "CDS"
    assert grouped.iloc[0]["gene_score"] == pytest.approx(0.6 * 1.0 * 1.5)

