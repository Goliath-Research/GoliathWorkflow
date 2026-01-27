"""
MethylBetaMixtureCentroid: per-position Beta Mixture parameters.

Stores mixture parameters for each genomic position/context and provides
conversion helpers to/from DataFrame for export and reuse.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import json

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

    Optional mask:
        - mask: DataFrame/list with [position, context] for selected DMPs
    """

    def __init__(
        self,
        df: pd.DataFrame,
        metadata: Optional[Dict[str, Any]] = None,
        mask: Optional[pd.DataFrame | List[Dict[str, Any]]] = None,
    ):
        self._df = df
        self._metadata = metadata or {}
        self._mask = self._normalize_mask(mask)

    @property
    def df(self) -> pd.DataFrame:
        return self._df

    @property
    def metadata(self) -> Dict[str, Any]:
        return self._metadata

    @property
    def mask(self) -> Optional[pd.DataFrame]:
        """Return mask DataFrame of selected positions (position + context)."""
        return self._mask

    @staticmethod
    def _to_list(value):
        if isinstance(value, list):
            return value
        if isinstance(value, np.ndarray):
            return value.tolist()
        return list(value)

    @staticmethod
    def _normalize_mask(
        mask: Optional[pd.DataFrame | List[Dict[str, Any]]]
    ) -> Optional[pd.DataFrame]:
        if mask is None:
            return None
        if isinstance(mask, list):
            mask_df = pd.DataFrame(mask)
        else:
            mask_df = mask.copy()
        if mask_df.empty:
            return mask_df
        if "position" in mask_df.columns:
            mask_df["position"] = mask_df["position"].astype(np.uint32)
        if "context" not in mask_df.columns:
            mask_df["context"] = "CG"
        return mask_df[["position", "context"]].drop_duplicates().reset_index(drop=True)

    @classmethod
    def from_records(
        cls,
        records: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        mask: Optional[pd.DataFrame | List[Dict[str, Any]]] = None,
    ) -> "MethylBetaMixtureCentroid":
        df = pd.DataFrame(records)
        if not df.empty:
            df["position"] = df["position"].astype(np.uint32)
            if "k" in df.columns:
                df["k"] = df["k"].astype(int)
        return cls(df, metadata=metadata, mask=mask)

    def to_dataframe(self) -> pd.DataFrame:
        return self._df.copy()

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "metadata": self._metadata,
            "records": self._df.to_dict(orient="records")
        }
        if self._mask is not None:
            payload["mask"] = self._mask.to_dict(orient="records")
        return payload

    def to_json(self, filepath: str | "Path") -> None:
        """Save mixture centroid to JSON."""
        from pathlib import Path
        path = Path(filepath)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    @classmethod
    def from_dataframe(
        cls,
        df: pd.DataFrame,
        metadata: Optional[Dict[str, Any]] = None,
        mask: Optional[pd.DataFrame | List[Dict[str, Any]]] = None,
    ) -> "MethylBetaMixtureCentroid":
        return cls(df.copy(), metadata=metadata, mask=mask)

    @classmethod
    def from_json(cls, filepath: str | "Path") -> "MethylBetaMixtureCentroid":
        """Load mixture centroid from JSON."""
        from pathlib import Path
        path = Path(filepath)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        records = data.get("records", [])
        metadata = data.get("metadata", {})
        mask = data.get("mask")
        df = pd.DataFrame(records)
        return cls.from_dataframe(df, metadata=metadata, mask=mask)
