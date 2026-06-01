"""
Observed-only hybrid feature builder for backend training/prediction.

This module intentionally avoids DMP-level value imputation. Per-sample features are
computed only from loci observed in that sample, plus explicit reliability features.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from methyl_utils.core.io import load_from_h5
from methyl_utils.methyl_centroid_pair import MethylCentroidPair
from scipy.stats import entropy


@dataclass
class ObservedFeatureArtifacts:
    X: np.ndarray
    feature_names: List[str]
    report: Dict[str, Any]


@dataclass
class ObservedHybridAnchors:
    healthy_reference_vector: np.ndarray
    cancer_reference_vector: np.ndarray
    per_cancer_reference_vectors: List[np.ndarray]
    healthy_class_index: int
    healthy_class_label: str
    cancer_class_labels: List[str]
    anchor_strategy: str
    feature_order_fingerprint: str


OBSERVED_HYBRID_SCHEMA_VERSION = "observed_hybrid_v28_no_healthy_centroid_features"
HYBRID_FEATURE_SCHEMA_VERSION = "hybrid_feature_v1"
HYBRID_FEATURE_FAMILY_SETS = (
    "dmp",
    "gene",
    "structural",
    "dmp+gene",
    "dmp+structural",
    "hybrid-all",
)
REMOVED_OBSERVED_HYBRID_FEATURES = {
    "gene_shift_q50",
    "gene_shift_iqr",
    "gene_hyper_extreme_fraction",
    "gene_hypo_extreme_fraction",
    "topk_minus_rest_abs_shift",
}


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    w_sum = float(np.sum(weights))
    if w_sum <= 0.0:
        return float("nan")
    return float(np.sum(values * weights) / w_sum)


def _weighted_std(values: np.ndarray, weights: np.ndarray) -> float:
    mu = _weighted_mean(values, weights)
    if not np.isfinite(mu):
        return float("nan")
    w_sum = float(np.sum(weights))
    if w_sum <= 0.0:
        return float("nan")
    var = float(np.sum(weights * ((values - mu) ** 2)) / w_sum)
    return float(np.sqrt(max(var, 0.0)))


def _weighted_kurtosis(values: np.ndarray, weights: np.ndarray) -> float:
    mu = _weighted_mean(values, weights)
    sd = _weighted_std(values, weights)
    if not np.isfinite(mu) or not np.isfinite(sd) or sd <= 1e-12:
        return float("nan")
    z = (values - mu) / sd
    w_sum = float(np.sum(weights))
    if w_sum <= 0.0:
        return float("nan")
    return float(np.sum(weights * (z**4)) / w_sum - 3.0)


def _weighted_skewness(values: np.ndarray, weights: np.ndarray) -> float:
    mu = _weighted_mean(values, weights)
    sd = _weighted_std(values, weights)
    if not np.isfinite(mu) or not np.isfinite(sd) or sd <= 1e-12:
        return float("nan")
    z = (values - mu) / sd
    w_sum = float(np.sum(weights))
    if w_sum <= 0.0:
        return float("nan")
    return float(np.sum(weights * (z**3)) / w_sum)


def _first_existing_column(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    cols_lower = {str(c).strip().lower(): str(c) for c in df.columns}
    for name in candidates:
        hit = cols_lower.get(str(name).strip().lower())
        if hit is not None:
            return hit
    return None


def _normalize_feature_key(value: object) -> str:
    text = str(value or "").strip()
    return text if text else "unknown"


def _normalize_structural_feature(value: object) -> str:
    token = _normalize_feature_key(value).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "promoter_region": "promoter",
        "genebody": "gene_body",
        "body": "gene_body",
        "terminator_region": "terminator",
    }
    token = aliases.get(token, token)
    allowed = {"promoter", "exon", "intron", "gene_body", "terminator"}
    return token if token in allowed else "unknown"


def _is_known_mapped_token(value: object) -> bool:
    token = str(value or "").strip().lower()
    return token not in {"", "unknown", "nan", "none"}


def _build_dynamic_mapped_feature_names(
    locus_df: pd.DataFrame,
    *,
    include_gene: bool,
    include_structural: bool,
) -> Tuple[List[str], List[str], Dict[str, Dict[str, Any]]]:
    gene_names: List[str] = []
    struct_names: List[str] = []
    metadata: Dict[str, Dict[str, Any]] = {}
    if locus_df is None or locus_df.empty:
        return gene_names, struct_names, metadata

    work = locus_df.copy()
    if "gene_name" in work.columns:
        gene_series = work["gene_name"]
    else:
        gene_series = pd.Series(["unknown"] * len(work), index=work.index, dtype=object)
    if "feature_type" in work.columns:
        feature_series = work["feature_type"]
    else:
        feature_series = pd.Series(["unknown"] * len(work), index=work.index, dtype=object)
    work["gene_name"] = gene_series.apply(_normalize_feature_key)
    work["feature_type"] = feature_series.apply(_normalize_structural_feature)
    if "effect_size" in work.columns:
        effect_series = work["effect_size"]
    else:
        effect_series = pd.Series([0.0] * len(work), index=work.index, dtype=float)
    work["effect_size"] = pd.to_numeric(effect_series, errors="coerce").fillna(0.0).astype(float)
    work["_abs_effect"] = np.abs(work["effect_size"].to_numpy(dtype=float))

    if include_gene:
        valid_gene = work["gene_name"].apply(_is_known_mapped_token)
        if bool(valid_gene.any()):
            genes = sorted(set(work.loc[valid_gene, "gene_name"].astype(str).tolist()))
            gene_names = [f"gene::{g}" for g in genes]
            for g in genes:
                mask = valid_gene & (work["gene_name"] == g)
                metadata[f"gene::{g}"] = {
                    "family": "gene",
                    "gene_name": g,
                    "n_loci": int(mask.sum()),
                    "sum_abs_effect_size": float(work.loc[mask, "_abs_effect"].sum()),
                }

    if include_structural:
        valid_struct = (
            work["gene_name"].apply(_is_known_mapped_token)
            & work["feature_type"].apply(_is_known_mapped_token)
            & (work["feature_type"] != "unknown")
        )
        if bool(valid_struct.any()):
            pairs = sorted(
                set(
                    (str(g), str(f))
                    for g, f in zip(
                        work.loc[valid_struct, "gene_name"].tolist(),
                        work.loc[valid_struct, "feature_type"].tolist(),
                    )
                )
            )
            struct_names = [f"struct::{g}::{f}" for g, f in pairs]
            for g, f in pairs:
                key = f"struct::{g}::{f}"
                mask = valid_struct & (work["gene_name"] == g) & (work["feature_type"] == f)
                metadata[key] = {
                    "family": "structural",
                    "gene_name": g,
                    "feature_type": f,
                    "n_loci": int(mask.sum()),
                    "sum_abs_effect_size": float(work.loc[mask, "_abs_effect"].sum()),
                }

    return gene_names, struct_names, metadata


def _family_flags(feature_family_set: Optional[str]) -> Tuple[bool, bool, bool]:
    token = str(feature_family_set or "dmp").strip().lower()
    if token == "dmp":
        return True, False, False
    if token == "gene":
        return False, True, False
    if token == "structural":
        return False, False, True
    if token == "dmp+gene":
        return True, True, False
    if token == "dmp+structural":
        return True, False, True
    if token == "hybrid-all":
        return True, True, True
    raise ValueError(
        f"Unsupported feature_family_set={feature_family_set!r}; "
        f"allowed={list(HYBRID_FEATURE_FAMILY_SETS)}"
    )


def _resolve_sample_context_h5(sample_path: str | Path, chromosome: str, context: str) -> Optional[Path]:
    p = Path(str(sample_path))
    if p.suffix.lower() == ".h5" and p.is_file():
        return p
    if p.is_file():
        return p
    candidate = p / f"{chromosome}-{context}.h5"
    if candidate.is_file():
        return candidate
    return None


def _collect_positions_for_ranges(
    sample_paths: Sequence[str],
    chromosome: str,
    context: str,
    ranges: np.ndarray,
) -> np.ndarray:
    if ranges.size == 0:
        return np.asarray([], dtype=np.uint32)
    source_h5: Optional[Path] = None
    for sp in sample_paths:
        hit = _resolve_sample_context_h5(sp, chromosome, context)
        if hit is not None:
            source_h5 = hit
            break
    if source_h5 is None:
        return np.asarray([], dtype=np.uint32)
    frame = load_from_h5(source_h5)
    pos_all = np.asarray(frame.df["pos"].values, dtype=np.uint32)
    if pos_all.size == 0:
        return np.asarray([], dtype=np.uint32)
    mask = np.zeros((pos_all.size,), dtype=bool)
    for start, end in ranges:
        lo = int(min(start, end))
        hi = int(max(start, end))
        mask |= (pos_all >= lo) & (pos_all <= hi)
    return np.unique(pos_all[mask]).astype(np.uint32)


def _expand_loci_df_from_gene_ranges(
    sample_paths: Sequence[str],
    base_dmp_df: pd.DataFrame,
    gene_feature_ranges_df: pd.DataFrame,
) -> pd.DataFrame:
    if base_dmp_df.empty or gene_feature_ranges_df is None or gene_feature_ranges_df.empty:
        return base_dmp_df
    required = {"gene_name", "chromosome", "feature_type", "feature_start", "feature_end"}
    if not required.issubset(set(gene_feature_ranges_df.columns)):
        return base_dmp_df
    work = gene_feature_ranges_df.copy()
    work["gene_name"] = work["gene_name"].apply(_normalize_feature_key)
    work["chromosome"] = work["chromosome"].astype(str)
    work["feature_type"] = work["feature_type"].apply(_normalize_structural_feature)
    work["feature_start"] = pd.to_numeric(work["feature_start"], errors="coerce")
    work["feature_end"] = pd.to_numeric(work["feature_end"], errors="coerce")
    work = work[np.isfinite(work["feature_start"]) & np.isfinite(work["feature_end"])].copy()
    if work.empty:
        return base_dmp_df

    base = base_dmp_df.copy()
    if "comparison_label" not in base.columns:
        base["comparison_label"] = "default"
    if "context" not in base.columns:
        base["context"] = "CG"
    contexts = sorted(set(base["context"].astype(str).tolist())) or ["CG"]
    comparisons = sorted(set(base["comparison_label"].astype(str).tolist())) or ["default"]

    expanded_rows: List[Dict[str, Any]] = []
    for cmp_label in comparisons:
        cmp_ranges = work
        if "comparison_label" in work.columns:
            filt = work["comparison_label"].astype(str) == str(cmp_label)
            if bool(filt.any()):
                cmp_ranges = work[filt].copy()
        if cmp_ranges.empty:
            continue
        for chrom, cdf in cmp_ranges.groupby("chromosome", sort=False):
            range_pairs = cdf[["feature_start", "feature_end"]].to_numpy(dtype=np.int64)
            for ctx in contexts:
                in_range = _collect_positions_for_ranges(sample_paths, str(chrom), str(ctx), range_pairs)
                if in_range.size == 0:
                    continue
                for _, r in cdf.iterrows():
                    lo = int(min(r["feature_start"], r["feature_end"]))
                    hi = int(max(r["feature_start"], r["feature_end"]))
                    pos = in_range[(in_range >= lo) & (in_range <= hi)]
                    if pos.size == 0:
                        continue
                    for p in pos.tolist():
                        expanded_rows.append(
                            {
                                "comparison_label": str(cmp_label),
                                "chromosome": str(chrom),
                                "context": str(ctx),
                                "position": int(p),
                                "gene_name": str(r["gene_name"]),
                                "feature_type": str(r["feature_type"]),
                                "region_weight": float(pd.to_numeric(r.get("region_weight", 1.0), errors="coerce") or 1.0),
                                "effect_size": float(
                                    pd.to_numeric(r.get("feature_effect_compound", np.nan), errors="coerce")
                                    if "feature_effect_compound" in r
                                    else np.nan
                                ),
                                "dmr_region": "unknown",
                                "source_csv": "gene_range_expansion",
                            }
                        )

    if not expanded_rows:
        return base_dmp_df
    expanded = pd.DataFrame(expanded_rows)
    expanded["effect_size"] = pd.to_numeric(expanded["effect_size"], errors="coerce").fillna(0.0).astype(float)
    expanded["weight"] = expanded["effect_size"]
    merged = pd.concat([base, expanded], ignore_index=True, sort=False)
    merged["position"] = pd.to_numeric(merged["position"], errors="coerce").fillna(-1).astype(int)
    merged = merged[merged["position"] >= 0].copy()
    merged["priority"] = np.abs(pd.to_numeric(merged.get("effect_size"), errors="coerce").fillna(0.0))
    merged = merged.sort_values(
        ["comparison_label", "chromosome", "context", "position", "priority"],
        ascending=[True, True, True, True, False],
    ).drop_duplicates(
        subset=["comparison_label", "chromosome", "context", "position"],
        keep="first",
    )
    merged = merged.drop(columns=["priority"], errors="ignore")
    return merged.reset_index(drop=True)


def _build_reference_map(
    dmp_df: pd.DataFrame,
) -> Tuple[
    Dict[str, Dict[str, np.ndarray]],
    List[Tuple[str, str, int]],
    np.ndarray,
    pd.DataFrame,
    Dict[str, np.ndarray],
]:
    refs: Dict[str, Dict[str, np.ndarray]] = {}
    order: List[Tuple[str, str, int]] = []
    weights: List[float] = []

    work_df = dmp_df.copy()
    if "effect_size" not in work_df.columns:
        raise ValueError("Observed-hybrid feature building requires DMP effect_size values.")
    if "comparison_label" not in work_df.columns:
        work_df["comparison_label"] = "default"
    if "context" not in work_df.columns:
        work_df["context"] = "CG"

    gene_col = _first_existing_column(
        work_df,
        ("gene_name", "gene", "gene_symbol", "symbol", "nearest_gene"),
    )
    if gene_col is None:
        work_df["gene_name"] = "unknown"
        gene_col = "gene_name"
    dmr_col = _first_existing_column(
        work_df,
        ("dmr_region", "region_id", "dmr_id", "region", "dmr"),
    )

    work_df["chromosome"] = work_df["chromosome"].astype(str)
    work_df["context"] = work_df["context"].astype(str)
    work_df["position"] = pd.to_numeric(work_df["position"], errors="coerce").fillna(-1).astype(int)
    work_df = work_df[work_df["position"] >= 0].copy()
    work_df["comparison_label"] = work_df["comparison_label"].apply(_normalize_feature_key)
    work_df["gene_name"] = work_df[gene_col].apply(_normalize_feature_key)
    if dmr_col is not None:
        work_df["dmr_region"] = work_df[dmr_col].apply(_normalize_feature_key)
    else:
        work_df["dmr_region"] = "unknown"

    work_df["_score"] = np.abs(pd.to_numeric(work_df["effect_size"], errors="coerce").fillna(0.0).astype(float))
    work_df = work_df.sort_values(
        ["_score", "chromosome", "context", "position"],
        ascending=[False, True, True, True],
    )
    locus_df = work_df.drop_duplicates(["chromosome", "context", "position"], keep="first").copy()
    locus_df["w"] = pd.to_numeric(locus_df["effect_size"], errors="coerce").fillna(0.0).astype(float)
    locus_df = locus_df.sort_values(["chromosome", "context", "position"], ascending=[True, True, True])

    for chrom, cdf in locus_df.groupby("chromosome", sort=True):
        refs[str(chrom)] = {}
        for ctx, xdf in cdf.groupby("context", sort=False):
            poss = np.asarray(sorted(set(int(v) for v in xdf["position"].tolist())), dtype=np.uint32)
            refs[str(chrom)][str(ctx)] = poss
        for _, row in cdf.iterrows():
            order.append((str(row["chromosome"]), str(row["context"]), int(row["position"])))
            weights.append(float(row["w"]))

    w = np.asarray(weights, dtype=np.float32)
    if w.size == 0:
        return refs, order, w, locus_df.reset_index(drop=True), {}
    w = np.abs(np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0))
    mx = float(np.max(w))
    if mx <= 0.0:
        w = np.ones_like(w, dtype=np.float32)
    else:
        w = w / mx
    order_to_idx = {key: idx for idx, key in enumerate(order)}
    per_label_weights: Dict[str, np.ndarray] = {}
    for comp_label, cdf in work_df.groupby("comparison_label", sort=False):
        comp_vec = np.zeros((len(order),), dtype=np.float32)
        if cdf.empty:
            per_label_weights[str(comp_label)] = comp_vec
            continue
        cdf2 = cdf.copy()
        cdf2["abs_effect"] = np.abs(pd.to_numeric(cdf2["effect_size"], errors="coerce").fillna(0.0).astype(float))
        cdf2 = cdf2.sort_values(
            ["abs_effect", "chromosome", "context", "position"],
            ascending=[False, True, True, True],
        ).drop_duplicates(["chromosome", "context", "position"], keep="first")
        for _, row in cdf2.iterrows():
            key = (str(row["chromosome"]), str(row["context"]), int(row["position"]))
            idx = order_to_idx.get(key)
            if idx is None:
                continue
            comp_vec[idx] = float(abs(float(pd.to_numeric(row["effect_size"], errors="coerce"))))
        per_label_weights[str(comp_label)] = comp_vec.astype(np.float32)
    return refs, order, w, locus_df.reset_index(drop=True), per_label_weights


def _extract_matrix_for_samples(
    sample_paths: Sequence[str],
    refs: Dict[str, Dict[str, np.ndarray]],
    feature_order: List[Tuple[str, str, int]],
    *,
    min_coverage: int = 1,
) -> np.ndarray:
    n_samples = len(sample_paths)
    if n_samples == 0:
        return np.zeros((0, len(feature_order)), dtype=np.float32)

    blocks: List[np.ndarray] = []
    for chrom in sorted(refs.keys(), key=lambda x: (len(str(x)), str(x))):
        chrom_order = [(c, ctx, pos) for (c, ctx, pos) in feature_order if c == chrom]
        if not chrom_order:
            continue
        X, all_positions, all_contexts, _idx = MethylCentroidPair.extract_methylation_fractions(
            list(sample_paths),
            refs[chrom],
            chromosome=chrom,
            min_coverage=min_coverage,
        )
        col_map: Dict[Tuple[str, str, int], int] = {}
        for j in range(len(all_positions)):
            col_map[(str(chrom), str(all_contexts[j]), int(all_positions[j]))] = int(j)
        X_block = np.full((n_samples, len(chrom_order)), np.nan, dtype=np.float32)
        for j, (_c, ctx, pos) in enumerate(chrom_order):
            src = col_map.get((chrom, ctx, pos))
            if src is not None:
                X_block[:, j] = X[:, int(src)]
        blocks.append(X_block)
    if not blocks:
        return np.full((n_samples, len(feature_order)), np.nan, dtype=np.float32)
    return np.concatenate(blocks, axis=1)


def _feature_order_fingerprint(feature_order: Sequence[Tuple[str, str, int]]) -> str:
    text = "\n".join([f"{c}:{ctx}:{int(pos)}" for c, ctx, pos in feature_order])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _select_healthy_index(class_names: Sequence[str]) -> int:
    if not class_names:
        return 0
    normalized = [str(x).strip().lower() for x in class_names]
    exact = ("healthy", "control", "normal")
    for name in exact:
        if name in normalized:
            return int(normalized.index(name))
    partial = ("healthy", "control", "normal")
    for idx, name in enumerate(normalized):
        if any(token in name for token in partial):
            return int(idx)
    return 0


def _safe_centroid(X: np.ndarray) -> np.ndarray:
    if X.ndim != 2 or X.shape[0] == 0:
        return np.zeros((X.shape[1] if X.ndim == 2 else 0,), dtype=np.float32)
    out = np.zeros((X.shape[1],), dtype=np.float32)
    for j in range(X.shape[1]):
        col = np.asarray(X[:, j], dtype=np.float64)
        finite = col[np.isfinite(col)]
        out[j] = float(np.mean(finite)) if finite.size > 0 else 0.5
    if out.ndim == 0:
        out = np.asarray([float(out)], dtype=np.float32)
    out = np.nan_to_num(out, nan=0.5, posinf=0.5, neginf=0.5).astype(np.float32)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def derive_observed_hybrid_anchors(
    sample_paths: Sequence[str],
    sample_class_indices: Sequence[int],
    class_names: Sequence[str],
    dmp_df: pd.DataFrame,
    *,
    min_coverage: int = 1,
    feature_family_set: str = "dmp",
    gene_feature_loading: str = "frozen",
    fixed_gene_features_df: Optional[pd.DataFrame] = None,
) -> ObservedHybridAnchors:
    _include_dmp_family, include_gene_family, _include_structural_family = _family_flags(feature_family_set)
    gene_feature_loading_norm = str(gene_feature_loading or "frozen").strip().lower()
    if gene_feature_loading_norm not in {"frozen", "range"}:
        raise ValueError("gene_feature_loading must be 'frozen' or 'range'")
    work_dmp_df = dmp_df
    if (
        gene_feature_loading_norm == "range"
        and include_gene_family
        and fixed_gene_features_df is not None
        and not fixed_gene_features_df.empty
    ):
        work_dmp_df = _expand_loci_df_from_gene_ranges(
            sample_paths=sample_paths,
            base_dmp_df=dmp_df,
            gene_feature_ranges_df=fixed_gene_features_df,
        )
    refs, feature_order, _weights, _locus_df, _per_label_weights = _build_reference_map(work_dmp_df)
    X_raw = _extract_matrix_for_samples(
        sample_paths,
        refs,
        feature_order,
        min_coverage=int(max(1, min_coverage)),
    )
    y = np.asarray(sample_class_indices, dtype=np.int32)
    if y.shape[0] != X_raw.shape[0]:
        raise ValueError("sample_class_indices length mismatch for observed_hybrid anchor derivation.")
    if X_raw.shape[0] == 0:
        raise ValueError("No samples available for observed_hybrid anchor derivation.")

    healthy_index = _select_healthy_index(class_names)
    if healthy_index < 0 or healthy_index >= len(class_names):
        healthy_index = 0
    healthy_mask = y == int(healthy_index)
    cancer_mask = ~healthy_mask

    if not np.any(healthy_mask):
        healthy_mask = np.ones_like(cancer_mask, dtype=bool)
        cancer_mask = np.ones_like(cancer_mask, dtype=bool)
        strategy = "fallback_all_samples_for_both_anchors"
    elif not np.any(cancer_mask):
        cancer_mask = healthy_mask.copy()
        strategy = "fallback_single_class_uses_healthy_for_cancer_anchor"
    else:
        strategy = "healthy_vs_nonhealthy_aggregate"

    healthy_vec = _safe_centroid(X_raw[healthy_mask, :])
    cancer_vec = _safe_centroid(X_raw[cancer_mask, :])
    cancer_labels = [str(name) for i, name in enumerate(class_names) if i != int(healthy_index)]
    if not cancer_labels:
        cancer_labels = [str(class_names[int(healthy_index)])] if class_names else ["unknown"]
    per_cancer_reference_vectors: List[np.ndarray] = []
    for i, name in enumerate(class_names):
        if int(i) == int(healthy_index):
            continue
        cls_mask = y == int(i)
        if np.any(cls_mask):
            per_cancer_reference_vectors.append(_safe_centroid(X_raw[cls_mask, :]))
        else:
            per_cancer_reference_vectors.append(cancer_vec.copy())
    if not per_cancer_reference_vectors:
        per_cancer_reference_vectors = [cancer_vec.copy()]
    return ObservedHybridAnchors(
        healthy_reference_vector=healthy_vec,
        cancer_reference_vector=cancer_vec,
        per_cancer_reference_vectors=per_cancer_reference_vectors,
        healthy_class_index=int(healthy_index),
        healthy_class_label=(str(class_names[int(healthy_index)]) if class_names else "unknown"),
        cancer_class_labels=cancer_labels,
        anchor_strategy=strategy,
        feature_order_fingerprint=_feature_order_fingerprint(feature_order),
    )


def _weighted_mean_with_fallback(values: np.ndarray, weights: np.ndarray) -> float:
    if values.size == 0:
        return float("nan")
    if weights.size == values.size and float(np.sum(weights)) > 0.0:
        return _weighted_mean(values, weights)
    return float(np.mean(values))


def _weighted_skew_kurt_with_fallback(values: np.ndarray, weights: np.ndarray) -> Tuple[float, float]:
    if values.size < 2:
        return float("nan"), float("nan")
    if weights.size == values.size and float(np.sum(weights)) > 0.0:
        return _weighted_skewness(values, weights), _weighted_kurtosis(values, weights)
    mu = float(np.mean(values))
    sd = float(np.std(values))
    if not np.isfinite(sd) or sd <= 1e-12:
        return float("nan"), float("nan")
    z = (values - mu) / sd
    skew = float(np.mean(z**3))
    kurt = float(np.mean(z**4) - 3.0)
    return skew, kurt


def _cosine_similarity(values_a: np.ndarray, values_b: np.ndarray) -> float:
    if values_a.size == 0 or values_b.size == 0 or values_a.size != values_b.size:
        return float("nan")
    na = float(np.linalg.norm(values_a))
    nb = float(np.linalg.norm(values_b))
    if na <= 1e-12 or nb <= 1e-12:
        return float("nan")
    return float(np.dot(values_a, values_b) / (na * nb))


def _weighted_cosine_similarity(values_a: np.ndarray, values_b: np.ndarray, weights: np.ndarray) -> float:
    if values_a.size == 0 or values_b.size == 0 or values_a.size != values_b.size:
        return float("nan")
    if weights.size != values_a.size:
        return float("nan")
    w = np.asarray(weights, dtype=np.float64)
    w = np.abs(np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0))
    if float(np.sum(w)) <= 0.0:
        return float("nan")
    a = np.asarray(values_a, dtype=np.float64)
    b = np.asarray(values_b, dtype=np.float64)
    num = float(np.sum(w * a * b))
    na = float(np.sqrt(np.sum(w * (a**2))))
    nb = float(np.sqrt(np.sum(w * (b**2))))
    if na <= 1e-12 or nb <= 1e-12:
        return float("nan")
    return float(num / (na * nb))


def _jensen_shannon_distance(values_a: np.ndarray, values_b: np.ndarray, eps: float = 1e-10) -> float:
    if values_a.size == 0 or values_b.size == 0 or values_a.size != values_b.size:
        return float("nan")
    p = np.clip(np.asarray(values_a, dtype=np.float64), eps, 1.0 - eps)
    q = np.clip(np.asarray(values_b, dtype=np.float64), eps, 1.0 - eps)
    m = 0.5 * (p + q)
    js_div = 0.5 * (entropy(p, m, base=2) + entropy(q, m, base=2))
    if not np.isfinite(js_div):
        return float("nan")
    return float(np.sqrt(max(float(js_div), 0.0)))


def _weighted_jensen_shannon_distance(
    values_a: np.ndarray,
    values_b: np.ndarray,
    weights: np.ndarray,
    eps: float = 1e-10,
) -> float:
    if values_a.size == 0 or values_b.size == 0 or values_a.size != values_b.size:
        return float("nan")
    if weights.size != values_a.size:
        return float("nan")
    w = np.asarray(weights, dtype=np.float64)
    w = np.abs(np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0))
    w_sum = float(np.sum(w))
    if w_sum <= 0.0:
        return float("nan")
    w = w / w_sum
    p = np.clip(np.asarray(values_a, dtype=np.float64), eps, 1.0 - eps)
    q = np.clip(np.asarray(values_b, dtype=np.float64), eps, 1.0 - eps)
    p_w = p * w
    q_w = q * w
    p_sum = float(np.sum(p_w))
    q_sum = float(np.sum(q_w))
    if p_sum <= 0.0 or q_sum <= 0.0:
        return float("nan")
    p_w = p_w / p_sum
    q_w = q_w / q_sum
    m = 0.5 * (p_w + q_w)
    js_div = 0.5 * (entropy(p_w, m, base=2) + entropy(q_w, m, base=2))
    if not np.isfinite(js_div):
        return float("nan")
    return float(np.sqrt(max(float(js_div), 0.0)))


def _weighted_mean_abs_error(values_a: np.ndarray, values_b: np.ndarray, weights: np.ndarray) -> float:
    if values_a.size == 0 or values_b.size == 0 or values_a.size != values_b.size:
        return float("nan")
    if weights.size != values_a.size:
        return float("nan")
    abs_err = np.abs(values_a - values_b)
    return _weighted_mean_with_fallback(abs_err, weights)


def _feature_label_token(label: object) -> str:
    token = str(label or "").strip().lower().replace("-", "_").replace(" ", "_")
    cleaned = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in token)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    cleaned = cleaned.strip("_")
    return cleaned or "cancer"


def _prepare_histogram_density_artifacts(
    locus_df: pd.DataFrame,
    healthy_class_label: Optional[str],
    cancer_class_labels: Sequence[str],
    centroid_dir_by_class_label: Optional[Dict[str, str]],
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Dict[str, np.ndarray]]:
    if centroid_dir_by_class_label is None or not centroid_dir_by_class_label:
        return None, None, {}
    healthy_label = str(healthy_class_label or "").strip()
    if not healthy_label:
        return None, None, {}
    healthy_dir = centroid_dir_by_class_label.get(healthy_label)
    if not healthy_dir:
        return None, None, {}
    if locus_df.empty:
        return None, None, {}

    n_loci = int(len(locus_df))
    bin_edges_ref: Optional[np.ndarray] = None
    healthy_counts_ref: Optional[np.ndarray] = None
    cancer_counts: Dict[str, np.ndarray] = {}

    by_chrom_indices: Dict[str, np.ndarray] = {}
    for chrom, cdf in locus_df.groupby("chromosome", sort=False):
        by_chrom_indices[str(chrom)] = cdf.index.to_numpy(dtype=np.int64)

    for cancer_label in [str(x) for x in cancer_class_labels]:
        cancer_dir = centroid_dir_by_class_label.get(cancer_label)
        if not cancer_dir:
            continue
        cancer_counts_for_label: Optional[np.ndarray] = None
        for chrom, idxs in by_chrom_indices.items():
            sub_df = locus_df.loc[idxs, ["position", "context"]].reset_index(drop=True)
            loaded = MethylCentroidPair.load_binned_counts_from_centroids(
                sub_df,
                centroid1_dir=healthy_dir,
                centroid2_dir=cancer_dir,
                chromosome=str(chrom),
            )
            if loaded is None:
                continue
            edges, healthy_sub, cancer_sub = loaded
            edges = np.asarray(edges, dtype=np.float64)
            healthy_sub = np.asarray(healthy_sub, dtype=np.float64)
            cancer_sub = np.asarray(cancer_sub, dtype=np.float64)
            if healthy_sub.ndim != 2 or cancer_sub.ndim != 2:
                continue
            if healthy_sub.shape[0] != len(sub_df) or cancer_sub.shape[0] != len(sub_df):
                continue
            if healthy_sub.shape[1] != cancer_sub.shape[1]:
                continue
            if edges.shape[0] != healthy_sub.shape[1] + 1:
                continue
            if bin_edges_ref is None:
                bin_edges_ref = edges
            elif bin_edges_ref.shape != edges.shape or not np.allclose(bin_edges_ref, edges):
                # Do not adapt/rebin: skip incompatible sources.
                continue
            if healthy_counts_ref is None:
                healthy_counts_ref = np.zeros((n_loci, healthy_sub.shape[1]), dtype=np.float64)
            if cancer_counts_for_label is None:
                cancer_counts_for_label = np.zeros((n_loci, healthy_sub.shape[1]), dtype=np.float64)
            healthy_counts_ref[idxs, :] = healthy_sub
            cancer_counts_for_label[idxs, :] = cancer_sub
        if cancer_counts_for_label is not None:
            cancer_counts[cancer_label] = cancer_counts_for_label

    return bin_edges_ref, healthy_counts_ref, cancer_counts


def _fixed_feature_names(cancer_class_labels: Optional[Sequence[str]] = None) -> List[str]:
    names = [
        "max_weighted_directional_score",
        "weighted_mean_abs_distance_margin",
        "weighted_centroid_contrast_score",
        "obs_fraction",
        "weighted_obs_fraction",
        "n_obs_dmps",
        "n_total_dmps",
    ]
    labels = [str(x) for x in (cancer_class_labels or [])]
    if not labels:
        labels = ["cancer"]
    for label in labels:
        suffix = _feature_label_token(label)
        names.extend(
            [
                f"weighted_directional_agreement__{suffix}",
                f"weighted_mean_abs_error_to_cancer_centroid__{suffix}",
                f"weighted_cosine_similarity_to_cancer_centroid__{suffix}",
                f"weighted_fraction_dmps_closer_to_cancer_centroid__{suffix}",
                f"weighted_healthy_tail_evidence__{suffix}",
            ]
        )
    return [name for name in names if name not in REMOVED_OBSERVED_HYBRID_FEATURES]


def _gene_structural_feature_names(
    *,
    include_gene: bool,
    include_structural: bool,
    locus_df: Optional[pd.DataFrame] = None,
) -> List[str]:
    gene_names, struct_names, _meta = _build_dynamic_mapped_feature_names(
        locus_df if locus_df is not None else pd.DataFrame(),
        include_gene=include_gene,
        include_structural=include_structural,
    )
    names: List[str] = []
    names.extend(gene_names)
    names.extend(struct_names)
    return names


def observed_hybrid_feature_names(
    cancer_class_labels: Optional[Sequence[str]] = None,
    feature_family_set: str = "dmp",
    dmp_df: Optional[pd.DataFrame] = None,
) -> List[str]:
    include_dmp_family, include_gene_family, include_structural_family = _family_flags(feature_family_set)
    names: List[str] = []
    if include_dmp_family:
        names.extend(_fixed_feature_names(cancer_class_labels=cancer_class_labels))
    names.extend(
        _gene_structural_feature_names(
            include_gene=include_gene_family,
            include_structural=include_structural_family,
            locus_df=dmp_df,
        )
    )
    return names


def observed_hybrid_schema_fingerprint(
    cancer_class_labels: Optional[Sequence[str]] = None,
    *,
    feature_family_set: str = "dmp",
    dmp_df: Optional[pd.DataFrame] = None,
) -> str:
    names = observed_hybrid_feature_names(
        cancer_class_labels=cancer_class_labels,
        feature_family_set=feature_family_set,
        dmp_df=dmp_df,
    )
    return hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()


def build_observed_hybrid_feature_table(
    sample_paths: Sequence[str],
    dmp_df: pd.DataFrame,
    *,
    quantiles: Optional[Sequence[float]] = None,
    min_coverage: int = 1,
    include_dmp_features: bool = True,
    include_chromosome_features: bool = True,
    include_dmr_features: bool = True,
    include_gene_features: bool = True,
    dmr_window_bp: int = 100_000,
    max_dmr_features: int = 32,
    max_gene_features: int = 32,
    healthy_reference_vector: Optional[Sequence[float]] = None,
    cancer_reference_vector: Optional[Sequence[float]] = None,
    per_cancer_reference_vectors: Optional[Sequence[Sequence[float]]] = None,
    healthy_class_label: Optional[str] = None,
    cancer_class_labels: Optional[Sequence[str]] = None,
    anchor_strategy: Optional[str] = None,
    expected_feature_order_fingerprint: Optional[str] = None,
    centroid_dir_by_class_label: Optional[Dict[str, str]] = None,
    hist_eps: float = 1e-6,
    hist_alpha: float = 0.5,
    hist_evidence_clip_cap: float = 5.0,
    hist_tail_agreement_threshold: float = 0.10,
    feature_family_set: str = "dmp",
    gene_feature_loading: str = "frozen",
    fixed_gene_features_df: Optional[pd.DataFrame] = None,
) -> ObservedFeatureArtifacts:
    del quantiles, dmr_window_bp, max_dmr_features, max_gene_features
    # The redesigned schema is fixed; these toggles are retained only for compatibility.
    del include_dmp_features, include_chromosome_features, include_dmr_features, include_gene_features
    del hist_tail_agreement_threshold

    include_dmp_family, include_gene_family, include_structural_family = _family_flags(feature_family_set)
    gene_feature_loading_norm = str(gene_feature_loading or "frozen").strip().lower()
    if gene_feature_loading_norm not in {"frozen", "range"}:
        raise ValueError("gene_feature_loading must be 'frozen' or 'range'")
    work_dmp_df = dmp_df
    if (
        gene_feature_loading_norm == "range"
        and include_gene_family
        and fixed_gene_features_df is not None
        and not fixed_gene_features_df.empty
    ):
        work_dmp_df = _expand_loci_df_from_gene_ranges(
            sample_paths=sample_paths,
            base_dmp_df=dmp_df,
            gene_feature_ranges_df=fixed_gene_features_df,
        )
    refs, feature_order, weights, locus_df, per_label_weights = _build_reference_map(work_dmp_df)
    X_raw = _extract_matrix_for_samples(
        sample_paths,
        refs,
        feature_order,
        min_coverage=min_coverage,
    )

    n_samples = int(X_raw.shape[0])
    n_loci = int(X_raw.shape[1])
    if n_loci <= 0:
        raise ValueError("Observed-hybrid feature building requires non-empty DMP locus reference.")

    if healthy_reference_vector is None or cancer_reference_vector is None:
        raise ValueError(
            "Observed-hybrid feature building requires healthy_reference_vector and cancer_reference_vector."
        )
    healthy_ref = np.asarray(healthy_reference_vector, dtype=np.float64).reshape(-1)
    cancer_ref = np.asarray(cancer_reference_vector, dtype=np.float64).reshape(-1)
    if healthy_ref.shape[0] != n_loci or cancer_ref.shape[0] != n_loci:
        raise ValueError(
            f"Observed-hybrid centroid reference length mismatch: expected {n_loci}, "
            f"got healthy={healthy_ref.shape[0]}, cancer={cancer_ref.shape[0]}"
        )
    healthy_ref = np.nan_to_num(healthy_ref, nan=0.5, posinf=0.5, neginf=0.5)
    cancer_ref = np.nan_to_num(cancer_ref, nan=0.5, posinf=0.5, neginf=0.5)
    healthy_ref = np.clip(healthy_ref, 0.0, 1.0)
    cancer_ref = np.clip(cancer_ref, 0.0, 1.0)
    per_cancer_refs: List[np.ndarray] = []
    if per_cancer_reference_vectors is not None:
        for vec in per_cancer_reference_vectors:
            v = np.asarray(vec, dtype=np.float64).reshape(-1)
            if v.shape[0] != n_loci:
                raise ValueError(
                    f"Observed-hybrid per-cancer centroid reference length mismatch: "
                    f"expected {n_loci}, got {v.shape[0]}"
                )
            per_cancer_refs.append(np.clip(np.nan_to_num(v, nan=0.5, posinf=0.5, neginf=0.5), 0.0, 1.0))
    if not per_cancer_refs:
        per_cancer_refs = [cancer_ref]

    observed_order_fp = _feature_order_fingerprint(feature_order)
    if expected_feature_order_fingerprint and observed_order_fp != str(expected_feature_order_fingerprint):
        raise ValueError(
            "Observed-hybrid reference fingerprint mismatch; DMP order used for prediction "
            "does not match training anchors."
        )

    w = np.asarray(weights, dtype=np.float64)
    if w.size != n_loci:
        w = np.ones((n_loci,), dtype=np.float64)
    total_w = float(np.sum(w)) if w.size else 0.0
    if total_w <= 0.0:
        w = np.ones((n_loci,), dtype=np.float64)
        total_w = float(np.sum(w))

    cancer_labels_raw = [str(x) for x in (cancer_class_labels or [])]
    if not cancer_labels_raw:
        cancer_labels_raw = [f"cancer_{k+1}" for k in range(len(per_cancer_refs))]
    if len(cancer_labels_raw) < len(per_cancer_refs):
        cancer_labels_raw.extend(
            [f"cancer_{k+1}" for k in range(len(cancer_labels_raw), len(per_cancer_refs))]
        )
    cancer_labels_raw = cancer_labels_raw[: len(per_cancer_refs)]
    feature_names = observed_hybrid_feature_names(
        cancer_class_labels=cancer_labels_raw,
        feature_family_set=str(feature_family_set),
        dmp_df=locus_df,
    )
    gene_feature_names, struct_feature_names, mapped_feature_meta = _build_dynamic_mapped_feature_names(
        locus_df,
        include_gene=include_gene_family,
        include_structural=include_structural_family,
    )
    X_feat = np.full((n_samples, len(feature_names)), np.nan, dtype=np.float32)

    idx = {name: j for j, name in enumerate(feature_names)}
    gene_feature_set = set(gene_feature_names)
    struct_feature_set = set(struct_feature_names)
    cancer_labels_norm = [str(lbl).strip().lower() for lbl in cancer_labels_raw]
    per_label_weights_norm = {
        str(key).strip().lower(): np.asarray(vec, dtype=np.float64) for key, vec in per_label_weights.items()
    }
    default_weights = np.asarray(w, dtype=np.float64)
    if "effect_size" in locus_df.columns:
        effect_series = pd.to_numeric(locus_df["effect_size"], errors="coerce")
    else:
        effect_series = pd.Series([0.0] * len(locus_df), index=locus_df.index, dtype=float)
    effect_loci = effect_series.fillna(0.0).to_numpy(dtype=np.float64)

    def _weights_for_cancer_label(cancer_label: str) -> np.ndarray:
        label = str(cancer_label).strip().lower()
        if label in per_label_weights_norm:
            return per_label_weights_norm[label]
        for k, v in per_label_weights_norm.items():
            if label and (label in k or k.endswith(f"_vs_{label}") or k.endswith(f"-vs-{label}")):
                return v
        return default_weights

    label_weight_vectors: List[np.ndarray] = []
    for j in range(len(per_cancer_refs)):
        if j < len(cancer_labels_norm):
            label_weight_vectors.append(_weights_for_cancer_label(cancer_labels_norm[j]))
        else:
            label_weight_vectors.append(default_weights)
    hist_eps = float(max(float(hist_eps), 1e-12))
    hist_alpha = float(max(float(hist_alpha), 0.0))
    hist_evidence_clip_cap = float(max(float(hist_evidence_clip_cap), 0.0))
    hist_min_delta = 0.0
    hist_bin_edges, hist_healthy_counts, hist_cancer_counts = _prepare_histogram_density_artifacts(
        locus_df,
        healthy_class_label=healthy_class_label,
        cancer_class_labels=cancer_labels_raw,
        centroid_dir_by_class_label=centroid_dir_by_class_label,
    )

    def _ecdf_at(count_rows: np.ndarray, locus_indices: np.ndarray, bin_indices: np.ndarray) -> np.ndarray:
        if count_rows.size == 0 or locus_indices.size == 0:
            return np.asarray([], dtype=np.float64)
        rows = count_rows[locus_indices, :]
        n_bins = int(rows.shape[1])
        if n_bins <= 0:
            return np.asarray([], dtype=np.float64)
        smoothed = np.asarray(rows, dtype=np.float64) + hist_alpha
        totals = np.sum(smoothed, axis=1)
        cumsum = np.cumsum(smoothed, axis=1)
        picked = cumsum[np.arange(locus_indices.size), bin_indices]
        with np.errstate(divide="ignore", invalid="ignore"):
            out = np.where(totals > 0.0, picked / totals, np.nan)
        return np.clip(out, hist_eps, 1.0 - hist_eps)

    for i in range(n_samples):
        row = np.asarray(X_raw[i, :], dtype=np.float64)
        obs_mask = np.isfinite(row)
        obs_vals = row[obs_mask]
        obs_w = w[obs_mask] if obs_mask.size == w.size else np.asarray([], dtype=np.float64)
        n_obs = int(obs_vals.size)

        if n_obs > 0:
            max_weighted_directional_score = float("nan")
            per_label_feature_values: Dict[str, float] = {}
            for k_idx, mu_k in enumerate(per_cancer_refs):
                suffix = _feature_label_token(cancer_labels_raw[k_idx])
                key_da = f"weighted_directional_agreement__{suffix}"
                key_wmae_c = f"weighted_mean_abs_error_to_cancer_centroid__{suffix}"
                key_wcos_c = f"weighted_cosine_similarity_to_cancer_centroid__{suffix}"
                key_frac_c = f"weighted_fraction_dmps_closer_to_cancer_centroid__{suffix}"
                per_label_feature_values.setdefault(key_da, float("nan"))
                per_label_feature_values.setdefault(key_wmae_c, float("nan"))
                per_label_feature_values.setdefault(key_wcos_c, float("nan"))
                per_label_feature_values.setdefault(key_frac_c, float("nan"))
                mu_k_obs = mu_k[obs_mask]
                numer = 2.0 * (obs_vals - healthy_ref[obs_mask])
                denom = (mu_k_obs - healthy_ref[obs_mask]) + 1e-6
                directional = np.clip((numer / denom) - 1.0, -1.0, 1.0)
                wk = label_weight_vectors[k_idx]
                wk_obs = wk[obs_mask] if wk.shape[0] == obs_mask.shape[0] else default_weights[obs_mask]
                wk_obs = np.asarray(np.nan_to_num(wk_obs, nan=0.0, posinf=0.0, neginf=0.0), dtype=np.float64)
                if wk_obs.shape[0] != directional.shape[0]:
                    continue
                wk_sum = float(np.sum(wk_obs))
                if wk_sum <= 0.0:
                    continue
                fk = float(np.sum(wk_obs * directional) / wk_sum)
                rk = (obs_vals - healthy_ref[obs_mask]) / (mu_k_obs - healthy_ref[obs_mask] + 1e-6)
                zk = 2.0 * rk - 1.0
                cancer_like_k = (zk > 0.0).astype(np.float64)
                per_label_feature_values[key_da] = float(np.sum(wk_obs * cancer_like_k) / wk_sum)
                per_label_feature_values[key_wmae_c] = _weighted_mean_abs_error(obs_vals, mu_k_obs, wk_obs)
                per_label_feature_values[key_wcos_c] = _weighted_cosine_similarity(obs_vals, mu_k_obs, wk_obs)
                dist_h_k = np.abs(obs_vals - healthy_ref[obs_mask])
                dist_c_k = np.abs(obs_vals - mu_k_obs)
                per_label_feature_values[key_frac_c] = float(np.sum(wk_obs[dist_c_k < dist_h_k]) / wk_sum)
                if not np.isfinite(max_weighted_directional_score) or fk > max_weighted_directional_score:
                    max_weighted_directional_score = fk

            tail_feature_values: Dict[str, float] = {}
            if (
                hist_bin_edges is not None
                and hist_healthy_counts is not None
                and hist_healthy_counts.shape[0] == n_loci
            ):
                obs_idx = np.where(obs_mask)[0].astype(np.int64)
                obs_vals_safe = np.clip(np.asarray(obs_vals, dtype=np.float64), 0.0, 1.0)
                bin_idx = np.searchsorted(hist_bin_edges, obs_vals_safe, side="right") - 1
                bin_idx = np.clip(bin_idx, 0, max(0, len(hist_bin_edges) - 2)).astype(np.int64)
                ecdf_h = _ecdf_at(hist_healthy_counts, obs_idx, bin_idx)
                if ecdf_h.size == obs_vals.size:
                    for k_idx, label_raw in enumerate(cancer_labels_raw):
                        suffix = _feature_label_token(label_raw)
                        key_e = f"weighted_healthy_tail_evidence__{suffix}"
                        tail_feature_values.setdefault(key_e, float("nan"))
                        counts_c = hist_cancer_counts.get(label_raw)
                        if counts_c is None or counts_c.shape != hist_healthy_counts.shape:
                            continue
                        ecdf_c = _ecdf_at(counts_c, obs_idx, bin_idx)
                        if ecdf_c.size != ecdf_h.size:
                            continue
                        wk = label_weight_vectors[k_idx]
                        wk_obs = wk[obs_mask] if wk.shape[0] == obs_mask.shape[0] else default_weights[obs_mask]
                        wk_obs = np.asarray(
                            np.nan_to_num(wk_obs, nan=0.0, posinf=0.0, neginf=0.0),
                            dtype=np.float64,
                        )
                        mu_h_obs = healthy_ref[obs_mask]
                        mu_k_obs = per_cancer_refs[k_idx][obs_mask]
                        counts_h_rows = hist_healthy_counts[obs_idx, :]
                        counts_c_rows = counts_c[obs_idx, :]
                        tot_h = np.sum(counts_h_rows, axis=1)
                        tot_c = np.sum(counts_c_rows, axis=1)
                        delta = mu_k_obs - mu_h_obs
                        direction_valid = np.logical_or(delta > 0.0, delta < 0.0)
                        valid = (
                            np.isfinite(obs_vals)
                            & np.isfinite(mu_h_obs)
                            & np.isfinite(mu_k_obs)
                            & np.isfinite(wk_obs)
                            & (wk_obs > 0.0)
                            & (tot_h > 0.0)
                            & (tot_c > 0.0)
                            & direction_valid
                            & (np.abs(delta) >= hist_min_delta)
                        )
                        if not np.any(valid):
                            continue
                        ecdf_h_v = ecdf_h[valid]
                        ecdf_c_v = ecdf_c[valid]
                        wk_v = wk_obs[valid]
                        delta_v = delta[valid]
                        upper_tail = 1.0 - ecdf_h_v
                        lower_tail = ecdf_h_v
                        t = np.where(delta_v > 0.0, upper_tail, lower_tail)
                        t = np.clip(t, hist_eps, 1.0)
                        evidence = np.minimum(-np.log(t + hist_eps), hist_evidence_clip_cap)
                        wk_sum = float(np.sum(wk_v))
                        if wk_sum <= 0.0:
                            continue
                        tail_feature_values[key_e] = float(np.sum(wk_v * evidence) / wk_sum)

            healthy_obs = healthy_ref[obs_mask]
            cancer_obs = cancer_ref[obs_mask]
            wjs_h = _weighted_jensen_shannon_distance(obs_vals, healthy_obs, obs_w)
            wjs_c = _weighted_jensen_shannon_distance(obs_vals, cancer_obs, obs_w)
            wmae_h = _weighted_mean_abs_error(obs_vals, healthy_obs, obs_w)
            wmae_c = _weighted_mean_abs_error(obs_vals, cancer_obs, obs_w)
            weighted_mean_abs_distance_margin = float(wmae_h - wmae_c)
            wcos_h = _weighted_cosine_similarity(obs_vals, healthy_obs, obs_w)
            wcos_c = _weighted_cosine_similarity(obs_vals, cancer_obs, obs_w)
            weighted_centroid_contrast_score = (wcos_c - wcos_h) + (wjs_h - wjs_c)
        else:
            max_weighted_directional_score = float("nan")
            per_label_feature_values = {}
            tail_feature_values = {}
            wjs_h = float("nan")
            wjs_c = float("nan")
            wmae_h = float("nan")
            wmae_c = float("nan")
            weighted_mean_abs_distance_margin = float("nan")
            wcos_h = float("nan")
            wcos_c = float("nan")
            weighted_centroid_contrast_score = float("nan")

        obs_frac = float(n_obs / max(1, n_loci))
        if w.size == n_loci and total_w > 0.0:
            obs_w_frac = float(np.sum(w[obs_mask]) / total_w)
        else:
            obs_w_frac = obs_frac

        if include_dmp_family:
            X_feat[i, idx["max_weighted_directional_score"]] = max_weighted_directional_score
            X_feat[i, idx["weighted_mean_abs_distance_margin"]] = weighted_mean_abs_distance_margin
            X_feat[i, idx["weighted_centroid_contrast_score"]] = weighted_centroid_contrast_score
            X_feat[i, idx["obs_fraction"]] = obs_frac
            X_feat[i, idx["weighted_obs_fraction"]] = obs_w_frac
            X_feat[i, idx["n_obs_dmps"]] = float(n_obs)
            X_feat[i, idx["n_total_dmps"]] = float(n_loci)
            for feat_name, feat_value in per_label_feature_values.items():
                if feat_name in idx:
                    X_feat[i, idx[feat_name]] = float(feat_value)
            for feat_name, feat_value in tail_feature_values.items():
                if feat_name in idx:
                    X_feat[i, idx[feat_name]] = float(feat_value)

        if (include_gene_family or include_structural_family) and n_obs > 0:
            obs_df = locus_df.loc[np.where(obs_mask)[0]].copy()
            obs_df["_obs_val"] = obs_vals
            obs_df["_healthy_ref"] = healthy_ref[obs_mask]
            obs_df["_cancer_ref"] = cancer_ref[obs_mask]
            obs_df["_w"] = obs_w if obs_w.size == obs_vals.size else 1.0
            if "feature_type" in obs_df.columns:
                feature_series = obs_df["feature_type"]
            else:
                feature_series = pd.Series(["unknown"] * len(obs_df), index=obs_df.index, dtype=object)
            if "gene_name" in obs_df.columns:
                gene_series = obs_df["gene_name"]
            else:
                gene_series = pd.Series(["unknown"] * len(obs_df), index=obs_df.index, dtype=object)
            obs_df["feature_type"] = feature_series.apply(_normalize_structural_feature)
            obs_df["gene_name"] = gene_series.apply(_normalize_feature_key)
            obs_df["_delta_h"] = obs_df["_obs_val"] - obs_df["_healthy_ref"]
            obs_df["_delta_c"] = obs_df["_obs_val"] - obs_df["_cancer_ref"]
            obs_idx = np.where(obs_mask)[0]
            eff_signed = effect_loci[obs_idx]
            abs_eff = np.abs(eff_signed)
            centered_beta = np.asarray(obs_df["_obs_val"], dtype=np.float64) - 0.5
            obs_df["_eff_signed"] = eff_signed
            obs_df["_eff_abs"] = abs_eff
            obs_df["_centered_beta"] = centered_beta

            if include_gene_family:
                gdf = obs_df[
                    obs_df["gene_name"].apply(_is_known_mapped_token)
                    & np.isfinite(obs_df["_eff_abs"])
                    & (obs_df["_eff_abs"] > 0.0)
                    & np.isfinite(obs_df["_centered_beta"])
                ].copy()
                if not gdf.empty:
                    grouped = gdf.groupby("gene_name", sort=False, dropna=False)
                    for gene_name, g in grouped:
                        feature_name = f"gene::{gene_name}"
                        if feature_name not in gene_feature_set or feature_name not in idx:
                            continue
                        denom = float(np.sum(g["_eff_abs"].to_numpy(dtype=np.float64)))
                        if denom <= 0.0:
                            continue
                        numer = float(
                            np.sum(
                                g["_eff_signed"].to_numpy(dtype=np.float64)
                                * g["_centered_beta"].to_numpy(dtype=np.float64)
                            )
                        )
                        X_feat[i, idx[feature_name]] = float(numer / denom)

            if include_structural_family:
                sdf = obs_df[
                    obs_df["gene_name"].apply(_is_known_mapped_token)
                    & obs_df["feature_type"].apply(_is_known_mapped_token)
                    & (obs_df["feature_type"] != "unknown")
                    & np.isfinite(obs_df["_eff_abs"])
                    & (obs_df["_eff_abs"] > 0.0)
                    & np.isfinite(obs_df["_centered_beta"])
                ].copy()
                if not sdf.empty:
                    sdf["_struct_key"] = (
                        "struct::"
                        + sdf["gene_name"].astype(str)
                        + "::"
                        + sdf["feature_type"].astype(str)
                    )
                    grouped_s = sdf.groupby("_struct_key", sort=False, dropna=False)
                    for s_key, g in grouped_s:
                        if s_key not in struct_feature_set or s_key not in idx:
                            continue
                        denom = float(np.sum(g["_eff_abs"].to_numpy(dtype=np.float64)))
                        if denom <= 0.0:
                            continue
                        numer = float(
                            np.sum(
                                g["_eff_signed"].to_numpy(dtype=np.float64)
                                * g["_centered_beta"].to_numpy(dtype=np.float64)
                            )
                        )
                        X_feat[i, idx[s_key]] = float(numer / denom)

    non_nan = np.isfinite(X_feat).sum(axis=0).astype(int).tolist()
    gene_col_idx = [j for j, name in enumerate(feature_names) if str(name).startswith("gene::")]
    struct_col_idx = [j for j, name in enumerate(feature_names) if str(name).startswith("struct::")]
    if gene_col_idx:
        gene_non_empty_per_sample = np.isfinite(X_feat[:, gene_col_idx]).sum(axis=1).astype(int)
    else:
        gene_non_empty_per_sample = np.zeros((n_samples,), dtype=int)
    if struct_col_idx:
        struct_non_empty_per_sample = np.isfinite(X_feat[:, struct_col_idx]).sum(axis=1).astype(int)
    else:
        struct_non_empty_per_sample = np.zeros((n_samples,), dtype=int)
    schema_fingerprint = observed_hybrid_schema_fingerprint(
        cancer_class_labels=cancer_labels_raw,
        feature_family_set=str(feature_family_set),
        dmp_df=locus_df,
    )
    report = {
        "n_samples": int(n_samples),
        "n_loci_reference": int(n_loci),
        "n_features": int(len(feature_names)),
        "schema_version": HYBRID_FEATURE_SCHEMA_VERSION if (include_gene_family or include_structural_family) else OBSERVED_HYBRID_SCHEMA_VERSION,
        "quantiles": [0.10, 0.50, 0.90],
        "feature_families": {
            "dmp": bool(include_dmp_family),
            "chromosome": False,
            "dmr": False,
            "gene": bool(include_gene_family),
            "structural": bool(include_structural_family),
        },
        "feature_family_set": str(feature_family_set),
        "gene_feature_loading": gene_feature_loading_norm,
        "healthy_class_label": str(healthy_class_label or "unknown"),
        "cancer_class_labels": [str(x) for x in cancer_labels_raw],
        "anchor_strategy": str(anchor_strategy or "unspecified"),
        "hist_eps": hist_eps,
        "hist_alpha": hist_alpha,
        "hist_evidence_clip_cap": hist_evidence_clip_cap,
        "feature_order_fingerprint": observed_order_fp,
        "schema_fingerprint": schema_fingerprint,
        "feature_non_nan_counts": {feature_names[j]: int(non_nan[j]) for j in range(len(feature_names))},
        "raw_mapped_feature_formula": "signed_weighted_centered_beta",
        "raw_mapped_feature_counts": {
            "gene": int(len(gene_feature_names)),
            "structural": int(len(struct_feature_names)),
            "total_mapped": int(len(gene_feature_names) + len(struct_feature_names)),
        },
        "raw_mapped_non_empty_per_sample": {
            "gene_mean": float(np.mean(gene_non_empty_per_sample)) if n_samples > 0 else 0.0,
            "gene_min": int(np.min(gene_non_empty_per_sample)) if n_samples > 0 else 0,
            "gene_max": int(np.max(gene_non_empty_per_sample)) if n_samples > 0 else 0,
            "structural_mean": float(np.mean(struct_non_empty_per_sample)) if n_samples > 0 else 0.0,
            "structural_min": int(np.min(struct_non_empty_per_sample)) if n_samples > 0 else 0,
            "structural_max": int(np.max(struct_non_empty_per_sample)) if n_samples > 0 else 0,
        },
        "raw_mapped_feature_metadata": mapped_feature_meta,
    }
    return ObservedFeatureArtifacts(X=X_feat, feature_names=feature_names, report=report)


def verify_feature_schema(
    observed_feature_names: Sequence[str],
    expected_feature_names: Sequence[str],
    *,
    context: str,
) -> None:
    got = [str(x) for x in observed_feature_names]
    expected = [str(x) for x in expected_feature_names]
    if got == expected:
        return
    min_len = min(len(got), len(expected))
    mismatch_idx = None
    for i in range(min_len):
        if got[i] != expected[i]:
            mismatch_idx = i
            break
    if mismatch_idx is None and len(got) != len(expected):
        mismatch_idx = min_len
    idx_msg = f"first mismatch index={mismatch_idx}" if mismatch_idx is not None else "schemas differ"
    raise ValueError(
        f"{context}: observed feature schema mismatch ({idx_msg}); "
        f"expected={len(expected)} cols, got={len(got)} cols."
    )


def fit_feature_fill_values(X: np.ndarray) -> np.ndarray:
    """
    Fit per-column fill values for engineered features.

    This is feature-level fallback (not DMP-level imputation): if a feature is NaN
    for some samples, fill with train-column median; if column is all-NaN, fill 0.
    """
    arr = np.asarray(X, dtype=np.float32)
    if arr.ndim != 2:
        raise ValueError("Expected 2D feature matrix")
    fill = np.zeros((arr.shape[1],), dtype=np.float32)
    for j in range(arr.shape[1]):
        col = arr[:, j]
        finite = col[np.isfinite(col)]
        if finite.size == 0:
            fill[j] = 0.0
        else:
            fill[j] = float(np.median(finite))
    return fill


def apply_feature_fill_values(X: np.ndarray, fill_values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(X, dtype=np.float32).copy()
    fill = np.asarray(fill_values, dtype=np.float32)
    if arr.ndim != 2:
        raise ValueError("Expected 2D feature matrix")
    if fill.shape[0] != arr.shape[1]:
        raise ValueError(f"fill_values length mismatch: {fill.shape[0]} != {arr.shape[1]}")
    mask = ~np.isfinite(arr)
    if np.any(mask):
        arr[mask] = np.take(fill, np.where(mask)[1])
    return arr


def sample_ids_from_paths(sample_paths: Sequence[str]) -> List[str]:
    return [Path(str(p)).name for p in sample_paths]