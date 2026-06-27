#!/usr/bin/env python3
"""Compare production freeze bundles (genes, DMPs) between plasma and buffy projects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Set

import pandas as pd


def _gene_set(path: Path, column: str = "gene_name") -> Set[str]:
    if not path.is_file():
        return set()
    df = pd.read_csv(path)
    col = column if column in df.columns else df.columns[0]
    vals = df[col].dropna().astype(str).str.strip()
    return set(vals[vals != ""].unique())


def _dmp_loci(path: Path) -> Set[tuple[str, int]]:
    if not path.is_file():
        return set()
    df = pd.read_csv(path)
    chrom = next((c for c in ("chromosome", "chrom", "chr") if c in df.columns), None)
    pos = next((c for c in ("position", "pos", "start") if c in df.columns), None)
    if chrom is None or pos is None:
        return set()
    out: Set[tuple[str, int]] = set()
    for _, row in df.iterrows():
        try:
            c = str(row[chrom]).strip()
            if c.lower().startswith("chr"):
                c = c[3:]
            out.add((c, int(row[pos])))
        except (TypeError, ValueError):
            continue
    return out


def _jaccard(a: Set[Any], b: Set[Any]) -> float:
    if not a and not b:
        return 1.0
    u = a | b
    return len(a & b) / len(u) if u else 0.0


def compare_production(plasma_root: Path, buffy_root: Path) -> Dict[str, Any]:
    plasma_prod = plasma_root / "monte_carlo_runs" / "production"
    buffy_prod = buffy_root / "monte_carlo_runs" / "production"

    plasma_genes = _gene_set(plasma_prod / "model_bundle" / "frozen_genes_production.csv")
    buffy_genes = _gene_set(buffy_prod / "model_bundle" / "frozen_genes_production.csv")
    shared_genes = plasma_genes & buffy_genes

    plasma_dmps = _dmp_loci(plasma_prod / "stable_dmps_genomewide.csv")
    buffy_dmps = _dmp_loci(buffy_prod / "stable_dmps_genomewide.csv")

    def _read_json(path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    pmv_plasma = _read_json(plasma_root / "monte_carlo_runs" / "post_model_validation" / "metrics_summary.json")
    pmv_buffy = _read_json(buffy_root / "monte_carlo_runs" / "post_model_validation" / "metrics_summary.json")

    return {
        "plasma_root": str(plasma_root),
        "buffy_root": str(buffy_root),
        "frozen_genes": {
            "plasma": len(plasma_genes),
            "buffy": len(buffy_genes),
            "intersection": len(shared_genes),
            "jaccard": _jaccard(plasma_genes, buffy_genes),
            "shared": sorted(shared_genes),
        },
        "stable_dmps_genomewide": {
            "plasma": len(plasma_dmps),
            "buffy": len(buffy_dmps),
            "intersection": len(plasma_dmps & buffy_dmps),
            "jaccard": _jaccard(plasma_dmps, buffy_dmps),
        },
        "production_summary": {
            "plasma": _read_json(plasma_prod / "production_summary.json"),
            "buffy": _read_json(buffy_prod / "production_summary.json"),
        },
        "post_model_validation": {
            "plasma": pmv_plasma,
            "buffy": pmv_buffy,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plasma-root", type=Path, required=True)
    parser.add_argument("--buffy-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = compare_production(args.plasma_root, args.buffy_root)
    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / "freeze_overlap.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame({"gene_name": result["frozen_genes"]["shared"]}).to_csv(
        args.out / "frozen_genes_shared.csv", index=False
    )
    print(json.dumps({k: result[k] for k in ("frozen_genes", "stable_dmps_genomewide")}, indent=2))


if __name__ == "__main__":
    main()
