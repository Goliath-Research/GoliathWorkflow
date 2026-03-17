"""
Module scoring and disease-aware ranking: compute module score from enrichment
metrics and optional disease relevance prior, then rank modules.
"""

import logging
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Minimal set of prostate-cancer-relevant gene symbols for disease prior (overlap scoring).
# Can be overridden or extended via config/file.
DEFAULT_PCA_RELEVANT_GENES: Set[str] = {
    "AR", "NKX3-1", "PTEN", "TP53", "MYC", "TMPRSS2", "ERG", "ETS1", "ETS2",
    "PIK3CA", "AKT1", "MTOR", "FOXA1", "HOXB13", "BRCA1", "BRCA2", "ATM",
    "CDKN1B", "RB1", "MYCL", "KLK3", "KLK2", "ACPP", "AMACR", "PCA3",
    "GSTP1", "APC", "CTNNB1", "WNT", "TGFB1", "SMAD4", "VEGFA", "IL6",
    "CD274", "PDCD1", "MSH2", "MSH6", "MLH1", "PMS2", "BARD1",
}


def _normalize_score(x: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clip and optionally scale to [0, 1]."""
    return float(np.clip(x, low, high))


def compute_module_enrichment_score(
    module_pathways: List[str],
    merged_df: pd.DataFrame,
    pathway_to_genes: Dict[str, Set[str]],
    gene_weights: Optional[Dict[str, float]] = None,
    w_mean_log10q: float = 0.4,
    w_n_pathways: float = 0.2,
    w_n_genes: float = 0.2,
    w_mean_gene_weight: float = 0.2,
) -> float:
    """
    Compute a single scalar enrichment score for a module.
    merged_df must have 'Term' and 'Adjusted P-value'.
    """
    if not module_pathways:
        return 0.0
    sub = merged_df[merged_df["Term"].isin(module_pathways)]
    if sub.empty:
        return 0.0
    q = pd.to_numeric(sub["Adjusted P-value"], errors="coerce").fillna(1.0)
    mean_log10q = np.mean(-np.log10(q.clip(lower=1e-10)))
    n_pathways = len(module_pathways)
    all_genes = set()
    for p in module_pathways:
        all_genes |= pathway_to_genes.get(p, set())
    n_genes = len(all_genes)
    mean_gw = 1.0
    if gene_weights and all_genes:
        vals = [gene_weights.get(g, 1.0) for g in all_genes]
        mean_gw = float(np.mean(vals)) if vals else 1.0
    # Normalize components to ~[0,1] scale then weighted sum
    score = (
        w_mean_log10q * _normalize_score(mean_log10q / 10.0)  # -log10(q) often 1–20
        + w_n_pathways * _normalize_score(n_pathways / 50.0)
        + w_n_genes * _normalize_score(n_genes / 200.0)
        + w_mean_gene_weight * _normalize_score(mean_gw)
    )
    return _normalize_score(score)


def compute_disease_relevance(
    module_genes: Set[str],
    disease_genes: Optional[Set[str]] = None,
) -> float:
    """
    Disease relevance score: fraction of module genes that are in disease set,
    or 0 if no disease set. Returns value in [0, 1].
    """
    disease_genes = disease_genes or set()
    if not disease_genes or not module_genes:
        return 0.5  # neutral when no prior
    disease_genes = {g.strip().upper() for g in disease_genes}
    module_genes = {g.strip().upper() for g in module_genes}
    overlap = len(module_genes & disease_genes)
    return _normalize_score(overlap / len(module_genes))


def pca_relevance_label(score: float) -> str:
    """Map disease relevance score to High/Medium/Low."""
    if score >= 0.4:
        return "High"
    if score >= 0.2:
        return "Medium"
    return "Low"


def score_and_rank_modules(
    pathway_to_module_id: Dict[str, int],
    pathway_to_genes: Dict[str, Set[str]],
    merged_df: pd.DataFrame,
    gene_weights: Optional[Dict[str, float]] = None,
    disease_genes: Optional[Set[str]] = None,
    weight_enrichment: float = 0.7,
    weight_disease: float = 0.3,
) -> pd.DataFrame:
    """
    For each module, compute enrichment score and disease relevance, combine into
    final score, and return a DataFrame of modules sorted by final score (descending).
    Columns: module_id, module_label (placeholder), n_pathways, n_genes, enrichment_score,
    disease_relevance, final_score, pca_relevance (High/Medium/Low).
    """
    disease_genes = disease_genes or DEFAULT_PCA_RELEVANT_GENES
    module_ids = sorted(set(pathway_to_module_id.values()))
    rows = []
    for mid in module_ids:
        pathways = [p for p, m in pathway_to_module_id.items() if m == mid]
        genes = set()
        for p in pathways:
            genes |= pathway_to_genes.get(p, set())
        enrich_score = compute_module_enrichment_score(
            pathways, merged_df, pathway_to_genes, gene_weights
        )
        disease_score = compute_disease_relevance(genes, disease_genes)
        final = weight_enrichment * enrich_score + weight_disease * disease_score
        rows.append({
            "module_id": mid,
            "n_pathways": len(pathways),
            "n_genes": len(genes),
            "enrichment_score": round(enrich_score, 4),
            "disease_relevance": round(disease_score, 4),
            "final_score": round(final, 4),
            "pca_relevance": pca_relevance_label(disease_score),
        })
    df = pd.DataFrame(rows)
    df.sort_values("final_score", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df
