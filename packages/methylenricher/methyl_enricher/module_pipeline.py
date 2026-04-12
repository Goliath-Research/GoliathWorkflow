"""
Pathway-to-module pipeline: run enrichment, normalize pathway names, cluster pathways
into modules, score/rank modules, and write modules_ranked.csv.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from .enricher import EnrichmentAnalyzer
from .pathway_normalizer import PathwayNormalizer, load_theme_extras
from .pathway_graph import canonical_pathway_key, run_pathway_clustering
from .module_scorer import score_and_rank_modules, DEFAULT_PCA_RELEVANT_GENES
from . import module_network_plot
from .ppi_network import (
    build_ppi_graph,
    compute_module_coherence,
    compute_network_metrics,
    detect_communities,
    fetch_string_edges,
    load_local_edges,
    rank_hubs,
)

logger = logging.getLogger(__name__)

OVERLAP_GENES_CAP = 50


def _reduce_terms_for_clustering(
    merged_df: pd.DataFrame,
    *,
    max_q: Optional[float] = None,
    top_terms_per_library: Optional[int] = None,
) -> pd.DataFrame:
    """
    Reduce enrichment terms before pathway clustering.

    This keeps enrichment exports untouched while allowing module construction
    to operate on a more focused term set when large library presets are used.
    """
    if merged_df.empty:
        return merged_df

    work = merged_df.copy()
    q_col = "Adjusted P-value" if "Adjusted P-value" in work.columns else None

    if max_q is not None and q_col is not None:
        q = pd.to_numeric(work[q_col], errors="coerce")
        work = work[q <= max_q].copy()

    if top_terms_per_library is not None and top_terms_per_library > 0 and "library" in work.columns:
        sort_cols: List[str] = []
        ascending: List[bool] = []
        if q_col is not None:
            work["_adj_q"] = pd.to_numeric(work[q_col], errors="coerce").fillna(1.0)
            sort_cols.append("_adj_q")
            ascending.append(True)
        if "P-value" in work.columns:
            work["_pval"] = pd.to_numeric(work["P-value"], errors="coerce").fillna(1.0)
            sort_cols.append("_pval")
            ascending.append(True)
        if "Combined Score" in work.columns:
            work["_combined_score"] = pd.to_numeric(work["Combined Score"], errors="coerce").fillna(0.0)
            sort_cols.append("_combined_score")
            ascending.append(False)

        if sort_cols:
            work = work.sort_values(sort_cols, ascending=ascending)
        work = (
            work.groupby("library", as_index=False, group_keys=False)
            .head(top_terms_per_library)
            .copy()
        )

    drop_cols = [c for c in ["_adj_q", "_pval", "_combined_score"] if c in work.columns]
    if drop_cols:
        work = work.drop(columns=drop_cols)
    return work


def _overlap_genes_str(module_genes: Set[str], cap: int = OVERLAP_GENES_CAP) -> str:
    """Comma-separated overlap genes for the module, optionally capped for readability."""
    genes = sorted(module_genes)
    if len(genes) > cap:
        genes = genes[:cap]
    return ", ".join(genes)


def _module_label_from_themes(pathways: List[str], normalizer: PathwayNormalizer) -> str:
    """Assign module label as the most frequent theme among pathways in the module."""
    if not pathways:
        return "Other"
    themes = [normalizer.normalize(p) for p in pathways]
    from collections import Counter
    counts = Counter(themes)
    return counts.most_common(1)[0][0]


def _main_genes_for_module(
    module_genes: Set[str],
    gene_weights: Dict[str, float],
    top_k: int = 10,
) -> str:
    """Top genes in module by weight, comma-separated."""
    if not module_genes:
        return ""
    weight_lookup = {k.upper(): v for k, v in (gene_weights or {}).items()}
    sorted_genes = sorted(
        module_genes,
        key=lambda g: weight_lookup.get(g.upper(), 1.0),
        reverse=True,
    )
    return ", ".join(sorted_genes[:top_k])


def _main_pathways_for_module(
    module_pathways: List[str],
    merged_df: pd.DataFrame,
    top_k: int = 5,
) -> str:
    """Top pathway names in module by adjusted p-value (most significant first)."""
    if not module_pathways or "Term" not in merged_df.columns or "Adjusted P-value" not in merged_df.columns:
        return ""
    key_set = set(module_pathways)
    ck = merged_df["Term"].map(canonical_pathway_key)
    sub = merged_df[ck.isin(key_set)].copy()
    sub["_q"] = pd.to_numeric(sub["Adjusted P-value"], errors="coerce").fillna(1.0)
    sub = sub.sort_values("_q", ascending=True)
    # One representative Term per canonical key (best q), then top_k keys
    seen_keys: Set[str] = set()
    terms: List[str] = []
    for t in sub["Term"].astype(str):
        k = canonical_pathway_key(t)
        if not k or k in seen_keys:
            continue
        seen_keys.add(k)
        terms.append(t)
        if len(terms) >= top_k:
            break
    return "; ".join(terms)


def _display_term_by_canonical_key(merged_df: pd.DataFrame) -> Dict[str, str]:
    """Map canonical_pathway_key -> best (lowest q) original Term for exports."""
    if "Term" not in merged_df.columns:
        return {}
    df = merged_df.copy()
    df["_pk"] = df["Term"].map(canonical_pathway_key)
    df = df[df["_pk"].astype(str).str.len() > 0]
    if df.empty:
        return {}
    if "Adjusted P-value" in df.columns:
        df["_q"] = pd.to_numeric(df["Adjusted P-value"], errors="coerce").fillna(1.0)
        df = df.sort_values("_q", ascending=True)
    out: Dict[str, str] = {}
    for _, row in df.iterrows():
        pk = row["_pk"]
        if pk not in out:
            out[str(pk)] = str(row["Term"])
    return out


def run_module_pipeline(
    input_path: Path,
    output_dir: Path,
    *,
    gene_column: Optional[str] = None,
    top_n: int = 200,
    libraries: Optional[List[str]] = None,
    organism: str = "Human",
    cutoff: float = 0.05,
    disease_only: bool = False,
    disease_association_types: Optional[List[str]] = None,
    min_disease_evidence_level: Optional[str] = None,
    min_disease_publications: Optional[int] = None,
    min_disease_score: Optional[float] = None,
    min_dmp_count: Optional[int] = None,
    min_unique_dmps: Optional[int] = None,
    max_gene_q_value: Optional[float] = None,
    min_mean_effect_size: Optional[float] = None,
    min_gene_z: Optional[float] = None,
    min_gene_importance: Optional[float] = None,
    feature_types: Optional[List[str]] = None,
    sort_by: Optional[str] = None,
    sort_ascending: bool = False,
    similarity_threshold: float = 0.15,
    cluster_resolution: float = 0.8,
    module_cluster_max_q: Optional[float] = None,
    module_cluster_top_terms_per_library: Optional[int] = None,
    disease_genes: Optional[Set[str]] = None,
    network_plot: Optional[str] = None,
    network_refinement_enabled: bool = False,
    network_refinement_source: str = "string_api",
    network_refinement_local_edges_file: Optional[str] = None,
    network_refinement_cache_path: Optional[str] = None,
    network_refinement_score_threshold: float = 400.0,
    network_refinement_community_method: str = "louvain",
    network_refinement_min_component_size: int = 2,
    network_refinement_weight_in_final_score: float = 0.3,
    dash_host: str = "127.0.0.1",
    dash_port: int = 8050,
    dash_open_browser: bool = False,
) -> pd.DataFrame:
    """
    Run the full pathway-to-module pipeline (Steps A–E) and write modules_ranked.csv.
    Returns the modules table (DataFrame).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    analyzer = EnrichmentAnalyzer(libraries=libraries, organism=organism, cutoff=cutoff)
    genes, gene_weights = analyzer.load_gene_list_with_weights(
        input_path,
        top_n=top_n,
        gene_column=gene_column,
        disease_only=disease_only,
        disease_association_types=disease_association_types,
        min_disease_evidence_level=min_disease_evidence_level,
        min_disease_publications=min_disease_publications,
        min_disease_score=min_disease_score,
        min_dmp_count=min_dmp_count,
        min_unique_dmps=min_unique_dmps,
        max_gene_q_value=max_gene_q_value,
        min_mean_effect_size=min_mean_effect_size,
        min_gene_z=min_gene_z,
        min_gene_importance=min_gene_importance,
        feature_types=feature_types,
        sort_by=sort_by,
        sort_ascending=sort_ascending,
    )
    if not genes:
        logger.warning("No genes loaded; cannot run module pipeline.")
        return pd.DataFrame()

    merged_df = analyzer.run_enrichment(genes, output_dir)
    if merged_df.empty:
        logger.warning("No enrichment results; cannot build modules.")
        return pd.DataFrame()

    clustering_df = _reduce_terms_for_clustering(
        merged_df,
        max_q=module_cluster_max_q,
        top_terms_per_library=module_cluster_top_terms_per_library,
    )
    if clustering_df.empty:
        logger.warning(
            "Term reduction produced zero rows for module clustering "
            f"(module_cluster_max_q={module_cluster_max_q}, "
            f"module_cluster_top_terms_per_library={module_cluster_top_terms_per_library})."
        )
        return pd.DataFrame()
    if len(clustering_df) < len(merged_df):
        logger.info(
            "Reduced terms for module clustering: %d -> %d rows",
            len(merged_df),
            len(clustering_df),
        )

    pathway_to_module_id, pathway_to_genes = run_pathway_clustering(
        clustering_df,
        similarity_threshold=similarity_threshold,
        use_jaccard=True,
        cluster_resolution=cluster_resolution,
    )
    if not pathway_to_module_id:
        logger.warning("Pathway clustering produced no modules.")
        return pd.DataFrame()

    normalizer = PathwayNormalizer()
    pca_relevance_tier, theme_descriptions = load_theme_extras()

    ppi_coherence_by_module: Dict[int, float] = {}
    ppi_dash_elements: Optional[List[Dict]] = None
    ppi_dash_stylesheet: Optional[List[Dict]] = None
    if network_refinement_enabled:
        try:
            if network_refinement_source == "local_edges":
                if not network_refinement_local_edges_file:
                    raise ValueError(
                        "network_refinement_local_edges_file is required when source=local_edges"
                    )
                edges_df = load_local_edges(network_refinement_local_edges_file)
                edges_df = edges_df[
                    pd.to_numeric(edges_df["score"], errors="coerce").fillna(0.0)
                    >= float(network_refinement_score_threshold)
                ].copy()
            else:
                edges_df = fetch_string_edges(
                    genes=genes,
                    required_score=float(network_refinement_score_threshold),
                    cache_path=network_refinement_cache_path,
                )

            network_genes = sorted(
                {
                    g.upper()
                    for genes_set in pathway_to_genes.values()
                    for g in genes_set
                    if str(g).strip()
                }
            )
            ppi_graph = build_ppi_graph(
                edges_df=edges_df,
                genes=network_genes,
                min_component_size=int(network_refinement_min_component_size),
            )
            node_metrics_df = compute_network_metrics(ppi_graph)
            communities = detect_communities(
                ppi_graph,
                method=network_refinement_community_method,
            )
            if not node_metrics_df.empty:
                node_metrics_df["community_id"] = (
                    node_metrics_df["gene"].astype(str).str.upper().map(communities)
                )
            module_coherence_df = compute_module_coherence(
                pathway_to_module_id=pathway_to_module_id,
                pathway_to_genes=pathway_to_genes,
                graph=ppi_graph,
                node_metrics=node_metrics_df,
            )

            ppi_coherence_by_module = {
                int(r["module_id"]): float(r["ppi_coherence_score"])
                for _, r in module_coherence_df.iterrows()
            }

            # Optional PPI dataset for Dash Cytoscape visualization
            if ppi_graph.number_of_nodes() > 0:
                for node in ppi_graph.nodes():
                    cid = int(communities.get(node, -1))
                    ppi_graph.nodes[node]["module_id"] = cid
                    ppi_graph.nodes[node]["module_label"] = f"Community {cid}" if cid >= 0 else "Other"
                    ppi_graph.nodes[node]["n_genes"] = int(ppi_graph.degree(node))
                ppi_payload = module_network_plot.build_cytoscape_payload_from_graph(
                    ppi_graph,
                    layout="spring",
                    include_positions=True,
                    show_labels=True,
                )
                ppi_dash_elements = ppi_payload.get("elements")
                ppi_dash_stylesheet = ppi_payload.get("stylesheet")

            edges_path = output_dir / "ppi_network_edges.csv"
            edges_df.to_csv(edges_path, index=False)
            logger.info("Wrote %s with %d edges.", edges_path, len(edges_df))

            node_metrics_path = output_dir / "ppi_node_metrics.csv"
            node_metrics_df.to_csv(node_metrics_path, index=False)
            logger.info("Wrote %s with %d nodes.", node_metrics_path, len(node_metrics_df))

            hubs_path = output_dir / "ppi_hubs.csv"
            rank_hubs(node_metrics_df, top_k=25).to_csv(hubs_path, index=False)
            logger.info("Wrote %s.", hubs_path)

            module_coherence_path = output_dir / "ppi_module_coherence.csv"
            module_coherence_df.to_csv(module_coherence_path, index=False)
            logger.info("Wrote %s with %d modules.", module_coherence_path, len(module_coherence_df))
        except Exception as exc:
            logger.warning(
                "Network refinement failed, falling back to baseline module score: %s",
                exc,
            )

    score_df = score_and_rank_modules(
        pathway_to_module_id,
        pathway_to_genes,
        clustering_df,
        gene_weights=gene_weights,
        disease_genes=disease_genes or DEFAULT_PCA_RELEVANT_GENES,
        ppi_coherence_by_module=ppi_coherence_by_module,
        ppi_weight_in_final_score=(
            float(network_refinement_weight_in_final_score)
            if network_refinement_enabled
            else 0.0
        ),
    )

    out_rows = []
    for _, row in score_df.iterrows():
        mid = row["module_id"]
        pathways = [p for p, m in pathway_to_module_id.items() if m == mid]
        module_genes = set()
        for p in pathways:
            module_genes |= pathway_to_genes.get(p, set())
        label = _module_label_from_themes(pathways, normalizer)
        main_genes = _main_genes_for_module(module_genes, gene_weights, top_k=10)
        main_pathways = _main_pathways_for_module(pathways, clustering_df, top_k=5)
        overlap_genes = _overlap_genes_str(module_genes)
        n_genes = row["n_genes"]
        # Curated PCa tier override for canonical themes; else use score-based
        pca_relevance = pca_relevance_tier.get(label, row["pca_relevance"])
        module_type = "candidate" if n_genes <= 2 else "core"
        main_theme = theme_descriptions.get(label, label)
        out_rows.append({
            "Module": label,
            "Score": round(row["final_score"], 4),
            "Base_score": round(row.get("base_score", row["final_score"]), 4),
            "PPI_coherence_score": round(row.get("ppi_coherence_score", 0.0), 4),
            "Blended_score": round(row.get("blended_score", row["final_score"]), 4),
            "Main_genes": main_genes,
            "Overlap_genes": overlap_genes,
            "Main_pathways": main_pathways,
            "Main_theme": main_theme,
            "PCa_relevance": pca_relevance,
            "module_type": module_type,
            "n_pathways": row["n_pathways"],
            "n_genes": n_genes,
        })

    out_df = pd.DataFrame(out_rows)
    # Core modules first (by score desc), then candidate modules at bottom
    out_df.sort_values(
        by=["module_type", "Score"],
        ascending=[True, False],
        inplace=True,
    )
    out_df.reset_index(drop=True, inplace=True)
    out_path = output_dir / "modules_ranked.csv"
    out_df.to_csv(out_path, index=False)
    logger.info(f"Wrote {out_path} with {len(out_df)} modules.")

    # Per-pathway overlap genes (which genes drive each pathway)
    if pathway_to_genes:
        display_by_key = _display_term_by_canonical_key(clustering_df)
        pathway_overlap = [
            {
                "Pathway": display_by_key.get(term, term),
                "Pathway_key": term,
                "Overlap_genes": ", ".join(sorted(genes)),
            }
            for term, genes in sorted(pathway_to_genes.items())
        ]
        if pathway_overlap:
            pathway_df = pd.DataFrame(pathway_overlap)
            pathway_out = output_dir / "pathway_overlap_genes.csv"
            pathway_df.to_csv(pathway_out, index=False)
            logger.info(f"Wrote {pathway_out} with {len(pathway_df)} pathways.")

    # Network plot (pathway similarity graph) when requested
    if network_plot and network_plot.lower() != "none":
        module_id_to_label = {}
        for mid in set(pathway_to_module_id.values()):
            pathways_in_module = [p for p, m in pathway_to_module_id.items() if m == mid]
            module_id_to_label[mid] = _module_label_from_themes(pathways_in_module, normalizer)
        module_network_plot.write_network_plots(
            output_dir=output_dir,
            pathway_to_module_id=pathway_to_module_id,
            pathway_to_genes=pathway_to_genes,
            merged_df=clustering_df,
            module_id_to_label=module_id_to_label,
            similarity_threshold=similarity_threshold,
            network_plot=network_plot,
            ppi_elements=ppi_dash_elements,
            ppi_stylesheet=ppi_dash_stylesheet,
            dash_host=dash_host,
            dash_port=dash_port,
            dash_open_browser=dash_open_browser,
        )

    return out_df
