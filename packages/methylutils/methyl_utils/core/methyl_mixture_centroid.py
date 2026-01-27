"""
MethylBetaMixtureCentroid: per-position Beta Mixture parameters.

Stores mixture parameters for each genomic position/context and provides
conversion helpers to/from DataFrame for export and reuse.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


class MethylBetaMixtureCentroid:
    """
    Container for Beta Mixture Model parameters per position.

    Expected columns in DataFrame:
        - position: uint32
        - context: str
        - k: int
        - weights: list[float]
        - alphas: list[float]
        - betas: list[float]
        - n_samples: int
        - converged: bool
        - bic: float
        - loglik: float
        - status: str (optional)
    """

    def __init__(self, df: pd.DataFrame, metadata: Optional[Dict[str, Any]] = None):
        self._df = df
        self._metadata = metadata or {}

    @property
    def df(self) -> pd.DataFrame:
        return self._df

    @property
    def metadata(self) -> Dict[str, Any]:
        return self._metadata

    @staticmethod
    def _to_list(value):
        if isinstance(value, list):
            return value
        if isinstance(value, np.ndarray):
            return value.tolist()
        return list(value)

    @classmethod
    def from_records(
        cls,
        records: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> "MethylBetaMixtureCentroid":
        df = pd.DataFrame(records)
        if not df.empty:
            df["position"] = df["position"].astype(np.uint32)
            if "k" in df.columns:
                df["k"] = df["k"].astype(int)
        return cls(df, metadata=metadata)

    def to_dataframe(self) -> pd.DataFrame:
        return self._df.copy()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self._metadata,
            "records": self._df.to_dict(orient="records")
        }

    @classmethod
    def from_dataframe(
        cls, df: pd.DataFrame, metadata: Optional[Dict[str, Any]] = None
    ) -> "MethylBetaMixtureCentroid":
        return cls(df.copy(), metadata=metadata)
