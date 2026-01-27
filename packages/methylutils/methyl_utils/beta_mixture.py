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

DEFAULT_EPS = 1e-6
MIN_WEIGHT = 1e-8
MIN_PARAM = 1e-4
MAX_PARAM = 1e4


def _log_beta_pdf(x: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Vectorized log Beta PDF with numerical safeguards."""
    x = np.clip(x, DEFAULT_EPS, 1.0 - DEFAULT_EPS)
    return (a - 1.0) * np.log(x) + (b - 1.0) * np.log(1.0 - x) - betaln(a, b)


def _logsumexp(a: np.ndarray, axis: int = -1) -> np.ndarray:
    """Stable log-sum-exp."""
    a_max = np.max(a, axis=axis, keepdims=True)
    out = a_max + np.log(np.sum(np.exp(a - a_max), axis=axis, keepdims=True))
    return np.squeeze(out, axis=axis)


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


def fit_beta_mixture(
    values: np.ndarray,
    weights: Optional[np.ndarray] = None,
    max_components: int = 3,
    max_iter: int = 50,
    tol: float = 1e-5,
    min_component_weight: float = 0.02,
    random_state: Optional[int] = None,
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

    Returns:
        Dict with keys: k, weights, alphas, betas, loglik, bic, converged
    """
    if random_state is not None:
        np.random.seed(random_state)

    x = np.asarray(values, dtype=float)
    if weights is None:
        w = np.ones_like(x, dtype=float)
    else:
        w = np.asarray(weights, dtype=float)

    # Remove NaNs
    mask = np.isfinite(x) & np.isfinite(w)
    x = x[mask]
    w = w[mask]
    if len(x) < 5:
        # Fallback to single Beta with method-of-moments
        mean = np.average(x, weights=w)
        var = np.average((x - mean) ** 2, weights=w)
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

    n_eff = float(np.sum(w))
    best = None

    for k in range(1, max_components + 1):
        pis, alphas, betas = _initialize_components(x, k, w)
        # Small jitter to break symmetry
        alphas = np.clip(alphas * (1.0 + 0.05 * np.random.randn(k)), MIN_PARAM, MAX_PARAM)
        betas = np.clip(betas * (1.0 + 0.05 * np.random.randn(k)), MIN_PARAM, MAX_PARAM)

        prev_ll = None
        converged = False

        for _ in range(max_iter):
            log_pdf = np.stack([_log_beta_pdf(x, alphas[j], betas[j]) for j in range(k)], axis=1)
            log_weighted = log_pdf + np.log(pis + MIN_WEIGHT)
            log_norm = _logsumexp(log_weighted, axis=1)
            resp = np.exp(log_weighted - log_norm[:, None])

            # Weighted responsibilities
            wr = resp * w[:, None]
            Nk = np.sum(wr, axis=0)
            Nk = np.clip(Nk, MIN_WEIGHT, None)

            pis = Nk / np.sum(Nk)

            # M-step: weighted moments per component
            for j in range(k):
                mean_j = np.sum(wr[:, j] * x) / Nk[j]
                var_j = np.sum(wr[:, j] * (x - mean_j) ** 2) / Nk[j]
                alphas[j], betas[j] = _moments_to_beta(mean_j, var_j)

            # Log-likelihood
            ll = float(np.sum(w * log_norm))
            if prev_ll is not None and abs(ll - prev_ll) < tol * (1.0 + abs(prev_ll)):
                converged = True
                break
            prev_ll = ll

        # Remove tiny components
        keep = pis >= min_component_weight
        if np.sum(keep) == 0:
            keep = np.ones_like(pis, dtype=bool)
        pis = pis[keep]
        alphas = alphas[keep]
        betas = betas[keep]
        pis = pis / np.sum(pis)
        k_eff = len(pis)

        # BIC
        p = (k_eff - 1) + 2 * k_eff
        bic = -2.0 * prev_ll + p * np.log(max(n_eff, 1.0))

        candidate = {
            "k": k_eff,
            "weights": pis,
            "alphas": alphas,
            "betas": betas,
            "loglik": prev_ll,
            "bic": bic,
            "converged": converged,
        }

        if best is None or candidate["bic"] < best["bic"]:
            best = candidate

    return best


def mixture_logpdf(
    x: np.ndarray, weights: np.ndarray, alphas: np.ndarray, betas: np.ndarray
) -> np.ndarray:
    """Log-pdf of a beta mixture at x."""
    log_pdf = np.stack([_log_beta_pdf(x, alphas[j], betas[j]) for j in range(len(weights))], axis=1)
    log_weighted = log_pdf + np.log(weights + MIN_WEIGHT)
    return _logsumexp(log_weighted, axis=1)


def estimate_js_divergence(
    weights1: np.ndarray,
    alphas1: np.ndarray,
    betas1: np.ndarray,
    weights2: np.ndarray,
    alphas2: np.ndarray,
    betas2: np.ndarray,
    n_samples: int = 200,
    random_state: Optional[int] = None,
) -> float:
    """
    Estimate Jensen-Shannon divergence between two beta mixtures via Monte Carlo.
    """
    if random_state is not None:
        rng = np.random.default_rng(random_state)
    else:
        rng = np.random.default_rng()

    def sample_mixture(weights, alphas, betas, n):
        comp = rng.choice(len(weights), size=n, p=weights)
        samples = np.empty(n, dtype=float)
        for j in range(len(weights)):
            idx = comp == j
            if np.any(idx):
                samples[idx] = rng.beta(alphas[j], betas[j], size=np.sum(idx))
        return samples

    x1 = sample_mixture(weights1, alphas1, betas1, n_samples)
    x2 = sample_mixture(weights2, alphas2, betas2, n_samples)

    log_p1 = mixture_logpdf(x1, weights1, alphas1, betas1)
    log_p2 = mixture_logpdf(x1, weights2, alphas2, betas2)
    log_m = np.log(0.5 * np.exp(log_p1) + 0.5 * np.exp(log_p2) + DEFAULT_EPS)
    kl_p1_m = np.mean(log_p1 - log_m)

    log_q1 = mixture_logpdf(x2, weights2, alphas2, betas2)
    log_q2 = mixture_logpdf(x2, weights1, alphas1, betas1)
    log_m2 = np.log(0.5 * np.exp(log_q1) + 0.5 * np.exp(log_q2) + DEFAULT_EPS)
    kl_p2_m = np.mean(log_q1 - log_m2)

    js = 0.5 * (kl_p1_m + kl_p2_m)
    return float(max(js, 0.0))
