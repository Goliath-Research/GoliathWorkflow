"""
Stability analysis across Monte Carlo runs.

Counts DMPs in detector discovery exports per iteration; optionally restricts
to iterations with ``balanced_accuracy`` above a threshold (from detector
validation or, when present, predictor metrics). Gene stability is computed
only when enricher outputs exist (e.g. after ``--freeze``, not during MC).
"""

from __future__ import annotations

import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from methyl_utils import load_project
from methyl_utils.logging_utils import setup_module_logging
from scipy.stats import norm

logger = setup_module_logging(__name__)

if TYPE_CHECKING:
    from .config import MonteCarloConfig


def find_validation_metrics_json(run_dir: Path) -> Optional[Path]:
    """Locate validation_metrics.json under run_dir/predictors (binary nested or flat)."""
    predictors = run_dir / "predictors"
    if not predictors.is_dir():
        for p in run_dir.glob("**/predictors"):
            if p.is_dir():
                predictors = p
                break
        else:
            return None
    for path in predictors.rglob("validation_metrics.json"):
        return path
    return None


def run_balanced_accuracy(run_dir: Path) -> Optional[float]:
    """
    Return balanced_accuracy for this run: prefer MethylPredictor validation_metrics.json,
    else mean balanced_accuracy from MethylDetector result*.json under detections/.
    """
    from .validator_metrics import iteration_scalar_metrics_from_run_dir

    row = iteration_scalar_metrics_from_run_dir(run_dir)
    ba = row.get("balanced_accuracy")
    if ba is None:
        bas: List[float] = []
        for path in _detector_results_files_for_run(run_dir):
            try:
                with open(path, encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception:
                continue
            # New nested format: optimization_validation.performance.balanced_accuracy
            opt = payload.get("optimization_validation")
            if isinstance(opt, dict):
                perf = opt.get("performance")
                if isinstance(perf, dict):
                    v = perf.get("balanced_accuracy")
                    if isinstance(v, (int, float)):
                        bas.append(float(v))
                        continue
            # Legacy/top-level fallback
            v = payload.get("balanced_accuracy")
            if isinstance(v, (int, float)):
                bas.append(float(v))
        if bas:
            return float(sum(bas) / len(bas))
        return None
    try:
        return float(ba)
    except (TypeError, ValueError):
        return None


def load_discovery_dmps(run_dir: Path, prefer_classifier_panel: bool = False) -> Optional[pd.DataFrame]:
    """Load and concatenate detector DMP exports from a MC run directory.

    Searches all detection subdirectories so that multi-chromosome runs are
    correctly aggregated into a single DataFrame before stability counting.

    When ``prefer_classifier_panel`` is true, the function prefers classifier
    exports (``dmps-*-classifier.csv`` / ``dmps-*.csv``) and falls back to
    discovery exports.
    """
    detection_dirs = list(run_dir.glob("**/detections/*/*"))
    if not detection_dirs:
        detection_dirs = list(run_dir.glob("detections/*/*"))
    frames: list = []
    for d in detection_dirs:
        patterns: List[str]
        if prefer_classifier_panel:
            patterns = ["dmps-*-classifier.csv", "dmps-*.csv", "dmps-*-discovery.csv"]
        else:
            patterns = ["dmps-*-discovery.csv"]
        found_local = False
        for pat in patterns:
            for csv in sorted(d.glob(pat)):
                try:
                    frames.append(pd.read_csv(csv))
                    found_local = True
                except Exception:
                    continue
            if found_local:
                break
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def load_enricher_genes(run_dir: Path) -> Optional[pd.DataFrame]:
    """Load enricher gene output (all-gene_name-combined.csv or similar)."""
    enricher_dirs = list(run_dir.glob("**/enricher/*/*")) or list(run_dir.glob("enricher/*/*"))
    for d in enricher_dirs:
        for csv in d.glob("*gene*.csv"):
            try:
                df = pd.read_csv(csv)
                if "gene_name" in df.columns:
                    return df
            except Exception:
                continue
    return None


def _numeric_summary(values: List[float]) -> Dict[str, Any]:
    """Compact numeric summary helper."""
    if not values:
        return {}
    vals = [float(v) for v in values]
    return {
        "count": int(len(vals)),
        "mean": float(sum(vals) / len(vals)),
        "min": float(min(vals)),
        "max": float(max(vals)),
    }


def _consistent_value(values: List[Any]) -> tuple[Optional[Any], bool]:
    """
    Return a value only when all non-null entries are identical.

    Returns (value, is_consistent). If no usable values exist, returns (None, True).
    """
    clean = [v for v in values if v is not None]
    if not clean:
        return None, True
    first = clean[0]
    if all(v == first for v in clean[1:]):
        return first, True
    return None, False


def _detector_results_files_for_run(run_dir: Path) -> List[Path]:
    """Locate detector run summary files under run_dir detections."""
    result_files: List[Path] = []
    detections_roots = [p for p in run_dir.rglob("detections") if p.is_dir()]
    for det_root in detections_roots:
        result_files.extend(sorted(det_root.rglob("results-*.json")))
    return result_files


def extract_detector_parameters_for_run(run_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Extract minimal detector/filter parameters from one MC run.

    Uses detector ``results-*.json`` files (typically one per chromosome).
    """
    result_files = _detector_results_files_for_run(run_dir)
    if not result_files:
        return None

    n_dmps_exported_vals: List[float] = []
    total_statistical_dmps_vals: List[float] = []
    total_biological_dmps_vals: List[float] = []
    effect_size_coverage_vals: List[Any] = []
    delta_mean_reduction_vals: List[Any] = []
    classifier_dmp_selection_vals: List[Any] = []
    dynamic_dmp_cutoff_enabled_vals: List[Any] = []

    for path in result_files:
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            continue

        if isinstance(payload.get("n_dmps_exported"), (int, float)):
            n_dmps_exported_vals.append(float(payload["n_dmps_exported"]))
        if isinstance(payload.get("total_statistical_dmps"), (int, float)):
            total_statistical_dmps_vals.append(float(payload["total_statistical_dmps"]))
        if isinstance(payload.get("total_biological_dmps"), (int, float)):
            total_biological_dmps_vals.append(float(payload["total_biological_dmps"]))

        cfg = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        effect_size_coverage_vals.append(cfg.get("effect_size_coverage"))
        delta_mean_reduction_vals.append(cfg.get("delta_mean_reduction"))
        classifier_dmp_selection_vals.append(cfg.get("classifier_dmp_selection"))
        dynamic_dmp_cutoff_enabled_vals.append(cfg.get("dynamic_dmp_cutoff_enabled"))

    if not (
        n_dmps_exported_vals
        or total_statistical_dmps_vals
        or total_biological_dmps_vals
        or any(v is not None for v in effect_size_coverage_vals)
        or any(v is not None for v in delta_mean_reduction_vals)
        or any(v is not None for v in classifier_dmp_selection_vals)
        or any(v is not None for v in dynamic_dmp_cutoff_enabled_vals)
    ):
        return None

    effect_size_coverage, esc_ok = _consistent_value(effect_size_coverage_vals)
    delta_mean_reduction, dmr_ok = _consistent_value(delta_mean_reduction_vals)
    classifier_dmp_selection, cds_ok = _consistent_value(classifier_dmp_selection_vals)
    dynamic_dmp_cutoff_enabled, ddc_ok = _consistent_value(dynamic_dmp_cutoff_enabled_vals)

    inconsistent_fields: List[str] = []
    if not esc_ok:
        inconsistent_fields.append("effect_size_coverage")
    if not dmr_ok:
        inconsistent_fields.append("delta_mean_reduction")
    if not cds_ok:
        inconsistent_fields.append("classifier_dmp_selection")
    if not ddc_ok:
        inconsistent_fields.append("dynamic_dmp_cutoff_enabled")

    return {
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "n_result_files": int(len(result_files)),
        "n_dmps_exported": _numeric_summary(n_dmps_exported_vals),
        "total_statistical_dmps": _numeric_summary(total_statistical_dmps_vals),
        "total_biological_dmps": _numeric_summary(total_biological_dmps_vals),
        "effect_size_coverage": effect_size_coverage,
        "delta_mean_reduction": delta_mean_reduction,
        "classifier_dmp_selection": classifier_dmp_selection,
        "dynamic_dmp_cutoff_enabled": dynamic_dmp_cutoff_enabled,
        "inconsistent_fields": inconsistent_fields,
    }


def compute_detector_parameter_stability(monte_carlo_runs_root: Path) -> Dict[str, Any]:
    """Aggregate minimal detector/filter parameter summaries across Monte Carlo runs."""
    runs = sorted(monte_carlo_runs_root.glob("run_*"))
    per_run: List[Dict[str, Any]] = []
    n_runs_without_results = 0

    for run_dir in runs:
        row = extract_detector_parameters_for_run(run_dir)
        if row is None:
            n_runs_without_results += 1
            continue
        per_run.append(row)

    if not per_run:
        return {
            "per_run": [],
            "aggregates": {
                "n_runs_with_results": 0,
                "n_runs_without_results": n_runs_without_results,
            },
        }

    numeric_values: Dict[str, List[float]] = defaultdict(list)
    categorical_values: Dict[str, Counter] = defaultdict(Counter)
    numeric_scalar_keys = [
        "n_result_files",
        "effect_size_coverage",
        "delta_mean_reduction",
    ]
    categorical_keys = [
        "classifier_dmp_selection",
        "dynamic_dmp_cutoff_enabled",
    ]
    nested_numeric_keys = [
        "n_dmps_exported",
        "total_statistical_dmps",
        "total_biological_dmps",
    ]

    for row in per_run:
        for key in numeric_scalar_keys:
            val = row.get(key)
            if isinstance(val, (int, float)):
                numeric_values[key].append(float(val))
        for key in categorical_keys:
            val = row.get(key)
            if val is not None:
                categorical_values[key][str(val)] += 1
        for key in nested_numeric_keys:
            node = row.get(key)
            if isinstance(node, dict):
                for suffix in ("mean", "min", "max"):
                    val = node.get(suffix)
                    if isinstance(val, (int, float)):
                        numeric_values[f"{key}_{suffix}"].append(float(val))

    aggregates = {
        "n_runs_with_results": int(len(per_run)),
        "n_runs_without_results": int(n_runs_without_results),
        "numeric": {
            key: _numeric_summary(vals)
            for key, vals in numeric_values.items()
            if vals
        },
        "categorical": {
            key: dict(counter)
            for key, counter in categorical_values.items()
            if counter
        },
    }
    return {"per_run": per_run, "aggregates": aggregates}


def _dmp_key_from_row(row: Any) -> Tuple[Any, int]:
    chrom = row["chromosome"]
    try:
        chrom_n = int(chrom)
    except (TypeError, ValueError):
        chrom_n = str(chrom).strip()
    return (chrom_n, int(row["position"]))


def _bh_qvalues(pvals: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg q-values for finite p-values in [0,1]."""
    n = int(len(pvals))
    if n == 0:
        return np.array([], dtype=float)
    order = np.argsort(pvals)
    ranked = pvals[order]
    q = np.empty(n, dtype=float)
    prev = 1.0
    for i in range(n - 1, -1, -1):
        rank = i + 1
        val = float(ranked[i] * n / rank)
        prev = min(prev, val)
        q[i] = prev
    out = np.empty(n, dtype=float)
    out[order] = np.clip(q, 0.0, 1.0)
    return out


def _signed_stouffer(pvals: np.ndarray, signs: np.ndarray, weights: np.ndarray) -> float:
    """Return two-sided p-value from signed weighted Stouffer aggregation."""
    if pvals.size == 0:
        return float("nan")
    pvals = np.clip(pvals.astype(float), 1e-300, 1.0 - 1e-16)
    z = norm.ppf(1.0 - pvals / 2.0) * signs.astype(float)
    w = weights.astype(float)
    valid = np.isfinite(z) & np.isfinite(w) & (w > 0)
    if not np.any(valid):
        return float("nan")
    z = z[valid]
    w = w[valid]
    denom = np.sqrt(np.sum(w ** 2))
    if not np.isfinite(denom) or denom <= 0:
        return float("nan")
    z_combined = float(np.sum(w * z) / denom)
    p = float(2.0 * (1.0 - norm.cdf(abs(z_combined))))
    return float(np.clip(p, 0.0, 1.0))


def _frequency_count_distribution(
    dmp_freq_df: pd.DataFrame,
    chromosome: Any,
) -> pd.DataFrame:
    """
    Frequency histogram for one chromosome with count-based Y axis.

    Returns columns: frequency_pct, dmps_count.
    """
    subset = dmp_freq_df[dmp_freq_df["chromosome"].astype(str) == str(chromosome)].copy()
    if subset.empty:
        return pd.DataFrame(columns=["frequency_pct", "dmps_count"])
    dist = (
        subset["frequency"]
        .dropna()
        .astype(float)
        .value_counts()
        .sort_index()
        .reset_index()
    )
    if dist.empty:
        return pd.DataFrame(columns=["frequency_pct", "dmps_count"])
    dist.columns = ["frequency", "dmps_count"]
    dist["frequency_pct"] = dist["frequency"] * 100.0
    return dist[["frequency_pct", "dmps_count"]]


def _select_stable_dmps_df(
    dmp_freq_df: pd.DataFrame,
    min_frequency: float = 0.7,
    top_n: Optional[int] = None,
) -> pd.DataFrame:
    """Build selected stable DMP table from full frequency table."""
    if dmp_freq_df is None or dmp_freq_df.empty or "frequency" not in dmp_freq_df.columns:
        return pd.DataFrame(
            columns=[
                "chromosome",
                "position",
                "frequency",
                "count",
                "n_runs",
                "effect_size",
                "p_value",
                "q_value",
            ]
        )
    selected = dmp_freq_df[dmp_freq_df["frequency"] >= min_frequency].copy()
    if top_n is not None and len(selected) > top_n:
        selected = selected.head(top_n)
    for col in ("chromosome", "position", "frequency", "count", "n_runs", "effect_size", "p_value", "q_value"):
        if col not in selected.columns:
            selected[col] = pd.Series(
                dtype="float64" if col in {"frequency", "effect_size", "p_value", "q_value"} else "object"
            )
    return selected


def _score_stable_dmps(
    selected_df: pd.DataFrame,
    score_eps: float = 1e-12,
) -> pd.DataFrame:
    """Score stable DMPs using effect_size * sqrt(frequency) and return sorted table."""
    if selected_df is None or selected_df.empty:
        out = selected_df.copy() if selected_df is not None else pd.DataFrame()
        if "combined_score" not in out.columns:
            out["combined_score"] = pd.Series(dtype="float64")
        return out

    out = selected_df.copy()
    freq = pd.to_numeric(out.get("frequency"), errors="coerce").clip(lower=0.0).fillna(0.0)
    effect = pd.to_numeric(out.get("effect_size"), errors="coerce").fillna(0.0)
    effect = effect.where(np.isfinite(effect), 0.0)
    effect = effect.clip(lower=0.0)
    out["combined_score"] = effect * np.sqrt(freq)
    out["combined_score"] = pd.to_numeric(out["combined_score"], errors="coerce").fillna(0.0)
    out["log_combined_score"] = np.log(out["combined_score"] + float(score_eps))
    out = out.sort_values(
        ["combined_score", "frequency", "effect_size"],
        ascending=[False, False, False],
        na_position="last",
    ).reset_index(drop=True)
    return out


def _detect_log_score_elbow(
    sorted_scores: pd.Series,
    score_eps: float = 1e-12,
) -> tuple[int, float]:
    """Detect a robust elbow for descending scores using log-scale distance-to-line."""
    scores = pd.to_numeric(sorted_scores, errors="coerce").fillna(0.0).astype(float).to_numpy()
    n = int(len(scores))
    if n == 0:
        return 0, 0.0
    if n == 1:
        return 0, float(scores[0])

    log_scores = np.log(np.clip(scores, 0.0, None) + float(score_eps))
    if not np.isfinite(log_scores).any() or n <= 2:
        idx = int(max(0, n - 1))
        return idx, float(scores[idx])

    x = np.linspace(0.0, 1.0, n, dtype=float)
    y = log_scores
    y_min = float(np.nanmin(y))
    y_max = float(np.nanmax(y))
    if not np.isfinite(y_min) or not np.isfinite(y_max) or np.isclose(y_max, y_min):
        idx = int(max(0, n - 1))
        return idx, float(scores[idx])
    y_norm = (y - y_min) / (y_max - y_min)

    x0, y0 = x[0], y_norm[0]
    x1, y1 = x[-1], y_norm[-1]
    denom = float(np.hypot(y1 - y0, x1 - x0))
    if denom <= 0.0 or not np.isfinite(denom):
        idx = int(max(0, n - 1))
        return idx, float(scores[idx])

    # Perpendicular distance from each point to endpoint line.
    distances = np.abs((y1 - y0) * x - (x1 - x0) * y_norm + x1 * y0 - y1 * x0) / denom
    if n > 2:
        distances[0] = -1.0
        distances[-1] = -1.0
    idx = int(np.argmax(distances))
    if idx < 0 or idx >= n:
        idx = int(max(0, n - 1))
    return idx, float(scores[idx])


def _select_dual_cutoff_dmps(
    dmp_freq_df: pd.DataFrame,
    min_frequency: float = 0.7,
    top_n: Optional[int] = None,
    relaxed_cutoff_mode: str = "elbow_log_score",
    relaxed_multiplier: float = 0.5,
    score_eps: float = 1e-12,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Select strict and relaxed stable DMP sets from a frequency table."""
    selected = _select_stable_dmps_df(dmp_freq_df, min_frequency=min_frequency, top_n=None)
    scored = _score_stable_dmps(selected, score_eps=score_eps)
    if scored.empty:
        return selected.copy(), selected.copy(), scored, {
            "enabled": True,
            "strict_cutoff_mode": "elbow_log_score",
            "relaxed_cutoff_mode": relaxed_cutoff_mode,
            "strict_cutoff_index": 0,
            "strict_cutoff_score": 0.0,
            "relaxed_cutoff_index": 0,
            "relaxed_cutoff_score": 0.0,
            "min_frequency": float(min_frequency),
            "n_candidates_after_min_frequency": 0,
            "n_strict_selected": 0,
            "n_relaxed_selected": 0,
            "relaxed_multiplier": float(relaxed_multiplier),
        }

    strict_idx, strict_score = _detect_log_score_elbow(
        scored["combined_score"], score_eps=score_eps
    )
    strict = scored.iloc[: strict_idx + 1].copy()

    relaxed_mode = str(relaxed_cutoff_mode).strip().lower()
    relaxed_idx = strict_idx
    relaxed_score = strict_score
    if relaxed_mode == "strict_multiplier":
        mult = float(relaxed_multiplier)
        if mult <= 0:
            mult = 1.0
        relaxed_score = float(strict_score * mult)
        relaxed = scored[scored["combined_score"] >= relaxed_score].copy()
        if relaxed.empty:
            relaxed = strict.copy()
    else:
        tail = scored.iloc[strict_idx:].reset_index(drop=True)
        tail_idx, tail_score = _detect_log_score_elbow(
            tail["combined_score"], score_eps=score_eps
        )
        relaxed_idx = int(strict_idx + tail_idx)
        relaxed_score = float(tail_score)
        if relaxed_score > strict_score:
            relaxed_score = strict_score
            relaxed_idx = strict_idx
        relaxed = scored.iloc[: relaxed_idx + 1].copy()

    # Guarantee strict subset semantics.
    if len(relaxed) < len(strict):
        relaxed = strict.copy()
        relaxed_idx = strict_idx
        relaxed_score = strict_score

    if top_n is not None:
        strict = strict.head(top_n).copy()
        relaxed = relaxed.head(top_n).copy()

    diagnostics = {
        "enabled": True,
        "strict_cutoff_mode": "elbow_log_score",
        "relaxed_cutoff_mode": relaxed_mode,
        "strict_cutoff_index": int(strict_idx),
        "strict_cutoff_score": float(strict_score),
        "relaxed_cutoff_index": int(relaxed_idx),
        "relaxed_cutoff_score": float(relaxed_score),
        "min_frequency": float(min_frequency),
        "n_candidates_after_min_frequency": int(len(scored)),
        "n_strict_selected": int(len(strict)),
        "n_relaxed_selected": int(len(relaxed)),
        "relaxed_multiplier": float(relaxed_multiplier),
    }
    return strict, relaxed, scored, diagnostics


def write_dmp_frequency_plot_by_chromosome(
    dmp_freq_df: pd.DataFrame,
    selected_dmp_df: pd.DataFrame,
    output_dir: Path,
) -> tuple[Optional[Path], Dict[str, str], Dict[str, Dict[str, int]]]:
    """
    Write Plotly frequency charts with one series per chromosome and all-vs-selected traces.

    Returns:
      - combined chart path
      - per chromosome chart paths
      - count summaries by chromosome
    """
    if dmp_freq_df.empty or "frequency" not in dmp_freq_df.columns:
        return None, {}, {}
    try:
        import plotly.graph_objects as go
    except Exception as e:
        logger.warning(f"Plotly not available; skipping DMP frequency chart: {e}")
        return None, {}, {}

    if "chromosome" not in dmp_freq_df.columns:
        return None, {}, {}

    output_dir.mkdir(parents=True, exist_ok=True)
    chromosomes = [str(c) for c in sorted(dmp_freq_df["chromosome"].dropna().unique(), key=str)]
    if not chromosomes:
        return None, {}, {}

    combined = go.Figure()
    # 25 colors: 24 chromosome series + selected marker
    palette_25 = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b",
        "#e377c2", "#7f7f7f", "#bcbd22", "#17becf", "#393b79", "#637939",
        "#8c6d31", "#843c39", "#7b4173", "#3182bd", "#31a354", "#756bb1",
        "#636363", "#e6550d", "#969696", "#6baed6", "#fd8d3c", "#74c476",
        "#000000", "#e41a1c",
    ]
    selected_color = palette_25[24]

    per_chrom_paths: Dict[str, str] = {}
    count_summary_by_chrom: Dict[str, Dict[str, int]] = {}
    selected_points_x: List[float] = []
    selected_points_y: List[float] = []
    selected_points_text: List[str] = []

    for i, chrom in enumerate(chromosomes):
        all_dist = _frequency_count_distribution(dmp_freq_df, chrom)
        sel_dist = _frequency_count_distribution(selected_dmp_df, chrom)
        if all_dist.empty:
            continue

        # Combined chart traces
        combined.add_trace(
            go.Scatter(
                x=all_dist["frequency_pct"],
                y=all_dist["dmps_count"],
                mode="lines+markers",
                name=f"chr{chrom}",
                line={"color": palette_25[i % 24]},
                marker={"color": palette_25[i % 24]},
                hovertemplate=f"chr{chrom} all<br>Frequency: %{{x:.2f}}%<br>DMPs: %{{y:.0f}}<extra></extra>",
            )
        )
        selected_threshold = None
        if not sel_dist.empty:
            # Selection point: left-most selected frequency on X axis
            selected_threshold = float(sel_dist["frequency_pct"].min())
            selected_points_x.append(selected_threshold)
            selected_points_y.append(0.0)
            selected_points_text.append(f"chr{chrom} selected@{selected_threshold:.2f}%")

        # Per chromosome chart with all-vs-selected
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=all_dist["frequency_pct"],
                y=all_dist["dmps_count"],
                mode="lines+markers",
                name="all",
                hovertemplate="All DMPs<br>Frequency: %{x:.2f}%<br>DMPs: %{y:.0f}<extra></extra>",
            )
        )
        if selected_threshold is not None:
            fig.add_trace(
                go.Scatter(
                    x=[selected_threshold],
                    y=[0.0],
                    mode="markers",
                    marker={"size": 10, "symbol": "circle", "color": selected_color},
                    name="selected",
                    hovertemplate="Selected threshold<br>Frequency: %{x:.2f}%<extra></extra>",
                )
            )
            fig.add_vline(
                x=selected_threshold,
                line_dash="dot",
                annotation_text=f"Selected ≈ {selected_threshold:.2f}%",
                annotation_position="top left",
            )

        fig.update_layout(
            title=f"DMP Frequency Distribution (chr{chrom})",
            xaxis_title="Frequency across runs (%)",
            yaxis_title="DMP count",
            template="plotly_white",
        )
        chrom_path = output_dir / f"dmp_frequency_chr_{chrom}.html"
        fig.write_html(str(chrom_path), include_plotlyjs="cdn", full_html=True)
        per_chrom_paths[str(chrom)] = str(chrom_path)

        all_total = int(
            len(dmp_freq_df[dmp_freq_df["chromosome"].astype(str) == str(chrom)])
        )
        sel_total = int(
            len(selected_dmp_df[selected_dmp_df["chromosome"].astype(str) == str(chrom)])
        )
        count_summary_by_chrom[str(chrom)] = {
            "all_dmps": all_total,
            "selected_dmps": sel_total,
        }

    if not per_chrom_paths:
        return None, {}, {}

    if selected_points_x:
        combined.add_trace(
            go.Scatter(
                x=selected_points_x,
                y=selected_points_y,
                mode="markers",
                marker={"size": 9, "symbol": "circle", "color": selected_color},
                name="selected",
                text=selected_points_text,
                hovertemplate="%{text}<extra></extra>",
            )
        )

    combined.update_layout(
        title="DMP Frequency Distribution by Chromosome",
        xaxis_title="Frequency across runs (%)",
        yaxis_title="DMP count",
        template="plotly_white",
    )
    combined_path = output_dir / "dmp_frequency_by_chromosome.html"
    combined.write_html(str(combined_path), include_plotlyjs="cdn", full_html=True)
    return combined_path, per_chrom_paths, count_summary_by_chrom


def compute_dmp_stability(
    monte_carlo_runs_root: Path,
    min_frequency: float = 0.7,
    min_balanced_accuracy: Optional[float] = None,
    prefer_classifier_panel_dmps: bool = False,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Count how often each DMP appears in detector exports across runs.

    If ``min_balanced_accuracy`` is set, only iterations whose ``validation_metrics.json``
    reports ``balanced_accuracy >= min_balanced_accuracy`` contribute DMPs and define the
    frequency denominator.
    """
    runs = sorted(monte_carlo_runs_root.glob("run_*"))
    if not runs:
        runs = sorted(monte_carlo_runs_root.glob("run_0*"))

    dmp_counts: Dict[Tuple[Any, int], int] = defaultdict(int)
    dmp_effect_sum: Dict[Tuple[Any, int], float] = defaultdict(float)
    dmp_effect_runs: Dict[Tuple[Any, int], int] = defaultdict(int)
    dmp_run_pvals: Dict[Tuple[Any, int], List[float]] = defaultdict(list)
    dmp_run_signs: Dict[Tuple[Any, int], List[float]] = defaultdict(list)
    dmp_run_weights: Dict[Tuple[Any, int], List[float]] = defaultdict(list)
    run_count = 0
    skipped_no_discovery = 0
    skipped_low_ba = 0

    for run_dir in runs:
        df = load_discovery_dmps(run_dir, prefer_classifier_panel=prefer_classifier_panel_dmps)
        if df is None or "position" not in df.columns or "chromosome" not in df.columns:
            skipped_no_discovery += 1
            continue
        if min_balanced_accuracy is not None:
            ba = run_balanced_accuracy(run_dir)
            if ba is None or ba < float(min_balanced_accuracy):
                skipped_low_ba += 1
                continue
        run_count += 1
        seen_keys: set[Tuple[Any, int]] = set()
        for _, row in df.iterrows():
            try:
                key = _dmp_key_from_row(row)
            except Exception:
                continue
            seen_keys.add(key)
        for key in seen_keys:
            dmp_counts[key] += 1

        # Compute one effect-size value per DMP key per run (mean over run duplicates),
        # then average those values across runs where the DMP is present.
        run_effect_values: Dict[Tuple[Any, int], List[float]] = defaultdict(list)
        run_p_values: Dict[Tuple[Any, int], List[float]] = defaultdict(list)
        run_delta_values: Dict[Tuple[Any, int], List[float]] = defaultdict(list)
        for _, row in df.iterrows():
            try:
                key = _dmp_key_from_row(row)
            except Exception:
                continue
            effect_val = pd.to_numeric(row.get("effect_size"), errors="coerce")
            if pd.notna(effect_val):
                run_effect_values[key].append(float(effect_val))
            p_val = pd.to_numeric(row.get("p_value"), errors="coerce")
            if pd.notna(p_val) and np.isfinite(p_val):
                run_p_values[key].append(float(p_val))
            delta_val = pd.to_numeric(row.get("delta_mean"), errors="coerce")
            if pd.notna(delta_val):
                run_delta_values[key].append(float(delta_val))

        for key, vals in run_effect_values.items():
            if not vals:
                continue
            dmp_effect_sum[key] += float(sum(vals) / len(vals))
            dmp_effect_runs[key] += 1

        # Per-run collapse -> one p-value and one signed direction per key.
        for key in seen_keys:
            pvals = run_p_values.get(key, [])
            if pvals:
                p_run = float(np.median(np.asarray(pvals, dtype=float)))
            else:
                p_run = float("nan")
            deltas = run_delta_values.get(key, [])
            if deltas:
                direction = float(np.sign(np.mean(np.asarray(deltas, dtype=float))))
            else:
                direction = 1.0
            if not np.isfinite(direction) or direction == 0.0:
                direction = 1.0
            if np.isfinite(p_run):
                dmp_run_pvals[key].append(p_run)
                dmp_run_signs[key].append(direction)
                dmp_run_weights[key].append(1.0)

    if run_count == 0:
        return pd.DataFrame(), {
            "n_runs_analyzed": 0,
            "skipped_no_discovery": skipped_no_discovery,
            "skipped_low_balanced_accuracy": skipped_low_ba,
            "min_balanced_accuracy": min_balanced_accuracy,
        }

    data = []
    for (chrom, pos), count in dmp_counts.items():
        freq = count / run_count
        effect_runs = int(dmp_effect_runs.get((chrom, pos), 0))
        effect_size = (
            float(dmp_effect_sum[(chrom, pos)] / effect_runs)
            if effect_runs > 0
            else float("nan")
        )
        pvals = np.asarray(dmp_run_pvals.get((chrom, pos), []), dtype=float)
        signs = np.asarray(dmp_run_signs.get((chrom, pos), []), dtype=float)
        weights = np.asarray(dmp_run_weights.get((chrom, pos), []), dtype=float)
        dmp_p = _signed_stouffer(pvals, signs, weights)
        data.append({
            "chromosome": chrom,
            "position": pos,
            "frequency": freq,
            "count": count,
            "n_runs": run_count,
            "effect_size": effect_size,
            "p_value": dmp_p,
        })

    df = pd.DataFrame(data)
    if not df.empty:
        pvals = pd.to_numeric(df.get("p_value"), errors="coerce")
        finite_mask = pvals.notna().to_numpy()
        qvals = np.full(len(df), np.nan, dtype=float)
        if finite_mask.any():
            qvals[finite_mask] = _bh_qvalues(pvals.to_numpy(dtype=float)[finite_mask])
        df["q_value"] = qvals
        df = df.sort_values(
            ["frequency", "effect_size"],
            ascending=[False, False],
            na_position="last",
        )

    stable = df[df["frequency"] >= min_frequency] if not df.empty else pd.DataFrame()
    summary = {
        "n_runs_analyzed": run_count,
        "skipped_no_discovery": skipped_no_discovery,
        "skipped_low_balanced_accuracy": skipped_low_ba,
        "min_balanced_accuracy": min_balanced_accuracy,
        "total_unique_dmps": len(dmp_counts),
        "stable_dmps_at_threshold": len(stable),
        "min_frequency": min_frequency,
        "stable_dmp_fraction": len(stable) / len(dmp_counts) if len(dmp_counts) > 0 else 0.0,
    }

    return df, summary


def compute_gene_stability(
    monte_carlo_runs_root: Path, min_frequency: float = 0.5
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Count gene appearance frequency from enricher outputs."""
    runs = sorted(monte_carlo_runs_root.glob("run_*"))
    gene_counts: Counter = Counter()
    run_count = 0

    for run_dir in runs:
        df = load_enricher_genes(run_dir)
        if df is None or "gene_name" not in df.columns:
            continue
        run_count += 1
        for gene in df["gene_name"].dropna().astype(str):
            gene_counts[gene.strip()] += 1

    if run_count == 0:
        return pd.DataFrame(), {}

    data = []
    for gene, count in gene_counts.items():
        freq = count / run_count
        data.append({"gene_name": gene, "frequency": freq, "count": count, "n_runs": run_count})

    df = pd.DataFrame(data).sort_values("frequency", ascending=False)

    stable = df[df["frequency"] >= min_frequency] if not df.empty else pd.DataFrame()
    summary = {
        "n_runs_analyzed": run_count,
        "total_unique_genes": len(gene_counts),
        "stable_genes_at_threshold": len(stable),
        "min_frequency": min_frequency,
    }

    return df, summary


def write_stable_panel(
    dmp_freq_df: pd.DataFrame,
    output_dir: Path,
    min_frequency: float = 0.7,
    top_n: Optional[int] = None,
) -> Path:
    """Write stable DMPs as a production classifier panel."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stable = _select_stable_dmps_df(dmp_freq_df, min_frequency=min_frequency, top_n=top_n)
    for col in ("effect_size", "p_value", "q_value"):
        if col not in stable.columns:
            stable[col] = pd.Series(dtype="float64")

    out_path = output_dir / "stable_dmps_production.csv"
    stable.to_csv(out_path, index=False)
    return out_path


def write_stable_dual_panels(
    dmp_freq_df: pd.DataFrame,
    output_dir: Path,
    min_frequency: float = 0.7,
    top_n: Optional[int] = None,
    relaxed_cutoff_mode: str = "elbow_log_score",
    relaxed_multiplier: float = 0.5,
    score_eps: float = 1e-12,
) -> Dict[str, Any]:
    """Write strict and relaxed stability panels plus scoring diagnostics."""
    output_dir.mkdir(parents=True, exist_ok=True)
    strict, relaxed, scored, diagnostics = _select_dual_cutoff_dmps(
        dmp_freq_df=dmp_freq_df,
        min_frequency=min_frequency,
        top_n=top_n,
        relaxed_cutoff_mode=relaxed_cutoff_mode,
        relaxed_multiplier=relaxed_multiplier,
        score_eps=score_eps,
    )

    strict_path = output_dir / "stable_dmps_strict.csv"
    relaxed_path = output_dir / "stable_dmps_relaxed.csv"
    production_path = output_dir / "stable_dmps_production.csv"
    diagnostics_json_path = output_dir / "stable_dmps_score_diagnostics.json"
    diagnostics_csv_path = output_dir / "stable_dmps_score_diagnostics.csv"
    ranking_path = output_dir / "stable_dmps_scored.csv"

    strict.to_csv(strict_path, index=False)
    relaxed.to_csv(relaxed_path, index=False)
    # Backward-compatible production panel: strict by default.
    strict.to_csv(production_path, index=False)
    scored.to_csv(ranking_path, index=False)
    with open(diagnostics_json_path, "w", encoding="utf-8") as f:
        json.dump(diagnostics, f, indent=2, default=str)
    pd.DataFrame([diagnostics]).to_csv(diagnostics_csv_path, index=False)

    return {
        "strict_path": strict_path,
        "relaxed_path": relaxed_path,
        "production_path": production_path,
        "scored_path": ranking_path,
        "diagnostics_json_path": diagnostics_json_path,
        "diagnostics_csv_path": diagnostics_csv_path,
        "strict_df": strict,
        "relaxed_df": relaxed,
        "diagnostics": diagnostics,
    }


def _write_tiered_stable_panels(
    dmp_freq_df: pd.DataFrame,
    output_dir: Path,
    top_n: Optional[int],
    relaxed_cutoff_mode: str,
    relaxed_multiplier: float,
    score_eps: float,
    tier_thresholds: Dict[str, float],
    default_tier: str,
) -> Dict[str, Any]:
    """Write tiered dual-panel outputs and alias root production panel."""
    tiers: Dict[str, Dict[str, Any]] = {}
    for tier_name, threshold in tier_thresholds.items():
        tier_out = output_dir / f"tier_{tier_name}"
        artifact = write_stable_dual_panels(
            dmp_freq_df=dmp_freq_df,
            output_dir=tier_out,
            min_frequency=float(threshold),
            top_n=top_n,
            relaxed_cutoff_mode=relaxed_cutoff_mode,
            relaxed_multiplier=relaxed_multiplier,
            score_eps=score_eps,
        )
        diag = artifact.get("diagnostics") or {}
        tiers[tier_name] = {
            "name": tier_name,
            "min_frequency": float(threshold),
            "output_dir": str(tier_out),
            "stable_dmp_csv": str(artifact["production_path"]),
            "stable_dmp_csv_strict": str(artifact["strict_path"]),
            "stable_dmp_csv_relaxed": str(artifact["relaxed_path"]),
            "stable_dmp_scored_csv": str(artifact["scored_path"]),
            "stable_dmp_score_diagnostics_json": str(artifact["diagnostics_json_path"]),
            "stable_dmp_score_diagnostics_csv": str(artifact["diagnostics_csv_path"]),
            "stable_dmp_score_diagnostics": diag,
            "n_candidates_after_min_frequency": int(diag.get("n_candidates_after_min_frequency", 0)),
            "n_strict_selected": int(diag.get("n_strict_selected", 0)),
            "n_relaxed_selected": int(diag.get("n_relaxed_selected", 0)),
        }

    selected_tier = default_tier if default_tier in tiers else "extended"
    if selected_tier not in tiers:
        selected_tier = next(iter(tiers.keys()))
    selected = tiers[selected_tier]

    root_production_path = output_dir / "stable_dmps_production.csv"
    shutil.copy2(Path(selected["stable_dmp_csv"]), root_production_path)
    selected["root_production_alias"] = str(root_production_path)

    return {
        "tiers": tiers,
        "default_tier": selected_tier,
        "root_production_path": root_production_path,
    }


def run_stability_analysis(
    monte_carlo_runs_root: Path,
    output_dir: Optional[Path] = None,
    dmp_min_freq: float = 0.7,
    gene_min_freq: float = 0.5,
    top_n_dmps: Optional[int] = None,
    min_balanced_accuracy: Optional[float] = None,
    prefer_classifier_panel_dmps: bool = False,
    dual_cutoff_enabled: bool = False,
    relaxed_cutoff_mode: str = "elbow_log_score",
    relaxed_multiplier: float = 0.5,
    score_eps: float = 1e-12,
    tiered_stability_enabled: bool = False,
    tier_core_frequency: float = 0.85,
    tier_extended_frequency: float = 0.80,
    tier_exploratory_frequency: float = 0.70,
    default_freeze_tier: str = "extended",
) -> Dict[str, Any]:
    """Main entry point for stability analysis."""
    if output_dir is None:
        output_dir = monte_carlo_runs_root / "stability"

    dmp_df, dmp_summary = compute_dmp_stability(
        monte_carlo_runs_root,
        dmp_min_freq,
        min_balanced_accuracy=min_balanced_accuracy,
        prefer_classifier_panel_dmps=prefer_classifier_panel_dmps,
    )
    gene_df, gene_summary = compute_gene_stability(monte_carlo_runs_root, gene_min_freq)
    detector_param_summary = compute_detector_parameter_stability(monte_carlo_runs_root)

    stable_dmp_path = None
    selected_dmp_df = pd.DataFrame()
    strict_dmp_path = None
    relaxed_dmp_path = None
    scored_dmp_path = None
    score_diagnostics_json_path = None
    score_diagnostics_csv_path = None
    score_diagnostics = None
    tier_outputs: Dict[str, Any] = {}
    selected_tier_name: Optional[str] = None
    dmp_frequency_plot_path = None
    dmp_frequency_plot_by_chrom = {}
    dmp_frequency_counts_by_chrom = {}
    if tiered_stability_enabled:
        tier_thresholds = {
            "core": float(tier_core_frequency),
            "extended": float(tier_extended_frequency),
            "exploratory": float(tier_exploratory_frequency),
        }
        tier_payload = _write_tiered_stable_panels(
            dmp_freq_df=dmp_df,
            output_dir=output_dir,
            top_n=top_n_dmps,
            relaxed_cutoff_mode=relaxed_cutoff_mode,
            relaxed_multiplier=relaxed_multiplier,
            score_eps=score_eps,
            tier_thresholds=tier_thresholds,
            default_tier=str(default_freeze_tier).strip().lower(),
        )
        tier_outputs = tier_payload["tiers"]
        selected_tier_name = tier_payload["default_tier"]
        stable_dmp_path = tier_payload["root_production_path"]

        selected_tier = tier_outputs[selected_tier_name]
        strict_dmp_path = Path(selected_tier["stable_dmp_csv_strict"])
        relaxed_dmp_path = Path(selected_tier["stable_dmp_csv_relaxed"])
        scored_dmp_path = Path(selected_tier["stable_dmp_scored_csv"])
        score_diagnostics_json_path = Path(selected_tier["stable_dmp_score_diagnostics_json"])
        score_diagnostics_csv_path = Path(selected_tier["stable_dmp_score_diagnostics_csv"])
        score_diagnostics = selected_tier["stable_dmp_score_diagnostics"]
        selected_dmp_df = pd.read_csv(strict_dmp_path) if strict_dmp_path.exists() else pd.DataFrame()
    elif dual_cutoff_enabled:
        dual_paths = write_stable_dual_panels(
            dmp_df,
            output_dir,
            min_frequency=dmp_min_freq,
            top_n=top_n_dmps,
            relaxed_cutoff_mode=relaxed_cutoff_mode,
            relaxed_multiplier=relaxed_multiplier,
            score_eps=score_eps,
        )
        selected_dmp_df = dual_paths["strict_df"]
        stable_dmp_path = dual_paths["production_path"]
        strict_dmp_path = dual_paths["strict_path"]
        relaxed_dmp_path = dual_paths["relaxed_path"]
        scored_dmp_path = dual_paths["scored_path"]
        score_diagnostics_json_path = dual_paths["diagnostics_json_path"]
        score_diagnostics_csv_path = dual_paths["diagnostics_csv_path"]
        score_diagnostics = dual_paths["diagnostics"]
    else:
        selected_dmp_df = _select_stable_dmps_df(
            dmp_df, min_frequency=dmp_min_freq, top_n=top_n_dmps
        )
        # Always materialize the stable panel path so --freeze has a deterministic input artifact,
        # even when no DMP passes thresholds (empty CSV with canonical headers).
        stable_dmp_path = write_stable_panel(dmp_df, output_dir, dmp_min_freq, top_n_dmps)
    if not dmp_df.empty:
        (
            dmp_frequency_plot_path,
            dmp_frequency_plot_by_chrom,
            dmp_frequency_counts_by_chrom,
        ) = write_dmp_frequency_plot_by_chromosome(
            dmp_df, selected_dmp_df, output_dir
        )

    summary = {
        "dmp_stability": dmp_summary,
        "gene_stability": gene_summary,
        "detector_parameters": detector_param_summary,
        "stable_dmp_csv": str(stable_dmp_path) if stable_dmp_path else None,
        "stable_dmp_csv_strict": str(strict_dmp_path) if strict_dmp_path else None,
        "stable_dmp_csv_relaxed": str(relaxed_dmp_path) if relaxed_dmp_path else None,
        "stable_dmp_scored_csv": str(scored_dmp_path) if scored_dmp_path else None,
        "stable_dmp_score_diagnostics_json": (
            str(score_diagnostics_json_path) if score_diagnostics_json_path else None
        ),
        "stable_dmp_score_diagnostics_csv": (
            str(score_diagnostics_csv_path) if score_diagnostics_csv_path else None
        ),
        "stable_dmp_score_diagnostics": score_diagnostics,
        "dual_cutoff_enabled": bool(dual_cutoff_enabled or tiered_stability_enabled),
        "tiered_stability_enabled": bool(tiered_stability_enabled),
        "stability_default_freeze_tier": selected_tier_name,
        "stability_tiers": tier_outputs,
        "dmp_frequency_plot_html": str(dmp_frequency_plot_path) if dmp_frequency_plot_path else None,
        "dmp_frequency_charts_by_chromosome": dmp_frequency_plot_by_chrom,
        "dmp_frequency_counts_by_chromosome": dmp_frequency_counts_by_chrom,
        "output_dir": str(output_dir),
    }

    summary_path = output_dir / "stability_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    if not dmp_df.empty:
        dmp_df.to_csv(output_dir / "dmp_frequency.csv", index=False)
    if not gene_df.empty:
        gene_df.to_csv(output_dir / "gene_frequency.csv", index=False)

    return summary


def _merge_stable_dmp_panels(
    stable_dmp_csv: str | Path,
    output_dir: Path,
) -> Path:
    """Merge one or more per-chromosome (or single genome-wide) stable DMP CSVs into a unified panel.

    The fixed_dmp_panel only requires 'chromosome' and 'position' columns (others are preserved).
    Deduplicates by (chromosome, position) keeping the highest-frequency entry if available.
    """
    stable_path = Path(stable_dmp_csv)
    if not stable_path.exists():
        raise FileNotFoundError(f"Stable DMP path not found: {stable_path}")

    merged_path = output_dir / "stable_dmps_genomewide.csv"
    output_dir.mkdir(parents=True, exist_ok=True)

    if stable_path.is_dir():
        # Support per-chromosome stable files (e.g. in stability/ dir or custom)
        csv_files = sorted(stable_path.glob("**/*stable*.csv")) or sorted(
            stable_path.glob("**/*.csv")
        )
        if not csv_files:
            csv_files = [stable_path / "stable_dmps_production.csv"]
        frames: List[pd.DataFrame] = []
        for csv_f in csv_files:
            if csv_f.exists() and csv_f.suffix.lower() == ".csv":
                try:
                    df = pd.read_csv(csv_f)
                    if {"chromosome", "position"}.issubset(df.columns):
                        frames.append(df)
                except Exception as e:
                    logger.warning(f"Skipping unreadable CSV {csv_f}: {e}")
        if frames:
            merged_df = pd.concat(frames, ignore_index=True)
            if "effect_size" not in merged_df.columns:
                merged_df["effect_size"] = pd.Series(dtype="float64")
            # Deduplicate, preferring higher frequency if column present
            if "frequency" in merged_df.columns:
                sort_cols = ["frequency"]
                sort_asc = [False]
                if "effect_size" in merged_df.columns:
                    sort_cols.append("effect_size")
                    sort_asc.append(False)
                merged_df = merged_df.sort_values(
                    sort_cols,
                    ascending=sort_asc,
                    na_position="last",
                )
            merged_df = merged_df.drop_duplicates(
                subset=["chromosome", "position"], keep="first"
            ).reset_index(drop=True)
            merged_df.to_csv(merged_path, index=False)
            logger.info(
                f"Merged {len(frames)} stable DMP CSVs → {len(merged_df):,} unique DMPs "
                f"(genome-wide panel at {merged_path})"
            )
            return merged_path
        else:
            # Fallback to single file in dir
            fallback = stable_path / "stable_dmps_production.csv"
            if fallback.exists():
                stable_path = fallback
            else:
                raise ValueError(f"No valid stable DMP CSVs found in directory: {stable_path}")

    # Single CSV case (default from write_stable_panel)
    if stable_path.suffix.lower() == ".csv":
        shutil.copy2(stable_path, merged_path)
        logger.info(f"Copied stable DMP panel to {merged_path}")
    else:
        merged_path = stable_path

    return merged_path


def freeze_production_model(
    base_project: Path,
    stable_dmp_csv: str,
    monte_carlo_runs_root: Path,
    production_output_dir: Optional[str] = None,
    skip_centroid: bool = False,
    config: Optional["MonteCarloConfig"] = None,
) -> Dict[str, Any]:
    """
    Merge per-chromosome stable DMPs (if multiple files/dir provided) into one
    genome-wide panel, generate production project.json with fixed_dmp_panel,
    and run the full production pipeline: centroid → detector(fixed panel)
    → mapper → enricher (no classifier or predictor).
    """
    if production_output_dir is None:
        production_output_dir = str(monte_carlo_runs_root / "production")
    prod_dir = Path(production_output_dir)
    prod_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Production freeze output dir: {prod_dir}")

    # Merge stable DMPs (handles single CSV from stability or per-chrom CSVs)
    merged_panel = _merge_stable_dmp_panels(stable_dmp_csv, prod_dir)

    logger.info(f"Using fixed DMP panel: {merged_panel} for production run")

    # Load base project JSON and modify for production
    with open(base_project, encoding="utf-8") as f:
        project_dict = json.load(f)

    pr = config.path_remap if config is not None else None
    pr_dict = dict(pr) if pr else None
    if pr_dict is not None:
        from .path_remap import (
            apply_path_remap_to_nested,
            remap_cohort_list_files_in_project,
            remap_path_string,
        )

        apply_path_remap_to_nested(project_dict, pr_dict)
    if config is not None and config.samples_base_path:
        # MonteCarloConfig.samples_base_path is copied from the template project at CLI load time.
        # Without remapping here it would overwrite apply_path_remap_to_nested's samples_base_path
        # with a stale OLD-prefix value.
        sbp = str(config.samples_base_path).rstrip("/")
        if pr_dict is not None:
            sbp = remap_path_string(sbp, pr_dict)
        project_dict["samples_base_path"] = sbp
    if pr_dict is not None:
        remap_cohort_list_files_in_project(project_dict, pr_dict, prod_dir)

    # Set fixed_dmp_panel in detection step config (bypasses discovery in MethylDetector)
    if "step_config" not in project_dict:
        project_dict["step_config"] = {}
    if "detection" not in project_dict["step_config"]:
        project_dict["step_config"]["detection"] = {}
    # Preserve configured path style (e.g., /work mount aliases) instead of
    # canonicalizing through OS realpath resolution, which can rewrite to
    # environment-specific NFS prefixes (e.g., /lambda/nfs/...).
    project_dict["step_config"]["detection"]["fixed_dmp_panel"] = str(merged_panel)

    # Production run uses full dataset (no MC train/val split), unique project name
    project_dict["project_name"] = "production"
    # Set output_base so outputs land under .../monte_carlo_runs/production/...
    if prod_dir.parent.name == "monte_carlo_runs":
        project_dict["output_base"] = str(prod_dir.parent)
    else:
        project_dict["output_base"] = str(prod_dir)

    prod_project_path = prod_dir / "project.json"
    with open(prod_project_path, "w", encoding="utf-8") as f:
        json.dump(project_dict, f, indent=2)

    # Run production pipeline (centroid on full data + fixed-panel detector etc.)
    from .pipeline_runner import run_pipeline_for_production
    success, errors, timings = run_pipeline_for_production(
        prod_project_path,
        logs_dir=prod_dir / "logs",
        skip_centroid=bool(skip_centroid),
        config=config,
    )

    summary = {
        "output_dir": str(prod_dir),
        "fixed_dmp_panel": str(merged_panel),
        "production_project": str(prod_project_path),
        "success": success,
        "errors": errors,
        "timings": timings,
    }
    summary_path = prod_dir / "production_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    logger.info(f"Production freeze complete: {summary_path}")
    return summary


def build_production_model(
    monte_carlo_runs_root: Path,
    production_output_dir: Optional[str] = None,
    config: Optional["MonteCarloConfig"] = None,
) -> Dict[str, Any]:
    """
    Run the model building and evaluation steps on the production project:
    classifier → predictor.
    Assumes --freeze has already generated the production project.json.
    """
    if production_output_dir is None:
        production_output_dir = str(monte_carlo_runs_root / "production")
    prod_dir = Path(production_output_dir)
    prod_project_path = prod_dir / "project.json"

    if not prod_project_path.exists():
        raise FileNotFoundError(f"Production project not found: {prod_project_path}. Run --freeze first.")

    logger.info(f"Production model output dir: {prod_dir}")

    from .pipeline_runner import run_pipeline_for_model

    predictor_out = prod_dir / "predictors"
    predictor_out.mkdir(parents=True, exist_ok=True)
    success, errors, timings = run_pipeline_for_model(
        prod_project_path,
        logs_dir=prod_dir / "logs",
        predictor_output_dir=predictor_out,
        config=config,
    )

    summary = {
        "output_dir": str(prod_dir),
        "production_project": str(prod_project_path),
        "model_backend": config.model_backend if config is not None else "ecdf",
        "success": success,
        "errors": errors,
        "timings": timings,
    }
    summary_path = prod_dir / "model_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    logger.info(f"Production model build complete: {summary_path}")
    return summary

