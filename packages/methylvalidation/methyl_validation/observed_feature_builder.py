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


def _build_reference_map(
    dmp_df: pd.DataFrame,
) -> Tuple[Dict[str, Dict[str, np.ndarray]], List[Tuple[str, str, int]], np.ndarray]:
    refs: Dict[str, Dict[str, np.ndarray]] = {}
    order: List[Tuple[str, str, int]] = []
    weights: List[float] = []

    w_col = "weight" if "weight" in dmp_df.columns else "effect_size"
    if w_col not in dmp_df.columns:
        dmp_df = dmp_df.copy()
        dmp_df["weight"] = 1.0
        w_col = "weight"

    grouped = dmp_df.groupby(["chromosome", "context", "position"], as_index=False)
    # Keep max weight/effect_size per unique locus tuple.
    agg = grouped[w_col].max().rename(columns={w_col: "w"})
    agg["chromosome"] = agg["chromosome"].astype(str)
    agg["context"] = agg["context"].astype(str)
    agg["position"] = pd.to_numeric(agg["position"], errors="coerce").fillna(-1).astype(int)
    agg = agg[agg["position"] >= 0].copy()

    for chrom, cdf in agg.groupby("chromosome", sort=True):
        refs[str(chrom)] = {}
        for ctx, xdf in cdf.groupby("context", sort=False):
            poss = np.asarray(sorted(set(int(v) for v in xdf["position"].tolist())), dtype=np.uint32)
            refs[str(chrom)][str(ctx)] = poss
        for _, row in cdf.iterrows():
            order.append((str(row["chromosome"]), str(row["context"]), int(row["position"])))
            weights.append(float(row["w"]))

    w = np.asarray(weights, dtype=np.float32)
    if w.size == 0:
        return refs, order, w
    w = np.abs(np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0))
    mx = float(np.max(w))
    if mx <= 0.0:
        w = np.ones_like(w, dtype=np.float32)
    else:
        w = w / mx
    return refs, order, w


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
) -> ObservedFeatureArtifacts:
    """
    Build observed-only hybrid features from bundle DMP loci.

    Features include:
    - global weighted methylation summaries
    - methylation quantiles from observed loci only
    - per-chromosome weighted means + observed fractions
    - reliability/evidence features
    """
    if quantiles is None:
        quantiles = (0.10, 0.25, 0.50, 0.75, 0.90)
    qv = [float(q) for q in quantiles if 0.0 <= float(q) <= 1.0]
    if not qv:
        qv = [0.5]

    refs, feature_order, weights = _build_reference_map(dmp_df)
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

    # Build feature names.
    feature_names: List[str] = [
        "global_weighted_mean",
        "global_weighted_std",
        "global_weighted_shift_from_half",
        "global_weighted_abs_shift_from_half",
    ]
    feature_names.extend([f"global_quantile_q{int(round(q * 100))}" for q in qv])
    feature_names.extend(_feature_names_for_chromosomes(chroms))
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

