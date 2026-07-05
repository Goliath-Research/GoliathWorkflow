"""Per-sample readlevel:: feature rows from pattern sidecars."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence

import numpy as np

from methyl_utils.core.read_level_io import discover_pattern_files, load_read_level_patterns

from ..config import InfoTheoryStepConfig
from .patterns import aggregate_file_measures


def _chrom_from_path(path: Path) -> str:
    stem = path.name.replace(".patterns.h5", "")
    if "-" in stem:
        return stem.split("-", 1)[0]
    return stem


def compute_sample_readlevel_measures(
    sample_id: str,
    sample_dir: str,
    *,
    chromosomes: Sequence[str],
    contexts: Sequence[str],
    cfg: InfoTheoryStepConfig,
) -> Dict[str, Any]:
    min_reads = int(cfg.min_tile_reads) if cfg.min_tile_reads is not None else 1
    row: Dict[str, Any] = {str(cfg.sample_id_column): str(sample_id)}

    chrom_acc: Dict[str, Dict[str, List[float]]] = {}
    global_acc = {
        "entropy": [],
        "epipolymorphism": [],
        "pdr": [],
        "weight": [],
    }

    paths = discover_pattern_files(sample_dir, chromosomes, contexts)
    for path in paths:
        try:
            patterns = load_read_level_patterns(path)
        except Exception:
            continue
        if cfg.tile_size is not None and int(patterns.tile_size) != int(cfg.tile_size):
            continue
        agg = aggregate_file_measures(patterns, min_tile_reads=min_reads)
        if not np.isfinite(agg["entropy"]):
            continue
        chrom = _chrom_from_path(path)
        bucket = chrom_acc.setdefault(
            chrom,
            {"entropy": [], "epipolymorphism": [], "pdr": [], "weight": []},
        )
        w = float(agg["n_tiles"])
        bucket["entropy"].append(agg["entropy"] * w)
        bucket["epipolymorphism"].append(agg["epipolymorphism"] * w)
        bucket["pdr"].append(agg["pdr"] * w)
        bucket["weight"].append(w)
        global_acc["entropy"].append(agg["entropy"] * w)
        global_acc["epipolymorphism"].append(agg["epipolymorphism"] * w)
        global_acc["pdr"].append(agg["pdr"] * w)
        global_acc["weight"].append(w)

    def _wmean(acc: Dict[str, List[float]], key: str) -> float:
        weights = acc.get("weight") or []
        if not weights:
            return float("nan")
        w_sum = float(np.sum(weights))
        vals = acc.get(key) or []
        if not vals or w_sum <= 0.0:
            return float("nan")
        return float(np.sum(vals) / w_sum)

    row["readlevel::global_entropy"] = _wmean(global_acc, "entropy")
    row["readlevel::global_epipolymorphism"] = _wmean(global_acc, "epipolymorphism")
    row["readlevel::global_pdr"] = _wmean(global_acc, "pdr")
    row["readlevel::n_pattern_files"] = float(len(paths))

    for chrom in chromosomes:
        acc = chrom_acc.get(str(chrom), {"entropy": [], "epipolymorphism": [], "pdr": [], "weight": []})
        row[f"readlevel::chrom_{chrom}::entropy"] = _wmean(acc, "entropy")
        row[f"readlevel::chrom_{chrom}::epipolymorphism"] = _wmean(acc, "epipolymorphism")
        row[f"readlevel::chrom_{chrom}::pdr"] = _wmean(acc, "pdr")

    return row
