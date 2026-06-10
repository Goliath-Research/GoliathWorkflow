#!/usr/bin/env python3
"""
Compare raw DMP and mapper gene outputs between plasma and buffy-coat project runs.

DMP locus overlap reads per-chromosome CSVs under detections/<control>/<disease>/.
Both discovery and classifier panels are written by methyl-detector (dual export); use
--dmp-source to choose which set to compare without re-running detection.

  dmps-*-discovery.csv           broad biology / mapper input (default)
  dmps-*-classifier.csv          core model panel (final model candidates)
  dmps-*-classifier-extended.csv classifier + margin (mapper/gene FeatureCuts)

Mapper gene overlap uses mapper/<control>/<disease>/all-gene_name-combined.csv from
whatever DMP panel methyl-mapper was run with (project step_config.mapper.csv_pattern).
Use --mapper-subdir when mapper was run to a separate directory (e.g. mapper_classifier).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd


LocusKey = Tuple[str, int]

DMP_SOURCE_PATTERNS: Dict[str, str] = {
    "discovery": "dmps-*-discovery.csv",
    "classifier": "dmps-*-classifier.csv",
    "classifier-extended": "dmps-*-classifier-extended.csv",
}


def _normalize_chrom(value: object) -> str:
    text = str(value).strip()
    if text.lower().startswith("chr"):
        text = text[3:]
    return text


def _locus_key(row: pd.Series) -> Optional[LocusKey]:
    chrom_col = next((c for c in ("chromosome", "chrom", "chr") if c in row.index), None)
    pos_col = next((c for c in ("position", "pos", "start") if c in row.index), None)
    if chrom_col is None or pos_col is None:
        return None
    try:
        return (_normalize_chrom(row[chrom_col]), int(row[pos_col]))
    except (TypeError, ValueError):
        return None


def load_dmps(detection_dir: Path, dmp_source: str) -> pd.DataFrame:
    pattern = DMP_SOURCE_PATTERNS[dmp_source]
    files = sorted(detection_dir.glob(pattern))
    if dmp_source == "classifier":
        files = [p for p in files if not p.stem.endswith("-classifier-extended")]
    if not files:
        raise FileNotFoundError(f"No {pattern} under {detection_dir}")
    frames = [pd.read_csv(path) for path in files]
    combined = pd.concat(frames, ignore_index=True)
    combined["_locus"] = combined.apply(_locus_key, axis=1)
    combined = combined.dropna(subset=["_locus"])
    return combined


def load_discovery_dmps(detection_dir: Path) -> pd.DataFrame:
    """Backward-compatible alias."""
    return load_dmps(detection_dir, "discovery")


def locus_set(df: pd.DataFrame) -> Set[LocusKey]:
    return set(df["_locus"].tolist())


def jaccard(a: Set[LocusKey], b: Set[LocusKey]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def direction_concordance(
    plasma_df: pd.DataFrame,
    buffy_df: pd.DataFrame,
    shared: Set[LocusKey],
) -> Dict[str, Any]:
    if not shared:
        return {"shared_loci": 0, "concordant": 0, "discordant": 0, "concordance_fraction": None}

    def sign_lookup(df: pd.DataFrame) -> Dict[LocusKey, float]:
        out: Dict[LocusKey, float] = {}
        for _, row in df.iterrows():
            key = row.get("_locus")
            if key not in shared or key in out:
                continue
            if "delta_sign" in row.index and pd.notna(row["delta_sign"]):
                out[key] = float(row["delta_sign"])
            elif "delta_mean" in row.index and pd.notna(row["delta_mean"]):
                out[key] = float(1.0 if row["delta_mean"] > 0 else (-1.0 if row["delta_mean"] < 0 else 0.0))
            elif "effect_size" in row.index and pd.notna(row["effect_size"]):
                out[key] = float(1.0 if row["effect_size"] > 0 else (-1.0 if row["effect_size"] < 0 else 0.0))
        return out

    plasma_sign = sign_lookup(plasma_df)
    buffy_sign = sign_lookup(buffy_df)
    concordant = 0
    discordant = 0
    for key in shared:
        ps = plasma_sign.get(key)
        bs = buffy_sign.get(key)
        if ps is None or bs is None or ps == 0 or bs == 0:
            continue
        if ps == bs:
            concordant += 1
        else:
            discordant += 1
    total = concordant + discordant
    return {
        "shared_loci": len(shared),
        "concordant": concordant,
        "discordant": discordant,
        "concordance_fraction": (concordant / total) if total else None,
    }


def load_gene_names(mapper_dir: Path, gene_column: str = "gene_name") -> Set[str]:
    path = mapper_dir / f"all-{gene_column}-combined.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    if gene_column not in df.columns:
        raise KeyError(f"Column {gene_column!r} not in {path}")
    genes = df[gene_column].dropna().astype(str).str.strip()
    return set(genes[genes != ""].unique())


def gene_jaccard(plasma: Set[str], buffy: Set[str]) -> Dict[str, Any]:
    union = plasma | buffy
    inter = plasma & buffy
    return {
        "plasma_genes": len(plasma),
        "buffy_genes": len(buffy),
        "intersection": len(inter),
        "union": len(union),
        "jaccard": (len(inter) / len(union)) if union else 1.0,
        "plasma_only": sorted(plasma - buffy),
        "buffy_only": sorted(buffy - plasma),
        "shared": sorted(inter),
    }


def write_locus_lists(
    out_dir: Path,
    plasma_loci: Set[LocusKey],
    buffy_loci: Set[LocusKey],
) -> None:
    shared = plasma_loci & buffy_loci
    plasma_only = plasma_loci - buffy_loci
    buffy_only = buffy_loci - plasma_loci

    def to_rows(items: Iterable[LocusKey]) -> pd.DataFrame:
        sorted_items = sorted(items)
        return pd.DataFrame(
            {
                "chromosome": [c for c, _ in sorted_items],
                "position": [p for _, p in sorted_items],
            }
        )

    to_rows(shared).to_csv(out_dir / "dmps_shared_loci.csv", index=False)
    to_rows(plasma_only).to_csv(out_dir / "dmps_plasma_only_loci.csv", index=False)
    to_rows(buffy_only).to_csv(out_dir / "dmps_buffy_only_loci.csv", index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plasma-root", type=Path, required=True, help="Plasma project output root")
    parser.add_argument("--buffy-root", type=Path, required=True, help="Buffy-coat project output root")
    parser.add_argument(
        "--comparison",
        default="all/PCa",
        help="Comparison subpath under detections/ and mapper/ (default: all/PCa)",
    )
    parser.add_argument(
        "--dmp-source",
        choices=sorted(DMP_SOURCE_PATTERNS),
        default="discovery",
        help=(
            "Which detector DMP export to compare (default: discovery). "
            "classifier = core model panel; no re-run needed if methyl-detector already ran."
        ),
    )
    parser.add_argument("--out", type=Path, required=True, help="Directory for summary JSON and CSV lists")
    parser.add_argument("--gene-column", default="gene_name", help="Mapper gene column (default: gene_name)")
    parser.add_argument(
        "--mapper-subdir",
        default="mapper",
        help='Mapper output segment under project root (default: mapper; e.g. mapper_classifier)',
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    control, disease = args.comparison.split("/", 1)
    rel = Path(control) / disease

    plasma_detection = args.plasma_root / "detections" / rel
    buffy_detection = args.buffy_root / "detections" / rel
    plasma_mapper = args.plasma_root / args.mapper_subdir / rel
    buffy_mapper = args.buffy_root / args.mapper_subdir / rel

    plasma_dmps = load_dmps(plasma_detection, args.dmp_source)
    buffy_dmps = load_dmps(buffy_detection, args.dmp_source)
    plasma_loci = locus_set(plasma_dmps)
    buffy_loci = locus_set(buffy_dmps)
    shared_loci = plasma_loci & buffy_loci

    dmp_summary: Dict[str, Any] = {
        "comparison": args.comparison,
        "dmp_source": args.dmp_source,
        "dmp_glob": DMP_SOURCE_PATTERNS[args.dmp_source],
        "plasma_root": str(args.plasma_root),
        "buffy_root": str(args.buffy_root),
        "plasma_dmp_count": len(plasma_loci),
        "buffy_dmp_count": len(buffy_loci),
        "intersection": len(shared_loci),
        "union": len(plasma_loci | buffy_loci),
        "jaccard": jaccard(plasma_loci, buffy_loci),
        "direction_concordance": direction_concordance(plasma_dmps, buffy_dmps, shared_loci),
    }

    plasma_genes = load_gene_names(plasma_mapper, args.gene_column)
    buffy_genes = load_gene_names(buffy_mapper, args.gene_column)
    gene_summary = gene_jaccard(plasma_genes, buffy_genes)
    gene_summary["comparison"] = args.comparison
    gene_summary["mapper_subdir"] = args.mapper_subdir
    gene_summary["plasma_root"] = str(args.plasma_root)
    gene_summary["buffy_root"] = str(args.buffy_root)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "dmp_overlap_summary.json").write_text(json.dumps(dmp_summary, indent=2) + "\n")
    (args.out / "gene_overlap_summary.json").write_text(json.dumps(gene_summary, indent=2) + "\n")

    pd.DataFrame({"gene_name": gene_summary["shared"]}).to_csv(args.out / "genes_shared.csv", index=False)
    pd.DataFrame({"gene_name": gene_summary["plasma_only"]}).to_csv(args.out / "genes_plasma_only.csv", index=False)
    pd.DataFrame({"gene_name": gene_summary["buffy_only"]}).to_csv(args.out / "genes_buffy_only.csv", index=False)
    write_locus_lists(args.out, plasma_loci, buffy_loci)

    print(json.dumps({"dmp": dmp_summary, "genes": {k: gene_summary[k] for k in (
        "plasma_genes", "buffy_genes", "intersection", "union", "jaccard"
    )}}, indent=2))


if __name__ == "__main__":
    main()
