#!/usr/bin/env python3
"""
Score recurrence of plasma vs buffy PPI hub gene signatures across MC iterations.

For each available context (discovery mapper, monte_carlo_runs/run_NNNN/mapper,
production/mapper, optional per-run enricher ppi_hubs.csv), apply the same
gene filters as step_config.enricher, take the top-N genes, and measure overlap
with two reference signature sets (typically discovery ppi_hubs from plasma
and buffy standalone runs).

Use this to confirm analyte-specific hub biology survives train/val resampling:
  - Plasma cohort runs should overlap the plasma signature more than the buffy signature.
  - Buffy cohort runs should show the reverse.

Example (Plasma project, signatures from discovery ppi_hubs):

  source .venv/bin/activate
  python tools/compare_analyte_mc_signatures.py \\
    --project /work/prostate-cancer/configs/project_Plasma_healthy_vs_PCa.json \\
    --plasma-hubs /work/prostate-cancer/Plasma_healthy_vs_PCa/enricher/all/PCa/ppi_hubs.csv \\
    --buffy-hubs /work/prostate-cancer/Buffy_healthy_vs_PCa/enricher/all/PCa/ppi_hubs.csv \\
    --out /work/prostate-cancer/analyte_comparison/signature_recurrence/plasma
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd
from methyl_utils.action_config_resolver import resolve_for_project

EVIDENCE_LEVEL_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}
SORT_BY_ALIASES = {"total_weight": "gene_importance"}


def _as_str_list(value: object) -> Optional[List[str]]:
    """Normalize config values that may be a list or a single string."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else None
    return [str(v).strip() for v in value if str(v).strip()]


def _load_signature_genes(path: Path, top_n: int) -> List[str]:
    df = pd.read_csv(path)
    if "gene" not in df.columns:
        raise ValueError(f"Signature file {path} must have a 'gene' column")
    genes: List[str] = []
    seen: Set[str] = set()
    for raw in df["gene"].astype(str):
        g = raw.strip()
        if not g or g in seen:
            continue
        seen.add(g)
        genes.append(g)
        if len(genes) >= top_n:
            break
    if not genes:
        raise ValueError(f"No genes found in signature file {path}")
    return genes


def _resolve_sort_column(df: pd.DataFrame, sort_by: Optional[str]) -> Optional[str]:
    if sort_by is None:
        return "gene_importance" if "gene_importance" in df.columns else None
    alias = SORT_BY_ALIASES.get(sort_by, sort_by)
    if alias in df.columns:
        return alias
    return sort_by if sort_by in df.columns else None


def filter_mapper_genes(
    df: pd.DataFrame,
    *,
    gene_column: str = "gene_name",
    disease_only: bool = False,
    disease_association_types: Optional[List[str]] = None,
    min_disease_evidence_level: Optional[str] = None,
    min_disease_score: Optional[float] = None,
    min_dmp_count: Optional[int] = None,
    min_unique_dmps: Optional[int] = None,
    max_gene_q_value: Optional[float] = None,
    sort_by: Optional[str] = None,
    sort_ascending: bool = False,
    top_n: Optional[int] = None,
) -> List[str]:
    """Apply enricher-style filters; return ordered unique gene names (silent)."""
    out = df.copy()
    hits_cols = [
        c
        for c in ("hits_promoter", "hits_exon", "hits_intron", "hits_gene_body", "hits_terminator")
        if c in out.columns
    ]
    if hits_cols:
        for c in hits_cols:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
        out = out[out[hits_cols].sum(axis=1) > 0]

    if disease_only and "disease_associated" in out.columns:
        out = out[out["disease_associated"].astype(str).str.upper().isin(("TRUE", "1", "YES"))]

    association_types = _as_str_list(disease_association_types)
    if association_types and "disease_association_type" in out.columns:
        allowed = {s.lower() for s in association_types}
        out = out[
            out["disease_association_type"].astype(str).str.strip().str.lower().isin(allowed)
        ]

    if min_disease_evidence_level is not None and "disease_evidence_level" in out.columns:
        min_level = EVIDENCE_LEVEL_ORDER.get(min_disease_evidence_level.lower(), 0)

        def _level_ok(val: object) -> bool:
            if pd.isna(val):
                return False
            return EVIDENCE_LEVEL_ORDER.get(str(val).lower(), 0) >= min_level

        out = out[out["disease_evidence_level"].apply(_level_ok)]

    if min_disease_score is not None and "disease_score" in out.columns:
        out = out[pd.to_numeric(out["disease_score"], errors="coerce").fillna(0) >= min_disease_score]

    if min_dmp_count is not None:
        if "unique_dmps" in out.columns:
            out = out[pd.to_numeric(out["unique_dmps"], errors="coerce").fillna(0) >= min_dmp_count]
        elif "dmp_count" in out.columns:
            out = out[pd.to_numeric(out["dmp_count"], errors="coerce").fillna(0) >= min_dmp_count]

    if min_unique_dmps is not None and "unique_dmps" in out.columns:
        if not (min_dmp_count is not None and min_unique_dmps == min_dmp_count):
            out = out[pd.to_numeric(out["unique_dmps"], errors="coerce").fillna(0) >= min_unique_dmps]

    qcol = None
    if max_gene_q_value is not None:
        if "gene_q_value" in out.columns:
            qcol = "gene_q_value"
        elif "q_value" in out.columns:
            qcol = "q_value"
        if qcol is not None:
            out = out[pd.to_numeric(out[qcol], errors="coerce") <= max_gene_q_value]

    sort_col = _resolve_sort_column(out, sort_by)
    if sort_col and sort_col in out.columns:
        out = out.sort_values(by=sort_col, ascending=sort_ascending)

    genes: List[str] = []
    seen: Set[str] = set()
    if gene_column not in out.columns:
        raise ValueError(f"Mapper CSV missing gene column {gene_column!r}")
    for _, row in out.iterrows():
        g = str(row[gene_column]).strip()
        if not g or g in seen:
            continue
        seen.add(g)
        genes.append(g)
        if top_n is not None and len(genes) >= top_n:
            break
    return genes


def _overlap_metrics(selected: Iterable[str], plasma_sig: Set[str], buffy_sig: Set[str]) -> Dict[str, Any]:
    sel = set(selected)
    p_hit = sel & plasma_sig
    b_hit = sel & buffy_sig
    p_frac = len(p_hit) / len(plasma_sig) if plasma_sig else 0.0
    b_frac = len(b_hit) / len(buffy_sig) if buffy_sig else 0.0
    if p_frac > b_frac:
        dominant = "plasma"
    elif b_frac > p_frac:
        dominant = "buffy"
    else:
        dominant = "tie"
    return {
        "n_selected": len(sel),
        "plasma_sig_overlap": len(p_hit),
        "plasma_sig_fraction": round(p_frac, 6),
        "buffy_sig_overlap": len(b_hit),
        "buffy_sig_fraction": round(b_frac, 6),
        "dominant_signature": dominant,
        "plasma_sig_genes_hit": sorted(p_hit),
        "buffy_sig_genes_hit": sorted(b_hit),
    }


@dataclass
class EvalContext:
    label: str
    mapper_csv: Optional[Path] = None
    ppi_hubs_csv: Optional[Path] = None


def _comparison_mapper_path(project_root: Path, comparison: str) -> Path:
    parts = comparison.strip("/").split("/")
    if len(parts) != 2:
        raise ValueError(f"comparison must be control/disease, got {comparison!r}")
    control, disease = parts
    return project_root / "mapper" / control / disease / "all-gene_name-combined.csv"


def _comparison_enricher_hubs(project_root: Path, comparison: str) -> Path:
    parts = comparison.strip("/").split("/")
    control, disease = parts
    return project_root / "enricher" / control / disease / "ppi_hubs.csv"


def _discover_contexts(project_json: Path, comparison: str) -> List[EvalContext]:
    from methyl_utils import load_project

    project = load_project(project_json)
    paths = project.get_derived_paths()
    cohort_root = Path(paths.output_base)
    mc_root = cohort_root / "monte_carlo_runs"

    contexts: List[EvalContext] = []

    discovery_mapper = _comparison_mapper_path(cohort_root, comparison)
    if discovery_mapper.is_file():
        contexts.append(
            EvalContext(
                label="discovery",
                mapper_csv=discovery_mapper,
                ppi_hubs_csv=_comparison_enricher_hubs(cohort_root, comparison)
                if _comparison_enricher_hubs(cohort_root, comparison).is_file()
                else None,
            )
        )

    if mc_root.is_dir():
        for run_dir in sorted(mc_root.glob("run_*")):
            if not run_dir.is_dir():
                continue
            mapper_csv = _comparison_mapper_path(run_dir, comparison)
            ppi_hubs = _comparison_enricher_hubs(run_dir, comparison)
            contexts.append(
                EvalContext(
                    label=run_dir.name,
                    mapper_csv=mapper_csv if mapper_csv.is_file() else None,
                    ppi_hubs_csv=ppi_hubs if ppi_hubs.is_file() else None,
                )
            )

        prod_root = mc_root / "production"
        prod_mapper = _comparison_mapper_path(prod_root, comparison)
        if prod_mapper.is_file():
            contexts.append(
                EvalContext(
                    label="production",
                    mapper_csv=prod_mapper,
                    ppi_hubs_csv=_comparison_enricher_hubs(prod_root, comparison)
                    if _comparison_enricher_hubs(prod_root, comparison).is_file()
                    else None,
                )
            )

    return contexts


def _enricher_filter_kwargs(project_json: Path) -> Dict[str, Any]:
    from methyl_utils import load_project

    project = load_project(project_json)
    cfg = resolve_for_project("enricher", project)
    return {
        "gene_column": cfg.get("gene_column") or "gene_name",
        "disease_only": bool(cfg.get("disease_only", False)),
        "disease_association_types": _as_str_list(cfg.get("disease_association_type")),
        "min_disease_evidence_level": cfg.get("min_disease_evidence_level"),
        "min_disease_score": cfg.get("min_disease_score"),
        "min_dmp_count": cfg.get("min_dmp_count"),
        "min_unique_dmps": cfg.get("min_unique_dmps"),
        "max_gene_q_value": cfg.get("max_gene_q_value"),
        "sort_by": cfg.get("sort_by"),
        "top_n": cfg.get("top") or 150,
    }


def evaluate_context(
    ctx: EvalContext,
    *,
    filter_kwargs: Dict[str, Any],
    plasma_sig: Set[str],
    buffy_sig: Set[str],
    signature_top_n: int,
    analyte: str,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "context": ctx.label,
        "analyte": analyte,
        "mapper_csv": str(ctx.mapper_csv) if ctx.mapper_csv else "",
        "ppi_hubs_csv": str(ctx.ppi_hubs_csv) if ctx.ppi_hubs_csv else "",
        "has_mapper": bool(ctx.mapper_csv and ctx.mapper_csv.is_file()),
        "has_ppi_hubs": bool(ctx.ppi_hubs_csv and ctx.ppi_hubs_csv.is_file()),
    }

    top_n = int(filter_kwargs.get("top_n") or 150)

    if ctx.mapper_csv and ctx.mapper_csv.is_file():
        df = pd.read_csv(ctx.mapper_csv)
        genes = filter_mapper_genes(df, **{k: v for k, v in filter_kwargs.items() if k != "top_n"}, top_n=top_n)
        metrics = _overlap_metrics(genes, plasma_sig, buffy_sig)
        row.update({f"mapper_{k}": v for k, v in metrics.items() if not k.endswith("_genes_hit")})
        row["mapper_plasma_sig_genes_hit"] = ";".join(metrics["plasma_sig_genes_hit"])
        row["mapper_buffy_sig_genes_hit"] = ";".join(metrics["buffy_sig_genes_hit"])
    else:
        row["mapper_n_selected"] = 0
        row["mapper_dominant_signature"] = "missing_mapper"

    if ctx.ppi_hubs_csv and ctx.ppi_hubs_csv.is_file():
        hub_genes = _load_signature_genes(ctx.ppi_hubs_csv, top_n=signature_top_n)
        metrics = _overlap_metrics(hub_genes, plasma_sig, buffy_sig)
        row.update({f"hubs_{k}": v for k, v in metrics.items() if not k.endswith("_genes_hit")})
        row["hubs_plasma_sig_genes_hit"] = ";".join(metrics["plasma_sig_genes_hit"])
        row["hubs_buffy_sig_genes_hit"] = ";".join(metrics["buffy_sig_genes_hit"])
    else:
        row["hubs_n_selected"] = 0
        row["hubs_dominant_signature"] = "missing_ppi_hubs"

    return row


def _summarize_rows(rows: List[Dict[str, Any]], analyte: str) -> Dict[str, Any]:
    mc_rows = [r for r in rows if re.match(r"run_\d{4}", str(r.get("context", "")))]
    mapper_ok = [r for r in mc_rows if r.get("has_mapper")]
    hubs_ok = [r for r in mc_rows if r.get("has_ppi_hubs")]

    def _dominant_counts(sub: List[Dict[str, Any]], prefix: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for r in sub:
            key = str(r.get(f"{prefix}dominant_signature") or "missing")
            counts[key] = counts.get(key, 0) + 1
        return counts

    return {
        "analyte": analyte,
        "n_contexts_total": len(rows),
        "n_mc_runs_seen": len(mc_rows),
        "n_mc_runs_with_mapper": len(mapper_ok),
        "n_mc_runs_with_ppi_hubs": len(hubs_ok),
        "mc_mapper_dominant_counts": _dominant_counts(mapper_ok, "mapper_"),
        "mc_hubs_dominant_counts": _dominant_counts(hubs_ok, "hubs_"),
        "expected_dominant_for_analyte": "plasma" if analyte == "cfdna" else "buffy",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", "-p", type=Path, required=True, help="Project JSON (Plasma or Buffy config)")
    parser.add_argument(
        "--plasma-hubs",
        type=Path,
        required=True,
        help="Reference ppi_hubs.csv from plasma discovery run (signature gene source)",
    )
    parser.add_argument(
        "--buffy-hubs",
        type=Path,
        required=True,
        help="Reference ppi_hubs.csv from buffy discovery run (signature gene source)",
    )
    parser.add_argument(
        "--comparison",
        default="all/PCa",
        help="Comparison subpath under mapper/ and enricher/ (default: all/PCa)",
    )
    parser.add_argument(
        "--signature-size",
        type=int,
        default=25,
        help="Number of top hub genes from each reference ppi_hubs file (default: 25)",
    )
    parser.add_argument(
        "--out",
        "-o",
        type=Path,
        required=True,
        help="Output directory for CSV/JSON summary",
    )
    args = parser.parse_args()

    from methyl_utils import load_project

    project = load_project(args.project)
    analyte = project.get_primary_analyte() or "unknown"

    plasma_genes = _load_signature_genes(args.plasma_hubs, args.signature_size)
    buffy_genes = _load_signature_genes(args.buffy_hubs, args.signature_size)
    plasma_sig = set(plasma_genes)
    buffy_sig = set(buffy_genes)

    filter_kwargs = _enricher_filter_kwargs(args.project)
    contexts = _discover_contexts(args.project, args.comparison)

    rows = [
        evaluate_context(
            ctx,
            filter_kwargs=filter_kwargs,
            plasma_sig=plasma_sig,
            buffy_sig=buffy_sig,
            signature_top_n=args.signature_size,
            analyte=analyte,
        )
        for ctx in contexts
    ]

    args.out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    csv_path = args.out / "signature_recurrence.csv"
    df.to_csv(csv_path, index=False)

    summary = {
        "project_json": str(args.project.resolve()),
        "comparison": args.comparison,
        "signature_size": args.signature_size,
        "plasma_signature_genes": plasma_genes,
        "buffy_signature_genes": buffy_genes,
        "enricher_filters": {k: v for k, v in filter_kwargs.items() if k != "top_n"},
        "enricher_top_n": filter_kwargs.get("top_n"),
        "summary": _summarize_rows(rows, analyte),
        "rows": rows,
    }
    json_path = args.out / "signature_recurrence.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")
    s = summary["summary"]
    print(
        f"Analyte={analyte} MC runs with mapper={s['n_mc_runs_with_mapper']}/{s['n_mc_runs_seen']} "
        f"mapper dominant counts={s['mc_mapper_dominant_counts']}"
    )


if __name__ == "__main__":
    main()
