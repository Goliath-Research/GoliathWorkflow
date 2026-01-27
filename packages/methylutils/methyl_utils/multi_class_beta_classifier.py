"""
Multi-class Beta (and Beta Mixture) classifier for methylation data.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


class MultiClassBetaMixtureClassifier:
    """
    Multi-class Bayesian classifier using Beta distributions with optional
    Beta Mixture overrides for selected DMPs.
    """

    def __init__(
        self,
        data: Dict[str, Any],
        min_sample_coverage: int = 10,
        coverage_weighting: bool = True,
    ):
        self.data = data
        self.min_sample_coverage = min_sample_coverage
        self.coverage_weighting = coverage_weighting

        self.positions = np.asarray(data["positions"], dtype=np.uint32)
        self.weights = np.asarray(
            data.get("weights", np.ones(len(self.positions))), dtype=np.float64
        )

        self.alpha = np.asarray(data["alpha"], dtype=np.float64)
        self.beta = np.asarray(data["beta"], dtype=np.float64)

        self.class_names = data.get("class_names")
        self.n_classes = (
            len(self.class_names) if self.class_names is not None else self.alpha.shape[0]
        )
        self.temperature = 2.0

        # Optional mixture parameters: list per class, list per position
        self.mix_weights = data.get("mix_weights")
        self.mix_alphas = data.get("mix_alphas")
        self.mix_betas = data.get("mix_betas")

        self._validate_shapes()

    def _validate_shapes(self) -> None:
        n_features = len(self.positions)
        if self.alpha.shape[0] != self.n_classes or self.beta.shape[0] != self.n_classes:
            raise ValueError(
                f"alpha/beta class dimension mismatch: expected {self.n_classes}, "
                f"got alpha={self.alpha.shape[0]}, beta={self.beta.shape[0]}"
            )
        if self.alpha.shape[1] != n_features or self.beta.shape[1] != n_features:
            raise ValueError(
                f"alpha/beta feature dimension mismatch: expected {n_features}, "
                f"got alpha={self.alpha.shape[1]}, beta={self.beta.shape[1]}"
            )
        if len(self.weights) != n_features:
            raise ValueError(
                f"weights length mismatch: expected {n_features}, got {len(self.weights)}"
            )
        if self.mix_weights is not None:
            if len(self.mix_weights) != self.n_classes:
                raise ValueError(
                    f"mix_weights class dimension mismatch: expected {self.n_classes}, "
                    f"got {len(self.mix_weights)}"
                )
            for i, per_class in enumerate(self.mix_weights):
                if per_class is not None and len(per_class) != n_features:
                    raise ValueError(
                        f"mix_weights[{i}] length mismatch: expected {n_features}, got {len(per_class)}"
                    )

    def set_temperature(self, temperature: float = 1.0) -> None:
        self.temperature = max(temperature, 0.1)

    def get_feature_info(self) -> Dict[str, Any]:
        return {
            "n_features": len(self.positions),
            "positions": self.positions,
            "weights": self.weights,
        }

    def predict_proba(
        self,
        X: np.ndarray,
        availability_mask: Optional[np.ndarray] = None,
        debug: bool = False,
        use_gpu: bool = True,
    ) -> np.ndarray:
        if X.shape[1] != len(self.positions):
            raise ValueError(
                f"Expected {len(self.positions)} features, got {X.shape[1]}"
            )

        try:
            from methyl_utils.beta_analytics import beta_log_pdf
            from methyl_utils.gpu_detection import is_gpu_available
        except ImportError:
            from .beta_analytics import beta_log_pdf
            from .gpu_detection import is_gpu_available

        use_gpu = use_gpu and is_gpu_available()

        n_samples = X.shape[0]
        n_features = len(self.positions)
        log_likelihoods = np.zeros((n_samples, self.n_classes), dtype=np.float64)

        methylation_vals = np.clip(X, 1e-6, 1 - 1e-6)

        # Validate parameters across classes
        valid = (
            np.isfinite(self.alpha)
            & np.isfinite(self.beta)
            & (self.alpha > 0)
            & (self.beta > 0)
        )
        valid_all = np.all(valid, axis=0)

        if availability_mask is not None:
            effective_mask = availability_mask & valid_all
        else:
            effective_mask = np.repeat(valid_all[np.newaxis, :], n_samples, axis=0)

        valid_counts = np.sum(effective_mask, axis=1)

        # Optional mixture override
        mix_available = (
            self.mix_weights is not None
            and self.mix_alphas is not None
            and self.mix_betas is not None
        )
        if mix_available:
            try:
                from methyl_utils.beta_mixture import mixture_logpdf, _resolve_backend, _to_numpy
            except ImportError:
                from .beta_mixture import mixture_logpdf, _resolve_backend, _to_numpy
            xp, betaln_fn, _ = _resolve_backend(use_gpu)
        else:
            mixture_logpdf = None
            _to_numpy = None
            xp = None
            betaln_fn = None

        for c in range(self.n_classes):
            alpha_c = self.alpha[c][np.newaxis, :]
            beta_c = self.beta[c][np.newaxis, :]
            log_p = beta_log_pdf(methylation_vals, alpha_c, beta_c, use_gpu=use_gpu)

            if mix_available and self.mix_weights[c] is not None:
                mixture_used = 0
                for idx in range(n_features):
                    w = self.mix_weights[c][idx]
                    a = self.mix_alphas[c][idx]
                    b = self.mix_betas[c][idx]
                    if not w or not a or not b:
                        continue

                    w = np.asarray(w, dtype=float)
                    a = np.asarray(a, dtype=float)
                    b = np.asarray(b, dtype=float)

                    if len(w) == 0 or len(w) != len(a) or len(w) != len(b):
                        continue

                    x = methylation_vals[:, idx]
                    try:
                        log_m = mixture_logpdf(
                            xp.asarray(x),
                            xp.asarray(w),
                            xp.asarray(a),
                            xp.asarray(b),
                            xp=xp,
                            betaln_fn=betaln_fn,
                        )
                        log_m = _to_numpy(log_m)
                    except Exception:
                        continue

                    if np.any(~np.isfinite(log_m)):
                        continue

                    log_p[:, idx] = log_m
                    mixture_used += 1

                if debug and mixture_used > 0:
                    print(f"Class {c}: using BMM mixtures for {mixture_used} positions")

            log_p = np.where(effective_mask, log_p, 0.0)
            weighted_log_p = log_p * self.weights[np.newaxis, :]
            log_likelihoods[:, c] = np.sum(weighted_log_p, axis=1)

        # Handle no valid positions (neutral)
        mask_no_valid = valid_counts == 0
        log_likelihoods[mask_no_valid] = 0.0

        # Softmax with temperature
        scaled = log_likelihoods / self.temperature
        max_log = np.max(scaled, axis=1, keepdims=True)
        exp_vals = np.exp(scaled - max_log)
        probs = exp_vals / np.sum(exp_vals, axis=1, keepdims=True)

        return probs

    def predict(
        self,
        X: np.ndarray,
        availability_mask: Optional[np.ndarray] = None,
        debug: bool = False,
        use_gpu: bool = True,
    ) -> np.ndarray:
        probs = self.predict_proba(X, availability_mask, debug=debug, use_gpu=use_gpu)
        return np.argmax(probs, axis=1)

