"""
Build a native multiclass histogram classifier package from a merged DMP table.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from methyl_utils import load_from_h5

from ..core.native_multiclass import NativeMulticlassHistogramClassifier

NATIVE_MULTICLASS_TYPE = "native_multiclass_histogram"
NATIVE_MULTICLASS_VERSION = 2
_REQUIRED_DMP_COLS = {"chromosome", "context", "position"}
_DEFAULT_WEIGHT_COLS = (
    "classifier_weight",
    "weight",
    "importance",
    "effect_size_sum",
    "effect_size_max",
    "effect_size",
)


def _prepare_feature_table(dmps_df: pd.DataFrame) -> pd.DataFrame:
    missing = _REQUIRED_DMP_COLS - set(dmps_df.columns)
    if missing:
        raise ValueError(f"DMP CSV missing required columns: {sorted(missing)}")
    out = dmps_df.reset_index(drop=True).copy()
    out["chromosome"] = out["chromosome"].astype(str)
    out["context"] = out["context"].astype(str)
    out["position"] = out["position"].astype(np.uint32)
    return out


def _normalize_weight_array(
    raw_weights: np.ndarray,
    *,
    weight_power: float,
) -> np.ndarray:
    weights = np.asarray(raw_weights, dtype=np.float64)
    if weights.size == 0:
        return weights
    if np.any(~np.isfinite(weights)) or np.any(weights <= 0.0):
        weights = np.where(np.isfinite(weights) & (weights > 0.0), weights, 1.0)
    w_max = float(np.max(weights))
    if w_max > 1e-6:
        weights = np.clip(weights / w_max, 1e-6, 1.0)
    else:
        weights = np.full(weights.shape, 1e-6, dtype=np.float64)
    if float(weight_power) != 1.0:
        weights = np.power(weights, float(weight_power))
        weights = np.maximum(weights, 1e-6)
    return weights.astype(np.float64)


def _resolve_weights(
    dmps_df: pd.DataFrame,
    weights_column: Optional[str],
    *,
    weight_power: float,
) -> Tuple[np.ndarray, str]:
    candidates: List[str] = []
    if weights_column:
        candidates.append(str(weights_column))
    for col in _DEFAULT_WEIGHT_COLS:
        if col not in candidates:
            candidates.append(col)

    raw: Optional[np.ndarray] = None
    used_col = "uniform"
    for col in candidates:
        if col in dmps_df.columns:
            raw = dmps_df[col].astype(float).to_numpy()
            used_col = col
            break
    if raw is None:
        raw = np.ones(len(dmps_df), dtype=np.float64)
    return _normalize_weight_array(raw, weight_power=weight_power), used_col


def _resolve_class_weight_matrix(
    dmps_df: pd.DataFrame,
    class_names: List[str],
    *,
    control_label: Optional[str],
    fallback_weights: np.ndarray,
    fallback_label: str,
    weight_power: float,
) -> Tuple[np.ndarray, Dict[str, str]]:
    class_weight_rows: List[np.ndarray] = []
    used_cols: Dict[str, str] = {}
    for class_name in class_names:
        if control_label is not None and str(class_name) == str(control_label):
            class_weight_rows.append(np.asarray(fallback_weights, dtype=np.float64))
            used_cols[str(class_name)] = fallback_label
            continue
        candidates = [
            f"effect_size__{class_name}",
            f"weight__{class_name}",
            f"importance__{class_name}",
        ]
        raw: Optional[np.ndarray] = None
        used = fallback_label
        for col in candidates:
            if col in dmps_df.columns:
                raw = dmps_df[col].astype(float).to_numpy()
                used = col
                break
        if raw is None:
            raw = np.asarray(fallback_weights, dtype=np.float64)
        else:
            raw = _normalize_weight_array(raw, weight_power=weight_power)
        class_weight_rows.append(np.asarray(raw, dtype=np.float64))
        used_cols[str(class_name)] = used
    return np.stack(class_weight_rows, axis=0), used_cols


def _load_aligned_histogram_probabilities(
    dmps_df: pd.DataFrame,
    centroid_dir: Path,
    *,
    smoothing: float,
    expected_bin_edges: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray, int]:
    n_rows = len(dmps_df)
    probs_out: Optional[np.ndarray] = None
    bin_edges_ref: Optional[np.ndarray] = (
        np.asarray(expected_bin_edges, dtype=np.float64)
        if expected_bin_edges is not None
        else None
    )
    loaded_any = False
    missing_mask = np.ones(n_rows, dtype=bool)

    for (chrom, ctx), group in dmps_df.groupby(
        ["chromosome", "context"], sort=False, observed=True
    ):
        centroid_path = centroid_dir / f"{chrom}-{ctx}.h5"
        if not centroid_path.exists():
            continue

        centroid = load_from_h5(centroid_path)
        binned = getattr(centroid, "binned_stats", None) or {}
        if "bin_edges" not in binned or "bin_counts" not in binned:
            raise ValueError(
                f"Centroid {centroid_path} is missing required binned_stats for native multiclass"
            )

        bin_edges = np.asarray(binned["bin_edges"], dtype=np.float64)
        bin_counts = np.asarray(binned["bin_counts"], dtype=np.float64)
        if bin_counts.ndim != 2 or bin_counts.shape[0] != len(centroid):
            raise ValueError(
                f"Centroid {centroid_path} has invalid bin_counts shape {bin_counts.shape}"
            )

        if bin_edges_ref is None:
            bin_edges_ref = bin_edges
        if probs_out is None:
            probs_out = np.full(
                (n_rows, bin_counts.shape[1]),
                1.0 / float(bin_counts.shape[1]),
                dtype=np.float64,
            )
        if len(bin_edges_ref) != len(bin_edges) or not np.allclose(
            bin_edges_ref, bin_edges
        ):
            raise ValueError(
                "All centroid histograms must share the same bin_edges for native multiclass"
            )

        centroid_pos = np.asarray(centroid.pos.values, dtype=np.uint32)
        positions = group["position"].astype(np.uint32).to_numpy()
        indices = np.searchsorted(centroid_pos, positions)
        valid = (indices < len(centroid_pos)) & (centroid_pos[indices] == positions)
        if not np.any(valid):
            loaded_any = True
            continue

        group_idx = group.index.to_numpy()
        row_idx = group_idx[valid]
        counts = bin_counts[indices[valid]]
        counts = np.maximum(counts, 0.0)
        probs = counts + float(smoothing)
        probs /= np.maximum(np.sum(probs, axis=1, keepdims=True), 1e-12)
        assert probs_out is not None
        probs_out[row_idx] = probs
        missing_mask[row_idx] = False
        loaded_any = True

    if not loaded_any or probs_out is None or bin_edges_ref is None:
        raise ValueError(
            f"No centroid histogram files were found under {centroid_dir} for the requested DMP contexts"
        )
    return bin_edges_ref, probs_out, int(np.sum(missing_mask))


def build_multiclass_model(config: Dict[str, Any]) -> Path:
    dmps_csv = Path(config["dmps_csv"])
    output_model = Path(config["output_model"])
    classes = list(config["classes"])
    weights_column = config.get("weights_column")
    weight_power = float(config.get("weight_power", 1.0))
    temperature = float(config.get("temperature", 1.0))
    histogram_smoothing = float(config.get("histogram_smoothing", 0.5))
    control_label = config.get("control_label")
    control_name = str(control_label) if control_label is not None else None
    score_mode = str(config.get("score_mode") or "auto")

    dmps_df = _prepare_feature_table(pd.read_csv(dmps_csv))
    classifier_weights, used_weight_col = _resolve_weights(
        dmps_df, weights_column, weight_power=weight_power
    )

    class_names: List[str] = []
    bin_prob_tables: List[np.ndarray] = []
    missing_by_class: Dict[str, int] = {}
    bin_edges_ref: Optional[np.ndarray] = None

    for class_cfg in classes:
        name = str(class_cfg["name"])
        centroid_dir = Path(class_cfg["centroid_dir"])
        bin_edges_ref, probs, missing_count = _load_aligned_histogram_probabilities(
            dmps_df,
            centroid_dir,
            smoothing=histogram_smoothing,
            expected_bin_edges=bin_edges_ref,
        )
        class_names.append(name)
        bin_prob_tables.append(probs)
        missing_by_class[name] = int(missing_count)

    class_weight_matrix, class_weight_columns = _resolve_class_weight_matrix(
        dmps_df,
        class_names,
        control_label=control_name,
        fallback_weights=classifier_weights,
        fallback_label=used_weight_col,
        weight_power=weight_power,
    )

    reference_class_index: Optional[int] = None
    if control_name is not None and control_name in class_names:
        reference_class_index = class_names.index(control_name)
    class_specific_cols_present = any(
        used != used_weight_col for name, used in class_weight_columns.items() if name != control_name
    )
    if score_mode == "auto":
        score_mode = (
            "contrast_vs_control"
            if reference_class_index is not None and class_specific_cols_present
            else "generative"
        )

    assert bin_edges_ref is not None
    classifier = NativeMulticlassHistogramClassifier(
        positions=dmps_df["position"].to_numpy(dtype=np.uint32),
        bin_edges=bin_edges_ref,
        bin_probabilities=np.stack(bin_prob_tables, axis=0),
        weights=class_weight_matrix if score_mode == "contrast_vs_control" else classifier_weights,
        class_names=class_names,
        temperature=temperature,
        contrast_reference_class_index=reference_class_index if score_mode == "contrast_vs_control" else None,
        score_mode=score_mode,
    )

    feature_table = dmps_df.copy()
    feature_table["classifier_weight"] = classifier_weights.astype(np.float64)
    for class_idx, class_name in enumerate(class_names):
        feature_table[f"classifier_weight__{class_name}"] = class_weight_matrix[
            class_idx
        ].astype(np.float64)

    metadata = {
        "classifier_type": NATIVE_MULTICLASS_TYPE,
        "package_version": NATIVE_MULTICLASS_VERSION,
        "n_classes": len(class_names),
        "class_names": class_names,
        "n_dmps": len(feature_table),
        "chromosome": (
            str(feature_table["chromosome"].iloc[0])
            if feature_table["chromosome"].nunique() == 1
            else "multi"
        ),
        "context": ",".join(str(x) for x in (config.get("contexts") or [])) or "unknown",
        "weights_column_requested": weights_column,
        "weights_column_used": used_weight_col,
        "class_weight_columns": class_weight_columns,
        "weight_power": weight_power,
        "histogram_smoothing": histogram_smoothing,
        "n_bins": len(bin_edges_ref) - 1,
        "control_label": config.get("control_label"),
        "score_mode": score_mode,
        "contrast_reference_class_index": reference_class_index,
        "comparison_labels": list(config.get("comparison_labels") or []),
        "missing_positions_by_class": missing_by_class,
        "config": dict(config),
    }
    model_package = {
        "classifier_type": NATIVE_MULTICLASS_TYPE,
        "package_version": NATIVE_MULTICLASS_VERSION,
        "classifier": classifier,
        "dmp_df": feature_table,
        "metadata": metadata,
    }

    output_model.parent.mkdir(parents=True, exist_ok=True)
    with open(output_model, "wb") as f:
        pickle.dump(model_package, f, protocol=pickle.HIGHEST_PROTOCOL)
    return output_model


def build_multiclass_model_from_json(config_path: Path) -> Path:
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return build_multiclass_model(config)

