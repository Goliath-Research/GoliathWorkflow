# methyl_utils/core/io.py
from pathlib import Path
from typing import Optional, Union
import hdf5plugin  # noqa: F401 - Must be imported before h5py
import h5py
import numpy as np
import pandas as pd
from .methyl_frame import MethylExtendedCentroid, MethylBasicCentroid, MethylSample, MethylBetaBinomialCentroid


def _indices_for_positions(pos_arr: np.ndarray, positions: np.ndarray):
    """Return row indices where pos_arr is in positions (same as align_to_positions subset)."""
    want = np.asarray(positions, dtype=np.uint32)
    mask = np.isin(pos_arr, want)
    return np.flatnonzero(mask)


def load_pos_from_h5(path: Union[str, Path]) -> np.ndarray:
    """
    Load only the position array from an HDF5 methylation file (lightweight read for indexing).
    Use with load_from_h5(path, indices=...) to avoid reading the full file repeatedly.
    Supports the same three formats as load_from_h5: methylation_data as Group, as compound
    Dataset (structured array), or pos at root.
    """
    path = Path(path)
    with h5py.File(path, "r") as f:
        if "methylation_data" in f:
            group = f["methylation_data"]
            if isinstance(group, h5py.Group) and "pos" in group:
                return np.asarray(group["pos"][:], dtype=np.uint32)
            if isinstance(group, h5py.Dataset) and group.dtype.names and "pos" in group.dtype.names:
                return np.asarray(group["pos"][:], dtype=np.uint32)
        if "pos" in f:
            return np.asarray(f["pos"][:], dtype=np.uint32)
    raise ValueError(f"No 'pos' dataset found in {path}")


def load_from_h5(
    path: Union[str, Path],
    positions: Optional[np.ndarray] = None,
    indices: Optional[np.ndarray] = None,
) -> MethylExtendedCentroid | MethylBasicCentroid | MethylSample | MethylBetaBinomialCentroid:
    """
    Load methylation data from HDF5 file.

    When positions is provided, only those rows are read from disk (hyperslice).
    When indices is provided, only those row indices are read (no full pos read); use with
    load_pos_from_h5() + _indices_for_positions for chunked centroid building.

    Supports both new and old formats:
    - New format: Datasets stored in 'methylation_data' group
    - Old format: Datasets stored at root level or 'methylation_data' as structured array

    Args:
        path: Path to HDF5 file
        positions: Optional array of positions to load; if set, only these rows are read (saves memory).
        indices: Optional integer array of row indices; if set, only these rows are read (avoids full pos read).

    Returns:
        MethylSample, MethylBasicCentroid, or MethylExtendedCentroid instance

    Raises:
        ValueError: If file doesn't have required datasets in any format
        KeyError: If required datasets are missing
    """
    path = Path(path)
    with h5py.File(path, "r") as f:
        data = {}
        datasets = []
        methyl_data = None

        # Try new format first: 'methylation_data' as a group
        if "methylation_data" in f:
            methyl_data = f["methylation_data"]
            if isinstance(methyl_data, h5py.Group):
                datasets = list(methyl_data.keys())
                # Check for required core datasets
                required_core = ["pos", "mC", "uC", "tnc"]
                missing = [d for d in required_core if d not in datasets]
                if not missing:
                    if indices is not None:
                        idx = np.asarray(indices, dtype=np.intp)
                        data = {
                            "pos": np.asarray(methyl_data["pos"][idx], dtype=np.uint32),
                            "mC": np.asarray(methyl_data["mC"][idx], dtype=np.uint32),
                            "uC": np.asarray(methyl_data["uC"][idx], dtype=np.uint32),
                            "tnc": np.asarray(methyl_data["tnc"][idx], dtype=np.uint8),
                        }
                    elif positions is not None:
                        pos_arr = np.asarray(methyl_data["pos"][:], dtype=np.uint32)
                        idx = _indices_for_positions(pos_arr, positions)
                        data = {
                            "pos": np.asarray(methyl_data["pos"][idx], dtype=np.uint32),
                            "mC": np.asarray(methyl_data["mC"][idx], dtype=np.uint32),
                            "uC": np.asarray(methyl_data["uC"][idx], dtype=np.uint32),
                            "tnc": np.asarray(methyl_data["tnc"][idx], dtype=np.uint8),
                        }
                    else:
                        idx = None
                        data = {
                            "pos": np.asarray(methyl_data["pos"][:], dtype=np.uint32),
                            "mC": np.asarray(methyl_data["mC"][:], dtype=np.uint32),
                            "uC": np.asarray(methyl_data["uC"][:], dtype=np.uint32),
                            "tnc": np.asarray(methyl_data["tnc"][:], dtype=np.uint8),
                        }
                    # Load optional centroid datasets
                    if "N" in datasets:
                        if indices is not None or positions is not None:
                            data["N"] = np.asarray(methyl_data["N"][idx], dtype=np.uint32)
                        else:
                            data["N"] = np.asarray(methyl_data["N"][:], dtype=np.uint32)
                    for col in ["Sx", "Sx2", "log_x_sum", "log_1_minus_x_sum"]:
                        if col in datasets:
                            if indices is not None or positions is not None:
                                data[col] = np.asarray(methyl_data[col][idx], dtype=np.float32)
                            else:
                                data[col] = np.asarray(methyl_data[col][:], dtype=np.float32)
                    # Extended sufficient statistics (optional)
                    extra_cols = {
                        "sum_mC": np.uint64,
                        "sum_uC": np.uint64,
                        "sum_cov": np.uint64,
                        "sum_cov2": np.float64,
                        "sum_mC2": np.float64,
                        "sum_uC2": np.float64,
                        "Sx3": np.float32,
                        "Sx4": np.float32,
                        "count_zero": np.uint32,
                        "count_one": np.uint32,
                    }
                    for col, dtype_cast in extra_cols.items():
                        if col in datasets:
                            if indices is not None or positions is not None:
                                data[col] = np.asarray(methyl_data[col][idx], dtype=dtype_cast)
                            else:
                                data[col] = np.asarray(methyl_data[col][:], dtype=dtype_cast)

        # Fallback to old format: datasets at root level
        if not data:
            root_keys = list(f.keys())
            required_core = ["pos", "mC", "uC", "tnc"]

            # Check if required datasets exist at root level
            missing = [d for d in required_core if d not in root_keys]
            if not missing:
                datasets = root_keys
                if indices is not None:
                    idx = np.asarray(indices, dtype=np.intp)
                    data = {
                        "pos": np.asarray(f["pos"][idx], dtype=np.uint32),
                        "mC": np.asarray(f["mC"][idx], dtype=np.uint32),
                        "uC": np.asarray(f["uC"][idx], dtype=np.uint32),
                        "tnc": np.asarray(f["tnc"][idx], dtype=np.uint8),
                    }
                elif positions is not None:
                    pos_arr = np.asarray(f["pos"][:], dtype=np.uint32)
                    idx = _indices_for_positions(pos_arr, positions)
                    data = {
                        "pos": np.asarray(f["pos"][idx], dtype=np.uint32),
                        "mC": np.asarray(f["mC"][idx], dtype=np.uint32),
                        "uC": np.asarray(f["uC"][idx], dtype=np.uint32),
                        "tnc": np.asarray(f["tnc"][idx], dtype=np.uint8),
                    }
                else:
                    idx = None
                    data = {
                        "pos": np.asarray(f["pos"][:], dtype=np.uint32),
                        "mC": np.asarray(f["mC"][:], dtype=np.uint32),
                        "uC": np.asarray(f["uC"][:], dtype=np.uint32),
                        "tnc": np.asarray(f["tnc"][:], dtype=np.uint8),
                    }
                # Load optional centroid datasets
                if "N" in root_keys:
                    if indices is not None or positions is not None:
                        data["N"] = np.asarray(f["N"][idx], dtype=np.uint32)
                    else:
                        data["N"] = np.asarray(f["N"][:], dtype=np.uint32)
                for col in ["Sx", "Sx2", "log_x_sum", "log_1_minus_x_sum"]:
                    if col in root_keys:
                        if indices is not None or positions is not None:
                            data[col] = np.asarray(f[col][idx], dtype=np.float32)
                        else:
                            data[col] = np.asarray(f[col][:], dtype=np.float32)
                # Extended sufficient statistics (optional)
                extra_cols = {
                    "sum_mC": np.uint64,
                    "sum_uC": np.uint64,
                    "sum_cov": np.uint64,
                    "sum_cov2": np.float64,
                    "sum_mC2": np.float64,
                    "sum_uC2": np.float64,
                    "Sx3": np.float32,
                    "Sx4": np.float32,
                    "count_zero": np.uint32,
                    "count_one": np.uint32,
                }
                for col, dtype_cast in extra_cols.items():
                    if col in root_keys:
                        if indices is not None or positions is not None:
                            data[col] = np.asarray(f[col][idx], dtype=dtype_cast)
                        else:
                            data[col] = np.asarray(f[col][:], dtype=dtype_cast)
        
        # Fallback to old format: 'methylation_data' as structured array
        if not data and "methylation_data" in f:
            methyl_data = f["methylation_data"]
            if isinstance(methyl_data, h5py.Dataset) and methyl_data.dtype.names:
                # Structured array format (single dataset; must load then filter if positions set)
                struct_data = methyl_data[:]
                datasets = list(methyl_data.dtype.names)
                required_core = ["pos", "mC", "uC", "tnc"]
                missing = [d for d in required_core if d not in datasets]
                if not missing:
                    pos_arr = np.asarray(struct_data["pos"], dtype=np.uint32)
                    if positions is not None:
                        idx = _indices_for_positions(pos_arr, positions)
                        data = {
                            "pos": np.asarray(struct_data["pos"][idx], dtype=np.uint32),
                            "mC": np.asarray(struct_data["mC"][idx], dtype=np.uint32),
                            "uC": np.asarray(struct_data["uC"][idx], dtype=np.uint32),
                            "tnc": np.asarray(struct_data["tnc"][idx], dtype=np.uint8),
                        }
                    else:
                        data = {
                            "pos": np.asarray(struct_data["pos"], dtype=np.uint32),
                            "mC": np.asarray(struct_data["mC"], dtype=np.uint32),
                            "uC": np.asarray(struct_data["uC"], dtype=np.uint32),
                            "tnc": np.asarray(struct_data["tnc"], dtype=np.uint8),
                        }
                    # Load optional centroid datasets
                    if "N" in datasets:
                        data["N"] = np.asarray(struct_data["N"], dtype=np.uint32) if positions is None else np.asarray(struct_data["N"][idx], dtype=np.uint32)
                    for col in ["Sx", "Sx2", "log_x_sum", "log_1_minus_x_sum"]:
                        if col in datasets:
                            data[col] = np.asarray(struct_data[col], dtype=np.float32) if positions is None else np.asarray(struct_data[col][idx], dtype=np.float32)
                    # Extended sufficient statistics (optional)
                    extra_cols = {
                        "sum_mC": np.uint64,
                        "sum_uC": np.uint64,
                        "sum_cov": np.uint64,
                        "sum_cov2": np.float64,
                        "sum_mC2": np.float64,
                        "sum_uC2": np.float64,
                        "Sx3": np.float32,
                        "Sx4": np.float32,
                        "count_zero": np.uint32,
                        "count_one": np.uint32,
                    }
                    for col, dtype_cast in extra_cols.items():
                        if col in datasets:
                            data[col] = np.asarray(struct_data[col], dtype=dtype_cast) if positions is None else np.asarray(struct_data[col][idx], dtype=dtype_cast)
        
        # If still no data, raise error
        if not data:
            available_keys = list(f.keys())
            raise ValueError(
                f"HDF5 file does not contain required datasets in any recognized format. "
                f"Required: ['pos', 'mC', 'uC', 'tnc']. Available keys: {available_keys}"
            )
        
        # Detect type by available datasets
        if "N" in data:
            # Check if extended centroid fields are present
            if set(MethylExtendedCentroid._required_stats).issubset(data.keys()):
                # If count columns present, use MethylBetaBinomialCentroid
                if MethylBetaBinomialCentroid._required_cols.issubset(data.keys()):
                    cls = MethylBetaBinomialCentroid
                else:
                    cls = MethylExtendedCentroid
            else:
                cls = MethylBasicCentroid
        else:
            cls = MethylSample
        
        # Load metadata from file attributes
        metadata = {}
        if f.attrs:
            import json
            for key, value in f.attrs.items():
                # Parse JSON strings (as written by save_to_h5)
                if isinstance(value, (str, bytes)):
                    try:
                        if isinstance(value, bytes):
                            value = value.decode('utf-8')
                        parsed = json.loads(value)
                        metadata[key] = parsed
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        # Not JSON, use as-is
                        metadata[key] = value
                else:
                    metadata[key] = value

        df = pd.DataFrame(data)
        obj = cls(df, metadata)

        # Load optional binned stats (skip for partial load by indices)
        if indices is None and "binned_stats" in f:
            try:
                bgroup = f["binned_stats"]
                if "bin_edges" in bgroup and "bin_counts" in bgroup:
                    bin_edges = np.asarray(bgroup["bin_edges"][:], dtype=np.float32)
                    bin_counts = np.asarray(bgroup["bin_counts"][:])
                    if hasattr(obj, "set_binned_stats"):
                        obj.set_binned_stats(bin_edges, bin_counts)
                    else:
                        obj._binned_stats = {"bin_edges": bin_edges, "bin_counts": bin_counts}
            except Exception:
                pass

        return obj
