"""RNA-Seq differential-expression gene panel selection + tabular classification.

This replaces the methylation centroid/detector/ECDF science for the RNA process pack:

1. Build a ``samples x genes`` log-CPM matrix for two groups.
2. Rank genes by Welch differential expression and keep a discriminatory panel.
3. Train a tabular sklearn classifier (optionally stacking covariates) and report
   cross-validated balanced accuracy.

The gene panel CSV mirrors the recurrence-friendly schema consumed by
``validation.stability`` (one row per selected feature keyed by ``gene_id``), so the
Monte Carlo stability aggregation counts gene recurrence across runs unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..models.config import RnaDeSelectConfig
from .matrix import load_expression_matrix

GENE_PANEL_FILENAME = "rna_de_panel.csv"
RESULTS_FILENAME = "rna_de_results.json"


def _welch_stats(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (t_stat, log2fc, mean_all) per column for groups a (control) and b (disease)."""
    from scipy import stats  # type: ignore

    mean_a = a.mean(axis=0)
    mean_b = b.mean(axis=0)
    log2fc = mean_b - mean_a  # inputs are already log2-CPM
    t_stat, _p = stats.ttest_ind(b, a, axis=0, equal_var=False, nan_policy="omit")
    t_stat = np.nan_to_num(np.asarray(t_stat, dtype=np.float64), nan=0.0)
    mean_all = np.vstack([a, b]).mean(axis=0)
    return t_stat, np.asarray(log2fc, dtype=np.float64), mean_all


def _welch_stats_numpy(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pure-numpy Welch t fallback when scipy is unavailable."""
    mean_a = a.mean(axis=0)
    mean_b = b.mean(axis=0)
    var_a = a.var(axis=0, ddof=1) if a.shape[0] > 1 else np.zeros(a.shape[1])
    var_b = b.var(axis=0, ddof=1) if b.shape[0] > 1 else np.zeros(b.shape[1])
    denom = np.sqrt(var_a / max(a.shape[0], 1) + var_b / max(b.shape[0], 1))
    denom[denom == 0] = np.inf
    t_stat = (mean_b - mean_a) / denom
    log2fc = mean_b - mean_a
    mean_all = np.vstack([a, b]).mean(axis=0)
    return np.nan_to_num(t_stat, nan=0.0), log2fc, mean_all


def select_de_genes(
    X: np.ndarray,
    y: np.ndarray,
    gene_ids: Sequence[str],
    *,
    config: RnaDeSelectConfig,
) -> pd.DataFrame:
    """Rank genes by differential expression and return the top-``max_genes`` panel."""
    y = np.asarray(y)
    control = X[y == 0]
    disease = X[y == 1]
    if control.shape[0] == 0 or disease.shape[0] == 0:
        raise ValueError("select_de_genes requires samples in both classes")

    try:
        t_stat, log2fc, mean_all = _welch_stats(control, disease)
    except Exception:
        t_stat, log2fc, mean_all = _welch_stats_numpy(control, disease)

    df = pd.DataFrame(
        {
            "gene_id": list(gene_ids),
            "t_stat": t_stat,
            "log2fc": log2fc,
            "mean_logcpm": mean_all,
        }
    )
    if config.min_mean_logcpm > 0:
        df = df[df["mean_logcpm"] >= config.min_mean_logcpm]

    if config.ranking == "signed_log2fc":
        df["score"] = df["log2fc"].abs()
    else:
        df["score"] = df["t_stat"].abs()
    df = df.sort_values("score", ascending=False).head(int(config.max_genes)).reset_index(drop=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1))
    return df


def _build_estimator(config: RnaDeSelectConfig):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression

    method = str(config.classifier_method).strip().lower()
    if method in ("random_forest", "rf"):
        return RandomForestClassifier(random_state=config.random_state)
    return LogisticRegression(max_iter=1000, random_state=config.random_state)


def _cross_validated_balanced_accuracy(
    X: np.ndarray, y: np.ndarray, config: RnaDeSelectConfig
) -> float:
    from sklearn.metrics import balanced_accuracy_score
    from sklearn.model_selection import StratifiedKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    y = np.asarray(y)
    n_min = int(np.min(np.bincount(y))) if len(y) else 0
    folds = max(2, min(int(config.cv_folds), n_min)) if n_min >= 2 else 0
    if folds < 2:
        return float("nan")
    skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=config.random_state)
    scores: List[float] = []
    for train_idx, test_idx in skf.split(X, y):
        model = make_pipeline(StandardScaler(), _build_estimator(config))
        model.fit(X[train_idx], y[train_idx])
        pred = model.predict(X[test_idx])
        scores.append(balanced_accuracy_score(y[test_idx], pred))
    return float(np.mean(scores)) if scores else float("nan")


def _stack_covariates(
    X: np.ndarray,
    sample_ids: Sequence[str],
    covariates_csv: Optional[str],
) -> np.ndarray:
    """Optionally append covariate columns (joined by sample_id) via methyl_validation."""
    if not covariates_csv:
        return X
    try:
        from methyl_validation.covariate_preprocessor import fit_covariates
    except Exception:
        return X
    path = Path(covariates_csv)
    if not path.is_file():
        return X
    try:
        cov_array, _preprocessor, _meta = fit_covariates(
            str(path),
            list(sample_ids),
            covariate_id_column="sample_id",
            strict_join=False,
        )
        if cov_array is None:
            return X
        cov = np.asarray(cov_array, dtype=np.float64)
        if cov.ndim == 2 and cov.shape[0] == X.shape[0] and cov.shape[1] > 0:
            return np.concatenate([X, cov], axis=1)
    except Exception:
        return X
    return X


def _resolve_two_groups(
    project_path: str, comparison: Optional[str]
) -> Tuple[str, List[str], str, List[str]]:
    """Resolve (control_label, control_dirs, disease_label, disease_dirs) from a project."""
    from methyl_utils import load_project

    project = load_project(project_path)
    groups = project.get_resolved_groups()
    if not groups:
        raise RuntimeError(f"project {project_path} resolved no groups")
    label_to_paths = {str(label): [str(p) for p in paths] for label, paths in groups}

    control_tokens = ("healthy", "control", "normal")
    labels = list(label_to_paths.keys())

    disease_label: Optional[str] = None
    control_label: Optional[str] = None
    if comparison and "_vs_" in comparison:
        left, _, right = comparison.partition("_vs_")
        if left in label_to_paths and right in label_to_paths:
            control_label, disease_label = left, right

    if control_label is None:
        for lab in labels:
            if any(tok in lab.lower() for tok in control_tokens):
                control_label = lab
                break
        if control_label is None:
            control_label = labels[0]
    if disease_label is None:
        remaining = [lab for lab in labels if lab != control_label]
        if comparison and comparison in label_to_paths and comparison != control_label:
            disease_label = comparison
        elif remaining:
            disease_label = remaining[0]
        else:
            raise RuntimeError("could not resolve a disease group distinct from control")

    return (
        control_label,
        label_to_paths[control_label],
        disease_label,
        label_to_paths[disease_label],
    )


def run_rna_de_select(
    *,
    project_path: str,
    output_dir: str | Path,
    comparison: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Select a DE gene panel and evaluate a tabular classifier for one comparison."""
    cfg = RnaDeSelectConfig.from_resolved(config)
    control_label, control_dirs, disease_label, disease_dirs = _resolve_two_groups(
        project_path, comparison
    )

    all_dirs = list(control_dirs) + list(disease_dirs)
    X, gene_ids, sample_ids = load_expression_matrix(all_dirs, transform=cfg.transform)
    y = np.asarray([0] * len(control_dirs) + [1] * len(disease_dirs))

    panel = select_de_genes(X, y, gene_ids, config=cfg)
    panel_genes = panel["gene_id"].tolist()
    col_index = {g: j for j, g in enumerate(gene_ids)}
    cols = [col_index[g] for g in panel_genes if g in col_index]
    X_panel = X[:, cols] if cols else X[:, :0]

    X_model = _stack_covariates(X_panel, sample_ids, cfg.covariates_csv)
    balanced_accuracy = _cross_validated_balanced_accuracy(X_model, y, cfg)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    panel_path = out_dir / GENE_PANEL_FILENAME
    panel.to_csv(panel_path, index=False)

    results = {
        "comparison": comparison or f"{control_label}_vs_{disease_label}",
        "control_label": control_label,
        "disease_label": disease_label,
        "n_control": len(control_dirs),
        "n_disease": len(disease_dirs),
        "n_genes_selected": int(len(panel)),
        "balanced_accuracy": balanced_accuracy,
        "gene_panel_csv": str(panel_path),
        "feature_mode": "rna_expression",
    }
    (out_dir / RESULTS_FILENAME).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results
