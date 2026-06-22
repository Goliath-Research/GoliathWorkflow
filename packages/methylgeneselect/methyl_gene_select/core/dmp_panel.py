"""Load classifier DMP panels from MC run directories."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Tuple

import pandas as pd


def _dmp_key_from_row(row: Any) -> Tuple[Any, int]:
    chrom = row["chromosome"]
    try:
        chrom_n = int(chrom)
    except (TypeError, ValueError):
        chrom_n = str(chrom).strip()
    return (chrom_n, int(row["position"]))


def load_classifier_dmp_panel(
    run_dir: Path,
    *,
    max_dmps: Optional[int] = None,
) -> Optional[pd.DataFrame]:
    """
    Load detector classifier DMP panel for gene-axis work.

    Prefers ``dmps-*-classifier-extended.csv``, else core classifier CSV.
    """
    detection_dirs = list(run_dir.glob("**/detections/*/*"))
    if not detection_dirs:
        detection_dirs = list(run_dir.glob("detections/*/*"))
    frames: list = []
    for d in detection_dirs:
        csvs = sorted(d.glob("dmps-*-classifier-extended.csv"))
        if not csvs:
            csvs = sorted(
                p
                for p in d.glob("dmps-*-classifier.csv")
                if not p.stem.endswith("-classifier-extended")
            )
        for csv in csvs:
            try:
                frames.append(pd.read_csv(csv))
            except Exception:
                continue
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    if df.empty:
        return df
    if "chromosome" not in df.columns or "position" not in df.columns:
        return df

    work = df.copy()
    if "effect_size" not in work.columns:
        work["effect_size"] = 0.0
    work["_abs_effect"] = pd.to_numeric(work["effect_size"], errors="coerce").fillna(0.0).abs()
    keys: List[Tuple[Any, int]] = []
    for _, row in work.iterrows():
        try:
            keys.append(_dmp_key_from_row(row))
        except Exception:
            keys.append((None, -1))
    work["_dmp_key"] = keys
    work = work[work["_dmp_key"].map(lambda k: k[1] >= 0)].copy()
    work = work.sort_values(["_abs_effect"], ascending=False, na_position="last")
    work = work.drop_duplicates(subset=["_dmp_key"], keep="first")
    if max_dmps is not None and int(max_dmps) > 0 and len(work) > int(max_dmps):
        work = work.head(int(max_dmps)).copy()
    return work.drop(columns=["_abs_effect", "_dmp_key"], errors="ignore")
