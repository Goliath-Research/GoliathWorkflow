"""
Merge DMP CSVs from multiple per-cancer detection dirs for multiclass model building.
"""

from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd


DMP_GLOB = "dmps-*.csv"
REQUIRED_COLS = {"chromosome", "context", "position"}
WEIGHT_COLS = ["importance", "effect_size", "weight"]


def _find_dmp_csvs(detection_dir: Path) -> List[Path]:
    """Return list of dmps-*.csv paths in detection_dir (empty if dir missing)."""
    if not detection_dir.exists():
        return []
    return sorted(detection_dir.glob(DMP_GLOB))


def check_detection_dirs_have_dmps(
    configs_and_labels: List[Tuple[object, str]],
    output_dir_attr: str = "output_dir",
) -> List[Tuple[Path, str]]:
    """
    Check that each (config, label) has at least one dmps-*.csv in config.output_dir.
    Returns list of (output_dir, label) that are missing DMP CSVs.
    """
    missing = []
    for config, label in configs_and_labels:
        out_dir = Path(getattr(config, output_dir_attr, config))
        csvs = _find_dmp_csvs(out_dir)
        if not csvs:
            missing.append((out_dir, label))
    return missing


def merge_dmp_csvs_from_detection_dirs(
    detection_dirs: List[Path],
    merged_path: Path,
    weights_column: Optional[str] = "importance",
) -> Path:
    """
    Read all dmps-*.csv from each detection dir, union by (chromosome, context, position),
    and write one merged CSV. For duplicate positions, keep the row with highest weight
    (importance/effect_size/weight) if present.
    """
    frames = []
    for ddir in detection_dirs:
        for csv_path in _find_dmp_csvs(ddir):
            df = pd.read_csv(csv_path)
            if not REQUIRED_COLS.issubset(df.columns):
                continue
            frames.append(df)
    if not frames:
        raise ValueError(
            f"No DMP CSVs found under the given detection dirs; expected {DMP_GLOB} in each."
        )
    combined = pd.concat(frames, ignore_index=True)
    combined["chromosome"] = combined["chromosome"].astype(str)
    combined["context"] = combined["context"].astype(str)
    combined["position"] = combined["position"].astype(np.uint32)

    # Choose weight column
    weight_col = None
    if weights_column and weights_column in combined.columns:
        weight_col = weights_column
    else:
        for c in WEIGHT_COLS:
            if c in combined.columns:
                weight_col = c
                break
    if weight_col is None:
        combined["importance"] = 1.0
        weight_col = "importance"

    # Deduplicate by (chromosome, context, position), keeping row with max weight
    combined = combined.sort_values(weight_col, ascending=False)
    merged = combined.drop_duplicates(subset=["chromosome", "context", "position"], keep="first")
    merged = merged.reset_index(drop=True)

    merged_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(merged_path, index=False)
    return merged_path
