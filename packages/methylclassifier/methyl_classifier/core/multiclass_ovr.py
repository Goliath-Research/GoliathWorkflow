"""
One-vs-rest (OvR) helpers for K-way ECDF classification.

Stateless utilities: union DMP table construction, column maps, and fusion of K
binary (n, 2) probability matrices into (n, K). Orchestration lives on MethylClassifier.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple, Union

import numpy as np
import pandas as pd

ECDF_ONE_VS_REST_TYPE = "ecdf_one_vs_rest"
OV_R_PACKAGE_VERSION = 1


def _normalize_chrom(c: Any) -> str:
    s = str(c).strip()
    if s.lower().startswith("chr"):
        s = s[3:]
    return s or str(c)


def _normalize_dmp_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "position" not in out.columns and "pos" in out.columns:
        out = out.rename(columns={"pos": "position"})
    if "chromosome" not in out.columns and "chrom" in out.columns:
        out = out.rename(columns={"chrom": "chromosome"})
    return out


def dmp_rows_from_binary_entry(
    entry: Dict[str, Any],
    default_chromosome: str = "1",
) -> List[Tuple[str, int]]:
    """
    Return ordered list of (chromosome, position) for one OvR binary model.

    Prefer entry['dmp_df'] with chromosome + position (or pos).
    Else use entry['chromosome'] + ECDF positions.
    """
    if "dmp_df" in entry and entry["dmp_df"] is not None:
        df = _normalize_dmp_columns(entry["dmp_df"])
        if "chromosome" not in df.columns or "position" not in df.columns:
            raise ValueError(
                "OvR binary model dmp_df must have chromosome and position (or pos) columns"
            )
        chrom_col = df["chromosome"].map(_normalize_chrom)
        pos_col = df["position"].astype(np.uint64).astype(np.int64)
        return list(zip(chrom_col.tolist(), pos_col.tolist()))

    ecdf = entry.get("ecdf")
    if ecdf is None:
        raise ValueError("OvR binary model needs 'ecdf' or 'dmp_df'")
    chrom = _normalize_chrom(entry.get("chromosome", default_chromosome))
    pos = np.asarray(ecdf.positions, dtype=np.uint32).ravel()
    return [(chrom, int(p)) for p in pos]


def build_union_dmp_dataframe(
    binary_entries: Sequence[Dict[str, Any]],
    default_chromosome: str = "1",
) -> Tuple[pd.DataFrame, List[np.ndarray]]:
    """
    Unique (chromosome, position) rows in stable sorted order; one column per row in flat X.

    Returns
    -------
    dmp_positions_df : DataFrame with columns chromosome (category), position (uint32)
    column_indices : list of length K; column_indices[k] maps binary model k columns -> union columns
    """
    all_rows: List[Tuple[str, int]] = []
    per_entry_rows: List[List[Tuple[str, int]]] = []
    for entry in binary_entries:
        rows = dmp_rows_from_binary_entry(entry, default_chromosome=default_chromosome)
        per_entry_rows.append(rows)
        all_rows.extend(rows)

    unique_sorted = sorted(set(all_rows), key=lambda t: (t[0], t[1]))
    df = pd.DataFrame(unique_sorted, columns=["chromosome", "position"])
    df["chromosome"] = df["chromosome"].astype(str).astype("category")
    df["position"] = df["position"].astype(np.uint32)

    key_to_idx = {(c, int(p)): i for i, (c, p) in enumerate(unique_sorted)}
    column_indices: List[np.ndarray] = []
    for rows in per_entry_rows:
        idx = np.array([key_to_idx[(c, int(p))] for c, p in rows], dtype=np.int32)
        column_indices.append(idx)

    return df, column_indices


def fuse_ovr_binary_probas(
    binary_probas: Sequence[np.ndarray],
    eps: float = 1e-12,
) -> np.ndarray:
    """
    Fuse K matrices of shape (n_samples, 2) into (n_samples, K) probabilities.

    Uses logit_k = log(P_k+) - log(P_k-) with log-sum-exp normalization (temperature 1).
    """
    if not binary_probas:
        raise ValueError("binary_probas must be non-empty")
    n = int(binary_probas[0].shape[0])
    K = len(binary_probas)
    logits = np.zeros((n, K), dtype=np.float64)
    for k, p in enumerate(binary_probas):
        if p.shape != (n, 2):
            raise ValueError(f"Expected proba shape ({n}, 2), got {p.shape}")
        p0 = np.clip(p[:, 0], eps, 1.0)
        p1 = np.clip(p[:, 1], eps, 1.0)
        logits[:, k] = np.log(p1) - np.log(p0)
    logits -= np.max(logits, axis=1, keepdims=True)
    ex = np.exp(logits)
    denom = np.sum(ex, axis=1, keepdims=True)
    denom = np.where(denom == 0, 1.0, denom)
    return ex / denom
