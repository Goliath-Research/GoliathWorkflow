"""
Comparison-level gene directional scores for feature_family_set=gene_scored.

Uses frozen mapper gene panels (gene_support_n, gene_importance) and per-comparison DMP
effect sizes with sample methylation at panel loci.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

def _normalize_feature_key(value: object) -> str:
    text = str(value or "").strip()
    return text if text else "unknown"


def _is_known_mapped_token(value: object) -> bool:
    token = str(value or "").strip().lower()
    return token not in {"", "unknown", "nan", "none"}


def _feature_label_token(label: object) -> str:
    token = str(label or "").strip().lower().replace("-", "_").replace(" ", "_")
    cleaned = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in token)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    cleaned = cleaned.strip("_")
    return cleaned or "cancer"


GENE_SCORED_FEATURE_PREFIX = "gene_directional_score__"
GENE_SCORED_SCHEMA_VERSION = "gene_scored_v1"


def gene_scored_feature_column(comparison_label: object) -> str:
    return f"{GENE_SCORED_FEATURE_PREFIX}{_feature_label_token(comparison_label)}"


def family_includes_gene_scored(feature_family_set: Optional[str]) -> bool:
    token = str(feature_family_set or "dmp").strip().lower()
    return token in {"gene_scored", "dmp+gene_scored"}


def resolve_gene_scored_comparison_labels(
    dmp_df: pd.DataFrame,
    frozen_gene_panel_df: pd.DataFrame,
) -> List[str]:
    dmp_labels: set[str] = set()
    if dmp_df is not None and not dmp_df.empty and "comparison_label" in dmp_df.columns:
        dmp_labels = {
            str(x).strip()
            for x in dmp_df["comparison_label"].astype(str).tolist()
            if str(x).strip()
        }
    panel_labels: set[str] = set()
    if frozen_gene_panel_df is not None and not frozen_gene_panel_df.empty:
        if "comparison_label" in frozen_gene_panel_df.columns:
            panel_labels = {
                str(x).strip()
                for x in frozen_gene_panel_df["comparison_label"].astype(str).tolist()
                if str(x).strip()
            }
    if dmp_labels and panel_labels:
        labels = sorted(dmp_labels & panel_labels)
    elif dmp_labels:
        labels = sorted(dmp_labels)
    elif panel_labels:
        labels = sorted(panel_labels)
    else:
        labels = []
    return labels


def gene_scored_feature_names(
    comparison_labels: Sequence[str],
) -> List[str]:
    return [gene_scored_feature_column(label) for label in comparison_labels]


def prepare_gene_scored_panels(
    frozen_gene_panel_df: pd.DataFrame,
    *,
    min_support_n: int = 2,
) -> Dict[str, pd.DataFrame]:
    if frozen_gene_panel_df is None or frozen_gene_panel_df.empty:
        return {}
    work = frozen_gene_panel_df.copy()
    if "comparison_label" not in work.columns or "gene_name" not in work.columns:
        return {}
    work["comparison_label"] = work["comparison_label"].astype(str)
    work["gene_name"] = work["gene_name"].map(_normalize_feature_key)
    work["gene_support_n"] = pd.to_numeric(work.get("gene_support_n"), errors="coerce").fillna(0).astype(int)
    work["gene_importance"] = pd.to_numeric(work.get("gene_importance"), errors="coerce").fillna(0.0)
    min_n = int(max(1, min_support_n))
    work = work[work["gene_support_n"] >= min_n].copy()
    work = work[work["gene_name"].apply(_is_known_mapped_token)].copy()
    work = work[work["gene_importance"] > 0.0].copy()
    if work.empty:
        return {}
    panels: Dict[str, pd.DataFrame] = {}
    for cmp_label, cdf in work.groupby("comparison_label", sort=True):
        panel = cdf.drop_duplicates(subset=["gene_name"], keep="first").copy()
        if not panel.empty:
            panels[str(cmp_label)] = panel.reset_index(drop=True)
    return panels


def build_locus_order_index(
    feature_order: Sequence[Tuple[str, str, int]],
) -> Dict[Tuple[str, str, int], int]:
    return {(str(c), str(ctx), int(pos)): int(i) for i, (c, ctx, pos) in enumerate(feature_order)}


def _gene_weight(
    row: pd.Series,
    *,
    gene_weight_mode: str,
) -> float:
    importance = float(pd.to_numeric(row.get("gene_importance"), errors="coerce") or 0.0)
    support_n = float(pd.to_numeric(row.get("gene_support_n"), errors="coerce") or 0.0)
    mode = str(gene_weight_mode or "importance_x_sqrt_support").strip().lower()
    if mode == "importance_only":
        return importance
    if importance <= 0.0 or support_n <= 0.0:
        return 0.0
    return importance * float(np.sqrt(support_n))


def compute_gene_directional_score_matrix(
    X_raw: np.ndarray,
    feature_order: Sequence[Tuple[str, str, int]],
    dmp_df: pd.DataFrame,
    panels: Dict[str, pd.DataFrame],
    comparison_labels: Sequence[str],
    *,
    use_region_weight: bool = True,
    gene_weight_mode: str = "importance_x_sqrt_support",
) -> np.ndarray:
    n_samples = int(X_raw.shape[0])
    labels = [str(x) for x in comparison_labels]
    out = np.full((n_samples, len(labels)), np.nan, dtype=np.float64)
    if n_samples == 0 or not labels:
        return out

    order_index = build_locus_order_index(feature_order)
    if dmp_df is None or dmp_df.empty:
        return out

    work = dmp_df.copy()
    if "comparison_label" not in work.columns:
        return out
    work["comparison_label"] = work["comparison_label"].astype(str)
    work["gene_name"] = work["gene_name"].map(_normalize_feature_key) if "gene_name" in work.columns else "unknown"
    work["chromosome"] = work["chromosome"].astype(str)
    work["context"] = work["context"].astype(str)
    work["position"] = pd.to_numeric(work["position"], errors="coerce").fillna(-1).astype(int)
    work["effect_size"] = pd.to_numeric(work.get("effect_size"), errors="coerce")
    if use_region_weight and "region_weight" in work.columns:
        work["_region_w"] = pd.to_numeric(work["region_weight"], errors="coerce").fillna(1.0).clip(lower=0.0)
    else:
        work["_region_w"] = 1.0
    work = work[
        np.isfinite(work["effect_size"])
        & (work["position"] >= 0)
        & work["gene_name"].apply(_is_known_mapped_token)
    ].copy()
    if work.empty:
        return out

    for j, cmp_label in enumerate(labels):
        panel = panels.get(cmp_label)
        if panel is None or panel.empty:
            continue
        cmp_dmp = work[work["comparison_label"] == cmp_label]
        if cmp_dmp.empty:
            continue

        loci_by_gene: Dict[str, List[Tuple[int, float, float]]] = {}
        for _, row in cmp_dmp.iterrows():
            key = (str(row["chromosome"]), str(row["context"]), int(row["position"]))
            col_idx = order_index.get(key)
            if col_idx is None:
                continue
            effect = float(row["effect_size"])
            abs_w = abs(effect) * float(row["_region_w"])
            if abs_w <= 0.0:
                continue
            sign_e = float(np.sign(effect))
            gene = str(row["gene_name"])
            loci_by_gene.setdefault(gene, []).append((int(col_idx), abs_w, sign_e))

        if not loci_by_gene:
            continue

        for i in range(n_samples):
            score_num = 0.0
            score_den = 0.0
            for _, grow in panel.iterrows():
                gene = str(grow["gene_name"])
                loci = loci_by_gene.get(gene)
                if not loci:
                    continue
                w_g = _gene_weight(grow, gene_weight_mode=gene_weight_mode)
                if w_g <= 0.0:
                    continue
                locus_num = 0.0
                locus_den = 0.0
                for col_idx, abs_w, sign_e in loci:
                    beta = float(X_raw[i, col_idx])
                    if not np.isfinite(beta):
                        continue
                    locus_num += sign_e * abs_w * (beta - 0.5)
                    locus_den += abs_w
                if locus_den <= 0.0:
                    continue
                dir_g = locus_num / locus_den
                score_num += w_g * dir_g
                score_den += w_g
            if score_den > 0.0:
                out[i, j] = float(score_num / score_den)

    return out
