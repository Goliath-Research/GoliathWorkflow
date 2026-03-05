# methyl_utils/core/io.py
from pathlib import Path
from typing import Optional, Union
import hdf5plugin  # noqa: F401 - Must be imported before h5py
import h5py
import numpy as np
import pandas as pd
from .methyl_frame import MethylExtendedCentroid, MethylSample


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
) -> MethylExtendedCentroid | MethylSample:
    """
    Load methylation data from HDF5 file.

    When positions is provided, only those rows are read from disk (hyperslice).
    When indices is provided, only those row indices are read (no full pos read); use with
    load_pos_from_h5() + _indices_for_positions for chunked centroid building.

    Centroid detection: presence of N, Sx, Sx2 (and core columns). Always returns MethylExtendedCentroid
    for centroids. log_x_sum, log_1_minus_x_sum and BB columns in file are ignored (backward compat).

    Returns:
        MethylSample or MethylExtendedCentroid instance

    Raises:
        ValueError: If file doesn't have required datasets in any format
        KeyError: If required datasets are missing
    """
    path = Path(path)
    load_idx = None  # when set, binned_stats will be sliced to match data rows
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
                        load_idx = idx
                        data = {
                            "pos": np.asarray(methyl_data["pos"][idx], dtype=np.uint32),
                            "mC": np.asarray(methyl_data["mC"][idx], dtype=np.uint32),
                            "uC": np.asarray(methyl_data["uC"][idx], dtype=np.uint32),
                            "tnc": np.asarray(methyl_data["tnc"][idx], dtype=np.uint8),
                        }
                    elif positions is not None:
                        pos_arr = np.asarray(methyl_data["pos"][:], dtype=np.uint32)
                        idx = _indices_for_positions(pos_arr, positions)
                        load_idx = idx
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
                    # Load centroid columns (single data-driven: N, Sx, Sx2 only; log/BB ignored)
                    if "N" in datasets:
                        if indices is not None or positions is not None:
                            data["N"] = np.asarray(methyl_data["N"][idx], dtype=np.uint32)
                        else:
                            data["N"] = np.asarray(methyl_data["N"][:], dtype=np.uint32)
                    for col in ["Sx", "Sx2"]:
                        if col in datasets:
                            if indices is not None or positions is not None:
                                data[col] = np.asarray(methyl_data[col][idx], dtype=np.float32)
                            else:
                                data[col] = np.asarray(methyl_data[col][:], dtype=np.float32)

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
                    load_idx = idx
                    data = {
                        "pos": np.asarray(f["pos"][idx], dtype=np.uint32),
                        "mC": np.asarray(f["mC"][idx], dtype=np.uint32),
                        "uC": np.asarray(f["uC"][idx], dtype=np.uint32),
                        "tnc": np.asarray(f["tnc"][idx], dtype=np.uint8),
                    }
                elif positions is not None:
                    pos_arr = np.asarray(f["pos"][:], dtype=np.uint32)
                    idx = _indices_for_positions(pos_arr, positions)
                    load_idx = idx
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
                if "N" in root_keys:
                    if indices is not None or positions is not None:
                        data["N"] = np.asarray(f["N"][idx], dtype=np.uint32)
                    else:
                        data["N"] = np.asarray(f["N"][:], dtype=np.uint32)
                for col in ["Sx", "Sx2"]:
                    if col in root_keys:
                        if indices is not None or positions is not None:
                            data[col] = np.asarray(f[col][idx], dtype=np.float32)
                        else:
                            data[col] = np.asarray(f[col][:], dtype=np.float32)
        
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
                        load_idx = idx
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
                    if "N" in datasets:
                        data["N"] = np.asarray(struct_data["N"], dtype=np.uint32) if positions is None else np.asarray(struct_data["N"][idx], dtype=np.uint32)
                    for col in ["Sx", "Sx2"]:
                        if col in datasets:
                            data[col] = np.asarray(struct_data[col], dtype=np.float32) if positions is None else np.asarray(struct_data[col][idx], dtype=np.float32)
        
        # If still no data, raise error
        if not data:
            available_keys = list(f.keys())
            raise ValueError(
                f"HDF5 file does not contain required datasets in any recognized format. "
                f"Required: ['pos', 'mC', 'uC', 'tnc']. Available keys: {available_keys}"
            )
        
        # Centroid: N and Sx, Sx2 present -> MethylExtendedCentroid. Else sample.
        if "N" in data and "Sx" in data and "Sx2" in data:
            cls = MethylExtendedCentroid
        elif "N" in data:
            # Old file with N but no Sx/Sx2: derive Sx, Sx2 from mC, uC for backward compat
            mC, uC = np.asarray(data["mC"], dtype=np.float64), np.asarray(data["uC"], dtype=np.float64)
            cov = mC + uC
            mean = np.where(cov > 0, mC / cov, 0.0)
            data["Sx"] = (mean * np.asarray(data["N"], dtype=np.float64)).astype(np.float32)
            data["Sx2"] = (mean ** 2 * np.asarray(data["N"], dtype=np.float64)).astype(np.float32)
            cls = MethylExtendedCentroid
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

        # Load optional binned stats (slice to load_idx when we loaded a subset of rows)
        if "binned_stats" in f:
            try:
                bgroup = f["binned_stats"]
                if "bin_edges" in bgroup and "bin_counts" in bgroup:
                    bin_edges = np.asarray(bgroup["bin_edges"][:], dtype=np.float32)
                    bin_counts = np.asarray(bgroup["bin_counts"][:])
                    if load_idx is not None and bin_counts.ndim == 2:
                        bin_counts = bin_counts[load_idx, :]
                    if hasattr(obj, "set_binned_stats"):
                        obj.set_binned_stats(bin_edges, bin_counts)
                    else:
                        obj._binned_stats = {"bin_edges": bin_edges, "bin_counts": bin_counts}
            except Exception:
                pass

        return obj


def estimate_n_cap_from_sample_path(
    path: Union[str, Path],
    *,
    max_positions: int = 100_000,
    iqr_multiplier: float = 1.5,
    seed: Optional[int] = None,
) -> int:
    """
    Estimate n_cap (coverage cap for outlier limiting) from one sample using IQR on sampled positions.

    Loads a random subset of positions (up to max_positions) from the file. The median is
    estimated from this sample (robust to outliers). The outlier limit is the upper fence
    Q3 + iqr_multiplier*IQR (standard 1.5*IQR rule); positions with coverage above that
    (e.g. re-sequencing duplicates) are capped. Returns n_cap = ceil(upper_fence) for use
    with cap_coverage_binomial.

    Args:
        path: Path to a methylation sample HDF5 file (e.g. 1-CG.h5).
        max_positions: Max number of positions to sample for the estimate.
        iqr_multiplier: Multiplier for IQR (default 1.5 = standard boxplot fence).
        seed: Optional RNG seed for reproducible sampling.

    Returns:
        Integer n_cap >= 1 (ceil of upper fence Q3 + iqr_multiplier*IQR).
    """
    path = Path(path)
    pos = load_pos_from_h5(path)
    n = len(pos)
    if n == 0:
        return 1
    rng = np.random.default_rng(seed)
    n_sample = min(n, max_positions)
    idx = rng.choice(n, size=n_sample, replace=False)
    obj = load_from_h5(path, indices=idx)
    _, _, n_cap = obj.coverage_iqr_n_cap(
        max_positions=n_sample,
        iqr_multiplier=iqr_multiplier,
        seed=seed,
    )
    return n_cap


def estimate_n_cap_from_sample_path_with_log(
    path: Union[str, Path],
    *,
    max_positions: int = 100_000,
    iqr_multiplier: float = 1.5,
    seed: Optional[int] = None,
) -> tuple[float, float, int]:
    """
    Like estimate_n_cap_from_sample_path but returns (median, upper_fence, n_cap) for logging.
    """
    path = Path(path)
    pos = load_pos_from_h5(path)
    n = len(pos)
    if n == 0:
        return 0.0, 0.0, 1
    rng = np.random.default_rng(seed)
    n_sample = min(n, max_positions)
    idx = rng.choice(n, size=n_sample, replace=False)
    obj = load_from_h5(path, indices=idx)
    return obj.coverage_iqr_n_cap(
        max_positions=n_sample,
        iqr_multiplier=iqr_multiplier,
        seed=seed,
    )
