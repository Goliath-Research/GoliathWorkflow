# methyl_utils/comparison.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple, Optional

import numpy as np
import pandas as pd

# GPU support (transparent)
try:
    import cupy as cp
    import cudf
    HAS_GPU = True
except ImportError:
    cp = np
    cudf = None
    HAS_GPU = False

from .core.methyl_frame import MethylExtendedCentroid
from .statistical_tests import (
    likelihood_ratio_test_beta,
    compute_bhattacharyya_distance,
)
from statsmodels.stats.multitest import multipletests

logger = logging.getLogger(__name__)


class MethylCentroidPair:
    """
    Ultra-clean, GPU-native comparator for two extended centroids.
    Returns a ready-to-use pandas DataFrame with everything MethylDetector needs.
    """

    def __init__(self, min_coverage: int = 4):
        self.min_coverage = min_coverage

    @staticmethod
    def align_centroids(
        c1: MethylExtendedCentroid,
        c2: MethylExtendedCentroid,
    ) -> Tuple[MethylExtendedCentroid, MethylExtendedCentroid]:
        """Find common positions and return aligned views (zero-copy when possible)."""
        common_pos = np.intersect1d(c1.pos.values, c2.pos.values, assume_unique=True)

        if len(common_pos) == 0:
            raise ValueError("No overlapping positions between the two centroids")

        # Fast searchsorted indexing
        idx1 = np.searchsorted(c1.pos.values, common_pos)
        idx2 = np.searchsorted(c2.pos.values, common_pos)

        # Zero-copy slicing using .df.loc (pandas/cuDF both support it)
        aligned1 = c1[idx1]
        aligned2 = c2[idx2]

        # Clamp zero-coverage positions (prevents NaN in LRT)
        for cent in (aligned1, aligned2):
            zero_cov = cent.coverage == 0
            if zero_cov.any():
                cent._df.loc[zero_cov, "uC"] = 1  # force mean = 0

        logger.info(f"Aligned on {len(common_pos):,} common positions")
        return aligned1, aligned2

    def compare(
        self,
        healthy: MethylExtendedCentroid,
        diseased: MethylExtendedCentroid,
        fdr: float = 0.05,
    ) -> pd.DataFrame:
        """
        One-liner API used by your disease detection pipeline.
        """
        # 1. Align
        h, d = self.align_centroids(healthy, diseased)

        # 2. Likelihood-ratio test (centroid API; uses N, Sx, Sx2 / MoM internally)
        use_gpu = bool(h.is_gpu and d.is_gpu and HAS_GPU)
        _, p_values = likelihood_ratio_test_beta(h, d, use_gpu=use_gpu)
        p_values = np.asarray(p_values).ravel()

        # 3. Beta parameters from centroids (MoM from N, Sx, Sx2)
        alpha1 = np.asarray(h.alpha).ravel()
        beta1 = np.asarray(h.beta).ravel()
        alpha2 = np.asarray(d.alpha).ravel()
        beta2 = np.asarray(d.beta).ravel()
        N1 = np.asarray(h.N).ravel()
        N2 = np.asarray(d.N).ravel()

        mean1 = alpha1 / (alpha1 + beta1 + 1e-12)
        mean2 = alpha2 / (alpha2 + beta2 + 1e-12)

        # 6. Bhattacharyya distance (GPU kernel)
        bd = compute_bhattacharyya_distance(
            alpha1, beta1, alpha2, beta2, use_gpu=(xp == cp)
        )
        bd = np.minimum(bd, 20.0)  # cap for BC = exp(-BD)

        # 7. FDR (Storey's method via statsmodels)
        q_values = multipletests(p_values, alpha=fdr, method="fdr_bh")[1]

        # 8. Final DataFrame (pure pandas – perfect for downstream ML)
        results = pd.DataFrame({
            "position": h.pos.values,
            "p_value": p_values.astype(np.float32),
            "q_value": q_values.astype(np.float32),
            "alpha_healthy": alpha1.astype(np.float64),
            "beta_healthy": beta1.astype(np.float64),
            "alpha_diseased": alpha2.astype(np.float64),
            "beta_diseased": beta2.astype(np.float64),
            "mean_healthy": mean1.astype(np.float32),
            "mean_diseased": mean2.astype(np.float32),
            "delta_mean": (mean2 - mean1).astype(np.float32),
            "bhattacharyya_distance": bd.astype(np.float32),
            "N_healthy": N1.astype(np.uint32),
            "N_diseased": N2.astype(np.uint32),
        })

        # Optional: biological importance (used by your classifier)
        bc = np.exp(-results["bhattacharyya_distance"])
        results["biological_importance"] = (
            np.abs(results["delta_mean"]) / (bc + 1e-8)
        ).astype(np.float32)

        results = results.sort_values("biological_importance", ascending=False).reset_index(drop=True)

        logger.info(f"DMP detection complete → {results['q_value'].le(fdr).sum():,} significant positions at FDR ≤ {fdr}")
        return results