"""
Core prediction: load MethylClassifier, run prediction on test sets, compute metrics, write JSON + CSV.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)

from ..models.config import PredictorConfig


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


def _build_samples_and_expected(
    config: PredictorConfig,
    n_classes: int,
) -> tuple[List[str], Optional[List[int]]]:
    """
    Build samples_list and expected_classes from config.
    Returns (samples_list, expected_classes). expected_classes is None for inference-only (no labels).
    """
    n_classes = n_classes or 2
    is_multiclass = n_classes > 2

    # Multi-class with labeled groups
    if is_multiclass and config.test_group_paths:
        samples_list: List[str] = []
        expected_classes: List[int] = []
        for i, entry in enumerate(config.test_group_paths):
            paths = entry.get("paths") or []
            paths = [p for p in paths if p and str(p).strip()]
            samples_list.extend(paths)
            expected_classes.extend([i] * len(paths))
        return samples_list, expected_classes if samples_list else None

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

    # Build classifier config and load model
    classifier_config = ClassifierConfig(
        model_path=config.model_path,
        model_dir=config.model_dir,
        temperature=1.0,
        enable_platt_calibration=False,
        trimmed_percentile_low=0.10,
        trimmed_percentile_high=0.01,
    )
    classifier = MethylClassifier(classifier_config)

    n_classes = getattr(classifier, "n_classes", None) or 2
    class_names = getattr(classifier, "class_names", None) or [
        f"Class_{i}" for i in range(n_classes)
    ]
    is_multiclass = n_classes > 2
    if is_multiclass:
        print(f"Multi-class classifier ({n_classes} classes: {class_names})")

    samples_list, expected_classes = _build_samples_and_expected(config, n_classes)
    if not samples_list:
        raise ValueError(
            "No test samples: provide test_control_paths + test_disease_paths (binary) "
            "or test_group_paths (multi-class)."
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
    )

    if not predictions_csv.exists():
        raise RuntimeError(f"Expected output CSV not found: {predictions_csv}")

    df = pd.read_csv(predictions_csv)
    if "prediction" not in df.columns:
        raise RuntimeError("predictions CSV must contain prediction column")

    # Metrics only when we have labels
    if expected_classes is not None and "expected_class" in df.columns:
        y_true = df["expected_class"].values.astype(int)
        y_pred = df["prediction"].values.astype(int)
        metrics = _compute_metrics(y_true, y_pred, n_classes, class_names)
        _print_metrics(metrics)
        metrics_path = output_dir / "validation_metrics.json"
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"\n💾 Metrics saved to {metrics_path}")
        print(f"💾 Predictions CSV: {predictions_csv}")
        return metrics
    # Inference-only: no validation_metrics.json
    print(f"\n💾 Predictions CSV: {predictions_csv} (no labels; metrics skipped)")
    return {"n_samples": len(df), "n_classes": n_classes, "class_names": class_names}
