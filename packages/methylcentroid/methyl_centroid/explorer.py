"""
MethylCentroidExplorer: Inspect a MethylFrame (single H5 or folder of H5 files).
Identifies type (MethylSample, MethylBasicCentroid, MethylExtendedCentroid, MethylBetaBinomialCentroid),
prints metadata, and optionally describes a range of positions in detail.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import h5py
except ImportError:
    h5py = None

import numpy as np
import pandas as pd


def _get_methyl_group(f) -> Any:
    """Return the group containing pos, mC, uC, tnc (methylation_data or root)."""
    if "methylation_data" in f and hasattr(f["methylation_data"], "keys"):
        return f["methylation_data"]
    return f


def _detect_type_from_keys(keys: List[str]) -> str:
    """Infer MethylFrame type from HDF5 dataset keys (without loading data)."""
    keys_set = set(keys)
    if "N" not in keys_set:
        return "MethylSample"
    if not {"Sx", "Sx2", "log_x_sum", "log_1_minus_x_sum"}.issubset(keys_set):
        return "MethylBasicCentroid"
    bb = {"sum_mC", "sum_uC", "sum_cov", "sum_cov2", "sum_mC2", "sum_uC2", "Sx3", "Sx4", "count_zero", "count_one"}
    if bb.issubset(keys_set):
        return "MethylBetaBinomialCentroid"
    return "MethylExtendedCentroid"


def get_frame_info(path: Path) -> Tuple[str, int, Dict[str, Any], List[str]]:
    """
    Read HDF5 without loading full data. Returns (type_name, n_positions, metadata, dataset_keys).
    """
    if not h5py:
        raise RuntimeError("h5py is required for MethylCentroidExplorer")
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Not a file: {path}")
    with h5py.File(path, "r") as f:
        group = _get_methyl_group(f)
        if isinstance(group, h5py.Group):
            keys = list(group.keys())
        else:
            keys = list(f.keys())
        required = {"pos", "mC", "uC", "tnc"}
        if not required.issubset(set(keys)):
            raise ValueError(f"Missing required datasets {required - set(keys)} in {path}")
        pos_ds = group["pos"] if "pos" in group.keys() else f["pos"]
        n_positions = int(pos_ds.shape[0])
        type_name = _detect_type_from_keys(keys)
        metadata = {}
        for name, value in f.attrs.items():
            try:
                if isinstance(value, (bytes, str)):
                    s = value.decode("utf-8") if isinstance(value, bytes) else value
                    metadata[name] = json.loads(s)
                else:
                    metadata[name] = value
            except (json.JSONDecodeError, TypeError):
                metadata[name] = value
        return type_name, n_positions, metadata, keys


def get_positions_in_range(path: Path, pos_start: int, pos_end: int) -> np.ndarray:
    """Read pos dataset and return positions that fall in [pos_start, pos_end] (inclusive)."""
    if not h5py:
        raise RuntimeError("h5py is required")
    path = Path(path)
    with h5py.File(path, "r") as f:
        group = _get_methyl_group(f)
        pos_ds = group["pos"]
        pos = np.asarray(pos_ds[:], dtype=np.uint32)
    mask = (pos >= pos_start) & (pos <= pos_end)
    return np.unique(pos[mask])


def load_frame(path: Path, positions: Optional[np.ndarray] = None):
    """Load a MethylFrame from H5; optionally only for given positions. Returns the methyl_utils object."""
    from methyl_utils.core.io import load_from_h5
    return load_from_h5(path, positions=positions)


def _safe_series_values(obj, name: str):
    """Get values from a DataFrame column or property; return list for JSON/print."""
    try:
        s = getattr(obj, name, None)
        if s is None and hasattr(obj, "_df") and name in obj._df.columns:
            s = obj._df[name]
        if s is not None:
            v = s.values if hasattr(s, "values") else np.asarray(s)
            return np.asarray(v).tolist()
    except Exception:
        pass
    return None


def build_position_table(frame, pos_start: int, pos_end: int) -> pd.DataFrame:
    """
    Build a per-position table with pos, mC, uC, coverage, mean, and type-specific fields
    (N, Sx, Sx2, alpha, beta, variance for centroids).
    """
    frame = frame.to_cpu()
    df = frame._df.copy()
    pos = np.asarray(df["pos"])
    mask = (pos >= pos_start) & (pos <= pos_end)
    df = df.loc[mask].copy()
    if len(df) == 0:
        return pd.DataFrame()
    # Trigger alpha/beta on the full frame so they are in _df, then copy to our slice
    if hasattr(frame, "alpha"):
        try:
            _ = frame.alpha
            _ = frame.beta
            if "alpha" in frame._df.columns and "beta" in frame._df.columns:
                df["alpha"] = frame._df.loc[df.index, "alpha"].values
                df["beta"] = frame._df.loc[df.index, "beta"].values
        except Exception:
            pass
    rows = []
    for _, row in df.iterrows():
        r = {"pos": int(row["pos"]), "mC": int(row["mC"]), "uC": int(row["uC"])}
        cov = int(row["mC"]) + int(row["uC"])
        r["coverage"] = cov
        r["mean"] = (int(row["mC"]) / cov) if cov > 0 else None
        if "N" in df.columns:
            r["N"] = int(row["N"])
        if "Sx" in df.columns:
            r["Sx"] = float(row["Sx"])
        if "Sx2" in df.columns:
            r["Sx2"] = float(row["Sx2"])
        if "log_x_sum" in df.columns:
            r["log_x_sum"] = float(row["log_x_sum"])
        if "log_1_minus_x_sum" in df.columns:
            r["log_1_minus_x_sum"] = float(row["log_1_minus_x_sum"])
        a = float(row["alpha"]) if "alpha" in df.columns else None
        b = float(row["beta"]) if "beta" in df.columns else None
        r["alpha"] = a
        r["beta"] = b
        if a is not None and b is not None and (a + b) > 0:
            r["variance"] = (a * b) / ((a + b) ** 2 * (a + b + 1))
        else:
            r["variance"] = None
        rows.append(r)
    return pd.DataFrame(rows)


def list_h5_in_folder(folder: Path) -> List[Path]:
    """Return sorted list of .h5 files in folder (non-recursive)."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.h5"))


def run_explorer(
    path: Path,
    *,
    file_filter: Optional[str] = None,
    chrom: Optional[str] = None,
    context: Optional[str] = None,
    pos_start: Optional[int] = None,
    pos_end: Optional[int] = None,
    max_positions: int = 10_000,
    json_metadata: bool = False,
) -> None:
    """
    Main explorer logic: resolve path (file or folder), detect type, print metadata,
    optionally print position range detail.
    """
    path = Path(path).resolve()
    if path.is_file():
        target = path
    elif path.is_dir():
        h5_files = list_h5_in_folder(path)
        if not h5_files:
            print(f"No .h5 files in {path}", file=sys.stderr)
            return
        if file_filter:
            h5_files = [p for p in h5_files if file_filter in p.name]
        if chrom or context:
            # e.g. 1-CG.h5
            parts = []
            if chrom:
                parts.append(str(chrom))
            if context:
                parts.append(str(context))
            pattern = "-".join(parts)
            h5_files = [p for p in h5_files if pattern in p.name or p.name.startswith(pattern + "-")]
        if not h5_files:
            print("No matching .h5 file after filter.", file=sys.stderr)
            return
        # If multiple, show first or list and pick first for detail
        if len(h5_files) > 1 and (pos_start is not None or pos_end is not None):
            print(f"Multiple files match; using first: {h5_files[0].name}", file=sys.stderr)
        target = h5_files[0]
        target = Path(target) if not isinstance(target, Path) else target
    else:
        print(f"Path not found: {path}", file=sys.stderr)
        return

    type_name, n_positions, metadata, keys = get_frame_info(target)
    print(f"Path: {target}")
    print(f"Type: {type_name}")
    print(f"Positions: {n_positions:,}")
    print(f"Datasets: {', '.join(sorted(keys))}")
    if json_metadata:
        print("Metadata (JSON):")
        print(json.dumps(metadata, indent=2, default=str))
    else:
        print("Metadata:")
        for k, v in metadata.items():
            print(f"  {k}: {v}")

    if pos_start is not None or pos_end is not None:
        pos_start = pos_start if pos_start is not None else 0
        pos_end = pos_end if pos_end is not None else (1 << 32) - 1
        positions_to_load = get_positions_in_range(target, pos_start, pos_end)
        if len(positions_to_load) == 0:
            print(f"No positions in range [{pos_start}, {pos_end}].", file=sys.stderr)
            return
        if len(positions_to_load) > max_positions:
            print(f"Range has {len(positions_to_load):,} positions; capping to {max_positions} (use --max-positions to change).", file=sys.stderr)
            positions_to_load = positions_to_load[:max_positions]
        frame = load_frame(target, positions=positions_to_load)
        table = build_position_table(frame, pos_start, pos_end)
        if table is None or len(table) == 0:
            print("No rows in position table.")
            return
        pd.set_option("display.max_rows", None)
        pd.set_option("display.width", None)
        print("\nPosition detail (first rows):")
        print(table.head(500).to_string(index=False))
        if len(table) > 500:
            print(f"... and {len(table) - 500} more rows.")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="MethylCentroidExplorer: Inspect a MethylFrame (folder or .h5 file), detect type, print metadata, and optionally describe a range of positions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("path", type=Path, help="Path to a MethylFrame folder or a single .h5 file")
    parser.add_argument("--file", dest="file_filter", metavar="SUBSTR", help="If path is a folder, only consider .h5 files whose name contains SUBSTR (e.g. '1-CG')")
    parser.add_argument("--chrom", "-c", help="If path is a folder, filter to .h5 files for this chromosome (e.g. 1)")
    parser.add_argument("--context", "-x", choices=["CG", "CHG", "CHH"], help="If path is a folder, filter to this context")
    parser.add_argument("--pos-start", type=int, default=None, metavar="POS", help="Start of position range (inclusive) for per-position detail")
    parser.add_argument("--pos-end", type=int, default=None, metavar="POS", help="End of position range (inclusive) for per-position detail")
    parser.add_argument("--max-positions", type=int, default=10_000, metavar="N", help="Maximum number of positions to load for detail (default 10000)")
    parser.add_argument("--json-metadata", action="store_true", help="Print metadata as JSON")
    args = parser.parse_args()
    run_explorer(
        args.path,
        file_filter=args.file_filter,
        chrom=args.chrom,
        context=args.context,
        pos_start=args.pos_start,
        pos_end=args.pos_end,
        max_positions=args.max_positions,
        json_metadata=args.json_metadata,
    )


if __name__ == "__main__":
    main()
