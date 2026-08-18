"""Positions present in sample.pos but with NaN methylation must not be marked available."""

import numpy as np

from methyl_classifier.utils.data_loader import DataLoader


def test_nan_at_matched_position_is_unavailable():
    class FakeSample:
        sample_type = "test"
        is_centroid = False

        pos = np.array([1000, 2000, 3000], dtype=np.uint32)

        def get_methylation_levels(self):
            return np.array([0.25, np.nan, 0.75], dtype=np.float64)

        def get_coverage(self):
            return np.array([10, 10, 10], dtype=np.int64)

    sample = FakeSample()
    dmps = np.array([1000, 2000, 4000], dtype=np.uint32)
    feats, avail, stats = DataLoader.extract_sample_features(sample, dmps)
    assert bool(avail[0])
    assert not avail[1]  # matched 2000 but NaN -> ignore
    assert not avail[2]  # no position 4000
    assert stats["missing_positions"] == 2
    assert np.isfinite(feats[0])
    assert feats[1] == 0.5  # placeholder only


def test_extract_sample_features_without_applier_is_identity():
    class FakeSample:
        sample_type = "test"
        is_centroid = False
        pos = np.array([10, 20], dtype=np.uint32)

        def lookup_at_positions(self, dmp_arr, min_coverage=1, missing_value=np.nan):
            values = np.array([0.2, 0.8], dtype=np.float64)
            mask = np.array([True, True])
            return values, mask

        def get_coverage(self):
            return np.array([10, 10], dtype=np.int64)

    sample = FakeSample()
    feats, avail, _ = DataLoader.extract_sample_features(
        sample, np.array([10, 20], dtype=np.uint32)
    )
    assert avail.all()
    np.testing.assert_allclose(feats, [0.2, 0.8])

