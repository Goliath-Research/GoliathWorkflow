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
