# methyl_utils/core/methyl_frame.py
from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, Union, List, Tuple, Literal

import numpy as np
import pandas as pd

# Lazy GPU support — zero overhead if not available
try:
    import cupy as cp
    import cudf
    from cudf import DataFrame as CuDataFrame
    from pandas import DataFrame as PdDataFrame
    HAS_GPU = True
except ImportError:  # pragma: no cover
    cp = None
    cudf = None
    CuDataFrame = None
    HAS_GPU = False

DataFrameType = Union[pd.DataFrame, 'cudf.DataFrame']


def _xp() -> Any:
    """Return numpy or cupy depending on runtime context."""
    return cp if (HAS_GPU and hasattr(_current_frame(), '_data')) else np


def _current_frame() -> 'MethylFrame':
    """Internal helper — will be set by MethylFrame instances."""
    return None  # placeholder


@dataclass(frozen=True, slots=True)
class TNC:
    tnc: int          # 0–31
    context: int      # 0=CG, 1=CHG, 2=CHH, 3=UNKNOWN
    strand: int       # 0=+, 1=-

    @classmethod
    def from_byte(cls, byte: int) -> "TNC":
        return cls(
            tnc=byte & 0b11111,
            context=(byte >> 5) & 0b11,
            strand=(byte >> 7) & 0b1,
        )

    def to_byte(self) -> int:
        return (self.tnc & 0b11111) | ((self.context & 0b11) << 5) | ((self.strand & 0b1) << 7)


class MethylFrame:
    """
    Immutable-by-convention container built on pandas (CPU) or cuDF (GPU).
    All heavy lifting is vectorized — no loops, no None-checking hell.
    """

    def __init__(
        self,
        df: DataFrameType,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        use_gpu: bool = False,
    ):
        if use_gpu and not HAS_GPU:
            warnings.warn("GPU requested but cuDF not available → falling back to pandas")
            use_gpu = False

        if use_gpu and not isinstance(df, cudf.DataFrame):
            df = cudf.from_pandas(df if isinstance(df, pd.DataFrame) else pd.DataFrame(df))

        if not use_gpu and isinstance(df, cudf.DataFrame):
            df = df.to_pandas()

        required_cols = {"pos", "mC", "uC", "tnc_byte"}
        if not required_cols.issubset(df.columns):
            raise ValueError(f"Missing required columns: {required_cols - set(df.columns)}")

        self._df = df.reset_index(drop=True)
        self._metadata = metadata.copy() if metadata is not None else {}
        self._use_gpu = use_gpu
        self._cache: Dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # Core properties (always available)
    # ------------------------------------------------------------------ #
    @property
    def df(self) -> DataFrameType:
        return self._df

    @property
    def is_gpu(self) -> bool:
        return self._use_gpu

    @property
    def pos(self):       return self._df["pos"]
    @property
    def mC(self):        return self._df["mC"]
    @property
    def uC(self):        return self._df["uC"]
    @property
    def tnc_byte(self):  return self._df["tnc_byte"]

    @property
    def coverage(self):
        key = "coverage"
        if key not in self._df.columns:
            self._df[key] = self.mC + self.uC
        return self._df[key]

    @property
    def empirical_mean(self):
        key = "empirical_mean"
        if key not in self._df.columns:
            eps = 1e-12
            self._df[key] = self.mC / (self.coverage + eps)
        return self._df[key]

    # ------------------------------------------------------------------ #
    # GPU / CPU conversion
    # ------------------------------------------------------------------ #
    def to_gpu(self) -> "MethylFrame":
        if self._use_gpu:
            return self
        if not HAS_GPU:
            raise RuntimeError("cuDF not available")
        return MethylFrame(cudf.from_pandas(self._df), self._metadata, use_gpu=True)

    def to_cpu(self) -> "MethylFrame":
        if not self._use_gpu:
            return self
        return MethylFrame(self._df.to_pandas(), self._metadata, use_gpu=False)

    # ------------------------------------------------------------------ #
    # Subclass-specific views (zero-copy)
    # ------------------------------------------------------------------ #
    def as_sample(self) -> "MethylSample":
        return MethylSample(self._df, self._metadata, use_gpu=self._use_gpu)

    def as_basic_centroid(self) -> "MethylBasicCentroid":
        return MethylBasicCentroid(self._df, self._metadata, use_gpu=self._use_gpu)

    def as_extended_centroid(self) -> "MethylExtendedCentroid":
        return MethylExtendedCentroid(self._df, self._metadata, use_gpu=self._use_gpu)

    # ------------------------------------------------------------------ #
    # Utilities
    # ------------------------------------------------------------------ #
    def __len__(self) -> int:
        return len(self._df)

    def __getitem__(self, mask) -> "MethylFrame":
        new_df = self._df.loc[mask]
        return MethylFrame(new_df, self._metadata, use_gpu=self._use_gpu)

    def copy(self) -> "MethylFrame":
        return MethylFrame(self._df.copy(), self._metadata, use_gpu=self._use_gpu)

    def save_parquet(self, path: Path | str):
        path = Path(path)
        self.to_cpu()._df.to_parquet(path, compression="zstd")
        # Save metadata as sidecar
        (path.parent / f"{path.stem}_meta.json").write_text(
            __import__("json").dumps(self._metadata, indent=2)
        )

    @classmethod
    def load_parquet(cls, path: Path | str) -> "MethylFrame":
        path = Path(path)
        df = pd.read_parquet(path)
        meta_path = path.parent / f"{path.stem}_meta.json"
        metadata = {}
        if meta_path.exists():
            metadata = __import__("json").loads(meta_path.read_text())
        return cls(df, metadata)


# -------------------------------------------------------------------------- #
# Type-specific lightweight views (enforce required columns, provide helpers)
# -------------------------------------------------------------------------- #

class MethylSample(MethylFrame):
    """Raw individual sample — only pos, mC, uC, tnc_byte required"""
    pass


class MethylBasicCentroid(MethylFrame):
    """Averaged counts + sample count N"""
    def __init__(self, df: DataFrameType, metadata: dict, *, use_gpu: bool):
        if "N" not in df.columns:
            raise ValueError("Basic centroid requires column 'N'")
        super().__init__(df, metadata, use_gpu=use_gpu)

    @property
    def N(self):
        return self._df["N"]


class MethylExtendedCentroid(MethylBasicCentroid):
    """
    Full sufficient statistics → Beta distribution per position.
    This is what MethylCentroidPair expects.
    """
    _required_stats = {"Sx", "Sx2", "log_x_sum", "log_1_minus_x_sum"}

    def __init__(self, df: DataFrameType, metadata: dict, *, use_gpu: bool):
        missing = self._required_stats - set(df.columns)
        if missing:
            raise ValueError(f"Extended centroid missing columns: {missing}")
        super().__init__(df, metadata, use_gpu=use_gpu)

    # ------------------------------------------------------------------ #
    # Lazy Beta parameter estimation (vectorized MLE, GPU-aware)
    # ------------------------------------------------------------------ #
    def _compute_beta_params(self) -> Tuple[pd.Series | cudf.Series, pd.Series | cudf.Series]:
        key = "beta_params"
        if key in self._cache:
            return self._cache[key]

        from methyl_utils.statistical_tests import beta_mle_estimation

        alpha, beta = beta_mle_estimation(
            n=self.N.values,
            log_x_sum=self._df["log_x_sum"].values,
            log_1mx_sum=self._df["log_1_minus_x_sum"].values,
            use_gpu=self.is_gpu,
        )

        if self.is_gpu:
            alpha = cudf.Series(alpha)
            beta = cudf.Series(beta)
        else:
            alpha = pd.Series(alpha, index=self._df.index)
            beta = pd.Series(beta, index=self._df.index)

        self._cache[key] = (alpha, beta)
        return alpha, beta

    @property
    def alpha(self):
        return self._compute_beta_params()[0]

    @property
    def beta(self):
        return self._compute_beta_params()[1]

    @property
    def beta_mean(self):
        a, b = self._compute_beta_params()
        return a / (a + b + 1e-12)

    @property
    def beta_variance(self):
        a, b = self._compute_beta_params()
        tau = a + b
        mean = a / (tau + 1e-12)
        return mean * (1 - mean) / (tau + 1)

    @property
    def adaptive_mean(self):
        """
        Smart mean: empirical for N<20, Beta mean for N≥20
        """
        if "adaptive_mean" not in self._df.columns:
            small = self.N < 20
            self._df["adaptive_mean"] = self.empirical_mean
            if small.any():
                self._df.loc[~small, "adaptive_mean"] = self.beta_mean.loc[~small]
        return self._df["adaptive_mean"]