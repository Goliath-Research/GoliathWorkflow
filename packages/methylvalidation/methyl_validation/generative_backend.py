"""
Hybrid generative backend for methyl-validation --model.

The model uses:
- detector-derived DMP feature weights from ModelFeatureBundle
- a linear latent encoder (VAE-style surrogate)
- class-conditional diagonal Gaussian density in latent space
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
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
from .eval_split_resolver import resolve_eval_paths_and_labels
from .model_bundle import load_bundle_dmp_index, load_bundle_gene_feature_ranges
from .observed_feature_builder import (
    HYBRID_FEATURE_FAMILY_SETS,
    apply_feature_fill_values,
    build_observed_hybrid_feature_table,
    derive_observed_hybrid_anchors,
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


def _resolve_eval_paths_and_labels(project_json: str | Path, class_names: List[str]) -> Tuple[List[str], Optional[np.ndarray]]:
    predictor_cfg = resolve_predictor_config(project_json)
    return resolve_eval_paths_and_labels(
        project_json,
        class_names,
        predictor_cfg=predictor_cfg,
        project_loader=load_project,
    )


def _resolve_class_centroid_dirs(project: Any, class_names: Sequence[str]) -> Dict[str, str]:
    label_to_dir: Dict[str, str] = {}
    try:
        resolved = project.get_resolved_groups()
        derived = project.get_derived_paths()
        centroid_dirs = list(getattr(derived, "centroid_dirs", []) or [])
        for idx, (label, _paths) in enumerate(resolved):
            if idx < len(centroid_dirs):
                label_to_dir[str(label)] = str(centroid_dirs[idx])
    except Exception:
        label_to_dir = {}
    for name in class_names:
        label_to_dir.setdefault(str(name), "")
    return {k: v for k, v in label_to_dir.items() if str(v).strip()}


def train_generative_model(
    project_json: str | Path,
    bundle_h5: str | Path,
    output_dir: str | Path,
    *,
    max_dmps: Optional[int] = None,
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
    feature_family_set: str = "dmp",
    gene_feature_loading: str = "frozen",
    observed_hist_eps: float = 1e-6,
    observed_hist_alpha: float = 0.5,
    observed_hist_evidence_clip_cap: float = 5.0,
    observed_hist_tail_agreement_threshold: float = 0.10,
) -> Path:
    np.random.seed(int(random_seed))
    with _project_cwd(project_json):
        project = load_project(project_json)
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    dmp_df = load_bundle_dmp_index(bundle_h5)
    fixed_gene_features_df = load_bundle_gene_feature_ranges(bundle_h5)
    max_dmps_norm = int(max_dmps) if (max_dmps is not None and int(max_dmps) > 0) else 0
    if max_dmps_norm and len(dmp_df) > max_dmps_norm:
        dmp_df = dmp_df.sort_values(["effect_size"], ascending=[False]).head(max_dmps_norm).copy()
    refs, feature_order = _build_reference_map(dmp_df)

    resolved = project.get_resolved_groups()
    class_names = [str(lbl) for lbl, _ in resolved]
    class_centroid_dirs = _resolve_class_centroid_dirs(project, class_names)
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

    feature_mode_norm = str(feature_mode or "raw_dmp").strip().lower()
    feature_family_set_norm = str(feature_family_set or "dmp").strip().lower()
    gene_feature_loading_norm = str(gene_feature_loading or "frozen").strip().lower()
    if feature_family_set_norm not in HYBRID_FEATURE_FAMILY_SETS:
        raise ValueError(
            f"feature_family_set must be one of {list(HYBRID_FEATURE_FAMILY_SETS)}, got {feature_family_set!r}"
        )
    if gene_feature_loading_norm not in {"frozen", "range"}:
        raise ValueError(
            f"gene_feature_loading must be one of ['frozen', 'range'], got {gene_feature_loading!r}"
        )
    if feature_mode_norm == "observed_hybrid":
        anchors = derive_observed_hybrid_anchors(
            all_paths,
            y,
            class_names,
            dmp_df,
            min_coverage=int(max(1, observed_feature_min_coverage)),
            gene_feature_loading=gene_feature_loading_norm,
            fixed_gene_features_df=fixed_gene_features_df,
        )
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
            healthy_reference_vector=anchors.healthy_reference_vector,
            cancer_reference_vector=anchors.cancer_reference_vector,
            per_cancer_reference_vectors=anchors.per_cancer_reference_vectors,
            healthy_class_label=anchors.healthy_class_label,
            cancer_class_labels=anchors.cancer_class_labels,
            anchor_strategy=anchors.anchor_strategy,
            expected_feature_order_fingerprint=anchors.feature_order_fingerprint,
            centroid_dir_by_class_label=class_centroid_dirs,
            hist_eps=float(observed_hist_eps),
            hist_alpha=float(observed_hist_alpha),
            hist_evidence_clip_cap=float(observed_hist_evidence_clip_cap),
            hist_tail_agreement_threshold=float(observed_hist_tail_agreement_threshold),
            feature_family_set=feature_family_set_norm,
            gene_feature_loading=gene_feature_loading_norm,
            fixed_gene_features_df=fixed_gene_features_df,
        )
        X_methyl = np.asarray(feat.X, dtype=np.float32)
        feature_fill_values = fit_feature_fill_values(X_methyl)
        X_methyl = apply_feature_fill_values(X_methyl, feature_fill_values)
        observed_feature_names = list(feat.feature_names)
        observed_feature_report = dict(feat.report)
        dmp_weights = np.ones((X_methyl.shape[1],), dtype=np.float32)
        observed_feature_quantiles_out = [float(q) for q in (feat.report.get("quantiles") or [])]
        observed_healthy_reference = anchors.healthy_reference_vector.astype(np.float32)
        observed_cancer_reference = anchors.cancer_reference_vector.astype(np.float32)
        observed_per_cancer_references = [
            np.asarray(v, dtype=np.float32) for v in anchors.per_cancer_reference_vectors
        ]
        observed_healthy_class_index = int(anchors.healthy_class_index)
        observed_healthy_class_label = str(anchors.healthy_class_label)
        observed_cancer_class_labels = [str(x) for x in anchors.cancer_class_labels]
        observed_anchor_strategy = str(anchors.anchor_strategy)
        observed_feature_order_fingerprint = str(anchors.feature_order_fingerprint)
    else:
        X_methyl = _extract_matrix_for_samples(all_paths, refs, feature_order, min_coverage=1)
        X_methyl = np.nan_to_num(np.asarray(X_methyl, dtype=np.float32), nan=0.5, posinf=0.5, neginf=0.5)

        if "effect_size" not in dmp_df.columns:
            raise ValueError("Raw DMP feature mode requires effect_size in bundle DMP index.")
        dmp_weights = np.asarray(dmp_df["effect_size"].fillna(0.0).astype(np.float32).tolist(), dtype=np.float32)
        dmp_weights = np.abs(dmp_weights)
        if float(np.max(dmp_weights)) <= 0.0:
            dmp_weights = np.ones_like(dmp_weights, dtype=np.float32)
        else:
            dmp_weights = dmp_weights / float(np.max(dmp_weights))
        feature_fill_values = None
        observed_feature_names = []
        observed_feature_report = {}
        observed_feature_quantiles_out = [float(q) for q in (observed_feature_quantiles or [])]
        observed_healthy_reference = None
        observed_cancer_reference = None
        observed_per_cancer_references: List[np.ndarray] = []
        observed_healthy_class_index = None
        observed_healthy_class_label = None
        observed_cancer_class_labels = []
        observed_anchor_strategy = None
        observed_feature_order_fingerprint = None

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

    train_probs = _posterior_from_latent(
        z=z,
        class_means=class_means,
        class_vars=class_vars,
        class_priors=class_priors,
    )
    y_pred_train = np.asarray(np.argmax(train_probs, axis=1), dtype=np.int32)
    train_metrics = _compute_metrics(y_arr, y_pred_train, class_names=class_names)
    train_metrics["metrics_source"] = "generative_train"
    train_metrics["evaluation_split"] = "training"
    train_metrics["n_train_samples"] = int(len(y_arr))
    train_metrics["n_train_features"] = int(X.shape[1])
    with open(out_dir / "training_metrics.json", "w", encoding="utf-8") as f:
        json.dump(train_metrics, f, indent=2)

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
        "feature_mode": feature_mode_norm,
        "feature_family_set": feature_family_set_norm,
        "gene_feature_loading": gene_feature_loading_norm,
        "density_type": str(density_type),
        "class_names": class_names,
        "n_classes": int(n_classes),
        "project_json": str(Path(project_json).resolve()),
        "bundle_h5": str(Path(bundle_h5).resolve()),
        "max_dmps": int(max_dmps_norm),
        "n_features": int(X.shape[1]),
        "n_dmps": int(len(feature_order)),
        "n_covariates": int(n_covariates),
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
        "observed_hist_eps": float(observed_hist_eps),
        "observed_hist_alpha": float(observed_hist_alpha),
        "observed_hist_evidence_clip_cap": float(observed_hist_evidence_clip_cap),
        "observed_hist_tail_agreement_threshold": float(observed_hist_tail_agreement_threshold),
        "observed_feature_fill_values": (
            [float(v) for v in feature_fill_values.tolist()] if feature_fill_values is not None else None
        ),
        "observed_feature_report": observed_feature_report,
        "observed_healthy_reference_vector": (
            [float(v) for v in observed_healthy_reference.tolist()] if observed_healthy_reference is not None else None
        ),
        "observed_cancer_reference_vector": (
            [float(v) for v in observed_cancer_reference.tolist()] if observed_cancer_reference is not None else None
        ),
        "observed_per_cancer_reference_vectors": [
            [float(v) for v in vec.tolist()] for vec in observed_per_cancer_references
        ],
        "observed_healthy_class_index": observed_healthy_class_index,
        "observed_healthy_class_label": observed_healthy_class_label,
        "observed_cancer_class_labels": observed_cancer_class_labels,
        "observed_anchor_strategy": observed_anchor_strategy,
        "observed_feature_order_fingerprint": observed_feature_order_fingerprint,
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
    observed_feature_min_obs_fraction: Optional[float] = None,
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
    feature_mode = str(meta.get("feature_mode", "raw_dmp")).strip().lower()
    with _project_cwd(project_json):
        project = load_project(project_json)
    class_centroid_dirs = _resolve_class_centroid_dirs(project, class_names)
    samples, y_true = _resolve_eval_paths_and_labels(project_json, class_names)
    if not samples:
        raise ValueError("No evaluation samples resolved for generative prediction.")
    sample_ids = sample_ids_from_paths(samples)

    obs_fraction_vec: Optional[np.ndarray] = None
    if feature_mode == "observed_hybrid":
        bundle_h5 = meta.get("bundle_h5")
        if not isinstance(bundle_h5, str) or not Path(bundle_h5).is_file():
            raise FileNotFoundError("Observed-hybrid mode requires bundle_h5 in generative metadata.")
        dmp_df = load_bundle_dmp_index(bundle_h5)
        max_dmps = int(meta.get("max_dmps", len(dmp_df) or 0))
        if max_dmps and len(dmp_df) > max_dmps:
            dmp_df = dmp_df.sort_values(["effect_size"], ascending=[False]).head(max_dmps).copy()
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
            healthy_reference_vector=meta.get("observed_healthy_reference_vector"),
            cancer_reference_vector=meta.get("observed_cancer_reference_vector"),
            per_cancer_reference_vectors=meta.get("observed_per_cancer_reference_vectors"),
            healthy_class_label=meta.get("observed_healthy_class_label"),
            cancer_class_labels=meta.get("observed_cancer_class_labels") or [],
            anchor_strategy=meta.get("observed_anchor_strategy"),
            expected_feature_order_fingerprint=meta.get("observed_feature_order_fingerprint"),
            centroid_dir_by_class_label=class_centroid_dirs,
            hist_eps=float(meta.get("observed_hist_eps", 1e-6)),
            hist_alpha=float(meta.get("observed_hist_alpha", 0.5)),
            hist_evidence_clip_cap=float(meta.get("observed_hist_evidence_clip_cap", 5.0)),
            hist_tail_agreement_threshold=float(
                meta.get("observed_hist_tail_agreement_threshold", 0.10)
            ),
            feature_family_set=str(meta.get("feature_family_set", "dmp")),
            gene_feature_loading=str(meta.get("gene_feature_loading", "frozen")),
            fixed_gene_features_df=load_bundle_gene_feature_ranges(bundle_h5),
        )
        verify_feature_schema(
            feat.feature_names,
            meta.get("observed_feature_names") or [],
            context="generative predict observed_hybrid",
        )
        X_methyl = np.asarray(feat.X, dtype=np.float32)
        if "obs_fraction" in feat.feature_names:
            obs_fraction_vec = X_methyl[:, feat.feature_names.index("obs_fraction")].astype(np.float32)
        fill_values = meta.get("observed_feature_fill_values")
        if not isinstance(fill_values, list):
            raise ValueError("Observed-hybrid mode requires observed_feature_fill_values in metadata.")
        X_methyl = apply_feature_fill_values(X_methyl, fill_values)
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
    if feature_mode == "observed_hybrid":
        active_family_set = str(meta.get("feature_family_set", "dmp"))
        active_gene_loading = str(meta.get("gene_feature_loading", "frozen"))
        cm = metrics.get("confusion_matrix") or []
        worst_group_ba = None
        if isinstance(cm, list) and cm:
            recalls: List[float] = []
            for i, row in enumerate(cm):
                denom = float(np.sum(row))
                recalls.append(float(row[i]) / denom if denom > 0 else 0.0)
            if recalls:
                worst_group_ba = float(min(recalls))
        ablation_report = {
            "backend": "generative_hybrid",
            "feature_mode": feature_mode,
            "balanced_accuracy": metrics.get("balanced_accuracy"),
            "worst_group_balanced_accuracy": worst_group_ba,
            "active_feature_family_set": active_family_set,
            "active_gene_feature_loading": active_gene_loading,
            "active_feature_families": {
                "dmp": ("dmp" in active_family_set or active_family_set == "hybrid-all"),
                "chromosome": bool(meta.get("observed_feature_include_chromosome", True)),
                "dmr": bool(meta.get("observed_feature_include_dmr", True)),
                "gene": ("gene" in active_family_set or active_family_set == "hybrid-all"),
                "structural": ("structural" in active_family_set or active_family_set == "hybrid-all"),
            },
            "mandatory_ablation_matrix": [
                {"name": "dmp", "feature_family_set": "dmp"},
                {"name": "gene", "feature_family_set": "gene"},
                {"name": "structural", "feature_family_set": "structural"},
                {"name": "dmp+gene", "feature_family_set": "dmp+gene"},
                {"name": "dmp+structural", "feature_family_set": "dmp+structural"},
                {"name": "hybrid-all", "feature_family_set": "hybrid-all"},
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
            "prediction": int(y_pred[i]),
        }
        if y_true is not None and i < len(y_true):
            rec["expected_class"] = int(y_true[i])
        for j in range(probs.shape[1]):
            rec[f"prob_class{j}"] = float(probs[i, j])
        if obs_fraction_vec is not None:
            obs_f = float(obs_fraction_vec[i])
            rec["obs_fraction"] = obs_f
            rec["low_evidence"] = bool(np.isfinite(obs_f) and obs_f < min_obs)
            rec["prediction_evidence_filtered"] = -1 if rec["low_evidence"] else int(y_pred[i])
        recs.append(rec)
    pd.DataFrame(recs).to_csv(out_dir / "predictions.csv", index=False)
    return metrics

