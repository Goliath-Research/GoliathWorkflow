"""Concordance between read-level JSD windows and existing DMP/gene rankings."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .cohort_jsd import TileJsdRecord


def _load_dmp_positions(dmp_csv: Path) -> List[tuple[str, int]]:
    df = pd.read_csv(dmp_csv)
    pos_col = None
    chrom_col = None
    for candidate in ("pos", "position", "start"):
        if candidate in df.columns:
            pos_col = candidate
            break
    for candidate in ("chrom", "chromosome", "chr"):
        if candidate in df.columns:
            chrom_col = candidate
            break
    if pos_col is None:
        return []
    out: List[tuple[str, int]] = []
    for _, row in df.iterrows():
        chrom = str(row[chrom_col]) if chrom_col else ""
        if chrom_col and chrom.startswith("chr"):
            chrom = chrom[3:]
        try:
            pos = int(row[pos_col])
        except (TypeError, ValueError):
            continue
        out.append((chrom, pos))
    return out


def _tile_overlaps_dmp(record: TileJsdRecord, dmp_loci: Sequence[tuple[str, int]]) -> bool:
    positions = set(record.tile_cpg_positions)
    for chrom, pos in dmp_loci:
        if str(chrom) != str(record.chrom):
            continue
        if int(pos) in positions or int(pos) == int(record.tile_start_pos):
            return True
    return False


def build_confirmation_report(
    jsd_records: Sequence[TileJsdRecord],
    *,
    dmp_panel_csv: Optional[str] = None,
    mapper_gene_csv: Optional[str] = None,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "n_jsd_windows": int(len(jsd_records)),
        "top_jsd": [
            {
                "chrom": r.chrom,
                "context": r.context,
                "tile_start_pos": r.tile_start_pos,
                "jsd": r.jsd,
                "n_reads_group1": r.n_reads_group1,
                "n_reads_group2": r.n_reads_group2,
            }
            for r in jsd_records[:20]
        ],
    }

    if dmp_panel_csv:
        dmp_path = Path(dmp_panel_csv)
        if dmp_path.is_file():
            loci = _load_dmp_positions(dmp_path)
            if loci and jsd_records:
                overlaps = sum(1 for r in jsd_records if _tile_overlaps_dmp(r, loci))
                report["dmp_concordance"] = {
                    "dmp_panel_csv": str(dmp_path.resolve()),
                    "n_dmp_loci": int(len(loci)),
                    "n_jsd_windows": int(len(jsd_records)),
                    "n_overlapping_windows": int(overlaps),
                    "overlap_fraction": float(overlaps / len(jsd_records)),
                }

    if mapper_gene_csv:
        mapper_path = Path(mapper_gene_csv)
        if mapper_path.is_file() and jsd_records:
            mapper_df = pd.read_csv(mapper_path)
            if "gene_name" in mapper_df.columns and "gene_importance" in mapper_df.columns:
                # Without per-gene JSD from genomic mapping, compare rank lists using
                # gene_importance vs a uniform JSD placeholder is not meaningful.
                # If intersections exist alongside mapper CSV, map tile midpoints to genes.
                mapper_dir = mapper_path.parent
                intersection_files = sorted(mapper_dir.glob("*-intersections.csv"))
                gene_jsd: Dict[str, List[float]] = {}
                if intersection_files:
                    for record in jsd_records:
                        mid = int(np.median(record.tile_cpg_positions))
                        for ix_path in intersection_files:
                            ix = pd.read_csv(ix_path)
                            if "gene_name" not in ix.columns or "pos" not in ix.columns:
                                continue
                            chrom_col = "chrom" if "chrom" in ix.columns else None
                            for _, row in ix.iterrows():
                                if chrom_col and str(row[chrom_col]).replace("chr", "") != str(record.chrom):
                                    continue
                                try:
                                    pos = int(row["pos"])
                                except (TypeError, ValueError):
                                    continue
                                if abs(pos - mid) <= 500:
                                    gene = str(row["gene_name"]).strip()
                                    if gene:
                                        gene_jsd.setdefault(gene, []).append(record.jsd)
                if gene_jsd:
                    jsd_rank = pd.DataFrame(
                        {
                            "gene_name": list(gene_jsd.keys()),
                            "mean_jsd": [float(np.mean(v)) for v in gene_jsd.values()],
                        }
                    )
                    merged = jsd_rank.merge(
                        mapper_df[["gene_name", "gene_importance"]],
                        on="gene_name",
                        how="inner",
                    )
                    if len(merged) >= 3:
                        rho, pval = spearmanr(
                            merged["mean_jsd"].astype(float),
                            merged["gene_importance"].astype(float),
                        )
                        top_k = min(50, len(merged))
                        top_jsd = set(
                            merged.sort_values("mean_jsd", ascending=False)
                            .head(top_k)["gene_name"]
                            .astype(str)
                        )
                        top_imp = set(
                            merged.sort_values("gene_importance", ascending=False)
                            .head(top_k)["gene_name"]
                            .astype(str)
                        )
                        report["gene_concordance"] = {
                            "mapper_gene_csv": str(mapper_path.resolve()),
                            "n_genes_compared": int(len(merged)),
                            "spearman_rho": float(rho) if np.isfinite(rho) else None,
                            "spearman_pvalue": float(pval) if np.isfinite(pval) else None,
                            "top_k": int(top_k),
                            "top_k_overlap": int(len(top_jsd & top_imp)),
                            "top_k_overlap_fraction": float(len(top_jsd & top_imp) / top_k),
                        }
                else:
                    report["gene_concordance"] = {
                        "mapper_gene_csv": str(mapper_path.resolve()),
                        "skipped": True,
                        "reason": "no_intersection_files_for_gene_jsd_mapping",
                    }

    return report
