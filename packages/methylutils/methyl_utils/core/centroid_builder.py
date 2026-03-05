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
from .io import load_from_h5

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
        chunk_size: int = 100_000_000,
        metadata: Optional[Dict[str, Any]] = None,
        binned_stats_bins: int = 101,
    ):
        self.min_coverage = min_coverage
        self.use_gpu = use_gpu and HAS_GPU
        self.xp = cp if self.use_gpu else np
        self.metadata = metadata or {}
        self.binned_stats_bins = binned_stats_bins
        self.bin_edges = np.linspace(0.0, 1.0, binned_stats_bins + 1, dtype=np.float64)

        logger.info(f"MethylCentroidBuilder initialized → GPU: {self.use_gpu}, binned_stats_bins={binned_stats_bins}")

        self.pos: CuArray = self.xp.zeros(chunk_size, dtype=np.uint32)
        self.mC_sum: CuArray = self.xp.zeros(chunk_size, dtype=np.uint64)
        self.uC_sum: CuArray = self.xp.zeros(chunk_size, dtype=np.uint64)
        self.N: CuArray = self.xp.zeros(chunk_size, dtype=np.uint32)
        self.Sx: CuArray = self.xp.zeros(chunk_size, dtype=np.float32)
        self.Sx2: CuArray = self.xp.zeros(chunk_size, dtype=np.float32)
        self.tnc: CuArray = self.xp.zeros(chunk_size, dtype=np.uint8)
        self.bin_counts: CuArray = self.xp.zeros((chunk_size, binned_stats_bins), dtype=np.uint32)

        self.size = 0
        self.capacity = chunk_size
        self.samples_processed = 0

    def release_gpu(self) -> None:
        """Release GPU array references so memory can be freed."""
        if not self.use_gpu or not HAS_GPU:
            return
        for attr in ["pos", "mC_sum", "uC_sum", "N", "Sx", "Sx2", "tnc", "bin_counts"]:
            if hasattr(self, attr):
                setattr(self, attr, None)
        logger.debug("MethylCentroidBuilder GPU arrays released")

    def _grow(self, min_needed: int):
        new_cap = max(min_needed, int(self.capacity * 1.6))
        logger.debug(f"Growing accumulators: {self.capacity:,} → {new_cap:,} positions")
        for attr in ["pos", "mC_sum", "uC_sum", "N", "Sx", "Sx2", "tnc"]:
            old = getattr(self, attr)
            new = self.xp.zeros(new_cap, dtype=old.dtype)
            new[: self.size] = old[: self.size]
            setattr(self, attr, new)
        old_bc = self.bin_counts
        new_bc = self.xp.zeros((new_cap, self.binned_stats_bins), dtype=old_bc.dtype)
        new_bc[: self.size, :] = old_bc[: self.size, :]
        self.bin_counts = new_bc
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

            # Find insertion points (searchsorted can return self.size when pos > max existing)
            idx = self.xp.searchsorted(self.pos[: self.size], pos)

            # Detect new positions: beyond current max (idx == size) or not found in place.
            # Do not index self.pos[idx] when idx == size (out of bounds).
            is_new = (idx == self.size)
            in_bounds = idx < self.size
            if self.xp.any(in_bounds):
                is_new = is_new.copy()
                is_new[in_bounds] = is_new[in_bounds] | (
                    self.pos[idx[in_bounds]] != pos[in_bounds]
                )
            n_new = int(is_new.sum())

            if n_new > 0:
                needed = self.size + n_new
                if needed > self.capacity:
                    self._grow(needed)

                # Efficiently merge new positions while maintaining sorted order
                new_pos = pos[is_new]
                new_tnc = tnc[is_new]

                # Get existing positions
                existing_pos = self.pos[: self.size]
                existing_tnc = self.tnc[: self.size]
                existing_mC_sum = self.mC_sum[: self.size]
                existing_uC_sum = self.uC_sum[: self.size]
                existing_N = self.N[: self.size]
                existing_Sx = self.Sx[: self.size]
                existing_Sx2 = self.Sx2[: self.size]
                existing_bin_counts = self.bin_counts[: self.size, :]
                all_pos = self.xp.concatenate([existing_pos, new_pos])
                sort_indices = self.xp.argsort(all_pos)
                n_all = len(all_pos)
                self.pos[: n_all] = all_pos[sort_indices]
                self.tnc[: n_all] = self.xp.concatenate([existing_tnc, new_tnc])[sort_indices]
                self.mC_sum[: n_all] = self.xp.concatenate([existing_mC_sum, self.xp.zeros(n_new, dtype=self.mC_sum.dtype)])[sort_indices]
                self.uC_sum[: n_all] = self.xp.concatenate([existing_uC_sum, self.xp.zeros(n_new, dtype=self.uC_sum.dtype)])[sort_indices]
                self.N[: n_all] = self.xp.concatenate([existing_N, self.xp.zeros(n_new, dtype=self.N.dtype)])[sort_indices]
                self.Sx[: n_all] = self.xp.concatenate([existing_Sx, self.xp.zeros(n_new, dtype=self.Sx.dtype)])[sort_indices]
                self.Sx2[: n_all] = self.xp.concatenate([existing_Sx2, self.xp.zeros(n_new, dtype=self.Sx2.dtype)])[sort_indices]
                new_bin_rows = self.xp.zeros((n_new, self.binned_stats_bins), dtype=self.bin_counts.dtype)
                self.bin_counts[: n_all, :] = self.xp.concatenate([existing_bin_counts, new_bin_rows])[sort_indices, :]
                self.size = n_all

            # Final indices after merge - positions are now properly sorted
            final_idx = self.xp.searchsorted(self.pos[: self.size], pos)
            # searchsorted can return self.size when pos > max(self.pos); skip those rows to avoid OOB
            valid = final_idx < self.size
            if not self.xp.all(valid):
                n_skip = int((~valid).sum())
                logger.warning(
                    "Builder: %d sample position(s) not in builder after merge (skipping)",
                    n_skip,
                )
                final_idx = final_idx[valid]
                mC = mC[valid]
                uC = uC[valid]

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
            self.Sx2[final_idx] += mean ** 2
            bin_edges_xp = self.xp.asarray(self.bin_edges)
            if self.binned_stats_bins > 1:
                bin_idx = self.xp.digitize(mean.astype(self.xp.float64), bin_edges_xp[1:-1])
                bin_idx = self.xp.clip(bin_idx, 0, self.binned_stats_bins - 1).astype(self.xp.intp)
            else:
                bin_idx = self.xp.zeros(len(mean), dtype=self.xp.intp)
            self.xp.add.at(self.bin_counts, (final_idx, bin_idx), 1)
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

    def finalize(self, log_finalize: bool = True) -> MethylExtendedCentroid:
        """Return MethylExtendedCentroid with pos, mC, uC, tnc, N, Sx, Sx2 and binned_stats."""
        if self.size == 0:
            raise ValueError("No data accumulated")
        to_cpu = cp.asnumpy if self.use_gpu else lambda x: x
        pos = to_cpu(self.pos[: self.size])
        mC_sum = to_cpu(self.mC_sum[: self.size])
        uC_sum = to_cpu(self.uC_sum[: self.size])
        N = to_cpu(self.N[: self.size])
        Sx = to_cpu(self.Sx[: self.size])
        Sx2 = to_cpu(self.Sx2[: self.size])
        tnc = to_cpu(self.tnc[: self.size])
        bin_counts = to_cpu(self.bin_counts[: self.size, :])
        coverage = mC_sum + uC_sum
        mask = coverage >= self.min_coverage
        avg_mC = (mC_sum[mask] / N[mask]).astype(np.uint32)
        avg_uC = (uC_sum[mask] / N[mask]).astype(np.uint32)
        df = pd.DataFrame({
            "pos": pos[mask].astype(np.uint32),
            "mC": avg_mC,
            "uC": avg_uC,
            "tnc": tnc[mask],
            "N": N[mask].astype(np.uint32),
            "Sx": Sx[mask].astype(np.float32),
            "Sx2": Sx2[mask].astype(np.float32),
        }).reset_index(drop=True)
        final_metadata = {
            **self.metadata,
            "builder": "MethylCentroidBuilder",
            "n_samples": self.samples_processed,
            "unique_positions_raw": int(self.size),
            "positions_after_filter": len(df),
            "min_coverage": self.min_coverage,
            "gpu_acceleration": self.use_gpu,
            "binned_stats_bins": self.binned_stats_bins,
        }
        centroid = MethylExtendedCentroid(df, final_metadata)
        centroid.set_binned_stats(self.bin_edges.copy(), bin_counts[mask, :].astype(np.float64))
        if log_finalize:
            logger.info(f"Centroid finalized → {len(df):,} positions from {self.samples_processed} samples")
        self.release_gpu()
        return centroid


# Convenience factory
def build_centroid(
    sample_paths: List[Union[str, Path]],
    min_coverage: int = 4,
    use_gpu: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
    binned_stats_bins: int = 101,
) -> MethylExtendedCentroid:
    builder = MethylCentroidBuilder(
        min_coverage=min_coverage,
        use_gpu=use_gpu,
        metadata=metadata,
        binned_stats_bins=binned_stats_bins,
    )
    for path in sample_paths:
        builder.add_sample(path)
    return builder.finalize()
