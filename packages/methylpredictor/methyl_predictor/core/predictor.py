"""
Core prediction: load MethylClassifier, run prediction on test sets, compute metrics, write JSON + CSV.
"""

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)

from ..models.config import PredictorConfig


def _expand_nested_blind_paths(config: PredictorConfig) -> None:
    """Expand config.blind groups into test_blind_paths and lineage (standalone JSON)."""
    if config.test_blind_paths:
        return
    if not config.blind or not isinstance(config.blind, dict):
        return
    groups = config.blind.get("groups")
    if not isinstance(groups, list) or len(groups) == 0:
        return

    from ..project_resolver import (
        _collect_paths_and_lineage,
        _expand_side_group_paths,
    )

    proj_stub = Path.cwd()
    wrap = {
        "label": config.blind.get("label") or "",
        "groups": groups,
    }
    bmap = _expand_side_group_paths(
        wrap, config.samples_base_path, proj_stub, config.path_remap
    )
    labels = [
        str(g.get("label"))
        for g in groups
        if isinstance(g, dict) and g.get("label")
    ]
    paths, lin = _collect_paths_and_lineage("blind", labels, bmap)
    config.test_blind_paths = paths
    config.sample_lineage = lin
    config.report_blind = copy.deepcopy(config.blind)


def _expand_nested_labeled_paths(config: PredictorConfig) -> None:
    """Expand optional config.controls / config.diseases into flat paths and report blocks."""
    if config.test_blind_paths:
        return
    if config.test_group_paths:
        return
    if config.test_control_paths or config.test_disease_paths:
        return
    if not config.controls or not config.diseases:
        return

    from ..project_resolver import (
        _collect_paths_and_lineage,
        _expand_side_group_paths,
    )

    proj_stub = Path.cwd()
    ctrl_map = _expand_side_group_paths(
        config.controls, config.samples_base_path, proj_stub, config.path_remap
    )
    dis_map = _expand_side_group_paths(
        config.diseases, config.samples_base_path, proj_stub, config.path_remap
    )
    ctrl_labels = [
        str(g.get("label"))
        for g in (config.controls.get("groups") or [])
        if isinstance(g, dict) and g.get("label")
    ]
    dis_labels: List[str] = []
    for g in config.diseases.get("groups") or []:
        if not isinstance(g, dict) or not g.get("label"):
            continue
        if g.get("stages"):
            for st in g.get("stages") or []:
                if isinstance(st, dict) and st.get("label"):
                    dis_labels.append(f"{g['label']}_{st['label']}")
        else:
            dis_labels.append(str(g["label"]))
    c_paths, lin_c = _collect_paths_and_lineage("control", ctrl_labels, ctrl_map)
    d_paths, lin_d = _collect_paths_and_lineage("disease", dis_labels, dis_map)
    config.test_control_paths = c_paths
    config.test_disease_paths = d_paths
    config.sample_lineage = lin_c + lin_d
    config.report_controls = copy.deepcopy(config.controls)
    config.report_diseases = copy.deepcopy(config.diseases)


def _prepare_predictor_paths_and_mode(
    config: PredictorConfig,
) -> Literal["labeled", "blind"]:
    """
    Resolve cohort paths once from config: either blind (test_blind_paths + lineage)
    or labeled (controls/diseases / test_group_paths / flat paths). Does not load H5;
    downstream runs a single classify_samples_from_list pass; metrics vs blind report
    depend only on this mode and expected_classes.
    """
    if not config.test_blind_paths:
        _expand_nested_blind_paths(config)
    if config.test_blind_paths:
        if (
            config.test_control_paths
            or config.test_disease_paths
            or config.test_group_paths
        ):
            raise ValueError(
                "Blind cohort (test_blind_paths) cannot be combined with labeled "
                "control/disease paths or test_group_paths."
            )
        return "blind"
    _expand_nested_labeled_paths(config)
    return "labeled"


def _row_to_sample_dict(row: pd.Series) -> Dict[str, Any]:
    """Serialize a CSV row to JSON-friendly dict (numpy scalars -> Python)."""
    out: Dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (np.floating, np.integer)):
            out[k] = float(v) if isinstance(v, np.floating) else int(v)
        elif pd.isna(v):
            out[k] = None
        else:
            out[k] = v
    return out


def _probability_map_from_row(
    row: pd.Series, n_classes: int, class_names: List[str]
) -> Dict[str, float]:
    """Build {class_name: probability} from prob_class0.. columns."""
    out: Dict[str, float] = {}
    for i in range(n_classes):
        col = f"prob_class{i}"
        if col not in row.index:
            continue
        v = row[col]
        name = class_names[i] if i < len(class_names) else f"Class_{i}"
        if pd.isna(v):
            out[str(name)] = float("nan")
        else:
            out[str(name)] = float(v)
    return out


def _blind_sample_record(
    row: pd.Series, n_classes: int, class_names: List[str]
) -> Dict[str, Any]:
    """One sample dict for blind mode: probabilities + predicted subgroup."""
    base = _row_to_sample_dict(row)
    probs = _probability_map_from_row(row, n_classes, class_names)
    pred_idx = int(row.get("prediction", 0))
    pred_name = (
        str(class_names[pred_idx])
        if pred_idx < len(class_names)
        else f"Class_{pred_idx}"
    )
    pvals = [probs.get(str(class_names[i] if i < len(class_names) else f"Class_{i}"), 0.0) for i in range(n_classes)]
    pvals = [0.0 if (isinstance(x, float) and np.isnan(x)) else float(x) for x in pvals]
    max_p = max(pvals) if pvals else 0.0
    ent = 0.0
    for p in pvals:
        if p > 0:
            ent -= p * np.log(p + 1e-300)
    base["probabilities"] = probs
    base["predicted_subgroup"] = pred_name
    base["max_probability"] = float(max_p)
    base["entropy"] = float(ent)
    return base


def _compute_blind_summary(
    df: pd.DataFrame, n_classes: int, class_names: List[str]
) -> Dict[str, Any]:
    """Aggregate stats for blind runs (no ground-truth metrics)."""
    counts: Dict[str, int] = {}
    for i in range(n_classes):
        name = str(class_names[i] if i < len(class_names) else f"Class_{i}")
        counts[name] = 0
    mean_probs: Dict[str, float] = {k: 0.0 for k in counts}
    n = len(df)
    entropies: List[float] = []
    for _, row in df.iterrows():
        pi = int(row.get("prediction", 0))
        pname = str(class_names[pi] if pi < len(class_names) else f"Class_{pi}")
        counts[pname] = counts.get(pname, 0) + 1
        rec = _blind_sample_record(row, n_classes, class_names)
        entropies.append(rec["entropy"])
        for k, v in rec["probabilities"].items():
            mean_probs[k] = mean_probs.get(k, 0.0) + (v if not np.isnan(v) else 0.0)
    if n > 0:
        for k in list(mean_probs.keys()):
            mean_probs[k] = float(mean_probs[k] / n)
    return {
        "n_samples": n,
        "predicted_counts_by_class": counts,
        "mean_probability_by_class": mean_probs,
        "mean_entropy": float(np.mean(entropies)) if entropies else 0.0,
    }


def _print_blind_summary(df: pd.DataFrame, n_classes: int, class_names: List[str]) -> None:
    summary = _compute_blind_summary(df, n_classes, class_names)
    print("\n🔬 Blind prediction summary (no ground-truth labels):")
    print(f"   Samples scored: {summary['n_samples']}")
    print("   Predicted class counts:")
    for k, v in summary["predicted_counts_by_class"].items():
        print(f"      {k}: {v}")
    print(f"   Mean entropy: {summary['mean_entropy']:.4f}")


def _hierarchy_probability_summary(
    df: pd.DataFrame,
    n_classes: int,
    class_names: List[str],
    hierarchy: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Mean class probabilities plus pooled control / disease-family marginals when metadata allows."""
    if not hierarchy or n_classes < 2:
        return None
    prob_cols = [f"prob_class{i}" for i in range(n_classes)]
    if not all(c in df.columns for c in prob_cols):
        return None
    mat = df[prob_cols].values.astype(float)
    mean_p = mat.mean(axis=0)
    name_to_i = {n: i for i, n in enumerate(class_names)}
    out: Dict[str, Any] = {
        "mean_probability_by_class": {class_names[i]: float(mean_p[i]) for i in range(n_classes)}
    }
    ctrl = hierarchy.get("control_strata") or []
    ci = [name_to_i[c] for c in ctrl if c in name_to_i]
    if ci:
        out["mean_probability_controls_pooled"] = float(mean_p[ci].sum())
    fams = hierarchy.get("disease_families")
    if isinstance(fams, list):
        fam_m: Dict[str, float] = {}
        for fam in fams:
            if not isinstance(fam, dict):
                continue
            flabel = str(fam.get("label", ""))
            leaves = fam.get("leaves") or []
            idxs = [name_to_i[l] for l in leaves if l in name_to_i]
            if idxs and flabel:
                fam_m[flabel] = float(mean_p[idxs].sum())
        if fam_m:
            out["mean_probability_by_disease_family"] = fam_m
    return out


def _build_prediction_report(
    config: PredictorConfig,
    df: pd.DataFrame,
    metrics: Optional[Dict[str, Any]],
    n_classes: int,
    class_names: List[str],
    prediction_mode: Literal["labeled", "blind"],
) -> Dict[str, Any]:
    """
    Build prediction_report.json body: labeled mode mirrors controls/diseases;
    blind mode adds probabilities per class name and blind_summary.
    """
    lineage = config.sample_lineage or []
    name_to_meta = {Path(entry["absolute_path"]).name: entry for entry in lineage}

    if prediction_mode == "blind":
        report: Dict[str, Any] = {
            "mode": "blind",
            "comparison_label": config.comparison_label,
            "validation_metrics": None,
            "class_names": class_names,
            "n_classes": n_classes,
            "blind_summary": _compute_blind_summary(df, n_classes, class_names),
        }
        hs = _hierarchy_probability_summary(
            df, n_classes, class_names, config.cohort_hierarchy
        )
        if hs:
            report["hierarchy_summary"] = hs
        rb = copy.deepcopy(config.report_blind or {"label": "", "groups": []})
        report["blind"] = rb
        groups = rb.get("groups") or []
        for g in groups:
            if not isinstance(g, dict):
                continue
            glabel = str(g.get("label", ""))
            samples: List[Dict[str, Any]] = []
            for _, row in df.iterrows():
                sn = str(row.get("sample", ""))
                meta = name_to_meta.get(sn)
                if meta is None:
                    continue
                if meta.get("side") != "blind" or meta.get("group_label") != glabel:
                    continue
                samples.append(_blind_sample_record(row, n_classes, class_names))
            g["samples"] = samples
        return report

    report = {
        "mode": "labeled",
        "comparison_label": config.comparison_label,
        "validation_metrics": metrics,
        "class_names": class_names,
        "n_classes": n_classes,
    }
    hs = _hierarchy_probability_summary(df, n_classes, class_names, config.cohort_hierarchy)
    if hs:
        report["hierarchy_summary"] = hs

    if config.report_controls is not None and config.report_diseases is not None:
        report["controls"] = copy.deepcopy(config.report_controls)
        report["diseases"] = copy.deepcopy(config.report_diseases)
        for side_key, side_name in (("controls", "control"), ("diseases", "disease")):
            side = report.get(side_key) or {}
            groups = side.get("groups") or []
            for g in groups:
                if not isinstance(g, dict):
                    continue
                glabel = str(g.get("label", ""))
                samples: List[Dict[str, Any]] = []
                for _, row in df.iterrows():
                    sn = str(row.get("sample", ""))
                    meta = name_to_meta.get(sn)
                    if meta is None:
                        continue
                    if meta.get("side") != side_name or meta.get("group_label") != glabel:
                        continue
                    samples.append(_row_to_sample_dict(row))
                g["samples"] = samples
        return report

    report["multiclass_groups"] = []
    if not config.test_group_paths:
        return report
    for entry in config.test_group_paths:
        if not isinstance(entry, dict):
            continue
        glabel = str(entry.get("label", ""))
        samples = []
        for _, row in df.iterrows():
            sn = str(row.get("sample", ""))
            meta = name_to_meta.get(sn)
            if meta is None or meta.get("group_label") != glabel:
                continue
            samples.append(_row_to_sample_dict(row))
        report["multiclass_groups"].append(
            {"label": glabel, "paths": entry.get("paths"), "samples": samples}
        )
    return report


def _compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_classes: int,
    class_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Compute classification metrics (binary or multiclass). Returns a JSON-serializable dict."""
    if class_names is None:
        class_names = [f"Class_{i}" for i in range(n_classes)]
    # Ensure we have labels for all classes
    labels = list(range(n_classes))
    acc = float(accuracy_score(y_true, y_pred))
    balanced_acc = float(balanced_accuracy_score(y_true, y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    metrics: Dict[str, Any] = {
        "accuracy": acc,
        "balanced_accuracy": balanced_acc,
        "confusion_matrix": cm.tolist(),
        "n_samples": int(len(y_true)),
        "n_classes": n_classes,
        "class_names": class_names,
    }
    # Per-class
    per_class = []
    for i, label in enumerate(labels):
        per_class.append({
            "class_index": i,
            "class_name": class_names[i] if i < len(class_names) else f"Class_{i}",
            "precision": float(precision[i]),
            "recall": float(recall[i]),
            "f1": float(f1[i]),
            "support": int(support[i]),
        })
    metrics["per_class"] = per_class
    metrics["macro_precision"] = float(np.mean(precision))
    metrics["macro_recall"] = float(np.mean(recall))
    metrics["macro_f1"] = float(np.mean(f1))
    metrics["weighted_f1"] = float(
        np.average(f1, weights=support) if support.sum() > 0 else 0.0
    )
    # Binary: sensitivity (recall class 1), specificity (recall class 0)
    if n_classes == 2:
        metrics["sensitivity"] = float(recall[1])
        metrics["specificity"] = float(recall[0])
        metrics["precision_binary"] = float(precision[1])
        metrics["recall_binary"] = float(recall[1])
        metrics["f1_binary"] = float(f1[1])
    return metrics


def _dmp_coverage_stats_from_predictions_df(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Aggregate DMP coverage columns from classify_samples_from_list CSV when present."""
    out: Dict[str, Any] = {}
    if "dmp_coverage_pct" in df.columns:
        s = pd.to_numeric(df["dmp_coverage_pct"], errors="coerce").dropna()
        if len(s) > 0:
            out["dmp_coverage_pct_min"] = float(s.min())
            out["dmp_coverage_pct_median"] = float(s.median())
            out["dmp_coverage_pct_mean"] = float(s.mean())
    if "dmps_used" in df.columns and "dmps_total" in df.columns:
        u = pd.to_numeric(df["dmps_used"], errors="coerce")
        t = pd.to_numeric(df["dmps_total"], errors="coerce").replace(0, np.nan)
        ratio = (u / t).replace([np.inf, -np.inf], np.nan).dropna()
        if len(ratio) > 0:
            out["dmps_used_fraction_median"] = float(ratio.median())
            out["dmps_used_fraction_min"] = float(ratio.min())
    return out if out else None


def _warn_if_degenerate_predictions(
    y_pred: np.ndarray, n_classes: int, class_names: List[str]
) -> None:
    """Warn when labeled evaluation uses fewer predicted classes than the model has."""
    uniq = np.unique(y_pred)
    if len(uniq) >= n_classes:
        return
    shown = []
    for i in uniq:
        idx = int(i)
        name = (
            str(class_names[idx])
            if 0 <= idx < len(class_names)
            else f"Class_{idx}"
        )
        shown.append(name)
    print(
        f"\n⚠️ Degenerate predictions: only {len(uniq)} distinct predicted class(es) "
        f"({', '.join(shown)}) for a {n_classes}-class model — "
        "metrics (e.g. balanced accuracy) may be uninformative.",
        flush=True,
    )


def _print_metrics(metrics: Dict[str, Any]) -> None:
    """Print a concise summary to console."""
    n_classes = metrics.get("n_classes", 2)
    print("\n📊 Validation metrics:")
    print(f"   Accuracy:          {metrics['accuracy']:.4f}")
    print(f"   Balanced accuracy: {metrics['balanced_accuracy']:.4f}")
    if n_classes == 2:
        print(f"   Sensitivity:       {metrics.get('sensitivity', 0):.4f}")
        print(f"   Specificity:      {metrics.get('specificity', 0):.4f}")
        print(f"   F1 (binary):      {metrics.get('f1_binary', 0):.4f}")
    else:
        print(f"   Macro F1:         {metrics['macro_f1']:.4f}")
        print(f"   Weighted F1:       {metrics['weighted_f1']:.4f}")
    print("   Confusion matrix (rows=expected, cols=predicted):")
    for row in metrics["confusion_matrix"]:
        print("     " + " ".join(f"{x:>4}" for x in row))
    cov = metrics.get("sample_dmp_coverage")
    if isinstance(cov, dict) and cov:
        parts = []
        if "dmp_coverage_pct_median" in cov:
            parts.append(f"median dmp_coverage_pct={cov['dmp_coverage_pct_median']:.2f}")
        if "dmps_used_fraction_median" in cov:
            parts.append(f"median dmps_used/total={cov['dmps_used_fraction_median']:.4f}")
        if parts:
            print("   " + "; ".join(parts))


def _build_samples_and_expected(
    config: PredictorConfig,
    n_classes: int,
    prediction_mode: Literal["labeled", "blind"],
) -> tuple[List[str], Optional[List[int]]]:
    """
    Build samples_list and expected_classes from already-resolved config paths.
    Returns (samples_list, expected_classes). expected_classes is None for blind or inference-only.
    """
    n_classes = n_classes or 2
    is_multiclass = n_classes > 2

    if prediction_mode == "blind":
        blind_list = [p for p in config.test_blind_paths if p and str(p).strip()]
        return blind_list, None if blind_list else None

    # Labeled runs: test_group_paths (K ≥ 2, including binary OvR where n_classes == 2).
    # Project-resolved multiclass configs set only test_group_paths, not test_control_paths /
    # test_disease_paths; previously K=2 models skipped this branch and saw an empty sample list.
    def _test_group_paths_have_samples() -> bool:
        if not config.test_group_paths:
            return False
        for entry in config.test_group_paths:
            if not isinstance(entry, dict):
                continue
            paths = entry.get("paths") or []
            if any(p and str(p).strip() for p in paths):
                return True
        return False

    if _test_group_paths_have_samples():
        samples_list = []
        expected_classes: List[int] = []
        for j, entry in enumerate(config.test_group_paths):
            if not isinstance(entry, dict):
                continue
            paths = entry.get("paths") or []
            paths = [p for p in paths if p and str(p).strip()]
            if not paths:
                continue
            cls_idx = int(entry.get("class_index", j))
            samples_list.extend(paths)
            expected_classes.extend([cls_idx] * len(paths))
        if samples_list:
            return samples_list, expected_classes

    # Multi-class inference-only: use binary-style paths as single unlabeled list
    if is_multiclass:
        flat = list(config.test_control_paths) + list(config.test_disease_paths)
        flat = [p for p in flat if p and str(p).strip()]
        return flat, None if flat else None

    # Binary
    samples_list = list(config.test_control_paths) + list(config.test_disease_paths)
    n_control = len(config.test_control_paths)
    n_disease = len(config.test_disease_paths)
    expected_classes = [0] * n_control + [1] * n_disease
    return samples_list, expected_classes


def run_prediction(config: PredictorConfig) -> Dict[str, Any]:
    """
    Load MethylClassifier, run prediction on test samples (binary or multi-class),
    optionally compute metrics when labels are provided, write validation_metrics.json and predictions CSV.
    Returns the metrics dictionary (or empty/minimal dict for inference-only).
    """
    from methyl_classifier.core.classifier import MethylClassifier
    from methyl_classifier.models.config import ClassifierConfig
    from methyl_classifier.cli.main import classify_samples_from_list

    prediction_mode = _prepare_predictor_paths_and_mode(config)

    # Build classifier config and load model (merge step_config.classifier snapshot from project resolver)
    snap = getattr(config, "classifier_step_snapshot", None) or {}
    merge_keys = (
        "temperature",
        "enable_platt_calibration",
        "use_isotonic_calibration",
        "trimmed_percentile_low",
        "trimmed_percentile_high",
        "weight_method",
        "weight_fit_regularization",
        "weight_fit_alpha",
        "weight_fit_l1_ratio",
        "use_elasticnet_stacking",
        "chromosome_weights",
    )
    cc_kwargs: Dict[str, Any] = {
        "model_path": config.model_path,
        "model_dir": config.model_dir,
        "temperature": 1.0,
        "enable_platt_calibration": False,
        "trimmed_percentile_low": 0.10,
        "trimmed_percentile_high": 0.01,
        "use_isotonic_calibration": False,
    }
    for k in merge_keys:
        if k in snap and snap[k] is not None:
            cc_kwargs[k] = snap[k]
    classifier_config = ClassifierConfig(**cc_kwargs)
    classifier = MethylClassifier(classifier_config)

    n_classes = getattr(classifier, "n_classes", None) or 2
    class_names = getattr(classifier, "class_names", None) or [
        f"Class_{i}" for i in range(n_classes)
    ]
    is_multiclass = n_classes > 2
    if is_multiclass:
        print(f"Multi-class classifier ({n_classes} classes: {class_names})")
    if getattr(classifier, "_ovr_mode", False):
        n_sub = len(getattr(classifier, "_ovr_binary_classifiers", []) or [])
        _df = getattr(classifier, "dmp_positions_df", None)
        n_union = len(_df) if _df is not None else 0
        print(
            f"OvR ECDF: {n_sub} binary sub-model(s), {n_union} union DMPs — "
            "HDF5 is read only during the sample-loading phase."
        )

    samples_list, expected_classes = _build_samples_and_expected(
        config, n_classes, prediction_mode
    )
    if not samples_list:
        raise ValueError(
            "No test samples: set predictor.blind, or config.controls and config.diseases, "
            "or test_control_paths + test_disease_paths (binary), "
            "or test_group_paths (K-class / OvR, including K=2)."
        )

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions_csv = output_dir / "predictions.csv"

    # Run classification with same DMP-based loading as MethylClassifier (required_chromosomes +
    # dmp_positions_by_chrom so only classifier chromosomes and DMP positions are read from H5).
    required_chromosomes: Optional[List[str]] = None
    dmp_positions_by_chrom: Optional[Any] = None
    if classifier.is_multi_chromosome:
        required_chromosomes = list(classifier.classifiers.keys())
        dmp_positions_by_chrom = getattr(classifier, "dmp_positions_df", None)
        if dmp_positions_by_chrom is None or len(dmp_positions_by_chrom) == 0:
            dmp_positions_by_chrom = {}
            for chrom, clf in classifier.classifiers.items():
                fi = clf.get_feature_info()
                dmp_positions_by_chrom[chrom] = fi["positions"]
    else:
        # Single-file (single-chromosome or multiclass): prefer dmp_positions_df when present (multiclass with dmp_df)
        dmp_df = getattr(classifier, "dmp_positions_df", None)
        if dmp_df is not None and len(dmp_df) > 0 and hasattr(dmp_df, "columns") and "chromosome" in dmp_df.columns:
            required_chromosomes = sorted(dmp_df["chromosome"].astype(str).unique().tolist())
            dmp_positions_by_chrom = dmp_df
        elif getattr(classifier, "classifier", None) is not None:
            feature_info = classifier.get_feature_info()
            chrom = getattr(classifier, "chromosome", None) or feature_info.get("chromosome") or "unknown"
            if chrom == "unknown":
                chrom = "1"
            required_chromosomes = [chrom]
            dmp_positions_by_chrom = {chrom: feature_info["positions"]}
        else:
            required_chromosomes = None
            dmp_positions_by_chrom = None

    classify_samples_from_list(
        classifier=classifier,
        samples_list=samples_list,
        output_file=predictions_csv,
        debug=config.debug,
        required_chromosomes=required_chromosomes,
        positions=None,
        dmp_positions_by_chrom=dmp_positions_by_chrom,
        expected_classes=expected_classes,
        panel_spec=config.panel,
    )

    if not predictions_csv.exists():
        raise RuntimeError(f"Expected output CSV not found: {predictions_csv}")

    df = pd.read_csv(predictions_csv)
    if "prediction" not in df.columns:
        raise RuntimeError("predictions CSV must contain prediction column")

    metrics: Optional[Dict[str, Any]] = None
    # Metrics only when we have labels
    if expected_classes is not None and "expected_class" in df.columns:
        y_true = df["expected_class"].values.astype(int)
        y_pred = df["prediction"].values.astype(int)
        metrics = _compute_metrics(y_true, y_pred, n_classes, class_names)
        _warn_if_degenerate_predictions(y_pred, n_classes, class_names)
        cov_stats = _dmp_coverage_stats_from_predictions_df(df)
        if cov_stats:
            metrics["sample_dmp_coverage"] = cov_stats
        _print_metrics(metrics)
        metrics_path = output_dir / "validation_metrics.json"
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"\n💾 Metrics saved to {metrics_path}")
        print(f"💾 Predictions CSV: {predictions_csv}")
    else:
        print(f"\n💾 Predictions CSV: {predictions_csv} (no labels; metrics skipped)")
        if prediction_mode == "blind":
            _print_blind_summary(df, n_classes, class_names)

    report_path = output_dir / "prediction_report.json"
    report_body = _build_prediction_report(
        config, df, metrics, n_classes, class_names, prediction_mode
    )
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_body, f, indent=2)
    print(f"💾 Prediction report: {report_path}")

    if metrics is not None:
        return metrics
    return {"n_samples": len(df), "n_classes": n_classes, "class_names": class_names}
