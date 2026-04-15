"""
Observed-only hybrid feature builder for backend training/prediction.

This module intentionally avoids DMP-level value imputation. Per-sample features are
computed only from loci observed in that sample, plus explicit reliability features.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from methyl_utils.methyl_centroid_pair import MethylCentroidPair


@dataclass
class ObservedFeatureArtifacts:
    X: np.ndarray
    feature_names: List[str]
    report: Dict[str, Any]


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


def _default_dmr_region_id(chrom: str, position: int, window_bp: int) -> str:
    w = max(1, int(window_bp))
    start = int(position // w) * w
    end = start + w
    return f"{chrom}:{start}-{end}"


def _select_top_tokens(
    tokens: Sequence[str],
    locus_weights: np.ndarray,
    *,
    max_items: int,
) -> List[str]:
    if max_items <= 0:
        return []
    score_map: Dict[str, float] = {}
    for idx, token in enumerate(tokens):
        t = str(token or "").strip()
        if not t or t == "unknown":
            continue
        score_map[t] = float(score_map.get(t, 0.0) + abs(float(locus_weights[idx])))
    ranked = sorted(score_map.items(), key=lambda kv: (-kv[1], kv[0]))
    return [name for name, _score in ranked[: int(max_items)]]


def _feature_names_for_named_groups(prefix: str, names: Sequence[str]) -> List[str]:
    out: List[str] = []
    for name in names:
        safe = str(name).replace(" ", "_")
        out.append(f"{prefix}_{safe}_weighted_mean")
        out.append(f"{prefix}_{safe}_obs_fraction")
    return out


def _build_reference_map(
    dmp_df: pd.DataFrame,
) -> Tuple[Dict[str, Dict[str, np.ndarray]], List[Tuple[str, str, int]], np.ndarray, pd.DataFrame]:
    refs: Dict[str, Dict[str, np.ndarray]] = {}
    order: List[Tuple[str, str, int]] = []
    weights: List[float] = []

    work_df = dmp_df.copy()
    w_col = "weight" if "weight" in work_df.columns else "effect_size"
    if w_col not in work_df.columns:
        work_df["weight"] = 1.0
        w_col = "weight"
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

    work_df["_score"] = np.abs(pd.to_numeric(work_df[w_col], errors="coerce").fillna(0.0).astype(float))
    if "effect_size" in work_df.columns:
        work_df["_score"] = np.maximum(
            work_df["_score"].astype(float),
            np.abs(pd.to_numeric(work_df["effect_size"], errors="coerce").fillna(0.0).astype(float)),
        )
    work_df = work_df.sort_values(
        ["_score", "chromosome", "context", "position"],
        ascending=[False, True, True, True],
    )
    locus_df = work_df.drop_duplicates(["chromosome", "context", "position"], keep="first").copy()
    locus_df["w"] = pd.to_numeric(locus_df[w_col], errors="coerce").fillna(0.0).astype(float)
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
        return refs, order, w, locus_df.reset_index(drop=True)
    w = np.abs(np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0))
    mx = float(np.max(w))
    if mx <= 0.0:
        w = np.ones_like(w, dtype=np.float32)
    else:
        w = w / mx
    return refs, order, w, locus_df.reset_index(drop=True)


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


def _feature_names_for_chromosomes(chromosomes: Iterable[str]) -> List[str]:
    out: List[str] = []
    for chrom in chromosomes:
        out.append(f"chrom_{chrom}_weighted_mean")
        out.append(f"chrom_{chrom}_obs_fraction")
    return out


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
) -> ObservedFeatureArtifacts:
    """
    Build observed-only hybrid features from bundle DMP loci.

    Feature families:
    - DMP-derived global and quantile summaries (enabled by include_dmp_features)
    - Disease/comparison summaries from DMP comparison_label (include_dmp_features)
    - Per-chromosome weighted means + observed fractions (include_chromosome_features)
    - DMR/region summaries (include_dmr_features)
    - Gene summaries (include_gene_features)
    - Reliability/evidence features (always included)
    """
    if quantiles is None:
        quantiles = (0.10, 0.25, 0.50, 0.75, 0.90)
    qv = [float(q) for q in quantiles if 0.0 <= float(q) <= 1.0]
    if not qv:
        qv = [0.5]

    refs, feature_order, weights, locus_df = _build_reference_map(dmp_df)
    if "dmr_region" not in locus_df.columns:
        locus_df = locus_df.copy()
        locus_df["dmr_region"] = [
            _default_dmr_region_id(str(chrom), int(pos), int(max(1, dmr_window_bp)))
            for chrom, pos in zip(
                locus_df["chromosome"].astype(str).tolist(),
                locus_df["position"].astype(int).tolist(),
            )
        ]
    else:
        dmr_vals = [
            _normalize_feature_key(v) if str(v).strip().lower() != "unknown" else ""
            for v in locus_df["dmr_region"].tolist()
        ]
        locus_df["dmr_region"] = [
            d if d else _default_dmr_region_id(str(chrom), int(pos), int(max(1, dmr_window_bp)))
            for d, chrom, pos in zip(
                dmr_vals,
                locus_df["chromosome"].astype(str).tolist(),
                locus_df["position"].astype(int).tolist(),
            )
        ]

    X_raw = _extract_matrix_for_samples(
        sample_paths,
        refs,
        feature_order,
        min_coverage=min_coverage,
    )

    n_samples = int(X_raw.shape[0])
    n_loci = int(X_raw.shape[1])
    w = np.asarray(weights, dtype=np.float64)
    if n_loci > 0 and (w.size != n_loci):
        # Defensive alignment fallback.
        w = np.ones((n_loci,), dtype=np.float64)
    total_w = float(np.sum(w)) if w.size else 0.0

    chroms = sorted({c for c, _ctx, _pos in feature_order}, key=lambda x: (len(str(x)), str(x)))
    chrom_to_indices: Dict[str, np.ndarray] = {}
    for chrom in chroms:
        idxs = [i for i, (c, _ctx, _pos) in enumerate(feature_order) if c == chrom]
        chrom_to_indices[chrom] = np.asarray(idxs, dtype=np.int32)

    comparison_labels = (
        locus_df["comparison_label"].astype(str).tolist()
        if "comparison_label" in locus_df.columns
        else ["default"] * n_loci
    )
    region_labels = (
        locus_df["dmr_region"].astype(str).tolist()
        if "dmr_region" in locus_df.columns
        else ["unknown"] * n_loci
    )
    gene_labels = (
        locus_df["gene_name"].astype(str).tolist()
        if "gene_name" in locus_df.columns
        else ["unknown"] * n_loci
    )
    if len(comparison_labels) != n_loci:
        comparison_labels = ["default"] * n_loci
    if len(region_labels) != n_loci:
        region_labels = ["unknown"] * n_loci
    if len(gene_labels) != n_loci:
        gene_labels = ["unknown"] * n_loci

    comparison_names = sorted({c for c in comparison_labels if c}, key=lambda x: x)
    comparison_to_indices: Dict[str, np.ndarray] = {
        comp: np.asarray([i for i, name in enumerate(comparison_labels) if name == comp], dtype=np.int32)
        for comp in comparison_names
    }
    selected_regions = _select_top_tokens(region_labels, w, max_items=int(max(0, max_dmr_features)))
    region_to_indices: Dict[str, np.ndarray] = {
        name: np.asarray([i for i, token in enumerate(region_labels) if token == name], dtype=np.int32)
        for name in selected_regions
    }
    selected_genes = _select_top_tokens(gene_labels, w, max_items=int(max(0, max_gene_features)))
    gene_to_indices: Dict[str, np.ndarray] = {
        name: np.asarray([i for i, token in enumerate(gene_labels) if token == name], dtype=np.int32)
        for name in selected_genes
    }

    # Build feature names.
    feature_names: List[str] = []
    if include_dmp_features:
        feature_names.extend(
            [
                "dmp_global_weighted_mean",
                "dmp_global_weighted_std",
                "dmp_global_weighted_shift_from_half",
                "dmp_global_weighted_abs_shift_from_half",
            ]
        )
        feature_names.extend([f"dmp_global_quantile_q{int(round(q * 100))}" for q in qv])
        feature_names.extend(_feature_names_for_named_groups("disease", comparison_names))
    if include_chromosome_features:
        feature_names.extend(_feature_names_for_chromosomes(chroms))
    if include_dmr_features:
        feature_names.extend(_feature_names_for_named_groups("dmr", selected_regions))
    if include_gene_features:
        feature_names.extend(_feature_names_for_named_groups("gene", selected_genes))
    feature_names.extend(
        [
            "obs_fraction",
            "obs_weight_fraction",
            "n_obs_dmps",
            "n_total_dmps",
        ]
    )

    n_features = len(feature_names)
    X_feat = np.full((n_samples, n_features), np.nan, dtype=np.float32)

    for i in range(n_samples):
        row = np.asarray(X_raw[i, :], dtype=np.float64) if n_loci > 0 else np.asarray([], dtype=np.float64)
        obs_mask = np.isfinite(row)
        obs_vals = row[obs_mask]
        obs_w = w[obs_mask] if (w.size and obs_mask.size == w.size) else np.asarray([], dtype=np.float64)

        cursor = 0
        if include_dmp_features:
            if obs_vals.size > 0 and obs_w.size > 0 and float(np.sum(obs_w)) > 0.0:
                g_mean = _weighted_mean(obs_vals, obs_w)
                g_std = _weighted_std(obs_vals, obs_w)
                shift = _weighted_mean(obs_vals - 0.5, obs_w)
                abs_shift = _weighted_mean(np.abs(obs_vals - 0.5), obs_w)
            elif obs_vals.size > 0:
                g_mean = float(np.mean(obs_vals))
                g_std = float(np.std(obs_vals))
                shift = float(np.mean(obs_vals - 0.5))
                abs_shift = float(np.mean(np.abs(obs_vals - 0.5)))
            else:
                g_mean = float("nan")
                g_std = float("nan")
                shift = float("nan")
                abs_shift = float("nan")
            X_feat[i, cursor : cursor + 4] = [g_mean, g_std, shift, abs_shift]
            cursor += 4

            if obs_vals.size > 0:
                qvals = np.quantile(obs_vals, qv)
                X_feat[i, cursor : cursor + len(qv)] = qvals.astype(np.float32)
            cursor += len(qv)

            for comp in comparison_names:
                idxs = comparison_to_indices.get(comp, np.asarray([], dtype=np.int32))
                if idxs.size == 0 or n_loci == 0:
                    X_feat[i, cursor : cursor + 2] = [np.nan, 0.0]
                    cursor += 2
                    continue
                vals = row[idxs]
                mask = np.isfinite(vals)
                obs_c = vals[mask]
                if obs_c.size == 0:
                    X_feat[i, cursor : cursor + 2] = [np.nan, 0.0]
                    cursor += 2
                    continue
                if w.size == n_loci:
                    w_c = w[idxs][mask]
                    mean_c = _weighted_mean(obs_c, w_c) if float(np.sum(w_c)) > 0.0 else float(np.mean(obs_c))
                else:
                    mean_c = float(np.mean(obs_c))
                frac_c = float(obs_c.size / max(1, idxs.size))
                X_feat[i, cursor : cursor + 2] = [mean_c, frac_c]
                cursor += 2

        if include_chromosome_features:
            for chrom in chroms:
                idxs = chrom_to_indices[chrom]
                if idxs.size == 0 or n_loci == 0:
                    X_feat[i, cursor : cursor + 2] = [np.nan, 0.0]
                    cursor += 2
                    continue
                vals_c = row[idxs]
                mask_c = np.isfinite(vals_c)
                obs_c = vals_c[mask_c]
                if obs_c.size == 0:
                    X_feat[i, cursor : cursor + 2] = [np.nan, 0.0]
                    cursor += 2
                    continue
                if w.size == n_loci:
                    w_c = w[idxs][mask_c]
                    mean_c = _weighted_mean(obs_c, w_c) if float(np.sum(w_c)) > 0.0 else float(np.mean(obs_c))
                else:
                    mean_c = float(np.mean(obs_c))
                frac_c = float(obs_c.size / max(1, idxs.size))
                X_feat[i, cursor : cursor + 2] = [mean_c, frac_c]
                cursor += 2

        if include_dmr_features:
            for name in selected_regions:
                idxs = region_to_indices.get(name, np.asarray([], dtype=np.int32))
                if idxs.size == 0 or n_loci == 0:
                    X_feat[i, cursor : cursor + 2] = [np.nan, 0.0]
                    cursor += 2
                    continue
                vals = row[idxs]
                mask = np.isfinite(vals)
                obs_c = vals[mask]
                if obs_c.size == 0:
                    X_feat[i, cursor : cursor + 2] = [np.nan, 0.0]
                    cursor += 2
                    continue
                if w.size == n_loci:
                    w_c = w[idxs][mask]
                    mean_c = _weighted_mean(obs_c, w_c) if float(np.sum(w_c)) > 0.0 else float(np.mean(obs_c))
                else:
                    mean_c = float(np.mean(obs_c))
                frac_c = float(obs_c.size / max(1, idxs.size))
                X_feat[i, cursor : cursor + 2] = [mean_c, frac_c]
                cursor += 2

        if include_gene_features:
            for name in selected_genes:
                idxs = gene_to_indices.get(name, np.asarray([], dtype=np.int32))
                if idxs.size == 0 or n_loci == 0:
                    X_feat[i, cursor : cursor + 2] = [np.nan, 0.0]
                    cursor += 2
                    continue
                vals = row[idxs]
                mask = np.isfinite(vals)
                obs_c = vals[mask]
                if obs_c.size == 0:
                    X_feat[i, cursor : cursor + 2] = [np.nan, 0.0]
                    cursor += 2
                    continue
                if w.size == n_loci:
                    w_c = w[idxs][mask]
                    mean_c = _weighted_mean(obs_c, w_c) if float(np.sum(w_c)) > 0.0 else float(np.mean(obs_c))
                else:
                    mean_c = float(np.mean(obs_c))
                frac_c = float(obs_c.size / max(1, idxs.size))
                X_feat[i, cursor : cursor + 2] = [mean_c, frac_c]
                cursor += 2

        n_obs = int(obs_vals.size)
        obs_frac = float(n_obs / max(1, n_loci))
        if w.size == n_loci and total_w > 0.0 and n_loci > 0:
            obs_w_frac = float(np.sum(w[obs_mask]) / total_w)
        else:
            obs_w_frac = obs_frac
        X_feat[i, cursor : cursor + 4] = [obs_frac, obs_w_frac, float(n_obs), float(n_loci)]

    non_nan = np.isfinite(X_feat).sum(axis=0).astype(int).tolist()
    schema_fingerprint = hashlib.sha256("\n".join(feature_names).encode("utf-8")).hexdigest()
    report = {
        "n_samples": int(n_samples),
        "n_loci_reference": int(n_loci),
        "n_features": int(n_features),
        "quantiles": [float(q) for q in qv],
        "feature_families": {
            "dmp": bool(include_dmp_features),
            "chromosome": bool(include_chromosome_features),
            "dmr": bool(include_dmr_features),
            "gene": bool(include_gene_features),
        },
        "selected_comparisons": [str(x) for x in comparison_names],
        "selected_dmrs": [str(x) for x in selected_regions],
        "selected_genes": [str(x) for x in selected_genes],
        "dmr_window_bp": int(max(1, dmr_window_bp)),
        "max_dmr_features": int(max(0, max_dmr_features)),
        "max_gene_features": int(max(0, max_gene_features)),
        "schema_fingerprint": schema_fingerprint,
        "feature_non_nan_counts": {feature_names[j]: int(non_nan[j]) for j in range(n_features)},
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

