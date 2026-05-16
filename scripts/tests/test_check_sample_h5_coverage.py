"""Tests for check_sample_h5_coverage."""

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_sample_h5_coverage import AUTOSOMES, check_sample_dir, list_sample_dirs  # noqa: E402


def _touch(sample_dir: Path, chrom: str, ctx: str = "CG") -> None:
    (sample_dir / f"{chrom}-{ctx}.h5").write_bytes(b"")


def test_auto_female_x_only(tmp_path: Path) -> None:
    sdir = tmp_path / "female_sample"
    sdir.mkdir()
    for c in AUTOSOMES:
        _touch(sdir, c)
    _touch(sdir, "X")
    result = check_sample_dir(sdir, "CG", sex_mode="auto")
    assert result.complete
    assert result.sex_profile == "female"
    assert "Y-CG.h5" not in result.missing


def test_auto_male_x_and_y(tmp_path: Path) -> None:
    sdir = tmp_path / "male_sample"
    sdir.mkdir()
    for c in AUTOSOMES:
        _touch(sdir, c)
    _touch(sdir, "X")
    _touch(sdir, "Y")
    result = check_sample_dir(sdir, "CG", sex_mode="auto")
    assert result.complete
    assert result.sex_profile == "male"


def test_list_sample_dirs(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "readme.txt").write_text("x")
    assert len(list_sample_dirs(tmp_path)) == 2
