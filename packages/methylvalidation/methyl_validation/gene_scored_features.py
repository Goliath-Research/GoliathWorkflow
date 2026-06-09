"""
Comparison-level gene directional scores for feature_family_set=gene_scored.

Uses frozen mapper gene panels (gene_support_n, gene_importance) and per-comparison DMP
effect sizes with sample methylation at panel loci.

Region-directional helpers below are reserved for a future structural_scored family
(frozen-panel-restricted); they are not emitted under gene_scored.
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
GENE_PANEL_OBS_FRACTION_PREFIX = "gene_panel_obs_fraction__"
GENE_DIRECTIONAL_IQR_PREFIX = "gene_directional_iqr__"
REGION_DIRECTIONAL_FEATURE_PREFIX = "region_directional_score__"
GENE_SCORED_SCHEMA_VERSION = "gene_scored_v3_panel_coverage_iqr"
DEFAULT_REGION_DIRECTIONAL_TYPES: Tuple[str, ...] = (
    "promoter",
    "exon",
    "intron",
    "terminator",
)
_ALLOWED_REGION_DIRECTIONAL_TYPES = frozenset(
    {"promoter", "exon", "intron", "gene_body", "terminator"}
)


def gene_scored_feature_column(comparison_label: object) -> str:
    return f"{GENE_SCORED_FEATURE_PREFIX}{_feature_label_token(comparison_label)}"


def gene_panel_obs_fraction_column(comparison_label: object) -> str:
    return f"{GENE_PANEL_OBS_FRACTION_PREFIX}{_feature_label_token(comparison_label)}"


def gene_directional_iqr_column(comparison_label: object) -> str:
    return f"{GENE_DIRECTIONAL_IQR_PREFIX}{_feature_label_token(comparison_label)}"


def family_includes_gene_scored(feature_family_set: Optional[str]) -> bool:
    from .observed_feature_builder import normalize_feature_family_set

    token = normalize_feature_family_set(feature_family_set)
    return token in {"gene_scored", "dmp_scored+gene_scored"}


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
    names: List[str] = []
    for label in comparison_labels:
        names.append(gene_scored_feature_column(label))
        names.append(gene_panel_obs_fraction_column(label))
        names.append(gene_directional_iqr_column(label))
    return names


def _normalize_structural_feature(value: object) -> str:
    token = _normalize_feature_key(value).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "promoter_region": "promoter",
        "genebody": "gene_body",
        "body": "gene_body",
        "terminator_region": "terminator",
    }
    token = aliases.get(token, token)
    return token if token in _ALLOWED_REGION_DIRECTIONAL_TYPES else "unknown"


def normalize_region_directional_region_types(
    region_types: Optional[Sequence[str]] = None,
) -> Tuple[str, ...]:
    if not region_types:
        return DEFAULT_REGION_DIRECTIONAL_TYPES
    out: List[str] = []
    seen: set[str] = set()
    for raw in region_types:
        token = _normalize_structural_feature(raw)
        if token == "unknown" or token in seen:
            continue
        seen.add(token)
        out.append(token)
    if not out:
        return DEFAULT_REGION_DIRECTIONAL_TYPES
    return tuple(out)


def region_directional_feature_column(
    comparison_label: object,
    region_type: object,
) -> str:
    return (
        f"{REGION_DIRECTIONAL_FEATURE_PREFIX}"
        f"{_feature_label_token(comparison_label)}__{_feature_label_token(region_type)}"
    )


def _prepare_dmp_work_df(
    dmp_df: pd.DataFrame,
    *,
    use_region_weight: bool,
) -> pd.DataFrame:
    work = dmp_df.copy()
    if "comparison_label" not in work.columns:
        return pd.DataFrame()
    work["comparison_label"] = work["comparison_label"].astype(str)
    work["chromosome"] = work["chromosome"].astype(str)
    work["context"] = work["context"].astype(str)
    work["position"] = pd.to_numeric(work["position"], errors="coerce").fillna(-1).astype(int)
    work["effect_size"] = pd.to_numeric(work.get("effect_size"), errors="coerce")
    if "feature_type" in work.columns:
        work["feature_type"] = work["feature_type"].map(_normalize_structural_feature)
    else:
        work["feature_type"] = "unknown"
    if use_region_weight and "region_weight" in work.columns:
        work["_region_w"] = pd.to_numeric(work["region_weight"], errors="coerce").fillna(1.0).clip(lower=0.0)
    else:
        work["_region_w"] = 1.0
    work = work[
        np.isfinite(work["effect_size"])
        & (work["position"] >= 0)
        & work["feature_type"].apply(_is_known_mapped_token)
        & (work["feature_type"] != "unknown")
    ].copy()
    return work


def count_region_directional_panel_loci(
    dmp_df: pd.DataFrame,
    feature_order: Sequence[Tuple[str, str, int]],
    comparison_label: str,
    region_type: str,
) -> int:
    if dmp_df is None or dmp_df.empty:
        return 0
    order_index = build_locus_order_index(feature_order)
    work = _prepare_dmp_work_df(dmp_df, use_region_weight=True)
    if work.empty:
        return 0
    cmp_dmp = work[
        (work["comparison_label"] == str(comparison_label))
        & (work["feature_type"] == str(region_type))
    ]
    if cmp_dmp.empty:
        return 0
    seen_keys: set[Tuple[str, str, int]] = set()
    n_panel = 0
    for _, row in cmp_dmp.iterrows():
        key = (str(row["chromosome"]), str(row["context"]), int(row["position"]))
        if key not in order_index or key in seen_keys:
            continue
        seen_keys.add(key)
        n_panel += 1
    return n_panel


def resolve_region_directional_column_specs(
    dmp_df: pd.DataFrame,
    feature_order: Sequence[Tuple[str, str, int]],
    comparison_labels: Sequence[str],
    region_types: Sequence[str],
    *,
    min_loci: int = 1,
) -> List[Tuple[str, str]]:
    if dmp_df is None or dmp_df.empty:
        return []
    order_index = build_locus_order_index(feature_order)
    work = _prepare_dmp_work_df(dmp_df, use_region_weight=True)
    if work.empty:
        return []
    min_n = int(max(1, min_loci))
    region_set = set(str(r) for r in region_types)
    specs: List[Tuple[str, str]] = []
    for cmp_label in [str(x) for x in comparison_labels]:
        cmp_dmp = work[work["comparison_label"] == cmp_label]
        if cmp_dmp.empty:
            continue
        for region in [str(r) for r in region_types]:
            if region not in region_set:
                continue
            cdf = cmp_dmp[cmp_dmp["feature_type"] == region]
            if cdf.empty:
                continue
            n_panel = 0
            seen_keys: set[Tuple[str, str, int]] = set()
            for _, row in cdf.iterrows():
                key = (str(row["chromosome"]), str(row["context"]), int(row["position"]))
                if key not in order_index or key in seen_keys:
                    continue
                seen_keys.add(key)
                n_panel += 1
            if n_panel >= min_n:
                specs.append((cmp_label, region))
    return specs


def region_directional_feature_names(
    dmp_df: pd.DataFrame,
    feature_order: Sequence[Tuple[str, str, int]],
    comparison_labels: Sequence[str],
    region_types: Optional[Sequence[str]] = None,
    *,
    min_loci: int = 1,
) -> List[str]:
    regions = normalize_region_directional_region_types(region_types)
    specs = resolve_region_directional_column_specs(
        dmp_df,
        feature_order,
        comparison_labels,
        regions,
        min_loci=min_loci,
    )
    return [region_directional_feature_column(cmp_label, region) for cmp_label, region in specs]


def compute_region_directional_score_matrix(
    X_raw: np.ndarray,
    feature_order: Sequence[Tuple[str, str, int]],
    dmp_df: pd.DataFrame,
    comparison_labels: Sequence[str],
    region_types: Optional[Sequence[str]] = None,
    *,
    min_loci: int = 1,
    use_region_weight: bool = True,
) -> Tuple[np.ndarray, List[Tuple[str, str]]]:
    n_samples = int(X_raw.shape[0])
    regions = normalize_region_directional_region_types(region_types)
    specs = resolve_region_directional_column_specs(
        dmp_df,
        feature_order,
        comparison_labels,
        regions,
        min_loci=min_loci,
    )
    out = np.full((n_samples, len(specs)), np.nan, dtype=np.float64)
    if n_samples == 0 or not specs:
        return out, specs

    order_index = build_locus_order_index(feature_order)
    work = _prepare_dmp_work_df(dmp_df, use_region_weight=use_region_weight)
    if work.empty:
        return out, specs

    loci_by_cmp_region: Dict[Tuple[str, str], List[Tuple[int, float, float]]] = {}
    spec_set = set(specs)
    for _, row in work.iterrows():
        cmp_label = str(row["comparison_label"])
        region = str(row["feature_type"])
        key = (cmp_label, region)
        if key not in spec_set:
            continue
        locus_key = (str(row["chromosome"]), str(row["context"]), int(row["position"]))
        col_idx = order_index.get(locus_key)
        if col_idx is None:
            continue
        effect = float(row["effect_size"])
        abs_w = abs(effect) * float(row["_region_w"])
        if abs_w <= 0.0:
            continue
        sign_e = float(np.sign(effect))
        loci_by_cmp_region.setdefault(key, []).append((int(col_idx), abs_w, sign_e))

    for j, spec_key in enumerate(specs):
        loci = loci_by_cmp_region.get(spec_key)
        if not loci:
            continue
        for i in range(n_samples):
            locus_num = 0.0
            locus_den = 0.0
            for col_idx, abs_w, sign_e in loci:
                beta = float(X_raw[i, col_idx])
                if not np.isfinite(beta):
                    continue
                locus_num += sign_e * abs_w * (beta - 0.5)
                locus_den += abs_w
            if locus_den > 0.0:
                out[i, j] = float(locus_num / locus_den)

    return out, specs


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


def _prepare_gene_scored_dmp_work(
    dmp_df: pd.DataFrame,
    *,
    use_region_weight: bool,
) -> pd.DataFrame:
    work = dmp_df.copy()
    if "comparison_label" not in work.columns:
        return pd.DataFrame()
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
    return work


def _build_loci_by_gene(
    cmp_dmp: pd.DataFrame,
    order_index: Dict[Tuple[str, str, int], int],
) -> Dict[str, List[Tuple[int, float, float]]]:
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
    return loci_by_gene


def _per_gene_directional_value(
    loci: Sequence[Tuple[int, float, float]],
    sample_row: np.ndarray,
) -> Optional[float]:
    locus_num = 0.0
    locus_den = 0.0
    for col_idx, abs_w, sign_e in loci:
        beta = float(sample_row[col_idx])
        if not np.isfinite(beta):
            continue
        locus_num += sign_e * abs_w * (beta - 0.5)
        locus_den += abs_w
    if locus_den <= 0.0:
        return None
    return float(locus_num / locus_den)


def _directional_iqr(dir_values: Sequence[float]) -> float:
    finite = [float(v) for v in dir_values if np.isfinite(v)]
    if len(finite) < 2:
        return float("nan")
    q75, q25 = np.nanpercentile(finite, [75.0, 25.0])
    return float(q75 - q25)


def compute_gene_scored_matrices(
    X_raw: np.ndarray,
    feature_order: Sequence[Tuple[str, str, int]],
    dmp_df: pd.DataFrame,
    panels: Dict[str, pd.DataFrame],
    comparison_labels: Sequence[str],
    *,
    use_region_weight: bool = True,
    gene_weight_mode: str = "importance_x_sqrt_support",
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    n_samples = int(X_raw.shape[0])
    labels = [str(x) for x in comparison_labels]
    directional = np.full((n_samples, len(labels)), np.nan, dtype=np.float64)
    obs_fraction = np.full((n_samples, len(labels)), np.nan, dtype=np.float64)
    directional_iqr = np.full((n_samples, len(labels)), np.nan, dtype=np.float64)
    if n_samples == 0 or not labels:
        return directional, obs_fraction, directional_iqr

    order_index = build_locus_order_index(feature_order)
    if dmp_df is None or dmp_df.empty:
        return directional, obs_fraction, directional_iqr

    work = _prepare_gene_scored_dmp_work(dmp_df, use_region_weight=use_region_weight)
    if work.empty:
        return directional, obs_fraction, directional_iqr

    for j, cmp_label in enumerate(labels):
        panel = panels.get(cmp_label)
        if panel is None or panel.empty:
            continue
        cmp_dmp = work[work["comparison_label"] == cmp_label]
        if cmp_dmp.empty:
            continue

        loci_by_gene = _build_loci_by_gene(cmp_dmp, order_index)
        if not loci_by_gene:
            continue

        panel_size = int(len(panel))
        if panel_size <= 0:
            continue

        for i in range(n_samples):
            sample_row = np.asarray(X_raw[i, :], dtype=np.float64)
            score_num = 0.0
            score_den = 0.0
            dir_values: List[float] = []
            n_genes_observed = 0
            for _, grow in panel.iterrows():
                gene = str(grow["gene_name"])
                loci = loci_by_gene.get(gene)
                if not loci:
                    continue
                dir_g = _per_gene_directional_value(loci, sample_row)
                if dir_g is None:
                    continue
                n_genes_observed += 1
                dir_values.append(dir_g)
                w_g = _gene_weight(grow, gene_weight_mode=gene_weight_mode)
                if w_g <= 0.0:
                    continue
                score_num += w_g * dir_g
                score_den += w_g
            obs_fraction[i, j] = float(n_genes_observed / panel_size)
            if score_den > 0.0:
                directional[i, j] = float(score_num / score_den)
            directional_iqr[i, j] = _directional_iqr(dir_values)

    return directional, obs_fraction, directional_iqr


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
    directional, _, _ = compute_gene_scored_matrices(
        X_raw,
        feature_order,
        dmp_df,
        panels,
        comparison_labels,
        use_region_weight=use_region_weight,
        gene_weight_mode=gene_weight_mode,
    )
    return directional
