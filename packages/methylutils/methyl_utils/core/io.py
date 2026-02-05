# methyl_utils/core/io.py
from pathlib import Path
from typing import Union
import hdf5plugin  # noqa: F401 - Must be imported before h5py
import h5py
import numpy as np
import pandas as pd
from .methyl_frame import MethylExtendedCentroid, MethylBasicCentroid, MethylSample, MethylBetaBinomialCentroid


def load_from_h5(
    path: Union[str, Path],
) -> MethylExtendedCentroid | MethylBasicCentroid | MethylSample | MethylBetaBinomialCentroid:
    """
    Load methylation data from HDF5 file.
    
    Supports both new and old formats:
    - New format: Datasets stored in 'methylation_data' group
    - Old format: Datasets stored at root level or 'methylation_data' as structured array
    
    Args:
        path: Path to HDF5 file
        
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
                    # Load core datasets from group
                    data = {
                        "pos": np.asarray(methyl_data["pos"][:], dtype=np.uint32),
                        "mC": np.asarray(methyl_data["mC"][:], dtype=np.uint32),
                        "uC": np.asarray(methyl_data["uC"][:], dtype=np.uint32),
                        "tnc": np.asarray(methyl_data["tnc"][:], dtype=np.uint8),
                    }
                    # Load optional centroid datasets
                    if "N" in datasets:
                        data["N"] = np.asarray(methyl_data["N"][:], dtype=np.uint32)
                    for col in ["Sx", "Sx2", "log_x_sum", "log_1_minus_x_sum"]:
                        if col in datasets:
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
                            data[col] = np.asarray(methyl_data[col][:], dtype=dtype_cast)
        
        # Fallback to old format: datasets at root level
        if not data:
            root_keys = list(f.keys())
            required_core = ["pos", "mC", "uC", "tnc"]
            
            # Check if required datasets exist at root level
            missing = [d for d in required_core if d not in root_keys]
            if not missing:
                datasets = root_keys
                # Load core datasets from root
                data = {
                    "pos": np.asarray(f["pos"][:], dtype=np.uint32),
                    "mC": np.asarray(f["mC"][:], dtype=np.uint32),
                    "uC": np.asarray(f["uC"][:], dtype=np.uint32),
                    "tnc": np.asarray(f["tnc"][:], dtype=np.uint8),
                }
                # Load optional centroid datasets
                if "N" in root_keys:
                    data["N"] = np.asarray(f["N"][:], dtype=np.uint32)
                for col in ["Sx", "Sx2", "log_x_sum", "log_1_minus_x_sum"]:
                    if col in root_keys:
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
                        data[col] = np.asarray(f[col][:], dtype=dtype_cast)
        
        # Fallback to old format: 'methylation_data' as structured array
        if not data and "methylation_data" in f:
            methyl_data = f["methylation_data"]
            if isinstance(methyl_data, h5py.Dataset) and methyl_data.dtype.names:
                # Structured array format
                struct_data = methyl_data[:]
                datasets = list(methyl_data.dtype.names)
                required_core = ["pos", "mC", "uC", "tnc"]
                missing = [d for d in required_core if d not in datasets]
                if not missing:
                    data = {
                        "pos": np.asarray(struct_data["pos"], dtype=np.uint32),
                        "mC": np.asarray(struct_data["mC"], dtype=np.uint32),
                        "uC": np.asarray(struct_data["uC"], dtype=np.uint32),
                        "tnc": np.asarray(struct_data["tnc"], dtype=np.uint8),
                    }
                    # Load optional centroid datasets
                    if "N" in datasets:
                        data["N"] = np.asarray(struct_data["N"], dtype=np.uint32)
                    for col in ["Sx", "Sx2", "log_x_sum", "log_1_minus_x_sum"]:
                        if col in datasets:
                            data[col] = np.asarray(struct_data[col], dtype=np.float32)
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
                            data[col] = np.asarray(struct_data[col], dtype=dtype_cast)
        
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

        # Load optional binned stats
        if "binned_stats" in f:
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
