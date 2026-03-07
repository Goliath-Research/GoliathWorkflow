# methyl_utils/core/io.py
from pathlib import Path
from typing import Optional, Union
import hdf5plugin  # noqa: F401 - Must be imported before h5py
import h5py
import numpy as np
import pandas as pd
from .methyl_frame import MethylCentroid, MethylSample


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
) -> MethylCentroid | MethylSample:
    """
    Load methylation data from HDF5 file.

    When positions is provided, only those rows are read from disk (hyperslice).
    When indices is provided, only those row indices are read (no full pos read); use with
    load_pos_from_h5() + _indices_for_positions for chunked centroid building.

    Centroid detection: presence of pos, tnc, N, Sx, Sx2, Sm, Su, Sc2, Swx2. Requires binned_stats (bins attr + bin_counts).
    No backward compatibility: only the new centroid schema is supported for centroids.

    Returns:
        MethylSample or MethylCentroid instance

    Raises:
        ValueError: If file doesn't have required datasets in any format
        KeyError: If required datasets are missing
    """
    path = Path(path)
    load_idx = None  # when set, bin_counts will be sliced to match data rows
    loaded_bins = None
    loaded_bin_counts = None
    with h5py.File(path, "r") as f:
        data = {}
        datasets = []
        methyl_data = None

        # Try new format first: 'methylation_data' as a group
        centroid_required = ["pos", "tnc", "N", "Sx", "Sx2", "Sm", "Su", "Sc2", "Swx2"]
        sample_required = ["pos", "mC", "uC", "tnc"]
        if "methylation_data" in f:
            methyl_data = f["methylation_data"]
            if isinstance(methyl_data, h5py.Group):
                datasets = list(methyl_data.keys())
                # Centroid: all nine fields + binned_stats required
                if all(d in datasets for d in centroid_required):
                    if indices is not None:
                        idx = np.asarray(indices, dtype=np.intp)
                        load_idx = idx
                    elif positions is not None:
                        pos_arr = np.asarray(methyl_data["pos"][:], dtype=np.uint32)
                        idx = _indices_for_positions(pos_arr, positions)
                        load_idx = idx
                    else:
                        idx = None
                        load_idx = None
                    def _load(key):
                        if idx is not None:
                            return np.asarray(methyl_data[key][idx])
                        return np.asarray(methyl_data[key][:])
                    data = {
                        "pos": _load("pos").astype(np.uint32),
                        "tnc": _load("tnc").astype(np.uint8),
                        "N": _load("N").astype(np.uint32),
                        "Sx": _load("Sx").astype(np.float32),
                        "Sx2": _load("Sx2").astype(np.float32),
                        "Sm": _load("Sm").astype(np.uint32),
                        "Su": _load("Su").astype(np.uint32),
                        "Sc2": _load("Sc2").astype(np.uint32),
                        "Swx2": _load("Swx2").astype(np.float32),
                    }
                    if "bins" not in methyl_data.attrs or "bin_counts" not in datasets:
                        raise ValueError("Centroid file must have binned_stats (bins attr and bin_counts dataset)")
                    loaded_bins = int(methyl_data.attrs["bins"])
                    if loaded_bins > 0:
                        loaded_bin_counts = _load("bin_counts")
                    else:
                        raise ValueError("Centroid binned_stats must have bins > 0")
                elif all(d in datasets for d in sample_required):
                    # Sample
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
                        load_idx = None
                        data = {
                            "pos": np.asarray(methyl_data["pos"][:], dtype=np.uint32),
                            "mC": np.asarray(methyl_data["mC"][:], dtype=np.uint32),
                            "uC": np.asarray(methyl_data["uC"][:], dtype=np.uint32),
                            "tnc": np.asarray(methyl_data["tnc"][:], dtype=np.uint8),
                        }

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
        
        # Centroid: full schema (Sm, Su, Sc2, Swx2) present -> MethylCentroid. Else sample.
        if "Sm" in data and "Su" in data and "Sc2" in data and "Swx2" in data:
            cls = MethylCentroid
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

        # Binned stats from methylation_data (bins attr + bin_counts); derive bin_edges
        if loaded_bins is not None and loaded_bin_counts is not None:
            bin_edges = np.linspace(0, 1, loaded_bins + 1, dtype=np.float32)
            if hasattr(obj, "set_binned_stats"):
                obj.set_binned_stats(bin_edges, loaded_bin_counts)
            else:
                obj._binned_stats = {"bin_edges": bin_edges, "bin_counts": loaded_bin_counts}

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
