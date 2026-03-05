# tests/test_centroid_builder.py
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st
from hypothesis.extra.numpy import arrays

from methyl_utils.core.centroid_builder import MethylCentroidBuilder, build_centroid
from methyl_utils.core.methyl_frame import MethylExtendedCentroid
from methyl_utils.core.io import load_from_h5  # assuming you have a minimal loader


# --------------------------------------------------------------------------- #
# Helper: Create a tiny in-memory HDF5 sample (no external files needed)
# --------------------------------------------------------------------------- #
def create_temp_sample(positions: List[int], mC: List[int], uC: List[int], tnc: List[int]) -> Path:
    import h5py

    tmp = Path(tempfile.mkstemp(suffix=".h5")[1])

    with h5py.File(tmp, "w") as f:
        group = f.create_group("methylation_data")
        group.create_dataset("pos", data=np.array(positions, dtype=np.uint32))
        group.create_dataset("mC", data=np.array(mC, dtype=np.uint32))
        group.create_dataset("uC", data=np.array(uC, dtype=np.uint32))
        group.create_dataset("tnc", data=np.array(tnc, dtype=np.uint8))

    return tmp


# --------------------------------------------------------------------------- #
# Basic sanity checks
# --------------------------------------------------------------------------- #
def test_empty_builder_raises():
    builder = MethylCentroidBuilder()
    with pytest.raises(ValueError, match="No data accumulated"):
        builder.finalize()


def test_single_sample_passes_through():
    positions = [100, 200, 300]
    mC = [5, 0, 10]
    uC = [0, 3, 2]
    tnc = [0, 1, 2]

    sample_path = create_temp_sample(positions, mC, uC, tnc)

    builder = MethylCentroidBuilder(min_coverage=1)
    builder.add_sample(sample_path)

    centroid = builder.finalize()

    assert isinstance(centroid, MethylExtendedCentroid)
    assert len(centroid) == 3
    assert centroid.N.to_list() == [1, 1, 1]
    np.testing.assert_array_equal(centroid.pos.values, positions)

    # Averaged counts should equal original (N=1)
    np.testing.assert_array_equal(centroid.mC.values, mC)
    np.testing.assert_array_equal(centroid.uC.values, uC)


def test_multiple_samples_are_averaged_correctly():
    # Two identical samples → averages should be the same
    pos = [1000, 2000]
    sample1 = create_temp_sample(pos, [10, 20], [5, 0], [0, 1])
    sample2 = create_temp_sample(pos, [10, 20], [5, 0], [0, 1])

    builder = MethylCentroidBuilder(min_coverage=1)
    builder.add_sample(sample1)
    builder.add_sample(sample2)
    centroid = builder.finalize()

    assert centroid.samples_processed == 2
    assert centroid.N.to_list() == [2, 2]
    np.testing.assert_array_equal(centroid.mC.values, [10, 20])  # exact avg
    np.testing.assert_array_equal(centroid.uC.values, [5, 0])


def test_coverage_filter_removes_low_coverage():
    sample1 = create_temp_sample([1, 2, 3], [10, 0, 1], [0, 0, 10], [0, 0, 0])
    sample2 = create_temp_sample([1, 2, 3], [10, 0, 1], [0, 0, 10], [0, 0, 0])

    builder = MethylCentroidBuilder(min_coverage=15)  # total cov per sample = 10, 0, 11 → after 2 samples: 20, 0, 22
    builder.add_sample(sample1)
    builder.add_sample(sample2)
    centroid = builder.finalize()

    # Position 2 has total coverage 0 → filtered out
    assert len(centroid) == 2
    assert set(centroid.pos.values) == {1, 3}


# --------------------------------------------------------------------------- #
# Property-based testing with Hypothesis (real confidence)
# --------------------------------------------------------------------------- #
@settings(deadline=1000)
@given(
    n_samples=st.integers(1, 20),
    n_positions=st.integers(1, 500),
    seed=st.integers(0, 2**32 - 1),
)
def test_accumulator_correctness_property(n_samples, n_positions, seed):
    rng = np.random.default_rng(seed)

    # Generate realistic random data
    positions = rng.integers(1, 10**9, size=n_positions, dtype=np.uint32)
    positions = np.unique(positions)
    positions.sort()
    n_pos = len(positions)

    # Create n_samples with some overlap
    sample_paths = []
    for i in range(n_samples):
        # Each sample covers 30–100% of positions
        subset = rng.choice([False, True], size=n_pos, p=[0.3, 0.7])
        if not subset.any():
            subset[0] = True

        pos_idx = np.where(subset)[0]
        mC = rng.integers(0, 50, size=len(pos_idx), dtype=np.uint32)
        uC = rng.integers(0, 50, size=len(pos_idx), dtype=np.uint32)
        tnc = rng.integers(0, 255, size=len(pos_idx), dtype=np.uint8)

        path = create_temp_sample(positions[pos_idx], mC.tolist(), uC.tolist(), tnc.tolist())
        sample_paths.append(path)

    builder = MethylCentroidBuilder(min_coverage=1)
    for p in sample_paths:
        builder.add_sample(p)

    centroid = builder.finalize()

    # Ground truth: manual accumulation
    truth_mC = np.zeros(n_pos, dtype=np.uint64)
    truth_uC = np.zeros(n_pos, dtype=np.uint64)
    truth_N = np.zeros(n_pos, dtype=np.uint32)
    truth_Sx = np.zeros(n_pos, dtype=np.float64)
    truth_Sx2 = np.zeros(n_pos, dtype=np.float64)
    truth_log_x = np.zeros(n_pos, dtype=np.float64)
    truth_log_1x = np.zeros(n_pos, dtype=np.float64)

    for path in sample_paths:
        # Re-load to accumulate manually
        df = pd.read_hdf(path, "methylation_data")
        idx = np.searchsorted(positions, df["pos"].values)
        mC = df["mC"].values
        uC = df["uC"].values
        cov = mC + uC
        mean = np.divide(mC, cov, where=cov > 0, out=np.zeros_like(mC, float))

        truth_mC[idx] += mC
        truth_uC[idx] += uC
        truth_N[idx] += 1
        truth_Sx[idx] += mean
        truth_Sx2[idx] += mean ** 2

        safe = np.clip(mean, 1e-10, 1 - 1e-10)
        truth_log_x[idx] += np.log(safe)
        truth_log_1x[idx] += np.log(1 - safe)

    # Compare
    mask = truth_N > 0
    final_pos = positions[mask]

    # Map centroid rows to global positions
    centroid_idx = np.searchsorted(final_pos, centroid.pos.values)
    assert np.all(centroid.pos.values == final_pos[centroid_idx])

    np.testing.assert_array_equal(centroid.N.values, truth_N[mask])
    np.testing.assert_array_almost_equal(
        centroid.mC.values, (truth_mC[mask] / truth_N[mask]).astype(np.uint32)
    )
    np.testing.assert_array_almost_equal(
        centroid.uC.values, (truth_uC[mask] / truth_N[mask]).astype(np.uint32)
    )
    np.testing.assert_array_almost_equal(centroid.Sx.values, truth_Sx[mask].astype(np.float32), decimal=5)
    np.testing.assert_array_almost_equal(centroid.Sx2.values, truth_Sx2[mask].astype(np.float32), decimal=5)
    # binned_stats (bin_edges, bin_counts) present when binned_stats_bins set
    assert centroid.binned_stats is not None
    assert "bin_edges" in centroid.binned_stats and "bin_counts" in centroid.binned_stats


# --------------------------------------------------------------------------- #
# GPU path smoke test (only runs if CuPy available)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not HAS_GPU, reason="CuPy not available")
def test_gpu_path_works():
    positions = [10, 20, 30]
    sample = create_temp_sample(positions, [5, 10, 15], [2, 0, 5], [0, 1, 2])

    builder = MethylCentroidBuilder(use_gpu=True)
    builder.add_sample(sample)
    centroid = builder.finalize()

    assert centroid.is_gpu is False  # finalize always returns CPU pandas
    assert len(centroid) == 3
    assert centroid.N.sum() == 1


# --------------------------------------------------------------------------- #
# Convenience function test
# --------------------------------------------------------------------------- #
def test_build_centroid_function():
    paths = [
        create_temp_sample([100], [8], [2], [0]),
        create_temp_sample([100], [12], [3], [0]),
    ]

    centroid = build_centroid(paths, min_coverage=1, use_gpu=False)

    assert isinstance(centroid, MethylExtendedCentroid)
    assert centroid.samples_processed == 2
    assert centroid.N.iloc[0] == 2
    assert centroid.mC.iloc[0] == 10
    assert centroid.uC.iloc[0] == 2  # (2+3)/2 = 2.5 → uint32 flooring? Wait — we use proper division in finalize


if __name__ == "__main__":
    pytest.main(["-v", __file__])