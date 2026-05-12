"""
Stability and freeze readiness analysis: audit MC stability outputs, production freeze,
and disease progression artifacts; emit structured JSON and markdown for pre-model review.

This module is read-only: it does not modify project data.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Mirror deprecated detector keys rejected by MethylDetectorConfig.model_validator (subset used in configs).
_REMOVED_DETECTOR_KEYS = frozenset(
    {
        "max_dmps_for_classifier",
        "use_gpu",
        "validation_mode",
        "n_validation_samples",
        "min_sample_coverage",
        "min_validation_coverage_per_position",
        "classifier_coverage_weighting",
        "synthetic_config",
        "classifier_type",
        "eps",
        "ecdf_overlap_grid_size",
        "ecdf_ks_grid_size",
        "statistical_test",
        "distribution",
        "delta_mean_mode",
        "overlap_mode",
        "max_N_for_ecdf",
    }
)


@dataclass
class ReadinessVerdict:
    """Aggregate go / go_with_risks / no_go with reasons."""

    overall: str  # go | go_with_risks | no_go
    stability: str
    freeze: str
    progression: str
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _safe_read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _scan_removed_detector_keys(detection: Dict[str, Any]) -> List[str]:
    return sorted(k for k in detection if k in _REMOVED_DETECTOR_KEYS)


def _progression_entity_columns(df: pd.DataFrame) -> Tuple[str, Optional[str]]:
    """Return (comparison_col, entity_col) for long-table progression CSV."""
    comp = "comparison" if "comparison" in df.columns else ("comparison_label" if "comparison_label" in df.columns else "")
    if not comp:
        return "", None
    for cand in ("module", "pathway", "gene"):
        if cand in df.columns:
            return comp, cand
    if "entity_label" in df.columns:
        return comp, "entity_label"
    return comp, None


def _module_trajectory_summary(modules_csv: Path, ordered_stages: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "modules_csv": str(modules_csv),
        "n_rows": 0,
        "n_unique_entities": 0,
        "entities_all_stages": 0,
        "median_abs_pearson_stage_vs_score": None,
        "fraction_monotone_up": None,
        "fraction_monotone_down": None,
        "top_by_abs_trend": [],
        "error": None,
    }
    if not modules_csv.is_file():
        out["error"] = "missing_file"
        return out
    try:
        df = pd.read_csv(modules_csv)
    except Exception as exc:
        out["error"] = str(exc)
        return out
    out["n_rows"] = int(len(df))
    comp_col, ent_col = _progression_entity_columns(df)
    if not comp_col or not ent_col or "stage_index" not in df.columns:
        out["error"] = "unexpected_columns"
        return out
    work = df[[comp_col, ent_col, "stage_index", "score"]].copy()
    work["stage_index"] = pd.to_numeric(work["stage_index"], errors="coerce")
    work["score"] = pd.to_numeric(work["score"], errors="coerce")
    work = work.dropna(subset=["stage_index", "score"])
    work[ent_col] = work[ent_col].astype(str)
    n_ent = work[ent_col].nunique()
    out["n_unique_entities"] = int(n_ent)

    stage_order = {lab: i for i, lab in enumerate(ordered_stages)}
    if not stage_order:
        stage_order = {str(k): int(k) for k in sorted(work["stage_index"].unique())}
    work["_ord"] = work[comp_col].map(stage_order).fillna(work["stage_index"])
    pearson_abs: List[float] = []
    mono_up = mono_down = 0
    ent_details: List[Tuple[str, float, float]] = []

    for ent, g in work.groupby(ent_col, sort=False):
        gg = g.sort_values("_ord").drop_duplicates(subset=["_ord"], keep="first")
        if len(gg) < 3:
            continue
        xs = gg["_ord"].to_numpy(dtype=float)
        ys = gg["score"].to_numpy(dtype=float)
        if np.std(xs) < 1e-12 or np.std(ys) < 1e-12:
            rho = 0.0
        else:
            rho = float(np.corrcoef(xs, ys)[0, 1])
            if np.isnan(rho):
                rho = 0.0
        pearson_abs.append(abs(rho))
        diffs = np.diff(ys)
        if len(diffs) >= 2:
            if np.all(diffs >= 0) and np.any(diffs > 0):
                mono_up += 1
            if np.all(diffs <= 0) and np.any(diffs < 0):
                mono_down += 1
        ent_details.append((str(ent), rho, float(np.mean(ys))))

    all_stage_labels = set(stage_order.keys())
    present_by_ent = work.groupby(ent_col)[comp_col].apply(lambda s: set(s.astype(str)))
    n_all = sum(1 for _e, labs in present_by_ent.items() if all_stage_labels <= labs)
    out["entities_all_stages"] = int(n_all)

    if pearson_abs:
        out["median_abs_pearson_stage_vs_score"] = float(np.median(pearson_abs))
        denom = len(pearson_abs)
        out["fraction_monotone_up"] = mono_up / denom
        out["fraction_monotone_down"] = mono_down / denom
    ent_details.sort(key=lambda t: abs(t[1]), reverse=True)
    out["top_by_abs_trend"] = [
        {"entity": e, "pearson_stage_vs_score": round(r, 4), "mean_score": round(m, 6)}
        for e, r, m in ent_details[:15]
    ]
    return out


def _chromosome_panel_balance(panel_csv: Path, max_freq_csv: Optional[Path]) -> Dict[str, Any]:
    """Fraction of stable DMPs per chromosome (from panel or frequency table)."""
    out: Dict[str, Any] = {"source": None, "n_positions": 0, "fraction_by_chromosome": {}, "max_chrom_share": None}
    path = panel_csv if panel_csv.is_file() else None
    if path is None and max_freq_csv and max_freq_csv.is_file():
        path = max_freq_csv
        out["source"] = "dmp_frequency.csv"
    elif path is not None:
        out["source"] = str(panel_csv.name)
    if path is None:
        return out
    try:
        df = pd.read_csv(path, usecols=lambda c: c in ("chromosome", "position"))
    except Exception:
        df = pd.read_csv(path)
    if "chromosome" not in df.columns:
        return out
    vc = df["chromosome"].astype(str).value_counts(normalize=True)
    out["n_positions"] = int(len(df))
    out["fraction_by_chromosome"] = {str(k): round(float(v), 6) for k, v in vc.items()}
    if len(vc):
        out["max_chrom_share"] = round(float(vc.max()), 6)
    return out


def _label_mix(labels_csv: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {"n_entities": 0, "by_type": {}, "label_counts": {}}
    if not labels_csv.is_file():
        return out
    try:
        df = pd.read_csv(labels_csv)
    except Exception:
        return out
    out["n_entities"] = int(len(df))
    if "entity_type" in df.columns:
        out["by_type"] = df["entity_type"].value_counts().to_dict()
    if "progression_labels" in df.columns:
        vc = df["progression_labels"].astype(str).value_counts().head(25)
        out["label_counts"] = vc.to_dict()
    return out


def analyze_project_root(project_root: Path) -> Dict[str, Any]:
    """
    Collect readiness metrics under ``project_root`` (directory that contains ``monte_carlo_runs``).

    Expected layout::
        {project_root}/monte_carlo_runs/stability/...
        {project_root}/monte_carlo_runs/production/...
    """
    root = project_root.resolve()
    mc = root / "monte_carlo_runs"
    stability_dir = mc / "stability"
    production_dir = mc / "production"
    progression_dir = production_dir / "progression"

    stability_summary_path = stability_dir / "stability_summary.json"
    production_summary_path = production_dir / "production_summary.json"
    production_project_path = production_dir / "project.json"

    stability_summary = _safe_read_json(stability_summary_path) or {}
    production_summary = _safe_read_json(production_summary_path) or {}
    production_project = _safe_read_json(production_project_path) or {}

    dmp_freq_path = stability_dir / "dmp_frequency.csv"
    stable_panel_path = stability_dir / "stable_dmps_production.csv"
    merged_panel_path = production_dir / "stable_dmps_genomewide.csv"
    progression_summary_path = progression_dir / "summary.json"

    dmp_stab = stability_summary.get("dmp_stability") or {}
    progression_summary = _safe_read_json(progression_summary_path) or {}

    detection_cfg = ((production_project.get("step_config") or {}).get("detection")) or {}
    fixed_panel = detection_cfg.get("fixed_dmp_panel")

    removed_in_production = _scan_removed_detector_keys(detection_cfg if isinstance(detection_cfg, dict) else {})

    ordered_labels = list(progression_summary.get("ordered_comparison_labels") or [])
    modules_long = progression_summary.get("modules_long_csv")
    mod_path = Path(modules_long) if modules_long else progression_dir / "modules_long.csv"

    ordered_stage_narratives: List[Dict[str, Any]] = []
    if production_project_path.is_file():
        try:
            from methyl_utils.pipeline_config import load_project

            proj = load_project(production_project_path)
            tokens = ordered_labels or proj.get_ordered_comparison_labels()
            ordered_stage_narratives = proj.get_ordered_stage_narratives(tokens)
        except Exception:
            ordered_stage_narratives = []

    mapper_cfg = ((production_project.get("step_config") or {}).get("mapper")) or {}
    disease_context = mapper_cfg.get("disease_term")
    if isinstance(disease_context, str):
        disease_context = disease_context.strip() or None
    else:
        disease_context = None

    report: Dict[str, Any] = {
        "project_root": str(root),
        "disease_context": disease_context,
        "paths": {
            "stability_summary": str(stability_summary_path),
            "production_summary": str(production_summary_path),
            "production_project": str(production_project_path),
            "stable_panel": str(stable_panel_path),
            "merged_panel": str(merged_panel_path),
            "progression_summary": str(progression_summary_path),
        },
        "stability": {
            "present": stability_summary_path.is_file(),
            "dmp_stability": dmp_stab,
            "stable_panel_rows": _count_csv_rows(stable_panel_path),
            "dmp_frequency_rows": _count_csv_rows(dmp_freq_path),
        },
        "freeze": {
            "present": production_summary_path.is_file(),
            "success": production_summary.get("success"),
            "errors": production_summary.get("errors"),
            "timings": production_summary.get("timings"),
            "fixed_dmp_panel_in_project": fixed_panel,
            "merged_panel_rows": _count_csv_rows(merged_panel_path),
            "removed_detector_keys_in_production_project": removed_in_production,
        },
        "progression": {
            "summary_present": progression_summary_path.is_file(),
            "ordered_comparison_labels": ordered_labels,
            "missing_inputs": progression_summary.get("missing_inputs"),
            "row_counts": {
                "genes": progression_summary.get("genes_rows"),
                "pathways": progression_summary.get("pathways_rows"),
                "modules": progression_summary.get("modules_rows"),
            },
            "module_trajectory": _module_trajectory_summary(mod_path, ordered_labels),
            "entity_labels": _label_mix(progression_dir / "entities_progression_labels.csv"),
            "ordered_stage_narratives": ordered_stage_narratives,
        },
        "panel_balance": _chromosome_panel_balance(merged_panel_path, dmp_freq_path),
    }
    report["verdict"] = asdict(_compute_verdict(report))
    return report


def _count_csv_rows(path: Path) -> Optional[int]:
    if not path.is_file():
        return None
    try:
        return sum(1 for _ in open(path, encoding="utf-8", errors="replace")) - 1
    except Exception:
        return None


def _compute_verdict(report: Dict[str, Any]) -> ReadinessVerdict:
    reasons: List[str] = []
    warnings: List[str] = []

    stab = report["stability"]
    fr = report["freeze"]
    prog = report["progression"]
    balance = report["panel_balance"]

    stab_status = "unknown"
    if not stab["present"]:
        stab_status = "fail"
        reasons.append("Missing stability_summary.json — run stability analysis first.")
    else:
        ds = stab.get("dmp_stability") or {}
        n_runs = int(ds.get("n_runs_analyzed") or 0)
        stable_n = int(ds.get("stable_dmps_at_threshold") or 0)
        panel_rows = stab.get("stable_panel_rows")
        if panel_rows is not None and panel_rows != stable_n and stable_n:
            warnings.append(f"stable_dmps_production.csv row count ({panel_rows}) differs from summary stable_dmps_at_threshold ({stable_n}).")
        if stable_n <= 0 or (panel_rows is not None and panel_rows <= 0):
            stab_status = "fail"
            reasons.append("Stable DMP panel is empty — lower stability_dmp_freq or increase iterations.")
        elif n_runs < 5:
            stab_status = "warn"
            warnings.append(f"Only {n_runs} runs analyzed; prefer ≥10 for robust recurrence estimates.")
        else:
            stab_status = "pass"

    freeze_status = "unknown"
    if not fr["present"]:
        freeze_status = "fail"
        reasons.append("Missing production_summary.json — run --freeze after stability.")
    elif fr.get("success") is not True:
        freeze_status = "fail"
        reasons.append(f"Freeze did not succeed: errors={fr.get('errors')!r}")
    else:
        timings = fr.get("timings") or []
        bad = []
        for t in timings:
            rc = t.get("return_code")
            if rc is None:
                rc = -1
            try:
                rc_int = int(rc)
            except (TypeError, ValueError):
                rc_int = -1
            if rc_int != 0:
                bad.append(t)
        if bad:
            freeze_status = "fail"
            reasons.append(f"Freeze steps with non-zero return_code: {[t.get('step_name') for t in bad]}")
        elif fr.get("removed_detector_keys_in_production_project"):
            freeze_status = "fail"
            reasons.append(
                "production/project.json detection block contains removed legacy keys: "
                f"{fr['removed_detector_keys_in_production_project']}"
            )
        elif not fr.get("fixed_dmp_panel_in_project"):
            freeze_status = "fail"
            reasons.append("production project missing step_config.detection.fixed_dmp_panel.")
        else:
            freeze_status = "pass"

    prog_status = "unknown"
    if prog["summary_present"]:
        miss = prog.get("missing_inputs") or []
        if miss:
            prog_status = "warn"
            warnings.append(f"Progression missing_inputs non-empty: {miss[:5]}...")
        else:
            traj = prog.get("module_trajectory") or {}
            if traj.get("error"):
                prog_status = "warn"
                warnings.append(f"Module trajectory could not be computed: {traj.get('error')}")
            elif int(traj.get("entities_all_stages") or 0) == 0:
                prog_status = "warn"
                warnings.append("No modules present across all ordered stages — review enricher modules_ranked.csv inputs.")
            else:
                prog_status = "pass"
        med = (prog.get("module_trajectory") or {}).get("median_abs_pearson_stage_vs_score")
        if med is not None and med < 0.15:
            warnings.append(
                "Weak median |Pearson(stage_ord, score)| across modules — progression signal may be subtle."
            )
    else:
        prog_status = "skipped"
        warnings.append("No progression/summary.json — enable step_config.progression on freeze or run progression separately.")

    if balance.get("max_chrom_share") is not None and balance["max_chrom_share"] > 0.45:
        warnings.append(
            f"Chromosome imbalance: one chromosome holds ~{balance['max_chrom_share']*100:.1f}% of stable panel."
        )

    # Overall
    if stab_status == "fail" or freeze_status == "fail":
        overall = "no_go"
    elif stab_status == "warn" or freeze_status == "warn" or prog_status == "warn" or warnings:
        overall = "go_with_risks"
    else:
        overall = "go"

    return ReadinessVerdict(
        overall=overall,
        stability=stab_status,
        freeze=freeze_status,
        progression=prog_status,
        reasons=reasons,
        warnings=warnings,
    )


def render_markdown(report: Dict[str, Any], *, redact_paths: bool = False) -> str:
    from .grok_readiness import redact_report_for_export

    src = redact_report_for_export(report) if redact_paths else report
    v = src.get("verdict") or {}
    lines = [
        "# Stability and freeze readiness report",
        "",
    ]
    if not redact_paths:
        lines.append(f"- **Project root**: `{src.get('project_root', '')}`")
    lines.extend(
        [
            f"- **Overall verdict**: **{v.get('overall', 'unknown')}**",
            f"- **Stability**: {v.get('stability')}",
            f"- **Freeze**: {v.get('freeze')}",
            f"- **Progression**: {v.get('progression')}",
            "",
        ]
    )
    if v.get("reasons"):
        lines.extend(["## Blocking issues", ""])
        lines.extend(f"- {r}" for r in v["reasons"])
        lines.append("")
    if v.get("warnings"):
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {w}" for w in v["warnings"])
        lines.append("")

    s = src.get("stability") or {}
    lines.extend(
        [
            "## Stability",
            "",
            f"- Summary present: {s.get('present')}",
            f"- Stable panel rows (CSV): {s.get('stable_panel_rows')}",
            f"- DMP frequency table rows: {s.get('dmp_frequency_rows')}",
        ]
    )
    ds = s.get("dmp_stability") or {}
    if ds:
        lines.extend(
            [
                f"- Runs analyzed: {ds.get('n_runs_analyzed')}",
                f"- Skipped (low BA): {ds.get('skipped_low_balanced_accuracy')}",
                f"- Min frequency threshold: {ds.get('min_frequency')}",
                f"- Stable DMPs at threshold: {ds.get('stable_dmps_at_threshold')}",
                f"- Total unique DMPs seen: {ds.get('total_unique_dmps')}",
            ]
        )
    lines.append("")

    f = src.get("freeze") or {}
    lines.extend(
        [
            "## Freeze (production)",
            "",
            f"- Summary present: {f.get('present')}",
            f"- Success: {f.get('success')}",
            (
                f"- Fixed panel path: `{f.get('fixed_dmp_panel_in_project')}`"
                if f.get("fixed_dmp_panel_in_project")
                else "- Fixed panel path: (redacted)"
            ),
            f"- Merged panel rows: {f.get('merged_panel_rows')}",
        ]
    )
    if f.get("removed_detector_keys_in_production_project"):
        lines.append(f"- **Legacy detector keys still present**: {f['removed_detector_keys_in_production_project']}")
    if f.get("timings"):
        lines.extend(["", "| Step | Seconds | RC |", "|------|---------|-----|"])
        for t in f["timings"]:
            lines.append(
                f"| {t.get('step_name')} | {t.get('duration_seconds')} | {t.get('return_code')} |"
            )
    lines.append("")

    p = src.get("progression") or {}
    lines.extend(
        [
            "## Progression",
            "",
            f"- Summary present: {p.get('summary_present')}",
            f"- Ordered comparisons: {p.get('ordered_comparison_labels')}",
            f"- Missing inputs: {p.get('missing_inputs')}",
            f"- Row counts: {p.get('row_counts')}",
        ]
    )
    narr = p.get("ordered_stage_narratives") or []
    if isinstance(narr, list) and narr:
        lines.extend(["", "### Stage definitions (from project config)", ""])
        for row in narr:
            if not isinstance(row, dict):
                continue
            lab = row.get("comparison_label") or "?"
            desc = row.get("description")
            if isinstance(desc, str) and desc.strip():
                lines.append(f"- **`{lab}`**: {desc.strip()}")
            else:
                lines.append(f"- **`{lab}`**")
    traj = p.get("module_trajectory") or {}
    if traj:
        lines.extend(
            [
                "",
                "### Module score trajectory (vs stage order)",
                "",
                f"- Entities with rows: {traj.get('n_unique_entities')}",
                f"- Entities present all stages: {traj.get('entities_all_stages')}",
                f"- Median |Pearson(stage_ord, score)|: {traj.get('median_abs_pearson_stage_vs_score')}",
                f"- Fraction monotone up (among scored): {traj.get('fraction_monotone_up')}",
                f"- Fraction monotone down (among scored): {traj.get('fraction_monotone_down')}",
            ]
        )
        top = traj.get("top_by_abs_trend") or []
        if top:
            lines.extend(["", "| Entity | Pearson | Mean score |", "|--------|---------|------------|"])
            for row in top[:10]:
                lines.append(
                    f"| {row.get('entity')} | {row.get('pearson_stage_vs_score')} | {row.get('mean_score')} |"
                )
    labels = p.get("entity_labels") or {}
    if labels.get("label_counts"):
        lines.extend(["", "### Progression label counts (entities_progression_labels)", ""])
        for lab, cnt in list(labels["label_counts"].items())[:15]:
            lines.append(f"- `{lab}`: {cnt}")
    lines.append("")

    bal = src.get("panel_balance") or {}
    lines.extend(
        [
            "## Stable panel chromosome balance",
            "",
            f"- Positions counted: {bal.get('n_positions')}",
            f"- Source: {bal.get('source')}",
            f"- Max chromosome share: {bal.get('max_chrom_share')}",
        ]
    )
    fracs = bal.get("fraction_by_chromosome") or {}
    if fracs:
        top_chrom = sorted(fracs.items(), key=lambda kv: kv[1], reverse=True)[:8]
        lines.append("- Top chromosomes: " + ", ".join(f"{c}:{frac:.3f}" for c, frac in top_chrom))
    lines.append("")

    ai = report.get("ai_review")
    if isinstance(ai, dict) and ai:
        lines.extend(["## AI readiness commentary (advisory)", "", "*Deterministic verdict above is unchanged; this section is LLM-assisted QA only.*", ""])
        st = ai.get("status")
        lines.append(f"- **Status**: `{st}`")
        if ai.get("model_used"):
            lines.append(f"- **Model**: `{ai.get('model_used')}`")
        if ai.get("error"):
            lines.extend(["", f"- **Error**: {ai.get('error')}", ""])
        if ai.get("credential_hint"):
            lines.extend(["", f"- **Credential hint**: {ai.get('credential_hint')}", ""])
        if ai.get("structured_parse_note"):
            lines.extend(["", f"- **Parse note**: {ai.get('structured_parse_note')}", ""])
        if ai.get("response_preview"):
            pv = str(ai.get("response_preview") or "")[:4000]
            lines.extend(["", "### Model reply (truncated)", "", "```", pv, "```", ""])
        struct = ai.get("structured")
        if isinstance(struct, dict):
            ca = struct.get("consistency_assessment")
            if ca:
                lines.append(f"- **Consistency assessment**: `{ca}`")
            for key, title in (
                ("summary_bullets", "Summary"),
                ("caveats", "Caveats"),
                ("suggested_human_checks", "Suggested human checks"),
            ):
                items = struct.get(key)
                if isinstance(items, list) and items:
                    lines.extend(["", f"### {title}", ""])
                    for item in items:
                        lines.append(f"- {item}")
            dp = struct.get("disease_progression_alignment")
            if isinstance(dp, str) and dp.strip():
                lines.extend(["", "### Disease progression alignment", "", dp.strip(), ""])
            if struct.get("narrative_text") and not dp:
                lines.extend(["", "### Narrative", "", str(struct["narrative_text"])[:4000], ""])
        lines.append("")

    lines.extend(
        [
            "---",
            "*Generated by `methyl-stability-freeze-readiness`. Interpret biology with domain review; progression labels are rule-based summaries.*",
        ]
    )
    return "\n".join(lines)


def _default_readiness_dir(project_root: Path) -> Path:
    """Reports live next to Monte Carlo outputs: ``<project>/readiness/``."""
    return project_root.resolve() / "readiness"


def _resolve_report_output_path(project_root: Path, arg: Optional[Path], default_filename: str) -> Path:
    """
    Default outputs go under ``<project_root>/readiness/``.

    - If ``arg`` is omitted: ``readiness/<default_filename>``.
    - If ``arg`` is absolute: use as-is.
    - If ``arg`` is relative: treat as relative to ``readiness/`` (not the shell cwd).
    """
    rd = _default_readiness_dir(project_root)
    if arg is None:
        return rd / default_filename
    p = arg.expanduser()
    if p.is_absolute():
        return p
    return (rd / p).resolve()


def _normalize_project_root_arg(raw: Path) -> Tuple[Optional[Path], int]:
    """
    Ensure the positional argument is a project directory, not a stray config file path.

    Returns ``(resolved_directory, 0)`` or ``(None, 2)`` when the path exists and is a file
    (common mistake: passing ``.../MyProject.json`` instead of ``.../MyProject``).
    """
    p = raw.expanduser().resolve()
    if p.exists() and p.is_file():
        lines = [
            "methyl-stability-freeze-readiness: first argument must be the PROJECT DIRECTORY "
            "that contains monte_carlo_runs/, not a JSON/config file.",
            f"Received a file: {p}",
        ]
        if p.suffix.lower() == ".json":
            cand = p.with_suffix("")
            mc = cand / "monte_carlo_runs"
            if cand.is_dir() and mc.is_dir():
                lines.append(f"Example: methyl-stability-freeze-readiness {cand}")
            elif cand.is_dir():
                lines.append(f"You may have meant the directory: {cand}")
        print("\n".join(lines), file=sys.stderr)
        return None, 2
    return p, 0


def _emit_grok_stderr_summary(ai_review: Dict[str, Any]) -> None:
    """One-line stderr hint so terminal runs show Grok outcome even if markdown is easy to miss."""
    st = ai_review.get("status")
    if st == "ok":
        mu = ai_review.get("model_used") or ai_review.get("model_requested") or "?"
        print(
            f"methyl-stability-freeze-readiness: Grok advisory review OK (model_used={mu}). "
            "See markdown section \"AI readiness commentary (advisory)\".",
            file=sys.stderr,
        )
        return
    if st == "skipped_no_key":
        hint = ai_review.get("credential_hint") or ai_review.get("error") or "(no detail)"
        print(
            "methyl-stability-freeze-readiness: Grok skipped — no API key resolved. "
            f"{hint}",
            file=sys.stderr,
        )
        return
    if st == "error":
        err = ai_review.get("error") or "(unknown)"
        print(
            f"methyl-stability-freeze-readiness: Grok request failed — {err}",
            file=sys.stderr,
        )
        return
    print(
        f"methyl-stability-freeze-readiness: Grok advisory status={st!r}.",
        file=sys.stderr,
    )


def main(argv: Optional[List[str]] = None) -> int:
    from .grok_readiness import (
        DEFAULT_GROK_MODEL,
        build_sanitized_ai_payload,
        redact_report_for_export,
        resolve_grok_api_key,
        run_grok_readiness_review,
    )

    parser = argparse.ArgumentParser(
        description="Audit stability, freeze, and progression artifacts before modeling."
    )
    parser.add_argument(
        "project_root",
        type=Path,
        help="Directory containing monte_carlo_runs/ (e.g. .../Healthy_vs_PCa1-4-CG)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        metavar="PATH",
        help="Write full report JSON (default: <project>/readiness/readiness.json). Relative paths are under readiness/.",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=None,
        metavar="PATH",
        help="Write markdown report (default: <project>/readiness/readiness.md). Relative paths are under readiness/.",
    )
    parser.add_argument(
        "--stdout-only",
        action="store_true",
        help="Do not write JSON/markdown files; print markdown to stdout only (legacy pipe-friendly mode).",
    )
    parser.add_argument(
        "--redact-paths",
        action="store_true",
        help="Omit project_root, artifact paths, and fixed_panel path from markdown and JSON export.",
    )
    grok = parser.add_argument_group("Grok advisory review (xAI)")
    grok.add_argument(
        "--no-grok-review",
        action="store_false",
        dest="grok_review",
        help="Disable Grok consistency review (default: enabled).",
    )
    grok.set_defaults(grok_review=True)
    grok.add_argument("--grok-model", type=str, default=DEFAULT_GROK_MODEL, help="xAI chat model name.")
    grok.add_argument("--grok-max-top-rows", type=int, default=10, help="Top-N rows for module trends and labels in AI payload.")
    grok.add_argument("--grok-timeout-seconds", type=float, default=60.0, help="HTTP timeout per Grok request.")
    grok.add_argument("--grok-max-retries", type=int, default=2, help="Retries on transient Grok failures.")
    grok.add_argument("--grok-temperature", type=float, default=0.1, help="Sampling temperature for Grok.")
    grok.add_argument("--grok-api-key", type=str, default=None, help="Explicit Grok API key (otherwise MethylMapper credential chain).")
    grok.add_argument(
        "--encrypted-file-path",
        type=Path,
        default=None,
        help="Encrypted Grok credential file (same as methyl-mapper --encrypted-file-path; default ~/.methyl_mapper/credentials/grok_api_key.encrypted).",
    )
    grok.add_argument("--azure-key-vault-url", type=str, default=None, help="Optional Azure Key Vault URL for Grok key.")
    grok.add_argument("--azure-secret-name", type=str, default=None, help="Optional Key Vault secret name (default grok-api-key).")
    grok.add_argument(
        "--methyl-mapper-home",
        type=Path,
        default=None,
        help="Optional MethylMapper home for credential file resolution (~/.methyl_mapper by default).",
    )
    grok.add_argument(
        "--disease-context",
        type=str,
        default=None,
        help="Override disease label sent to Grok (default: production project mapper disease_term).",
    )
    grok.add_argument(
        "--include-ai-raw-response",
        action="store_true",
        help="Include truncated raw Grok text in ai_review (default: off).",
    )
    grok.add_argument("--ai-raw-response-max-chars", type=int, default=2000, help="Max chars when --include-ai-raw-response.")
    args = parser.parse_args(argv)

    proj_root, arg_rc = _normalize_project_root_arg(args.project_root)
    if arg_rc != 0:
        return arg_rc
    args.project_root = proj_root

    report = analyze_project_root(args.project_root)

    ai_review: Optional[Dict[str, Any]] = None
    if getattr(args, "grok_review", True):
        disease = (args.disease_context or "").strip() or report.get("disease_context")
        payload = build_sanitized_ai_payload(
            report,
            disease_context=str(disease) if disease else None,
            top_n=max(1, int(args.grok_max_top_rows)),
        )
        api_key, key_hint = resolve_grok_api_key(
            explicit_key=args.grok_api_key,
            azure_key_vault_url=(args.azure_key_vault_url or "").strip() or None,
            azure_secret_name=(args.azure_secret_name or "").strip() or None,
            methyl_mapper_home=args.methyl_mapper_home.expanduser() if args.methyl_mapper_home else None,
            encrypted_file_path=args.encrypted_file_path.expanduser() if args.encrypted_file_path else None,
        )
        if not api_key:
            ai_review = {
                "status": "skipped_no_key",
                "error": "No Grok API key resolved (set GROK_API_KEY, use methyl_mapper_credentials save, or pass --grok-api-key).",
                "credential_hint": key_hint,
                "advisory_only": True,
            }
        else:
            ai_review = run_grok_readiness_review(
                sanitized_payload=payload,
                api_key=api_key,
                model=args.grok_model,
                temperature=float(args.grok_temperature),
                timeout_seconds=float(args.grok_timeout_seconds),
                max_retries=int(args.grok_max_retries),
                include_raw_response=bool(args.include_ai_raw_response),
                raw_max_chars=int(args.ai_raw_response_max_chars),
            )
        report["ai_review"] = ai_review
        report["ai_review_payload_meta"] = {
            "sanitized": True,
            "top_n": max(1, int(args.grok_max_top_rows)),
            "model_requested": args.grok_model,
        }
        _emit_grok_stderr_summary(ai_review)
    else:
        report["ai_review"] = {"status": "disabled", "advisory_only": True}
        print(
            "methyl-stability-freeze-readiness: Grok advisory review disabled (--no-grok-review).",
            file=sys.stderr,
        )

    export_doc = copy.deepcopy(report)
    if args.redact_paths:
        export_doc = redact_report_for_export(export_doc)

    text = render_markdown(report, redact_paths=bool(args.redact_paths))

    if not args.stdout_only:
        json_path = _resolve_report_output_path(args.project_root, args.json_out, "readiness.json")
        md_path = _resolve_report_output_path(args.project_root, args.markdown_out, "readiness.md")

        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(export_doc, jf, indent=2, default=str)

        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(text, encoding="utf-8")

        print(
            f"methyl-stability-freeze-readiness: wrote JSON → {json_path}\n"
            f"methyl-stability-freeze-readiness: wrote markdown → {md_path}",
            file=sys.stderr,
        )
    print(text)
    return 0 if report.get("verdict", {}).get("overall") != "no_go" else 2


if __name__ == "__main__":
    sys.exit(main())
