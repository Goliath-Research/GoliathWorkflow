# methyl_utils/core/centroid_builder.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Dict, Any, Union, List

import numpy as np
import pandas as pd

# GPU support — transparent and lazy
try:
    import cupy as cp
    from cupy import ndarray as CuArray

    HAS_GPU = True
except ImportError:
    cp = np
    CuArray = np.ndarray
    HAS_GPU = False

from .methyl_frame import MethylExtendedCentroid
from .io import load_from_h5  # or your preferred loader

logger = logging.getLogger(__name__)


class MethylCentroidBuilder:
    """
    The one and only way to build extended centroids in 2025+.
    Streaming, GPU-accelerated, memory-efficient, and outputs clean MethylExtendedCentroid.
    Replaces PositionAligner + old MethylSample logic completely.
    """

    def __init__(
        self,
        min_coverage: int = 4,
        use_gpu: bool = True,
        chunk_size: int = 100_000_000,  # ~100M positions → covers hg38 + margin
        metadata: Optional[Dict[str, Any]] = None,
        store_extended_stats: bool = True,
    ):
        self.min_coverage = min_coverage
        self.use_gpu = use_gpu and HAS_GPU
        self.xp = cp if self.use_gpu else np
        self.metadata = metadata or {}
        self.store_extended_stats = store_extended_stats

        logger.info(f"MethylCentroidBuilder initialized → GPU: {self.use_gpu}")

        # Dynamic accumulators
        self.pos: CuArray = self.xp.zeros(chunk_size, dtype=np.uint32)
        self.mC_sum: CuArray = self.xp.zeros(chunk_size, dtype=np.uint64)
        self.uC_sum: CuArray = self.xp.zeros(chunk_size, dtype=np.uint64)
        self.N: CuArray = self.xp.zeros(chunk_size, dtype=np.uint32)
        self.Sx: CuArray = self.xp.zeros(chunk_size, dtype=np.float32)
        self.Sx2: CuArray = self.xp.zeros(chunk_size, dtype=np.float32)
        self.log_x_sum: CuArray = self.xp.zeros(chunk_size, dtype=np.float32)
        self.log_1x_sum: CuArray = self.xp.zeros(chunk_size, dtype=np.float32)
        self.tnc: CuArray = self.xp.zeros(chunk_size, dtype=np.uint8)

        # Extended sufficient stats for additional distributions
        if self.store_extended_stats:
            self.sum_cov: CuArray = self.xp.zeros(chunk_size, dtype=np.uint64)
            self.sum_cov2: CuArray = self.xp.zeros(chunk_size, dtype=np.float64)
            self.sum_mC: CuArray = self.xp.zeros(chunk_size, dtype=np.uint64)
            self.sum_uC: CuArray = self.xp.zeros(chunk_size, dtype=np.uint64)
            self.sum_mC2: CuArray = self.xp.zeros(chunk_size, dtype=np.float64)
            self.sum_uC2: CuArray = self.xp.zeros(chunk_size, dtype=np.float64)
            self.Sx3: CuArray = self.xp.zeros(chunk_size, dtype=np.float32)
            self.Sx4: CuArray = self.xp.zeros(chunk_size, dtype=np.float32)
            self.count_zero: CuArray = self.xp.zeros(chunk_size, dtype=np.uint32)
            self.count_one: CuArray = self.xp.zeros(chunk_size, dtype=np.uint32)

        self.size = 0
        self.capacity = chunk_size
        self.samples_processed = 0

    def _grow(self, min_needed: int):
        new_cap = max(min_needed, int(self.capacity * 1.6))
        logger.debug(f"Growing accumulators: {self.capacity:,} → {new_cap:,} positions")

        grow_attrs = [
            "pos",
            "mC_sum",
            "uC_sum",
            "N",
            "Sx",
            "Sx2",
            "log_x_sum",
            "log_1x_sum",
            "tnc",
        ]
        if self.store_extended_stats:
            grow_attrs.extend([
                "sum_cov",
                "sum_cov2",
                "sum_mC",
                "sum_uC",
                "sum_mC2",
                "sum_uC2",
                "Sx3",
                "Sx4",
                "count_zero",
                "count_one",
            ])

        for attr in grow_attrs:
            old = getattr(self, attr)
            new = self.xp.zeros(new_cap, dtype=old.dtype)
            new[: self.size] = old[: self.size]
            setattr(self, attr, new)

        self.capacity = new_cap

    def add_sample(self, sample_path: Union[str, Path]):
        """Add one sample from disk — memory-safe streaming"""
        from methyl_utils.core.methyl_frame import MethylSample  # lazy import

        # Load sample - load_from_h5 returns the appropriate type directly
        loaded = load_from_h5(sample_path)
        # If it's already a MethylSample, use it directly; otherwise convert if needed
        if isinstance(loaded, MethylSample):
            sample = loaded
        else:
            # If it's a centroid, we can't use it directly - this shouldn't happen
            raise ValueError(f"Expected MethylSample, got {type(loaded)}")
        try:
            if len(sample) == 0:
                return

            pos = sample.pos.values.astype(np.uint32)
            mC = sample.mC.values.astype(np.uint64)
            uC = sample.uC.values.astype(np.uint64)
            # Access tnc from DataFrame directly
            tnc = sample._df["tnc"].values.astype(np.uint8)

            # Move to GPU if needed
            if self.use_gpu:
                pos = self.xp.asarray(pos)
                mC = self.xp.asarray(mC)
                uC = self.xp.asarray(uC)
                tnc = self.xp.asarray(tnc)

            # Find insertion points
            idx = self.xp.searchsorted(self.pos[: self.size], pos)

            # Detect new positions
            is_new = (idx == self.size) | (self.pos[idx] != pos)
            n_new = int(is_new.sum())

            if n_new > 0:
                needed = self.size + n_new
                if needed > self.capacity:
                    self._grow(needed)

                # Insert new positions in order
                new_pos = pos[is_new]
                self.pos[self.size : self.size + n_new] = new_pos
                self.tnc[self.size : self.size + n_new] = tnc[is_new]
                self.size += n_new

            # Final indices after insertion
            final_idx = self.xp.searchsorted(self.pos[: self.size], pos)

            # Update accumulators
            total_cov = mC + uC
            # Use xp.where instead of xp.divide with where parameter for CuPy compatibility
            # xp is either cp (CuPy) or np (NumPy), both support where()
            mean = self.xp.where(
                total_cov > 0,
                mC.astype(self.xp.float64) / total_cov.astype(self.xp.float64),
                self.xp.float64(0.0)
            ).astype(self.xp.float32)

            self.mC_sum[final_idx] += mC
            self.uC_sum[final_idx] += uC
            self.N[final_idx] += 1
            self.Sx[final_idx] += mean
            self.Sx2[final_idx] += mean**2

            if self.store_extended_stats:
                cov = total_cov.astype(self.xp.uint64)
                self.sum_cov[final_idx] += cov
                self.sum_cov2[final_idx] += cov.astype(self.xp.float64) ** 2
                self.sum_mC[final_idx] += mC.astype(self.xp.uint64)
                self.sum_uC[final_idx] += uC.astype(self.xp.uint64)
                self.sum_mC2[final_idx] += mC.astype(self.xp.float64) ** 2
                self.sum_uC2[final_idx] += uC.astype(self.xp.float64) ** 2
                self.Sx3[final_idx] += mean.astype(self.xp.float32) ** 3
                self.Sx4[final_idx] += mean.astype(self.xp.float32) ** 4
                zero_mask = (mC == 0) & (total_cov > 0)
                one_mask = (uC == 0) & (total_cov > 0)
                self.count_zero[final_idx] += zero_mask.astype(self.xp.uint32)
                self.count_one[final_idx] += one_mask.astype(self.xp.uint32)

            # Clip for log calculations - ensure we never get exactly 0 or 1
            # Use tighter bounds to avoid log(0) warnings
            eps = np.finfo(np.float32).eps * 10  # ~1e-6 for float32
            safe_mean = self.xp.clip(mean, eps, 1.0 - eps)
            # Ensure 1 - safe_mean is also >= eps to avoid log(0)
            one_minus_mean = self.xp.clip(1.0 - safe_mean, eps, 1.0 - eps)
            with np.errstate(divide='ignore', invalid='ignore'):
                self.log_x_sum[final_idx] += self.xp.log(safe_mean)
                self.log_1x_sum[final_idx] += self.xp.log(one_minus_mean)

            self.samples_processed += 1
            if self.samples_processed % 50 == 0:
                logger.info(
                    f"Processed {self.samples_processed} samples → {self.size:,} unique positions"
                )
        finally:
            try:
                sample.close()
            except Exception as e:
                logger.debug(f"Sample cleanup failed: {e}")

    def finalize(self) -> MethylExtendedCentroid:
        """Return final clean MethylExtendedCentroid"""
        if self.size == 0:
            raise ValueError("No data accumulated")

        # Move to CPU
        to_cpu = cp.asnumpy if self.use_gpu else lambda x: x

        pos = to_cpu(self.pos[: self.size])
        mC_sum = to_cpu(self.mC_sum[: self.size])
        uC_sum = to_cpu(self.uC_sum[: self.size])
        N = to_cpu(self.N[: self.size])
        Sx = to_cpu(self.Sx[: self.size])
        Sx2 = to_cpu(self.Sx2[: self.size])
        log_x = to_cpu(self.log_x_sum[: self.size])
        log_1x = to_cpu(self.log_1x_sum[: self.size])
        tnc = to_cpu(self.tnc[: self.size])
        if self.store_extended_stats:
            sum_cov = to_cpu(self.sum_cov[: self.size])
            sum_cov2 = to_cpu(self.sum_cov2[: self.size])
            sum_mC = to_cpu(self.sum_mC[: self.size])
            sum_uC = to_cpu(self.sum_uC[: self.size])
            sum_mC2 = to_cpu(self.sum_mC2[: self.size])
            sum_uC2 = to_cpu(self.sum_uC2[: self.size])
            Sx3 = to_cpu(self.Sx3[: self.size])
            Sx4 = to_cpu(self.Sx4[: self.size])
            count_zero = to_cpu(self.count_zero[: self.size])
            count_one = to_cpu(self.count_one[: self.size])

        # Apply coverage filter
        coverage = mC_sum + uC_sum
        mask = coverage >= self.min_coverage

        # Averaged counts for basic centroid compatibility
        avg_mC = (mC_sum[mask] / N[mask]).astype(np.uint32)
        avg_uC = (uC_sum[mask] / N[mask]).astype(np.uint32)

        df = pd.DataFrame(
            {
                "pos": pos[mask].astype(np.uint32),
                "mC": avg_mC,
                "uC": avg_uC,
                "tnc": tnc[mask],
                "N": N[mask].astype(np.uint32),
                "Sx": Sx[mask],
                "Sx2": Sx2[mask],
                "log_x_sum": log_x[mask],
                "log_1_minus_x_sum": log_1x[mask],
            }
        ).reset_index(drop=True)

        if self.store_extended_stats:
            df["sum_cov"] = sum_cov[mask].astype(np.uint64)
            df["sum_cov2"] = sum_cov2[mask].astype(np.float64)
            df["sum_mC"] = sum_mC[mask].astype(np.uint64)
            df["sum_uC"] = sum_uC[mask].astype(np.uint64)
            df["sum_mC2"] = sum_mC2[mask].astype(np.float64)
            df["sum_uC2"] = sum_uC2[mask].astype(np.float64)
            df["Sx3"] = Sx3[mask].astype(np.float32)
            df["Sx4"] = Sx4[mask].astype(np.float32)
            df["count_zero"] = count_zero[mask].astype(np.uint32)
            df["count_one"] = count_one[mask].astype(np.uint32)

        final_metadata = {
            **self.metadata,
            "builder": "MethylCentroidBuilder",
            "n_samples": self.samples_processed,
            "unique_positions_raw": int(self.size),
            "positions_after_filter": len(df),
            "min_coverage": self.min_coverage,
            "gpu_acceleration": self.use_gpu,
            "extended_stats": self.store_extended_stats,
        }

        logger.info(f"Centroid finalized → {len(df):,} positions from {self.samples_processed} samples")
        return MethylExtendedCentroid(df, final_metadata)


# Convenience factory
def build_centroid(
    sample_paths: List[Union[str, Path]],
    min_coverage: int = 4,
    use_gpu: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
    store_extended_stats: bool = True,
) -> MethylExtendedCentroid:
    builder = MethylCentroidBuilder(
        min_coverage=min_coverage, 
        use_gpu=use_gpu, 
        metadata=metadata,
        store_extended_stats=store_extended_stats,
    )
    for path in sample_paths:
        builder.add_sample(path)
    return builder.finalize()
