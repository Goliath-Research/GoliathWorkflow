# methyl_utils/core/methyl_frame.py
from __future__ import annotations

from typing import Optional, Dict, Any, Union, List, Literal
from pathlib import Path

import numpy as np
import pandas as pd

# GPU support (transparent)
import logging
import gc

try:
    from ..gpu_detection import get_cupy, is_gpu_available, cleanup_gpu_memory
except ImportError:
    try:
        from methyl_utils.gpu_detection import get_cupy, is_gpu_available, cleanup_gpu_memory
    except ImportError:
        def get_cupy():  # type: ignore[override]
            return None

        def is_gpu_available():  # type: ignore[override]
            return False

        def cleanup_gpu_memory() -> bool:  # type: ignore[override]
            return False

try:
    import cudf
except ImportError:
    cudf = None

cp = get_cupy()
HAS_GPU = cp is not None and cudf is not None and is_gpu_available()


# Single source of truth — column name → optimal dtype
COLUMN_DTYPES = {
    "pos": "uint32",
    "mC": "uint32",
    "uC": "uint32",
    "tnc": "uint8",
    "N": "uint32",
    "Sx": "float32",
    "Sx2": "float32",
    "log_x_sum": "float32",
    "log_1_minus_x_sum": "float32",
}

# Categorical definitions
ContextDtype = pd.CategoricalDtype(
    categories=["CG", "CHG", "CHH", "UNKNOWN"], ordered=False
)
StrandDtype = pd.CategoricalDtype(categories=["+", "-"], ordered=False)

# TNC byte bit field layout (C-style)
# Bit 7 (MSB): strand (0 = '+', 1 = '-')
# Bits 0-6: TNC value (7 bits, 0-127)
TNC_VALUE_MASK = 0x7F  # Mask for 7-bit TNC value (bits 0-6)
STRAND_SHIFT = 7       # Bit position of strand (MSB)
STRAND_MASK = 0x1      # Mask for strand bit

# Fast lookup tables
_TNC_CONTEXT_CODES = np.array([0] * 32 + [1] * 32 + [2] * 32 + [3] * 32, dtype=np.uint8)
_TNC_STRAND_CODES = np.array([0] * 128 + [1] * 128, dtype=np.uint8)


class MethylFrame:
    _required_cols = {"pos", "mC", "uC", "tnc"}

    def __init__(
        self,
        df: pd.DataFrame | "cudf.DataFrame",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        missing = self._required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Apply optimal dtypes from single source
        dtypes = {
            col: dtype for col, dtype in COLUMN_DTYPES.items() if col in df.columns
        }
        df = df.astype(dtypes)

        # Decode context/strand once
        if "context" not in df.columns:
            # Ensure we are working with a CPU DataFrame if GPU isn't available
            if not HAS_GPU and cudf is not None and isinstance(df, cudf.DataFrame):
                df = df.to_pandas()

            tnc = df["tnc"].values
            # Extract TNC value (bits 0-6) and strand (bit 7) using bit field masks
            if HAS_GPU and hasattr(tnc, "__cuda_array_interface__"):
                try:
                    tnc_context = tnc & TNC_VALUE_MASK
                    strand_codes = (tnc >> STRAND_SHIFT) & STRAND_MASK
                    ctx_codes = cp.asarray(_TNC_CONTEXT_CODES)[tnc_context]
                    df["context"] = cudf.Series(ctx_codes, dtype=ContextDtype)
                    df["strand"] = cudf.Series(strand_codes, dtype=StrandDtype)
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        f"GPU context decode failed; falling back to CPU: {e}"
                    )
                    if cudf is not None and isinstance(df, cudf.DataFrame):
                        df = df.to_pandas()
                    tnc = df["tnc"].values
                    tnc_context = tnc & TNC_VALUE_MASK
                    strand_codes = (tnc >> STRAND_SHIFT) & STRAND_MASK
                    df["context"] = pd.Categorical.from_codes(
                        _TNC_CONTEXT_CODES[tnc_context], dtype=ContextDtype
                    )
                    df["strand"] = pd.Categorical.from_codes(
                        strand_codes, dtype=StrandDtype
                    )
            else:
                tnc_context = tnc & TNC_VALUE_MASK
                strand_codes = (tnc >> STRAND_SHIFT) & STRAND_MASK
                df["context"] = pd.Categorical.from_codes(
                    _TNC_CONTEXT_CODES[tnc_context], dtype=ContextDtype
                )
                df["strand"] = pd.Categorical.from_codes(
                    strand_codes, dtype=StrandDtype
                )

        self._df = df.sort_values("pos").reset_index(drop=True)
        self._metadata = metadata or {}
        self._binned_stats = None

    @property
    def df(self):
        return self._df

    @property
    def is_gpu(self) -> bool:
        return HAS_GPU and cudf is not None and isinstance(self._df, cudf.DataFrame)

    @property
    def pos(self):
        return self._df["pos"]

    @property
    def mC(self):
        return self._df["mC"]

    @property
    def uC(self):
        return self._df["uC"]

    @property
    def coverage(self):
        return self.mC + self.uC

    @property
    def context(self):
        return self._df["context"]

    @property
    def strand(self):
        return self._df["strand"]

    def to_gpu(self):
        if not HAS_GPU or self.is_gpu:
            return self
        return type(self)(cudf.from_pandas(self._df.to_pandas()), self._metadata)

    def to_cpu(self):
        if not self.is_gpu:
            return self
        return type(self)(self._df.to_pandas(), self._metadata)

    def __len__(self):
        return len(self._df)

    def __getitem__(self, key):
        return type(self)(self._df.loc[key], self._metadata.copy())

    def close(self, free_gpu_pool: bool = False) -> None:
        """
        Release references and (optionally) free GPU memory pools.

        Note: freeing the GPU pool is global and may impact performance if called
        frequently. Use free_gpu_pool=True only when you need to return memory
        to the system.
        """
        if getattr(self, "_closed", False):
            return
        self._closed = True

        df = getattr(self, "_df", None)
        self._df = None
        self._binned_stats = None
        self._metadata = {}

        try:
            if free_gpu_pool and df is not None and self.is_gpu:
                cleanup_gpu_memory()
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"GPU memory cleanup failed during close: {e}"
            )

        gc.collect()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close(free_gpu_pool=False)
        return False

    def __del__(self):
        try:
            self.close(free_gpu_pool=False)
        except Exception:
            pass

    def _get_values(self, series) -> np.ndarray:
        """Safely extract values from pandas/cudf Series, handling GPU compatibility.

        Args:
            series: pandas or cudf Series

        Returns:
            numpy array of values
        """
        if hasattr(series, 'values'):
            return series.values
        else:
            return np.asarray(series)

    @property
    def metadata(self) -> Dict[str, Any]:
        """Get metadata dictionary."""
        return self._metadata

    @metadata.setter
    def metadata(self, value: Dict[str, Any]):
        """Set metadata dictionary."""
        self._metadata = value or {}

    @property
    def binned_stats(self) -> Optional[Dict[str, Any]]:
        """Optional binned stats (bin_edges + bin_counts)."""
        return self._binned_stats

    def set_binned_stats(self, bin_edges: np.ndarray, bin_counts: np.ndarray) -> None:
        """Attach binned stats to this object for HDF5 persistence."""
        self._binned_stats = {
            "bin_edges": np.asarray(bin_edges, dtype=np.float32),
            "bin_counts": np.asarray(bin_counts),
        }

    # Metadata properties (read-write for easy manipulation)
    @property
    def laboratory(self) -> Optional[str]:
        """Get laboratory name from metadata."""
        return self._metadata.get("laboratory") if self._metadata else None

    @laboratory.setter
    def laboratory(self, value: str):
        """Set laboratory name in metadata."""
        if self._metadata is None:
            self._metadata = {}
        self._metadata["laboratory"] = value

    @property
    def disease(self) -> Optional[str]:
        """Get disease from metadata."""
        return self._metadata.get("disease") if self._metadata else None

    @disease.setter
    def disease(self, value: str):
        """Set disease in metadata."""
        if self._metadata is None:
            self._metadata = {}
        self._metadata["disease"] = value

    @property
    def group(self) -> Optional[str]:
        """Get group identifier from metadata."""
        return self._metadata.get("group") if self._metadata else None

    @group.setter
    def group(self, value: str):
        """Set group identifier in metadata."""
        if self._metadata is None:
            self._metadata = {}
        self._metadata["group"] = value

    @property
    def batch(self) -> Optional[str]:
        """Get batch identifier from metadata."""
        return self._metadata.get("batch") if self._metadata else None

    @batch.setter
    def batch(self, value: str):
        """Set batch identifier in metadata."""
        if self._metadata is None:
            self._metadata = {}
        self._metadata["batch"] = value

    @property
    def chromosome(self) -> Optional[str]:
        """Get chromosome from metadata."""
        return self._metadata.get("chromosome") if self._metadata else None

    @chromosome.setter
    def chromosome(self, value: str):
        """Set chromosome in metadata."""
        if self._metadata is None:
            self._metadata = {}
        self._metadata["chromosome"] = value

    @property
    def context_metadata(self) -> Optional[str]:
        """Get methylation context from metadata."""
        return self._metadata.get("context") if self._metadata else None

    @context_metadata.setter
    def context_metadata(self, value: str):
        """Set methylation context in metadata."""
        if self._metadata is None:
            self._metadata = {}
        self._metadata["context"] = value

    @property
    def samples(self) -> List[str]:
        """List of sample file paths that form this centroid (from metadata)."""
        if not self._metadata:
            return []
        # Check for 'sample_paths' first, fall back to 'samples_used'
        return self._metadata.get('sample_paths') or self._metadata.get('samples_used', [])

    @property
    def group_name(self) -> str:
        """Group name or label for this centroid (from metadata)."""
        return self._metadata.get('group_name', 'Unknown') if self._metadata else 'Unknown'

    @property
    def is_centroid(self) -> bool:
        """Check if this is a centroid."""
        return False

    @property
    def is_extended_centroid(self) -> bool:
        """Check if this is an extended centroid."""
        return False

    @property
    def sample_type(self) -> str:
        """Get the sample type."""
        return "sample"

    @property
    def position_count(self) -> int:
        """Number of genomic positions."""
        return len(self._df)

    @property
    def memory_usage_mb(self) -> float:
        """Memory usage in megabytes."""
        if self.is_gpu:
            return self._df.memory_usage(deep=True).sum() / (1024 * 1024)
        else:
            return self._df.memory_usage(deep=True).sum() / (1024 * 1024)

    def apply_mask(self, mask_or_indices: Union[np.ndarray, List[int], bool]) -> "MethylFrame":
        """
        Apply a boolean mask or integer indices to filter the data.

        Args:
            mask_or_indices: Boolean mask array or integer indices

        Returns:
            New instance with filtered data
        """
        if isinstance(mask_or_indices, (list, np.ndarray)) and len(mask_or_indices) > 0:
            # Check if it's a boolean mask
            if isinstance(mask_or_indices, np.ndarray) and mask_or_indices.dtype == bool:
                # Boolean mask - use .loc with boolean array
                return type(self)(self._df.loc[mask_or_indices], self._metadata.copy())
            elif isinstance(mask_or_indices[0], bool):
                # Boolean mask (list or array with bool elements)
                mask_array = np.asarray(mask_or_indices, dtype=bool)
                return type(self)(self._df.loc[mask_array], self._metadata.copy())
            else:
                # Integer indices - use .iloc for position-based indexing
                indices_array = np.asarray(mask_or_indices, dtype=np.int64)
                return type(self)(self._df.iloc[indices_array], self._metadata.copy())
        return self

    def align_to_positions(self, positions: np.ndarray) -> "MethylFrame":
        """
        Align to reference positions, keeping only common positions.

        Args:
            positions: Reference positions to align to

        Returns:
            New instance aligned to reference positions
        """
        pos_values = self.pos.values if hasattr(self.pos, 'values') else np.asarray(self.pos)
        common_pos, idx1, _ = np.intersect1d(pos_values, positions, assume_unique=True, return_indices=True)
        return self.apply_mask(idx1)

    def get_methylation_levels(self) -> np.ndarray:
        """Get methylation levels (mC / (mC + uC))."""
        cov = self.coverage.values if hasattr(self.coverage, 'values') else np.asarray(self.coverage)
        mC_vals = self.mC.values if hasattr(self.mC, 'values') else np.asarray(self.mC)
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.where(cov > 0, mC_vals / cov, 0.0)

    def get_coverage(self) -> np.ndarray:
        """Get total coverage (mC + uC)."""
        return self.coverage.values if hasattr(self.coverage, 'values') else np.asarray(self.coverage)

    @classmethod
    def load_from_h5(cls, path: Union[str, Path], positions: Optional[np.ndarray] = None) -> "MethylFrame":
        """
        Load from HDF5 file. When positions is given, only those rows are read from disk
        (same hyperslice approach as MethylDetector validation).

        Args:
            path: Path to HDF5 file
            positions: Optional positions to load; only these rows are read (saves memory).

        Returns:
            MethylSample, MethylBasicCentroid, or MethylExtendedCentroid instance
        """
        from .io import load_from_h5
        result = load_from_h5(path, positions=positions)
        if positions is not None:
            result = result.align_to_positions(positions)
        return result

    def save_to_h5(self, path: Union[str, Path], compressed: bool = True) -> Path:
        """
        Save to HDF5 file.

        Args:
            path: Path to save to
            compressed: Whether to use compression

        Returns:
            Path to saved file
        """
        path = Path(path)
        import h5py
        import hdf5plugin

        with h5py.File(path, "w") as f:
            # Store metadata as attributes
            for key, value in self._metadata.items():
                if isinstance(value, (dict, list)):
                    import json
                    f.attrs[key] = json.dumps(value)
                else:
                    f.attrs[key] = value

            # Create methylation_data group
            group = f.create_group("methylation_data")

            # Store core columns
            for col in ["pos", "mC", "uC", "tnc"]:
                if col in self._df.columns:
                    data = self._df[col].values if hasattr(self._df[col], 'values') else np.asarray(self._df[col])
                    if compressed:
                        group.create_dataset(col, data=data, **hdf5plugin.Blosc())
                    else:
                        group.create_dataset(col, data=data)

            # Store centroid columns if present
            for col in [
                "N",
                "Sx",
                "Sx2",
                "log_x_sum",
                "log_1_minus_x_sum",
                # Extended sufficient statistics (optional)
                "sum_mC",
                "sum_uC",
                "sum_cov",
                "sum_cov2",
                "sum_mC2",
                "sum_uC2",
                "Sx3",
                "Sx4",
                "count_zero",
                "count_one",
            ]:
                if col in self._df.columns:
                    data = self._df[col].values if hasattr(self._df[col], 'values') else np.asarray(self._df[col])
                    if compressed:
                        group.create_dataset(col, data=data, **hdf5plugin.Blosc())
                    else:
                        group.create_dataset(col, data=data)

            # Optional binned stats (large arrays) stored in separate group
            if hasattr(self, "_binned_stats") and self._binned_stats:
                binned = self._binned_stats
                if "bin_edges" in binned and "bin_counts" in binned:
                    bgroup = f.create_group("binned_stats")
                    if compressed:
                        bgroup.create_dataset("bin_edges", data=binned["bin_edges"], **hdf5plugin.Blosc())
                        bgroup.create_dataset("bin_counts", data=binned["bin_counts"], **hdf5plugin.Blosc())
                    else:
                        bgroup.create_dataset("bin_edges", data=binned["bin_edges"])
                        bgroup.create_dataset("bin_counts", data=binned["bin_counts"])

        return path

    @classmethod
    def from_sample_data(
        cls,
        pos: np.ndarray,
        mC: np.ndarray,
        uC: np.ndarray,
        tnc: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None
    ) -> "MethylSample":
        """
        Create MethylSample from arrays.

        Args:
            pos: Genomic positions
            mC: Methylated counts
            uC: Unmethylated counts
            tnc: Trinucleotide context bytes
            metadata: Optional metadata

        Returns:
            MethylSample instance
        """
        df = pd.DataFrame({
            "pos": pos,
            "mC": mC,
            "uC": uC,
            "tnc": tnc,
        })
        return MethylSample(df, metadata)

# Single sample class
class MethylSample(MethylFrame):
    _required_cols = {"pos", "mC", "uC", "tnc"}

    def cap_coverage_binomial(
        self,
        n_cap: int,
        *,
        seed: Optional[int] = None,
    ) -> "MethylSample":
        """
        Cap per-CpG coverage by binomial thinning (in-place).

        For each position where total coverage n = mC + uC > n_cap, reduce counts
        by random thinning: keep probability p = n_cap / n, draw mC' ~ Binomial(mC, p)
        and uC' ~ Binomial(uC, p). Keeps methylation proportion unbiased in expectation
        while preventing ultra-deep positions from dominating. Mutates this sample
        in place and returns self for chaining.

        Args:
            n_cap: Maximum coverage per position; positions with coverage > n_cap are thinned.
            seed: Optional RNG seed for reproducibility.

        Returns:
            self (for chaining).
        """
        if n_cap < 1:
            raise ValueError("n_cap must be >= 1")
        self = self.to_cpu()
        mC = np.asarray(self._get_values(self.mC), dtype=np.uint32)
        uC = np.asarray(self._get_values(self.uC), dtype=np.uint32)
        cov = mC.astype(np.float64) + uC.astype(np.float64)
        over = cov > n_cap
        if not np.any(over):
            return self
        rng = np.random.default_rng(seed)
        p_over = n_cap / cov[over]
        mC_new = mC.copy()
        uC_new = uC.copy()
        mC_new[over] = rng.binomial(mC[over].astype(np.int64), p_over).astype(np.uint32)
        uC_new[over] = rng.binomial(uC[over].astype(np.int64), p_over).astype(np.uint32)
        self._df = self._df.copy()
        self._df.loc[over, "mC"] = mC_new[over]
        self._df.loc[over, "uC"] = uC_new[over]
        return self

    def median_coverage(
        self,
        *,
        max_positions: int = 100_000,
        seed: Optional[int] = None,
    ) -> float:
        """
        Median coverage across positions (sampled for large samples).

        For samples with more than max_positions positions, uses a random subset
        so the result is fast and scalable (e.g. for 80M+ positions). Intended
        for cohort-level outlier detection.

        Args:
            max_positions: Cap the number of positions used to compute the median.
            seed: Optional RNG seed when sampling positions.

        Returns:
            Median of (mC + uC) over positions (or over a random subset).
        """
        cov = self.get_coverage()
        n = len(cov)
        if n == 0:
            return 0.0
        if n <= max_positions:
            return float(np.median(cov))
        rng = np.random.default_rng(seed)
        idx = rng.choice(n, size=max_positions, replace=False)
        return float(np.median(cov[idx]))

    def coverage_iqr_n_cap(
        self,
        *,
        max_positions: int = 100_000,
        iqr_multiplier: float = 1.5,
        seed: Optional[int] = None,
    ) -> tuple[float, float, int]:
        """
        Estimate median, upper fence (Q3 + k*IQR), and n_cap from a random sample of positions.

        Uses the same random subset of positions as median_coverage. The median is robust
        to outliers (e.g. re-sequencing duplicates). The outlier limit is the upper fence
        Q3 + iqr_multiplier*IQR (standard 1.5*IQR boxplot rule); positions with coverage
        above that are considered impossible given the distribution and should be capped.

        Args:
            max_positions: Cap the number of positions used (same as median_coverage).
            iqr_multiplier: Multiplier for IQR (default 1.5 = standard boxplot fence).
            seed: Optional RNG seed when sampling positions.

        Returns:
            (median, upper_fence, n_cap) where n_cap = max(1, ceil(upper_fence)).
            If IQR == 0, n_cap is set from ceil(median) so we do not cap everything.
        """
        cov = self.get_coverage()
        n = len(cov)
        if n == 0:
            return 0.0, 0.0, 1
        if n <= max_positions:
            cov_sample = np.asarray(cov, dtype=np.float64)
        else:
            rng = np.random.default_rng(seed)
            idx = rng.choice(n, size=max_positions, replace=False)
            cov_sample = np.asarray(cov, dtype=np.float64)[idx]
        median = float(np.median(cov_sample))
        q1 = float(np.percentile(cov_sample, 25))
        q3 = float(np.percentile(cov_sample, 75))
        iqr = q3 - q1
        if iqr <= 0:
            upper_fence = float(q3) if q3 > 0 else median
            n_cap = max(1, int(np.ceil(upper_fence)))
        else:
            upper_fence = q3 + iqr_multiplier * iqr
            n_cap = max(1, int(np.ceil(upper_fence)))
        return median, upper_fence, n_cap

    def mean_coverage(self) -> float:
        """
        Mean coverage across positions (single-pass, O(n)).

        Returns:
            Mean of (mC + uC) over all positions.
        """
        cov = self.get_coverage()
        n = len(cov)
        if n == 0:
            return 0.0
        return float(np.mean(cov))

# Basic centroid class (aggregated from multiple samples to use naive methylation level calculation - deprecated)
class MethylBasicCentroid(MethylFrame):
    _required_cols = {"pos", "mC", "uC", "tnc", "N"}

    @property
    def N(self):
        return self._df["N"]

    @property
    def mean(self):
        """Pooled proportion mC/coverage. Only appropriate for single-sample centroids (N=1).
        For multi-sample centroids use MethylExtendedCentroid, which defines mean = Sx/N."""
        if "mean" not in self._df.columns:
            self._df["mean"] = (self.mC / self.coverage).astype("float32")
        return self._df["mean"]

    @property
    def is_centroid(self) -> bool:
        """Check if this is a centroid."""
        return True

    @property
    def sample_type(self) -> str:
        """Get the sample type."""
        return "basic_centroid"

    def get_sample_count(self) -> np.ndarray:
        """Get sample counts (N array)."""
        return self.N.values if hasattr(self.N, 'values') else np.asarray(self.N)

    def to_numpy(self, extended: bool = False) -> np.ndarray:
        """
        Convert MethylBasicCentroid to structured numpy array format.

        Args:
            extended: Whether to include extended centroid fields (always False for MethylBasicCentroid)

        Returns:
            Structured numpy array with centroid data
        """
        from methyl_utils import METHYL_CENTROID_DTYPE
        
        # Convert to CPU first
        df_cpu = self.to_cpu()._df
        
        # Use basic centroid dtype
        dtype = METHYL_CENTROID_DTYPE
        data = np.empty(len(df_cpu), dtype=dtype)
        data["pos"] = np.asarray(self._get_values(df_cpu["pos"]), dtype=np.uint32)
        data["mC"] = np.asarray(self._get_values(df_cpu["mC"]), dtype=np.uint32)
        data["uC"] = np.asarray(self._get_values(df_cpu["uC"]), dtype=np.uint32)
        data["tnc"] = np.asarray(self._get_values(df_cpu["tnc"]), dtype=np.uint8)
        data["N"] = np.asarray(self._get_values(df_cpu["N"]), dtype=np.uint32)

        return data

# Extended centroid class (aggregated from multiple samples to use Beta distribution parameter estimation)
class MethylExtendedCentroid(MethylBasicCentroid):
    _required_cols = {
        "pos",
        "mC",
        "uC",
        "tnc",
        "N",
        "Sx",
        "Sx2",
        "log_x_sum",
        "log_1_minus_x_sum",
    }
    # Sufficient stats to estimate Normal and Beta distribution parameters
    _required_stats = {"Sx", "Sx2", "log_x_sum", "log_1_minus_x_sum"}

    @property
    def mean(self):
        """Sample mean of proportions (Sx/N). Use this for comparisons; mC/coverage is only
        appropriate for single-sample centroids."""
        col = "_mean_sx_n"
        if col not in self._df.columns:
            N = self.N
            denom = N if getattr(N, "clip", None) else np.maximum(np.asarray(N), 1)
            if hasattr(denom, "clip"):
                denom = denom.clip(lower=1)
            else:
                denom = np.maximum(np.asarray(denom), 1)
            self._df[col] = (self.Sx / denom).astype("float64")
            if hasattr(self._df[col], "clip"):
                self._df[col] = self._df[col].clip(0.0, 1.0)
        return self._df[col]

    @property
    def alpha(self):
        if "alpha" not in self._df.columns:
            from methyl_utils.statistical_tests import beta_estimation_hybrid
            n = np.asarray(self._get_values(self.N), dtype=np.float64)
            Sx = np.asarray(self._get_values(self.Sx), dtype=np.float64)
            Sx2 = np.asarray(self._get_values(self.Sx2), dtype=np.float64)
            log_x = np.asarray(self._get_values(self._df["log_x_sum"]), dtype=np.float64)
            log_1mx = np.asarray(self._get_values(self._df["log_1_minus_x_sum"]), dtype=np.float64)
            alpha, beta = beta_estimation_hybrid(
                n=n, Sx=Sx, Sx2=Sx2,
                log_x_sum=log_x, log_1_minus_x_sum=log_1mx,
            )
            if self.is_gpu:
                self._df["alpha"] = cudf.Series(alpha, dtype="float64")
                self._df["beta"] = cudf.Series(beta, dtype="float64")
            else:
                self._df["alpha"] = pd.Series(alpha, dtype="float64", index=self._df.index)
                self._df["beta"] = pd.Series(beta, dtype="float64", index=self._df.index)
        return self._df["alpha"]

    # Beautiful name for alpha parameter
    @property
    def α(self):
        return self.alpha

    # Beta distribution beta parameter
    @property
    def beta(self):
        self.alpha  # trigger
        return self._df["beta"]

    # Beautiful name for beta parameter
    @property
    def β(self):
        return self.beta

    # Adaptive mean: same as mean (Sx/N) so we always use the sample mean of proportions.
    @property
    def adaptive_mean(self):
        """Same as mean (Sx/N). Kept for API compatibility with MethylDetector."""
        return self.mean

    # Lightning-fast context filters
    def cg(self):
        return self[self.context == "CG"]

    def chg(self):
        return self[self.context == "CHG"]

    def chh(self):
        return self[self.context == "CHH"]

    @property
    def is_extended_centroid(self) -> bool:
        """Check if this is an extended centroid."""
        return True

    @property
    def sample_type(self) -> str:
        """Get the sample type."""
        return "extended_centroid"

    @property
    def Sx(self):
        """Sum of methylation levels."""
        return self._df["Sx"]

    @property
    def Sx2(self):
        """Sum of squared methylation levels."""
        return self._df["Sx2"]

    @property
    def log_x_sum(self):
        """Sum of log(methylation_level)."""
        return self._df["log_x_sum"]

    @property
    def log_1_minus_x_sum(self):
        """Sum of log(1 - methylation_level)."""
        return self._df["log_1_minus_x_sum"]

    def to_numpy(self, extended: bool = True) -> np.ndarray:
        """
        Convert MethylExtendedCentroid to structured numpy array format.

        Args:
            extended: Whether to include extended centroid fields (always True for MethylExtendedCentroid)

        Returns:
            Structured numpy array with centroid data
        """
        from methyl_utils import METHYL_EXTENDED_ONLY_DTYPE

        # Convert to CPU first
        df_cpu = self.to_cpu()._df

        # MethylExtendedCentroid only has required Beta/Normal stats (no count columns)
        dtype = np.dtype(METHYL_EXTENDED_ONLY_DTYPE)
        data = np.empty(len(df_cpu), dtype=dtype)
        data["pos"] = np.asarray(self._get_values(df_cpu["pos"]), dtype=np.uint32)
        data["mC"] = np.asarray(self._get_values(df_cpu["mC"]), dtype=np.uint32)
        data["uC"] = np.asarray(self._get_values(df_cpu["uC"]), dtype=np.uint32)
        data["tnc"] = np.asarray(self._get_values(df_cpu["tnc"]), dtype=np.uint8)
        data["N"] = np.asarray(self._get_values(df_cpu["N"]), dtype=np.uint32)
        data["Sx"] = np.asarray(self._get_values(df_cpu["Sx"]), dtype=np.float32)
        data["Sx2"] = np.asarray(self._get_values(df_cpu["Sx2"]), dtype=np.float32)
        data["log_x_sum"] = np.asarray(self._get_values(df_cpu["log_x_sum"]), dtype=np.float32)
        data["log_1_minus_x_sum"] = np.asarray(self._get_values(df_cpu["log_1_minus_x_sum"]), dtype=np.float32)
        return data

    def add_sample(self, sample: "MethylSample") -> "MethylExtendedCentroid":
        """
        Add a sample to this centroid, returning a new MethylExtendedCentroid.
        
        Args:
            sample: MethylSample to add to the centroid
            
        Returns:
            New MethylExtendedCentroid with the sample added
        """
        # Convert to CPU for operations
        centroid_cpu = self.to_cpu()
        sample_cpu = sample.to_cpu()
        
        # Get numpy arrays
        centroid_pos = np.asarray(centroid_cpu.pos.values, dtype=np.uint32)
        centroid_mC_sum = np.asarray(centroid_cpu.mC.values, dtype=np.uint64) * np.asarray(centroid_cpu.N.values, dtype=np.uint64)
        centroid_uC_sum = np.asarray(centroid_cpu.uC.values, dtype=np.uint64) * np.asarray(centroid_cpu.N.values, dtype=np.uint64)
        centroid_N = np.asarray(centroid_cpu.N.values, dtype=np.uint32)
        centroid_Sx = np.asarray(centroid_cpu.Sx.values, dtype=np.float32)
        centroid_Sx2 = np.asarray(centroid_cpu.Sx2.values, dtype=np.float32)
        centroid_log_x_sum = np.asarray(centroid_cpu.log_x_sum.values, dtype=np.float32)
        centroid_log_1mx_sum = np.asarray(centroid_cpu.log_1_minus_x_sum.values, dtype=np.float32)
        centroid_tnc = np.asarray(centroid_cpu._df["tnc"].values, dtype=np.uint8)

        sample_pos = np.asarray(sample_cpu.pos.values, dtype=np.uint32)
        sample_mC = np.asarray(sample_cpu.mC.values, dtype=np.uint32)
        sample_uC = np.asarray(sample_cpu.uC.values, dtype=np.uint32)
        sample_tnc = np.asarray(sample_cpu._df["tnc"].values, dtype=np.uint8)
        
        # Calculate methylation levels for sample
        sample_coverage = sample_mC + sample_uC
        with np.errstate(divide='ignore', invalid='ignore'):
            sample_mean = np.where(sample_coverage > 0, sample_mC.astype(np.float32) / sample_coverage.astype(np.float32), 0.0)
        
        # Clip for log calculations - ensure we never get exactly 0 or 1
        # Use tighter bounds to avoid log(0) warnings
        eps = np.finfo(np.float32).eps * 10  # ~1e-6 for float32
        sample_mean_clipped = np.clip(sample_mean, eps, 1.0 - eps)
        # Ensure 1 - sample_mean_clipped is also >= eps to avoid log(0)
        one_minus_mean = np.clip(1.0 - sample_mean_clipped, eps, 1.0 - eps)
        with np.errstate(divide='ignore', invalid='ignore'):
            sample_log_x = np.log(sample_mean_clipped)
            sample_log_1mx = np.log(one_minus_mean)

        # Find common positions
        common_mask_centroid = np.isin(centroid_pos, sample_pos)
        common_mask_sample = np.isin(sample_pos, centroid_pos)
        
        # Update common positions
        if np.any(common_mask_centroid):
            # Find indices in sample for common positions
            sample_indices = np.searchsorted(sample_pos, centroid_pos[common_mask_centroid])
            valid_sample_mask = (sample_indices < len(sample_pos)) & (sample_pos[sample_indices] == centroid_pos[common_mask_centroid])
            
            centroid_mC_sum[common_mask_centroid] += np.where(valid_sample_mask, sample_mC[sample_indices].astype(np.uint64), np.uint64(0))
            centroid_uC_sum[common_mask_centroid] += np.where(valid_sample_mask, sample_uC[sample_indices].astype(np.uint64), np.uint64(0))
            centroid_N[common_mask_centroid] += np.where(valid_sample_mask, np.uint32(1), np.uint32(0))
            centroid_Sx[common_mask_centroid] += np.where(valid_sample_mask, sample_mean[sample_indices], 0)
            centroid_Sx2[common_mask_centroid] += np.where(valid_sample_mask, sample_mean[sample_indices]**2, 0)
            centroid_log_x_sum[common_mask_centroid] += np.where(valid_sample_mask, sample_log_x[sample_indices], 0)
            centroid_log_1mx_sum[common_mask_centroid] += np.where(valid_sample_mask, sample_log_1mx[sample_indices], 0)

        # Add new positions from sample
        new_pos_mask = ~common_mask_sample
        if np.any(new_pos_mask):
            new_pos = sample_pos[new_pos_mask]
            new_mC = sample_mC[new_pos_mask]
            new_uC = sample_uC[new_pos_mask]
            new_tnc = sample_tnc[new_pos_mask]
            new_mean = sample_mean[new_pos_mask]
            new_log_x = sample_log_x[new_pos_mask]
            new_log_1mx = sample_log_1mx[new_pos_mask]

            all_pos = np.concatenate([centroid_pos, new_pos])
            all_mC_sum = np.concatenate([centroid_mC_sum, new_mC.astype(np.uint64)])
            all_uC_sum = np.concatenate([centroid_uC_sum, new_uC.astype(np.uint64)])
            all_N = np.concatenate([centroid_N, np.ones(len(new_pos), dtype=np.uint32)])
            all_Sx = np.concatenate([centroid_Sx, new_mean])
            all_Sx2 = np.concatenate([centroid_Sx2, new_mean**2])
            all_log_x_sum = np.concatenate([centroid_log_x_sum, new_log_x])
            all_log_1mx_sum = np.concatenate([centroid_log_1mx_sum, new_log_1mx])
            all_tnc = np.concatenate([centroid_tnc, new_tnc])

            sort_idx = np.argsort(all_pos)
            all_pos = all_pos[sort_idx]
            all_mC_sum = all_mC_sum[sort_idx]
            all_uC_sum = all_uC_sum[sort_idx]
            all_N = all_N[sort_idx]
            all_Sx = all_Sx[sort_idx]
            all_Sx2 = all_Sx2[sort_idx]
            all_log_x_sum = all_log_x_sum[sort_idx]
            all_log_1mx_sum = all_log_1mx_sum[sort_idx]
            all_tnc = all_tnc[sort_idx]
        else:
            all_pos = centroid_pos
            all_mC_sum = centroid_mC_sum
            all_uC_sum = centroid_uC_sum
            all_N = centroid_N
            all_Sx = centroid_Sx
            all_Sx2 = centroid_Sx2
            all_log_x_sum = centroid_log_x_sum
            all_log_1mx_sum = centroid_log_1mx_sum
            all_tnc = centroid_tnc

        # Recalculate averaged mC/uC from sums
        with np.errstate(divide='ignore', invalid='ignore'):
            avg_mC = np.where(all_N > 0, (all_mC_sum / all_N.astype(np.float64)).astype(np.uint32), 0)
            avg_uC = np.where(all_N > 0, (all_uC_sum / all_N.astype(np.float64)).astype(np.uint32), 0)
        
        # Create new DataFrame
        new_df = pd.DataFrame({
            "pos": all_pos,
            "mC": avg_mC,
            "uC": avg_uC,
            "tnc": all_tnc,
            "N": all_N,
            "Sx": all_Sx.astype(np.float32),
            "Sx2": all_Sx2.astype(np.float32),
            "log_x_sum": all_log_x_sum.astype(np.float32),
            "log_1_minus_x_sum": all_log_1mx_sum.astype(np.float32),
        })

        # Preserve metadata
        new_metadata = self._metadata.copy() if self._metadata else {}
        if "n_samples" in new_metadata:
            new_metadata["n_samples"] = new_metadata.get("n_samples", 0) + 1
        else:
            new_metadata["n_samples"] = 1
        
        return MethylExtendedCentroid(new_df, metadata=new_metadata)

    def remove_sample(self, sample: "MethylSample") -> "MethylExtendedCentroid":
        """
        Remove a sample from this centroid, returning a new MethylExtendedCentroid.
        
        Args:
            sample: MethylSample to remove from the centroid
            
        Returns:
            New MethylExtendedCentroid with the sample removed
        """
        # Convert to CPU for operations
        centroid_cpu = self.to_cpu()
        sample_cpu = sample.to_cpu()
        
        # Get numpy arrays
        centroid_pos = np.asarray(centroid_cpu.pos.values, dtype=np.uint32)
        centroid_mC_sum = np.asarray(centroid_cpu.mC.values, dtype=np.uint64) * np.asarray(centroid_cpu.N.values, dtype=np.uint64)
        centroid_uC_sum = np.asarray(centroid_cpu.uC.values, dtype=np.uint64) * np.asarray(centroid_cpu.N.values, dtype=np.uint64)
        centroid_N = np.asarray(centroid_cpu.N.values, dtype=np.uint32)
        centroid_Sx = np.asarray(centroid_cpu.Sx.values, dtype=np.float32)
        centroid_Sx2 = np.asarray(centroid_cpu.Sx2.values, dtype=np.float32)
        centroid_log_x_sum = np.asarray(centroid_cpu.log_x_sum.values, dtype=np.float32)
        centroid_log_1mx_sum = np.asarray(centroid_cpu.log_1_minus_x_sum.values, dtype=np.float32)
        centroid_tnc = np.asarray(centroid_cpu._df["tnc"].values, dtype=np.uint8)
        
        sample_pos = np.asarray(sample_cpu.pos.values, dtype=np.uint32)
        sample_mC = np.asarray(sample_cpu.mC.values, dtype=np.uint32)
        sample_uC = np.asarray(sample_cpu.uC.values, dtype=np.uint32)
        
        # Calculate methylation levels for sample
        sample_coverage = sample_mC + sample_uC
        with np.errstate(divide='ignore', invalid='ignore'):
            sample_mean = np.where(sample_coverage > 0, sample_mC.astype(np.float32) / sample_coverage.astype(np.float32), 0.0)
        
        # Clip for log calculations - ensure we never get exactly 0 or 1
        # Use tighter bounds to avoid log(0) warnings
        eps = np.finfo(np.float32).eps * 10  # ~1e-6 for float32
        sample_mean_clipped = np.clip(sample_mean, eps, 1.0 - eps)
        # Ensure 1 - sample_mean_clipped is also >= eps to avoid log(0)
        one_minus_mean = np.clip(1.0 - sample_mean_clipped, eps, 1.0 - eps)
        with np.errstate(divide='ignore', invalid='ignore'):
            sample_log_x = np.log(sample_mean_clipped)
            sample_log_1mx = np.log(one_minus_mean)
        
        # Find common positions
        common_mask_centroid = np.isin(centroid_pos, sample_pos)
        
        if np.any(common_mask_centroid):
            # Find indices in sample for common positions
            sample_indices = np.searchsorted(sample_pos, centroid_pos[common_mask_centroid])
            valid_sample_mask = (sample_indices < len(sample_pos)) & (sample_pos[sample_indices] == centroid_pos[common_mask_centroid])
            
            # Subtract sample contributions
            centroid_mC_sum[common_mask_centroid] -= np.where(valid_sample_mask, sample_mC[sample_indices].astype(np.uint64), np.uint64(0))
            centroid_uC_sum[common_mask_centroid] -= np.where(valid_sample_mask, sample_uC[sample_indices].astype(np.uint64), np.uint64(0))
            centroid_N[common_mask_centroid] = np.maximum(0, centroid_N[common_mask_centroid] - np.where(valid_sample_mask, np.uint32(1), np.uint32(0)).astype(np.int32)).astype(np.uint32)
            centroid_Sx[common_mask_centroid] -= np.where(valid_sample_mask, sample_mean[sample_indices], 0)
            centroid_Sx2[common_mask_centroid] -= np.where(valid_sample_mask, sample_mean[sample_indices]**2, 0)
            centroid_log_x_sum[common_mask_centroid] -= np.where(valid_sample_mask, sample_log_x[sample_indices], 0)
            centroid_log_1mx_sum[common_mask_centroid] -= np.where(valid_sample_mask, sample_log_1mx[sample_indices], 0)

        # Keep only positions with N > 0
        valid_mask = centroid_N > 0
        
        if not np.any(valid_mask):
            raise ValueError("Cannot remove sample: centroid would have no valid positions")
        
        # Recalculate averaged mC/uC from sums
        with np.errstate(divide='ignore', invalid='ignore'):
            avg_mC = np.where(centroid_N[valid_mask] > 0, (centroid_mC_sum[valid_mask] / centroid_N[valid_mask].astype(np.float64)).astype(np.uint32), 0)
            avg_uC = np.where(centroid_N[valid_mask] > 0, (centroid_uC_sum[valid_mask] / centroid_N[valid_mask].astype(np.float64)).astype(np.uint32), 0)
        
        # Create new DataFrame
        new_df = pd.DataFrame({
            "pos": centroid_pos[valid_mask],
            "mC": avg_mC,
            "uC": avg_uC,
            "tnc": centroid_tnc[valid_mask],
            "N": centroid_N[valid_mask],
            "Sx": centroid_Sx[valid_mask].astype(np.float32),
            "Sx2": centroid_Sx2[valid_mask].astype(np.float32),
            "log_x_sum": centroid_log_x_sum[valid_mask].astype(np.float32),
            "log_1_minus_x_sum": centroid_log_1mx_sum[valid_mask].astype(np.float32),
        })

        new_metadata = self._metadata.copy() if self._metadata else {}
        if "n_samples" in new_metadata:
            new_metadata["n_samples"] = max(0, new_metadata.get("n_samples", 1) - 1)

        return MethylExtendedCentroid(new_df, metadata=new_metadata)

    @classmethod
    def from_centroid_data(
        cls,
        data: Union[Dict[str, np.ndarray], np.ndarray],
        metadata: Optional[Dict[str, Any]] = None
    ) -> "MethylExtendedCentroid":
        """
        Create MethylExtendedCentroid from data dictionary or structured array.

        Args:
            data: Dictionary with arrays or structured numpy array
            metadata: Optional metadata

        Returns:
            MethylExtendedCentroid instance
        """
        if isinstance(data, np.ndarray):
            # Structured array
            df = pd.DataFrame({
                "pos": data["pos"],
                "mC": data["mC"],
                "uC": data["uC"],
                "tnc": data["tnc"],
                "N": data["N"],
                "Sx": data["Sx"],
                "Sx2": data["Sx2"],
                "log_x_sum": data["log_x_sum"],
                "log_1_minus_x_sum": data["log_1_minus_x_sum"],
            })
        else:
            # Dictionary
            df = pd.DataFrame(data)
        return cls(df, metadata)


# Beta-Binomial centroid: extends extended centroid with required count-based columns
_BB_COUNT_COLS = {
    "sum_mC", "sum_uC", "sum_cov", "sum_cov2", "sum_mC2", "sum_uC2",
    "Sx3", "Sx4", "count_zero", "count_one",
}


class MethylBetaBinomialCentroid(MethylExtendedCentroid):
    """
    Centroid with count-based sufficient statistics for Beta-Binomial at each position.
    Requires count columns (sum_mC, sum_uC, sum_cov, etc.); not present on MethylExtendedCentroid.
    """
    _required_cols = MethylExtendedCentroid._required_cols | _BB_COUNT_COLS

    @property
    def sum_mC(self):
        return self._df["sum_mC"]

    @property
    def sum_uC(self):
        return self._df["sum_uC"]

    @property
    def sum_cov(self):
        return self._df["sum_cov"]

    @property
    def sum_cov2(self):
        return self._df["sum_cov2"]

    @property
    def sum_mC2(self):
        return self._df["sum_mC2"]

    @property
    def sum_uC2(self):
        return self._df["sum_uC2"]

    @property
    def Sx3(self):
        return self._df["Sx3"]

    @property
    def Sx4(self):
        return self._df["Sx4"]

    @property
    def count_zero(self):
        return self._df["count_zero"]

    @property
    def count_one(self):
        return self._df["count_one"]

    @property
    def alpha_bb(self):
        """Beta-Binomial α from discrete count statistics (MoM: sum_mC, sum_mC2, sum_cov).
        Uses count-based sufficient stats, not proportion MoM, so the discrete model is respected."""
        if "alpha_bb" not in self._df.columns:
            from methyl_utils.statistical_tests import beta_binomial_mom_estimation
            n_samples = np.asarray(self._get_values(self.N), dtype=np.float64)
            sum_mC = np.asarray(self._get_values(self.sum_mC), dtype=np.float64)
            sum_mC2 = np.asarray(self._get_values(self.sum_mC2), dtype=np.float64)
            sum_cov = np.asarray(self._get_values(self.sum_cov), dtype=np.float64)
            alpha, beta = beta_binomial_mom_estimation(
                n_samples=n_samples, sum_mC=sum_mC, sum_mC2=sum_mC2, sum_cov=sum_cov
            )
            if self.is_gpu:
                self._df["alpha_bb"] = cudf.Series(alpha, dtype="float64")
                self._df["beta_bb"] = cudf.Series(beta, dtype="float64")
            else:
                self._df["alpha_bb"] = pd.Series(alpha, dtype="float64", index=self._df.index)
                self._df["beta_bb"] = pd.Series(beta, dtype="float64", index=self._df.index)
        return self._df["alpha_bb"]

    @property
    def beta_bb(self):
        self.alpha_bb  # trigger
        return self._df["beta_bb"]

    @property
    def mean(self):
        """Beta-Binomial mean α_bb/(α_bb+β_bb) from count-based MoM parameters.
        This is the correct mean for the discrete model and is generally better than
        the Beta approximation unless N is large (both converge as N increases)."""
        a, b = self.alpha_bb.values, self.beta_bb.values
        if hasattr(a, "__cuda_array_interface__"):
            a, b = np.asarray(a), np.asarray(b)
        tau = np.maximum(a + b, 1e-12)
        mu = np.where(tau > 0, a / tau, 0.5)
        if self.is_gpu:
            return cudf.Series(mu, dtype="float64", index=self._df.index)
        return pd.Series(mu, dtype="float64", index=self._df.index)

    def overlap(self, other: Union["MethylBetaBinomialCentroid", "MethylExtendedCentroid"]) -> np.ndarray:
        """Overlap with another centroid (Bhattacharyya coefficient of Beta distributions)."""
        from methyl_utils.beta_analytics import compute_bhattacharyya_coefficient
        a1 = np.asarray(self.alpha_bb.values, dtype=np.float64)
        b1 = np.asarray(self.beta_bb.values, dtype=np.float64)
        if isinstance(other, MethylBetaBinomialCentroid):
            a2 = np.asarray(other.alpha_bb.values, dtype=np.float64)
            b2 = np.asarray(other.beta_bb.values, dtype=np.float64)
        else:
            a2 = np.asarray(other.alpha.values, dtype=np.float64)
            b2 = np.asarray(other.beta.values, dtype=np.float64)
        n = min(len(a1), len(a2))
        return compute_bhattacharyya_coefficient(a1[:n], b1[:n], a2[:n], b2[:n], use_gpu=False)

    def to_numpy(self, extended: bool = True) -> np.ndarray:
        from methyl_utils import METHYL_EXTENDED_CENTROID_DTYPE
        df_cpu = self.to_cpu()._df
        dtype = np.dtype(METHYL_EXTENDED_CENTROID_DTYPE)
        data = np.empty(len(df_cpu), dtype=dtype)
        data["pos"] = np.asarray(df_cpu["pos"].values, dtype=np.uint32)
        data["mC"] = np.asarray(df_cpu["mC"].values, dtype=np.uint32)
        data["uC"] = np.asarray(df_cpu["uC"].values, dtype=np.uint32)
        data["tnc"] = np.asarray(df_cpu["tnc"].values, dtype=np.uint8)
        data["N"] = np.asarray(df_cpu["N"].values, dtype=np.uint32)
        data["Sx"] = np.asarray(df_cpu["Sx"].values, dtype=np.float32)
        data["Sx2"] = np.asarray(df_cpu["Sx2"].values, dtype=np.float32)
        data["log_x_sum"] = np.asarray(df_cpu["log_x_sum"].values, dtype=np.float32)
        data["log_1_minus_x_sum"] = np.asarray(df_cpu["log_1_minus_x_sum"].values, dtype=np.float32)
        data["sum_mC"] = np.asarray(df_cpu["sum_mC"].values, dtype=np.uint64)
        data["sum_uC"] = np.asarray(df_cpu["sum_uC"].values, dtype=np.uint64)
        data["sum_cov"] = np.asarray(df_cpu["sum_cov"].values, dtype=np.uint64)
        data["sum_cov2"] = np.asarray(df_cpu["sum_cov2"].values, dtype=np.float64)
        data["sum_mC2"] = np.asarray(df_cpu["sum_mC2"].values, dtype=np.float64)
        data["sum_uC2"] = np.asarray(df_cpu["sum_uC2"].values, dtype=np.float64)
        data["Sx3"] = np.asarray(df_cpu["Sx3"].values, dtype=np.float32)
        data["Sx4"] = np.asarray(df_cpu["Sx4"].values, dtype=np.float32)
        data["count_zero"] = np.asarray(df_cpu["count_zero"].values, dtype=np.uint32)
        data["count_one"] = np.asarray(df_cpu["count_one"].values, dtype=np.uint32)
        return data

    def add_sample(self, sample: "MethylSample") -> "MethylBetaBinomialCentroid":
        """Add a sample to this centroid; updates count stats and returns MethylBetaBinomialCentroid."""
        centroid_cpu = self.to_cpu()
        sample_cpu = sample.to_cpu()
        centroid_pos = np.asarray(centroid_cpu.pos.values, dtype=np.uint32)
        centroid_mC_sum = np.asarray(centroid_cpu.mC.values, dtype=np.uint64) * np.asarray(centroid_cpu.N.values, dtype=np.uint64)
        centroid_uC_sum = np.asarray(centroid_cpu.uC.values, dtype=np.uint64) * np.asarray(centroid_cpu.N.values, dtype=np.uint64)
        centroid_N = np.asarray(centroid_cpu.N.values, dtype=np.uint32)
        centroid_Sx = np.asarray(centroid_cpu.Sx.values, dtype=np.float32)
        centroid_Sx2 = np.asarray(centroid_cpu.Sx2.values, dtype=np.float32)
        centroid_log_x_sum = np.asarray(centroid_cpu.log_x_sum.values, dtype=np.float32)
        centroid_log_1mx_sum = np.asarray(centroid_cpu.log_1_minus_x_sum.values, dtype=np.float32)
        centroid_tnc = np.asarray(centroid_cpu._df["tnc"].values, dtype=np.uint8)
        centroid_sum_cov = np.asarray(centroid_cpu._df["sum_cov"].values, dtype=np.uint64)
        centroid_sum_cov2 = np.asarray(centroid_cpu._df["sum_cov2"].values, dtype=np.float64)
        centroid_sum_mC = np.asarray(centroid_cpu._df["sum_mC"].values, dtype=np.uint64)
        centroid_sum_uC = np.asarray(centroid_cpu._df["sum_uC"].values, dtype=np.uint64)
        centroid_sum_mC2 = np.asarray(centroid_cpu._df["sum_mC2"].values, dtype=np.float64)
        centroid_sum_uC2 = np.asarray(centroid_cpu._df["sum_uC2"].values, dtype=np.float64)
        centroid_Sx3 = np.asarray(centroid_cpu._df["Sx3"].values, dtype=np.float32)
        centroid_Sx4 = np.asarray(centroid_cpu._df["Sx4"].values, dtype=np.float32)
        centroid_count_zero = np.asarray(centroid_cpu._df["count_zero"].values, dtype=np.uint32)
        centroid_count_one = np.asarray(centroid_cpu._df["count_one"].values, dtype=np.uint32)

        sample_pos = np.asarray(sample_cpu.pos.values, dtype=np.uint32)
        sample_mC = np.asarray(sample_cpu.mC.values, dtype=np.uint32)
        sample_uC = np.asarray(sample_cpu.uC.values, dtype=np.uint32)
        sample_tnc = np.asarray(sample_cpu._df["tnc"].values, dtype=np.uint8)
        sample_coverage = sample_mC + sample_uC
        with np.errstate(divide="ignore", invalid="ignore"):
            sample_mean = np.where(sample_coverage > 0, sample_mC.astype(np.float32) / sample_coverage.astype(np.float32), 0.0)
        eps = np.finfo(np.float32).eps * 10
        sample_mean_clipped = np.clip(sample_mean, eps, 1.0 - eps)
        one_minus_mean = np.clip(1.0 - sample_mean_clipped, eps, 1.0 - eps)
        with np.errstate(divide="ignore", invalid="ignore"):
            sample_log_x = np.log(sample_mean_clipped)
            sample_log_1mx = np.log(one_minus_mean)
        sample_cov = sample_coverage.astype(np.uint64)
        sample_cov2 = sample_cov.astype(np.float64) ** 2
        sample_mC2 = sample_mC.astype(np.float64) ** 2
        sample_uC2 = sample_uC.astype(np.float64) ** 2
        sample_mean3 = sample_mean.astype(np.float32) ** 3
        sample_mean4 = sample_mean.astype(np.float32) ** 4
        sample_zero = ((sample_mC == 0) & (sample_coverage > 0)).astype(np.uint32)
        sample_one = ((sample_uC == 0) & (sample_coverage > 0)).astype(np.uint32)

        common_mask_centroid = np.isin(centroid_pos, sample_pos)
        common_mask_sample = np.isin(sample_pos, centroid_pos)
        if np.any(common_mask_centroid):
            sample_indices = np.searchsorted(sample_pos, centroid_pos[common_mask_centroid])
            valid = (sample_indices < len(sample_pos)) & (sample_pos[sample_indices] == centroid_pos[common_mask_centroid])
            centroid_mC_sum[common_mask_centroid] += np.where(valid, sample_mC[sample_indices].astype(np.uint64), 0)
            centroid_uC_sum[common_mask_centroid] += np.where(valid, sample_uC[sample_indices].astype(np.uint64), 0)
            centroid_N[common_mask_centroid] += np.where(valid, np.uint32(1), 0)
            centroid_Sx[common_mask_centroid] += np.where(valid, sample_mean[sample_indices], 0)
            centroid_Sx2[common_mask_centroid] += np.where(valid, sample_mean[sample_indices] ** 2, 0)
            centroid_log_x_sum[common_mask_centroid] += np.where(valid, sample_log_x[sample_indices], 0)
            centroid_log_1mx_sum[common_mask_centroid] += np.where(valid, sample_log_1mx[sample_indices], 0)
            centroid_sum_cov[common_mask_centroid] += np.where(valid, sample_cov[sample_indices], 0)
            centroid_sum_cov2[common_mask_centroid] += np.where(valid, sample_cov2[sample_indices], 0)
            centroid_sum_mC[common_mask_centroid] += np.where(valid, sample_mC[sample_indices].astype(np.uint64), 0)
            centroid_sum_uC[common_mask_centroid] += np.where(valid, sample_uC[sample_indices].astype(np.uint64), 0)
            centroid_sum_mC2[common_mask_centroid] += np.where(valid, sample_mC2[sample_indices], 0)
            centroid_sum_uC2[common_mask_centroid] += np.where(valid, sample_uC2[sample_indices], 0)
            centroid_Sx3[common_mask_centroid] += np.where(valid, sample_mean3[sample_indices], 0)
            centroid_Sx4[common_mask_centroid] += np.where(valid, sample_mean4[sample_indices], 0)
            centroid_count_zero[common_mask_centroid] += np.where(valid, sample_zero[sample_indices], 0)
            centroid_count_one[common_mask_centroid] += np.where(valid, sample_one[sample_indices], 0)

        new_pos_mask = ~common_mask_sample
        if np.any(new_pos_mask):
            new_pos = sample_pos[new_pos_mask]
            new_mC = sample_mC[new_pos_mask]
            new_uC = sample_uC[new_pos_mask]
            new_tnc = sample_tnc[new_pos_mask]
            new_mean = sample_mean[new_pos_mask]
            new_log_x = sample_log_x[new_pos_mask]
            new_log_1mx = sample_log_1mx[new_pos_mask]
            new_cov = sample_cov[new_pos_mask]
            new_cov2 = sample_cov2[new_pos_mask]
            new_mC2 = sample_mC2[new_pos_mask]
            new_uC2 = sample_uC2[new_pos_mask]
            new_mean3 = sample_mean3[new_pos_mask]
            new_mean4 = sample_mean4[new_pos_mask]
            new_zero = sample_zero[new_pos_mask]
            new_one = sample_one[new_pos_mask]
            all_pos = np.concatenate([centroid_pos, new_pos])
            all_mC_sum = np.concatenate([centroid_mC_sum, new_mC.astype(np.uint64)])
            all_uC_sum = np.concatenate([centroid_uC_sum, new_uC.astype(np.uint64)])
            all_N = np.concatenate([centroid_N, np.ones(len(new_pos), dtype=np.uint32)])
            all_Sx = np.concatenate([centroid_Sx, new_mean])
            all_Sx2 = np.concatenate([centroid_Sx2, new_mean ** 2])
            all_log_x_sum = np.concatenate([centroid_log_x_sum, new_log_x])
            all_log_1mx_sum = np.concatenate([centroid_log_1mx_sum, new_log_1mx])
            all_tnc = np.concatenate([centroid_tnc, new_tnc])
            all_sum_cov = np.concatenate([centroid_sum_cov, new_cov])
            all_sum_cov2 = np.concatenate([centroid_sum_cov2, new_cov2])
            all_sum_mC = np.concatenate([centroid_sum_mC, new_mC.astype(np.uint64)])
            all_sum_uC = np.concatenate([centroid_sum_uC, new_uC.astype(np.uint64)])
            all_sum_mC2 = np.concatenate([centroid_sum_mC2, new_mC2])
            all_sum_uC2 = np.concatenate([centroid_sum_uC2, new_uC2])
            all_Sx3 = np.concatenate([centroid_Sx3, new_mean3])
            all_Sx4 = np.concatenate([centroid_Sx4, new_mean4])
            all_count_zero = np.concatenate([centroid_count_zero, new_zero])
            all_count_one = np.concatenate([centroid_count_one, new_one])
            sort_idx = np.argsort(all_pos)
            all_pos = all_pos[sort_idx]
            all_mC_sum = all_mC_sum[sort_idx]
            all_uC_sum = all_uC_sum[sort_idx]
            all_N = all_N[sort_idx]
            all_Sx = all_Sx[sort_idx]
            all_Sx2 = all_Sx2[sort_idx]
            all_log_x_sum = all_log_x_sum[sort_idx]
            all_log_1mx_sum = all_log_1mx_sum[sort_idx]
            all_tnc = all_tnc[sort_idx]
            all_sum_cov = all_sum_cov[sort_idx]
            all_sum_cov2 = all_sum_cov2[sort_idx]
            all_sum_mC = all_sum_mC[sort_idx]
            all_sum_uC = all_sum_uC[sort_idx]
            all_sum_mC2 = all_sum_mC2[sort_idx]
            all_sum_uC2 = all_sum_uC2[sort_idx]
            all_Sx3 = all_Sx3[sort_idx]
            all_Sx4 = all_Sx4[sort_idx]
            all_count_zero = all_count_zero[sort_idx]
            all_count_one = all_count_one[sort_idx]
        else:
            all_pos = centroid_pos
            all_mC_sum = centroid_mC_sum
            all_uC_sum = centroid_uC_sum
            all_N = centroid_N
            all_Sx = centroid_Sx
            all_Sx2 = centroid_Sx2
            all_log_x_sum = centroid_log_x_sum
            all_log_1mx_sum = centroid_log_1mx_sum
            all_tnc = centroid_tnc
            all_sum_cov = centroid_sum_cov
            all_sum_cov2 = centroid_sum_cov2
            all_sum_mC = centroid_sum_mC
            all_sum_uC = centroid_sum_uC
            all_sum_mC2 = centroid_sum_mC2
            all_sum_uC2 = centroid_sum_uC2
            all_Sx3 = centroid_Sx3
            all_Sx4 = centroid_Sx4
            all_count_zero = centroid_count_zero
            all_count_one = centroid_count_one

        with np.errstate(divide="ignore", invalid="ignore"):
            avg_mC = np.where(all_N > 0, (all_mC_sum / all_N.astype(np.float64)).astype(np.uint32), 0)
            avg_uC = np.where(all_N > 0, (all_uC_sum / all_N.astype(np.float64)).astype(np.uint32), 0)
        new_df = pd.DataFrame({
            "pos": all_pos, "mC": avg_mC, "uC": avg_uC, "tnc": all_tnc, "N": all_N,
            "Sx": all_Sx.astype(np.float32), "Sx2": all_Sx2.astype(np.float32),
            "log_x_sum": all_log_x_sum.astype(np.float32), "log_1_minus_x_sum": all_log_1mx_sum.astype(np.float32),
            "sum_cov": all_sum_cov.astype(np.uint64), "sum_cov2": all_sum_cov2.astype(np.float64),
            "sum_mC": all_sum_mC.astype(np.uint64), "sum_uC": all_sum_uC.astype(np.uint64),
            "sum_mC2": all_sum_mC2.astype(np.float64), "sum_uC2": all_sum_uC2.astype(np.float64),
            "Sx3": all_Sx3.astype(np.float32), "Sx4": all_Sx4.astype(np.float32),
            "count_zero": all_count_zero.astype(np.uint32), "count_one": all_count_one.astype(np.uint32),
        })
        new_metadata = self._metadata.copy() if self._metadata else {}
        new_metadata["n_samples"] = new_metadata.get("n_samples", 0) + 1
        return MethylBetaBinomialCentroid(new_df, metadata=new_metadata)

    def remove_sample(self, sample: "MethylSample") -> "MethylBetaBinomialCentroid":
        """Remove a sample from this centroid; returns MethylBetaBinomialCentroid."""
        centroid_cpu = self.to_cpu()
        sample_cpu = sample.to_cpu()
        centroid_pos = np.asarray(centroid_cpu.pos.values, dtype=np.uint32)
        centroid_mC_sum = np.asarray(centroid_cpu.mC.values, dtype=np.uint64) * np.asarray(centroid_cpu.N.values, dtype=np.uint64)
        centroid_uC_sum = np.asarray(centroid_cpu.uC.values, dtype=np.uint64) * np.asarray(centroid_cpu.N.values, dtype=np.uint64)
        centroid_N = np.asarray(centroid_cpu.N.values, dtype=np.uint32)
        centroid_Sx = np.asarray(centroid_cpu.Sx.values, dtype=np.float32)
        centroid_Sx2 = np.asarray(centroid_cpu.Sx2.values, dtype=np.float32)
        centroid_log_x_sum = np.asarray(centroid_cpu.log_x_sum.values, dtype=np.float32)
        centroid_log_1mx_sum = np.asarray(centroid_cpu.log_1_minus_x_sum.values, dtype=np.float32)
        centroid_tnc = np.asarray(centroid_cpu._df["tnc"].values, dtype=np.uint8)
        centroid_sum_cov = np.asarray(centroid_cpu._df["sum_cov"].values, dtype=np.uint64)
        centroid_sum_cov2 = np.asarray(centroid_cpu._df["sum_cov2"].values, dtype=np.float64)
        centroid_sum_mC = np.asarray(centroid_cpu._df["sum_mC"].values, dtype=np.uint64)
        centroid_sum_uC = np.asarray(centroid_cpu._df["sum_uC"].values, dtype=np.uint64)
        centroid_sum_mC2 = np.asarray(centroid_cpu._df["sum_mC2"].values, dtype=np.float64)
        centroid_sum_uC2 = np.asarray(centroid_cpu._df["sum_uC2"].values, dtype=np.float64)
        centroid_Sx3 = np.asarray(centroid_cpu._df["Sx3"].values, dtype=np.float32)
        centroid_Sx4 = np.asarray(centroid_cpu._df["Sx4"].values, dtype=np.float32)
        centroid_count_zero = np.asarray(centroid_cpu._df["count_zero"].values, dtype=np.uint32)
        centroid_count_one = np.asarray(centroid_cpu._df["count_one"].values, dtype=np.uint32)
        sample_pos = np.asarray(sample_cpu.pos.values, dtype=np.uint32)
        sample_mC = np.asarray(sample_cpu.mC.values, dtype=np.uint32)
        sample_uC = np.asarray(sample_cpu.uC.values, dtype=np.uint32)
        sample_coverage = sample_mC + sample_uC
        with np.errstate(divide="ignore", invalid="ignore"):
            sample_mean = np.where(sample_coverage > 0, sample_mC.astype(np.float32) / sample_coverage.astype(np.float32), 0.0)
        eps = np.finfo(np.float32).eps * 10
        sample_mean_clipped = np.clip(sample_mean, eps, 1.0 - eps)
        one_minus_mean = np.clip(1.0 - sample_mean_clipped, eps, 1.0 - eps)
        with np.errstate(divide="ignore", invalid="ignore"):
            sample_log_x = np.log(sample_mean_clipped)
            sample_log_1mx = np.log(one_minus_mean)
        sample_cov = sample_coverage.astype(np.uint64)
        sample_cov2 = sample_cov.astype(np.float64) ** 2
        sample_mC2 = sample_mC.astype(np.float64) ** 2
        sample_uC2 = sample_uC.astype(np.float64) ** 2
        sample_mean3 = sample_mean.astype(np.float32) ** 3
        sample_mean4 = sample_mean.astype(np.float32) ** 4
        sample_zero = ((sample_mC == 0) & (sample_coverage > 0)).astype(np.uint32)
        sample_one = ((sample_uC == 0) & (sample_coverage > 0)).astype(np.uint32)
        common_mask_centroid = np.isin(centroid_pos, sample_pos)
        if np.any(common_mask_centroid):
            sample_indices = np.searchsorted(sample_pos, centroid_pos[common_mask_centroid])
            valid = (sample_indices < len(sample_pos)) & (sample_pos[sample_indices] == centroid_pos[common_mask_centroid])
            centroid_mC_sum[common_mask_centroid] -= np.where(valid, sample_mC[sample_indices].astype(np.uint64), 0)
            centroid_uC_sum[common_mask_centroid] -= np.where(valid, sample_uC[sample_indices].astype(np.uint64), 0)
            centroid_N[common_mask_centroid] = np.maximum(0, centroid_N[common_mask_centroid] - np.where(valid, np.uint32(1), 0).astype(np.int32)).astype(np.uint32)
            centroid_Sx[common_mask_centroid] -= np.where(valid, sample_mean[sample_indices], 0)
            centroid_Sx2[common_mask_centroid] -= np.where(valid, sample_mean[sample_indices] ** 2, 0)
            centroid_log_x_sum[common_mask_centroid] -= np.where(valid, sample_log_x[sample_indices], 0)
            centroid_log_1mx_sum[common_mask_centroid] -= np.where(valid, sample_log_1mx[sample_indices], 0)
            centroid_sum_cov[common_mask_centroid] -= np.where(valid, sample_cov[sample_indices], 0)
            centroid_sum_cov2[common_mask_centroid] -= np.where(valid, sample_cov2[sample_indices], 0)
            centroid_sum_mC[common_mask_centroid] -= np.where(valid, sample_mC[sample_indices].astype(np.uint64), 0)
            centroid_sum_uC[common_mask_centroid] -= np.where(valid, sample_uC[sample_indices].astype(np.uint64), 0)
            centroid_sum_mC2[common_mask_centroid] -= np.where(valid, sample_mC2[sample_indices], 0)
            centroid_sum_uC2[common_mask_centroid] -= np.where(valid, sample_uC2[sample_indices], 0)
            centroid_Sx3[common_mask_centroid] -= np.where(valid, sample_mean3[sample_indices], 0)
            centroid_Sx4[common_mask_centroid] -= np.where(valid, sample_mean4[sample_indices], 0)
            centroid_count_zero[common_mask_centroid] -= np.where(valid, sample_zero[sample_indices], 0)
            centroid_count_one[common_mask_centroid] -= np.where(valid, sample_one[sample_indices], 0)
        valid_mask = centroid_N > 0
        if not np.any(valid_mask):
            raise ValueError("Cannot remove sample: centroid would have no valid positions")
        with np.errstate(divide="ignore", invalid="ignore"):
            avg_mC = np.where(centroid_N[valid_mask] > 0, (centroid_mC_sum[valid_mask] / centroid_N[valid_mask].astype(np.float64)).astype(np.uint32), 0)
            avg_uC = np.where(centroid_N[valid_mask] > 0, (centroid_uC_sum[valid_mask] / centroid_N[valid_mask].astype(np.float64)).astype(np.uint32), 0)
        new_df = pd.DataFrame({
            "pos": centroid_pos[valid_mask], "mC": avg_mC, "uC": avg_uC, "tnc": centroid_tnc[valid_mask],
            "N": centroid_N[valid_mask],
            "Sx": centroid_Sx[valid_mask].astype(np.float32), "Sx2": centroid_Sx2[valid_mask].astype(np.float32),
            "log_x_sum": centroid_log_x_sum[valid_mask].astype(np.float32), "log_1_minus_x_sum": centroid_log_1mx_sum[valid_mask].astype(np.float32),
            "sum_cov": centroid_sum_cov[valid_mask].astype(np.uint64), "sum_cov2": centroid_sum_cov2[valid_mask].astype(np.float64),
            "sum_mC": centroid_sum_mC[valid_mask].astype(np.uint64), "sum_uC": centroid_sum_uC[valid_mask].astype(np.uint64),
            "sum_mC2": centroid_sum_mC2[valid_mask].astype(np.float64), "sum_uC2": centroid_sum_uC2[valid_mask].astype(np.float64),
            "Sx3": centroid_Sx3[valid_mask].astype(np.float32), "Sx4": centroid_Sx4[valid_mask].astype(np.float32),
            "count_zero": centroid_count_zero[valid_mask].astype(np.uint32), "count_one": centroid_count_one[valid_mask].astype(np.uint32),
        })
        new_metadata = self._metadata.copy() if self._metadata else {}
        new_metadata["n_samples"] = max(0, new_metadata.get("n_samples", 1) - 1)
        return MethylBetaBinomialCentroid(new_df, metadata=new_metadata)


def compute_coverage_outlier_flags(
    samples: List[MethylSample],
    *,
    method: Literal["robust_z", "iqr"] = "robust_z",
    threshold: float = 3.5,
    max_positions: int = 100_000,
    seed: Optional[int] = None,
) -> List[bool]:
    """
    Flag samples with outlying coverage (for optional capping).

    Computes a per-sample coverage summary (sampled median) and flags samples
    that are outliers using robust z-score or IQR. Use the result to cap only
    flagged samples: e.g. for i, s in enumerate(samples): if flags[i]: s.cap_coverage_binomial(n_cap=35, seed=0).

    Args:
        samples: List of MethylSample instances.
        method: "robust_z" (median, MAD, rz = 0.6745*(x-med)/mad, flag rz > threshold)
            or "iqr" (flag summary > Q3 + 1.5*IQR).
        threshold: For robust_z, flag when robust z-score > threshold (default 3.5).
        max_positions: Passed to each sample's median_coverage (sampled median).
        seed: Passed to each sample's median_coverage for reproducibility.

    Returns:
        List of bool, one per sample: True if that sample is flagged as outlier.
    """
    if not samples:
        return []
    summaries = np.array(
        [s.median_coverage(max_positions=max_positions, seed=seed) for s in samples],
        dtype=np.float64,
    )
    if method == "robust_z":
        med = np.median(summaries)
        mad = np.median(np.abs(summaries - med))
        if mad <= 0:
            return [False] * len(samples)
        rz = 0.6745 * (summaries - med) / mad
        return (rz > threshold).tolist()
    if method == "iqr":
        q1, q3 = np.percentile(summaries, [25, 75])
        iqr = q3 - q1
        if iqr <= 0:
            return [False] * len(samples)
        return (summaries > q3 + 1.5 * iqr).tolist()
    raise ValueError(f"method must be 'robust_z' or 'iqr', got {method!r}")
