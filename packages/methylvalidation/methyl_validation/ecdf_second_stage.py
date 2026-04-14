"""
Optional ECDF second-stage scorer using observed-only hybrid features.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from methyl_predictor.project_resolver import resolve_predictor_config

from .model_bundle import build_model_feature_bundle, load_bundle_dmp_index
from .observed_feature_builder import (
    apply_feature_fill_values,
    build_observed_hybrid_feature_table,
    fit_feature_fill_values,
    verify_feature_schema,
)


def _resolve_eval_paths_and_labels(project_json: str | Path) -> Tuple[List[str], Optional[np.ndarray]]:
    cfg = resolve_predictor_config(project_json)
    samples: List[str] = []
    y_true: List[int] = []

    test_group_paths = getattr(cfg, "test_group_paths", None)
    holdout_group_paths = getattr(cfg, "holdout_group_paths", None)
    train_group_paths = getattr(cfg, "train_group_paths", None)
    if test_group_paths:
        for idx, entry in enumerate(test_group_paths):
            cls_idx = int(entry.get("class_index", idx))
            for p in (entry.get("paths") or []):
                samples.append(str(p))
                y_true.append(cls_idx)
        return samples, np.asarray(y_true, dtype=np.int32)
    if holdout_group_paths:
        for idx, entry in enumerate(holdout_group_paths):
            cls_idx = int(entry.get("class_index", idx))
            for p in (entry.get("paths") or []):
                samples.append(str(p))
                y_true.append(cls_idx)
        if samples:
            return samples, np.asarray(y_true, dtype=np.int32)
    if train_group_paths:
        for idx, entry in enumerate(train_group_paths):
            cls_idx = int(entry.get("class_index", idx))
            for p in (entry.get("paths") or []):
                samples.append(str(p))
                y_true.append(cls_idx)
        if samples:
            return samples, np.asarray(y_true, dtype=np.int32)

    control = list(getattr(cfg, "test_control_paths", []) or []) + list(getattr(cfg, "holdout_control_paths", []) or [])
    disease = list(getattr(cfg, "test_disease_paths", []) or []) + list(getattr(cfg, "holdout_disease_paths", []) or [])
    if control or disease:
        samples = [str(p) for p in control + disease]
        y_true = [0] * len(control) + [1] * len(disease)
        return samples, np.asarray(y_true, dtype=np.int32)

    return [], None


def _ensure_bundle_h5(project_json: Path, bundle_dir: Path) -> Path:
    bundle_h5 = bundle_dir / "model_feature_bundle.h5"
    if bundle_h5.is_file():
        return bundle_h5
    bundle_dir.mkdir(parents=True, exist_ok=True)
    build_model_feature_bundle(
        project_json=project_json,
        output_dir=bundle_dir,
        weight_column="weight",
        extra_metadata={"model_backend": "ecdf_second_stage"},
    )
    if not bundle_h5.is_file():
        raise FileNotFoundError(f"Model bundle not found at {bundle_h5}")
    return bundle_h5


def _align_features_to_predictions(
    predictions_df: pd.DataFrame,
    sample_paths: Sequence[str],
    feature_matrix: np.ndarray,
) -> np.ndarray:
    sid_to_idx = {Path(str(p)).name: i for i, p in enumerate(sample_paths)}
    idxs: List[int] = []
    for sample_id in predictions_df["sample"].astype(str).tolist():
        if sample_id not in sid_to_idx:
            raise ValueError(f"Sample {sample_id} not found in resolved evaluation paths for second-stage scorer.")
        idxs.append(int(sid_to_idx[sample_id]))
    return feature_matrix[np.asarray(idxs, dtype=np.int32), :]


def train_and_apply_ecdf_second_stage(
    *,
    project_json: str | Path,
    predictor_output_dir: str | Path,
    classifier_output_dir: str | Path,
    max_dmps: int = 5000,
    quantiles: Optional[List[float]] = None,
    min_coverage: int = 1,
) -> Dict[str, Any]:
    project_json = Path(project_json).resolve()
    predictor_output_dir = Path(predictor_output_dir).resolve()
    classifier_output_dir = Path(classifier_output_dir).resolve()
    classifier_output_dir.mkdir(parents=True, exist_ok=True)

    pred_csv = predictor_output_dir / "predictions.csv"
    if not pred_csv.is_file():
        raise FileNotFoundError(f"Missing predictions.csv under {predictor_output_dir}")
    df = pd.read_csv(pred_csv)
    if "prob_class0" not in df.columns or "prob_class1" not in df.columns:
        raise ValueError("Second-stage scorer requires binary ECDF probabilities: prob_class0/prob_class1.")
    if "expected_class" not in df.columns:
        raise ValueError("Second-stage scorer requires expected_class column in predictions.csv.")
    if "sample" not in df.columns:
        raise ValueError("Second-stage scorer requires sample column in predictions.csv.")

    bundle_dir = project_json.parent / "model_bundle"
    bundle_h5 = _ensure_bundle_h5(project_json, bundle_dir)
    dmp_df = load_bundle_dmp_index(bundle_h5)
    if max_dmps and len(dmp_df) > max_dmps:
        dmp_df = dmp_df.sort_values(["weight", "effect_size"], ascending=[False, False]).head(max_dmps).copy()

    sample_paths, _labels = _resolve_eval_paths_and_labels(project_json)
    if not sample_paths:
        raise ValueError("Could not resolve evaluation sample paths for ECDF second-stage scorer.")
    feat = build_observed_hybrid_feature_table(
        sample_paths,
        dmp_df,
        quantiles=quantiles,
        min_coverage=int(max(1, min_coverage)),
    )
    X_obs = np.asarray(feat.X, dtype=np.float32)
    fill_values = fit_feature_fill_values(X_obs)
    X_obs = apply_feature_fill_values(X_obs, fill_values)
    X_obs = _align_features_to_predictions(df, sample_paths, X_obs)

    X_prob = df[["prob_class0", "prob_class1"]].astype(np.float32).to_numpy()
    X = np.concatenate([X_prob, X_obs], axis=1)
    y = pd.to_numeric(df["expected_class"], errors="coerce").fillna(-1).astype(int).to_numpy()
    valid = np.isin(y, [0, 1])
    if int(np.sum(valid)) < 4:
        raise ValueError("Second-stage scorer requires at least 4 valid binary labeled rows.")
    X = X[valid, :]
    y = y[valid]

    clf = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=13)
    clf.fit(X, y)
    probs = clf.predict_proba(np.concatenate([X_prob, X_obs], axis=1))
    y_hat = np.asarray(np.argmax(probs, axis=1), dtype=np.int32)

    df["prob_refined_class0"] = probs[:, 0].astype(float)
    df["prob_refined_class1"] = probs[:, 1].astype(float)
    df["prediction_refined"] = y_hat.astype(int)
    df.to_csv(pred_csv, index=False)

    model_path = classifier_output_dir / "ecdf-second-stage.joblib"
    joblib.dump(clf, model_path)
    meta = {
        "model_backend": "ecdf",
        "second_stage_type": "logistic_regression",
        "project_json": str(project_json),
        "predictor_output_dir": str(predictor_output_dir),
        "bundle_h5": str(bundle_h5),
        "n_features": int(X.shape[1]),
        "n_observed_features": int(X_obs.shape[1]),
        "observed_feature_names": list(feat.feature_names),
        "observed_feature_report": dict(feat.report),
        "observed_feature_fill_values": [float(v) for v in fill_values.tolist()],
        "max_dmps": int(max_dmps),
        "quantiles": [float(q) for q in (feat.report.get("quantiles") or [])],
        "min_coverage": int(max(1, min_coverage)),
    }
    verify_feature_schema(
        feat.feature_names,
        meta["observed_feature_names"],
        context="ecdf second-stage train/apply",
    )
    meta_path = classifier_output_dir / "ecdf-second-stage-metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return {
        "model_path": str(model_path),
        "metadata_path": str(meta_path),
        "predictions_csv": str(pred_csv),
        "n_rows": int(df.shape[0]),
    }

