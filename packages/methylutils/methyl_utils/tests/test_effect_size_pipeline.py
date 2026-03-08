import sys
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "packages/methylutils"))

from methyl_utils.core.distribution_views import ECDFView
from methyl_utils.statistical_tests import (
    ecdf_overlap_integral,
    effect_size_from_components,
    ecdf_effect_size,
)


def _build_view(bin_counts, means, variances, n=40):
    bin_counts = np.asarray(bin_counts, dtype=np.float64)
    means = np.asarray(means, dtype=np.float64)
    variances = np.asarray(variances, dtype=np.float64)
    N = np.full(len(means), float(n), dtype=np.float64)
    Sx = means * N
    Sx2 = variances * np.maximum(N - 1.0, 1.0) + (Sx ** 2) / N
    bin_edges = np.linspace(0.0, 1.0, bin_counts.shape[1] + 1, dtype=np.float64)
    return ECDFView(bin_edges, bin_counts, Sx, N, Sx2)


def test_identical_distributions_have_overlap_one_and_zero_effect():
    view1 = _build_view([[2, 8, 8, 2]], [0.5], [0.01])
    view2 = _build_view([[2, 8, 8, 2]], [0.5], [0.01])
    overlap = ecdf_overlap_integral(view1, view2, np.array([0], dtype=np.intp), grid_size=512)
    result = ecdf_effect_size(
        delta_mean=np.array([0.0]),
        var1=np.array([0.01]),
        var2=np.array([0.01]),
        ecdf_view1=view1,
        ecdf_view2=view2,
        position_indices=np.array([0], dtype=np.intp),
        lambda_var=2.0,
        grid_size=512,
    )
    assert np.isclose(overlap[0], 1.0, atol=1e-3)
    assert np.isclose(result["effect_size"][0], 0.0, atol=1e-8)


def test_separated_distributions_raise_effect_size():
    view1 = _build_view([[20, 1, 0, 0]], [0.05], [0.002])
    view2 = _build_view([[0, 0, 1, 20]], [0.95], [0.002])
    result = ecdf_effect_size(
        delta_mean=np.array([0.9]),
        var1=np.array([0.002]),
        var2=np.array([0.002]),
        ecdf_view1=view1,
        ecdf_view2=view2,
        position_indices=np.array([0], dtype=np.intp),
        lambda_var=1.0,
        grid_size=512,
    )
    assert result["overlap"][0] < 0.2
    assert result["effect_size"][0] > 0.5


def test_same_mean_different_shape_keeps_biological_score_low():
    result = effect_size_from_components(
        delta_mean=np.array([0.01]),
        overlap=np.array([0.1]),
        var1=np.array([0.01]),
        var2=np.array([0.01]),
        lambda_var=1.0,
    )
    assert result["effect_size"][0] < 0.01


def test_variance_penalty_is_symmetric():
    result_a = effect_size_from_components(
        delta_mean=np.array([0.4]),
        overlap=np.array([0.2]),
        var1=np.array([0.01]),
        var2=np.array([0.09]),
        lambda_var=2.0,
    )
    result_b = effect_size_from_components(
        delta_mean=np.array([0.4]),
        overlap=np.array([0.2]),
        var1=np.array([0.09]),
        var2=np.array([0.01]),
        lambda_var=2.0,
    )
    assert np.isclose(result_a["effect_size"][0], result_b["effect_size"][0], atol=1e-10)
    baseline = effect_size_from_components(
        delta_mean=np.array([0.4]),
        overlap=np.array([0.2]),
        var1=np.array([0.01]),
        var2=np.array([0.01]),
        lambda_var=2.0,
    )
    assert result_a["effect_size"][0] < baseline["effect_size"][0]
