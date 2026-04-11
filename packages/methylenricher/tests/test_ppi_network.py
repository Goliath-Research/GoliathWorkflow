import pandas as pd

from methyl_enricher.ppi_network import (
    build_ppi_graph,
    compute_module_coherence,
    compute_network_metrics,
    detect_communities,
    load_local_edges,
    normalize_gene_symbols,
)


def test_normalize_gene_symbols_deduplicates_and_upcases():
    genes = ["tp53", " TP53 ", "", None, "brca1"]
    assert normalize_gene_symbols(genes) == ["TP53", "BRCA1"]


def test_load_local_edges_supports_source_target(tmp_path):
    path = tmp_path / "edges.csv"
    path.write_text("source,target,score\nTP53,BRCA1,700\nBRCA1,EGFR,450\n", encoding="utf-8")
    df = load_local_edges(str(path))
    assert list(df.columns) == ["source", "target", "score"]
    assert len(df) == 2
    assert set(df["source"]) == {"TP53", "BRCA1"}


def test_compute_module_coherence_outputs_expected_columns():
    edges = pd.DataFrame(
        [
            {"source": "TP53", "target": "BRCA1", "score": 700},
            {"source": "BRCA1", "target": "EGFR", "score": 650},
        ]
    )
    graph = build_ppi_graph(edges, genes=["TP53", "BRCA1", "EGFR"], min_component_size=2)
    node_metrics = compute_network_metrics(graph)
    communities = detect_communities(graph, method="connected_components")
    assert set(communities.keys()) == {"TP53", "BRCA1", "EGFR"}

    pathway_to_module_id = {"dna repair": 0, "growth": 1}
    pathway_to_genes = {"dna repair": {"TP53", "BRCA1"}, "growth": {"EGFR"}}
    module_df = compute_module_coherence(
        pathway_to_module_id=pathway_to_module_id,
        pathway_to_genes=pathway_to_genes,
        graph=graph,
        node_metrics=node_metrics,
    )
    assert not module_df.empty
    assert {
        "module_id",
        "ppi_coherence_score",
        "ppi_density",
        "ppi_mean_degree_centrality",
        "ppi_largest_component_ratio",
        "ppi_nodes",
        "ppi_edges",
    }.issubset(set(module_df.columns))
