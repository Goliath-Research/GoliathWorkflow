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
