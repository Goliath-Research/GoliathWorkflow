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
    
    Supports both formats:
    1. New format: datasets in 'methylation_data' group
    2. Old format: datasets at root level
    
    Args:
        path: Path to HDF5 file
        
    Returns:
        MethylSample, MethylBasicCentroid, or MethylExtendedCentroid instance
    """
    path = Path(path)
    with h5py.File(path, "r") as f:
        # Determine data location (group or root)
        data_source = None
        datasets = []
        
        # Try new format first: check for 'methylation_data' group
        if "methylation_data" in f:
            methyl_data = f["methylation_data"]
            if isinstance(methyl_data, h5py.Group):
                # It's a group - use it
                data_source = methyl_data
                datasets = list(methyl_data.keys())
            elif isinstance(methyl_data, h5py.Dataset):
                # It's a dataset (structured array format) - handle differently
                # This is the old structured array format
                data_source = methyl_data
                # For structured arrays, check dtype.names
                if hasattr(methyl_data.dtype, 'names') and methyl_data.dtype.names:
                    datasets = list(methyl_data.dtype.names)
                else:
                    # Fall back to root level
                    data_source = f
                    datasets = [key for key in f.keys() if isinstance(f[key], h5py.Dataset)]
        
        # If no methylation_data group found, check root level (old format)
        if data_source is None:
            data_source = f
            datasets = [key for key in f.keys() if isinstance(f[key], h5py.Dataset)]
        
        # Check for required datasets
        if "pos" not in datasets:
            raise ValueError(f"Missing required dataset 'pos' in HDF5 file. Available: {datasets}")
        
        # Load core datasets
        if isinstance(data_source, h5py.Dataset):
            # Structured array format
            if hasattr(data_source.dtype, 'names') and data_source.dtype.names:
                # Load all data at once
                structured_data = data_source[:]
                # Access structured array fields using dictionary-like syntax
                data = {
                    "pos": np.asarray(structured_data["pos"], dtype=np.uint32),
                    "mC": np.asarray(structured_data["mC"], dtype=np.uint32),
                    "uC": np.asarray(structured_data["uC"], dtype=np.uint32),
                }
                # Handle tnc field (might be missing in old files)
                if "tnc" in data_source.dtype.names:
                    data["tnc"] = np.asarray(structured_data["tnc"], dtype=np.uint8)
                else:
                    data["tnc"] = np.zeros(len(structured_data), dtype=np.uint8)
                
                # Check for centroid fields
                if "N" in data_source.dtype.names:
                    data["N"] = np.asarray(structured_data["N"], dtype=np.uint32)
                    if set(MethylExtendedCentroid._required_stats).issubset(data_source.dtype.names):
                        for col in MethylExtendedCentroid._required_stats:
                            data[col] = np.asarray(structured_data[col], dtype=np.float32)
                        cls = MethylExtendedCentroid
                    else:
                        cls = MethylBasicCentroid
                else:
                    cls = MethylSample
            else:
                raise ValueError("Dataset 'methylation_data' is not a structured array")
        else:
            # Group format (new format) or root level (old format)
            data = {
                "pos": np.asarray(data_source["pos"][:], dtype=np.uint32),
                "mC": np.asarray(data_source["mC"][:], dtype=np.uint32),
                "uC": np.asarray(data_source["uC"][:], dtype=np.uint32),
            }
            
            # Handle tnc (might be missing in old files)
            if "tnc" in datasets:
                data["tnc"] = np.asarray(data_source["tnc"][:], dtype=np.uint8)
            else:
                data["tnc"] = np.zeros(len(data["pos"]), dtype=np.uint8)
            
            # Detect type by available datasets
            if "N" in datasets:
                data["N"] = np.asarray(data_source["N"][:], dtype=np.uint32)
                if set(MethylExtendedCentroid._required_stats).issubset(datasets):
                    for col in MethylExtendedCentroid._required_stats:
                        data[col] = np.asarray(data_source[col][:], dtype=np.float32)
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
                # Try to parse JSON strings
                if isinstance(value, (str, bytes)):
                    try:
                        if isinstance(value, bytes):
                            value = value.decode('utf-8')
                        parsed = json.loads(value)
                        metadata[key] = parsed
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        metadata[key] = value
                else:
                    metadata[key] = value

        df = pd.DataFrame(data)
        return cls(df, metadata)
