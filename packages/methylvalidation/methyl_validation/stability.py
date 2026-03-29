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
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from methyl_utils import load_project
from methyl_utils.logging_utils import setup_module_logging

logger = setup_module_logging(__name__)


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
        return None
    try:
        return float(ba)
    except (TypeError, ValueError):
        return None


def load_discovery_dmps(run_dir: Path) -> Optional[pd.DataFrame]:
    """Load and concatenate all dmps-*-discovery.csv files from a MC run directory.

    Searches all detection subdirectories so that multi-chromosome runs are
    correctly aggregated into a single DataFrame before stability counting.
    """
    detection_dirs = list(run_dir.glob("**/detections/*/*"))
    if not detection_dirs:
        detection_dirs = list(run_dir.glob("detections/*/*"))
    frames: list = []
    for d in detection_dirs:
        for csv in sorted(d.glob("dmps-*-discovery.csv")):
            try:
                frames.append(pd.read_csv(csv))
            except Exception:
                continue
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


def _curve_elbow_point(x_vals: List[float], y_vals: List[float]) -> Optional[Dict[str, float]]:
    """
    Return elbow point using max distance to line between first/last points.

    Expects x and y as aligned lists with at least 3 points.
    """
    if len(x_vals) < 3 or len(y_vals) < 3 or len(x_vals) != len(y_vals):
        return None

    x0, y0 = float(x_vals[0]), float(y_vals[0])
    x1, y1 = float(x_vals[-1]), float(y_vals[-1])
    line_dx = x1 - x0
    line_dy = y1 - y0
    denom = (line_dx**2 + line_dy**2) ** 0.5
    if denom <= 0:
        return None

    best_idx = None
    best_dist = -1.0
    for i in range(1, len(x_vals) - 1):
        px, py = float(x_vals[i]), float(y_vals[i])
        # Perpendicular distance from point to segment-defining line
        dist = abs(line_dy * px - line_dx * py + x1 * y0 - y1 * x0) / denom
        if dist > best_dist:
            best_dist = dist
            best_idx = i

    if best_idx is None:
        return None
    return {
        "frequency_pct": float(x_vals[best_idx]),
        "dmps_count": float(y_vals[best_idx]),
        "distance_to_baseline": float(best_dist),
    }


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
    selected = dmp_freq_df[dmp_freq_df["frequency"] >= min_frequency].copy()
    if top_n is not None and len(selected) > top_n:
        selected = selected.head(top_n)
    return selected


def write_dmp_frequency_plot_by_chromosome(
    dmp_freq_df: pd.DataFrame,
    selected_dmp_df: pd.DataFrame,
    output_dir: Path,
) -> tuple[Optional[Path], Dict[str, str], Dict[str, Dict[str, float]], Dict[str, Dict[str, int]]]:
    """
    Write Plotly frequency charts with one series per chromosome and all-vs-selected traces.

    Returns:
      - combined chart path
      - per chromosome chart paths
      - elbow by chromosome
      - count summaries by chromosome
    """
    if dmp_freq_df.empty or "frequency" not in dmp_freq_df.columns:
        return None, {}, {}, {}
    try:
        import plotly.graph_objects as go
    except Exception as e:
        logger.warning(f"Plotly not available; skipping DMP frequency chart: {e}")
        return None, {}, {}, {}

    if "chromosome" not in dmp_freq_df.columns:
        return None, {}, {}, {}

    output_dir.mkdir(parents=True, exist_ok=True)
    chromosomes = [str(c) for c in sorted(dmp_freq_df["chromosome"].dropna().unique(), key=str)]
    if not chromosomes:
        return None, {}, {}, {}

    combined = go.Figure()
    # 26 unique colors: 24 chromosome series + selected/elbow marker colors
    palette_26 = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b",
        "#e377c2", "#7f7f7f", "#bcbd22", "#17becf", "#393b79", "#637939",
        "#8c6d31", "#843c39", "#7b4173", "#3182bd", "#31a354", "#756bb1",
        "#636363", "#e6550d", "#969696", "#6baed6", "#fd8d3c", "#74c476",
        "#000000", "#e41a1c",
    ]
    selected_color = palette_26[24]
    elbow_color = palette_26[25]

    per_chrom_paths: Dict[str, str] = {}
    elbow_by_chrom: Dict[str, Dict[str, float]] = {}
    count_summary_by_chrom: Dict[str, Dict[str, int]] = {}
    selected_points_x: List[float] = []
    selected_points_y: List[float] = []
    selected_points_text: List[str] = []
    elbow_points_x: List[float] = []
    elbow_points_y: List[float] = []
    elbow_points_text: List[str] = []

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
                line={"color": palette_26[i % 24]},
                marker={"color": palette_26[i % 24]},
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

        elbow_source = sel_dist if len(sel_dist) >= 3 else all_dist
        elbow = _curve_elbow_point(
            elbow_source["frequency_pct"].tolist(),
            elbow_source["dmps_count"].tolist(),
        )
        if elbow is not None:
            elbow_by_chrom[str(chrom)] = elbow
            elbow_points_x.append(float(elbow["frequency_pct"]))
            elbow_points_y.append(float(elbow["dmps_count"]))
            elbow_points_text.append(f"chr{chrom} elbow@{elbow['frequency_pct']:.2f}%")
            fig.add_trace(
                go.Scatter(
                    x=[elbow["frequency_pct"]],
                    y=[elbow["dmps_count"]],
                    mode="markers",
                    marker={"size": 11, "symbol": "diamond", "color": elbow_color},
                    name="elbow",
                    hovertemplate="Elbow<br>Frequency: %{x:.2f}%<br>DMPs: %{y:.0f}<extra></extra>",
                )
            )
            fig.add_vline(
                x=float(elbow["frequency_pct"]),
                line_dash="dash",
                annotation_text=f"Elbow ≈ {elbow['frequency_pct']:.2f}%",
                annotation_position="top right",
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
        return None, {}, {}, {}

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
    if elbow_points_x:
        combined.add_trace(
            go.Scatter(
                x=elbow_points_x,
                y=elbow_points_y,
                mode="markers",
                marker={"size": 10, "symbol": "diamond", "color": elbow_color},
                name="elbow",
                text=elbow_points_text,
                hovertemplate="%{text}<br>DMPs: %{y:.0f}<extra></extra>",
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
    return combined_path, per_chrom_paths, elbow_by_chrom, count_summary_by_chrom


def compute_dmp_stability(
    monte_carlo_runs_root: Path,
    min_frequency: float = 0.7,
    min_balanced_accuracy: Optional[float] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Count how often each DMP appears in discovery CSVs across runs.

    If ``min_balanced_accuracy`` is set, only iterations whose ``validation_metrics.json``
    reports ``balanced_accuracy >= min_balanced_accuracy`` contribute DMPs and define the
    frequency denominator.
    """
    runs = sorted(monte_carlo_runs_root.glob("run_*"))
    if not runs:
        runs = sorted(monte_carlo_runs_root.glob("run_0*"))

    dmp_counts: Dict[Tuple[Any, int], int] = defaultdict(int)
    run_count = 0
    skipped_no_discovery = 0
    skipped_low_ba = 0

    for run_dir in runs:
        df = load_discovery_dmps(run_dir)
        if df is None or "position" not in df.columns or "chromosome" not in df.columns:
            skipped_no_discovery += 1
            continue
        if min_balanced_accuracy is not None:
            ba = run_balanced_accuracy(run_dir)
            if ba is None or ba < float(min_balanced_accuracy):
                skipped_low_ba += 1
                continue
        run_count += 1
        for _, row in df.iterrows():
            key = _dmp_key_from_row(row)
            dmp_counts[key] += 1

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
        data.append({
            "chromosome": chrom,
            "position": pos,
            "frequency": freq,
            "count": count,
            "n_runs": run_count,
        })

    df = pd.DataFrame(data)
    if not df.empty:
        df = df.sort_values("frequency", ascending=False)

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

    out_path = output_dir / "stable_dmps_production.csv"
    stable.to_csv(out_path, index=False)
    return out_path


def run_stability_analysis(
    monte_carlo_runs_root: Path,
    output_dir: Optional[Path] = None,
    dmp_min_freq: float = 0.7,
    gene_min_freq: float = 0.5,
    top_n_dmps: Optional[int] = None,
    min_balanced_accuracy: Optional[float] = None,
) -> Dict[str, Any]:
    """Main entry point for stability analysis."""
    if output_dir is None:
        output_dir = monte_carlo_runs_root / "stability"

    dmp_df, dmp_summary = compute_dmp_stability(
        monte_carlo_runs_root, dmp_min_freq, min_balanced_accuracy=min_balanced_accuracy
    )
    gene_df, gene_summary = compute_gene_stability(monte_carlo_runs_root, gene_min_freq)
    detector_param_summary = compute_detector_parameter_stability(monte_carlo_runs_root)

    stable_dmp_path = None
    selected_dmp_df = pd.DataFrame()
    dmp_frequency_plot_path = None
    dmp_frequency_plot_by_chrom = {}
    dmp_frequency_elbow_by_chrom = {}
    dmp_frequency_counts_by_chrom = {}
    dmp_frequency_elbow = None
    if not dmp_df.empty:
        selected_dmp_df = _select_stable_dmps_df(
            dmp_df, min_frequency=dmp_min_freq, top_n=top_n_dmps
        )
        stable_dmp_path = write_stable_panel(dmp_df, output_dir, dmp_min_freq, top_n_dmps)
        (
            dmp_frequency_plot_path,
            dmp_frequency_plot_by_chrom,
            dmp_frequency_elbow_by_chrom,
            dmp_frequency_counts_by_chrom,
        ) = write_dmp_frequency_plot_by_chromosome(
            dmp_df, selected_dmp_df, output_dir
        )
        if len(dmp_frequency_elbow_by_chrom) == 1:
            dmp_frequency_elbow = next(iter(dmp_frequency_elbow_by_chrom.values()))

    summary = {
        "dmp_stability": dmp_summary,
        "gene_stability": gene_summary,
        "detector_parameters": detector_param_summary,
        "stable_dmp_csv": str(stable_dmp_path) if stable_dmp_path else None,
        "dmp_frequency_plot_html": str(dmp_frequency_plot_path) if dmp_frequency_plot_path else None,
        "dmp_frequency_charts_by_chromosome": dmp_frequency_plot_by_chrom,
        "dmp_frequency_elbow_by_chromosome": dmp_frequency_elbow_by_chrom,
        "dmp_frequency_counts_by_chromosome": dmp_frequency_counts_by_chrom,
        "dmp_frequency_elbow": dmp_frequency_elbow,
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
            # Deduplicate, preferring higher frequency if column present
            if "frequency" in merged_df.columns:
                merged_df = merged_df.sort_values("frequency", ascending=False)
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
    config: Optional[Any] = None,
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

    # Set fixed_dmp_panel in detection step config (bypasses discovery in MethylDetector)
    if "step_config" not in project_dict:
        project_dict["step_config"] = {}
    if "detection" not in project_dict["step_config"]:
        project_dict["step_config"]["detection"] = {}
    project_dict["step_config"]["detection"]["fixed_dmp_panel"] = str(merged_panel.resolve())

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
    config: Optional[Any] = None,
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
    )

    summary = {
        "output_dir": str(prod_dir),
        "production_project": str(prod_project_path),
        "success": success,
        "errors": errors,
        "timings": timings,
    }
    summary_path = prod_dir / "model_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    logger.info(f"Production model build complete: {summary_path}")
    return summary

