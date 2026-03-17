"""
Pathway-to-module pipeline: run enrichment, normalize pathway names, cluster pathways
into modules, score/rank modules, and write modules_ranked.csv.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from .enricher import EnrichmentAnalyzer
from .pathway_normalizer import PathwayNormalizer
from .pathway_graph import run_pathway_clustering
from .module_scorer import score_and_rank_modules, DEFAULT_PCA_RELEVANT_GENES

logger = logging.getLogger(__name__)

OVERLAP_GENES_CAP = 50


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
    sub = merged_df[merged_df["Term"].isin(module_pathways)].copy()
    sub = sub.sort_values("Adjusted P-value", ascending=True)
    terms = sub["Term"].head(top_k).tolist()
    return "; ".join(str(t) for t in terms)


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
    disease_genes: Optional[Set[str]] = None,
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

    pathway_to_module_id, pathway_to_genes = run_pathway_clustering(
        merged_df,
        similarity_threshold=similarity_threshold,
        use_jaccard=True,
        cluster_resolution=cluster_resolution,
    )
    if not pathway_to_module_id:
        logger.warning("Pathway clustering produced no modules.")
        return pd.DataFrame()

    normalizer = PathwayNormalizer()
    score_df = score_and_rank_modules(
        pathway_to_module_id,
        pathway_to_genes,
        merged_df,
        gene_weights=gene_weights,
        disease_genes=disease_genes or DEFAULT_PCA_RELEVANT_GENES,
    )

    module_ids = score_df["module_id"].tolist()
    out_rows = []
    for _, row in score_df.iterrows():
        mid = row["module_id"]
        pathways = [p for p, m in pathway_to_module_id.items() if m == mid]
        module_genes = set()
        for p in pathways:
            module_genes |= pathway_to_genes.get(p, set())
        label = _module_label_from_themes(pathways, normalizer)
        main_genes = _main_genes_for_module(module_genes, gene_weights, top_k=10)
        main_pathways = _main_pathways_for_module(pathways, merged_df, top_k=5)
        overlap_genes = _overlap_genes_str(module_genes)
        out_rows.append({
            "Module": label,
            "Score": round(row["final_score"], 4),
            "Main_genes": main_genes,
            "Overlap_genes": overlap_genes,
            "Main_pathways": main_pathways,
            "PCa_relevance": row["pca_relevance"],
            "n_pathways": row["n_pathways"],
            "n_genes": row["n_genes"],
        })

    out_df = pd.DataFrame(out_rows)
    out_path = output_dir / "modules_ranked.csv"
    out_df.to_csv(out_path, index=False)
    logger.info(f"Wrote {out_path} with {len(out_df)} modules.")

    # Per-pathway overlap genes (which genes drive each pathway)
    if pathway_to_genes:
        pathway_overlap = [
            {"Pathway": term, "Overlap_genes": ", ".join(sorted(genes))}
            for term, genes in pathway_to_genes.items()
        ]
        if pathway_overlap:
            pathway_df = pd.DataFrame(pathway_overlap)
            pathway_out = output_dir / "pathway_overlap_genes.csv"
            pathway_df.to_csv(pathway_out, index=False)
            logger.info(f"Wrote {pathway_out} with {len(pathway_df)} pathways.")

    return out_df
