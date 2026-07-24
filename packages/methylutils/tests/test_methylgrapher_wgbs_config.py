"""Tests for methylGrapher WGBS site/resolvedConfig resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from methyl_utils.action_config_resolver import (
    resolve_methylgrapher_wgbs_genome,
    site_slice_for_action,
)


def test_missing_assets_raise_without_stock_fallback() -> None:
    site = {
        "pangenome_genome": {
            "gbz": "/stock.gbz",
            "dist": "/stock.dist",
            "min": "/stock.min",
            "zipcodes": "/stock.zip",
            "ref_paths": "/stock.paths",
            "linear_ref_fasta": "/stock.fa",
        }
    }
    with pytest.raises(RuntimeError, match="do not fall back|missing"):
        resolve_methylgrapher_wgbs_genome(site)


def test_site_slice_fills_from_pangenome_wgbs_genome() -> None:
    site = {
        "pangenome_wgbs_genome": {
            "c2t": {"gbz": "/c2t.gbz"},
            "linear_ref_fasta": "/lin.fa",
        }
    }
    out = site_slice_for_action(site, "methylgrapher_wgbs")
    assert out["linear_ref_fasta"] == "/lin.fa"
    assert out["c2t"]["gbz"] == "/c2t.gbz"


def test_resolved_config_wins(tmp_path: Path) -> None:
    for name in (
        "c2t.gbz",
        "c2t.dist",
        "c2t.min",
        "c2t.zip",
        "g2a.gbz",
        "g2a.dist",
        "g2a.min",
        "g2a.zip",
        "ref.paths",
        "cpg.tsv",
        "lin.fa",
    ):
        (tmp_path / name).write_text("x")
    cfg = {
        "c2t": {
            "gbz": str(tmp_path / "c2t.gbz"),
            "dist": str(tmp_path / "c2t.dist"),
            "min": str(tmp_path / "c2t.min"),
            "zipcodes": str(tmp_path / "c2t.zip"),
        },
        "g2a": {
            "gbz": str(tmp_path / "g2a.gbz"),
            "dist": str(tmp_path / "g2a.dist"),
            "min": str(tmp_path / "g2a.min"),
            "zipcodes": str(tmp_path / "g2a.zip"),
        },
        "ref_paths": str(tmp_path / "ref.paths"),
        "cpg_tsv": str(tmp_path / "cpg.tsv"),
        "linear_ref_fasta": str(tmp_path / "lin.fa"),
        "directional": False,
    }
    resolved = resolve_methylgrapher_wgbs_genome(resolved_config=cfg)
    assert resolved["directional"] is False
    assert resolved["c2t"]["gbz"].endswith("c2t.gbz")
