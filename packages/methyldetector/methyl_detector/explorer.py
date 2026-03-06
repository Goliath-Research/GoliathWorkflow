"""
MethylDetectorExplorer: Analyze and optimize DMP detection using a two-phase effect size strategy.

Phase 1: Compute approximate bounded_effect_size (sigmoid-like [0,1]) for a sample of positions
using delta_mean, variances, and rough overlap from discrete bin counts. Sort descending.

Phase 2: Use decay analysis to choose K positions; compute refined bounded_effect_size via
ECDF (Pchip) overlap only for those top K positions to avoid CPU-bound work on full chromosome.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import spearmanr

logger = logging.getLogger(__name__)

# MethylUtils imports
try:
    from methyl_utils import MethylCentroidPair
    from methyl_utils.statistical_tests import (
        discrete_overlap_from_bin_counts,
        welch_d_fast_overlap_approx,
        welch_d_ks_overlap,
    )
    from methyl_utils.core.distribution_views import ECDFView
except ImportError as e:
    raise ImportError(
        "MethylDetectorExplorer requires methyl_utils (MethylUtils). "
        "Install it from the monorepo (e.g. packages/methylutils)."
    ) from e


K_HEURISTIC = Literal["decay_limit", "knee", "threshold", "fraction", "fixed"]
APPROX_OVERLAP = Literal["auto", "discrete", "normal"]


def _require_binned_stats(centroid: Any) -> None:
    """Raise if centroid lacks binned_stats (required in pipeline)."""
    binned = getattr(centroid, "binned_stats", None)
    if not binned or "bin_edges" not in binned or "bin_counts" not in binned:
        raise ValueError(
            "Centroids must have binned_stats (bin_edges, bin_counts) for MethylDetectorExplorer. "
            "Build centroids with binned_stats_bins (e.g. 20)."
        )


def _same_bin_edges(centroid1: Any, centroid2: Any) -> bool:
    """True if both centroids have binned_stats with identical bin_edges (shape and values)."""
    bs1 = getattr(centroid1, "binned_stats", None)
    bs2 = getattr(centroid2, "binned_stats", None)
    if not bs1 or "bin_edges" not in bs1 or not bs2 or "bin_edges" not in bs2:
        return False
    e1 = np.asarray(bs1["bin_edges"], dtype=np.float64)
    e2 = np.asarray(bs2["bin_edges"], dtype=np.float64)
    return e1.shape == e2.shape and bool(np.allclose(e1, e2))


def _to_arr(x: Any) -> np.ndarray:
    """Convert column/property to 1d numpy array."""
    if hasattr(x, "values"):
        return np.asarray(x.values, dtype=np.float64).ravel()
    return np.asarray(x, dtype=np.float64).ravel()


def _min_n_filter_indices(
    n1: np.ndarray,
    n2: np.ndarray,
    min_N: Optional[int],
    min_N_pct: float,
) -> np.ndarray:
    """
    Return indices of positions that pass the minimum-N filter (for centroid comparison).
    If min_N is set: keep where n1 >= min_N and n2 >= min_N.
    Else: keep where min(n1,n2) >= min_N_pct * max(n1,n2), and max(n1,n2) > 0.
    """
    n1 = np.asarray(n1, dtype=np.float64).ravel()
    n2 = np.asarray(n2, dtype=np.float64).ravel()
    if min_N is not None:
        keep = (n1 >= min_N) & (n2 >= min_N)
    else:
        max_n = np.maximum(n1, n2)
        min_n = np.minimum(n1, n2)
        keep = (max_n > 0) & (min_n >= min_N_pct * max_n)
    return np.where(keep)[0].astype(np.intp)


def _extract_phase1_data(
    centroid1: Any,
    centroid2: Any,
    indices: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Extract delta_mean, var1, var2, n1, n2, bc1, bc2, mean1, mean2 for given indices. All arrays same length as indices."""
    n1 = _to_arr(centroid1.N)[indices]
    n2 = _to_arr(centroid2.N)[indices]
    mean1 = _to_arr(centroid1.mean)[indices]
    mean2 = _to_arr(centroid2.mean)[indices]
    var1 = _to_arr(centroid1.variance)[indices]
    var2 = _to_arr(centroid2.variance)[indices]
    delta_mean = mean1 - mean2

    bs1 = centroid1.binned_stats
    bs2 = centroid2.binned_stats
    bc1 = np.asarray(bs1["bin_counts"], dtype=np.float64)[indices]
    bc2 = np.asarray(bs2["bin_counts"], dtype=np.float64)[indices]

    return delta_mean, var1, var2, n1, n2, bc1, bc2, indices, mean1, mean2


def _choose_k(
    effect_sizes: np.ndarray,
    heuristic: K_HEURISTIC,
    refine_top_k: Optional[int] = None,
    max_decay_per_position: float = 0.01,
    threshold_fraction: float = 0.1,
    fraction_top: float = 0.01,
) -> Tuple[int, Dict[str, Any]]:
    """
    Choose K = number of positions to refine from sorted (descending) effect_sizes.
    effect_sizes[0] is the largest.
    """
    n = len(effect_sizes)
    if n == 0:
        return 0, {"heuristic": heuristic, "reason": "no_positions"}

    if heuristic == "fixed" and refine_top_k is not None:
        k = min(max(0, int(refine_top_k)), n)
        return k, {"heuristic": "fixed", "refine_top_k": refine_top_k, "k": k}

    max_eff = float(np.nanmax(effect_sizes))
    if max_eff <= 0:
        return 0, {"heuristic": heuristic, "reason": "max_effect_size_zero"}

    if heuristic == "decay_limit":
        # K = last rank before decay rate exceeds max_decay_per_position
        diff = np.diff(effect_sizes.astype(np.float64))
        # diff[i] = effect_sizes[i] - effect_sizes[i+1]; negative means drop
        decay = np.abs(diff)
        over = np.where(decay > max_decay_per_position)[0]
        k = int(over[0] + 1) if len(over) > 0 else n
        k = min(k, n)
        return k, {"heuristic": "decay_limit", "max_decay_per_position": max_decay_per_position, "k": k}

    if heuristic == "knee":
        # Simple elbow: max curvature or first point where second derivative is large
        x = np.arange(n, dtype=np.float64)
        y = np.asarray(effect_sizes, dtype=np.float64)
        if len(y) < 3:
            k = n
            return k, {"heuristic": "knee", "k": k}
        d1 = np.gradient(y, x)
        d2 = np.gradient(d1, x)
        # Knee: where curvature is high (absolute second derivative)
        curvature = np.abs(d2)
        # Take first index where curvature is above median of top half
        top_half = curvature[: max(1, n // 2)]
        thresh = np.median(top_half) if len(top_half) > 0 else 0
        candidates = np.where(curvature >= thresh * 1.5)[0]
        k = int(candidates[0]) if len(candidates) > 0 else min(n, max(1, n // 10))
        k = min(max(1, k), n)
        return k, {"heuristic": "knee", "k": k}

    if heuristic == "threshold":
        # K = number of positions with effect_size >= threshold_fraction * max
        thresh = max_eff * threshold_fraction
        k = int(np.sum(effect_sizes >= thresh))
        k = min(max(1, k), n)
        return k, {"heuristic": "threshold", "threshold_fraction": threshold_fraction, "k": k}

    if heuristic == "fraction":
        k = min(max(1, int(n * fraction_top)), n)
        return k, {"heuristic": "fraction", "fraction_top": fraction_top, "k": k}

    # default: refine top 10% or 1000, whichever is smaller
    k = min(max(1, int(n * 0.1)), 1000, n)
    return k, {"heuristic": "default", "k": k}


class MethylDetectorExplorer:
    """
    Two-phase DMP effect size analysis: approximate ranking then ECDF refinement for top K.
    """

    def __init__(
        self,
        centroid1_path: Union[str, Path],
        centroid2_path: Union[str, Path],
        min_coverage: int = 4,
        min_N: Optional[int] = None,
        min_N_pct: float = 0.05,
        approx_overlap: APPROX_OVERLAP = "auto",
        sample_fraction: float = 0.01,
        sigmoid_scale: float = 3.0,
        calibrate_scale: bool = False,
        k_heuristic: K_HEURISTIC = "decay_limit",
        refine_top_k: Optional[int] = None,
        max_decay_per_position: float = 0.01,
        threshold_fraction: float = 0.1,
        fraction_top: float = 0.01,
    ):
        self.centroid1_path = Path(centroid1_path)
        self.centroid2_path = Path(centroid2_path)
        self.min_coverage = min_coverage
        self.min_N = min_N
        self.min_N_pct = float(min_N_pct)
        self.approx_overlap = approx_overlap
        self.sample_fraction = float(sample_fraction)
        self.sigmoid_scale = sigmoid_scale
        self.calibrate_scale = calibrate_scale
        self.k_heuristic = k_heuristic
        self.refine_top_k = refine_top_k
        self.max_decay_per_position = max_decay_per_position
        self.threshold_fraction = threshold_fraction
        self.fraction_top = fraction_top

        self._centroid1: Optional[Any] = None
        self._centroid2: Optional[Any] = None
        self._common_positions: Optional[np.ndarray] = None
        self._phase1_indices: Optional[np.ndarray] = None  # indices into common_positions for Phase 1
        self._df_phase1: Optional[pd.DataFrame] = None
        self._k: Optional[int] = None
        self._report: Optional[Dict[str, Any]] = None

    def run(self) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Run two-phase analysis. Returns (result DataFrame, report dict)."""
        t0 = time.perf_counter()
        centroid1, centroid2, common_pos = MethylCentroidPair.load_and_align(
            str(self.centroid1_path),
            str(self.centroid2_path),
            min_coverage=self.min_coverage,
        )
        _require_binned_stats(centroid1)
        _require_binned_stats(centroid2)
        n_total = len(common_pos)

        # Min-N filter: keep only positions with sufficient N in both centroids (before delta_mean / Phase 1)
        n1_all = _to_arr(centroid1.N)
        n2_all = _to_arr(centroid2.N)
        indices_after_N_filter = _min_n_filter_indices(
            n1_all, n2_all, self.min_N, self.min_N_pct
        )
        n_after_filter = len(indices_after_N_filter)

        # Optionally subsample for Phase 1 (from N-filtered pool only)
        if self.sample_fraction < 1.0 and n_after_filter > 0:
            n_sample = max(1, int(n_after_filter * self.sample_fraction))
            rng = np.random.default_rng(42)
            phase1_local = rng.choice(
                n_after_filter, size=min(n_sample, n_after_filter), replace=False
            )
            phase1_local = np.sort(phase1_local)
            phase1_indices = indices_after_N_filter[phase1_local]
        else:
            phase1_indices = indices_after_N_filter

        self._centroid1 = centroid1
        self._centroid2 = centroid2
        self._common_positions = common_pos
        self._phase1_indices = phase1_indices

        # Phase 1: approximate bounded_effect_size
        delta_mean, var1, var2, n1, n2, bc1, bc2, _, mean1, mean2 = _extract_phase1_data(
            centroid1, centroid2, phase1_indices
        )
        # Overlap for approx: discrete Bhattacharyya only when bin_edges align; else Normal fallback
        use_discrete = self.approx_overlap == "discrete" or (
            self.approx_overlap == "auto" and _same_bin_edges(centroid1, centroid2)
        )
        if self.approx_overlap == "normal":
            overlap_approx = None
            approx_overlap_method = "normal"
        elif use_discrete:
            if self.approx_overlap == "discrete" and not _same_bin_edges(centroid1, centroid2):
                logger.warning(
                    "approx_overlap='discrete' but centroid bin_edges differ; "
                    "discrete overlap may be misleading. Prefer same binned_stats_bins or use --approx-overlap normal."
                )
            overlap_approx = discrete_overlap_from_bin_counts(bc1, bc2, method="bhattacharyya")
            approx_overlap_method = "discrete_bhattacharyya"
        else:
            if self.approx_overlap == "auto":
                logger.warning(
                    "Centroid bin_edges differ; using Normal-based overlap for Phase 1 "
                    "(discrete overlap skipped). Build both centroids with the same binned_stats_bins for comparable approx vs exact."
                )
            overlap_approx = None
            approx_overlap_method = "normal"
        result_fast = welch_d_fast_overlap_approx(
            delta_mean, var1, n1, var2, n2,
            scale=self.sigmoid_scale,
            overlap_approx=overlap_approx,
        )
        positions_phase1 = common_pos[phase1_indices]
        df = pd.DataFrame({
            "position": positions_phase1,
            "mean1": mean1,
            "mean2": mean2,
            "delta_mean": delta_mean,
            "variance1": var1,
            "variance2": var2,
            "n1": n1,
            "n2": n2,
            "overlap_approx": result_fast["overlap_approx"],
            "bounded_effect_size_approx": result_fast["bounded_effect_size_approx"],
            "welch_d": result_fast["welch_d"],
        })
        df = df.sort_values("bounded_effect_size_approx", ascending=False).reset_index(drop=True)
        t1 = time.perf_counter()

        # Choose K
        k, k_info = _choose_k(
            df["bounded_effect_size_approx"].values,
            heuristic=self.k_heuristic,
            refine_top_k=self.refine_top_k,
            max_decay_per_position=self.max_decay_per_position,
            threshold_fraction=self.threshold_fraction,
            fraction_top=self.fraction_top,
        )
        self._k = k
        k_info["k"] = k

        # Phase 2: refine top K with ECDF
        df["bounded_effect_size"] = df["bounded_effect_size_approx"]
        df["overlap"] = df["overlap_approx"]
        df["ks_d"] = np.nan
        df["ks_p"] = np.nan
        scale_used = self.sigmoid_scale
        effect_size_vs_ks_p_correlation: Optional[float] = None
        if k > 0:
            top_k_indices_in_phase1 = np.arange(k)
            positions_top_k = df.loc[top_k_indices_in_phase1, "position"].values
            # Map position -> index in common_pos (common_pos is sorted)
            pos_to_idx = {int(p): i for i, p in enumerate(common_pos)}
            idx_in_common = np.array([pos_to_idx[int(p)] for p in positions_top_k], dtype=np.intp)

            bin_edges = np.asarray(centroid1.binned_stats["bin_edges"], dtype=np.float64)
            bc1_k = np.asarray(centroid1.binned_stats["bin_counts"], dtype=np.float64)[idx_in_common]
            bc2_k = np.asarray(centroid2.binned_stats["bin_counts"], dtype=np.float64)[idx_in_common]
            c1_Sx = _to_arr(centroid1.Sx)[idx_in_common]
            c2_Sx = _to_arr(centroid2.Sx)[idx_in_common]
            N1 = _to_arr(centroid1.N)[idx_in_common]
            N2 = _to_arr(centroid2.N)[idx_in_common]
            c1_Sx2 = _to_arr(centroid1.Sx2)[idx_in_common]
            c2_Sx2 = _to_arr(centroid2.Sx2)[idx_in_common]

            view1 = ECDFView(bin_edges, bc1_k, c1_Sx, N1, c1_Sx2)
            view2 = ECDFView(bin_edges, bc2_k, c2_Sx, N2, c2_Sx2)
            var1_k = view1.variance
            var2_k = view2.variance
            dm_k = view1.mean - view2.mean
            pos_indices = np.arange(k, dtype=np.intp)
            res = welch_d_ks_overlap(
                dm_k, var1_k, N1, var2_k, N2,
                ecdf_view1=view1, ecdf_view2=view2, position_indices=pos_indices,
                scale=self.sigmoid_scale, grid_size=256,
            )
            refined_bes = res["bounded_effect_size"]
            refined_overlap = 1.0 - res["ks_d"]
            ks_d_arr = res["ks_d"]
            ks_p_arr = res["ks_p"]
            for i, idx_df in enumerate(top_k_indices_in_phase1):
                if i < len(refined_bes):
                    df.loc[idx_df, "bounded_effect_size"] = refined_bes[i]
                    df.loc[idx_df, "overlap"] = refined_overlap[i]
                if i < len(ks_d_arr):
                    df.loc[idx_df, "ks_d"] = ks_d_arr[i]
                if i < len(ks_p_arr):
                    df.loc[idx_df, "ks_p"] = ks_p_arr[i]

            # Optional: calibrate scale to maximize correlation between effect_size and (1 - ks_p)
            if self.calibrate_scale:
                sub = df.iloc[:k]
                n1_k = np.asarray(sub["n1"].values, dtype=np.float64)
                n2_k = np.asarray(sub["n2"].values, dtype=np.float64)
                n_eff = 2.0 / (1.0 / np.maximum(n1_k, 1) + 1.0 / np.maximum(n2_k, 1))
                T = np.minimum(np.sqrt(n_eff) * np.asarray(sub["ks_d"].values, dtype=np.float64), 15.0)
                welch_d_k = np.asarray(sub["welch_d"].values, dtype=np.float64)
                one_minus_p = 1.0 - np.asarray(sub["ks_p"].values, dtype=np.float64)
                scales = np.arange(0.5, 12.5, 0.5)
                best_scale = float(self.sigmoid_scale)
                best_corr = -np.inf
                for s in scales:
                    bes = np.clip(2.0 * expit(s * welch_d_k * T) - 1.0, 0.0, 1.0)
                    r, _ = spearmanr(bes, one_minus_p)
                    if np.isfinite(r) and r > best_corr:
                        best_corr = float(r)
                        best_scale = float(s)
                scale_used = best_scale
                effect_size_vs_ks_p_correlation = best_corr
                # Recompute bounded_effect_size for refined rows with chosen scale
                bes_calibrated = np.clip(2.0 * expit(best_scale * welch_d_k * T) - 1.0, 0.0, 1.0)
                for i, idx_df in enumerate(top_k_indices_in_phase1):
                    if i < len(bes_calibrated):
                        df.loc[idx_df, "bounded_effect_size"] = bes_calibrated[i]
                logger.info(
                    "Calibrated sigmoid_scale=%.2f (Spearman effect_size vs (1-ks_p)=%.4f)",
                    scale_used,
                    effect_size_vs_ks_p_correlation,
                )

        t2 = time.perf_counter()
        self._df_phase1 = df
        self._report = {
            "total_positions": int(n_total),
            "positions_after_min_N_filter": int(n_after_filter),
            "phase1_sample_size": int(len(phase1_indices)),
            "sample_fraction": self.sample_fraction,
            "approx_overlap_method": approx_overlap_method,
            "sigmoid_scale_used": scale_used,
            "k_chosen": int(k),
            "k_heuristic": self.k_heuristic,
            "k_info": k_info,
            "time_phase1_s": t1 - t0,
            "time_phase2_s": t2 - t1,
            "time_total_s": t2 - t0,
        }
        if effect_size_vs_ks_p_correlation is not None:
            self._report["effect_size_vs_ks_p_correlation"] = effect_size_vs_ks_p_correlation
        return df, self._report

    @property
    def report(self) -> Optional[Dict[str, Any]]:
        return self._report

    @property
    def result_df(self) -> Optional[pd.DataFrame]:
        return self._df_phase1

