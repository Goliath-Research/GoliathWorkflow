"""
One-vs-rest (OvR) helpers for K-way ECDF classification.

Stateless utilities: union DMP table construction, column maps, and fusion of K
binary (n, 2) probability matrices into (n, K). Orchestration lives on MethylClassifier.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

ECDF_ONE_VS_REST_TYPE = "ecdf_one_vs_rest"
OV_R_PACKAGE_VERSION = 2


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


class OvrMultiChromBinaryExpert:
    """
    One OvR class head: per-chromosome binary ECDFs + weights, fused to (n_samples, 2)
    like MethylClassifier multi-chromosome mode.
    """

    def __init__(
        self,
        classifiers: Dict[str, Any],
        chromosome_weights: Dict[str, float],
    ) -> None:
        self.classifiers = {str(k): v for k, v in classifiers.items()}
        self.chromosome_weights = {str(k): float(v) for k, v in chromosome_weights.items()}

    def set_temperature(self, temperature: float) -> None:
        for clf in self.classifiers.values():
            _t = (
                clf.classifier
                if (
                    hasattr(clf, "classifier")
                    and hasattr(getattr(clf, "classifier", None), "set_temperature")
                )
                else clf
            )
            if hasattr(_t, "set_temperature"):
                _t.set_temperature(temperature)

    def predict_proba_binary(
        self,
        methylation_data: np.ndarray,
        availability_mask: Optional[np.ndarray],
        idx: np.ndarray,
        positions_df: pd.DataFrame,
        *,
        calibrated: bool,
        debug: bool = False,
    ) -> np.ndarray:
        n_samples = int(methylation_data.shape[0])
        idx = np.asarray(idx, dtype=np.intp)
        sub_df = positions_df.iloc[idx].reset_index(drop=True)
        sub_df["__slot"] = np.arange(len(sub_df), dtype=np.intp)

        chrom_order = sorted(self.classifiers.keys(), key=lambda x: (len(str(x)), str(x)))
        n_classes = 2
        weighted = np.zeros((n_samples, n_classes), dtype=np.float64)
        active_w = 0.0

        for chrom in chrom_order:
            w = float(self.chromosome_weights.get(chrom, 0.0))
            if w == 0.0:
                continue
            clf = self.classifiers[chrom]
            fi = clf.get_feature_info()
            n_feat = int(fi["n_features"])
            pos_expected = np.asarray(fi["positions"], dtype=np.uint32)

            sel = sub_df.loc[sub_df["chromosome"].astype(str).values == str(chrom)]
            if len(sel) == 0:
                continue
            sel = sel.sort_values("position")
            slots = sel["__slot"].values.astype(np.intp)
            if len(slots) != n_feat:
                raise ValueError(
                    f"OvR multichrom expert chr{chrom}: classifier expects {n_feat} features, "
                    f"union slice has {len(slots)} rows for this chromosome"
                )
            got_pos = sel["position"].astype(np.uint32).values
            if not np.array_equal(got_pos, pos_expected):
                raise ValueError(
                    f"OvR multichrom expert chr{chrom}: union positions do not match classifier order"
                )

            Xc = np.ascontiguousarray(methylation_data[:, idx[slots]], dtype=np.float64)
            Mc = availability_mask[:, idx[slots]] if availability_mask is not None else None

            if (
                calibrated
                and hasattr(clf, "predict_proba_calibrated")
                and getattr(clf, "calibrator", None) is not None
            ):
                pc = clf.predict_proba_calibrated(Xc, Mc)
            else:
                pc = clf.predict_proba(Xc, Mc, debug=debug)
            weighted += w * pc
            active_w += w

        if active_w <= 0.0:
            return np.full((n_samples, n_classes), 0.5, dtype=np.float64)
        s = np.sum(weighted, axis=1, keepdims=True)
        s = np.where(s == 0, 1.0, s)
        return weighted / s


def dmp_rows_from_binary_entry(
    entry: Dict[str, Any],
    default_chromosome: str = "1",
) -> List[Tuple[str, int]]:
    """
    Return ordered list of (chromosome, position) for one OvR binary model.

    Prefer entry['dmp_df'] with chromosome + position (or pos).
    Else use entry['chromosome'] + ECDF positions.
    """
    if entry.get("chrom_classifiers"):
        if entry.get("dmp_df") is None:
            raise ValueError("Multichrom OvR binary entry requires dmp_df")
        df = _normalize_dmp_columns(entry["dmp_df"])
        if "chromosome" not in df.columns or "position" not in df.columns:
            raise ValueError("Multichrom OvR dmp_df must have chromosome and position columns")
        chrom_col = df["chromosome"].map(_normalize_chrom)
        pos_col = df["position"].astype(np.uint64).astype(np.int64)
        return list(zip(chrom_col.tolist(), pos_col.tolist()))

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
