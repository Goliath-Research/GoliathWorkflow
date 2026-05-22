"""
Disease progression synthesis from per-comparison mapper/enricher outputs.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
from methyl_utils import load_project


@dataclass
class StageSpec:
    stage_index: int
    control_group: str
    disease_group: str
    comparison_label: str
    mapper_combined_csv: Path
    enricher_dir: Path
    pathway_csv: Path
    modules_csv: Path


def _pick_existing_path(candidates: Sequence[Path]) -> Optional[Path]:
    for path in candidates:
        if path.exists():
            return path
    return None


def resolve_stage_specs(
    project_path: Path,
    ordered_comparison_labels: Optional[Sequence[str]] = None,
) -> Tuple[List[StageSpec], Dict[str, Any]]:
    """
    Resolve ordered per-stage inputs from project comparisons.

    Default stage order matches ``ProjectConfig.get_ordered_comparison_labels()`` in methylutils
    (i.e. ``comparisons`` list order or shorthand expansion) when neither CLI nor
    ``step_config.progression.ordered_comparison_labels`` / ``ordered_disease_groups`` is set.
    """
    project = load_project(project_path)
    progression_cfg = project.get_step_config("progression") or {}
    comparisons = list(project.get_comparisons())
    if not comparisons:
        raise ValueError("No project comparisons found; disease progression needs comparison-based outputs.")

    by_disease_group: Dict[str, Any] = {c.disease_group: c for c in comparisons}
    by_label: Dict[str, Any] = {
        (c.comparison_label or c.disease_group): c for c in comparisons
    }

    selected: List[Any] = []
    ordered_labels = list(ordered_comparison_labels or [])
    if not ordered_labels:
        cfg_order = progression_cfg.get("ordered_comparison_labels") or progression_cfg.get(
            "ordered_disease_groups"
        )
        if isinstance(cfg_order, list):
            ordered_labels = [str(x) for x in cfg_order]
    if not ordered_labels:
        # Backward-compatible fallback: older methyl_utils ProjectConfig versions may not
        # expose get_ordered_comparison_labels(), so use comparison iteration order.
        get_ordered = getattr(project, "get_ordered_comparison_labels", None)
        if callable(get_ordered):
            resolved_order = get_ordered()
            if isinstance(resolved_order, list):
                ordered_labels = [str(x) for x in resolved_order]
            elif isinstance(resolved_order, tuple):
                ordered_labels = [str(x) for x in resolved_order]
        else:
            ordered_labels = [str(c.comparison_label or c.disease_group) for c in comparisons]
    if ordered_labels:
        for token in ordered_labels:
            c = by_disease_group.get(token) or by_label.get(token)
            if c is None:
                known = sorted(set(by_disease_group.keys()) | set(by_label.keys()))
                raise ValueError(
                    f"Unknown ordered comparison label {token!r}. Known labels/groups: {known}"
                )
            selected.append(c)
    else:
        selected = comparisons

    enricher_cfg = project.get_step_config("enricher") or {}
    combined_csv_name = str(enricher_cfg.get("combined_csv_name") or "all-gene_name-combined.csv")

    specs: List[StageSpec] = []
    for idx, c in enumerate(selected):
        label = c.comparison_label or c.disease_group
        map_dir = Path(project.get_mapper_output_dir(c.control_group, c.disease_group))
        enr_dir = Path(project.get_enricher_output_dir(c.control_group, c.disease_group))
        pathway_csv = _pick_existing_path(
            [
                enr_dir / "enrichment_merged.csv",
                enr_dir / "enrichment_top_q0.05.csv",
            ]
        ) or (enr_dir / "enrichment_merged.csv")
        specs.append(
            StageSpec(
                stage_index=idx,
                control_group=str(c.control_group),
                disease_group=str(c.disease_group),
                comparison_label=str(label),
                mapper_combined_csv=map_dir / combined_csv_name,
                enricher_dir=enr_dir,
                pathway_csv=pathway_csv,
                modules_csv=enr_dir / "modules_ranked.csv",
            )
        )

    meta = {
        "project_name": project.project_name,
        "project_root": project.get_project_root(),
        "ordered_comparison_labels": [s.comparison_label for s in specs],
        "ordered_disease_groups": [s.disease_group for s in specs],
        "progression_step_config": progression_cfg,
    }
    return specs, meta


def _first_existing_column(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _build_gene_rows(stage: StageSpec) -> pd.DataFrame:
    if not stage.mapper_combined_csv.exists():
        return pd.DataFrame()
    df = pd.read_csv(stage.mapper_combined_csv)
    gene_col = _first_existing_column(df, ["gene_name", "gene_symbol", "gene", "symbol", "gene_id"])
    if gene_col is None:
        return pd.DataFrame()
    score_col = _first_existing_column(
        df,
        ["total_weight", "gene_importance", "total_importance", "mean_effect_size", "mean_weight"],
    )
    work = df[[gene_col] + ([score_col] if score_col else [])].copy()
    work[gene_col] = work[gene_col].astype(str).str.strip()
    work = work[work[gene_col] != ""]
    if score_col is not None:
        work[score_col] = pd.to_numeric(work[score_col], errors="coerce").fillna(0.0)
        agg = work.groupby(gene_col, as_index=False)[score_col].max()
        agg = agg.sort_values(score_col, ascending=False).reset_index(drop=True)
        agg["rank"] = agg.index + 1
        agg["score"] = agg[score_col]
    else:
        agg = work.drop_duplicates(subset=[gene_col]).reset_index(drop=True)
        agg["rank"] = agg.index + 1
        agg["score"] = 1.0
    return pd.DataFrame(
        {
            "stage_index": stage.stage_index,
            "comparison": stage.comparison_label,
            "rank": agg["rank"],
            "score": agg["score"],
            "gene": agg[gene_col].astype(str),
        }
    )


def _build_pathway_rows(stage: StageSpec) -> pd.DataFrame:
    if not stage.pathway_csv.exists():
        return pd.DataFrame()
    df = pd.read_csv(stage.pathway_csv)
    term_col = _first_existing_column(df, ["Term", "term", "Pathway", "pathway"])
    if term_col is None:
        return pd.DataFrame()
    q_col = _first_existing_column(df, ["Adjusted P-value", "adj_p", "q_value", "q"])
    score_col = _first_existing_column(df, ["Combined Score", "Odds Ratio", "score"])
    work_cols = [term_col]
    if q_col:
        work_cols.append(q_col)
    if score_col and score_col not in work_cols:
        work_cols.append(score_col)
    work = df[work_cols].copy()
    work[term_col] = work[term_col].astype(str).str.strip()
    work = work[work[term_col] != ""]
    if q_col:
        work[q_col] = pd.to_numeric(work[q_col], errors="coerce").fillna(1.0)
        work = work.sort_values(q_col, ascending=True).reset_index(drop=True)
    else:
        work = work.reset_index(drop=True)
    work["rank"] = work.index + 1
    if q_col:
        # Higher is better for monotonic trend checks.
        work["score"] = work[q_col].map(lambda x: -math.log10(max(float(x), 1e-300)))
    elif score_col:
        work["score"] = pd.to_numeric(work[score_col], errors="coerce").fillna(0.0)
    else:
        work["score"] = 0.0
    return pd.DataFrame(
        {
            "stage_index": stage.stage_index,
            "comparison": stage.comparison_label,
            "rank": work["rank"],
            "score": work["score"],
            "pathway": work[term_col].astype(str),
        }
    )


def _build_module_rows(stage: StageSpec) -> pd.DataFrame:
    if not stage.modules_csv.exists():
        return pd.DataFrame()
    df = pd.read_csv(stage.modules_csv)
    module_col = _first_existing_column(
        df,
        ["Module_primary", "Module_display", "Module", "module", "module_name"],
    )
    if module_col is None:
        return pd.DataFrame()
    score_col = _first_existing_column(df, ["Score", "score"])
    work_cols = [module_col] + ([score_col] if score_col else [])
    work = df[work_cols].copy()
    work[module_col] = work[module_col].astype(str).str.strip()
    work = work[work[module_col] != ""]
    if score_col:
        work[score_col] = pd.to_numeric(work[score_col], errors="coerce").fillna(0.0)
        work = work.sort_values(score_col, ascending=False).reset_index(drop=True)
        work["score"] = work[score_col]
    else:
        work = work.reset_index(drop=True)
        work["score"] = 0.0
    work["rank"] = work.index + 1
    return pd.DataFrame(
        {
            "stage_index": stage.stage_index,
            "comparison": stage.comparison_label,
            "rank": work["rank"],
            "score": work["score"],
            "module": work[module_col].astype(str),
        }
    )


def _build_module_variant_rows(stage: StageSpec) -> pd.DataFrame:
    """Variant module rows using a stable family key with display-label fallbacks."""
    if not stage.modules_csv.exists():
        return pd.DataFrame()
    df = pd.read_csv(stage.modules_csv)
    if "Module_variant_family" not in df.columns and "Module_primary" in df.columns:
        # Backward-compatible stable family derivation for legacy enricher outputs:
        # preserve variant-vs-canonical distinction without stage-volatile subtitles.
        primary = df["Module_primary"].astype(str).str.strip()
        has_supporting = (
            df["Module_display"].astype(str).str.contains(r"\|", regex=True)
            if "Module_display" in df.columns
            else False
        )
        df["Module_variant_family"] = primary.where(
            ~has_supporting,
            primary + " | perturbation_evidence",
        )
    module_col = _first_existing_column(
        df,
        ["Module_variant_family", "Module_display", "Module", "module", "module_name"],
    )
    if module_col is None:
        return pd.DataFrame()
    score_col = _first_existing_column(df, ["Score", "score"])
    work_cols = [module_col] + ([score_col] if score_col else [])
    work = df[work_cols].copy()
    work[module_col] = work[module_col].astype(str).str.strip()
    work = work[work[module_col] != ""]
    if score_col:
        work[score_col] = pd.to_numeric(work[score_col], errors="coerce").fillna(0.0)
        work = work.sort_values(score_col, ascending=False).reset_index(drop=True)
        work["score"] = work[score_col]
    else:
        work = work.reset_index(drop=True)
        work["score"] = 0.0
    work["rank"] = work.index + 1
    return pd.DataFrame(
        {
            "stage_index": stage.stage_index,
            "comparison": stage.comparison_label,
            "rank": work["rank"],
            "score": work["score"],
            "module": work[module_col].astype(str),
        }
    )


def _enricher_completeness_missing(project_path: Path) -> List[str]:
    """Load production enricher_completeness.json and return human-readable gaps."""
    try:
        from methyl_utils import load_project
    except ImportError:
        return []

    project = load_project(project_path)
    manifest = Path(project.get_project_root()) / "enricher" / "enricher_completeness.json"
    if not manifest.is_file():
        return []

    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return ["enricher: could not parse enricher_completeness.json"]

    missing_msgs: List[str] = []
    if not data.get("all_complete", False):
        for label, comp in (data.get("comparisons") or {}).items():
            if comp.get("complete"):
                continue
            miss_libs = comp.get("missing_libraries") or []
            if miss_libs:
                missing_msgs.append(
                    f"{label}: enricher incomplete — missing libraries: {', '.join(miss_libs[:8])}"
                    + ("..." if len(miss_libs) > 8 else "")
                )
            elif not comp.get("modules_present") and comp.get("modules_required"):
                missing_msgs.append(f"{label}: enricher incomplete — modules_ranked.csv missing")
            else:
                missing_msgs.append(f"{label}: enricher incomplete")
    return missing_msgs


def aggregate_stage_tables(
    stage_specs: Sequence[StageSpec],
    *,
    strict_missing: bool = False,
    extra_missing: Optional[Sequence[str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    genes: List[pd.DataFrame] = []
    pathways: List[pd.DataFrame] = []
    modules: List[pd.DataFrame] = []
    module_variants: List[pd.DataFrame] = []
    missing: List[str] = []

    for spec in stage_specs:
        g = _build_gene_rows(spec)
        p = _build_pathway_rows(spec)
        m = _build_module_rows(spec)
        mv = _build_module_variant_rows(spec)
        if g.empty:
            missing.append(f"{spec.comparison_label}: mapper missing or no gene columns ({spec.mapper_combined_csv})")
        if p.empty:
            missing.append(f"{spec.comparison_label}: pathway table missing or invalid ({spec.pathway_csv})")
        genes.append(g)
        pathways.append(p)
        modules.append(m)
        module_variants.append(mv)

    genes_df = pd.concat(genes, ignore_index=True) if genes else pd.DataFrame()
    pathways_df = pd.concat(pathways, ignore_index=True) if pathways else pd.DataFrame()
    modules_df = pd.concat(modules, ignore_index=True) if modules else pd.DataFrame()
    modules_variant_df = (
        pd.concat(module_variants, ignore_index=True) if module_variants else pd.DataFrame()
    )
    if extra_missing:
        missing = list(missing) + list(extra_missing)
    if strict_missing and missing:
        raise ValueError("Missing required progression inputs: " + "; ".join(missing))
    io_summary = {
        "missing_inputs": missing,
        "genes_rows": int(len(genes_df)),
        "pathways_rows": int(len(pathways_df)),
        "modules_rows": int(len(modules_df)),
        "modules_variant_rows": int(len(modules_variant_df)),
    }
    return genes_df, pathways_df, modules_df, modules_variant_df, io_summary


def _labels_for_entity(stages_present: List[int], scores: List[float], max_stage_index: int) -> List[str]:
    labels: List[str] = []
    unique_stages = sorted(set(stages_present))
    if len(unique_stages) == 1:
        labels.append("stage_specific")
    if unique_stages == [0]:
        labels.append("early_only")
    if unique_stages == [max_stage_index]:
        labels.append("late_only")
    if len(unique_stages) == max_stage_index + 1:
        labels.append("stable_across_stages")
    if len(scores) >= 3:
        diffs = [b - a for a, b in zip(scores[:-1], scores[1:])]
        if all(d >= 0 for d in diffs) and any(d > 0 for d in diffs):
            labels.append("monotonic_up")
        if all(d <= 0 for d in diffs) and any(d < 0 for d in diffs):
            labels.append("monotonic_down")
    return labels


def _long_table_to_label_frame(df: pd.DataFrame, entity_type: str, name_col: str) -> pd.DataFrame:
    """Map slim long-table rows to the internal columns used by compute_progression_labels."""
    if df.empty or name_col not in df.columns:
        return pd.DataFrame()
    names = df[name_col].astype(str)
    return pd.DataFrame(
        {
            "entity_type": entity_type,
            "entity_id": names,
            "entity_label": names,
            "stage_index": df["stage_index"],
            "score": df["score"],
        }
    )


def compute_progression_labels(
    genes_df: pd.DataFrame,
    pathways_df: pd.DataFrame,
    modules_df: pd.DataFrame,
    *,
    stage_count: int,
) -> pd.DataFrame:
    entity_frames = [
        f
        for f in (
            _long_table_to_label_frame(genes_df, "gene", "gene"),
            _long_table_to_label_frame(pathways_df, "pathway", "pathway"),
            _long_table_to_label_frame(modules_df, "module", "module"),
        )
        if not f.empty
    ]
    if not entity_frames:
        return pd.DataFrame(
            columns=[
                "entity_type",
                "entity_id",
                "entity_label",
                "stages_present",
                "n_stages_present",
                "progression_labels",
            ]
        )
    all_entities = pd.concat(entity_frames, ignore_index=True)
    out_rows: List[Dict[str, Any]] = []
    max_stage_index = max(0, stage_count - 1)
    for (entity_type, entity_id), grp in all_entities.groupby(["entity_type", "entity_id"], sort=False):
        grp = grp.sort_values("stage_index")
        stages = grp["stage_index"].astype(int).tolist()
        scores = pd.to_numeric(grp["score"], errors="coerce").fillna(0.0).astype(float).tolist()
        labels = _labels_for_entity(stages, scores, max_stage_index)
        out_rows.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_label": str(grp["entity_label"].iloc[0]),
                "stages_present": ",".join(str(x) for x in sorted(set(stages))),
                "n_stages_present": int(len(set(stages))),
                "progression_labels": "|".join(labels) if labels else "none",
            }
        )
    return pd.DataFrame(out_rows).sort_values(
        ["entity_type", "n_stages_present", "entity_id"],
        ascending=[True, False, True],
    )


def render_markdown_report(
    summary: Dict[str, Any],
    labels_df: pd.DataFrame,
    *,
    top_n: int = 10,
    gene_set_metrics_df: Optional[pd.DataFrame] = None,
) -> str:
    lines = [
        "# Disease Progression Report",
        "",
        f"- Project: `{summary.get('project_name', 'unknown')}`",
        f"- Ordered stages: {', '.join(summary.get('ordered_comparison_labels', []))}",
        f"- Genes rows: {summary.get('genes_rows', 0)}",
        f"- Pathways rows: {summary.get('pathways_rows', 0)}",
        f"- Modules rows: {summary.get('modules_rows', 0)}",
        "",
    ]
    if summary.get("missing_inputs"):
        lines.append("## Missing Inputs")
        for item in summary["missing_inputs"]:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("## Top progression labels")
    if labels_df.empty:
        lines.append("- No entities found.")
    else:
        vc = (
            labels_df["progression_labels"]
            .astype(str)
            .value_counts()
            .head(top_n)
            .to_dict()
        )
        for label, count in vc.items():
            lines.append(f"- `{label}`: {count}")
    lines.append("")

    if gene_set_metrics_df is not None and not gene_set_metrics_df.empty:
        lines.append("## Gene set overlap metrics")
        lines.append("")
        frac_meta = summary.get("gene_set_fractions") or summary.get("gene_set_metrics") or {}
        bn = str(frac_meta.get("output_basename") or "stage_gene_set_fractions").strip() or "stage_gene_set_fractions"
        lines.append(
            "Per-stage fraction of mapper gene universe overlapping curated categories "
            f"(see `{bn}.csv` and `{bn}.json`)."
        )
        lines.append("")
        src = gene_set_metrics_df["gene_set_profile_source"].iloc[0]
        lines.append(f"- Profile source: `{src}`")
        lines.append("")
        for _, row in gene_set_metrics_df.sort_values(
            ["stage_index", "category_id"]
        ).iterrows():
            lines.append(
                f"- Stage {int(row['stage_index'])} `{row['comparison_label']}` "
                f"**{row['category_id']}**: "
                f"{float(row['fraction']):.4f} ({int(row['n_overlap'])}/{int(row['n_universe'])})"
            )
        lines.append("")

    return "\n".join(lines)


def run_progression_report(
    *,
    project_path: Path,
    output_dir: Optional[Path] = None,
    ordered_comparison_labels: Optional[Sequence[str]] = None,
    strict_missing: bool = False,
    report_md: bool = False,
    gene_set_metrics_enabled: Optional[bool] = None,
    gene_sets_path: Optional[Path] = None,
    disease_profile: Optional[str] = None,
    gene_set_profile: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Main entrypoint for progression synthesis.
    """
    stage_specs, meta = resolve_stage_specs(project_path, ordered_comparison_labels=ordered_comparison_labels)
    out_dir = output_dir or (Path(meta["project_root"]) / "progression")
    out_dir.mkdir(parents=True, exist_ok=True)

    enricher_missing = _enricher_completeness_missing(project_path)
    genes_df, pathways_df, modules_df, modules_variant_df, io_summary = aggregate_stage_tables(
        stage_specs,
        strict_missing=strict_missing,
        extra_missing=enricher_missing,
    )
    if enricher_missing:
        io_summary["enricher_completeness_missing"] = enricher_missing
    labels_df = compute_progression_labels(
        genes_df,
        pathways_df,
        modules_df,
        stage_count=len(stage_specs),
    )

    from .gene_set_coverage import (
        build_gene_set_fractions_json_payload,
        compute_gene_set_fractions,
        gene_set_fractions_summary,
        normalize_progression_gene_set_config,
    )

    gene_cfg: Dict[str, Any] = dict(meta.get("progression_step_config") or {})
    if gene_set_metrics_enabled is not None:
        gene_cfg["gene_set_metrics_enabled"] = bool(gene_set_metrics_enabled)
    if gene_sets_path is not None:
        gene_cfg["gene_sets_path"] = str(Path(gene_sets_path).expanduser())
    if disease_profile is not None:
        gene_cfg["disease_profile"] = str(disease_profile).strip()
    if gene_set_profile is not None:
        gene_cfg["gene_set_profile"] = str(Path(gene_set_profile).expanduser())

    metrics_df = compute_gene_set_fractions(stage_specs, gene_cfg)
    gene_norm = normalize_progression_gene_set_config(gene_cfg)

    genes_path = out_dir / "genes_long.csv"
    pathways_path = out_dir / "pathways_long.csv"
    modules_path = out_dir / "modules_long.csv"
    modules_variant_path = out_dir / "modules_long_variant.csv"
    labels_path = out_dir / "entities_progression_labels.csv"
    summary_path = out_dir / "summary.json"

    genes_df.to_csv(genes_path, index=False)
    pathways_df.to_csv(pathways_path, index=False)
    modules_df.to_csv(modules_path, index=False)
    modules_variant_df.to_csv(modules_variant_path, index=False)
    labels_df.to_csv(labels_path, index=False)

    summary: Dict[str, Any] = {
        **meta,
        **io_summary,
        "output_dir": str(out_dir),
        "genes_long_csv": str(genes_path),
        "pathways_long_csv": str(pathways_path),
        "modules_long_csv": str(modules_path),
        "modules_long_variant_csv": str(modules_variant_path),
        "labels_csv": str(labels_path),
    }
    _gsm = gene_set_fractions_summary(metrics_df, gene_cfg)
    summary["gene_set_fractions"] = _gsm
    summary["gene_set_metrics"] = _gsm
    if not metrics_df.empty:
        base = str(gene_norm.get("_gene_set_output_basename") or "stage_gene_set_fractions").strip()
        if not base:
            base = "stage_gene_set_fractions"
        metrics_path = out_dir / f"{base}.csv"
        metrics_json_path = out_dir / f"{base}.json"
        metrics_df.to_csv(metrics_path, index=False)
        with open(metrics_json_path, "w", encoding="utf-8") as jf:
            json.dump(build_gene_set_fractions_json_payload(metrics_df), jf, indent=2, default=str)
        summary["gene_set_fractions_csv"] = str(metrics_path)
        summary["gene_set_fractions_json"] = str(metrics_json_path)
        summary["gene_set_metrics_csv"] = str(metrics_path)

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    summary["summary_json"] = str(summary_path)

    if report_md:
        md_path = out_dir / "report.md"
        md_path.write_text(
            render_markdown_report(
                summary,
                labels_df,
                gene_set_metrics_df=metrics_df if not metrics_df.empty else None,
            ),
            encoding="utf-8",
        )
        summary["report_md"] = str(md_path)

    return summary

