"""
Optional STRING/PPI network utilities for module refinement.
"""

from __future__ import annotations

import io
import logging
from hashlib import sha1
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set
from urllib.error import URLError
from urllib.parse import quote_plus
from urllib.request import urlopen

import networkx as nx
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

STRING_NETWORK_API = "https://string-db.org/api/tsv/network"


def _cache_file_path(
    cache_path: str,
    genes: Sequence[str],
    species: int,
    required_score: float,
) -> Path:
    """
    Resolve cache file location.

    If cache_path ends with '.csv', it is treated as explicit file path.
    Otherwise cache_path is treated as a directory and a query-keyed file is used.
    """
    base = Path(cache_path)
    if base.suffix.lower() == ".csv":
        base.parent.mkdir(parents=True, exist_ok=True)
        return base
    base.mkdir(parents=True, exist_ok=True)
    key_payload = "|".join(
        [
            ",".join(sorted(normalize_gene_symbols(genes))),
            str(int(species)),
            f"{float(required_score):.4f}",
        ]
    )
    key = sha1(key_payload.encode("utf-8")).hexdigest()[:16]
    return base / f"string_edges_{key}.csv"


def normalize_gene_symbols(genes: Iterable[str]) -> List[str]:
    """Normalize symbols to upper-case, de-duplicated order-preserving list."""
    out: List[str] = []
    seen: Set[str] = set()
    for raw in genes:
        symbol = str(raw or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        out.append(symbol)
        seen.add(symbol)
    return out


def fetch_string_edges(
    genes: Sequence[str],
    species: int = 9606,
    required_score: float = 400.0,
    timeout_s: int = 20,
    cache_path: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch STRING edges for a gene symbol list.

    Returns columns: source, target, score.
    """
    gene_list = normalize_gene_symbols(genes)
    if len(gene_list) < 2:
        return pd.DataFrame(columns=["source", "target", "score"])

    cache_file: Optional[Path] = None
    if cache_path:
        cache_file = _cache_file_path(
            cache_path=cache_path,
            genes=gene_list,
            species=species,
            required_score=required_score,
        )
        if cache_file.exists():
            try:
                cached = load_local_edges(str(cache_file))
                cached = cached[
                    pd.to_numeric(cached["score"], errors="coerce").fillna(0.0)
                    >= float(required_score)
                ].copy()
                logger.info("Using cached STRING edges: %s", cache_file)
                return cached
            except Exception as exc:
                logger.warning("Failed to read STRING edge cache %s: %s", cache_file, exc)

    identifiers = "%0d".join(gene_list)
    query = (
        f"{STRING_NETWORK_API}?identifiers={quote_plus(identifiers)}"
        f"&species={int(species)}"
        "&caller_identity=methyl_enricher"
    )
    try:
        with urlopen(query, timeout=timeout_s) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except URLError as exc:
        logger.warning("STRING edge fetch failed: %s", exc)
        return pd.DataFrame(columns=["source", "target", "score"])
    except Exception as exc:
        logger.warning("STRING edge fetch failed: %s", exc)
        return pd.DataFrame(columns=["source", "target", "score"])

    if not raw.strip():
        return pd.DataFrame(columns=["source", "target", "score"])

    df = pd.read_csv(io.StringIO(raw), sep="\t")
    if df.empty:
        return pd.DataFrame(columns=["source", "target", "score"])

    # STRING network endpoint usually returns preferredName_A/B and score in [0, 1].
    src_col = "preferredName_A" if "preferredName_A" in df.columns else None
    dst_col = "preferredName_B" if "preferredName_B" in df.columns else None
    score_col = "score" if "score" in df.columns else None
    if not src_col or not dst_col or not score_col:
        return pd.DataFrame(columns=["source", "target", "score"])

    out = pd.DataFrame(
        {
            "source": df[src_col].astype(str).str.upper(),
            "target": df[dst_col].astype(str).str.upper(),
            "score": pd.to_numeric(df[score_col], errors="coerce").fillna(0.0),
        }
    )
    # Normalize score to [0,1000]-like scale for consistent threshold semantics.
    if float(out["score"].max()) <= 1.0:
        out["score"] = out["score"] * 1000.0
    out = out[out["score"] >= float(required_score)].copy()
    out = out[out["source"] != out["target"]].copy()
    out.drop_duplicates(subset=["source", "target"], inplace=True)
    out.reset_index(drop=True, inplace=True)
    if cache_file is not None:
        try:
            out.to_csv(cache_file, index=False)
            logger.info("Saved STRING edges cache: %s", cache_file)
        except Exception as exc:
            logger.warning("Failed to write STRING edge cache %s: %s", cache_file, exc)
    return out


def load_local_edges(path: str) -> pd.DataFrame:
    """
    Load local edge list CSV.

    Supported columns:
    - source,target[,score]
    - gene_a,gene_b[,score]
    """
    df = pd.read_csv(path)
    if df.empty:
        return pd.DataFrame(columns=["source", "target", "score"])

    if {"source", "target"}.issubset(df.columns):
        src_col, dst_col = "source", "target"
    elif {"gene_a", "gene_b"}.issubset(df.columns):
        src_col, dst_col = "gene_a", "gene_b"
    else:
        raise ValueError(
            "Local edge CSV must contain source/target or gene_a/gene_b columns."
        )

    score_col = "score" if "score" in df.columns else None
    out = pd.DataFrame(
        {
            "source": df[src_col].astype(str).str.upper(),
            "target": df[dst_col].astype(str).str.upper(),
            "score": (
                pd.to_numeric(df[score_col], errors="coerce").fillna(1000.0)
                if score_col
                else 1000.0
            ),
        }
    )
    out = out[out["source"] != out["target"]].copy()
    out.drop_duplicates(subset=["source", "target"], inplace=True)
    out.reset_index(drop=True, inplace=True)
    return out


def build_ppi_graph(
    edges_df: pd.DataFrame,
    genes: Sequence[str],
    min_component_size: int = 2,
) -> nx.Graph:
    """Build undirected weighted graph and retain only minimum-size components."""
    graph = nx.Graph()
    gene_nodes = normalize_gene_symbols(genes)
    graph.add_nodes_from(gene_nodes)
    if not edges_df.empty:
        for _, row in edges_df.iterrows():
            src = str(row["source"]).strip().upper()
            dst = str(row["target"]).strip().upper()
            if not src or not dst or src == dst:
                continue
            weight = float(pd.to_numeric(row.get("score", 0.0), errors="coerce") or 0.0)
            graph.add_edge(src, dst, weight=weight)

    if min_component_size and min_component_size > 1 and graph.number_of_nodes() > 0:
        keep_nodes: Set[str] = set()
        for comp in nx.connected_components(graph):
            if len(comp) >= int(min_component_size):
                keep_nodes.update(comp)
        # keep isolated nodes only when threshold is 1
        if keep_nodes:
            graph = graph.subgraph(keep_nodes).copy()
        else:
            graph = nx.Graph()
    return graph


def compute_network_metrics(graph: nx.Graph) -> pd.DataFrame:
    """Compute node-level centrality metrics."""
    if graph.number_of_nodes() == 0:
        return pd.DataFrame(
            columns=[
                "gene",
                "degree",
                "degree_centrality",
                "betweenness_centrality",
                "closeness_centrality",
            ]
        )

    degree = dict(graph.degree())
    degree_c = nx.degree_centrality(graph)
    betweenness = nx.betweenness_centrality(graph, normalized=True)
    closeness = nx.closeness_centrality(graph)
    rows = []
    for gene in graph.nodes():
        rows.append(
            {
                "gene": gene,
                "degree": float(degree.get(gene, 0.0)),
                "degree_centrality": float(degree_c.get(gene, 0.0)),
                "betweenness_centrality": float(betweenness.get(gene, 0.0)),
                "closeness_centrality": float(closeness.get(gene, 0.0)),
            }
        )
    df = pd.DataFrame(rows)
    df.sort_values(
        by=["degree_centrality", "betweenness_centrality", "closeness_centrality"],
        ascending=False,
        inplace=True,
    )
    df.reset_index(drop=True, inplace=True)
    return df


def rank_hubs(node_metrics: pd.DataFrame, top_k: int = 25) -> pd.DataFrame:
    """Return top central genes."""
    if node_metrics.empty:
        return node_metrics
    return node_metrics.head(top_k).copy()


def detect_communities(graph: nx.Graph, method: str = "louvain") -> Dict[str, int]:
    """Return node -> community id mapping."""
    if graph.number_of_nodes() == 0:
        return {}
    if method == "connected_components":
        communities = list(nx.connected_components(graph))
    elif method == "label_propagation":
        communities = list(nx.algorithms.community.label_propagation_communities(graph))
    else:
        # Default Louvain where available; fallback to greedy modularity if needed.
        try:
            communities = list(nx.algorithms.community.louvain_communities(graph, weight="weight"))
        except Exception:
            communities = list(nx.algorithms.community.greedy_modularity_communities(graph, weight="weight"))
    out: Dict[str, int] = {}
    for cid, members in enumerate(communities):
        for node in members:
            out[str(node)] = int(cid)
    return out


def _largest_component_ratio(subgraph: nx.Graph) -> float:
    if subgraph.number_of_nodes() == 0:
        return 0.0
    components = list(nx.connected_components(subgraph))
    if not components:
        return 0.0
    largest = max(len(c) for c in components)
    return float(largest) / float(subgraph.number_of_nodes())


def compute_module_coherence(
    pathway_to_module_id: Dict[str, int],
    pathway_to_genes: Dict[str, Set[str]],
    graph: nx.Graph,
    node_metrics: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute module-level PPI coherence metrics.

    Returns columns:
      module_id, ppi_coherence_score, ppi_density, ppi_mean_degree_centrality,
      ppi_largest_component_ratio, ppi_nodes, ppi_edges
    """
    metric_lookup: Dict[str, float] = {}
    if not node_metrics.empty and "gene" in node_metrics.columns:
        metric_lookup = {
            str(r["gene"]).upper(): float(r.get("degree_centrality", 0.0))
            for _, r in node_metrics.iterrows()
        }

    module_ids = sorted(set(pathway_to_module_id.values()))
    rows: List[Dict[str, float]] = []
    for module_id in module_ids:
        module_pathways = [p for p, m in pathway_to_module_id.items() if m == module_id]
        module_genes: Set[str] = set()
        for pathway in module_pathways:
            module_genes |= {g.upper() for g in pathway_to_genes.get(pathway, set())}
        existing_nodes = sorted(g for g in module_genes if graph.has_node(g))
        subgraph = graph.subgraph(existing_nodes).copy() if existing_nodes else nx.Graph()
        density = float(nx.density(subgraph)) if subgraph.number_of_nodes() > 1 else 0.0
        mean_centrality = (
            float(np.mean([metric_lookup.get(g, 0.0) for g in existing_nodes]))
            if existing_nodes
            else 0.0
        )
        lcc_ratio = _largest_component_ratio(subgraph)
        # Balanced coherence score in [0,1]
        coherence = float(np.clip(0.4 * density + 0.3 * mean_centrality + 0.3 * lcc_ratio, 0.0, 1.0))
        rows.append(
            {
                "module_id": int(module_id),
                "ppi_coherence_score": coherence,
                "ppi_density": density,
                "ppi_mean_degree_centrality": mean_centrality,
                "ppi_largest_component_ratio": lcc_ratio,
                "ppi_nodes": int(subgraph.number_of_nodes()),
                "ppi_edges": int(subgraph.number_of_edges()),
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out.sort_values("ppi_coherence_score", ascending=False, inplace=True)
        out.reset_index(drop=True, inplace=True)
    return out
