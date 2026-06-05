# tests/test_io.py
"""Tests for methyl_utils.core.io, including position-subset loading (binary search in H5)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import h5py
import numpy as np
import pytest

from methyl_utils.core.io import (
    _indices_for_positions,
    _indices_for_positions_h5,
    load_from_h5,
)
from methyl_utils.core.methyl_frame import MethylCentroid, MethylSample


def test_indices_for_positions_h5_matches_full_load():
    """_indices_for_positions_h5 returns same indices as _indices_for_positions(loaded_pos, positions)."""
    # Sorted pos in file (e.g. 100 positions)
    pos_full = np.arange(1000, 1100, dtype=np.uint32)
    with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        with h5py.File(path, "w") as f:
            g = f.create_group("methylation_data")
            g.create_dataset("pos", data=pos_full)
            g.create_dataset("mC", data=np.zeros(len(pos_full), dtype=np.uint32))
            g.create_dataset("uC", data=np.ones(len(pos_full), dtype=np.uint32))
            g.create_dataset("tnc", data=np.zeros(len(pos_full), dtype=np.uint8))

        with h5py.File(path, "r") as f:
            pos_dset = f["methylation_data"]["pos"]
            # Subset of positions + one not in file (999)
            positions = np.array([1005, 1020, 1030, 999, 1080], dtype=np.uint32)
            idx_h5 = _indices_for_positions_h5(pos_dset, positions)

        # Compare to in-memory reference
        pos_arr = np.asarray(pos_full, dtype=np.uint32)
        idx_ref = _indices_for_positions(pos_arr, positions)
        np.testing.assert_array_equal(idx_h5, idx_ref)
        # 999 is not in file, so we get 4 indices (for 1005, 1020, 1030, 1080)
        assert len(idx_h5) == 4
    finally:
        path.unlink(missing_ok=True)


def test_indices_for_positions_h5_empty_positions():
    """_indices_for_positions_h5 with empty positions returns empty array."""
    pos_full = np.array([1, 2, 3], dtype=np.uint32)
    with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        with h5py.File(path, "w") as f:
            g = f.create_group("methylation_data")
            g.create_dataset("pos", data=pos_full)
            g.create_dataset("mC", data=np.zeros(3, dtype=np.uint32))
            g.create_dataset("uC", data=np.ones(3, dtype=np.uint32))
            g.create_dataset("tnc", data=np.zeros(3, dtype=np.uint8))
        with h5py.File(path, "r") as f:
            pos_dset = f["methylation_data"]["pos"]
            idx = _indices_for_positions_h5(pos_dset, np.array([], dtype=np.uint32))
        assert idx.shape == (0,)
        assert idx.dtype == np.int32
    finally:
        path.unlink(missing_ok=True)


def test_load_from_h5_positions_subset_equals_full_then_filter():
    """load_from_h5(path, positions=...) returns same data as loading full then filtering by positions."""
    pos_full = np.array([10, 20, 30, 40, 50, 60, 70, 80, 90, 100], dtype=np.uint32)
    mC = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=np.uint32)
    uC = np.array([9, 8, 7, 6, 5, 4, 3, 2, 1, 0], dtype=np.uint32)
    tnc = np.zeros(10, dtype=np.uint8)
    with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        with h5py.File(path, "w") as f:
            g = f.create_group("methylation_data")
            g.create_dataset("pos", data=pos_full)
            g.create_dataset("mC", data=mC)
            g.create_dataset("uC", data=uC)
            g.create_dataset("tnc", data=tnc)

        positions = np.array([20, 50, 90], dtype=np.uint32)
        subset = load_from_h5(path, positions=positions)
        full = load_from_h5(path)

        # Subset should have only the requested positions that exist (all three exist)
        np.testing.assert_array_equal(np.sort(subset.pos.values), positions)
        # Values at those positions should match full
        for p in positions:
            idx_full = np.flatnonzero(full.pos.values == p)[0]
            idx_sub = np.flatnonzero(subset.pos.values == p)[0]
            assert subset.mC.values[idx_sub] == full.mC.values[idx_full]
            assert subset.uC.values[idx_sub] == full.uC.values[idx_full]
    finally:
        path.unlink(missing_ok=True)


def test_methylsample_load_from_h5_with_indices():
    """MethylSample.load_from_h5 supports indexed loads via shared API."""
    pos_full = np.array([10, 20, 30, 40], dtype=np.uint32)
    mC = np.array([1, 2, 3, 4], dtype=np.uint32)
    uC = np.array([9, 8, 7, 6], dtype=np.uint32)
    tnc = np.zeros(4, dtype=np.uint8)
    with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        with h5py.File(path, "w") as f:
            g = f.create_group("methylation_data")
            g.create_dataset("pos", data=pos_full)
            g.create_dataset("mC", data=mC)
            g.create_dataset("uC", data=uC)
            g.create_dataset("tnc", data=tnc)

        loaded = MethylSample.load_from_h5(path, indices=np.array([0, 2], dtype=np.int32))
        np.testing.assert_array_equal(np.asarray(loaded.pos.values, dtype=np.uint32), np.array([10, 30], dtype=np.uint32))
        np.testing.assert_array_equal(np.asarray(loaded.mC.values, dtype=np.uint32), np.array([1, 3], dtype=np.uint32))
    finally:
        path.unlink(missing_ok=True)


def test_methylsample_lookup_at_positions_reference_order_and_coverage():
    """lookup_at_positions preserves reference order and applies coverage threshold."""
    pos = np.array([10, 20, 30], dtype=np.uint32)
    mC = np.array([5, 0, 2], dtype=np.uint32)
    uC = np.array([5, 1, 0], dtype=np.uint32)
    tnc = np.zeros(3, dtype=np.uint8)
    sample = MethylSample.from_sample_data(pos=pos, mC=mC, uC=uC, tnc=tnc)

    query = np.array([20, 40, 10, 30], dtype=np.uint32)
    values, availability = sample.lookup_at_positions(query, min_coverage=2, missing_value=np.nan)

    # pos=20 has coverage 1 -> unavailable, pos=40 missing -> unavailable
    assert availability.tolist() == [False, False, True, True]
    # returned in query order
    assert np.isnan(values[0])
    assert np.isnan(values[1])
    assert values[2] == pytest.approx(0.5)
    assert values[3] == pytest.approx(1.0)


def test_methylcentroid_lookup_at_positions_uses_weighted_mean():
    """Centroid lookup uses Sm/(Sm+Su), not derived mC/coverage."""
    import pandas as pd

    pos = np.array([10, 20, 30], dtype=np.uint32)
    df = pd.DataFrame(
        {
            "pos": pos,
            "tnc": np.zeros(3, dtype=np.uint8),
            "N": np.array([2, 2, 2], dtype=np.uint32),
            "Sx": np.array([1.0, 0.5, 1.5], dtype=np.float32),
            "Sx2": np.array([0.5, 0.25, 0.75], dtype=np.float32),
            "Sm": np.array([6, 0, 8], dtype=np.uint32),
            "Su": np.array([4, 10, 2], dtype=np.uint32),
            "Sc2": np.array([100, 100, 100], dtype=np.uint32),
            "Swx2": np.array([0.36, 0.0, 0.64], dtype=np.float32),
        }
    )
    centroid = MethylCentroid(df)

    query = np.array([20, 40, 10, 30], dtype=np.uint32)
    values, availability = centroid.lookup_at_positions(query, min_coverage=5, missing_value=np.nan)

    assert availability.tolist() == [True, False, True, True]
    assert np.isnan(values[1])
    assert values[0] == pytest.approx(0.0)  # Sm=0, Su=10
    assert values[2] == pytest.approx(0.6)  # 6/(6+4)
    assert values[3] == pytest.approx(0.8)  # 8/(8+2)
