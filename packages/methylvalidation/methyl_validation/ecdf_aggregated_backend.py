"""
Aggregated-feature ECDF OvR backend for methyl-validation --model.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)

from methyl_predictor.models.config import PredictorConfig
from methyl_predictor.project_resolver import resolve_predictor_config
from methyl_utils import load_project
from methyl_utils.ecdf_aggregated_ovr import (
    AGGREGATED_ECDF_OVR_TYPE,
    build_effect_size_feature_weights,
    predict_aggregated_ecdf_ovr_proba,
    train_aggregated_ecdf_ovr_package,
)

from .eval_split_resolver import resolve_eval_paths_and_labels
from .model_bundle import load_bundle_dmp_index
from .observed_feature_builder import (
    build_observed_hybrid_feature_table,
    derive_observed_hybrid_anchors,
)
from .tabular_backend import (
    _resolve_class_centroid_dirs,
    _select_healthy_index_for_labels,
)


def _load_training_samples(project_json: str | Path) -> Tuple[List[str], np.ndarray, List[str]]:
    project = load_project(project_json)
    resolved = project.get_resolved_groups()
    if len(resolved) < 2:
        raise ValueError("Aggregated ECDF requires at least two resolved training groups")
    all_paths: List[str] = []
    y: List[int] = []
    class_names: List[str] = []
    for cls, (label, paths) in enumerate(resolved):
        class_names.append(str(label))
        for p in paths:
            all_paths.append(str(p))
            y.append(int(cls))
    if not all_paths:
        raise ValueError("No training samples resolved from project")
    return all_paths, np.asarray(y, dtype=np.int32), class_names


def _compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_classes: int,
    class_names: Sequence[str],
) -> Dict[str, Any]:
    yt = np.asarray(y_true, dtype=int).reshape(-1)
    yp = np.asarray(y_pred, dtype=int).reshape(-1)
    labels = list(range(int(n_classes)))
    metrics: Dict[str, Any] = {
        "n_samples": int(len(yt)),
        "n_classes": int(n_classes),
        "accuracy": float(accuracy_score(yt, yp)) if len(yt) else 0.0,
        "balanced_accuracy": float(balanced_accuracy_score(yt, yp)) if len(yt) else 0.0,
    }
    precision, recall, f1, support = precision_recall_fscore_support(
        yt,
        yp,
        labels=labels,
        average=None,
        zero_division=0,
    )
    precision = np.asarray(precision, dtype=np.float64)
    recall = np.asarray(recall, dtype=np.float64)
    f1 = np.asarray(f1, dtype=np.float64)
    support = np.asarray(support, dtype=np.int64)
    metrics["per_class"] = {
        str(class_names[i] if i < len(class_names) else f"Class_{i}"): {
            "precision": float(precision[i]),
            "recall": float(recall[i]),
            "f1": float(f1[i]),
            "support": int(support[i]),
        }
        for i in range(len(labels))
    }
    metrics["macro_precision"] = float(np.mean(precision)) if len(precision) else 0.0
    metrics["macro_recall"] = float(np.mean(recall)) if len(recall) else 0.0
    metrics["macro_f1"] = float(np.mean(f1)) if len(f1) else 0.0
    _, _, weighted_f1, _ = precision_recall_fscore_support(
        yt,
        yp,
        labels=labels,
        average="weighted",
        zero_division=0,
    )
    metrics["weighted_f1"] = float(weighted_f1)
    cm = confusion_matrix(yt, yp, labels=labels)
    metrics["confusion_matrix"] = cm.astype(int).tolist()
    if int(n_classes) == 2 and cm.shape == (2, 2):
        tn, fp, fn, tp = [int(v) for v in cm.ravel().tolist()]
        metrics["specificity"] = float(tn / max(1, tn + fp))
        metrics["sensitivity"] = float(tp / max(1, tp + fn))
        metrics["precision_binary"] = float(tp / max(1, tp + fp))
        metrics["recall_binary"] = metrics["sensitivity"]
        metrics["f1_binary"] = float(2 * tp / max(1, (2 * tp) + fp + fn))
    return metrics


def train_ecdf_aggregated_ovr_model(
    *,
    project_json: str | Path,
    bundle_h5: str | Path,
    output_dir: str | Path,
    feature_family_set: str = "gene",
    observed_feature_min_coverage: int = 1,
    observed_hist_eps: float = 1e-6,
    observed_hist_alpha: float = 0.5,
    observed_hist_evidence_clip_cap: float = 5.0,
    observed_hist_tail_agreement_threshold: float = 0.10,
    n_bins: int = 100,
    temperature: float = 2.0,
) -> Path:
    project = load_project(project_json)
    all_paths, y, class_names = _load_training_samples(project_json)
    dmp_df = load_bundle_dmp_index(bundle_h5)
    class_centroid_dirs = _resolve_class_centroid_dirs(project, class_names)

    anchors = derive_observed_hybrid_anchors(
        all_paths,
        y.tolist(),
        class_names,
        dmp_df,
        min_coverage=int(max(1, observed_feature_min_coverage)),
    )
    feat = build_observed_hybrid_feature_table(
        all_paths,
        dmp_df,
        min_coverage=int(max(1, observed_feature_min_coverage)),
        healthy_reference_vector=anchors.healthy_reference_vector.tolist(),
        cancer_reference_vector=anchors.cancer_reference_vector.tolist(),
        per_cancer_reference_vectors=[v.tolist() for v in anchors.per_cancer_reference_vectors],
        healthy_class_label=anchors.healthy_class_label,
        cancer_class_labels=anchors.cancer_class_labels,
        anchor_strategy=anchors.anchor_strategy,
        expected_feature_order_fingerprint=anchors.feature_order_fingerprint,
        centroid_dir_by_class_label=class_centroid_dirs,
        hist_eps=float(observed_hist_eps),
        hist_alpha=float(observed_hist_alpha),
        hist_evidence_clip_cap=float(observed_hist_evidence_clip_cap),
        hist_tail_agreement_threshold=float(observed_hist_tail_agreement_threshold),
        feature_family_set=str(feature_family_set),
    )
    X = np.asarray(feat.X, dtype=np.float64)
    feature_names = list(feat.feature_names)
    feature_weights = build_effect_size_feature_weights(dmp_df, feature_names)
    package = train_aggregated_ecdf_ovr_package(
        X,
        y,
        class_names=class_names,
        feature_names=feature_names,
        feature_weights=feature_weights,
        feature_family_set=str(feature_family_set),
        feature_mode="observed_hybrid",
        n_bins=int(max(8, n_bins)),
        temperature=float(temperature),
        package_metadata={
            "backend": "ecdf",
            "model_backend": "ecdf",
            "training_project_json": str(Path(project_json).resolve()),
            "package_notes": "Aggregated observed-hybrid ECDF OvR",
        },
    )
    package["observed_hybrid"] = {
        "dmp_df": dmp_df,
        "healthy_reference_vector": anchors.healthy_reference_vector.astype(np.float64),
        "cancer_reference_vector": anchors.cancer_reference_vector.astype(np.float64),
        "per_cancer_reference_vectors": [
            np.asarray(v, dtype=np.float64) for v in anchors.per_cancer_reference_vectors
        ],
        "healthy_class_label": str(anchors.healthy_class_label),
        "cancer_class_labels": [str(x) for x in anchors.cancer_class_labels],
        "anchor_strategy": str(anchors.anchor_strategy),
        "feature_order_fingerprint": str(anchors.feature_order_fingerprint),
        "feature_family_set": str(feature_family_set),
        "min_coverage": int(max(1, observed_feature_min_coverage)),
        "hist_eps": float(observed_hist_eps),
        "hist_alpha": float(observed_hist_alpha),
        "hist_evidence_clip_cap": float(observed_hist_evidence_clip_cap),
        "hist_tail_agreement_threshold": float(observed_hist_tail_agreement_threshold),
        "class_centroid_dirs": {str(k): str(v) for k, v in class_centroid_dirs.items()},
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "ecdf_aggregated_ovr.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(package, f, protocol=pickle.HIGHEST_PROTOCOL)
    with open(out_dir / "ecdf_aggregated_ovr.meta.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "classifier_type": AGGREGATED_ECDF_OVR_TYPE,
                "class_names": [str(x) for x in class_names],
                "n_features": int(len(feature_names)),
                "feature_family_set": str(feature_family_set),
            },
            f,
            indent=2,
        )
    return model_path


def _build_predictor_eval_paths(
    project_json: str | Path,
    class_names: List[str],
) -> Tuple[List[str], Optional[np.ndarray]]:
    predictor_cfg = resolve_predictor_config(project_json)
    eval_paths, eval_y = resolve_eval_paths_and_labels(
        project_json,
        class_names,
        predictor_cfg=predictor_cfg,
        project_loader=load_project,
    )
    if eval_y is None:
        return eval_paths, None
    return eval_paths, np.asarray(eval_y, dtype=np.int32)


def predict_ecdf_aggregated_ovr_from_project(
    *,
    project_json: str | Path,
    model_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    with open(model_path, "rb") as f:
        package = pickle.load(f)
    if not isinstance(package, dict) or package.get("classifier_type") != AGGREGATED_ECDF_OVR_TYPE:
        raise ValueError(f"Model file is not {AGGREGATED_ECDF_OVR_TYPE}: {model_path}")

    class_names = [str(x) for x in (package.get("class_names") or [])]
    if len(class_names) < 2:
        raise ValueError("Aggregated ECDF package missing class names")
    obs = package.get("observed_hybrid") or {}
    dmp_df = obs.get("dmp_df")
    if dmp_df is None or not hasattr(dmp_df, "columns"):
        raise ValueError("Aggregated ECDF package missing observed_hybrid.dmp_df")

    eval_paths, eval_y = _build_predictor_eval_paths(project_json, class_names)
    if not eval_paths:
        raise ValueError("No evaluation paths resolved for aggregated ECDF predictor")

    feat = build_observed_hybrid_feature_table(
        eval_paths,
        dmp_df,
        min_coverage=int(obs.get("min_coverage", 1)),
        healthy_reference_vector=np.asarray(obs.get("healthy_reference_vector"), dtype=np.float64).tolist(),
        cancer_reference_vector=np.asarray(obs.get("cancer_reference_vector"), dtype=np.float64).tolist(),
        per_cancer_reference_vectors=[
            np.asarray(v, dtype=np.float64).tolist()
            for v in (obs.get("per_cancer_reference_vectors") or [])
        ],
        healthy_class_label=str(obs.get("healthy_class_label") or class_names[_select_healthy_index_for_labels(class_names)]),
        cancer_class_labels=[str(x) for x in (obs.get("cancer_class_labels") or class_names[1:])],
        anchor_strategy=str(obs.get("anchor_strategy") or "class_centroid"),
        expected_feature_order_fingerprint=str(obs.get("feature_order_fingerprint") or ""),
        centroid_dir_by_class_label={str(k): str(v) for k, v in (obs.get("class_centroid_dirs") or {}).items()},
        hist_eps=float(obs.get("hist_eps", 1e-6)),
        hist_alpha=float(obs.get("hist_alpha", 0.5)),
        hist_evidence_clip_cap=float(obs.get("hist_evidence_clip_cap", 5.0)),
        hist_tail_agreement_threshold=float(obs.get("hist_tail_agreement_threshold", 0.10)),
        feature_family_set=str(obs.get("feature_family_set") or "gene"),
    )
    schema_names = [str(x) for x in ((package.get("feature_schema") or {}).get("feature_names") or [])]
    if list(feat.feature_names) != schema_names:
        raise ValueError("Aggregated ECDF feature schema mismatch between training and prediction")

    probs, evidence = predict_aggregated_ecdf_ovr_proba(
        package,
        np.asarray(feat.X, dtype=np.float64),
    )
    pred = np.argmax(probs, axis=1).astype(int)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_csv = out_dir / "predictions.csv"
    df = pd.DataFrame(
        {
            "sample": [str(p) for p in eval_paths],
            "prediction": pred.astype(int),
            "prediction_label": [class_names[int(i)] for i in pred.tolist()],
        }
    )
    for j in range(probs.shape[1]):
        df[f"prob_class{j}"] = probs[:, j]
        df[f"evidence_class{j}"] = evidence[:, j]
    if eval_y is not None and len(eval_y) == len(df):
        df["expected_class"] = eval_y.astype(int)
    df.to_csv(pred_csv, index=False)

    metrics: Dict[str, Any] = {
        "classifier_type": AGGREGATED_ECDF_OVR_TYPE,
        "n_samples": int(len(df)),
        "n_classes": int(len(class_names)),
        "class_names": [str(x) for x in class_names],
        "probability_semantics": {
            "posterior_source": "aggregated_ecdf_ovr_softmax",
            "evidence_columns": [f"evidence_class{i}" for i in range(len(class_names))],
            "note": "evidence_class* are pre-softmax OvR log-evidence diagnostics, not p-values.",
        },
    }
    if "expected_class" in df.columns:
        y_true = df["expected_class"].to_numpy(dtype=int)
        y_pred = df["prediction"].to_numpy(dtype=int)
        scored = _compute_metrics(y_true, y_pred, len(class_names), class_names)
        metrics.update(scored)

    metrics_path = out_dir / "validation_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    report_path = out_dir / "prediction_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "model_type": AGGREGATED_ECDF_OVR_TYPE,
                "predictions_csv": str(pred_csv),
                "validation_metrics": str(metrics_path),
                "n_samples": int(len(df)),
                "n_classes": int(len(class_names)),
            },
            f,
            indent=2,
        )
    return metrics
