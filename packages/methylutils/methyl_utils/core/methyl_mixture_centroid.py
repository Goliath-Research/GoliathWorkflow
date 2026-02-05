"""
MethylBetaMixtureCentroid: per-position Beta Mixture parameters.

Stores mixture parameters for each genomic position/context and provides
conversion helpers to/from DataFrame for export and reuse.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
import json

import numpy as np
import pandas as pd

MIN_BETA_PARAM = 1e-6


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

    @property
    def mean(self) -> np.ndarray:
        """Virtual mean: per-position weighted sum of component means (alpha_j/(alpha_j+beta_j)), 0/1 safe."""
        means = []
        for _, row in self._df.iterrows():
            w = np.asarray(self._to_list(row["weights"]), dtype=np.float64)
            a = np.maximum(np.asarray(self._to_list(row["alphas"]), dtype=np.float64), MIN_BETA_PARAM)
            b = np.maximum(np.asarray(self._to_list(row["betas"]), dtype=np.float64), MIN_BETA_PARAM)
            comp_mean = a / (a + b)
            means.append(float(np.sum(w * comp_mean)))
        return np.array(means, dtype=np.float64)

    def overlap(
        self,
        other: Union["MethylBetaMixtureCentroid", Any],
    ) -> np.ndarray:
        """Overlap with another BMM or Beta: 1 - |mean_self - mean_other| clipped to [0,1], or Bhattacharyya when applicable."""
        m_self = np.asarray(self.mean, dtype=np.float64)
        if isinstance(other, MethylBetaMixtureCentroid):
            m_other = np.asarray(other.mean, dtype=np.float64)
        else:
            m_other = np.asarray(getattr(other, "mean", other), dtype=np.float64)
        n = min(len(m_self), len(m_other))
        return np.clip(1 - np.abs(m_self[:n] - m_other[:n]), 0.0, 1.0)
