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


OBSERVED_HYBRID_SCHEMA_VERSION = "observed_hybrid_v20_add_max_weighted_directional_score"
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
) -> ObservedHybridAnchors:
    refs, feature_order, _weights, _locus_df, _per_label_weights = _build_reference_map(dmp_df)
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


def _fixed_feature_names() -> List[str]:
    names = [
        "max_weighted_directional_score",
        "weighted_js_distance_to_healthy_centroid",
        "weighted_js_distance_to_cancer_centroid",
        "weighted_mean_abs_error_to_healthy_centroid",
        "weighted_mean_abs_error_to_cancer_centroid",
        "weighted_mean_abs_distance_margin",
        "weighted_cosine_similarity_to_healthy_centroid",
        "weighted_cosine_similarity_to_cancer_centroid",
        "weighted_centroid_contrast_score",
        "weighted_fraction_dmps_closer_to_cancer_centroid",
        "weighted_fraction_dmps_closer_to_healthy_centroid",
        "obs_fraction",
        "weighted_obs_fraction",
        "n_obs_dmps",
        "n_total_dmps",
    ]
    return [name for name in names if name not in REMOVED_OBSERVED_HYBRID_FEATURES]


def observed_hybrid_feature_names() -> List[str]:
    return _fixed_feature_names()


def observed_hybrid_schema_fingerprint() -> str:
    return hashlib.sha256("\n".join(_fixed_feature_names()).encode("utf-8")).hexdigest()


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
) -> ObservedFeatureArtifacts:
    del quantiles, dmr_window_bp, max_dmr_features, max_gene_features
    # The redesigned schema is fixed; these toggles are retained only for compatibility.
    del include_dmp_features, include_chromosome_features, include_dmr_features, include_gene_features

    refs, feature_order, weights, _locus_df, per_label_weights = _build_reference_map(dmp_df)
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

    feature_names = _fixed_feature_names()
    X_feat = np.full((n_samples, len(feature_names)), np.nan, dtype=np.float32)

    idx = {name: j for j, name in enumerate(feature_names)}
    cancer_labels_norm = [str(lbl).strip().lower() for lbl in (cancer_class_labels or [])]
    per_label_weights_norm = {
        str(key).strip().lower(): np.asarray(vec, dtype=np.float64) for key, vec in per_label_weights.items()
    }
    default_weights = np.asarray(w, dtype=np.float64)

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

    for i in range(n_samples):
        row = np.asarray(X_raw[i, :], dtype=np.float64)
        obs_mask = np.isfinite(row)
        obs_vals = row[obs_mask]
        obs_w = w[obs_mask] if obs_mask.size == w.size else np.asarray([], dtype=np.float64)
        n_obs = int(obs_vals.size)

        if n_obs > 0:
            max_weighted_directional_score = float("nan")
            for k_idx, mu_k in enumerate(per_cancer_refs):
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
                if not np.isfinite(max_weighted_directional_score) or fk > max_weighted_directional_score:
                    max_weighted_directional_score = fk
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
            dist_h = np.abs(obs_vals - healthy_obs)
            dist_c = np.abs(obs_vals - cancer_obs)
            obs_w_sum = float(np.sum(obs_w))
            if obs_w.size == obs_vals.size and obs_w_sum > 0.0:
                weighted_closer_to_cancer = float(np.sum(obs_w[dist_c < dist_h]) / obs_w_sum)
                weighted_closer_to_healthy = float(np.sum(obs_w[dist_h < dist_c]) / obs_w_sum)
            else:
                weighted_closer_to_cancer = float("nan")
                weighted_closer_to_healthy = float("nan")
        else:
            max_weighted_directional_score = float("nan")
            wjs_h = float("nan")
            wjs_c = float("nan")
            wmae_h = float("nan")
            wmae_c = float("nan")
            weighted_mean_abs_distance_margin = float("nan")
            wcos_h = float("nan")
            wcos_c = float("nan")
            weighted_centroid_contrast_score = float("nan")
            weighted_closer_to_cancer = float("nan")
            weighted_closer_to_healthy = float("nan")

        obs_frac = float(n_obs / max(1, n_loci))
        if w.size == n_loci and total_w > 0.0:
            obs_w_frac = float(np.sum(w[obs_mask]) / total_w)
        else:
            obs_w_frac = obs_frac

        X_feat[i, idx["max_weighted_directional_score"]] = max_weighted_directional_score
        X_feat[i, idx["weighted_js_distance_to_healthy_centroid"]] = wjs_h
        X_feat[i, idx["weighted_js_distance_to_cancer_centroid"]] = wjs_c
        X_feat[i, idx["weighted_mean_abs_error_to_healthy_centroid"]] = wmae_h
        X_feat[i, idx["weighted_mean_abs_error_to_cancer_centroid"]] = wmae_c
        X_feat[i, idx["weighted_mean_abs_distance_margin"]] = weighted_mean_abs_distance_margin
        X_feat[i, idx["weighted_cosine_similarity_to_healthy_centroid"]] = wcos_h
        X_feat[i, idx["weighted_cosine_similarity_to_cancer_centroid"]] = wcos_c
        X_feat[i, idx["weighted_centroid_contrast_score"]] = weighted_centroid_contrast_score
        X_feat[i, idx["weighted_fraction_dmps_closer_to_cancer_centroid"]] = weighted_closer_to_cancer
        X_feat[i, idx["weighted_fraction_dmps_closer_to_healthy_centroid"]] = weighted_closer_to_healthy
        X_feat[i, idx["obs_fraction"]] = obs_frac
        X_feat[i, idx["weighted_obs_fraction"]] = obs_w_frac
        X_feat[i, idx["n_obs_dmps"]] = float(n_obs)
        X_feat[i, idx["n_total_dmps"]] = float(n_loci)

    non_nan = np.isfinite(X_feat).sum(axis=0).astype(int).tolist()
    schema_fingerprint = observed_hybrid_schema_fingerprint()
    report = {
        "n_samples": int(n_samples),
        "n_loci_reference": int(n_loci),
        "n_features": int(len(feature_names)),
        "schema_version": OBSERVED_HYBRID_SCHEMA_VERSION,
        "quantiles": [0.10, 0.50, 0.90],
        "feature_families": {
            "dmp": True,
            "chromosome": False,
            "dmr": False,
            "gene": False,
        },
        "healthy_class_label": str(healthy_class_label or "unknown"),
        "cancer_class_labels": [str(x) for x in (cancer_class_labels or [])],
        "anchor_strategy": str(anchor_strategy or "unspecified"),
        "feature_order_fingerprint": observed_order_fp,
        "schema_fingerprint": schema_fingerprint,
        "feature_non_nan_counts": {feature_names[j]: int(non_nan[j]) for j in range(len(feature_names))},
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
