"""
Lightweight Beta Mixture Model (BMM) utilities.

Provides a small EM fitter with optional weighted samples to support
compressed/binned inputs (e.g., bin centers with counts as weights).
Designed for per-position fitting during DMP refinement.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
from scipy.special import betaln

from .gpu_detection import (
    is_gpu_available,
    is_cupyx_scipy_special_available,
    get_cupy,
    to_cpu_array,
)

DEFAULT_EPS = 1e-6
MIN_WEIGHT = 1e-8
MIN_PARAM = 1e-4
MAX_PARAM = 1e4


def _log_beta_pdf(
    x: np.ndarray,
    a: np.ndarray,
    b: np.ndarray,
    xp=np,
    betaln_fn=betaln,
) -> np.ndarray:
    """Vectorized log Beta PDF with numerical safeguards."""
    x = xp.clip(x, DEFAULT_EPS, 1.0 - DEFAULT_EPS)
    return (a - 1.0) * xp.log(x) + (b - 1.0) * xp.log(1.0 - x) - betaln_fn(a, b)


def _logsumexp(a: np.ndarray, axis: int = -1, xp=np) -> np.ndarray:
    """Stable log-sum-exp."""
    a_max = xp.max(a, axis=axis, keepdims=True)
    out = a_max + xp.log(xp.sum(xp.exp(a - a_max), axis=axis, keepdims=True))
    return xp.squeeze(out, axis=axis)


def _moments_to_beta(mean: float, var: float) -> Tuple[float, float]:
    """Convert mean/variance to alpha/beta with clipping."""
    mean = float(np.clip(mean, DEFAULT_EPS, 1.0 - DEFAULT_EPS))
    var = float(max(var, DEFAULT_EPS))
    phi = mean * (1.0 - mean) / var - 1.0
    if not np.isfinite(phi) or phi <= 0:
        phi = 2.0
    alpha = np.clip(mean * phi, MIN_PARAM, MAX_PARAM)
    beta = np.clip((1.0 - mean) * phi, MIN_PARAM, MAX_PARAM)
    return alpha, beta


def _initialize_components(
    values: np.ndarray, k: int, weights: Optional[np.ndarray]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Initialize mixture weights and Beta params from quantiles."""
    if weights is None:
        weights = np.ones_like(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    weights = np.clip(weights, MIN_WEIGHT, None)

    # Weighted quantiles for initialization
    order = np.argsort(values)
    vals = values[order]
    w = weights[order]
    cdf = np.cumsum(w) / np.sum(w)

    quantiles = np.linspace(0.15, 0.85, k)
    means = np.interp(quantiles, cdf, vals)
    var = np.average((values - np.average(values, weights=weights)) ** 2, weights=weights)

    pis = np.full(k, 1.0 / k, dtype=float)
    alphas = np.zeros(k, dtype=float)
    betas = np.zeros(k, dtype=float)
    for i in range(k):
        alphas[i], betas[i] = _moments_to_beta(means[i], var)
    return pis, alphas, betas


def _resolve_backend(use_gpu: bool):
    if use_gpu and is_gpu_available() and is_cupyx_scipy_special_available():
        cp = get_cupy()
        if cp is not None:
            try:
                from cupyx.scipy.special import betaln as cupy_betaln
                return cp, cupy_betaln, True
            except Exception:
                pass
    return np, betaln, False


def _to_numpy(arr):
    return to_cpu_array(arr)


def fit_beta_mixture(
    values: np.ndarray,
    weights: Optional[np.ndarray] = None,
    max_components: int = 3,
    max_iter: int = 50,
    tol: float = 1e-5,
    min_component_weight: float = 0.02,
    random_state: Optional[int] = None,
    use_gpu: bool = False,
) -> Dict[str, np.ndarray]:
    """
    Fit Beta mixture models (K=1..max_components) using EM and select by BIC.

    Args:
        values: 1D array of methylation values in [0, 1].
        weights: Optional weights for each value (e.g., binned counts).
        max_components: Maximum number of mixture components to try.
        max_iter: Maximum EM iterations per K.
        tol: Convergence tolerance on log-likelihood.
        min_component_weight: Minimum mixture weight to keep a component.
        random_state: Optional seed for reproducibility (affects init jitter).
        use_gpu: If True, attempt GPU acceleration (falls back to CPU if unavailable).

    Returns:
        Dict with keys: k, weights, alphas, betas, loglik, bic, converged
    """
    if random_state is not None:
        np.random.seed(random_state)

    xp, betaln_fn, using_gpu = _resolve_backend(use_gpu)

    x = np.asarray(values, dtype=float)
    if weights is None:
        w = np.ones_like(x, dtype=float)
    else:
        w = np.asarray(weights, dtype=float)

    # Remove NaNs
    if using_gpu:
        x = xp.asarray(x)
        w = xp.asarray(w)
        mask = xp.isfinite(x) & xp.isfinite(w)
    else:
        mask = np.isfinite(x) & np.isfinite(w)
    x = x[mask]
    w = w[mask]
    if len(x) < 5:
        # Fallback to single Beta with method-of-moments
        mean = float(np.average(_to_numpy(x), weights=_to_numpy(w)))
        var = float(np.average((_to_numpy(x) - mean) ** 2, weights=_to_numpy(w)))
        alpha, beta = _moments_to_beta(mean, var)
        return {
            "k": 1,
            "weights": np.array([1.0]),
            "alphas": np.array([alpha]),
            "betas": np.array([beta]),
            "loglik": float("nan"),
            "bic": float("inf"),
            "converged": False,
        }

    n_eff = float(xp.sum(w))
    best = None

    for k in range(1, max_components + 1):
        pis, alphas, betas = _initialize_components(_to_numpy(x), k, _to_numpy(w))
        if using_gpu:
            pis = xp.asarray(pis)
            alphas = xp.asarray(alphas)
            betas = xp.asarray(betas)
        # Small jitter to break symmetry
        alphas = xp.clip(alphas * (1.0 + 0.05 * np.random.randn(k)), MIN_PARAM, MAX_PARAM)
        betas = xp.clip(betas * (1.0 + 0.05 * np.random.randn(k)), MIN_PARAM, MAX_PARAM)

        prev_ll = None
        converged = False

        for _ in range(max_iter):
            log_pdf = xp.stack(
                [_log_beta_pdf(x, alphas[j], betas[j], xp=xp, betaln_fn=betaln_fn) for j in range(k)],
                axis=1
            )
            log_weighted = log_pdf + xp.log(pis + MIN_WEIGHT)
            log_norm = _logsumexp(log_weighted, axis=1, xp=xp)
            resp = xp.exp(log_weighted - log_norm[:, None])

            # Weighted responsibilities
            wr = resp * w[:, None]
            Nk = xp.sum(wr, axis=0)
            Nk = xp.clip(Nk, MIN_WEIGHT, None)

            pis = Nk / xp.sum(Nk)

            # M-step: weighted moments per component
            for j in range(k):
                mean_j = float(xp.sum(wr[:, j] * x) / Nk[j])
                var_j = float(xp.sum(wr[:, j] * (x - mean_j) ** 2) / Nk[j])
                alphas[j], betas[j] = _moments_to_beta(mean_j, var_j)

            # Log-likelihood
            ll = float(xp.sum(w * log_norm))
            if prev_ll is not None and abs(ll - prev_ll) < tol * (1.0 + abs(prev_ll)):
                converged = True
                break
            prev_ll = ll

        # Remove tiny components
        keep = pis >= min_component_weight
        if int(xp.sum(keep)) == 0:
            keep = xp.ones_like(pis, dtype=bool)
        pis = pis[keep]
        alphas = alphas[keep]
        betas = betas[keep]
        pis = pis / xp.sum(pis)
        k_eff = len(pis)

        # BIC
        p = (k_eff - 1) + 2 * k_eff
        bic = -2.0 * prev_ll + p * np.log(max(n_eff, 1.0))

        candidate = {
            "k": k_eff,
            "weights": _to_numpy(pis),
            "alphas": _to_numpy(alphas),
            "betas": _to_numpy(betas),
            "loglik": prev_ll,
            "bic": bic,
            "converged": converged,
        }

        if best is None or candidate["bic"] < best["bic"]:
            best = candidate

    return best


def mixture_logpdf(
    x: np.ndarray,
    weights: np.ndarray,
    alphas: np.ndarray,
    betas: np.ndarray,
    xp=np,
    betaln_fn=betaln,
) -> np.ndarray:
    """Log-pdf of a beta mixture at x."""
    log_pdf = xp.stack(
        [_log_beta_pdf(x, alphas[j], betas[j], xp=xp, betaln_fn=betaln_fn) for j in range(len(weights))],
        axis=1
    )
    log_weighted = log_pdf + xp.log(weights + MIN_WEIGHT)
    return _logsumexp(log_weighted, axis=1, xp=xp)


def estimate_js_divergence(
    weights1: np.ndarray,
    alphas1: np.ndarray,
    betas1: np.ndarray,
    weights2: np.ndarray,
    alphas2: np.ndarray,
    betas2: np.ndarray,
    n_samples: int = 200,
    random_state: Optional[int] = None,
    use_gpu: bool = False,
) -> float:
    """
    Estimate Jensen-Shannon divergence between two beta mixtures via Monte Carlo.

    Args:
        use_gpu: If True, attempt GPU acceleration (falls back to CPU if unavailable).
    """
    xp, betaln_fn, _ = _resolve_backend(use_gpu)
    if random_state is not None:
        try:
            xp.random.seed(random_state)
        except Exception:
            pass

    weights1 = xp.asarray(weights1, dtype=float)
    weights2 = xp.asarray(weights2, dtype=float)
    alphas1 = xp.asarray(alphas1, dtype=float)
    alphas2 = xp.asarray(alphas2, dtype=float)
    betas1 = xp.asarray(betas1, dtype=float)
    betas2 = xp.asarray(betas2, dtype=float)

    def _normalize(weights):
        denom = xp.sum(weights)
        if float(_to_numpy(denom)) <= 0.0:
            return xp.ones_like(weights) / max(len(weights), 1)
        return weights / denom

    def sample_mixture(weights, alphas, betas, n):
        weights = _normalize(weights)
        comp = xp.random.choice(len(weights), size=n, p=weights)
        samples = xp.empty(n, dtype=float)
        for j in range(len(weights)):
            idx = comp == j
            if bool(xp.any(idx)):
                count = int(_to_numpy(xp.sum(idx)))
                samples[idx] = xp.random.beta(alphas[j], betas[j], size=count)
        return samples

    x1 = sample_mixture(weights1, alphas1, betas1, n_samples)
    x2 = sample_mixture(weights2, alphas2, betas2, n_samples)

    log_p1 = mixture_logpdf(x1, weights1, alphas1, betas1, xp=xp, betaln_fn=betaln_fn)
    log_p2 = mixture_logpdf(x1, weights2, alphas2, betas2, xp=xp, betaln_fn=betaln_fn)
    log_m = xp.log(0.5 * xp.exp(log_p1) + 0.5 * xp.exp(log_p2) + DEFAULT_EPS)
    kl_p1_m = xp.mean(log_p1 - log_m)

    log_q1 = mixture_logpdf(x2, weights2, alphas2, betas2, xp=xp, betaln_fn=betaln_fn)
    log_q2 = mixture_logpdf(x2, weights1, alphas1, betas1, xp=xp, betaln_fn=betaln_fn)
    log_m2 = xp.log(0.5 * xp.exp(log_q1) + 0.5 * xp.exp(log_q2) + DEFAULT_EPS)
    kl_p2_m = xp.mean(log_q1 - log_m2)

    js = 0.5 * (kl_p1_m + kl_p2_m)
    return float(_to_numpy(xp.maximum(js, 0.0)))
