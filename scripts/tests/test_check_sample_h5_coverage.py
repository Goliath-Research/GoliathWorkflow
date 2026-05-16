"""Tests for check_sample_h5_coverage."""

import os
import stat
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_sample_h5_coverage import (  # noqa: E402
    AUTOSOMES,
    _readable_h5,
    check_sample_dir,
    ensure_h5_accessible,
    list_sample_dirs,
)


def _touch(sample_dir: Path, chrom: str, ctx: str = "CG") -> Path:
    p = sample_dir / f"{chrom}-{ctx}.h5"
    p.write_bytes(b"\x00")
    return p


def _full_female(sample_dir: Path) -> None:
    for c in AUTOSOMES:
        _touch(sample_dir, c)
    _touch(sample_dir, "X")


def test_auto_female_x_only(tmp_path: Path) -> None:
    sdir = tmp_path / "female_sample"
    sdir.mkdir()
    _full_female(sdir)
    uid, gid = os.getuid(), os.getgid()
    result = check_sample_dir(
        sdir,
        "CG",
        sex_mode="auto",
        owner_uid=uid,
        owner_gid=gid,
        fix_permissions=True,
        samples_base=tmp_path,
    )
    assert result.complete
    assert result.sex_profile == "female"


def test_fix_unreadable_h5(tmp_path: Path) -> None:
    sdir = tmp_path / "fix_me"
    sdir.mkdir()
    _full_female(sdir)
    h5 = sdir / "1-CG.h5"
    h5.chmod(0o000)
    uid, gid = os.getuid(), os.getgid()
    ok, fixed = ensure_h5_accessible(
        h5, uid=uid, gid=gid, fix=True, stop_at=tmp_path
    )
    assert fixed
    assert ok
    assert _readable_h5(h5)
    h5.chmod(0o644)


def test_list_sample_dirs(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "readme.txt").write_text("x")
    assert len(list_sample_dirs(tmp_path)) == 2


def test_unknown_no_sex_chromosomes_expected_includes_sex_slot(tmp_path: Path) -> None:
    """All autos present but no X/Y: expected must not read 22/22 while incomplete."""
    sdir = tmp_path / "no_sex"
    sdir.mkdir()
    for c in AUTOSOMES:
        _touch(sdir, c)
    uid, gid = os.getuid(), os.getgid()
    result = check_sample_dir(
        sdir,
        "CG",
        sex_mode="auto",
        owner_uid=uid,
        owner_gid=gid,
        fix_permissions=True,
        samples_base=tmp_path,
    )
    assert not result.complete
    assert result.expected == len(AUTOSOMES) + 1
    assert result.found == len(AUTOSOMES)
    assert result.found < result.expected
    assert any("at least one of" in m for m in result.missing)


def test_inaccessible_reported_when_no_fix(tmp_path: Path) -> None:
    sdir = tmp_path / "locked"
    sdir.mkdir()
    _full_female(sdir)
    h5 = sdir / "1-CG.h5"
    h5.chmod(0o000)
    uid, gid = os.getuid(), os.getgid()
    try:
        result = check_sample_dir(
            sdir,
            "CG",
            sex_mode="auto",
            owner_uid=uid,
            owner_gid=gid,
            fix_permissions=False,
            samples_base=tmp_path,
        )
        assert "1-CG.h5" in result.inaccessible
        assert not result.complete
    finally:
        h5.chmod(0o644)
