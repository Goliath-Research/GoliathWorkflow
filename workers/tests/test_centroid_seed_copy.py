"""Tests for shared MC centroid seed baseline copy."""

from __future__ import annotations

from pathlib import Path

from methyl_validation.project_gen import copy_centroid_seed_baseline


def test_copy_centroid_seed_baseline_copies_tree(tmp_path: Path) -> None:
    seed = tmp_path / "seed" / "controls" / "healthy" / "healthy"
    seed.mkdir(parents=True)
    (seed / "21-CG.h5").write_bytes(b"seed")
    out = tmp_path / "run_0001" / "centroids" / "controls" / "healthy" / "healthy"
    assert copy_centroid_seed_baseline(seed, out)
    assert (out / "21-CG.h5").is_file()


def test_copy_centroid_seed_baseline_missing_seed_returns_false(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert not copy_centroid_seed_baseline(tmp_path / "missing", out)
