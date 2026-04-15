"""
Tabular sklearn backend for methyl-validation --model.

Builds features from bundle-selected DMP loci and optional covariates, then trains
and evaluates a multiclass classifier.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)

from methyl_predictor.project_resolver import resolve_predictor_config
from methyl_utils import load_project
from methyl_utils.methyl_centroid_pair import MethylCentroidPair

from .covariate_preprocessor import CovariatePreprocessor, fit_covariates, transform_covariates
from .model_bundle import load_bundle_dmp_index
from .observed_feature_builder import (
    apply_feature_fill_values,
    build_observed_hybrid_feature_table,
    fit_feature_fill_values,
    sample_ids_from_paths,
    verify_feature_schema,
)


@contextmanager
def _project_cwd(project_json: str | Path):
    pj = Path(project_json).resolve()
    prev = Path.cwd()
    try:
        os.chdir(pj.parent)
        yield
    finally:
        os.chdir(prev)


def _build_reference_map(
    dmp_df: pd.DataFrame,
) -> Tuple[Dict[str, Dict[str, np.ndarray]], List[Tuple[str, str, int]]]:
    refs: Dict[str, Dict[str, np.ndarray]] = {}
    order: List[Tuple[str, str, int]] = []
    for chrom, cdf in dmp_df.groupby("chromosome", sort=True):
        refs[str(chrom)] = {}
        for ctx, xdf in cdf.groupby("context", sort=False):
            poss = np.asarray(sorted(set(int(v) for v in xdf["position"].tolist())), dtype=np.uint32)
            refs[str(chrom)][str(ctx)] = poss
        for _, row in cdf.iterrows():
            order.append((str(row["chromosome"]), str(row["context"]), int(row["position"])))
    return refs, order


def _extract_matrix_for_samples(
    sample_paths: Sequence[str],
    refs: Dict[str, Dict[str, np.ndarray]],
    feature_order: List[Tuple[str, str, int]],
    min_coverage: int = 1,
) -> np.ndarray:
    n_samples = len(sample_paths)
    if n_samples == 0:
        return np.zeros((0, len(feature_order)), dtype=np.float32)

    blocks: List[np.ndarray] = []
    for chrom in sorted(refs.keys(), key=lambda x: (len(str(x)), str(x))):
        X, all_positions, all_contexts, _idx = MethylCentroidPair.extract_methylation_fractions(
            list(sample_paths),
            refs[chrom],
            chromosome=chrom,
            min_coverage=min_coverage,
        )
        col_map: Dict[Tuple[str, str, int], int] = {}
        for j in range(len(all_positions)):
            col_map[(str(chrom), str(all_contexts[j]), int(all_positions[j]))] = int(j)
        wanted_cols = [col_map[(chrom, ctx, pos)] for (c, ctx, pos) in feature_order if c == chrom]
        if wanted_cols:
            blocks.append(X[:, wanted_cols])
    if not blocks:
        return np.full((n_samples, len(feature_order)), np.nan, dtype=np.float32)
    X_all = np.concatenate(blocks, axis=1)
    return X_all


def _build_estimator(model_type: str, random_state: int = 13):
    mt = str(model_type or "random_forest").strip().lower()
    if mt == "hist_gradient_boosting":
        return HistGradientBoostingClassifier(random_state=random_state)
    if mt == "logistic_regression":
        return LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
            random_state=random_state,
        )
    return RandomForestClassifier(
        n_estimators=300,
        min_samples_leaf=2,
        n_jobs=-1,
        class_weight="balanced_subsample",
        random_state=random_state,
    )


def _compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, class_names: List[str]) -> Dict[str, Any]:
    n_classes = len(class_names)
    labels = list(range(n_classes))
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    specificity_per_class: List[float] = []
    for i in range(n_classes):
        tp = float(cm[i, i])
        fp = float(cm[:, i].sum() - tp)
        fn = float(cm[i, :].sum() - tp)
        tn = float(cm.sum() - tp - fp - fn)
        denom = tn + fp
        specificity_per_class.append(float(tn / denom) if denom > 0 else 0.0)
    macro_precision = float(np.mean(precision)) if len(precision) > 0 else 0.0
    macro_recall = float(np.mean(recall)) if len(recall) > 0 else 0.0
    sensitivity = float(recall[1]) if n_classes == 2 and len(recall) > 1 else macro_recall
    specificity = (
        float(specificity_per_class[1])
        if n_classes == 2 and len(specificity_per_class) > 1
        else float(np.mean(specificity_per_class) if specificity_per_class else 0.0)
    )
    precision_binary = float(precision[1]) if n_classes == 2 and len(precision) > 1 else macro_precision
    recall_binary = float(recall[1]) if n_classes == 2 and len(recall) > 1 else macro_recall
    f1_binary = float(f1[1]) if n_classes == 2 and len(f1) > 1 else float(np.mean(f1) if len(f1) > 0 else 0.0)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "confusion_matrix": cm.tolist(),
        "n_samples": int(len(y_true)),
        "n_classes": int(n_classes),
        "class_names": class_names,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "precision_binary": precision_binary,
        "recall_binary": recall_binary,
        "f1_binary": f1_binary,
        "macro_f1": float(np.mean(f1)),
        "weighted_f1": float(np.average(f1, weights=support) if support.sum() > 0 else 0.0),
    }


def _resolve_eval_paths_and_labels(project_json: str | Path, class_names: List[str]) -> Tuple[List[str], np.ndarray]:
    predictor_cfg = resolve_predictor_config(project_json)
    samples: List[str] = []
    y_true: List[int] = []
    test_group_paths = getattr(predictor_cfg, "test_group_paths", None)
    holdout_group_paths = getattr(predictor_cfg, "holdout_group_paths", None)
    train_group_paths = getattr(predictor_cfg, "train_group_paths", None)
    test_control_paths = list(getattr(predictor_cfg, "test_control_paths", []) or [])
    test_disease_paths = list(getattr(predictor_cfg, "test_disease_paths", []) or [])
    holdout_control_paths = list(getattr(predictor_cfg, "holdout_control_paths", []) or [])
    holdout_disease_paths = list(getattr(predictor_cfg, "holdout_disease_paths", []) or [])
    train_control_paths = list(getattr(predictor_cfg, "train_control_paths", []) or [])
    train_disease_paths = list(getattr(predictor_cfg, "train_disease_paths", []) or [])

    if test_group_paths:
        for idx, entry in enumerate(test_group_paths):
            cls_idx = int(entry.get("class_index", idx))
            paths = [str(p) for p in (entry.get("paths") or [])]
            for p in paths:
                samples.append(p)
                y_true.append(cls_idx)
        return samples, np.asarray(y_true, dtype=np.int32)

    if holdout_group_paths:
        for idx, entry in enumerate(holdout_group_paths):
            cls_idx = int(entry.get("class_index", idx))
            paths = [str(p) for p in (entry.get("paths") or [])]
            for p in paths:
                samples.append(p)
                y_true.append(cls_idx)
        if samples:
            return samples, np.asarray(y_true, dtype=np.int32)

    if train_group_paths:
        for idx, entry in enumerate(train_group_paths):
            cls_idx = int(entry.get("class_index", idx))
            paths = [str(p) for p in (entry.get("paths") or [])]
            for p in paths:
                samples.append(p)
                y_true.append(cls_idx)
        if samples:
            return samples, np.asarray(y_true, dtype=np.int32)

    if (holdout_control_paths or holdout_disease_paths) and len(class_names) <= 2:
        samples = holdout_control_paths + holdout_disease_paths
        y_true = [0] * len(holdout_control_paths) + [1] * len(holdout_disease_paths)
        return samples, np.asarray(y_true, dtype=np.int32)

    if (train_control_paths or train_disease_paths) and len(class_names) <= 2:
        samples = train_control_paths + train_disease_paths
        y_true = [0] * len(train_control_paths) + [1] * len(train_disease_paths)
        return samples, np.asarray(y_true, dtype=np.int32)

    if (test_control_paths or test_disease_paths) and len(class_names) <= 2:
        samples = test_control_paths + test_disease_paths
        y_true = [0] * len(test_control_paths) + [1] * len(test_disease_paths)
        return samples, np.asarray(y_true, dtype=np.int32)

    with _project_cwd(project_json):
        project = load_project(project_json)
    for cls_idx, (label, paths) in enumerate(project.get_resolved_groups()):
        if cls_idx >= len(class_names):
            continue
        for p in paths:
            samples.append(str(p))
            y_true.append(cls_idx)
    return samples, np.asarray(y_true, dtype=np.int32)


def train_tabular_model(
    project_json: str | Path,
    bundle_h5: str | Path,
    output_dir: str | Path,
    *,
    model_type: str = "random_forest",
    max_dmps: int = 5000,
    covariates_path: Optional[str] = None,
    covariate_id_column: str = "sample_id",
    covariates_strict_join: bool = False,
    covariate_numeric_columns: Optional[List[str]] = None,
    covariate_ordinal_columns: Optional[List[str]] = None,
    covariate_ordinal_maps: Optional[Dict[str, Dict[str, float]]] = None,
    covariate_ordinal_unknown_value: float = 0.0,
    covariate_categorical_columns: Optional[List[str]] = None,
    covariate_missing_numeric_strategy: str = "mean",
    covariate_standardize_numeric: bool = True,
    feature_mode: str = "raw_dmp",
    observed_feature_quantiles: Optional[List[float]] = None,
    observed_feature_min_coverage: int = 1,
    observed_feature_min_obs_fraction: float = 0.0,
    observed_feature_include_dmp: bool = True,
    observed_feature_include_chromosome: bool = True,
    observed_feature_include_dmr: bool = True,
    observed_feature_include_gene: bool = True,
    observed_feature_dmr_window_bp: int = 100000,
    observed_feature_max_dmrs: int = 32,
    observed_feature_max_genes: int = 32,
) -> Path:
    with _project_cwd(project_json):
        project = load_project(project_json)
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    dmp_df = load_bundle_dmp_index(bundle_h5)
    if max_dmps and len(dmp_df) > max_dmps:
        dmp_df = dmp_df.sort_values(["weight", "effect_size"], ascending=[False, False]).head(max_dmps).copy()
    refs, feature_order = _build_reference_map(dmp_df)

    resolved = project.get_resolved_groups()
    class_names = [str(lbl) for lbl, _ in resolved]
    all_paths: List[str] = []
    y: List[int] = []
    sample_ids: List[str] = []
    for cls_idx, (_label, paths) in enumerate(resolved):
        for p in paths:
            all_paths.append(str(p))
            y.append(cls_idx)
            sample_ids.append(Path(str(p)).name)

    feature_mode_norm = str(feature_mode or "raw_dmp").strip().lower()
    if feature_mode_norm == "observed_hybrid":
        feat = build_observed_hybrid_feature_table(
            all_paths,
            dmp_df,
            quantiles=observed_feature_quantiles,
            min_coverage=int(max(1, observed_feature_min_coverage)),
            include_dmp_features=bool(observed_feature_include_dmp),
            include_chromosome_features=bool(observed_feature_include_chromosome),
            include_dmr_features=bool(observed_feature_include_dmr),
            include_gene_features=bool(observed_feature_include_gene),
            dmr_window_bp=int(max(1, observed_feature_dmr_window_bp)),
            max_dmr_features=int(max(0, observed_feature_max_dmrs)),
            max_gene_features=int(max(0, observed_feature_max_genes)),
        )
        X = np.asarray(feat.X, dtype=np.float32)
        feature_fill_values = fit_feature_fill_values(X)
        X = apply_feature_fill_values(X, feature_fill_values)
        observed_feature_names = list(feat.feature_names)
        observed_feature_report = dict(feat.report)
        observed_feature_quantiles_out = [float(q) for q in (feat.report.get("quantiles") or [])]
    else:
        X = _extract_matrix_for_samples(all_paths, refs, feature_order, min_coverage=1)
        X = np.asarray(X, dtype=np.float32)
        X = np.nan_to_num(X, nan=0.5, posinf=0.5, neginf=0.5)
        feature_fill_values = None
        observed_feature_names = []
        observed_feature_report = {}
        observed_feature_quantiles_out = [float(q) for q in (observed_feature_quantiles or [])]

    cov, preprocessor, cov_report = fit_covariates(
        covariates_path,
        sample_ids,
        covariate_id_column=covariate_id_column,
        strict_join=covariates_strict_join,
        numeric_columns=covariate_numeric_columns,
        ordinal_columns=covariate_ordinal_columns,
        ordinal_maps=covariate_ordinal_maps,
        ordinal_unknown_value=covariate_ordinal_unknown_value,
        categorical_columns=covariate_categorical_columns,
        missing_numeric_strategy=covariate_missing_numeric_strategy,
        standardize_numeric=covariate_standardize_numeric,
    )
    if cov is not None:
        X = np.concatenate([X, cov], axis=1)

    y_arr = np.asarray(y, dtype=np.int32)
    estimator = _build_estimator(model_type=model_type)
    estimator.fit(X, y_arr)

    model_path = out_dir / "tabular-model.joblib"
    joblib.dump(estimator, model_path)

    preprocessor_path = out_dir / "covariate-preprocessor.json"
    if preprocessor is not None:
        preprocessor.save_json(preprocessor_path)

    meta = {
        "model_backend": "tabular_sklearn",
        "model_type": model_type,
        "feature_mode": feature_mode_norm,
        "class_names": class_names,
        "project_json": str(Path(project_json).resolve()),
        "bundle_h5": str(Path(bundle_h5).resolve()),
        "max_dmps": int(max_dmps),
        "n_features": int(X.shape[1]),
        "n_dmps": int(len(feature_order)),
        "feature_order": [{"chromosome": c, "context": ctx, "position": int(pos)} for c, ctx, pos in feature_order],
        "observed_feature_names": observed_feature_names,
        "observed_feature_quantiles": observed_feature_quantiles_out,
        "observed_feature_min_coverage": int(max(1, observed_feature_min_coverage)),
        "observed_feature_min_obs_fraction": float(max(0.0, min(1.0, observed_feature_min_obs_fraction))),
        "observed_feature_include_dmp": bool(observed_feature_include_dmp),
        "observed_feature_include_chromosome": bool(observed_feature_include_chromosome),
        "observed_feature_include_dmr": bool(observed_feature_include_dmr),
        "observed_feature_include_gene": bool(observed_feature_include_gene),
        "observed_feature_dmr_window_bp": int(max(1, observed_feature_dmr_window_bp)),
        "observed_feature_max_dmrs": int(max(0, observed_feature_max_dmrs)),
        "observed_feature_max_genes": int(max(0, observed_feature_max_genes)),
        "observed_feature_fill_values": (
            [float(v) for v in feature_fill_values.tolist()] if feature_fill_values is not None else None
        ),
        "observed_feature_report": observed_feature_report,
        "covariates_path": str(covariates_path) if covariates_path else None,
        "covariate_id_column": covariate_id_column,
        "covariates_strict_join": bool(covariates_strict_join),
        "covariate_numeric_columns": [str(x) for x in (covariate_numeric_columns or [])],
        "covariate_ordinal_columns": [str(x) for x in (covariate_ordinal_columns or [])],
        "covariate_ordinal_maps": covariate_ordinal_maps or {},
        "covariate_ordinal_unknown_value": float(covariate_ordinal_unknown_value),
        "covariate_categorical_columns": [str(x) for x in (covariate_categorical_columns or [])],
        "covariate_missing_numeric_strategy": str(covariate_missing_numeric_strategy),
        "covariate_standardize_numeric": bool(covariate_standardize_numeric),
        "covariate_preprocessor_path": str(preprocessor_path) if preprocessor is not None else None,
        "covariate_preprocessing": cov_report,
    }
    with open(out_dir / "tabular-model-metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return model_path


def predict_tabular_model_from_project(
    project_json: str | Path,
    model_dir: str | Path,
    output_dir: str | Path,
    *,
    covariates_path: Optional[str] = None,
    covariate_id_column: str = "sample_id",
    covariates_strict_join: bool = False,
    observed_feature_min_obs_fraction: Optional[float] = None,
) -> Dict[str, Any]:
    model_dir = Path(model_dir).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / "tabular-model.joblib"
    meta_path = model_dir / "tabular-model-metadata.json"
    if not model_path.is_file() or not meta_path.is_file():
        raise FileNotFoundError(f"Tabular model artifacts not found under {model_dir}")

    estimator = joblib.load(model_path)
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    class_names = [str(x) for x in meta.get("class_names", [])]
    feature_mode = str(meta.get("feature_mode", "raw_dmp")).strip().lower()

    samples, y_true = _resolve_eval_paths_and_labels(project_json, class_names)
    sample_ids = sample_ids_from_paths(samples)

    obs_fraction_vec: Optional[np.ndarray] = None
    if feature_mode == "observed_hybrid":
        bundle_h5 = meta.get("bundle_h5")
        if not isinstance(bundle_h5, str) or not Path(bundle_h5).is_file():
            raise FileNotFoundError("Observed-hybrid mode requires bundle_h5 in tabular metadata.")
        dmp_df = load_bundle_dmp_index(bundle_h5)
        max_dmps = int(meta.get("max_dmps", len(dmp_df) or 0))
        if max_dmps and len(dmp_df) > max_dmps:
            dmp_df = dmp_df.sort_values(["weight", "effect_size"], ascending=[False, False]).head(max_dmps).copy()
        feat = build_observed_hybrid_feature_table(
            samples,
            dmp_df,
            quantiles=meta.get("observed_feature_quantiles") or None,
            min_coverage=int(meta.get("observed_feature_min_coverage") or 1),
            include_dmp_features=bool(meta.get("observed_feature_include_dmp", True)),
            include_chromosome_features=bool(meta.get("observed_feature_include_chromosome", True)),
            include_dmr_features=bool(meta.get("observed_feature_include_dmr", True)),
            include_gene_features=bool(meta.get("observed_feature_include_gene", True)),
            dmr_window_bp=int(meta.get("observed_feature_dmr_window_bp", 100000)),
            max_dmr_features=int(meta.get("observed_feature_max_dmrs", 32)),
            max_gene_features=int(meta.get("observed_feature_max_genes", 32)),
        )
        verify_feature_schema(
            feat.feature_names,
            meta.get("observed_feature_names") or [],
            context="tabular predict observed_hybrid",
        )
        X = np.asarray(feat.X, dtype=np.float32)
        if "obs_fraction" in feat.feature_names:
            obs_fraction_vec = X[:, feat.feature_names.index("obs_fraction")].astype(np.float32)
        fill_values = meta.get("observed_feature_fill_values")
        if not isinstance(fill_values, list):
            raise ValueError("Observed-hybrid mode requires observed_feature_fill_values in metadata.")
        X = apply_feature_fill_values(X, fill_values)
    else:
        feature_order = [
            (str(r["chromosome"]), str(r["context"]), int(r["position"]))
            for r in meta.get("feature_order", [])
        ]
        refs: Dict[str, Dict[str, np.ndarray]] = {}
        for chrom, ctx, pos in feature_order:
            refs.setdefault(chrom, {}).setdefault(ctx, []).append(int(pos))
        for chrom in list(refs.keys()):
            for ctx in list(refs[chrom].keys()):
                refs[chrom][ctx] = np.asarray(sorted(set(refs[chrom][ctx])), dtype=np.uint32)
        X = _extract_matrix_for_samples(samples, refs, feature_order, min_coverage=1)
        X = np.nan_to_num(np.asarray(X, dtype=np.float32), nan=0.5, posinf=0.5, neginf=0.5)
    preproc_path_meta = meta.get("covariate_preprocessor_path")
    preprocessor = (
        CovariatePreprocessor.load_json(preproc_path_meta)
        if isinstance(preproc_path_meta, str) and Path(preproc_path_meta).is_file()
        else None
    )
    cov, cov_report = transform_covariates(
        covariates_path or meta.get("covariates_path"),
        sample_ids,
        preprocessor,
        strict_join=bool(covariates_strict_join or meta.get("covariates_strict_join", False)),
    )
    if cov is not None:
        X = np.concatenate([X, cov], axis=1)

    probs = estimator.predict_proba(X)
    y_pred = np.asarray(np.argmax(probs, axis=1), dtype=np.int32)
    metrics = _compute_metrics(y_true, y_pred, class_names=class_names or ["control", "disease"])
    metrics["covariate_preprocessing"] = cov_report
    metrics["n_covariate_features_used"] = int(cov.shape[1]) if cov is not None else 0
    metrics_path = out_dir / "validation_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    if feature_mode == "observed_hybrid":
        ablation_report = {
            "backend": "tabular_sklearn",
            "feature_mode": feature_mode,
            "balanced_accuracy": metrics.get("balanced_accuracy"),
            "active_feature_families": {
                "dmp": bool(meta.get("observed_feature_include_dmp", True)),
                "chromosome": bool(meta.get("observed_feature_include_chromosome", True)),
                "dmr": bool(meta.get("observed_feature_include_dmr", True)),
                "gene": bool(meta.get("observed_feature_include_gene", True)),
            },
            "recommended_ablation_matrix": [
                {"name": "baseline", "include_dmp": False, "include_dmr": False, "include_gene": False},
                {"name": "plus_dmp", "include_dmp": True, "include_dmr": False, "include_gene": False},
                {"name": "plus_dmr", "include_dmp": False, "include_dmr": True, "include_gene": False},
                {"name": "plus_gene", "include_dmp": False, "include_dmr": False, "include_gene": True},
                {"name": "all", "include_dmp": True, "include_dmr": True, "include_gene": True},
            ],
        }
        with open(out_dir / "feature_family_ablation.json", "w", encoding="utf-8") as f:
            json.dump(ablation_report, f, indent=2)

    recs: List[Dict[str, Any]] = []
    min_obs = float(
        max(
            0.0,
            min(
                1.0,
                observed_feature_min_obs_fraction
                if observed_feature_min_obs_fraction is not None
                else float(meta.get("observed_feature_min_obs_fraction", 0.0)),
            ),
        )
    )
    for i, sample in enumerate(samples):
        rec: Dict[str, Any] = {
            "sample": Path(sample).name,
            "sample_path": sample,
            "expected_class": int(y_true[i]),
            "prediction": int(y_pred[i]),
        }
        for j in range(probs.shape[1]):
            rec[f"prob_class{j}"] = float(probs[i, j])
        if obs_fraction_vec is not None:
            obs_f = float(obs_fraction_vec[i])
            rec["obs_fraction"] = obs_f
            rec["low_evidence"] = bool(np.isfinite(obs_f) and obs_f < min_obs)
            rec["prediction_evidence_filtered"] = -1 if rec["low_evidence"] else int(y_pred[i])
        recs.append(rec)
    pred_csv = out_dir / "predictions.csv"
    pd.DataFrame(recs).to_csv(pred_csv, index=False)
    return metrics

