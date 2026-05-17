"""Tests for split_sample_h5_by_context."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from methyl_utils import MethylSample  # noqa: E402

from split_sample_h5_by_context import (  # noqa: E402
    parse_chromosome_list,
    discover_source_files,
    split_one_chromosome,
    _is_centroid_h5,
)


def _write_combined_sample(path: Path, rows_per_context: int = 3) -> None:
    """Write 1.h5 with CG, CHG, CHH rows (tnc context bands 0, 32, 64)."""
    pos = np.arange(rows_per_context * 3, dtype=np.uint32) + 1
    mC = np.ones(len(pos), dtype=np.uint32)
    uC = np.ones(len(pos), dtype=np.uint32) * 2
    tnc = np.array(
        [0] * rows_per_context + [32] * rows_per_context + [64] * rows_per_context,
        dtype=np.uint8,
    )
    df = pd.DataFrame({"pos": pos, "mC": mC, "uC": uC, "tnc": tnc})
    MethylSample(df, {"sample_id": "test"}).save_to_h5(path, compressed=False)


def test_split_exports_contexts_and_archives_source(tmp_path: Path) -> None:
    sample_dir = tmp_path / "sample_a"
    sample_dir.mkdir()
    source = sample_dir / "1.h5"
    _write_combined_sample(source, rows_per_context=5)

    res = split_one_chromosome(
        sample_dir,
        "1",
        source,
        contexts=["CG", "CHG", "CHH"],
        overwrite=False,
        dry_run=False,
        skip_empty=True,
        archive_source=True,
        owner_uid=0,
        owner_gid=0,
    )
    assert res.status == "ok"
    assert "archived 1.h5 -> 1.h5.bak" in res.message
    assert not source.is_file()
    assert (sample_dir / "1.h5.bak").is_file()
    for ctx in ("CG", "CHG", "CHH"):
        out = sample_dir / f"1-{ctx}.h5"
        assert out.is_file()
        part = MethylSample.load_from_h5(out)
        assert len(part) == 5
        assert part.context_metadata == ctx


def test_split_skips_when_targets_exist(tmp_path: Path) -> None:
    sample_dir = tmp_path / "sample_b"
    sample_dir.mkdir()
    source = sample_dir / "1.h5"
    _write_combined_sample(source, rows_per_context=2)
    (sample_dir / "1-CG.h5").write_bytes(b"x")
    (sample_dir / "1-CHG.h5").write_bytes(b"x")
    (sample_dir / "1-CHH.h5").write_bytes(b"x")

    res = split_one_chromosome(
        sample_dir,
        "1",
        source,
        contexts=["CG", "CHG", "CHH"],
        overwrite=False,
        dry_run=False,
        skip_empty=True,
        archive_source=True,
        owner_uid=0,
        owner_gid=0,
    )
    assert res.status == "skipped"
    assert source.is_file()


def test_discover_source_files_ignores_pipeline_names(tmp_path: Path) -> None:
    sample_dir = tmp_path / "sample_c"
    sample_dir.mkdir()
    _write_combined_sample(sample_dir / "1.h5", rows_per_context=1)
    (sample_dir / "1-CG.h5").write_bytes(b"already")
    (sample_dir / "10.h5").write_bytes(b"ten")

    found = discover_source_files(sample_dir, {"1", "10"})
    chroms = {c for c, _ in found}
    assert chroms == {"1", "10"}
    assert not any(p.name == "1-CG.h5" for _, p in found)


def test_centroid_h5_skipped(tmp_path: Path) -> None:
    import h5py

    sample_dir = tmp_path / "sample_d"
    sample_dir.mkdir()
    path = sample_dir / "1.h5"
    with h5py.File(path, "w") as f:
        grp = f.create_group("methylation_data")
        grp.create_dataset("pos", data=np.array([1], dtype=np.uint32))
        grp.create_dataset("tnc", data=np.array([0], dtype=np.uint8))
        grp.create_dataset("N", data=np.array([1], dtype=np.uint32))
        grp.create_dataset("Sx", data=np.array([0.0], dtype=np.float32))
        grp.create_dataset("Sx2", data=np.array([0.0], dtype=np.float32))
        grp.create_dataset("Sm", data=np.array([1], dtype=np.uint32))
        grp.create_dataset("Su", data=np.array([0], dtype=np.uint32))
        grp.create_dataset("Sc2", data=np.array([0], dtype=np.uint32))
        grp.create_dataset("Swx2", data=np.array([0.0], dtype=np.float32))
        grp.attrs["bins"] = 1
        grp.create_dataset("bin_counts", data=np.zeros((1, 1), dtype=np.uint64))

    assert _is_centroid_h5(path)
    res = split_one_chromosome(
        sample_dir,
        "1",
        path,
        contexts=["CG"],
        overwrite=False,
        dry_run=False,
        skip_empty=True,
        archive_source=True,
        owner_uid=0,
        owner_gid=0,
    )
    assert res.status == "skipped"
    assert path.is_file()


def test_parse_chromosome_list_normalizes_sex_chromosome_case() -> None:
    parsed = parse_chromosome_list("1,x,y,10")
    assert parsed == ["1", "X", "Y", "10"]
