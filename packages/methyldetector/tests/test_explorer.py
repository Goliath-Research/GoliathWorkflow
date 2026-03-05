"""Tests for MethylDetectorExplorer and K-selection heuristics.

K-selection and helper logic is tested in isolation so tests run without
methyl_utils/hdf5plugin. Full MethylDetectorExplorer integration can be
tested when the full env is available.
"""

import numpy as np
import pytest

# Inline _choose_k logic so we can test without importing explorer (which pulls in methyl_utils)
def _choose_k_local(
    effect_sizes,
    heuristic,
    refine_top_k=None,
    max_decay_per_position=0.01,
    threshold_fraction=0.1,
    fraction_top=0.01,
):
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
        diff = np.diff(np.asarray(effect_sizes, dtype=np.float64))
        decay = np.abs(diff)
        over = np.where(decay > max_decay_per_position)[0]
        k = int(over[0] + 1) if len(over) > 0 else n
        k = min(k, n)
        return k, {"heuristic": "decay_limit", "max_decay_per_position": max_decay_per_position, "k": k}
    if heuristic == "knee":
        x = np.arange(n, dtype=np.float64)
        y = np.asarray(effect_sizes, dtype=np.float64)
        if len(y) < 3:
            return n, {"heuristic": "knee", "k": n}
        d1 = np.gradient(y, x)
        d2 = np.gradient(d1, x)
        curvature = np.abs(d2)
        top_half = curvature[: max(1, n // 2)]
        thresh = np.median(top_half) if len(top_half) > 0 else 0
        candidates = np.where(curvature >= thresh * 1.5)[0]
        k = int(candidates[0]) if len(candidates) > 0 else min(n, max(1, n // 10))
        k = min(max(1, k), n)
        return k, {"heuristic": "knee", "k": k}
    if heuristic == "threshold":
        thresh = max_eff * threshold_fraction
        k = int(np.sum(np.asarray(effect_sizes) >= thresh))
        k = min(max(1, k), n)
        return k, {"heuristic": "threshold", "threshold_fraction": threshold_fraction, "k": k}
    if heuristic == "fraction":
        k = min(max(1, int(n * fraction_top)), n)
        return k, {"heuristic": "fraction", "fraction_top": fraction_top, "k": k}
    k = min(max(1, int(n * 0.1)), 1000, n)
    return k, {"heuristic": "default", "k": k}


def _require_binned_stats_local(centroid):
    binned = getattr(centroid, "binned_stats", None)
    if not binned or "bin_edges" not in binned or "bin_counts" not in binned:
        raise ValueError("Centroids must have binned_stats (bin_edges, bin_counts).")


class TestChooseK:
    """Test K selection heuristics with synthetic effect size curves (mirrors explorer._choose_k)."""

    def test_fixed_override(self):
        effect_sizes = np.array([0.9, 0.8, 0.7, 0.6, 0.5])
        k, info = _choose_k_local(effect_sizes, "fixed", refine_top_k=3)
        assert k == 3
        assert info["heuristic"] == "fixed"

    def test_fixed_capped_by_n(self):
        effect_sizes = np.array([0.9, 0.8])
        k, _ = _choose_k_local(effect_sizes, "fixed", refine_top_k=10)
        assert k == 2

    def test_decay_limit(self):
        # Steep drop at index 2: diff[0]=0.05, diff[1]=0.02, diff[2]=0.5
        effect_sizes = np.array([1.0, 0.95, 0.93, 0.43, 0.4])
        k, info = _choose_k_local(
            effect_sizes, "decay_limit", max_decay_per_position=0.1
        )
        assert info["heuristic"] == "decay_limit"
        # First decay > 0.1 is at index 2 (0.93 - 0.43 = 0.5), so k = 2 + 1 = 3
        assert k == 3

    def test_threshold(self):
        effect_sizes = np.array([1.0, 0.8, 0.5, 0.2, 0.1])
        k, info = _choose_k_local(
            effect_sizes, "threshold", threshold_fraction=0.2
        )
        assert k >= 1
        assert info["heuristic"] == "threshold"

    def test_fraction(self):
        effect_sizes = np.array([1.0] * 100)
        k, info = _choose_k_local(
            effect_sizes, "fraction", fraction_top=0.1
        )
        assert k == 10
        assert info["heuristic"] == "fraction"

    def test_empty(self):
        k, info = _choose_k_local(np.array([]), "decay_limit")
        assert k == 0
        assert "reason" in info

    def test_knee_smoke(self):
        effect_sizes = np.linspace(1.0, 0.1, 50)
        k, info = _choose_k_local(effect_sizes, "knee")
        assert 1 <= k <= 50
        assert info["heuristic"] == "knee"


class TestExtractPhase1Data:
    """Test data extraction logic: mock centroids with N, mean, variance, binned_stats."""

    def test_extract_basic(self):
        n = 5
        indices = np.arange(n)

        class MockCentroid:
            def __init__(self, N, mean, var, bin_counts):
                self._n = np.asarray(N, dtype=np.float64)
                self._mean = np.asarray(mean, dtype=np.float64)
                self._var = np.asarray(var, dtype=np.float64)
                self._bc = np.asarray(bin_counts, dtype=np.float64)

            @property
            def N(self):
                return self._n

            @property
            def mean(self):
                return self._mean

            @property
            def variance(self):
                return self._var

            @property
            def binned_stats(self):
                return {"bin_edges": np.linspace(0, 1, 6), "bin_counts": self._bc}

        N1 = np.array([10.0] * n)
        N2 = np.array([12.0] * n)
        mean1 = np.array([0.2, 0.5, 0.8, 0.3, 0.6])
        mean2 = np.array([0.3, 0.4, 0.5, 0.5, 0.4])
        var1 = np.array([0.01] * n)
        var2 = np.array([0.01] * n)
        np.random.seed(42)
        bc1 = np.random.rand(n, 5).astype(np.float64)
        bc2 = np.random.rand(n, 5).astype(np.float64)
        c1 = MockCentroid(N1, mean1, var1, bc1)
        c2 = MockCentroid(N2, mean2, var2, bc2)
        # Inline extract: same as explorer._extract_phase1_data
        def to_arr(x):
            return np.asarray(x.values, dtype=np.float64).ravel() if hasattr(x, "values") else np.asarray(x, dtype=np.float64).ravel()
        n1 = to_arr(c1.N)[indices]
        n2 = to_arr(c2.N)[indices]
        mean1_i = to_arr(c1.mean)[indices]
        mean2_i = to_arr(c2.mean)[indices]
        var1_i = to_arr(c1.variance)[indices]
        var2_i = to_arr(c2.variance)[indices]
        delta_mean = mean1_i - mean2_i
        bc1_i = np.asarray(c1.binned_stats["bin_counts"], dtype=np.float64)[indices]
        bc2_i = np.asarray(c2.binned_stats["bin_counts"], dtype=np.float64)[indices]
        assert len(delta_mean) == n
        np.testing.assert_array_almost_equal(delta_mean, mean1 - mean2)
        np.testing.assert_array_almost_equal(var1_i, var1)
        np.testing.assert_array_almost_equal(var2_i, var2)
        assert bc1_i.shape == (n, 5)
        assert bc2_i.shape == (n, 5)


class TestRequireBinnedStats:
    """Test binned_stats requirement (mirrors explorer._require_binned_stats)."""

    def test_raises_when_missing(self):
        class NoBinned:
            pass
        with pytest.raises(ValueError, match="binned_stats"):
            _require_binned_stats_local(NoBinned())

    def test_raises_when_empty(self):
        class EmptyBinned:
            binned_stats = {}
        with pytest.raises(ValueError, match="binned_stats"):
            _require_binned_stats_local(EmptyBinned())

    def test_passes_when_present(self):
        class WithBinned:
            binned_stats = {"bin_edges": np.array([0, 1]), "bin_counts": np.array([[1.0]])}
        _require_binned_stats_local(WithBinned())
