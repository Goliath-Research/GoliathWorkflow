"""Tests for pathway graph: canonical keys merge same-name pathways across libraries."""

import pandas as pd

from methyl_enricher.pathway_graph import (
    canonical_pathway_key,
    pathway_gene_sets_from_merged,
    run_pathway_clustering,
)


def test_canonical_pathway_key_case_and_whitespace():
    assert canonical_pathway_key("  Cell   Cycle  ") == canonical_pathway_key("cell cycle")
    assert canonical_pathway_key("Cell Cycle") == "cell cycle"


def test_pathway_gene_sets_merge_same_canonical_name():
    df = pd.DataFrame(
        {
            "Term": ["Cell Cycle", "cell cycle", "Other Pathway"],
            "Genes": ["A;B", "B;C", "X"],
        }
    )
    out = pathway_gene_sets_from_merged(df)
    assert set(out.keys()) == {"cell cycle", "other pathway"}
    assert out["cell cycle"] == {"A", "B", "C"}
    assert out["other pathway"] == {"X"}


def test_run_pathway_clustering_single_node_per_canonical_name():
    # Two library-style duplicates: same pathway, different casing → one graph node (one key)
    df = pd.DataFrame(
        {
            "Term": ["Apoptosis", "APOPTOSIS", "DNA Repair"],
            "Genes": ["A;B", "A;B", "C;D"],
            "Adjusted P-value": [0.01, 0.02, 0.01],
        }
    )
    part, pgenes = run_pathway_clustering(df, similarity_threshold=0.15, cluster_resolution=1.0)
    assert len(pgenes) == 2
    assert canonical_pathway_key("Apoptosis") in pgenes
    assert canonical_pathway_key("DNA Repair") in pgenes
    assert sum(1 for k in pgenes if k == "apoptosis") == 1
