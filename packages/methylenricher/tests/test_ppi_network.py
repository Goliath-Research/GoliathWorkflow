import pandas as pd

from methyl_enricher.ppi_network import (
    build_ppi_graph,
    compute_module_coherence,
    compute_network_metrics,
    detect_communities,
    fetch_string_edges,
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


class _FakeResponse:
    def __init__(self, payload: str):
        self._payload = payload.encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_fetch_string_edges_uses_cache(monkeypatch, tmp_path):
    tsv = "preferredName_A\tpreferredName_B\tscore\nTP53\tBRCA1\t0.91\n"
    monkeypatch.setattr("methyl_enricher.ppi_network.urlopen", lambda *_a, **_k: _FakeResponse(tsv))
    cache_dir = tmp_path / "string_cache"

    first = fetch_string_edges(
        genes=["TP53", "BRCA1"],
        required_score=400.0,
        cache_path=str(cache_dir),
    )
    assert len(first) == 1
    assert any(cache_dir.glob("string_edges_*.csv"))

    def _fail_open(*_args, **_kwargs):
        raise AssertionError("Network should not be called when cache exists.")

    monkeypatch.setattr("methyl_enricher.ppi_network.urlopen", _fail_open)
    second = fetch_string_edges(
        genes=["BRCA1", "TP53"],  # same set, different order
        required_score=400.0,
        cache_path=str(cache_dir),
    )
    assert len(second) == 1
    assert set(second.columns) == {"source", "target", "score"}
