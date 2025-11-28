# methyl_utils/core/io.py
from pathlib import Path
from typing import Union
import hdf5plugin  # noqa: F401 - Must be imported before h5py
import h5py
import numpy as np
import pandas as pd
from .methyl_frame import MethylExtendedCentroid, MethylBasicCentroid, MethylSample


def load_from_h5(
    path: Union[str, Path],
) -> MethylExtendedCentroid | MethylBasicCentroid | MethylSample:
    """
    Load methylation data from HDF5 file.
    
    Supports the format written by save_to_h5():
    - Metadata stored as file attributes (JSON-encoded for dict/list)
    - Datasets stored in 'methylation_data' group
    - Core datasets: pos, mC, uC, tnc
    - Optional centroid datasets: N, Sx, Sx2, log_x_sum, log_1_minus_x_sum
    
    Args:
        path: Path to HDF5 file
        
    Returns:
        MethylSample, MethylBasicCentroid, or MethylExtendedCentroid instance
        
    Raises:
        ValueError: If file doesn't have the expected 'methylation_data' group
        KeyError: If required datasets are missing
    """
    path = Path(path)
    with h5py.File(path, "r") as f:
        # Check for 'methylation_data' group (format written by save_to_h5)
        if "methylation_data" not in f:
            raise ValueError(
                f"HDF5 file does not contain 'methylation_data' group. "
                f"This file may be in an old format. Available keys: {list(f.keys())}"
            )
        
        methyl_data = f["methylation_data"]
        if not isinstance(methyl_data, h5py.Group):
            raise ValueError(
                f"'methylation_data' exists but is not a group. "
                f"This file may be in an old format."
            )
        
        datasets = list(methyl_data.keys())
        
        # Check for required core datasets
        required_core = ["pos", "mC", "uC", "tnc"]
        missing = [d for d in required_core if d not in datasets]
        if missing:
            raise ValueError(
                f"Missing required datasets in 'methylation_data' group: {missing}. "
                f"Available: {datasets}"
            )
        
        # Load core datasets
        data = {
            "pos": np.asarray(methyl_data["pos"][:], dtype=np.uint32),
            "mC": np.asarray(methyl_data["mC"][:], dtype=np.uint32),
            "uC": np.asarray(methyl_data["uC"][:], dtype=np.uint32),
            "tnc": np.asarray(methyl_data["tnc"][:], dtype=np.uint8),
        }
        
        # Detect type by available datasets
        if "N" in datasets:
            data["N"] = np.asarray(methyl_data["N"][:], dtype=np.uint32)
            
            # Check if extended centroid fields are present
            if set(MethylExtendedCentroid._required_stats).issubset(datasets):
                for col in MethylExtendedCentroid._required_stats:
                    data[col] = np.asarray(methyl_data[col][:], dtype=np.float32)
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
        return cls(df, metadata)
