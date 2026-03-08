"""MethylDetectorExplorer: staged statistical and biological effect-size analysis."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
import pandas as pd
from scipy.stats import rankdata

logger = logging.getLogger(__name__)

try:
    from methyl_utils import MethylCentroidPair, storey_qvalues
    from methyl_utils.statistical_tests import (
        welch_mean_test,
        ecdf_overlap_integral,
        effect_size_from_components,
        optimize_lambda_var,
    )
    from methyl_utils.core.distribution_views import ECDFView
except ImportError as e:
    raise ImportError(
        "MethylDetectorExplorer requires methyl_utils (MethylUtils). "
        "Install it from the monorepo (e.g. packages/methylutils)."
    ) from e


def _require_binned_stats(centroid: Any) -> None:
    binned = getattr(centroid, "binned_stats", None)
    if not binned or "bin_edges" not in binned or "bin_counts" not in binned:
        raise ValueError(
            "Centroids must have binned_stats (bin_edges, bin_counts) for MethylDetectorExplorer. "
            "Build centroids with binned_stats_bins (e.g. 20)."
        )


def _to_arr(x: Any) -> np.ndarray:
    if hasattr(x, "values"):
        return np.asarray(x.values, dtype=np.float64).ravel()
    return np.asarray(x, dtype=np.float64).ravel()


def _min_n_filter_indices(
    n1: np.ndarray,
    n2: np.ndarray,
    min_N: Optional[int],
    min_N_pct: float,
) -> np.ndarray:
    n1 = np.asarray(n1, dtype=np.float64).ravel()
    n2 = np.asarray(n2, dtype=np.float64).ravel()
    if min_N is not None:
        keep = (n1 >= min_N) & (n2 >= min_N)
    else:
        max_n = np.maximum(n1, n2)
        min_n = np.minimum(n1, n2)
        keep = (max_n > 0) & (min_n >= min_N_pct * max_n)
    return np.where(keep)[0].astype(np.intp)


class MethylDetectorExplorer:
    """Analyze the staged detector pipeline with a single canonical effect_size."""

    def __init__(
        self,
        centroid1_path: Union[str, Path],
        centroid2_path: Union[str, Path],
        alpha: float = 0.05,
        min_coverage: int = 4,
        min_N: Optional[int] = None,
        min_N_pct: float = 0.05,
        delta_mean_reduction: Optional[float] = None,
        min_delta_mean: Optional[float] = None,
        max_overlap: Optional[float] = None,
        min_effect_size: Optional[float] = None,
        lambda_var: float = 2.0,
        optimize_lambda_var: bool = False,
        lambda_var_min: float = 0.0,
        lambda_var_max: float = 6.0,
        lambda_var_step: float = 0.25,
        ecdf_overlap_grid_size: int = 512,
    ):
        self.centroid1_path = Path(centroid1_path)
        self.centroid2_path = Path(centroid2_path)
        self.alpha = float(alpha)
        self.min_coverage = int(min_coverage)
        self.min_N = min_N
        self.min_N_pct = float(min_N_pct)
        self.delta_mean_reduction = delta_mean_reduction
        self.min_delta_mean = min_delta_mean
        self.max_overlap = max_overlap
        self.min_effect_size = min_effect_size
        self.lambda_var = float(lambda_var)
        self.optimize_lambda_var = bool(optimize_lambda_var)
        self.lambda_var_min = float(lambda_var_min)
        self.lambda_var_max = float(lambda_var_max)
        self.lambda_var_step = float(lambda_var_step)
        self.ecdf_overlap_grid_size = int(ecdf_overlap_grid_size)
        self._report: Optional[Dict[str, Any]] = None
        self._result_df: Optional[pd.DataFrame] = None

    def run(self) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        t0 = time.perf_counter()
        centroid1, centroid2, common_pos = MethylCentroidPair.load_and_align(
            str(self.centroid1_path),
            str(self.centroid2_path),
            min_coverage=self.min_coverage,
        )
        _require_binned_stats(centroid1)
        _require_binned_stats(centroid2)

        n1_all = _to_arr(centroid1.N)
        n2_all = _to_arr(centroid2.N)
        keep_idx = _min_n_filter_indices(n1_all, n2_all, self.min_N, self.min_N_pct)
        if len(keep_idx) == 0:
            self._result_df = pd.DataFrame()
            self._report = {
                "total_positions": int(len(common_pos)),
                "positions_after_min_N_filter": 0,
                "positions_after_statistical_filter": 0,
                "positions_after_delta_mean_reduction": 0,
                "positions_after_biological_filter": 0,
                "lambda_var_used": self.lambda_var,
                "time_total_s": time.perf_counter() - t0,
            }
            return self._result_df, self._report

        mean1 = _to_arr(centroid1.mean)[keep_idx]
        mean2 = _to_arr(centroid2.mean)[keep_idx]
        var1 = _to_arr(centroid1.variance)[keep_idx]
        var2 = _to_arr(centroid2.variance)[keep_idx]
        n1 = n1_all[keep_idx]
        n2 = n2_all[keep_idx]
        signed_delta = mean1 - mean2
        delta_mean = np.abs(signed_delta)

        welch = welch_mean_test(
            delta_mean=signed_delta,
            var1=var1,
            n1=n1,
            var2=var2,
            n2=n2,
        )
        q_values, _ = storey_qvalues(np.asarray(welch["p_value"], dtype=np.float64))
        df = pd.DataFrame(
            {
                "position": common_pos[keep_idx],
                "mean1": mean1,
                "mean2": mean2,
                "delta_mean": delta_mean,
                "variance1": var1,
                "variance2": var2,
                "n1": n1,
                "n2": n2,
                "p_value": np.asarray(welch["p_value"], dtype=np.float64),
                "q_value": np.asarray(q_values, dtype=np.float64),
            }
        )

        stat_df = df[df["q_value"] <= self.alpha].copy()
        delta_gate = self.delta_mean_reduction
        if delta_gate is None:
            delta_gate = self.min_delta_mean
        reduced_df = stat_df.copy()
        if delta_gate is not None and len(reduced_df) > 0:
            reduced_df = reduced_df[reduced_df["delta_mean"].astype(float) >= float(delta_gate)].copy()

        if len(reduced_df) > 0:
            pos_to_idx = {int(p): i for i, p in enumerate(common_pos)}
            idx_in_common = np.asarray([pos_to_idx[int(p)] for p in reduced_df["position"].values], dtype=np.intp)
            bin_edges = np.asarray(centroid1.binned_stats["bin_edges"], dtype=np.float64)
            bc1 = np.asarray(centroid1.binned_stats["bin_counts"], dtype=np.float64)[idx_in_common]
            bc2 = np.asarray(centroid2.binned_stats["bin_counts"], dtype=np.float64)[idx_in_common]
            sx1 = _to_arr(centroid1.Sx)[idx_in_common]
            sx2 = _to_arr(centroid2.Sx)[idx_in_common]
            sx2_1 = _to_arr(centroid1.Sx2)[idx_in_common]
            sx2_2 = _to_arr(centroid2.Sx2)[idx_in_common]
            N1 = _to_arr(centroid1.N)[idx_in_common]
            N2 = _to_arr(centroid2.N)[idx_in_common]
            view1 = ECDFView(bin_edges, bc1, sx1, N1, sx2_1)
            view2 = ECDFView(bin_edges, bc2, sx2, N2, sx2_2)
            overlap = ecdf_overlap_integral(
                view1,
                view2,
                np.arange(len(reduced_df), dtype=np.intp),
                grid_size=self.ecdf_overlap_grid_size,
            )
            lambda_used = self.lambda_var
            lambda_corr = None
            if self.optimize_lambda_var and len(reduced_df) > 1:
                lambda_values = np.arange(
                    self.lambda_var_min,
                    self.lambda_var_max + self.lambda_var_step * 0.5,
                    self.lambda_var_step,
                    dtype=np.float64,
                )
                optimized = optimize_lambda_var(
                    delta_mean=reduced_df["delta_mean"].values.astype(np.float64),
                    overlap=overlap,
                    var1=reduced_df["variance1"].values.astype(np.float64),
                    var2=reduced_df["variance2"].values.astype(np.float64),
                    target_scores=1.0 - reduced_df["q_value"].values.astype(np.float64),
                    lambda_values=lambda_values,
                )
                lambda_used = float(optimized["lambda_var"])
                lambda_corr = optimized["correlation"]
                effect_size = np.asarray(optimized["effect_size"], dtype=np.float64)
                reliability = effect_size_from_components(
                    delta_mean=reduced_df["delta_mean"].values.astype(np.float64),
                    overlap=overlap,
                    var1=reduced_df["variance1"].values.astype(np.float64),
                    var2=reduced_df["variance2"].values.astype(np.float64),
                    lambda_var=lambda_used,
                )["reliability"]
            else:
                effect = effect_size_from_components(
                    delta_mean=reduced_df["delta_mean"].values.astype(np.float64),
                    overlap=overlap,
                    var1=reduced_df["variance1"].values.astype(np.float64),
                    var2=reduced_df["variance2"].values.astype(np.float64),
                    lambda_var=lambda_used,
                )
                effect_size = effect["effect_size"]
                reliability = effect["reliability"]

            reduced_df["overlap"] = overlap.astype(np.float64)
            reduced_df["effect_size"] = effect_size.astype(np.float64)
            reduced_df["effect_size_reliability"] = np.asarray(reliability, dtype=np.float64)
            ranks = rankdata(reduced_df["effect_size"].values.astype(np.float64))
            reduced_df["effect_size_ecdf"] = (ranks - 0.5) / len(ranks)
        else:
            lambda_used = self.lambda_var
            lambda_corr = None
            reduced_df["overlap"] = np.nan
            reduced_df["effect_size"] = np.nan
            reduced_df["effect_size_reliability"] = np.nan
            reduced_df["effect_size_ecdf"] = np.nan

        bio_df = reduced_df.copy()
        if self.min_delta_mean is not None and len(bio_df) > 0:
            bio_df = bio_df[bio_df["delta_mean"].astype(float) >= float(self.min_delta_mean)].copy()
        if self.max_overlap is not None and len(bio_df) > 0:
            bio_df = bio_df[bio_df["overlap"].astype(float) <= float(self.max_overlap)].copy()
        if self.min_effect_size is not None and len(bio_df) > 0:
            bio_df = bio_df[bio_df["effect_size"].astype(float) >= float(self.min_effect_size)].copy()
        if "effect_size" in bio_df.columns and len(bio_df) > 0:
            bio_df = bio_df.sort_values("effect_size", ascending=False).reset_index(drop=True)

        report = {
            "total_positions": int(len(common_pos)),
            "positions_after_min_N_filter": int(len(df)),
            "positions_after_statistical_filter": int(len(stat_df)),
            "positions_after_delta_mean_reduction": int(len(reduced_df)),
            "positions_after_biological_filter": int(len(bio_df)),
            "alpha": self.alpha,
            "delta_mean_reduction_used": delta_gate,
            "lambda_var_used": float(lambda_used),
            "ecdf_overlap_grid_size": self.ecdf_overlap_grid_size,
            "time_total_s": time.perf_counter() - t0,
        }
        if lambda_corr is not None:
            report["effect_size_vs_1_minus_q_correlation"] = float(lambda_corr)
        if len(reduced_df) > 0 and np.isfinite(reduced_df["effect_size"]).any():
            effect_vals = reduced_df["effect_size"].astype(float).values
            report["effect_size_90th_percentile"] = float(np.percentile(effect_vals, 90))
            report["effect_size_95th_percentile"] = float(np.percentile(effect_vals, 95))
            report["effect_size_99th_percentile"] = float(np.percentile(effect_vals, 99))

        self._report = report
        self._result_df = bio_df
        return bio_df, report

    @property
    def report(self) -> Optional[Dict[str, Any]]:
        return self._report

    @property
    def result_df(self) -> Optional[pd.DataFrame]:
        return self._result_df

