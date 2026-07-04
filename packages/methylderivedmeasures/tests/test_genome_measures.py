"""Tests for genome-wide derived measures."""

from __future__ import annotations

import numpy as np

from methyl_derived_measures.core.genome_measures import (
    _adjacent_disagreement_fraction,
    _binary_entropy_mean,
    _weighted_fraction,
)


def test_binary_entropy_and_weighted_fraction():
    vals = np.array([0.1, 0.9, 0.5], dtype=np.float64)
    w = np.array([1.0, 1.0, 1.0], dtype=np.float64)
    assert np.isfinite(_binary_entropy_mean(vals, w))
    assert 0.0 <= _weighted_fraction(vals, w, 0.0, 0.2) <= 1.0


def test_adjacent_disagreement_fraction():
    pos = np.array([10, 11, 12], dtype=np.uint32)
    vals = np.array([0.1, 0.9, 0.2], dtype=np.float64)
    cov = np.array([5, 5, 5], dtype=np.int64)
    frac = _adjacent_disagreement_fraction(
        pos, vals, cov, min_coverage=1, threshold=0.25
    )
    assert np.isfinite(frac)
