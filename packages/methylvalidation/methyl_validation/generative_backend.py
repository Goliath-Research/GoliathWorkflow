"""
Hybrid generative backend for methyl-validation --model.

The model uses:
- detector-derived DMP feature weights from ModelFeatureBundle
- a linear latent encoder (VAE-style surrogate)
- class-conditional diagonal Gaussian density in latent space
"""

from __future__ import annotations

import json
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

from methyl_predictor.project_resolver import resolve_predictor_config
from methyl_utils import load_project
from methyl_utils.methyl_centroid_pair import MethylCentroidPair

from .covariate_preprocessor import CovariatePreprocessor, fit_covariates, transform_covariates
from .model_bundle import load_bundle_dmp_index


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


def _fit_linear_latent_encoder(X: np.ndarray, latent_dim: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    X_mean = np.mean(X, axis=0, dtype=np.float64).astype(np.float32)
    X_centered = X - X_mean
    _u, _s, vt = np.linalg.svd(X_centered, full_matrices=False)
    k = int(max(1, min(int(latent_dim), vt.shape[0])))
    components = vt[:k, :].astype(np.float32)
    z = X_centered @ components.T
    return X_mean, components, z


def _gaussian_log_prob_diag(z: np.ndarray, mean: np.ndarray, var: np.ndarray) -> np.ndarray:
    var_safe = np.maximum(var, 1e-6)
    return -0.5 * np.sum(np.log(2.0 * np.pi * var_safe) + ((z - mean) ** 2) / var_safe, axis=1)


def _posterior_from_latent(
    z: np.ndarray,
    class_means: np.ndarray,
    class_vars: np.ndarray,
    class_priors: np.ndarray,
) -> np.ndarray:
    n_classes = class_means.shape[0]
    log_scores = np.zeros((z.shape[0], n_classes), dtype=np.float64)
    for cls in range(n_classes):
        log_scores[:, cls] = _gaussian_log_prob_diag(z, class_means[cls], class_vars[cls]) + np.log(
            max(float(class_priors[cls]), 1e-12)
        )
    log_scores -= np.max(log_scores, axis=1, keepdims=True)
    probs = np.exp(log_scores)
    denom = np.sum(probs, axis=1, keepdims=True)
    denom = np.where(denom <= 0.0, 1.0, denom)
    return (probs / denom).astype(np.float32)


def _compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, class_names: List[str]) -> Dict[str, Any]:
    n_classes = len(class_names)
    labels = list(range(n_classes))
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        "n_samples": int(len(y_true)),
        "n_classes": int(n_classes),
        "class_names": class_names,
        "macro_f1": float(np.mean(f1)),
        "weighted_f1": float(np.average(f1, weights=support) if support.sum() > 0 else 0.0),
    }


def _resolve_eval_paths_and_labels(project_json: str | Path, class_names: List[str]) -> Tuple[List[str], Optional[np.ndarray]]:
    predictor_cfg = resolve_predictor_config(project_json)
    samples: List[str] = []
    y_true: List[int] = []

    if predictor_cfg.test_group_paths:
        for idx, entry in enumerate(predictor_cfg.test_group_paths):
            cls_idx = int(entry.get("class_index", idx))
            paths = [str(p) for p in (entry.get("paths") or [])]
            for p in paths:
                samples.append(p)
                y_true.append(cls_idx)
        return samples, np.asarray(y_true, dtype=np.int32)

    if predictor_cfg.test_control_paths or predictor_cfg.test_disease_paths:
        samples = list(predictor_cfg.test_control_paths) + list(predictor_cfg.test_disease_paths)
        y_true = [0] * len(predictor_cfg.test_control_paths) + [1] * len(predictor_cfg.test_disease_paths)
        return samples, np.asarray(y_true, dtype=np.int32)

    # Fallback: evaluate on project-resolved cohorts.
    project = load_project(project_json)
    for cls_idx, (label, paths) in enumerate(project.get_resolved_groups()):
        if cls_idx >= len(class_names):
            continue
        for p in paths:
            samples.append(str(p))
            y_true.append(cls_idx)
    if samples:
        return samples, np.asarray(y_true, dtype=np.int32)
    return [], None


def train_generative_model(
    project_json: str | Path,
    bundle_h5: str | Path,
    output_dir: str | Path,
    *,
    max_dmps: int = 5000,
    latent_dim: int = 16,
    kl_weight: float = 0.1,
    density_type: str = "diag_gaussian",
    epochs: int = 50,
    batch_size: int = 64,
    random_seed: int = 13,
    calibrate: bool = False,
    covariates_path: Optional[str] = None,
    covariate_id_column: str = "sample_id",
    covariates_strict_join: bool = True,
    covariate_numeric_columns: Optional[List[str]] = None,
    covariate_categorical_columns: Optional[List[str]] = None,
    covariate_missing_numeric_strategy: str = "mean",
    covariate_standardize_numeric: bool = True,
) -> Path:
    np.random.seed(int(random_seed))
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
    if len(all_paths) < 2:
        raise ValueError("Need at least 2 training samples to fit generative backend.")

    X_methyl = _extract_matrix_for_samples(all_paths, refs, feature_order, min_coverage=1)
    X_methyl = np.nan_to_num(np.asarray(X_methyl, dtype=np.float32), nan=0.5, posinf=0.5, neginf=0.5)

    dmp_weights = np.asarray(dmp_df["weight"].fillna(0.0).astype(np.float32).tolist(), dtype=np.float32)
    dmp_weights = np.abs(dmp_weights)
    if float(np.max(dmp_weights)) <= 0.0:
        dmp_weights = np.ones_like(dmp_weights, dtype=np.float32)
    else:
        dmp_weights = dmp_weights / float(np.max(dmp_weights))

    cov, preprocessor, cov_report = fit_covariates(
        covariates_path,
        sample_ids,
        covariate_id_column=covariate_id_column,
        strict_join=covariates_strict_join,
        numeric_columns=covariate_numeric_columns,
        categorical_columns=covariate_categorical_columns,
        missing_numeric_strategy=covariate_missing_numeric_strategy,
        standardize_numeric=covariate_standardize_numeric,
    )
    n_covariates = 0
    if cov is not None:
        n_covariates = int(cov.shape[1])
        X = np.concatenate([X_methyl, cov], axis=1)
        feature_weights = np.concatenate([dmp_weights, np.ones((n_covariates,), dtype=np.float32)], axis=0)
    else:
        X = X_methyl
        feature_weights = dmp_weights

    X_weighted = X * feature_weights.reshape(1, -1)
    encoder_mean, encoder_components, z = _fit_linear_latent_encoder(X_weighted, latent_dim=latent_dim)

    y_arr = np.asarray(y, dtype=np.int32)
    n_classes = len(class_names)
    class_means = np.zeros((n_classes, z.shape[1]), dtype=np.float32)
    class_vars = np.zeros((n_classes, z.shape[1]), dtype=np.float32)
    class_priors = np.zeros((n_classes,), dtype=np.float32)
    for cls in range(n_classes):
        z_cls = z[y_arr == cls]
        if z_cls.shape[0] == 0:
            class_means[cls] = 0.0
            class_vars[cls] = 1.0
            class_priors[cls] = 1e-6
            continue
        class_means[cls] = np.mean(z_cls, axis=0, dtype=np.float64).astype(np.float32)
        class_vars[cls] = np.var(z_cls, axis=0, dtype=np.float64).astype(np.float32) + 1e-4
        class_priors[cls] = float(z_cls.shape[0]) / float(z.shape[0])

    model_path = out_dir / "generative-model.npz"
    np.savez_compressed(
        model_path,
        encoder_mean=encoder_mean.astype(np.float32),
        encoder_components=encoder_components.astype(np.float32),
        feature_weights=feature_weights.astype(np.float32),
        class_means=class_means.astype(np.float32),
        class_vars=class_vars.astype(np.float32),
        class_priors=class_priors.astype(np.float32),
    )

    preprocessor_path = out_dir / "covariate-preprocessor.json"
    if preprocessor is not None:
        preprocessor.save_json(preprocessor_path)

    meta = {
        "model_backend": "generative_hybrid",
        "architecture": "linear_encoder_diag_gaussian",
        "density_type": str(density_type),
        "class_names": class_names,
        "n_classes": int(n_classes),
        "project_json": str(Path(project_json).resolve()),
        "bundle_h5": str(Path(bundle_h5).resolve()),
        "n_features": int(X.shape[1]),
        "n_dmps": int(len(feature_order)),
        "n_covariates": int(n_covariates),
        "feature_order": [{"chromosome": c, "context": ctx, "position": int(pos)} for c, ctx, pos in feature_order],
        "covariates_path": str(covariates_path) if covariates_path else None,
        "covariate_id_column": covariate_id_column,
        "covariates_strict_join": bool(covariates_strict_join),
        "covariate_numeric_columns": [str(x) for x in (covariate_numeric_columns or [])],
        "covariate_categorical_columns": [str(x) for x in (covariate_categorical_columns or [])],
        "covariate_missing_numeric_strategy": str(covariate_missing_numeric_strategy),
        "covariate_standardize_numeric": bool(covariate_standardize_numeric),
        "covariate_preprocessor_path": str(preprocessor_path) if preprocessor is not None else None,
        "covariate_preprocessing": cov_report,
        "latent_dim_requested": int(latent_dim),
        "latent_dim_fitted": int(encoder_components.shape[0]),
        "kl_weight": float(kl_weight),
        "epochs": int(epochs),
        "batch_size": int(batch_size),
        "random_seed": int(random_seed),
        "calibrate": bool(calibrate),
    }
    with open(out_dir / "generative-model-metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return model_path


def predict_generative_model_from_project(
    project_json: str | Path,
    model_dir: str | Path,
    output_dir: str | Path,
    *,
    covariates_path: Optional[str] = None,
    covariate_id_column: str = "sample_id",
    covariates_strict_join: bool = True,
) -> Dict[str, Any]:
    model_dir = Path(model_dir).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / "generative-model.npz"
    meta_path = model_dir / "generative-model-metadata.json"
    if not model_path.is_file() or not meta_path.is_file():
        raise FileNotFoundError(f"Generative model artifacts not found under {model_dir}")

    data = np.load(model_path)
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    class_names = [str(x) for x in meta.get("class_names", [])]
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

    samples, y_true = _resolve_eval_paths_and_labels(project_json, class_names)
    if not samples:
        raise ValueError("No evaluation samples resolved for generative prediction.")
    sample_ids = [Path(p).name for p in samples]

    X_methyl = _extract_matrix_for_samples(samples, refs, feature_order, min_coverage=1)
    X_methyl = np.nan_to_num(np.asarray(X_methyl, dtype=np.float32), nan=0.5, posinf=0.5, neginf=0.5)

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
        strict_join=bool(covariates_strict_join),
    )
    if cov is not None:
        X = np.concatenate([X_methyl, cov], axis=1)
    else:
        X = X_methyl

    feature_weights = np.asarray(data["feature_weights"], dtype=np.float32)
    if X.shape[1] != feature_weights.shape[0]:
        raise ValueError(
            "Feature shape mismatch between prediction matrix and trained model: "
            f"{X.shape[1]} != {feature_weights.shape[0]}"
        )
    X_weighted = X * feature_weights.reshape(1, -1)
    encoder_mean = np.asarray(data["encoder_mean"], dtype=np.float32)
    encoder_components = np.asarray(data["encoder_components"], dtype=np.float32)
    z = (X_weighted - encoder_mean.reshape(1, -1)) @ encoder_components.T

    probs = _posterior_from_latent(
        z=z,
        class_means=np.asarray(data["class_means"], dtype=np.float32),
        class_vars=np.asarray(data["class_vars"], dtype=np.float32),
        class_priors=np.asarray(data["class_priors"], dtype=np.float32),
    )
    y_pred = np.asarray(np.argmax(probs, axis=1), dtype=np.int32)

    metrics: Dict[str, Any]
    if y_true is not None and y_true.shape[0] == y_pred.shape[0]:
        metrics = _compute_metrics(y_true, y_pred, class_names=class_names)
    else:
        metrics = {
            "n_samples": int(y_pred.shape[0]),
            "n_classes": int(len(class_names)),
            "class_names": class_names,
        }
    metrics["covariate_preprocessing"] = cov_report
    metrics["n_covariate_features_used"] = int(cov.shape[1]) if cov is not None else 0
    with open(out_dir / "validation_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    recs: List[Dict[str, Any]] = []
    for i, sample in enumerate(samples):
        rec: Dict[str, Any] = {
            "sample": Path(sample).name,
            "sample_path": sample,
            "prediction": int(y_pred[i]),
        }
        if y_true is not None and i < len(y_true):
            rec["expected_class"] = int(y_true[i])
        for j in range(probs.shape[1]):
            rec[f"prob_class{j}"] = float(probs[i, j])
        recs.append(rec)
    pd.DataFrame(recs).to_csv(out_dir / "predictions.csv", index=False)
    return metrics

