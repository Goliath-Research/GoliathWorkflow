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
from sklearn.metrics import balanced_accuracy_score

from methyl_predictor.project_resolver import resolve_predictor_config
from methyl_utils import load_project

from .model_bundle import build_model_feature_bundle, load_bundle_dmp_index
from .observed_feature_builder import (
    apply_feature_fill_values,
    build_observed_hybrid_feature_table,
    derive_observed_hybrid_anchors,
    fit_feature_fill_values,
    select_training_feature_matrix,
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


def _resolve_class_centroid_dirs(project_json: Path) -> Dict[str, str]:
    label_to_dir: Dict[str, str] = {}
    try:
        project = load_project(project_json)
        resolved = project.get_resolved_groups()
        derived = project.get_derived_paths()
        centroid_dirs = list(getattr(derived, "centroid_dirs", []) or [])
        for idx, (label, _paths) in enumerate(resolved):
            if idx < len(centroid_dirs):
                label_to_dir[str(label)] = str(centroid_dirs[idx])
    except Exception:
        return {}
    return {k: v for k, v in label_to_dir.items() if str(v).strip()}


def _sample_paths_from_predictions(
    predictions_df: pd.DataFrame,
    project_json: Path,
) -> List[str]:
    """
    Build per-row sample paths directly from predictions rows.

    This avoids train/holdout/test group-resolution ambiguity and guarantees row
    parity between ECDF probabilities and observed-hybrid features.
    """
    with open(project_json, encoding="utf-8") as f:
        project_data = json.load(f)
    samples_base = str(project_data.get("samples_base_path") or "").strip()
    samples_base_path = Path(samples_base) if samples_base else None

    resolved_eval_paths, _ = _resolve_eval_paths_and_labels(project_json)
    eval_by_name: Dict[str, str] = {Path(str(p)).name: str(p) for p in resolved_eval_paths}
    eval_by_stem: Dict[str, str] = {Path(str(p)).stem: str(p) for p in resolved_eval_paths}

    out: List[str] = []
    for row in predictions_df.itertuples(index=False):
        sample = str(getattr(row, "sample", "") or "").strip()
        sample_path = str(getattr(row, "sample_path", "") or "").strip()
        chosen: Optional[str] = None

        if sample_path:
            p = Path(sample_path)
            if p.is_absolute():
                chosen = str(p)
            elif samples_base_path is not None:
                chosen = str((samples_base_path / sample_path).resolve())
            else:
                chosen = str(p)

        if not chosen and sample:
            # Prefer exact match from predictor-resolved lineage when available.
            if sample in eval_by_name:
                chosen = eval_by_name[sample]
            elif sample in eval_by_stem:
                chosen = eval_by_stem[sample]
            elif samples_base_path is not None:
                chosen = str((samples_base_path / sample).resolve())
            else:
                chosen = sample

        if not chosen:
            raise ValueError("Encountered prediction row without sample identifier for second-stage scorer.")
        out.append(chosen)
    return out


def train_and_apply_ecdf_second_stage(
    *,
    project_json: str | Path,
    predictor_output_dir: str | Path,
    classifier_output_dir: str | Path,
    max_dmps: Optional[int] = None,
    quantiles: Optional[List[float]] = None,
    min_coverage: int = 1,
    include_dmp_features: bool = True,
    include_chromosome_features: bool = True,
    include_dmr_features: bool = True,
    include_gene_features: bool = True,
    dmr_window_bp: int = 100000,
    max_dmr_features: int = 32,
    max_gene_features: int = 32,
    hist_eps: float = 1e-6,
    hist_alpha: float = 0.5,
    hist_evidence_clip_cap: float = 5.0,
    hist_tail_agreement_threshold: float = 0.10,
    chromosome_hypo_beta_threshold: Optional[float] = None,
    chromosome_intermediate_beta_lo: Optional[float] = None,
    chromosome_intermediate_beta_hi: Optional[float] = None,
    chromosome_distance_metrics: Optional[List[str]] = None,
    chromosome_list: Optional[List[str]] = None,
    feature_family_set: str = "dmp_scored",
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
    max_dmps_norm = int(max_dmps) if (max_dmps is not None and int(max_dmps) > 0) else 0
    if max_dmps_norm and len(dmp_df) > max_dmps_norm:
        dmp_df = dmp_df.sort_values(["effect_size"], ascending=[False]).head(max_dmps_norm).copy()

    sample_paths = _sample_paths_from_predictions(df, project_json)
    if not sample_paths:
        raise ValueError("No sample paths were derived from predictions.csv for ECDF second-stage scorer.")
    y_for_anchor = pd.to_numeric(df["expected_class"], errors="coerce").fillna(0).astype(int).to_numpy()
    y_for_anchor = np.where(y_for_anchor > 0, 1, 0).astype(np.int32)
    centroid_dirs = _resolve_class_centroid_dirs(project_json)
    healthy_label = "healthy"
    cancer_labels = ["cancer"]
    if centroid_dirs:
        labels = list(centroid_dirs.keys())
        if labels:
            healthy_label = labels[0]
            if len(labels) > 1:
                cancer_labels = [labels[1]]

    anchors = derive_observed_hybrid_anchors(
        sample_paths=sample_paths,
        sample_class_indices=y_for_anchor.tolist(),
        class_names=[healthy_label] + cancer_labels,
        dmp_df=dmp_df,
        min_coverage=int(max(1, min_coverage)),
    )
    feat = build_observed_hybrid_feature_table(
        sample_paths,
        dmp_df,
        quantiles=quantiles,
        min_coverage=int(max(1, min_coverage)),
        include_dmp_features=bool(include_dmp_features),
        include_chromosome_features=bool(include_chromosome_features),
        include_dmr_features=bool(include_dmr_features),
        include_gene_features=bool(include_gene_features),
        dmr_window_bp=int(max(1, dmr_window_bp)),
        max_dmr_features=int(max(0, max_dmr_features)),
        max_gene_features=int(max(0, max_gene_features)),
        healthy_reference_vector=anchors.healthy_reference_vector,
        cancer_reference_vector=anchors.cancer_reference_vector,
        per_cancer_reference_vectors=anchors.per_cancer_reference_vectors,
        healthy_class_label=anchors.healthy_class_label,
        cancer_class_labels=anchors.cancer_class_labels,
        all_class_labels=[healthy_label] + cancer_labels,
        anchor_strategy=anchors.anchor_strategy,
        expected_feature_order_fingerprint=anchors.feature_order_fingerprint,
        centroid_dir_by_class_label=centroid_dirs,
        hist_eps=float(hist_eps),
        hist_alpha=float(hist_alpha),
        hist_evidence_clip_cap=float(hist_evidence_clip_cap),
        hist_tail_agreement_threshold=float(hist_tail_agreement_threshold),
        feature_family_set=str(feature_family_set),
        chromosome_hypo_beta_threshold=chromosome_hypo_beta_threshold,
        chromosome_intermediate_beta_lo=chromosome_intermediate_beta_lo,
        chromosome_intermediate_beta_hi=chromosome_intermediate_beta_hi,
        chromosome_distance_metrics=chromosome_distance_metrics,
        chromosome_list=chromosome_list,
    )
    X_obs_full = np.asarray(feat.X, dtype=np.float32)
    fill_values = fit_feature_fill_values(X_obs_full)
    X_obs_full = apply_feature_fill_values(X_obs_full, fill_values)
    X_obs = select_training_feature_matrix(
        X_obs_full,
        feat.feature_names,
        feat.training_feature_names,
    )

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
    refined_balanced_accuracy = float(balanced_accuracy_score(y, y_hat[valid])) if int(np.sum(valid)) > 0 else None

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
        "training_feature_names": list(feat.training_feature_names),
        "quality_feature_names": list(feat.quality_feature_names),
        "observed_feature_report": dict(feat.report),
        "observed_feature_fill_values": [float(v) for v in fill_values.tolist()],
        "observed_healthy_reference_vector": [float(v) for v in anchors.healthy_reference_vector.tolist()],
        "observed_cancer_reference_vector": [float(v) for v in anchors.cancer_reference_vector.tolist()],
        "observed_healthy_class_label": str(anchors.healthy_class_label),
        "observed_cancer_class_labels": [str(x) for x in anchors.cancer_class_labels],
        "observed_anchor_strategy": str(anchors.anchor_strategy),
        "observed_feature_order_fingerprint": str(anchors.feature_order_fingerprint),
        "max_dmps": int(max_dmps_norm),
        "quantiles": [float(q) for q in (feat.report.get("quantiles") or [])],
        "min_coverage": int(max(1, min_coverage)),
        "refined_balanced_accuracy_labeled_rows": refined_balanced_accuracy,
        "observed_feature_include_dmp": bool(include_dmp_features),
        "observed_feature_include_chromosome": bool(include_chromosome_features),
        "observed_feature_include_dmr": bool(include_dmr_features),
        "observed_feature_include_gene": bool(include_gene_features),
        "observed_feature_dmr_window_bp": int(max(1, dmr_window_bp)),
        "observed_feature_max_dmrs": int(max(0, max_dmr_features)),
        "observed_feature_max_genes": int(max(0, max_gene_features)),
        "observed_hist_eps": float(hist_eps),
        "observed_hist_alpha": float(hist_alpha),
        "observed_hist_evidence_clip_cap": float(hist_evidence_clip_cap),
        "observed_hist_tail_agreement_threshold": float(hist_tail_agreement_threshold),
    }
    verify_feature_schema(
        feat.feature_names,
        meta["observed_feature_names"],
        context="ecdf second-stage train/apply",
    )
    meta_path = classifier_output_dir / "ecdf-second-stage-metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    ablation_report = {
        "backend": "ecdf",
        "stage": "second_stage",
        "balanced_accuracy_labeled_rows": refined_balanced_accuracy,
        "active_feature_families": {
            "dmp": bool(include_dmp_features),
            "chromosome": bool(include_chromosome_features),
            "dmr": bool(include_dmr_features),
            "gene": bool(include_gene_features),
        },
        "recommended_ablation_matrix": [
            {"name": "baseline", "include_dmp": False, "include_dmr": False, "include_gene": False},
            {"name": "plus_dmp", "include_dmp": True, "include_dmr": False, "include_gene": False},
            {"name": "plus_dmr", "include_dmp": False, "include_dmr": True, "include_gene": False},
            {"name": "plus_gene", "include_dmp": False, "include_dmr": False, "include_gene": True},
            {"name": "all", "include_dmp": True, "include_dmr": True, "include_gene": True},
        ],
    }
    with open(classifier_output_dir / "feature_family_ablation.json", "w", encoding="utf-8") as f:
        json.dump(ablation_report, f, indent=2)

    return {
        "model_path": str(model_path),
        "metadata_path": str(meta_path),
        "predictions_csv": str(pred_csv),
        "n_rows": int(df.shape[0]),
    }

