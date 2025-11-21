# methyl_utils/core/io.py
from pathlib import Path
from typing import Union
import hdf5plugin   # noqa: F401 - Must be imported before h5py
import h5py
import pandas as pd
from .methyl_frame import MethylExtendedCentroid, MethylBasicCentroid, MethylSample

def load_from_h5(path: Union[str, Path]) -> MethylExtendedCentroid | MethylBasicCentroid | MethylSample:
    path = Path(path)
    with h5py.File(path, "r") as f:
        if "methylation_data" not in f:
            raise ValueError("Not a valid methylation HDF5 file")

        group = f["methylation_data"]
        datasets = list(group.keys())

        # Detect type by available datasets
        data = {
            "pos": group["pos"][:],
            "mC": group["mC"][:],
            "uC": group["uC"][:],
            "tnc_byte": group["tnc"][:],
        }

        metadata = dict(f.attrs)

        if "N" in datasets:
            data["N"] = group["N"][:]
            if set(MethylExtendedCentroid._required_stats).issubset(datasets):
                for col in MethylExtendedCentroid._required_stats:
                    data[col] = group[col][:]
                cls = MethylExtendedCentroid
            else:
                cls = MethylBasicCentroid
        else:
            cls = MethylSample

        df = pd.DataFrame(data)
        return cls(df, metadata, use_gpu=False)