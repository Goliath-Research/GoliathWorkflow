"""Tests for enricher completeness helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from methyl_enricher.enricher_completeness import (
    RetryPolicy,
    assess_completeness,
    classify_enrich_error,
    enrich_one_library,
    is_retryable,
    merge_library_results,
    EnrichErrorKind,
)


def test_classify_enrich_error_429():
    assert classify_enrich_error(Exception("status code: 429")) == EnrichErrorKind.RATE_LIMITED


def test_merge_library_results_from_csvs(tmp_path: Path):
    lib = "KEGG_2021_Human"
    df = pd.DataFrame(
        {
            "Term": ["pathway_a"],
            "Adjusted P-value": [0.01],
            "P-value": [0.001],
            "Odds Ratio": [2.0],
        }
    )
    df.to_csv(tmp_path / f"enrich_{lib}.csv", index=False)
    merged = merge_library_results(tmp_path, [lib], cutoff=0.05)
    assert len(merged) == 1
    assert (tmp_path / "enrichment_merged.csv").is_file()


def test_assess_completeness_detects_missing(tmp_path: Path):
    libs = ["KEGG_2021_Human", "Reactome_2022"]
    (tmp_path / "enrich_KEGG_2021_Human.csv").write_text("Term\nx\n", encoding="utf-8")
    report = assess_completeness(tmp_path, libs, modules_required=False)
    assert not report.complete
    assert "Reactome_2022" in report.missing_libraries


def test_enrich_one_library_retries_then_succeeds(tmp_path: Path):
    policy = RetryPolicy(max_retries=2, base_seconds=0.01, max_seconds=0.05, inter_library_delay_seconds=0)
    mock_df = pd.DataFrame(
        {
            "Term": ["t1"],
            "Adjusted P-value": [0.01],
            "P-value": [0.001],
            "Odds Ratio": [1.5],
        }
    )
    mock_enr = MagicMock()
    mock_enr.results = mock_df

    calls = {"n": 0}

    def fake_enrichr(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("status code: 429")
        return mock_enr

    with patch("gseapy.enrichr", side_effect=fake_enrichr):
        res = enrich_one_library(
            "KEGG_2021_Human",
            ["BRCA1", "TP53"],
            tmp_path,
            policy=policy,
        )
    assert res.success
    assert res.attempts == 2
    assert is_retryable(EnrichErrorKind.RATE_LIMITED)
