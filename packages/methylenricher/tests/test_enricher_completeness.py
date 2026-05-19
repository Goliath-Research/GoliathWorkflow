"""Tests for enricher completeness helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from methyl_enricher.enricher_completeness import (
    COMPLETENESS_MANIFEST_FILENAME,
    CompletenessReport,
    RetryPolicy,
    assess_completeness,
    classify_enrich_error,
    completeness_manifest_path,
    enrich_one_library,
    is_retryable,
    merge_library_results,
    production_enricher_root,
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


def test_production_enricher_root_not_control_subdir(tmp_path: Path):
    """Manifest and queue must live under enricher/, not enricher/<control_group>/."""
    sample_csv = tmp_path / "PCa1.csv"
    sample_csv.write_text("sample_id\ns1\n", encoding="utf-8")
    healthy_csv = tmp_path / "healthy.csv"
    healthy_csv.write_text("sample_id\nh1\n", encoding="utf-8")
    prod_dir = tmp_path / "production"
    proj = {
        "project_name": "production",
        "output_base": str(tmp_path),
        "controls": {
            "label": "healthy",
            "groups": [{"label": "all", "sample_paths": [str(healthy_csv)]}],
        },
        "diseases": {
            "label": "cancer",
            "groups": [
                {
                    "label": "PCa",
                    "stages": [{"label": "PCa1", "sample_paths": [str(sample_csv)]}],
                }
            ],
        },
        "comparisons": "control_vs_each_disease",
    }
    prod_dir.mkdir(parents=True)
    project_json = prod_dir / "project.json"
    project_json.write_text(json.dumps(proj), encoding="utf-8")

    root = production_enricher_root(project_json)
    assert root == prod_dir / "enricher"
    assert root != prod_dir / "enricher" / "all"

    manifest = completeness_manifest_path(project_json)
    assert manifest == prod_dir / "enricher" / COMPLETENESS_MANIFEST_FILENAME

    from methyl_enricher.ensure_complete import write_project_completeness_manifest

    write_project_completeness_manifest(
        project_json,
        {
            "PCa_PCa1": CompletenessReport(
                output_dir=str(prod_dir / "enricher" / "all" / "PCa_PCa1"),
                expected_libraries=["KEGG_2021_Human"],
                present_libraries=["KEGG_2021_Human"],
                missing_libraries=[],
                modules_required=False,
                modules_present=False,
                complete=True,
            )
        },
    )
    assert manifest.is_file()
    assert not (prod_dir / "enricher" / "all" / COMPLETENESS_MANIFEST_FILENAME).is_file()


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
