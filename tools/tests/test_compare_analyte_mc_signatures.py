"""Tests for analyte MC signature recurrence helper."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compare_analyte_mc_signatures import (
    _load_signature_genes,
    _overlap_metrics,
    filter_mapper_genes,
)


def test_overlap_metrics_prefers_plasma_signature():
    plasma_sig = {"AR", "KLK3", "TMPRSS2"}
    buffy_sig = {"DMD", "PCDH11X", "NLGN4X"}
    m = _overlap_metrics(["AR", "DMD", "ZZZ"], plasma_sig, buffy_sig)
    assert m["plasma_sig_overlap"] == 1
    assert m["buffy_sig_overlap"] == 1
    assert m["dominant_signature"] == "tie"


def test_filter_mapper_genes_disease_only(tmp_path: Path):
    mapper = tmp_path / "genes.csv"
    mapper.write_text(
        "gene_name,gene_importance,unique_dmps,disease_associated,disease_evidence_level\n"
        "AR,10,5,True,medium\n"
        "DMD,50,10,False,low\n"
        "KLK3,8,3,True,low\n",
        encoding="utf-8",
    )
    df = pd.read_csv(mapper)
    genes = filter_mapper_genes(
        df,
        disease_only=True,
        min_disease_evidence_level="low",
        min_dmp_count=2,
        sort_by="gene_importance",
        top_n=10,
    )
    assert genes == ["AR", "KLK3"]


def test_load_signature_genes(tmp_path: Path):
    hubs = tmp_path / "hubs.csv"
    hubs.write_text("gene,combined_hub_score\nAR,1.0\nKLK3,0.9\n", encoding="utf-8")
    assert _load_signature_genes(hubs, 1) == ["AR"]


def test_filter_mapper_genes_association_type_string_not_characters():
    df = pd.DataFrame(
        {
            "gene_name": ["AR", "KLK3", "DMD"],
            "gene_importance": [10, 8, 50],
            "disease_association_type": ["direct", "indirect", "direct"],
        }
    )
    genes = filter_mapper_genes(
        df,
        disease_association_types="direct",
        sort_by="gene_importance",
        top_n=10,
    )
    assert genes == ["DMD", "AR"]
