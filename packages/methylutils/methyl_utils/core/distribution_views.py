# methyl_utils/core/distribution_views.py
"""
Distribution views for methylation centroids: common protocol (parameters, mean, overlap)
and six implementations: Counts, Normal, Beta, Beta-Binomial, Beta Mixture Model, ECDF.
All handle edge cases where methylation level is 0 (mC=0) or 1 (uC=0).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Union

import numpy as np

try:
    from scipy.interpolate import PchipInterpolator
except ImportError:
    PchipInterpolator = None  # type: ignore

try:
    from .methyl_frame import MethylExtendedCentroid, MethylBetaBinomialCentroid, MethylSample
except ImportError:
    MethylExtendedCentroid = None  # type: ignore
    MethylBetaBinomialCentroid = None  # type: ignore
    MethylSample = None  # type: ignore

MIN_EPS = 1e-12


class MethylDistributionView(Protocol):
    """Protocol: parameters, mean, and overlap(other)."""

    @property
    def parameters(self) -> Dict[str, Any]:
        """Distribution parameters (e.g. alpha, beta; or mu, sigma2; or weights, alphas, betas)."""
        ...

    @property
    def mean(self) -> np.ndarray:
        """Per-position mean (0/1 safe)."""
        ...

    def overlap(self, other: "MethylDistributionView") -> np.ndarray:
        """Overlap with another view; returns array in [0, 1]."""
        ...


def _clip_proportion(p: np.ndarray, eps: float = MIN_EPS) -> np.ndarray:
    return np.clip(np.asarray(p, dtype=np.float64), eps, 1.0 - eps)


def _safe_mean_numer(a: np.ndarray, b: np.ndarray, eps: float = MIN_EPS) -> np.ndarray:
    s = np.maximum(np.asarray(a, dtype=np.float64) + np.asarray(b, dtype=np.float64), eps)
    return np.where(s > 0, np.asarray(a, dtype=np.float64) / s, 0.5)


# --- Counts view (proportions from mC, uC) ---
class CountsView:
    """Count-based view: parameters = (mC, uC), mean = mC/(mC+uC), 0/1 safe."""

    def __init__(self, mC: np.ndarray, uC: np.ndarray):
        self._mC = np.asarray(mC, dtype=np.uint32)
        self._uC = np.asarray(uC, dtype=np.uint32)
        cov = self._mC.astype(np.float64) + self._uC.astype(np.float64)
        self._mean = np.where(cov > 0, self._mC.astype(np.float64) / cov, 0.5)

    @property
    def parameters(self) -> Dict[str, Any]:
        return {"mC": self._mC, "uC": self._uC}

    @property
    def mean(self) -> np.ndarray:
        return self._mean

    def overlap(self, other: MethylDistributionView) -> np.ndarray:
        if isinstance(other, CountsView):
            n = min(len(self._mean), len(other.mean))
            return np.maximum(0, 1 - np.abs(self._mean[:n] - other.mean[:n]))
        # vs Beta: use other's mean and 1 - |p1 - p2| as proxy
        om = np.asarray(other.mean, dtype=np.float64)
        n = min(len(self._mean), len(om))
        return np.clip(1 - np.abs(self._mean[:n] - om[:n]), 0, 1)


# --- Normal view (mu, sigma2 from Sx, Sx2, N) ---
class NormalView:
    """Normal view: parameters = (mu, sigma2), mean = mu."""

    def __init__(self, Sx: np.ndarray, Sx2: np.ndarray, N: np.ndarray):
        N = np.maximum(np.asarray(N, dtype=np.float64), 1)
        self._mu = np.asarray(Sx, dtype=np.float64) / N
        self._sigma2 = np.maximum(
            np.asarray(Sx2, dtype=np.float64) / N - self._mu ** 2,
            MIN_EPS,
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {"mu": self._mu, "sigma2": self._sigma2}

    @property
    def mean(self) -> np.ndarray:
        return self._mu

    def overlap(self, other: MethylDistributionView) -> np.ndarray:
        from methyl_utils.beta_analytics import compute_bhattacharyya_coefficient
        if isinstance(other, NormalView):
            mu1, v1 = self._mu, self._sigma2
            mu2 = np.asarray(other.mean, dtype=np.float64)
            v2 = np.asarray(other.parameters["sigma2"], dtype=np.float64)
            n = min(len(mu1), len(mu2))
            mu1, v1, mu2, v2 = mu1[:n], v1[:n], mu2[:n], v2[:n]
            # Bhattacharyya for Normal: exp(- (mu1-mu2)^2 / (8 * (var1+var2)/2) ) = exp(- (mu1-mu2)^2 / (4*(v1+v2)))
            denom = 4 * (v1 + v2)
            denom = np.maximum(denom, MIN_EPS)
            bc = np.exp(-((mu1 - mu2) ** 2) / denom)
            return np.clip(bc, 0, 1)
        # vs Beta: approximate Beta by Normal and use above
        om = np.asarray(other.mean, dtype=np.float64)
        n = min(len(self._mu), len(om))
        v2 = np.full(n, MIN_EPS)
        if "sigma2" in getattr(other, "parameters", {}):
            v2 = np.asarray(other.parameters["sigma2"], dtype=np.float64)[:n]
        denom = 4 * (self._sigma2[:n] + v2)
        denom = np.maximum(denom, MIN_EPS)
        bc = np.exp(-((self._mu[:n] - om[:n]) ** 2) / denom)
        return np.clip(bc, 0, 1)


# --- Beta view ---
class BetaView:
    """Beta view: parameters = (alpha, beta), mean = alpha/(alpha+beta), 0/1 safe."""

    def __init__(self, alpha: np.ndarray, beta: np.ndarray):
        from .methyl_distribution_utils import clip_beta_params_for_bounds
        self._alpha, self._beta = clip_beta_params_for_bounds(
            np.asarray(alpha, dtype=np.float64),
            np.asarray(beta, dtype=np.float64),
        )
        self._mean = _safe_mean_numer(self._alpha, self._beta)

    @property
    def parameters(self) -> Dict[str, Any]:
        return {"alpha": self._alpha, "beta": self._beta}

    @property
    def mean(self) -> np.ndarray:
        return self._mean

    def overlap(self, other: MethylDistributionView) -> np.ndarray:
        from methyl_utils.beta_analytics import compute_bhattacharyya_coefficient
        a2 = np.asarray(getattr(other, "parameters", {}).get("alpha", getattr(other, "alpha_bb", None)), dtype=np.float64)
        b2 = np.asarray(getattr(other, "parameters", {}).get("beta", getattr(other, "beta_bb", None)), dtype=np.float64)
        if a2 is None or b2 is None:
            a2 = np.asarray(other.mean, dtype=np.float64)
            b2 = np.maximum(1 - a2, MIN_EPS) * 10
            a2 = np.maximum(a2 * 10, MIN_EPS)
        n = min(len(self._alpha), len(a2))
        return compute_bhattacharyya_coefficient(
            self._alpha[:n], self._beta[:n], a2[:n], b2[:n], use_gpu=False
        )


# --- Beta-Binomial view ---
class BetaBinomialView:
    """Beta-Binomial view: parameters = (alpha, beta[, n]), mean = alpha/(alpha+beta)."""

    def __init__(self, alpha: np.ndarray, beta: np.ndarray, n: Optional[np.ndarray] = None):
        from .methyl_distribution_utils import clip_beta_params_for_bounds
        self._alpha, self._beta = clip_beta_params_for_bounds(
            np.asarray(alpha, dtype=np.float64),
            np.asarray(beta, dtype=np.float64),
        )
        self._n = np.asarray(n, dtype=np.uint32) if n is not None else None
        self._mean = _safe_mean_numer(self._alpha, self._beta)

    @property
    def parameters(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"alpha": self._alpha, "beta": self._beta}
        if self._n is not None:
            out["n"] = self._n
        return out

    @property
    def mean(self) -> np.ndarray:
        return self._mean

    def overlap(self, other: MethylDistributionView) -> np.ndarray:
        from methyl_utils.beta_analytics import compute_bhattacharyya_coefficient
        a2 = np.asarray(getattr(other, "parameters", {}).get("alpha", getattr(other, "alpha_bb", other.mean)), dtype=np.float64)
        b2 = np.asarray(getattr(other, "parameters", {}).get("beta", getattr(other, "beta_bb", None)), dtype=np.float64)
        if b2 is None:
            b2 = np.maximum(1 - a2, MIN_EPS) * 10
            a2 = np.maximum(a2 * 10, MIN_EPS)
        n = min(len(self._alpha), len(a2))
        return compute_bhattacharyya_coefficient(
            self._alpha[:n], self._beta[:n], a2[:n], b2[:n], use_gpu=False
        )


# --- ECDF view (spline-interpolated from binned_stats) ---
# KS grid size for overlap
_ECDF_KS_GRID_SIZE = 256


class ECDFView:
    """
    Empirical CDF view: parameters from binned_stats (bin_edges, bin_counts).
    Uses PCHIP spline interpolation so F(x) and PDF(x)=F'(x) are defined for any x in [0,1].
    Mean = Sx/N, variance = sample variance from Sx, Sx2, N.
    """

    def __init__(
        self,
        bin_edges: np.ndarray,
        bin_counts: np.ndarray,
        Sx: np.ndarray,
        N: np.ndarray,
        Sx2: Optional[np.ndarray] = None,
    ):
        self._bin_edges = np.asarray(bin_edges, dtype=np.float64)
        self._bin_counts = np.asarray(bin_counts, dtype=np.float64)
        n_positions, n_bins = self._bin_counts.shape
        if len(self._bin_edges) != n_bins + 1:
            raise ValueError("bin_edges length must be n_bins + 1")
        self._Sx = np.asarray(Sx, dtype=np.float64)
        self._N = np.maximum(np.asarray(N, dtype=np.float64), 1.0)
        self._mean = self._Sx / self._N
        if Sx2 is not None:
            self._Sx2 = np.asarray(Sx2, dtype=np.float64)
            self._variance = np.maximum(
                (self._Sx2 / self._N) - (self._Sx / self._N) ** 2,
                MIN_EPS,
            )
            self._variance = self._variance / np.maximum(self._N - 1.0, 1.0)
        else:
            self._Sx2 = None
            self._variance = np.full(n_positions, MIN_EPS, dtype=np.float64)

        # Build per-position CDF at bin edges: [0, cdf_1, cdf_2, ..., 1]
        total = np.sum(self._bin_counts, axis=1, keepdims=True)
        total = np.maximum(total, MIN_EPS)
        cdf_at_edges = np.cumsum(self._bin_counts, axis=1) / total
        cdf_at_edges = np.concatenate(
            [np.zeros((n_positions, 1), dtype=np.float64), cdf_at_edges],
            axis=1,
        )

        self._interpolators: List[Any] = []
        if PchipInterpolator is not None:
            for i in range(n_positions):
                interp = PchipInterpolator(self._bin_edges, cdf_at_edges[i])
                self._interpolators.append(interp)
        else:
            self._interpolators = None
        self._cdf_at_edges = cdf_at_edges
        self._n_positions = n_positions

    @property
    def parameters(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "bin_edges": self._bin_edges,
            "bin_counts": self._bin_counts,
            "Sx": self._Sx,
            "N": self._N,
        }
        if self._Sx2 is not None:
            out["Sx2"] = self._Sx2
        return out

    @property
    def mean(self) -> np.ndarray:
        return self._mean

    @property
    def variance(self) -> np.ndarray:
        return self._variance

    def _cdf(self, position_idx: int, x: np.ndarray) -> np.ndarray:
        x = np.clip(np.asarray(x, dtype=np.float64), 0.0, 1.0)
        if self._interpolators is not None:
            return np.clip(self._interpolators[position_idx](x), 0.0, 1.0)
        # Fallback: piecewise constant from edges
        return np.interp(x, self._bin_edges, self._cdf_at_edges[position_idx])

    def _pdf(self, position_idx: int, x: float) -> float:
        if self._interpolators is not None:
            interp = self._interpolators[position_idx]
            deriv = interp.derivative()
            pdf_val = float(deriv(x))
            return max(pdf_val, MIN_EPS)
        # Piecewise constant: find bin, return (count/total)/width
        total = np.sum(self._bin_counts[position_idx])
        if total <= 0:
            return MIN_EPS
        idx = np.searchsorted(self._bin_edges, x, side="right") - 1
        idx = np.clip(idx, 0, self._bin_counts.shape[1] - 1)
        width = self._bin_edges[idx + 1] - self._bin_edges[idx]
        width = max(width, 1e-10)
        return max(float(self._bin_counts[position_idx, idx] / total / width), MIN_EPS)

    def overlap(self, other: MethylDistributionView) -> np.ndarray:
        if isinstance(other, ECDFView):
            n = min(self._n_positions, len(other.mean))
            grid = np.linspace(0.0, 1.0, _ECDF_KS_GRID_SIZE, dtype=np.float64)
            ks = np.zeros(n, dtype=np.float64)
            for i in range(n):
                f1 = self._cdf(i, grid)
                f2 = other._cdf(i, grid)
                ks[i] = np.max(np.abs(f1 - f2))
            return np.clip(1.0 - ks, 0.0, 1.0)
        om = np.asarray(other.mean, dtype=np.float64)
        n = min(len(self._mean), len(om))
        return np.clip(1.0 - np.abs(self._mean[:n] - om[:n]), 0.0, 1.0)


# --- BMM view (per-position weights, alphas, betas) ---
class BMMView:
    """Beta Mixture Model view: parameters = (weights, alphas, betas) per position, mean = weighted component means."""

    def __init__(
        self,
        weights: Union[List[np.ndarray], np.ndarray],
        alphas: Union[List[np.ndarray], np.ndarray],
        betas: Union[List[np.ndarray], np.ndarray],
    ):
        if isinstance(weights, np.ndarray) and weights.ndim == 2:
            self._weights = np.asarray(weights, dtype=np.float64)
            self._alphas = np.asarray(alphas, dtype=np.float64)
            self._betas = np.asarray(betas, dtype=np.float64)
        else:
            self._weights = np.stack([np.asarray(w, dtype=np.float64) for w in weights], axis=1)
            self._alphas = np.stack([np.maximum(np.asarray(a, dtype=np.float64), MIN_EPS) for a in alphas], axis=1)
            self._betas = np.stack([np.maximum(np.asarray(b, dtype=np.float64), MIN_EPS) for b in betas], axis=1)
        comp_means = self._alphas / np.maximum(self._alphas + self._betas, MIN_EPS)
        self._mean = np.sum(self._weights * comp_means, axis=1)

    @property
    def parameters(self) -> Dict[str, Any]:
        return {"weights": self._weights, "alphas": self._alphas, "betas": self._betas}

    @property
    def mean(self) -> np.ndarray:
        return self._mean

    def overlap(self, other: MethylDistributionView) -> np.ndarray:
        om = np.asarray(other.mean, dtype=np.float64)
        n = min(len(self._mean), len(om))
        return np.clip(1 - np.abs(self._mean[:n] - om[:n]), 0, 1)


def get_distribution_view(
    centroid: Union[MethylExtendedCentroid, MethylBetaBinomialCentroid],
    mode: str,
    positions: Optional[np.ndarray] = None,
) -> MethylDistributionView:
    """Build a distribution view from a centroid for the given mode."""
    mode = (mode or "beta").lower()
    if positions is not None:
        pos_arr = np.asarray(centroid.pos.values, dtype=np.uint32)
        idx = np.isin(pos_arr, np.asarray(positions, dtype=np.uint32))
        centroid = centroid[idx]
    if mode == "counts":
        return CountsView(
            np.asarray(centroid.mC.values),
            np.asarray(centroid.uC.values),
        )
    if mode == "normal":
        return NormalView(
            np.asarray(centroid.Sx.values),
            np.asarray(centroid.Sx2.values),
            np.asarray(centroid.N.values),
        )
    if mode == "beta":
        return BetaView(
            np.asarray(centroid.alpha.values),
            np.asarray(centroid.beta.values),
        )
    if mode == "beta_binomial":
        a = getattr(centroid, "alpha_bb", centroid.alpha).values
        b = getattr(centroid, "beta_bb", centroid.beta).values
        return BetaBinomialView(np.asarray(a), np.asarray(b), np.asarray(centroid.N.values))
    if mode == "ecdf":
        binned = getattr(centroid, "binned_stats", None)
        if binned is None or "bin_edges" not in binned or "bin_counts" not in binned:
            raise ValueError(
                "ecdf view requires centroid with binned_stats (bin_edges, bin_counts). "
                "Build centroid with enable_binned_stats=True."
            )
        bin_edges = np.asarray(binned["bin_edges"], dtype=np.float64)
        bin_counts = np.asarray(binned["bin_counts"], dtype=np.float64)
        Sx = np.asarray(centroid.Sx.values, dtype=np.float64)
        N = np.asarray(centroid.N.values, dtype=np.float64)
        Sx2 = np.asarray(centroid.Sx2.values, dtype=np.float64) if hasattr(centroid, "Sx2") else None
        return ECDFView(bin_edges, bin_counts, Sx, N, Sx2)
    if mode == "beta_mixture":
        raise ValueError("beta_mixture view requires MethylBetaMixtureCentroid; use its mean/overlap directly.")
    raise ValueError(
        f"Unknown mode: {mode}. Use one of: counts, normal, beta, beta_binomial, beta_mixture, ecdf"
    )


def log_probability_sample_given_centroid(
    sample: Any,
    centroid: Union[MethylExtendedCentroid, MethylBetaBinomialCentroid],
    mode: str,
    positions: Optional[np.ndarray] = None,
    use_gpu: bool = False,
) -> np.ndarray:
    """
    Log P(sample | centroid) per position for the given mode.
    Aligns sample to centroid on common positions; returns log prob per position (0/1 safe).
    """
    mode = (mode or "beta").lower()
    pos_c = np.asarray(centroid.pos.values, dtype=np.uint32)
    pos_s = np.asarray(sample.pos.values, dtype=np.uint32)
    if positions is not None:
        positions = np.asarray(positions, dtype=np.uint32)
        pos_c = pos_c[np.isin(pos_c, positions)]
    common = np.intersect1d(pos_c, pos_s, assume_unique=True)
    if len(common) == 0:
        return np.array([], dtype=np.float64)
    idx_c = np.searchsorted(pos_c, common)
    idx_s = np.searchsorted(pos_s, common)
    n = len(common)

    if mode == "counts":
        mC_c = np.asarray(centroid.mC.values, dtype=np.float64)[idx_c]
        uC_c = np.asarray(centroid.uC.values, dtype=np.float64)[idx_c]
        p = mC_c / np.maximum(mC_c + uC_c, MIN_EPS)
        p = _clip_proportion(p)
        k = np.asarray(sample.mC.values, dtype=np.float64)[idx_s]
        cov = np.asarray(sample.mC.values, dtype=np.float64)[idx_s] + np.asarray(sample.uC.values, dtype=np.float64)[idx_s]
        log_p = k * np.log(p) + (cov - k) * np.log(1 - p)
        return np.asarray(log_p, dtype=np.float64)

    if mode == "normal":
        N = np.maximum(np.asarray(centroid.N.values, dtype=np.float64)[idx_c], 1)
        mu = np.asarray(centroid.Sx.values, dtype=np.float64)[idx_c] / N
        Sx2 = np.asarray(centroid.Sx2.values, dtype=np.float64)[idx_c]
        sigma2 = np.maximum(Sx2 / N - mu ** 2, MIN_EPS)
        x = (np.asarray(sample.mC.values, dtype=np.float64)[idx_s] / np.maximum(
            np.asarray(sample.mC.values, dtype=np.float64)[idx_s] + np.asarray(sample.uC.values, dtype=np.float64)[idx_s],
            MIN_EPS,
        ))
        log_p = -0.5 * (np.log(2 * np.pi * sigma2) + (x - mu) ** 2 / sigma2)
        return log_p

    if mode == "beta":
        from methyl_utils.beta_analytics import beta_log_pdf
        alpha = np.asarray(centroid.alpha.values, dtype=np.float64)[idx_c]
        beta = np.asarray(centroid.beta.values, dtype=np.float64)[idx_c]
        cov_s = np.asarray(sample.mC.values, dtype=np.float64)[idx_s] + np.asarray(sample.uC.values, dtype=np.float64)[idx_s]
        x = np.where(cov_s > 0, np.asarray(sample.mC.values, dtype=np.float64)[idx_s] / cov_s, 0.5)
        x = _clip_proportion(x)
        return beta_log_pdf(x, alpha, beta, use_gpu=use_gpu)

    if mode == "beta_binomial":
        from methyl_utils.beta_analytics import log_beta_binomial_pmf
        alpha = np.asarray(getattr(centroid, "alpha_bb", centroid.alpha).values, dtype=np.float64)[idx_c]
        beta = np.asarray(getattr(centroid, "beta_bb", centroid.beta).values, dtype=np.float64)[idx_c]
        k = np.asarray(sample.mC.values, dtype=np.int64)[idx_s]
        n_trials = np.asarray(sample.mC.values, dtype=np.int64)[idx_s] + np.asarray(sample.uC.values, dtype=np.int64)[idx_s]
        return log_beta_binomial_pmf(k, n_trials, alpha, beta, use_gpu=use_gpu)

    if mode == "ecdf":
        binned = getattr(centroid, "binned_stats", None)
        if binned is None or "bin_edges" not in binned or "bin_counts" not in binned:
            raise ValueError(
                "log_probability with mode=ecdf requires centroid with binned_stats. "
                "Build centroid with enable_binned_stats=True."
            )
        view = get_distribution_view(centroid, "ecdf", positions=common)
        cov_s = np.asarray(sample.mC.values, dtype=np.float64)[idx_s] + np.asarray(sample.uC.values, dtype=np.float64)[idx_s]
        x = np.where(cov_s > 0, np.asarray(sample.mC.values, dtype=np.float64)[idx_s] / cov_s, 0.5)
        x = _clip_proportion(x)
        log_p = np.zeros(n, dtype=np.float64)
        for i in range(n):
            pdf_val = view._pdf(i, float(x[i]))
            log_p[i] = np.log(max(pdf_val, MIN_EPS))
        return log_p

    if mode == "beta_mixture":
        raise ValueError("beta_mixture requires MethylBetaMixtureCentroid; use mixture_logpdf separately.")
    raise ValueError(f"Unknown mode: {mode}")


def overlap_between_centroids(
    centroid1: Union[MethylExtendedCentroid, MethylBetaBinomialCentroid],
    centroid2: Union[MethylExtendedCentroid, MethylBetaBinomialCentroid],
    mode: str,
    positions: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Overlap between two centroids for the given mode (Bhattacharyya or mode-specific)."""
    v1 = get_distribution_view(centroid1, mode, positions)
    v2 = get_distribution_view(centroid2, mode, positions)
    return v1.overlap(v2)
