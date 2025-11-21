# methyl_utils/core/centroid_builder.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, Union, List

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
    ):
        self.min_coverage = min_coverage
        self.use_gpu = use_gpu and HAS_GPU
        self.xp = cp if self.use_gpu else np
        self.metadata = metadata or {}

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
        self.tnc_byte: CuArray = self.xp.zeros(chunk_size, dtype=np.uint8)

        self.size = 0
        self.capacity = chunk_size
        self.samples_processed = 0

    def _grow(self, min_needed: int):
        new_cap = max(min_needed, int(self.capacity * 1.6))
        logger.debug(f"Growing accumulators: {self.capacity:,} → {new_cap:,} positions")

        for attr in ["pos", "mC_sum", "uC_sum", "N", "Sx", "Sx2", "log_x_sum", "log_1x_sum", "tnc_byte"]:
            old = getattr(self, attr)
            new = self.xp.zeros(new_cap, dtype=old.dtype)
            new[:self.size] = old[:self.size]
            setattr(self, attr, new)

        self.capacity = new_cap

    def add_sample(self, sample_path: Union[str, Path]):
        """Add one sample from disk — memory-safe streaming"""
        from methyl_utils.core.methyl_frame import MethylSample  # lazy import

        sample = load_from_h5(sample_path).as_sample()
        if len(sample) == 0:
            return

        pos = sample.pos.values.astype(np.uint32)
        mC = sample.mC.values.astype(np.uint64)
        uC = sample.uC.values.astype(np.uint64)
        tnc = sample.tnc_byte.values.astype(np.uint8)

        # Move to GPU if needed
        if self.use_gpu:
            pos = self.xp.asarray(pos)
            mC = self.xp.asarray(mC)
            uC = self.xp.asarray(uC)
            tnc = self.xp.asarray(tnc)

        # Find insertion points
        idx = self.xp.searchsorted(self.pos[:self.size], pos)

        # Detect new positions
        is_new = (idx == self.size) | (self.pos[idx] != pos)
        n_new = int(is_new.sum())

        if n_new > 0:
            needed = self.size + n_new
            if needed > self.capacity:
                self._grow(needed)

            # Insert new positions in order
            new_pos = pos[is_new]
            insert_at = idx[is_new] + self.xp.arange(n_new)
            self.pos[self.size:self.size + n_new] = new_pos
            self.tnc_byte[self.size:self.size + n_new] = tnc[is_new]
            self.size += n_new

        # Final indices after insertion
        final_idx = self.xp.searchsorted(self.pos[:self.size], pos)

        # Update accumulators
        total_cov = mC + uC
        mean = self.xp.divide(mC, total_cov.astype(np.float64), where=total_cov > 0).astype(np.float32)

        self.mC_sum[final_idx] += mC
        self.uC_sum[final_idx] += uC
        self.N[final_idx] += 1
        self.Sx[final_idx] += mean
        self.Sx2[final_idx] += mean ** 2

        safe_mean = self.xp.clip(mean, 1e-10, 1 - 1e-10)
        self.log_x_sum[final_idx] += self.xp.log(safe_mean)
        self.log_1x_sum[final_idx] += self.xp.log(1 - safe_mean)

        self.samples_processed += 1
        if self.samples_processed % 50 == 0:
            logger.info(f"Processed {self.samples_processed} samples → {self.size:,} unique positions")

    def finalize(self) -> MethylExtendedCentroid:
        """Return final clean MethylExtendedCentroid"""
        if self.size == 0:
            raise ValueError("No data accumulated")

        # Move to CPU
        to_cpu = cp.asnumpy if self.use_gpu else lambda x: x

        pos = to_cpu(self.pos[:self.size])
        mC_sum = to_cpu(self.mC_sum[:self.size])
        uC_sum = to_cpu(self.uC_sum[:self.size])
        N = to_cpu(self.N[:self.size])
        Sx = to_cpu(self.Sx[:self.size])
        Sx2 = to_cpu(self.Sx2[:self.size])
        log_x = to_cpu(self.log_x_sum[:self.size])
        log_1x = to_cpu(self.log_1x_sum[:self.size])
        tnc = to_cpu(self.tnc_byte[:self.size])

        # Apply coverage filter
        coverage = mC_sum + uC_sum
        mask = coverage >= self.min_coverage

        # Averaged counts for basic centroid compatibility
        avg_mC = (mC_sum[mask] / N[mask]).astype(np.uint32)
        avg_uC = (uC_sum[mask] / N[mask]).astype(np.uint32)

        df = pd.DataFrame({
            "pos": pos[mask].astype(np.uint32),
            "mC": avg_mC,
            "uC": avg_uC,
            "tnc_byte": tnc[mask],
            "N": N[mask].astype(np.uint32),
            "Sx": Sx[mask],
            "Sx2": Sx2[mask],
            "log_x_sum": log_x[mask],
            "log_1_minus_x_sum": log_1x[mask],
        }).reset_index(drop=True)

        final_metadata = {
            **self.metadata,
            "builder": "MethylCentroidBuilder",
            "n_samples": self.samples_processed,
            "unique_positions_raw": int(self.size),
            "positions_after_filter": len(df),
            "min_coverage": self.min_coverage,
            "gpu_acceleration": self.use_gpu,
        }

        logger.info(f"Centroid finalized → {len(df):,} positions from {self.samples_processed} samples")
        return MethylExtendedCentroid(df, final_metadata)


# Convenience factory
def build_centroid(
    sample_paths: List[Union[str, Path]],
    min_coverage: int = 4,
    use_gpu: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
) -> MethylExtendedCentroid:
    builder = MethylCentroidBuilder(min_coverage=min_coverage, use_gpu=use_gpu, metadata=metadata)
    for path in sample_paths:
        builder.add_sample(path)
    return builder.finalize()