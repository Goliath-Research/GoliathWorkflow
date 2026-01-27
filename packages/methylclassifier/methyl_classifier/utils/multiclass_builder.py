"""
Build a multi-class Beta/BMM classifier model package.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import pickle
import numpy as np
import pandas as pd

from methyl_utils import load_from_h5, MultiClassBetaMixtureClassifier
from methyl_utils.core.methyl_mixture_centroid import MethylBetaMixtureCentroid


def _resolve_weights(dmps_df: pd.DataFrame, weights_column: Optional[str]) -> np.ndarray:
    if weights_column and weights_column in dmps_df.columns:
        return dmps_df[weights_column].astype(float).to_numpy()
    for col in ["importance", "effect_size", "weight"]:
        if col in dmps_df.columns:
            return dmps_df[col].astype(float).to_numpy()
    return np.ones(len(dmps_df), dtype=np.float64)


def _load_centroid_params(centroid_path: Path) -> Dict[str, np.ndarray]:
    centroid = load_from_h5(centroid_path)
    pos = np.asarray(centroid.pos, dtype=np.uint32)
    alpha = np.asarray(centroid.alpha.values, dtype=np.float64)
    beta = np.asarray(centroid.beta.values, dtype=np.float64)
    return {"pos": pos, "alpha": alpha, "beta": beta}


def _fill_class_params(
    dmps_df: pd.DataFrame,
    centroid_dir: Path,
) -> Dict[str, np.ndarray]:
    n = len(dmps_df)
    alpha_out = np.full(n, np.nan, dtype=np.float64)
    beta_out = np.full(n, np.nan, dtype=np.float64)

    for (chrom, ctx), group in dmps_df.groupby(["chromosome", "context"]):
        centroid_path = centroid_dir / f"{chrom}-{ctx}.h5"
        if not centroid_path.exists():
            continue

        params = _load_centroid_params(centroid_path)
        centroid_pos = params["pos"]

        positions = group["position"].astype(np.uint32).to_numpy()
        indices = np.searchsorted(centroid_pos, positions)
        valid = (indices < len(centroid_pos)) & (centroid_pos[indices] == positions)
        if not np.any(valid):
            continue

        group_idx = group.index.to_numpy()
        alpha_out[group_idx[valid]] = params["alpha"][indices[valid]]
        beta_out[group_idx[valid]] = params["beta"][indices[valid]]

    return {"alpha": alpha_out, "beta": beta_out}


def _load_bmm_records(bmm_dir: Path, chrom: str, ctx: str, group: str) -> Optional[pd.DataFrame]:
    suffix = "" if group == "centroid1" else f"-{group}"
    path = bmm_dir / f"bmm-centroid-{chrom}-{ctx}{suffix}.json"
    if not path.exists():
        return None
    centroid = MethylBetaMixtureCentroid.from_json(path)
    return centroid.df


def _fill_class_mixtures(
    dmps_df: pd.DataFrame,
    bmm_dir: Optional[Path],
    bmm_group: str,
) -> Dict[str, List[Optional[List[float]]]]:
    n = len(dmps_df)
    mix_weights: List[Optional[List[float]]] = [None] * n
    mix_alphas: List[Optional[List[float]]] = [None] * n
    mix_betas: List[Optional[List[float]]] = [None] * n

    if bmm_dir is None:
        return {
            "mix_weights": mix_weights,
            "mix_alphas": mix_alphas,
            "mix_betas": mix_betas,
        }

    for (chrom, ctx), group in dmps_df.groupby(["chromosome", "context"]):
        df = _load_bmm_records(bmm_dir, chrom, ctx, bmm_group)
        if df is None or df.empty:
            continue

        record_map = {}
        for _, row in df.iterrows():
            if row.get("status") != "fit":
                continue
            record_map[int(row["position"])] = row

        for idx, row in group.iterrows():
            rec = record_map.get(int(row["position"]))
            if rec is None:
                continue
            mix_weights[idx] = rec.get("weights")
            mix_alphas[idx] = rec.get("alphas")
            mix_betas[idx] = rec.get("betas")

    return {
        "mix_weights": mix_weights,
        "mix_alphas": mix_alphas,
        "mix_betas": mix_betas,
    }


def build_multiclass_model(config: Dict[str, Any]) -> Path:
    dmps_csv = Path(config["dmps_csv"])
    output_model = Path(config["output_model"])
    classes = config["classes"]
    weights_column = config.get("weights_column")

    dmps_df = pd.read_csv(dmps_csv)
    required_cols = {"chromosome", "context", "position"}
    if not required_cols.issubset(dmps_df.columns):
        missing = required_cols - set(dmps_df.columns)
        raise ValueError(f"DMP CSV missing required columns: {missing}")

    dmps_df = dmps_df.reset_index(drop=True)
    dmps_df["chromosome"] = dmps_df["chromosome"].astype(str)
    dmps_df["context"] = dmps_df["context"].astype(str)
    dmps_df["position"] = dmps_df["position"].astype(np.uint32)

    weights = _resolve_weights(dmps_df, weights_column)

    class_names: List[str] = []
    alpha_list: List[np.ndarray] = []
    beta_list: List[np.ndarray] = []
    mix_weights_list: List[List[Optional[List[float]]]] = []
    mix_alphas_list: List[List[Optional[List[float]]]] = []
    mix_betas_list: List[List[Optional[List[float]]]] = []

    for class_cfg in classes:
        name = class_cfg["name"]
        centroid_dir = Path(class_cfg["centroid_dir"])
        bmm_dir = Path(class_cfg["bmm_centroid_dir"]) if class_cfg.get("bmm_centroid_dir") else None
        bmm_group = class_cfg.get("bmm_group", "centroid1")

        params = _fill_class_params(dmps_df, centroid_dir)
        alpha_list.append(params["alpha"])
        beta_list.append(params["beta"])

        mix = _fill_class_mixtures(dmps_df, bmm_dir, bmm_group)
        mix_weights_list.append(mix["mix_weights"])
        mix_alphas_list.append(mix["mix_alphas"])
        mix_betas_list.append(mix["mix_betas"])

        class_names.append(name)

    alpha = np.stack(alpha_list, axis=0)
    beta = np.stack(beta_list, axis=0)

    data = {
        "positions": dmps_df["position"].to_numpy(dtype=np.uint32),
        "weights": weights.astype(np.float64),
        "alpha": alpha,
        "beta": beta,
        "class_names": class_names,
        "mix_weights": mix_weights_list,
        "mix_alphas": mix_alphas_list,
        "mix_betas": mix_betas_list,
    }

    classifier = MultiClassBetaMixtureClassifier(
        data,
        min_sample_coverage=config.get("min_sample_coverage", 10),
        coverage_weighting=config.get("coverage_weighting", True),
    )

    model_package = {
        "classifier": classifier,
        "dmp_df": dmps_df,
        "metadata": {
            "classifier_type": "MultiClassBetaMixtureClassifier",
            "n_classes": len(class_names),
            "class_names": class_names,
            "n_dmps": len(dmps_df),
            "weights_column": weights_column,
            "config": config,
        },
    }

    output_model.parent.mkdir(parents=True, exist_ok=True)
    with open(output_model, "wb") as f:
        pickle.dump(model_package, f)

    return output_model


def build_multiclass_model_from_json(config_path: Path) -> Path:
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return build_multiclass_model(config)

